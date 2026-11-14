"""Three ways to subtract "the sky as it was" from a SPHEREx frame.

All three return the same thing (:class:`Diff`: residual, sigma and signal-to-noise cubes)
so they can be compared like for like:

* ``naive``     frame minus the same-detector frame nearest in time from another survey
                pass - what a plain blink comparator does. The two frames usually differ
                in wavelength, so colour shows up as "change".
* ``gated``     frame minus the other-pass frame whose centre wavelength is closest, and
                only if it is closer than ``gate`` (0.5) bandwidths; otherwise the frame
                gets no result at all. This is the wavelength gating other tools use.
* ``corrected`` frame minus the chromatic template (see ``template.py``).

The same three calibration steps are applied to every mode, so that none is favoured:

1. a per-frame background offset, measured on faint pixels, is removed;
2. a per-frame scale of the pixel noise, measured on faint pixels, makes the SNR of
   empty sky unit variance;
3. "star noise": SPHEREx images are undersampled, so a star's pixel values change with
   the sub-pixel pointing by tens of percent. This error is proportional to the local
   spatial contrast of the subtracted image; its amplitude is fitted per detector from
   the data (robustly) and added to sigma. ``star_noise=False`` gives the plain
   statistical sigma a naive subtraction would quote.

For the corrected mode the star-noise term is combined with the per-pixel empirical
model error of the template (the larger of the two is used). The pair modes have no such
map, so this is an extra term only the template gets; ``plain_modes`` and
``corrected_diff(model_error=False)`` give the comparisons without it.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi

from .frames import BAD_HARD, BAD_SOFT, Field
from .template import Template, build_template

MODES = ("naive", "gated", "corrected")
GATE = 0.5  # maximum |wavelength difference| / bandwidth accepted by the gated mode
FAINT_SNR = 3.0  # a pixel is "faint" if the subtracted image is below this many sigma
BRIGHT_CONTRAST = 10.0  # pixels used to fit the star-noise amplitude: contrast > 10 sigma
MIN_PIXELS = 100  # minimum number of pixels for a per-frame calibration
UJY_PER_MJYSR = 889.86  # microJy per 6.15 arcsec pixel for 1 MJy/sr


@dataclass
class Diff:
    """Result of one difference mode. Cubes are (N, n, n) float32, NaN = undefined."""

    mode: str
    resid: np.ndarray  # MJy/sr
    sigma: np.ndarray  # MJy/sr, 1-sigma uncertainty of ``resid``
    snr: np.ndarray
    static: np.ndarray  # the image that was subtracted (partner frame or template)
    mismatch: np.ndarray  # wavelength distance to the subtracted data, in bandwidths
    partner: np.ndarray  # (N,) index of the partner frame, -1 if none / not applicable
    usable: np.ndarray  # (N,) bool: the frame has a result
    info: dict = field(default_factory=dict)


def _mad_std(a: np.ndarray) -> float:
    a = a[np.isfinite(a)]
    if a.size == 0:
        return float("nan")
    return float(1.4826 * np.median(np.abs(a - np.median(a))))


def naive_partners(f: Field) -> np.ndarray:
    """Same detector, another survey pass, nearest in time. -1 if there is none."""
    out = np.full(len(f), -1, dtype=np.int32)
    for i in range(len(f)):
        cand = np.flatnonzero((f.det == f.det[i]) & (f.campaign != f.campaign[i]))
        if len(cand):
            out[i] = cand[np.argmin(np.abs(f.mjd[cand] - f.mjd[i]))]
    return out


def gated_partners(f: Field, gate: float = GATE) -> np.ndarray:
    """Other-pass frame closest in centre wavelength, if within ``gate`` bandwidths."""
    out = np.full(len(f), -1, dtype=np.int32)
    lam0 = f.lam0.astype(np.float64)
    c = f.n // 2
    bw0 = f.bw[:, c, c].astype(np.float64)
    for i in range(len(f)):
        cand = np.flatnonzero((f.campaign != f.campaign[i]) & np.isfinite(lam0))
        if len(cand) == 0 or not np.isfinite(lam0[i]) or not bw0[i] > 0:
            continue
        d = np.abs(lam0[cand] - lam0[i])
        j = int(np.argmin(d))
        if d[j] < gate * bw0[i]:
            out[i] = cand[j]
    return out


def mismatch_map(f: Field, i: int, j: int) -> np.ndarray:
    """Per-pixel wavelength mismatch of frames i and j: (lam_i - lam_j) / bandwidth_i."""
    with np.errstate(all="ignore"):
        return ((f.lam[i] - f.lam[j]) / f.bw[i]).astype(np.float32)


def local_contrast(static: np.ndarray) -> np.ndarray:
    """Max minus min of each pixel's 3x3 neighbourhood: how much a sub-pixel shift matters."""
    filled = np.nan_to_num(static, nan=0.0)
    size = (1, 3, 3) if static.ndim == 3 else (3, 3)
    hi = ndi.maximum_filter(filled, size=size, mode="nearest")
    lo = ndi.minimum_filter(filled, size=size, mode="nearest")
    return (hi - lo).astype(np.float32)


