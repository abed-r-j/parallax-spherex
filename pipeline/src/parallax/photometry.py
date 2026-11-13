"""Photometry of one sky position in every frame of a Field: the "spectrum on the fly".

Every SPHEREx exposure sees a given sky position at a different wavelength, so a list of
fluxes measured frame by frame *is* a spectrum. This module measures, for each frame,

* an aperture flux (default radius 2.5 pixels = 15.4 arcsec) with a local background
  annulus, in microjansky with a 1-sigma error;
* a PSF-weighted flux (Gaussian of the effective width of the resampled image), which is
  better for faint sources;
* a "wing" flux (ring medians between 4 and 7 pixels) that still works when the core of a
  bright star is saturated. It is a fixed but uncalibrated fraction of the total flux at a
  given wavelength, so it is only good for *ratios* between epochs at the same wavelength.

Each measurement carries a quality code (good / suspect / saturated / no data) built
from the SPHEREx pixel flags and from missing (NaN) core pixels. ``spectra_by_group`` bins
the per-frame fluxes onto the 102-channel grid or a regular R ~ 40 grid, per survey pass.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from .frames import Field, bitmask

# 1 MJy/sr over one 6.15 arcsec pixel, in microjansky.
ARCSEC_PER_RAD = 206264.806


def ujy_per_mjysr(scale_arcsec: float) -> float:
    """Microjansky per pixel for a surface brightness of 1 MJy/sr."""
    return 1e12 * (scale_arcsec / ARCSEC_PER_RAD) ** 2


# Detector band edges in micron (measured on the data, see the project facts).
DETECTOR_BANDS: dict[int, tuple[float, float]] = {
    1: (0.74, 1.11), 2: (1.10, 1.66), 3: (1.62, 2.41),
    4: (2.42, 3.80), 5: (3.82, 4.43), 6: (4.41, 5.00),
}
CHANNELS_PER_DETECTOR = 17  # 6 x 17 = 102 spectral channels

GOOD, SUSPECT, SATURATED, NODATA = 0, 1, 2, 3
QUALITY_NAMES = {GOOD: "good", SUSPECT: "suspect", SATURATED: "saturated", NODATA: "no data"}

_OVERFLOW = bitmask("OVERFLOW")
_SUSPECT = bitmask("OVERFLOW", "NONLINEAR", "PERSIST", "DICHROIC")

STAMP_HALF = 18  # half-size of the working stamp, pixels


@dataclass
class Photometry:
    """Per-frame measurements of one sky position (arrays of length n_frames)."""

    x: np.ndarray  # pixel position used in each frame
    y: np.ndarray
    mjd: np.ndarray
    det: np.ndarray
    campaign: np.ndarray
    lam: np.ndarray  # micron, at the position
    bw: np.ndarray
    flux: np.ndarray  # aperture flux, microJy
    err: np.ndarray
    flux_psf: np.ndarray  # PSF-weighted flux, microJy
    err_psf: np.ndarray
    flux_wing: np.ndarray  # ring-median wing flux, microJy (relative use only)
    err_wing: np.ndarray
    bkg: np.ndarray  # local background, MJy/sr
    quality: np.ndarray  # GOOD / SUSPECT / SATURATED / NODATA
    hole: np.ndarray  # radius (pixels) of the missing core, 0 if complete
    r_ap: float
    wing: tuple[float, float]

    def __len__(self) -> int:
        return len(self.mjd)

    def good(self, max_quality: int = GOOD) -> np.ndarray:
        return (self.quality <= max_quality) & np.isfinite(self.flux) & np.isfinite(self.err)

    def values(self, which: str = "flux") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(flux, error, usable mask) for ``which`` in 'flux', 'psf' or 'wing'."""
        if which == "flux":
            return self.flux, self.err, self.good()
        if which == "psf":
            ok = (self.quality <= GOOD) & np.isfinite(self.flux_psf)
            return self.flux_psf, self.err_psf, ok
        if which == "wing":
            ok = np.isfinite(self.flux_wing) & np.isfinite(self.err_wing)
            return self.flux_wing, self.err_wing, ok
        raise ValueError(f"unknown flux kind {which!r}")


