"""Chromatic template: what a static sky would look like in each frame.

A SPHEREx Level-2 frame is taken through a linear variable filter, so every pixel of every
frame has its own wavelength. For a target frame ``t`` we predict, pixel by pixel, the
brightness a *static* sky would have at that pixel's wavelength ``lam_t(p)``. The prediction
uses only frames from the OTHER survey passes, so anything that moved or varied between
passes is absent from the prediction and survives the subtraction.

Method, per sky pixel: weighted local-linear regression in wavelength over the reference
samples of that pixel, Gaussian kernel of width ``kernel * bw`` (bw = local filter
bandwidth), inverse-variance weights, one robust reweighting pass. The kernel starts at
half that width and is widened (x2, x4, x8) only where too few samples fall inside it,
so a densely sampled spectrum is followed closely and a sparse one still gets a fit.

Besides the prediction and its statistical variance we return an EMPIRICAL model-error
map: the excess scatter of the reference samples around the local fit. SPHEREx images are
undersampled, so the core of a bright star changes from frame to frame with the sub-pixel
pointing even at a fixed wavelength; that scatter (and any real spectral structure the
local line cannot follow) is measured from the data instead of being assumed.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .frames import BAD_HARD, BAD_SOFT, Field

KERNEL_SCALES = (0.5, 1.0, 2.0, 4.0)  # kernel widening steps, in units of ``kernel * bw``
ROBUST_SCALE = 2.0  # kernel width (same units) of the robust outlier pass
N_TARGET = 4.0 # effective number of references we try to reach before widening stops
MIN_REF = 2.0  # below this effective number there is no prediction
CLIP_SIGMA = 3.5  # robust pass: samples further than this from the fit are dropped
EXCESS_SIGMA = 1.5  # model error is kept only where the excess scatter is this significant
VISIT_GAP_DAYS = 0.02  # leave-one-visit-out: frames closer in time than this are one visit
CROSS_PASS = "cross-pass"
LEAVE_VISIT_OUT = "leave-one-visit-out"


@dataclass
class Template:
    """Static-sky prediction for every frame of a field. Arrays are (N, n, n) float32."""

    pred: np.ndarray  # MJy/sr, NaN where there is no prediction
    var: np.ndarray  # statistical variance of ``pred`` (propagated pixel noise)
    n_eff: np.ndarray  # effective number of reference samples behind ``pred``
    model_err: np.ndarray  # empirical excess scatter of the samples around the fit, MJy/sr
    nearest: np.ndarray  # |wavelength distance| to the nearest used sample, in bandwidths
    mode: str  # CROSS_PASS or LEAVE_VISIT_OUT
    kernel: float

    def n_ref_per_frame(self) -> np.ndarray:
        """Median effective number of references per frame (0 where no prediction)."""
        with np.errstate(all="ignore"):
            med = np.nanmedian(self.n_eff.reshape(len(self.n_eff), -1), axis=1)
        return np.nan_to_num(med, nan=0.0)

    def usable(self, min_fraction: float = 0.5) -> np.ndarray:
        """Frames where at least ``min_fraction`` of the pixels have a prediction."""
        return np.isfinite(self.pred).reshape(len(self.pred), -1).mean(axis=1) >= min_fraction


def reference_ok(f: Field) -> np.ndarray:
    """Pixels allowed to feed a template: finite, positive variance, no bad flag."""
    return (
        np.isfinite(f.img) & np.isfinite(f.var) & (f.var > 0) & np.isfinite(f.lam)
        & ((f.flags & (BAD_SOFT | BAD_HARD)) == 0)
    )


def template_mode(f: Field) -> str:
    return CROSS_PASS if len(np.unique(f.campaign)) > 1 else LEAVE_VISIT_OUT


def reference_frames(f: Field, t: int, mode: str | None = None) -> np.ndarray:
    """Indices of the frames allowed as references for target frame ``t``."""
    mode = mode or template_mode(f)
    if mode == CROSS_PASS:
        return np.flatnonzero(f.campaign != f.campaign[t])
    return np.flatnonzero(np.abs(f.mjd - f.mjd[t]) > VISIT_GAP_DAYS)


def wavelength_ranges(f: Field) -> tuple[np.ndarray, np.ndarray]:
    """Smallest and largest wavelength of every frame (NaN for an empty frame)."""
    flat = f.lam.reshape(len(f), -1)
    with np.errstate(all="ignore"):
        return np.nanmin(flat, axis=1), np.nanmax(flat, axis=1)


def _nearby(f: Field, t: int, refs: np.ndarray, reach: float, lam_range=None):
    """Keep the references whose wavelength range can reach the target's (cheap pre-cut).

    Returns the kept references and their wavelength ranges.
    """
    lo, hi = lam_range if lam_range is not None else wavelength_ranges(f)
    if not np.isfinite(lo[t]):
        return refs[:0], lo[:0], hi[:0]
    keep = refs[(hi[refs] > lo[t] - reach) & (lo[refs] < hi[t] + reach)]
    return keep, lo[keep], hi[keep]


def _local_linear(y, v, dl, k):
    """One weighted local-linear fit along axis 0.

    ``k`` holds the kernel weights (0 = sample not used). Returns the value at dl = 0, the
    slope, and the equivalent linear-smoother weights ``l`` (prediction = sum l * y).
    Falls back to a weighted mean where the samples do not span a line.
    """
    w = k / v
    s0 = w.sum(0)
    s1 = (w * dl).sum(0)
    s2 = (w * dl * dl).sum(0)
    t0 = (w * y).sum(0)
    t1 = (w * dl * y).sum(0)
    den = s0 * s2 - s1 * s1
    lin = den > 1e-4 * s0 * s2
    with np.errstate(all="ignore"):
        a = np.where(lin, (s2 * t0 - s1 * t1) / den, t0 / s0)
        b = np.where(lin, (s0 * t1 - s1 * t0) / den, 0.0)
        lw = np.where(lin, w * (s2 - s1 * dl) / den, w / s0)
    return a, b, np.nan_to_num(lw)


def _scatter(y, v, dl, k, a, b, grp=None):
    """Weighted scatter of the samples about the fit and the mean sample variance.

    With ``grp`` (the survey pass of every sample) the scatter is measured WITHIN each
    pass: the mean residual of a pass is removed first. A source that really changed
    between two reference passes then does not inflate the model error (which would hide
    exactly the change we are looking for), while pixel-phase noise, which is random
    from frame to frame inside a pass, is still measured in full.
    """
    r = y - a - b * dl
    ks = k.sum(0)
    extra = 0.0
    rs = r
    if grp is not None and len(np.unique(grp)) > 1:
        rs = r.copy()
        present = np.zeros(r.shape[1:])
        for g in np.unique(grp):
            m = grp == g
            kg = k[m].sum(0)
            with np.errstate(all="ignore"):
                rs[m] -= np.nan_to_num((k[m] * r[m]).sum(0) / kg)
            present += kg > 0
        extra = np.clip(present - 1.0, 0.0, None)  # one more fitted level per extra pass
    with np.errstate(all="ignore"):
        s2 = (k * rs * rs).sum(0) / ks
        vbar = (k * v).sum(0) / ks
        nk = ks * ks / (k * k).sum(0)
    dof = np.maximum(nk - 2.0 - extra, 0.5)  # two fitted parameters (+ pass levels)
    corr = np.clip(nk / dof, 1.0, 4.0)
    return r, s2 * corr, vbar, dof


def _excess(s2, vbar, dof):
    """Model error = scatter in excess of the pixel noise, kept only where significant.

    With a handful of samples the scatter estimate is itself noisy (relative error
    sqrt(2/dof)); an unconditional ``max(s2 - vbar, 0)`` would be biased high on empty
    sky and cost depth, so an excess below ``EXCESS_SIGMA`` of that error counts as zero.
    """
    with np.errstate(all="ignore"):
        significant = s2 > vbar * (1.0 + EXCESS_SIGMA * np.sqrt(2.0 / dof))
    return np.sqrt(np.where(significant, np.clip(s2 - vbar, 0.0, None), 0.0))


def _robust_keep(r, v, k, lw):
    """Mask of samples that survive the robust pass (leave-one-out residual vs MAD)."""
    used = k > 0.05 * k.max(axis=0, keepdims=True)
    with np.errstate(all="ignore"):
        absr = np.where(used, np.abs(r), np.nan)
        absr[0] = np.where(used.any(axis=0), absr[0], 0.0)  # avoid all-NaN columns
        mad = 1.4826 * np.nanmedian(absr, axis=0)
    mad = np.nan_to_num(mad)
    loo = r / np.clip(1.0 - lw, 0.3, None)
    return loo * loo <= CLIP_SIGMA**2 * (v + mad * mad)


def _kernel(dl, ok, h):
    with np.errstate(all="ignore"):
        u = dl / h
    return np.where(ok & (np.abs(u) < 3.0), np.exp(-0.5 * u * u), 0.0)


def _outliers(y, v, dl, ok, h):
    """Robust pass: samples that disagree with a fit through a wide kernel ``h``.

    Done once per target frame with a kernel wide enough to hold several samples, so
    that one bad sample (a cosmic ray, a mover sitting in a reference frame) cannot
    drag the fit and hide itself. Returns the mask of samples to keep.
    """
    k = _kernel(dl, ok, h)
    a, b, lw = _local_linear(y, v, dl, k)
    r = _scatter(y, v, dl, k, a, b)[0]
    return _robust_keep(r, v, k, lw) | (k == 0)


def _fit_scale(y, v, dl, ok, h, grp=None):
    """Fit with kernel width ``h`` (n, n). Returns pred, var, n_eff, model_err, nearest."""
    k = _kernel(dl, ok, h)
    a, b, lw = _local_linear(y, v, dl, k)
    _, s2, vbar, dof = _scatter(y, v, dl, k, a, b, grp)
    with np.errstate(all="ignore"):
        n_eff = 1.0 / (lw * lw).sum(0)
        nearest = np.min(np.where(k > 0, np.abs(dl), np.inf), axis=0)
    var = (lw * lw * v).sum(0)
    merr = _excess(s2, vbar, dof)
    return a, var, np.nan_to_num(n_eff, posinf=0.0), merr, nearest


def predict_frame(f: Field, t: int, refs: np.ndarray, ok: np.ndarray, kernel: float = 1.0,
                  robust: bool = True, lam_range=None, within_pass: bool = True):
    """Predict frame ``t`` from reference frames ``refs``.

    Returns (pred, var, n_eff, model_err, nearest), each (n, n); ``nearest`` is in units
    of the local bandwidth. Pixels without enough references are NaN in ``pred``.
    """
    shape = (f.n, f.n)
    nan = np.full(shape, np.nan, np.float32)
    bw = np.where(np.isfinite(f.bw[t]) & (f.bw[t] > 0), f.bw[t], np.nan).astype(np.float64)
    if not np.isfinite(bw).any():
        return nan, nan.copy(), np.zeros(shape, np.float32), nan.copy(), nan.copy()
    bw_max = float(np.nanmax(bw))
    widest = max(KERNEL_SCALES[-1], ROBUST_SCALE)
    refs, lo_r, hi_r = _nearby(f, t, refs, 3.0 * kernel * widest * bw_max, lam_range)
    if len(refs) == 0:
        return nan, nan.copy(), np.zeros(shape, np.float32), nan.copy(), nan.copy()
    with np.errstate(all="ignore"):
        lo_t, hi_t = float(np.nanmin(f.lam[t])), float(np.nanmax(f.lam[t]))
    y = np.nan_to_num(f.img[refs].astype(np.float64))
    okr = ok[refs]
    v = np.where(okr, f.var[refs], 1.0).astype(np.float64)
    dl = np.nan_to_num(f.lam[refs].astype(np.float64) - f.lam[t].astype(np.float64)[None])
    okr = okr & np.isfinite(f.lam[t])[None]

    def within(scale: float) -> np.ndarray:
        """References that can fall inside a kernel of this scale (saves most of the work)."""
        reach = 3.0 * kernel * scale * bw_max
        return np.flatnonzero((hi_r > lo_t - reach) & (lo_r < hi_t + reach))

    out = [np.full(shape, np.nan) for _ in range(5)]
    out[2] = np.zeros(shape)
    todo = np.isfinite(bw)
    if robust:
        s = within(ROBUST_SCALE)
        okr[s] &= _outliers(y[s], v[s], dl[s], okr[s], kernel * ROBUST_SCALE * bw)
    for scale in KERNEL_SCALES:
        s = within(scale)
        if len(s) == 0:
            continue
        grp = f.campaign[refs[s]] if within_pass else None
        res = _fit_scale(y[s], v[s], dl[s], okr[s], kernel * scale * bw, grp)
        take = todo & (res[2] > out[2])
        for o, r in zip(out, res, strict=True):
            o[take] = r[take]
        todo &= out[2] < N_TARGET
        if not todo.any():
            break
    bad = ~(out[2] >= MIN_REF) | ~np.isfinite(out[0])
    for i in (0, 1, 3, 4):
        out[i][bad] = np.nan
    out[4] = out[4] / bw
    return tuple(o.astype(np.float32) for o in out)


def build_template(f: Field, kernel: float = 1.0, robust: bool = True,
                   mode: str | None = None, frames: np.ndarray | None = None,
                   within_pass: bool = True) -> Template:
    """Chromatic template for every frame (or only ``frames``; the rest stay NaN).

    ``within_pass=False`` measures the model error from the scatter of all reference
    samples together instead of within each reference pass (see ``_scatter``).
    """
    mode = mode or template_mode(f)
    ok = reference_ok(f)
    shape = f.img.shape
    pred = np.full(shape, np.nan, np.float32)
    var = np.full(shape, np.nan, np.float32)
    n_eff = np.zeros(shape, np.float32)
    merr = np.full(shape, np.nan, np.float32)
    near = np.full(shape, np.nan, np.float32)
    todo = range(len(f)) if frames is None else [int(i) for i in frames]
    rng = wavelength_ranges(f)
    for t in todo:
        refs = reference_frames(f, t, mode)
        pred[t], var[t], n_eff[t], merr[t], near[t] = predict_frame(
            f, t, refs, ok, kernel, robust, rng, within_pass)
    return Template(pred, var, n_eff, merr, near, mode, kernel)


def pixel_spectrum(f: Field, tpl: Template, t: int, y: int, x: int) -> dict:
    """Reference samples and template prediction of one sky pixel (for the paper figure).

    ``samples`` are the measurements of pixel (y, x) in the reference frames of frame
    ``t``; ``curve`` is the template evaluated for every frame of ``t``'s own pass, i.e.
    the predicted static spectrum of that pixel at the wavelengths that pass observed.
    """
    refs = reference_frames(f, t, tpl.mode)
    ok = reference_ok(f)[refs, y, x]
    own = np.flatnonzero(f.campaign == f.campaign[t])
    order = own[np.argsort(f.lam[own, y, x])]
    return {
        "lam_ref": f.lam[refs, y, x][ok], "flux_ref": f.img[refs, y, x][ok],
        "err_ref": np.sqrt(f.var[refs, y, x][ok]), "det_ref": f.det[refs][ok],
        "lam_own": f.lam[order, y, x], "flux_own": f.img[order, y, x],
        "err_own": np.sqrt(f.var[order, y, x]), "pred_own": tpl.pred[order, y, x],
        "err_pred": np.sqrt(tpl.var[order, y, x] + tpl.model_err[order, y, x] ** 2),
        "lam_t": float(f.lam[t, y, x]), "pred_t": float(tpl.pred[t, y, x]),
    }