def _remove_background(resid, faint):
    """Subtract the per-frame median of the faint pixels. Returns the offsets."""
    off = np.zeros(len(resid), dtype=np.float32)
    for i in range(len(resid)):
        m = faint[i] & np.isfinite(resid[i])
        if m.sum() >= MIN_PIXELS:
            off[i] = np.median(resid[i][m])
    resid -= off[:, None, None]
    return off


def fit_star_noise(resid, var_stat, contrast, det, exclude=None) -> dict[int, float]:
    """Per detector: robust amplitude g with  star error = g * local contrast.

    ``exclude`` (boolean cube) keeps pixels out of the fit, e.g. the surroundings of a
    known variable or moving star whose real change must not be mistaken for star noise.
    """
    out: dict[int, float] = {}
    with np.errstate(all="ignore"):
        bright = (contrast > BRIGHT_CONTRAST * np.sqrt(var_stat)) & np.isfinite(resid)
        ratio = resid / contrast
    if exclude is not None:
        bright &= ~exclude
    for d in np.unique(det):
        m = bright[det == d]
        r = ratio[det == d][m]
        out[int(d)] = _mad_std(r) if r.size >= MIN_PIXELS else 0.0
    return out


def _noise_scale(snr, faint):
    """Per-frame robust width of the SNR of faint pixels (1 if it cannot be measured)."""
    sc = np.ones(len(snr), dtype=np.float32)
    for i in range(len(snr)):
        m = faint[i] & np.isfinite(snr[i])
        if m.sum() >= MIN_PIXELS:
            s = _mad_std(snr[i][m])
            if np.isfinite(s) and s > 0:
                sc[i] = np.clip(s, 0.5, 5.0)
    return sc


def calibrate(f: Field, mode: str, resid, var_stat, static, mismatch, partner, usable,
              local_var=None, star_noise: bool = True, match_background: bool = True,
              rescale: bool = True, exclude: np.ndarray | None = None) -> Diff:
    """Common calibration of a raw difference (see the module docstring)."""
    resid = resid.astype(np.float32, copy=True)
    with np.errstate(all="ignore"):
        faint = np.abs(static) < FAINT_SNR * np.sqrt(var_stat)
    info: dict = {"star_noise": star_noise}
    if match_background:
        info["offset"] = _remove_background(resid, faint)
    var = var_stat.astype(np.float32, copy=True)
    if rescale:  # the scale applies to the pixel noise only, not to the star-noise term
        with np.errstate(all="ignore"):
            sc = _noise_scale(resid / np.sqrt(var), faint)
        var *= (sc * sc)[:, None, None]
        info["noise_scale"] = sc
    if star_noise:
        contrast = local_contrast(static)
        gains = fit_star_noise(resid, var_stat, contrast, f.det, exclude)
        g = np.array([gains[int(d)] for d in f.det], dtype=np.float32)[:, None, None]
        star_var = (g * contrast) ** 2
        if local_var is not None:
            star_var = np.fmax(star_var, local_var)
        var = var + star_var
        info["star_gain"] = gains
    elif local_var is not None:
        var = var + np.nan_to_num(local_var)
    with np.errstate(all="ignore"):
        sigma = np.sqrt(var)
        snr = resid / sigma
    bad =~np.isfinite(snr)
    resid[bad] = np.nan
    sigma[bad] = np.nan
    return Diff(mode, resid, sigma.astype(np.float32), snr.astype(np.float32),
                static.astype(np.float32), mismatch.astype(np.float32), partner, usable, info)