def pixel_xy(field: Field, ra, dec) -> tuple[np.ndarray, np.ndarray]:
    """0-based pixel coordinates of sky positions on the field grid."""
    x, y = field.wcs.all_world2pix(np.asarray(ra, float), np.asarray(dec, float), 0)
    return np.asarray(x, float), np.asarray(y, float)


def effective_sigma_pix(fwhm_arcsec: float, scale: float) -> float:
    """Gaussian sigma (pixels) of a star in the *resampled* image.

    The bilinear resampling onto the common grid adds a triangle kernel of variance
    1/6 pixel^2 to the native point-spread function.
    """
    fwhm = fwhm_arcsec if np.isfinite(fwhm_arcsec) and fwhm_arcsec > 0 else 8.0
    return float(np.sqrt((fwhm / 2.3548 / scale) ** 2 + 1.0 / 6.0))


def aperture_weights(shape: tuple[int, int], x: float, y: float, r: float,
                     sub: int = 5) -> np.ndarray:
    """Fraction of each pixel inside a circle of radius ``r`` centred on (x, y)."""
    ny, nx = shape
    off = (np.arange(sub) + 0.5) / sub - 0.5
    yy, xx = np.mgrid[0:ny, 0:nx]
    w = np.zeros(shape)
    for dy in off:
        for dx in off:
            w += ((xx + dx - x) ** 2 + (yy + dy - y) ** 2) <= r * r
    return w / (sub * sub)


def robust_level(v: np.ndarray, nsig: float = 3.0, iters: int = 4) -> tuple[float, float, int]:
    """Sigma-clipped median, its robust scatter and the number of values kept."""
    v = v[np.isfinite(v)]
    if v.size == 0:
        return np.nan, np.nan, 0
    for _ in range(iters):
        med = np.median(v)
        sd = 1.4826 * np.median(np.abs(v - med))
        if sd <= 0:
            break
        keep = np.abs(v - med) < nsig * sd
        if keep.all():
            break
        v = v[keep]
    med = float(np.median(v))
    return med, float(1.4826 * np.median(np.abs(v - med))), int(v.size)


def _stamp(a: np.ndarray, x: float, y: float, half: int) -> tuple[np.ndarray, float, float]:
    """Sub-array around (x, y) and the position inside it."""
    n = a.shape[-1]
    x0 = min(max(round(x) - half, 0), max(n - 1, 0))
    y0 = min(max(round(y) - half, 0), max(n - 1, 0))
    return a[y0 : y0 + 2 * half + 1, x0 : x0 + 2 * half + 1], x - x0, y - y0


def measure_frame(
    img: np.ndarray, var: np.ndarray, flags: np.ndarray, x: float, y: float,
    sigma_pix: float, ujy: float, r_ap: float = 2.5, annulus: tuple[float, float] = (5.0, 8.0),
    wing: tuple[float, float] = (4.0, 7.0), wing_bkg: tuple[float, float] = (12.0, 16.0),
    r_core: float = 1.5,
) -> dict[str, float]:
    """Measure one position in one image (MJy/sr in, microJy out)."""
    out = dict.fromkeys(
        ("flux", "err", "flux_psf", "err_psf", "flux_wing", "err_wing", "bkg"), np.nan
    )
    out["quality"] = NODATA
    out["hole"] = 0.0
    n = img.shape[0]
    if not (np.isfinite(x) and np.isfinite(y) and 0 <= x <= n - 1 and 0 <= y <= n - 1):
        return out
    im, xs, ys = _stamp(img, x, y, STAMP_HALF)
    vr, _, _ = _stamp(var, x, y, STAMP_HALF)
    fl, _, _ = _stamp(flags, x, y, STAMP_HALF)
    yy, xx = np.mgrid[0 : im.shape[0], 0 : im.shape[1]]
    r = np.hypot(xx - xs, yy - ys)
    ok = np.isfinite(im) & np.isfinite(vr) & (vr > 0)

    # Local background and its pixel scatter.
    ring = (r >= annulus[0]) & (r < annulus[1]) & ok
    bkg, bsd, nb = robust_level(im[ring])
    if nb < 10:
        return out
    out["bkg"] = bkg
    core = r <= r_core
    missing_core = bool((core & ~ok).any())
    if missing_core:
        out["hole"] = _hole_radius(ok, r)

    # Aperture flux.
    w = aperture_weights(im.shape, xs, ys, r_ap)
    inside = w > 0
    complete = bool(ok[inside].all()) and inside.sum() > 0
    if complete:
        area = w.sum()
        out["flux"] = float((w[inside] * (im[inside] - bkg)).sum() * ujy)
        v = (w[inside] ** 2 * vr[inside]).sum() + area**2 * bsd**2 / nb
        out["err"] = float(np.sqrt(v) * ujy)

    # PSF-weighted flux on the valid pixels.
    p = np.exp(-0.5 * (r / sigma_pix) ** 2) / (2 * np.pi * sigma_pix**2)
    fit = (r <= 3.0 * sigma_pix + 1.0) & ok
    if fit.any() and p[fit].sum() > 0.5 * p[r <= 3.0 * sigma_pix + 1.0].sum():
        den = (p[fit] ** 2 / vr[fit]).sum()
        out["flux_psf"] = float((p[fit] * (im[fit] - bkg) / vr[fit]).sum() / den * ujy)
        out["err_psf"] = float(np.sqrt(1.0 / den) * ujy)

    # Wing flux: ring medians, far background. Robust to a saturated core.
    out["flux_wing"], out["err_wing"] = _wing_flux(im, ok, r, wing, wing_bkg, ujy)

    core_flags = int(np.bitwise_or.reduce(fl[r <= r_ap].astype(np.int64)))
    if not complete:
        saturated = bool(core_flags & _OVERFLOW) or (missing_core and np.nanmax(im[r <= 4]) > 50.0)
        out["quality"] = SATURATED if saturated else NODATA
    elif int(np.bitwise_or.reduce(fl[core].astype(np.int64))) & _SUSPECT:
        out["quality"] = SUSPECT
    else:
        out["quality"] = GOOD
    return out


def _hole_radius(ok: np.ndarray, r: np.ndarray, r_max: float = 14.0) -> float:
    """Radius of the missing core: the first 1-pixel ring that is at least 90 % valid."""
    for a in np.arange(0.0, r_max, 1.0):
        ring = (r >= a) & (r < a + 1.0)
        if ring.any() and ok[ring].mean() >= 0.9:
            return float(a)
    return float(r_max)


def _wing_flux(im, ok, r, wing, wing_bkg, ujy) -> tuple[float, float]:
    far = (r >= wing_bkg[0]) & (r < wing_bkg[1]) & ok
    b, _, nb = robust_level(im[far])
    if nb < 30:
        return np.nan, np.nan
    total, var = 0.0, 0.0
    edges = np.arange(wing[0], wing[1] + 1e-9, 1.0)
    for a, c in pairwise(edges):
        sel = (r >= a) & (r < c)
        good = sel & ok
        if good.sum() < 0.6 * sel.sum() or good.sum() < 8:
            return np.nan, np.nan
        v = im[good]
        med = np.median(v)
        sd = 1.4826 * np.median(np.abs(v - med))
        area = np.pi * (c * c - a * a)
        total += (med - b) * area
        var += (1.2533 * sd * area) ** 2 / good.sum()
    return float(total * ujy), float(np.sqrt(var) * ujy)