def pair_difference(f: Field, partner: np.ndarray, mode: str, **kw) -> Diff:
    """Frame minus its partner frame, for every frame that has one."""
    shape = f.img.shape
    has = partner >= 0
    j = np.where(has, partner, 0)
    okp = (
        np.isfinite(f.img[j]) & np.isfinite(f.var[j])
        & ((f.flags[j] & (BAD_SOFT | BAD_HARD)) == 0) & has[:, None, None]
    )
    static = np.where(okp, f.img[j], np.nan)
    resid = f.img - static
    var_stat = np.where(okp, f.var + f.var[j], np.nan)
    with np.errstate(all="ignore"):
        mism = np.where(has[:, None, None], (f.lam - f.lam[j]) / f.bw, np.nan)
    usable = has & (np.isfinite(resid).reshape(shape[0], -1).mean(axis=1) >= 0.5)
    return calibrate(f, mode, resid, var_stat, static, mism, partner.astype(np.int32),
                     usable, **kw)


def naive_diff(f: Field, **kw) -> Diff:
    return pair_difference(f, naive_partners(f), "naive", **kw)


def gated_diff(f: Field, gate: float = GATE, **kw) -> Diff:
    return pair_difference(f, gated_partners(f, gate), "gated", **kw)


def corrected_diff(f: Field, tpl: Template | None = None, model_error: bool = True,
                   **kw) -> Diff:
    """Frame minus chromatic template; sigma includes the empirical model error.

    ``model_error=False`` leaves the template's per-pixel model-error map out of sigma, so
    that the mode is calibrated exactly like the pair modes (with ``star_noise=False``
    this is the purely statistical sigma).
    """
    tpl = tpl or build_template(f)
    resid = f.img - tpl.pred
    var_stat = f.var + tpl.var
    # each reference sample scatters by model_err around the fit, and so does the target
    local = None
    if model_error:
        with np.errstate(all="ignore"):
            local = tpl.model_err**2 * (1.0 + 1.0 / np.maximum(tpl.n_eff, 1.0))
    partner = np.full(len(f), -1, dtype=np.int32)
    d = calibrate(f, "corrected", resid, var_stat, tpl.pred, tpl.nearest, partner,
                  tpl.usable(), local_var=local, **kw)
    d.info["template_mode"] = tpl.mode
    d.info["model_error"] = model_error
    return d


def plain_modes(f: Field, tpl: Template | None = None) -> dict[str, Diff]:
    """All three modes with ONE purely statistical sigma: no star-noise term for anyone
    and no model-error map for the template. This is the like-for-like "plain" baseline."""
    tpl = tpl or build_template(f)
    return {"naive": naive_diff(f, star_noise=False), "gated": gated_diff(f, star_noise=False),
            "corrected": corrected_diff(f, tpl, model_error=False, star_noise=False)}


def difference(f: Field, mode: str, tpl: Template | None = None, **kw) -> Diff:
    """Dispatch on ``mode`` (one of :data:`MODES`)."""
    if mode == "naive":
        return naive_diff(f, **kw)
    if mode == "gated":
        return gated_diff(f, **kw)
    if mode == "corrected":
        return corrected_diff(f, tpl, **kw)
    raise ValueError(f"unknown difference mode {mode!r}")


def all_modes(f: Field, tpl: Template | None = None, **kw) -> dict[str, Diff]:
    tpl = tpl or build_template(f)
    return {m: difference(f, m, tpl, **kw) for m in MODES}