def photometry(
    field: Field, ra, dec, r_ap: float = 2.5, annulus: tuple[float, float] = (5.0, 8.0),
    wing: tuple[float, float] = (4.0, 7.0), wing_bkg: tuple[float, float] = (12.0, 16.0),
) -> Photometry:
    """Measure a sky position in every frame.

    ``ra`` and ``dec`` (degrees) may be scalars or arrays with one value per frame, so a
    moving target can be followed.
    """
    nf = len(field)
    x, y = pixel_xy(field, np.broadcast_to(ra, (nf,)), np.broadcast_to(dec, (nf,)))
    ujy = ujy_per_mjysr(field.scale)
    cols: dict[str, list[float]] = {}
    lam = np.full(nf, np.nan)
    bw = np.full(nf, np.nan)
    for i in range(nf):
        sig = effective_sigma_pix(float(field.psf_fwhm[i]), field.scale)
        m = measure_frame(field.img[i], field.var[i], field.flags[i], float(x[i]), float(y[i]),
                          sig, ujy, r_ap, annulus, wing, wing_bkg)
        for k, v in m.items():
            cols.setdefault(k, []).append(v)
        ix, iy = round(float(x[i])), round(float(y[i]))
        if 0 <= ix < field.n and 0 <= iy < field.n:
            lam[i], bw[i] = field.lam[i, iy, ix], field.bw[i, iy, ix]
    a = {k: np.array(v, dtype=float) for k, v in cols.items()}
    return Photometry(
        x=x, y=y, mjd=field.mjd.copy(), det=field.det.astype(int),
        campaign=field.campaign.astype(int), lam=lam, bw=bw, flux=a["flux"], err=a["err"],
        flux_psf=a["flux_psf"], err_psf=a["err_psf"], flux_wing=a["flux_wing"],
        err_wing=a["err_wing"], bkg=a["bkg"], quality=a["quality"].astype(int), hole=a["hole"],
        r_ap=r_ap, wing=wing,
    )


# --------------------------------------------------------------------------- spectra


@dataclass(frozen=True)
class Grid:
    """Wavelength bins. ``det`` is 0 when a bin accepts every detector."""

    lo: np.ndarray
    hi: np.ndarray
    det: np.ndarray
    name: str

    @property
    def centre(self) -> np.ndarray:
        return np.sqrt(self.lo * self.hi)

    def __len__(self) -> int:
        return len(self.lo)


def channel_grid(per_detector: int = CHANNELS_PER_DETECTOR) -> Grid:
    """The 102-channel grid: 17 logarithmic channels across each of the six detectors."""
    lo, hi, det = [], [], []
    for d, (a, b) in DETECTOR_BANDS.items():
        e = np.geomspace(a, b, per_detector + 1)
        lo.extend(e[:-1])
        hi.extend(e[1:])
        det.extend([d] * per_detector)
    return Grid(np.array(lo), np.array(hi), np.array(det), f"{6 * per_detector} channels")


def regular_grid(resolving_power: float = 40.0, lam_min: float = 0.74,
                 lam_max: float = 5.0) -> Grid:
    """Logarithmic bins of constant resolving power lambda / d(lambda)."""
    nbin = int(np.ceil(np.log(lam_max / lam_min) * resolving_power))
    e = lam_min * np.exp(np.arange(nbin + 1) / resolving_power)
    return Grid(e[:-1], e[1:], np.zeros(nbin, dtype=int), f"R={resolving_power:g}")


def combine(v: np.ndarray, e: np.ndarray, clip: float = 5.0) -> tuple[float, float, int]:
    """Clipped inverse-variance mean. The error is the larger of the formal error and
    the standard error from the scatter, because under-sampling adds scatter that the
    pixel variances do not know about."""
    ok = np.isfinite(v) & np.isfinite(e) & (e > 0)
    v, e = v[ok], e[ok]
    if v.size == 0:
        return np.nan, np.nan, 0
    if v.size >= 4:
        med = np.median(v)
        sd = 1.4826 * np.median(np.abs(v - med))
        if sd > 0:  # a zero MAD says nothing about the scatter: do not clip
            keep = np.abs(v - med) <= clip * np.maximum(sd, e)
            v, e = v[keep], e[keep]
    w = 1.0 / e**2
    mean = float((w * v).sum() / w.sum())
    err = float(np.sqrt(1.0 / w.sum()))
    if v.size >= 2:
        err = max(err, float(np.std(v, ddof=1) / np.sqrt(v.size)))
    return mean, err, int(v.size)


def bin_values(lam: np.ndarray, det: np.ndarray, v: np.ndarray, e: np.ndarray,
               grid: Grid) -> dict[str, np.ndarray]:
    """Bin per-frame values onto a wavelength grid."""
    nb = len(grid)
    mean, err, lam_mean = np.full(nb, np.nan), np.full(nb, np.nan), np.full(nb, np.nan)
    count = np.zeros(nb, dtype=int)
    for k in range(nb):
        sel = (lam >= grid.lo[k]) & (lam < grid.hi[k]) & np.isfinite(v)
        if grid.det[k]:
            sel &= det == grid.det[k]
        if not sel.any():
            continue
        mean[k], err[k], count[k] = combine(v[sel], e[sel])
        lam_mean[k] = float(np.mean(lam[sel]))
    return {"lam": lam_mean, "value": mean, "err": err, "n": count,
            "det": grid.det.copy(), "centre": grid.centre}


def spectra_by_group(phot: Photometry, groups: np.ndarray | None = None,
                     grid: Grid | None = None, which: str = "flux") -> list[dict]:
    """Binned spectrum of each group of frames (default: each survey pass)."""
    grid = grid or channel_grid()
    groups = phot.campaign if groups is None else np.asarray(groups)
    v, e, ok = phot.values(which)
    out = []
    for g in np.unique(groups[groups >= 0]):
        sel = (groups == g) & ok
        b = bin_values(phot.lam[sel], phot.det[sel], v[sel], e[sel], grid)
        b.update(group=int(g), n_frames=int(sel.sum()), which=which, grid=grid.name,
                 mjd=float(np.mean(phot.mjd[groups == g])))
        out.append(b)
    return out


def quality_report(phot: Photometry) -> dict:
    """How many frames are good / suspect / saturated per detector, and which wavelength
    ranges keep at least half of their frames unsaturated."""
    grid = channel_grid()
    per_det = {}
    for d in range(1, 7):
        s = phot.det == d
        if not s.any():
            continue
        per_det[str(d)] = {
            "frames": int(s.sum()),
            **{QUALITY_NAMES[q]: int((phot.quality[s] == q).sum()) for q in QUALITY_NAMES},
            "medianHolePix": float(np.median(phot.hole[s])),
        }
    usable, lost = [], []
    for k in range(len(grid)):
        s = (phot.det == grid.det[k]) & (phot.lam >= grid.lo[k]) & (phot.lam < grid.hi[k])
        if not s.any():
            continue
        frac = float((phot.quality[s] <= SUSPECT).mean())
        (usable if frac >= 0.5 else lost).append((float(grid.lo[k]), float(grid.hi[k])))
    nsat = int((phot.quality == SATURATED).sum())
    return {
        "perDetector": per_det, "nFrames": len(phot), "nSaturated": nsat,
        "saturatedFraction": nsat / max(len(phot), 1),
        "usableRanges": merge_ranges(usable), "saturatedRanges": merge_ranges(lost),
    }


def merge_ranges(r: list[tuple[float, float]], tol: float = 1e-6) -> list[list[float]]:
    """Merge touching wavelength intervals."""
    out: list[list[float]] = []
    for lo, hi in sorted(r):
        if out and lo <= out[-1][1] + tol:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return [[round(a, 4), round(b, 4)] for a, b in out]
