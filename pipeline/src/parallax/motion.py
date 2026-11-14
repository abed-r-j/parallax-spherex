"""Where is a star in each survey pass, and how fast does it move?

SPHEREx pixels are 6.15 arcsec and the fastest star in the sky moves 10 arcsec per year,
so the challenge targets shift by one or two pixels over the available baseline. The
measurement therefore has to be honest about sub-pixel precision:

1. ``pass_detector_stacks`` builds one clipped mean image per survey pass and detector
   (a pass holds 15-25 dithered exposures per detector, so the stack is well sampled
   although single exposures are not).
2. ``fit_centre`` fits a round Moffat profile on a tilted plane to the valid pixels. It
   works when the core is saturated (missing), because the wings still fix the centre.
3. Each detector gives an independent position. Their scatter, not the formal fit error,
   is used as the uncertainty of the pass position.
4. Field stars measured the same way give the frame-to-frame registration error of each
   pass, which is removed and added to the error budget.
5. ``fit_motion`` fits proper motion with the parallax either fixed to the catalogue
   value or free. SPHEREx always looks about 90 degrees from the Sun, so consecutive
   passes sit at opposite extremes of the parallax ellipse.

``faint_detection`` is the forced, matched-filter version for a target that no single
exposure can show (WISE 0855-0714).

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage, optimize

from .frames import Field
from .photometry import effective_sigma_pix, robust_level, ujy_per_mjysr
from .targets import Target

# Catalogue parallaxes (mas) of the built-in moving targets.
PARALLAX_MAS: dict[str, tuple[float, str]] = {
    "barnard": (546.98, "Gaia DR3"),
    "epsindi": (274.84, "Gaia DR3 (Epsilon Indi A)"),
    "wise0855": (433.0, "Luhman & Esplin 2016"),
}


def mjd_to_year(mjd) -> np.ndarray:
    return 2000.0 + (np.asarray(mjd, float) - 51544.5) / 365.25


# ----------------------------------------------------------------------------- stacks


@dataclass
class PassStacks:
    """Mean images per survey pass (axis 0) and detector 1..6 (axis 1)."""

    img: np.ndarray  # (C, 6, n, n) MJy/sr, NaN where no data
    var: np.ndarray  # (C, 6, n, n)
    cov: np.ndarray  # (C, 6, n, n) fraction of the exposures that contribute
    nexp: np.ndarray  # (C, 6) exposures used
    mjd: np.ndarray  # (C, 6) mean epoch, NaN if empty
    lam: np.ndarray  # (C, 6) mean wavelength at the field centre

    @property
    def n_pass(self) -> int:
        return self.img.shape[0]


def stack_frames(img: np.ndarray, var: np.ndarray, clip: float = 5.0,
                 grow: int = 1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Clipped mean of a set of aligned frames, one weight per frame.

    Per-frame (not per-pixel) weights keep the stack unbiased on bright stars, whose
    pixel variance depends on the signal. ``grow`` discards the pixels next to missing
    data: they are bilinear mixes that touch a dead or saturated pixel.
    """
    ok = np.isfinite(img) & np.isfinite(var) & (var > 0)
    if grow:
        st = np.ones((1, 2 * grow + 1, 2 * grow + 1), dtype=bool)
        ok &= ~ndimage.binary_dilation(~ok, structure=st)
    d = np.where(ok, img, np.nan).astype(np.float64)
    if len(d) >= 5:
        with np.errstate(all="ignore"):
            med = np.nanmedian(d, axis=0)
            mad = 1.4826 * np.nanmedian(np.abs(d - med), axis=0)
            tol = clip * np.maximum(mad, np.sqrt(np.where(ok, var, np.inf)))
            ok &= np.abs(d - med) <= tol
    with np.errstate(all="ignore"):
        wf = 1.0 / np.nanmedian(np.where(ok, var, np.nan).reshape(len(d), -1), axis=1)
    wf = np.where(np.isfinite(wf), wf, 0.0)[:, None, None]
    w = np.where(ok, wf, 0.0)
    den = w.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(den > 0, (w * np.where(ok, img, 0.0)).sum(0) / den, np.nan)
        v = np.where(den > 0, (w**2 * np.where(ok, var, 0.0)).sum(0) / den**2, np.nan)
    return mean, v, ok.mean(axis=0)


def pass_detector_stacks(field: Field, clip: float = 5.0, grow: int = 1) -> PassStacks:
    """One clipped mean image per survey pass and detector."""
    ncamp = int(field.campaign.max()) + 1
    shape = (ncamp, 6, field.n, field.n)
    img, var, cov = np.full(shape, np.nan), np.full(shape, np.nan), np.zeros(shape)
    nexp = np.zeros((ncamp, 6), dtype=int)
    mjd, lam = np.full((ncamp, 6), np.nan), np.full((ncamp, 6), np.nan)
    for c in range(ncamp):
        for d in range(1, 7):
            sel = (field.campaign == c) & (field.det == d)
            if sel.sum() < 2:
                continue
            img[c, d - 1], var[c, d - 1], cov[c, d - 1] = stack_frames(
                field.img[sel], field.var[sel], clip, grow)
            nexp[c, d - 1] = int(sel.sum())
            mjd[c, d - 1] = float(field.mjd[sel].mean())
            lam[c, d - 1] = float(np.nanmean(field.lam0[sel]))
    return PassStacks(img, var, cov, nexp, mjd, lam)


def combine_detectors(stacks: PassStacks, c: int, dets: tuple[int, ...] = (1, 2, 3, 4, 5, 6)
                      ) -> tuple[np.ndarray, np.ndarray]:
    """Exposure-weighted mean of the detector stacks of one pass."""
    idx = [d - 1 for d in dets if stacks.nexp[c, d - 1] > 0]
    n = stacks.img.shape[-1]
    if not idx:
        return np.full((n, n), np.nan), np.full((n, n), np.nan)
    w = np.where(np.isfinite(stacks.img[c, idx]), stacks.nexp[c, idx][:, None, None], 0.0)
    den = w.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(den > 0, (w * np.nan_to_num(stacks.img[c, idx])).sum(0) / den, np.nan)
        var = np.where(den > 0, (w**2 * np.nan_to_num(stacks.var[c, idx])).sum(0) / den**2, np.nan)
    return mean, var


# -------------------------------------------------------------------------- centroids


@dataclass
class Centroid:
    x: float
    y: float
    ex: float  # formal 1-sigma errors, pixels (optimistic: see module docstring)
    ey: float
    flux: float  # integral of the fitted Gaussians: indicative only (trades with the plane)
    fwhm: float  # pixels
    core_missing: bool
    npix: int
    rchi2: float


PROFILE_SIGMAS = (0.5, 0.75, 1.1, 1.6, 2.4, 3.6, 5.4, 8.0)  # pixels


def _profile_basis(xx: np.ndarray, yy: np.ndarray, x0: float, y0: float,
                   sigmas: tuple[float, ...]) -> np.ndarray:
    """Design matrix of a round multi-Gaussian profile on a tilted plane."""
    dx, dy = xx - x0, yy - y0
    r2 = dx * dx + dy * dy
    cols = [np.exp(-0.5 * r2 / s**2) for s in sigmas]
    cols += [np.ones_like(dx), dx, dy]
    return np.column_stack(cols)


def _profile_solve(xy, xv, yv, dv, sig, sigmas) -> tuple[np.ndarray, np.ndarray]:
    a = _profile_basis(xv, yv, xy[0], xy[1], sigmas) / sig[:, None]
    coef, *_ = np.linalg.lstsq(a, dv / sig, rcond=1e-8)
    return coef, a @ coef - dv / sig


def _hole(ok: np.ndarray, r: np.ndarray, radius: float) -> float | None:
    """Inner radius from which rings are at least 70 % valid (0 for a complete core)."""
    for a in np.arange(0.0, radius, 0.5):
        ring = (r >= a) & (r < a + 1.0)
        if ring.any() and ok[ring].mean() >= 0.7:
            return float(a)
    return None


def fit_centre(img: np.ndarray, var: np.ndarray, x0: float, y0: float, radius: float = 6.0,
               max_shift: float = 3.0, model_error: float = 0.1) -> Centroid | None:
    """Centre of a star from the valid pixels within ``radius``.

    The model is any round profile (a sum of concentric Gaussians whose amplitudes are
    solved linearly) on a tilted plane; only the centre is non-linear. Nothing is assumed
    about the shape of the profile, so the fit also works on the wings of a star whose
    core is saturated and missing. ``model_error`` is the fractional departure from
    roundness that is tolerated (diffraction spikes), which keeps bright pixels from
    dominating. Returns None when there are too few pixels or the fit hits its bounds.
    """
    n = img.shape[0]
    half = int(np.ceil(radius)) + 1
    xi, yi = round(x0), round(y0)
    ys = slice(max(yi - half, 0), min(yi + half + 1, n))
    xs = slice(max(xi - half, 0), min(xi + half + 1, n))
    yy, xx = np.mgrid[ys, xs]
    d, v = img[ys, xs], var[ys, xs]
    r = np.hypot(xx - x0, yy - y0)
    ok = np.isfinite(d) & np.isfinite(v) & (v > 0) & (r <= radius)
    hole = _hole(ok, r, radius)
    if ok.sum() < 30 or hole is None:
        return None
    core_missing = hole > 0.0
    sigmas = tuple(s for s in PROFILE_SIGMAS if hole / 2.5 <= s <= radius)
    xv, yv, dv = xx[ok].astype(float), yy[ok].astype(float), d[ok].astype(float)
    b0 = float(np.percentile(dv, 5))
    if dv.max() - b0 <= 0:
        return None
    sig = np.sqrt(v[ok] + (model_error * np.abs(dv - b0)) ** 2)

    def resid(xy: np.ndarray) -> np.ndarray:
        return _profile_solve(xy, xv, yv, dv, sig, sigmas)[1]

    lo, hi = [x0 - max_shift, y0 - max_shift], [x0 + max_shift, y0 + max_shift]
    try:
        res = optimize.least_squares(resid, [x0, y0], bounds=(lo, hi), loss="soft_l1",
                                     f_scale=2.0, diff_step=1e-3)
    except (ValueError, np.linalg.LinAlgError):
        return None
    x, y = res.x
    if not res.success or abs(x - x0) > max_shift - 1e-3 or abs(y - y0) > max_shift - 1e-3:
        return None
    dof = max(ok.sum() - len(sigmas) - 5, 1)
    rchi2 = float((res.fun**2).sum() / dof)
    try:
        cov = np.linalg.inv(res.jac.T @ res.jac) * max(rchi2, 1.0)
        ex, ey = float(np.sqrt(cov[0, 0])), float(np.sqrt(cov[1, 1]))
    except np.linalg.LinAlgError:
        ex = ey = np.nan
    coef, _ = _profile_solve(res.x, xv, yv, dv, sig, sigmas)
    amp = coef[: len(sigmas)]
    s2 = np.square(sigmas)
    flux = float((amp * 2 * np.pi * s2).sum())
    fwhm = np.nan
    if not core_missing:
        rr = np.linspace(0.0, radius, 400)
        prof = (amp[:, None] * np.exp(-0.5 * rr[None, :] ** 2 / s2[:, None])).sum(0)
        below = np.flatnonzero(prof < 0.5 * prof[0])
        fwhm = float(2 * rr[below[0]]) if below.size and prof[0] > 0 else np.nan
    return Centroid(float(x), float(y), ex, ey, flux, fwhm, core_missing, int(ok.sum()), rchi2)


def windowed_centroid(img: np.ndarray, x0: float, y0: float, sigma: float = 1.2,
                      iters: int = 30, tol: float = 1e-4) -> tuple[float, float] | None:
    """Iterative Gaussian-windowed first moment (complete, unsaturated cores only)."""
    n = img.shape[0]
    half = int(np.ceil(4 * sigma)) + 1
    x, y = float(x0), float(y0)
    yy0, xx0 = np.mgrid[0:n, 0:n]
    ring = (np.hypot(xx0 - x0, yy0 - y0) >= 5) & (np.hypot(xx0 - x0, yy0 - y0) < 8)
    bkg, _, nb = robust_level(img[ring])
    if nb < 10:
        return None
    for _ in range(iters):
        xi, yi = round(x), round(y)
        if not (half <= xi < n - half and half <= yi < n - half):
            return None
        sl = (slice(yi - half, yi + half + 1), slice(xi - half, xi + half + 1))
        d = img[sl] - bkg
        yy, xx = yy0[sl], xx0[sl]
        r2 = (xx - x) ** 2 + (yy - y) ** 2
        if not np.isfinite(d[r2 <= (3 * sigma) ** 2]).all():
            return None
        w = np.exp(-0.5 * r2 / sigma**2) * np.nan_to_num(d)
        tot = w.sum()
        if tot <= 0:
            return None
        dx, dy = 2.0 * (w * (xx - x)).sum() / tot, 2.0 * (w * (yy - y)).sum() / tot
        x, y = x + dx, y + dy
        if abs(x - x0) > 3 or abs(y - y0) > 3:
            return None
        if dx * dx + dy * dy < tol * tol:
            break
    return x, y


# ------------------------------------------------------------------- reference frame


def find_reference_stars(img: np.ndarray, var: np.ndarray, avoid_xy: tuple[float, float],
                         avoid_r: float = 10.0, edge: int = 6, max_stars: int = 40,
                         min_snr: float = 10.0) -> list[tuple[float, float]]:
    """Isolated, unsaturated field stars: local maxima of the smoothed stack."""
    ok = np.isfinite(img)
    filled = np.where(ok, img, 0.0)
    wsum = ndimage.gaussian_filter(ok.astype(float), 0.8)
    with np.errstate(invalid="ignore", divide="ignore"):
        sm = np.where(wsum > 0.5, ndimage.gaussian_filter(filled, 0.8) / wsum, np.nan)
    bkg, sd, _ = robust_level(sm[ok])
    if not np.isfinite(sd) or sd <= 0:
        return []
    peak = (sm == ndimage.maximum_filter(np.nan_to_num(sm, nan=-np.inf), size=9)) & ok
    n = img.shape[0]
    ys, xs = np.nonzero(peak & (sm - bkg > min_snr * sd))
    cand = sorted(zip(sm[ys, xs], xs, ys, strict=True), reverse=True)
    out: list[tuple[float, float]] = []
    for _, x, y in cand:
        if not (edge <= x < n - edge and edge <= y < n - edge):
            continue
        if np.hypot(x - avoid_xy[0], y - avoid_xy[1]) < avoid_r:
            continue
        if not ok[y - 2 : y + 3, x - 2 : x + 3].all():
            continue  # saturated or damaged core
        out.append((float(x), float(y)))
        if len(out) >= max_stars:
            break
    return out


def registration_offsets(stacks: PassStacks, refs: list[tuple[float, float]],
                         radius: float = 4.0) -> list[dict]:
    """Shift of every pass with respect to the mean of all passes, from field stars.

    Returns one dict per pass with ``dx``, ``dy`` (pixels), their standard errors and
    the number of stars. A pass without enough stars gets zero shift and NaN errors.
    """
    npass = stacks.n_pass
    pos = np.full((npass, len(refs), 2), np.nan)
    for c in range(npass):
        img, var = combine_detectors(stacks, c)
        for k, (x, y) in enumerate(refs):
            f = fit_centre(img, var, x, y, radius=radius, max_shift=1.5)
            if f is not None and not f.core_missing and 0.8 < f.fwhm < 5.0:
                pos[c, k] = (f.x, f.y)
    complete = np.isfinite(pos).all(axis=(0, 2))
    out = []
    for c in range(npass):
        if complete.sum() < 3:
            out.append({"dx": 0.0, "dy": 0.0, "ex": np.nan, "ey": np.nan,
                        "n": int(complete.sum())})
            continue
        d = pos[c, complete] - pos[:, complete].mean(axis=0)
        dx, sx, _ = robust_level(d[:, 0])
        dy, sy, _ = robust_level(d[:, 1])
        m = int(complete.sum())
        # 1.2533: the median is noisier than the mean. Floor the scatter estimate.
        sx, sy = max(sx, 0.01), max(sy, 0.01)
        out.append({"dx": dx, "dy": dy, "ex": 1.2533 * sx / np.sqrt(m),
                    "ey": 1.2533 * sy / np.sqrt(m), "n": m, "scatter": float(np.hypot(sx, sy))})
    return out


# ---------------------------------------------------------------------- sky geometry


def parallax_factors(ra_deg: float, dec_deg: float, mjd) -> tuple[np.ndarray, np.ndarray]:
    """Displacement (east, north) per unit parallax for an observer at the Earth."""
    from astropy.coordinates import get_body_barycentric
    from astropy.time import Time

    xyz = get_body_barycentric("earth", Time(np.atleast_1d(mjd), format="mjd")).xyz.to_value("au")
    a, d = np.radians(ra_deg), np.radians(dec_deg)
    pe = xyz[0] * np.sin(a) - xyz[1] * np.cos(a)
    pn = xyz[0] * np.cos(a) * np.sin(d) + xyz[1] * np.sin(a) * np.sin(d) - xyz[2] * np.cos(d)
    return pe, pn


def xy_to_offsets(field: Field, x, y) -> tuple[np.ndarray, np.ndarray]:
    """Pixel coordinates to (east, north) arcsec from the field centre (tangent plane)."""
    c = (field.n - 1) / 2
    return -(np.asarray(x, float) - c) * field.scale, (np.asarray(y, float) - c) * field.scale


def offsets_to_xy(field: Field, east, north) -> tuple[np.ndarray, np.ndarray]:
    c = (field.n - 1) / 2
    return c - np.asarray(east, float) / field.scale, c + np.asarray(north, float) / field.scale


def catalogue_track(field: Field, target: Target, mjd, parallax_mas: float = 0.0
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Catalogue-predicted (east, north) arcsec offsets from the field centre at ``mjd``."""
    mjd = np.atleast_1d(np.asarray(mjd, float))
    pos = np.array([target.at(float(y)) for y in mjd_to_year(mjd)])
    x, y = field.wcs.all_world2pix(pos[:, 0], pos[:, 1], 0)
    east, north = xy_to_offsets(field, x, y)
    if parallax_mas:
        pe, pn = parallax_factors(target.ra, target.dec, mjd)
        east, north = east + parallax_mas / 1e3 * pe, north + parallax_mas / 1e3 * pn
    return east, north


# ------------------------------------------------------------------------ motion fit


def fit_motion(year, east, north, e_east, e_north, pe=None, pn=None,
               parallax: float | None = None, free_parallax: bool = False) -> dict:
    """Weighted least-squares proper motion (arcsec, arcsec/yr).

    ``parallax`` (arcsec) is removed before the fit when given. ``free_parallax`` adds it
    as a fifth parameter (needs ``pe`` and ``pn`` and at least three epochs).
    """
    t = np.asarray(year, float)
    e, nn = np.asarray(east, float).copy(), np.asarray(north, float).copy()
    se, sn = np.asarray(e_east, float), np.asarray(e_north, float)
    m = len(t)
    if parallax is not None and pe is not None:
        e, nn = e - parallax * np.asarray(pe), nn - parallax * np.asarray(pn)
    w = np.concatenate([1 / se**2, 1 / sn**2])
    t0 = float((np.concatenate([t, t]) * w).sum() / w.sum())
    dt = t - t0
    one, zero = np.ones(m), np.zeros(m)
    cols = [np.concatenate([one, zero]), np.concatenate([zero, one]),
            np.concatenate([dt, zero]), np.concatenate([zero, dt])]
    if free_parallax:
        cols.append(np.concatenate([np.asarray(pe, float), np.asarray(pn, float)]))
    a = np.column_stack(cols)
    yv = np.concatenate([e, nn])
    npar = a.shape[1]
    if 2 * m < npar:
        raise ValueError("not enough epochs for this fit")
    cov = np.linalg.inv(a.T @ (a * w[:, None]))
    p = cov @ (a.T @ (w * yv))
    res = yv - a @ p
    dof = 2 * m - npar
    out = {
        "t0": t0, "east0": float(p[0]), "north0": float(p[1]),
        "pmEast": float(p[2]), "pmNorth": float(p[3]),
        "ePmEast": float(np.sqrt(cov[2, 2])), "ePmNorth": float(np.sqrt(cov[3, 3])),
        "chi2": float((w * res**2).sum()), "dof": int(dof),
        "resEast": res[:m].tolist(), "resNorth": res[m:].tolist(),
    }
    out.update(_polar(p[2], p[3], cov[2:4, 2:4]))
    if free_parallax:
        out["parallax"] = float(p[4])
        out["eParallax"] = float(np.sqrt(cov[4, 4]))
    return out


def _polar(pm_e: float, pm_n: float, cov: np.ndarray) -> dict:
    """Total motion and position angle (degrees east of north) with propagated errors."""
    tot = float(np.hypot(pm_e, pm_n))
    pa = float(np.degrees(np.arctan2(pm_e, pm_n)) % 360.0)
    if tot <= 0:
        return {"total": tot, "eTotal": np.nan, "pa": pa, "ePa": np.nan}
    g = np.array([pm_e, pm_n]) / tot
    h = np.array([pm_n, -pm_e]) / tot**2
    return {"total": tot, "eTotal": float(np.sqrt(g @ cov @ g)), "pa": pa,
            "ePa": float(np.degrees(np.sqrt(h @ cov @ h)))}


# ------------------------------------------------------------- the full measurement


def _target_centroids(field: Field, stacks: PassStacks, target: Target, plx_mas: float,
                      radius: float, wing_radius: float = 9.0,
                      min_coverage: float = 0.8) -> list[dict]:
    """Fit the target in every (pass, detector) stack, starting from the catalogue track."""
    rows = []
    for c in range(stacks.n_pass):
        for d in range(1, 7):
            if stacks.nexp[c, d - 1] == 0:
                continue
            ce, cn = catalogue_track(field, target, stacks.mjd[c, d - 1], plx_mas)
            x0, y0 = offsets_to_xy(field, ce[0], cn[0])
            # Keep only pixels seen in nearly every exposure: around a saturated core the
            # others are a biased sample (valid only when the star fell further away).
            img = np.where(stacks.cov[c, d - 1] >= min_coverage, stacks.img[c, d - 1], np.nan)
            var = stacks.var[c, d - 1]
            f = fit_centre(img, var, float(x0), float(y0), radius=radius)
            if f is None or f.core_missing:
                f = fit_centre(img, var, float(x0), float(y0), radius=wing_radius) or f
            if f is None:
                continue
            wc = None if f.core_missing else windowed_centroid(img, f.x, f.y)
            rows.append({"pass": c, "det": d, "mjd": float(stacks.mjd[c, d - 1]),
                         "nExp": int(stacks.nexp[c, d - 1]), "x": f.x, "y": f.y,
                         "xWin": wc[0] if wc else None, "yWin": wc[1] if wc else None,
                         "fwhmPix": f.fwhm, "coreMissing": f.core_missing,
                         "formalErrPix": float(np.hypot(f.ex, f.ey)), "rchi2": f.rchi2})
    return rows


def _pass_positions(field: Field, rows: list[dict], reg: list[dict], target: Target,
                    plx_mas: float) -> tuple[list[dict], float]:
    """Combine detectors into one position per pass; pooled detector scatter as error."""
    if not rows:
        return [], np.nan
    by_pass: dict[int, list[dict]] = {}
    for r in rows:
        by_pass.setdefault(r["pass"], []).append(r)
    # Detectors are weighted by their formal fit errors; the formal errors are then
    # rescaled so that they reproduce the scatter actually seen between detectors.
    def weights(rs: list[dict]) -> np.ndarray:
        w = 1.0 / np.maximum([r["formalErrPix"] / np.sqrt(2) for r in rs], 0.02) ** 2
        return w / w.sum()

    chi, dof, dev = 0.0, 0, []
    for rs in by_pass.values():
        if len(rs) >= 2:
            w = weights(rs)
            for k in ("x", "y"):
                v = np.array([r[k] for r in rs])
                d = v - (w * v).sum()
                chi += float((d**2 / np.maximum([r["formalErrPix"] / np.sqrt(2) for r in rs],
                                               0.02) ** 2).sum())
                dof += len(rs) - 1
                dev.extend((d * np.sqrt(len(rs) / (len(rs) - 1.0))).tolist())
    scale = max(float(np.sqrt(chi / dof)), 1.0) if dof else 1.0
    # Per-axis scatter of one detector position (pixels), for the record.
    sig_det = float(np.sqrt(np.mean(np.square(dev)))) if dev else np.nan
    out = []
    for c, rs in sorted(by_pass.items()):
        w = weights(rs)
        fe = np.maximum([r["formalErrPix"] / np.sqrt(2) for r in rs], 0.02)
        g = reg[c]
        x = float((w * np.array([r["x"] for r in rs])).sum()) - g["dx"]
        y = float((w * np.array([r["y"] for r in rs])).sum()) - g["dy"]
        e_stat = scale * float(np.sqrt(1.0 / (1.0 / fe**2).sum())) if dof else 0.1
        ex = float(np.hypot(e_stat, np.nan_to_num(g["ex"])))
        ey = float(np.hypot(e_stat, np.nan_to_num(g["ey"])))
        mjds = np.array([r["mjd"] for r in rs])
        mjd = float((w * mjds).sum())
        east, north = xy_to_offsets(field, x, y)
        ce, cn = (np.atleast_1d((w * v).sum()) for v in
                  catalogue_track(field, target, mjds, plx_mas))
        cx, cy = offsets_to_xy(field, ce[0], cn[0])
        pe, pn = (np.atleast_1d((w * v).sum()) for v in
                  parallax_factors(target.ra, target.dec, mjds))
        ra, dec = field.wcs.all_pix2world(x, y, 0)
        out.append({
            "pass": int(c), "mjd": mjd, "year": float(mjd_to_year(mjd)), "nDet": len(rs),
            "dets": [r["det"] for r in rs], "x": float(x), "y": float(y),
            "ra": float(ra), "dec": float(dec),
            "east": float(east), "north": float(north),
            "eEast": ex * field.scale, "eNorth": ey * field.scale,
            "catX": float(cx), "catY": float(cy), "catEast": float(ce[0]), "catNorth": float(cn[0]),
            "resEast": float(east - ce[0]), "resNorth": float(north - cn[0]),
            "plxFactorEast": float(pe[0]), "plxFactorNorth": float(pn[0]),
            "regShiftXPix": float(g["dx"]), "regShiftYPix": float(g["dy"]), "nRefStars": int(g["n"]),
        })
    return out, sig_det


def _as_mas(fit: dict) -> dict:
    """Rename a ``fit_motion`` result to the data-pack convention (mas/yr, arcsec/yr)."""
    out = {
        "pmRa": 1e3 * fit["pmEast"], "pmDec": 1e3 * fit["pmNorth"],
        "ePmRa": 1e3 * fit["ePmEast"], "ePmDec": 1e3 * fit["ePmNorth"],
        "total": fit["total"], "eTotal": fit["eTotal"], "pa": fit["pa"], "ePa": fit["ePa"],
        "chi2": fit["chi2"], "dof": fit["dof"], "epoch": fit["t0"],
    }
    if "parallax" in fit:
        out["parallaxMas"] = 1e3 * fit["parallax"]
        out["eParallaxMas"] = 1e3 * fit["eParallax"]
    return out


def catalogue_motion(target: Target, plx_mas: float) -> dict:
    return {"pmRa": target.pm_ra, "pmDec": target.pm_dec,
            "total": float(np.hypot(target.pm_ra, target.pm_dec)) / 1e3,
            "pa": float(np.degrees(np.arctan2(target.pm_ra, target.pm_dec)) % 360.0),
            "parallaxMas": plx_mas, "source": target.source}


def _solve(passes: list[dict], plx_mas: float) -> dict:
    """All motion fits for a list of pass positions."""
    arr = {k: np.array([p[k] for p in passes]) for k in
           ("year", "east", "north", "eEast", "eNorth", "plxFactorEast", "plxFactorNorth")}
    args = (arr["year"], arr["east"], arr["north"], arr["eEast"], arr["eNorth"],
            arr["plxFactorEast"], arr["plxFactorNorth"])
    out = {"fixed": fit_motion(*args, parallax=plx_mas / 1e3),
           "linear": fit_motion(*args)}
    if len(passes) >= 3:
        out["free"] = fit_motion(*args, free_parallax=True)
    return out


def measure_motion(field: Field, target: Target, parallax_mas: float | None = None,
                   radius: float = 6.0, stacks: PassStacks | None = None) -> dict:
    """Per-pass positions and proper motion of a (bright enough) star, with ground truth."""
    plx = PARALLAX_MAS.get(target.key, (0.0, ""))[0] if parallax_mas is None else parallax_mas
    stacks = stacks or pass_detector_stacks(field)
    notes: list[str] = []
    rows = _target_centroids(field, stacks, target, plx, radius)
    all_img = stack_frames(field.img, field.var, grow=0)[:2]
    tx, ty = offsets_to_xy(field, *[v[0] for v in catalogue_track(field, target, field.mjd.mean())])
    saturated = bool(rows) and float(np.mean([r["coreMissing"] for r in rows])) > 0.5
    refs = find_reference_stars(*all_img, (float(tx), float(ty)),
                                avoid_r=14.0 if saturated else 8.0)
    reg = registration_offsets(stacks, refs)
    passes, sig_det = _pass_positions(field, rows, reg, target, plx)
    result: dict = {
        "method": "round-profile centre fit on per-pass, per-detector clipped mean stacks; "
                  "errors from the scatter between detectors; registration from field stars",
        "catalogue": catalogue_motion(target, plx),
        "perDetector": rows, "perPass": passes, "nPasses": len(passes),
        "detectorScatterPix": sig_det, "detectorScatterArcsec": sig_det * field.scale,
        "nReferenceStars": int(max((g["n"] for g in reg), default=0)),
        "referenceStars": [{"x": x, "y": y} for x, y in refs],
        "registration": reg, "saturatedCore": saturated, "notes": notes,
    }
    if saturated:
        notes.append("The core of the star is saturated (missing) in the stacks; the centre "
                     "comes from the unsaturated wings only.")
    if any(not np.isfinite(g["ex"]) for g in reg):
        notes.append("Too few field stars to check the registration between passes; "
                     "the image headers are trusted as they are.")
    if len(passes) < 2:
        notes.append("Fewer than two survey passes with a usable position: no motion.")
        result["measured"] = None
        return result
    fits = _solve(passes, plx)
    primary = "free" if "free" in fits else "fixed"
    meas = _as_mas(_inflate(fits[primary]))
    meas["model"] = ("proper motion + free annual (parallax-like) term" if primary == "free"
                     else "proper motion with the catalogue parallax removed")
    result["perDetectorMotion"] = _per_detector_motion(field, rows, reg, target, plx)
    meas = _with_detector_scatter(meas, result["perDetectorMotion"])
    result["measured"] = meas
    result["fits"] = {"annualTermFree": _as_mas(fits["free"]) if "free" in fits else None,
                      "parallaxFixed": _as_mas(fits["fixed"]), "linear": _as_mas(fits["linear"])}
    cat = result["catalogue"]
    d_ra, d_dec = meas["pmRa"] - cat["pmRa"], meas["pmDec"] - cat["pmDec"]
    nsig = float(np.hypot(d_ra / meas["ePmRa"], d_dec / meas["ePmDec"]))
    result["residual"] = {
        "dPmRa": d_ra, "dPmDec": d_dec, "dTotal": meas["total"] - cat["total"],
        "dPa": float((meas["pa"] - cat["pa"] + 180) % 360 - 180), "nSigma": nsig,
        "meanOffsetEast": float(np.mean([p["resEast"] for p in passes])),
        "meanOffsetNorth": float(np.mean([p["resNorth"] for p in passes])),
    }
    first, last = passes[0], passes[-1]
    result["displacementPix"] = float(np.hypot(last["x"] - first["x"], last["y"] - first["y"]))
    result["baselineYears"] = last["year"] - first["year"]
    result["parallax"] = _parallax_verdict(fits, plx, len(passes), saturated)
    if meas.get("errorSource") == "detector scatter":
        notes.append(
            f"The quoted error of the total motion ({meas['eTotal']:.2f} arcsec/yr) is the "
            f"standard error of {meas['nDetectorsForError']} independent per-detector motions; "
            f"the formal error of the weighted fit ({meas['eTotalFormal']:.2f}) is smaller "
            "because it trusts the formal centroid errors of the best detectors.")
    if primary == "fixed":
        notes.append("Only two passes: the catalogue parallax had to be assumed, and the "
                     "motion has no redundancy (zero degrees of freedom).")
    return result


MIN_DETECTORS_FOR_SCATTER = 3


def _with_detector_scatter(meas: dict, per_detector: dict) -> dict:
    """Quote the larger of the formal error and the scatter between detectors.

    The estimator is not changed. Every detector seen in two or more passes gives an
    independent motion (``_per_detector_motion``); the standard error of those values
    measures what the formal error of the weighted fit cannot: centroid systematics that
    differ from detector to detector. Both errors are kept (``...Formal``,
    ``...Detectors``) and the larger one is reported, for the total motion, its position
    angle and the two components. Needs at least three detectors.
    """
    out = dict(meas)
    keys = ("eTotal", "ePa", "ePmRa", "ePmDec")
    for k in keys:
        out[k + "Formal"] = meas[k]
    fits = per_detector.get("fits", [])
    out["errorSource"] = "formal"
    if len(fits) < MIN_DETECTORS_FOR_SCATTER:
        return out
    n = len(fits)

    def se(v) -> float:
        return float(np.std(np.asarray(v, float), ddof=1) / np.sqrt(n))

    dpa = [(f["pa"] - meas["pa"] + 180.0) % 360.0 - 180.0 for f in fits]
    scatter = {"eTotal": se([f["total"] for f in fits]), "ePa": se(dpa),
               "ePmRa": se([f["pmRa"] for f in fits]), "ePmDec": se([f["pmDec"] for f in fits])}
    for k in keys:
        out[k + "Detectors"] = scatter[k]
        out[k] = max(float(meas[k]), scatter[k])
    out["nDetectorsForError"] = n
    if scatter["eTotal"] > meas["eTotal"]:
        out["errorSource"] = "detector scatter"
    return out


def _inflate(fit: dict) -> dict:
    """Scale the errors by sqrt(chi2/dof) when the model fits worse than the errors allow."""
    out = dict(fit)
    k = float(np.sqrt(fit["chi2"] / fit["dof"])) if fit["dof"] > 0 else 1.0
    out["errorInflation"] = max(k, 1.0)
    if k > 1.0:
        for key in ("ePmEast", "ePmNorth", "eTotal", "ePa", "eParallax"):
            if key in out:
                out[key] = out[key] * k
    return out


def _parallax_verdict(fits: dict, plx_mas: float, npass: int, saturated: bool) -> dict:
    """Does the baseline support a parallax measurement?

    SPHEREx revisits a field every six months, always near 90 degrees from the Sun, so
    the parallax displacement alternates in sign from pass to pass. Anything else that
    alternates with the spacecraft orientation (registration, PSF asymmetry) has the same
    signature, so the fitted "annual term" is an upper bound on what the data know.
    """
    out: dict = {"catalogueMas": plx_mas, "nPasses": npass, "supported": False,
                 "consistentWithCatalogue": None}
    if "free" not in fits:
        out["note"] = ("Two passes give four numbers for five unknowns: proper motion and "
                       "parallax cannot be separated.")
        return out
    f = _inflate(fits["free"])
    fitted, err = 1e3 * f["parallax"], 1e3 * f["eParallax"]
    out.update(annualTermMas=fitted, errMas=err, dof=f["dof"], chi2=f["chi2"],
               chi2NoParallax=fits["linear"]["chi2"], chi2CatalogueParallax=fits["fixed"]["chi2"],
               dofFixed=fits["fixed"]["dof"])
    significant = bool(err > 0 and fitted / err >= 3.0)
    consistent = bool(err > 0 and abs(fitted - plx_mas) <= 3.0 * err)
    out["consistentWithCatalogue"] = consistent
    out["supported"] = significant and consistent and not saturated
    verdict = ("an annual term is detected and agrees with the catalogue parallax within "
               "3 sigma" if out["supported"] else
               "an annual term is detected but it does not match the catalogue parallax: "
               "it is dominated by systematics" if significant and not consistent else
               "an annual term is detected, but the star is saturated and the wing centroid "
               "is not trusted at this level" if significant else
               "no annual term is detected above 3 sigma")
    out["note"] = (f"Annual term {fitted:.0f} +- {err:.0f} mas against a catalogue parallax of "
                   f"{plx_mas:.0f} mas: {verdict}. {npass} passes leave {f['dof']} degree(s) "
                   "of freedom.")
    return out


def _per_detector_motion(field: Field, rows: list[dict], reg: list[dict], target: Target,
                         plx_mas: float) -> dict:
    """Cross-check: an independent motion from each detector seen in two or more passes.

    A constant offset of one detector (wavelength-dependent PSF asymmetry) cancels here.
    """
    fits = []
    for d in range(1, 7):
        rs = [r for r in rows if r["det"] == d]
        if len(rs) < 2:
            continue
        x = np.array([r["x"] - reg[r["pass"]]["dx"] for r in rs])
        y = np.array([r["y"] - reg[r["pass"]]["dy"] for r in rs])
        mjd = np.array([r["mjd"] for r in rs])
        east, north = xy_to_offsets(field, x, y)
        pe, pn = parallax_factors(target.ra, target.dec, mjd)
        one = np.ones(len(rs))
        f = fit_motion(mjd_to_year(mjd), east, north, one, one, pe, pn, parallax=plx_mas / 1e3)
        fits.append({"det": d, "nPasses": len(rs), "pmRa": 1e3 * f["pmEast"],
                     "pmDec": 1e3 * f["pmNorth"], "total": f["total"], "pa": f["pa"]})
    out: dict = {"fits": fits}
    if len(fits) >= 2:
        ra, dec = np.array([f["pmRa"] for f in fits]), np.array([f["pmDec"] for f in fits])
        k = np.sqrt(len(fits))
        out.update(pmRa=float(ra.mean()), pmDec=float(dec.mean()),
                   ePmRa=float(ra.std(ddof=1) / k), ePmDec=float(dec.std(ddof=1) / k),
                   total=float(np.hypot(ra.mean(), dec.mean())) / 1e3,
                   pa=float(np.degrees(np.arctan2(ra.mean(), dec.mean())) % 360))
    return out


# -------------------------------------------------- faint target: forced detection


def matched_filter(img: np.ndarray, sigma_pix: float, half: int = 4) -> np.ndarray:
    """Zero-sum Gaussian matched filter.

    Returns the best-fit point-source flux (image units times pixel) at every pixel. A
    constant local background cancels exactly. Positions whose window touches missing
    data are NaN.
    """
    yy, xx = np.mgrid[-half : half + 1, -half : half + 1]
    p = np.exp(-0.5 * (xx**2 + yy**2) / sigma_pix**2)
    p /= p.sum()
    k = p - p.mean()
    norm = float((k * p).sum())
    ok = np.isfinite(img)
    num = ndimage.correlate(np.where(ok, img, 0.0), k, mode="constant")
    full = ndimage.correlate(ok.astype(float), np.ones_like(k), mode="constant") > k.size - 0.5
    return np.where(full, num / norm, np.nan)


def snr_map(img: np.ndarray, sigma_pix: float) -> tuple[np.ndarray, float]:
    """Matched-filter flux map and its robust scatter over the image (confusion included)."""
    flux = matched_filter(img, sigma_pix)
    _, sd, npix = robust_level(flux[np.isfinite(flux)])
    return flux, (sd if npix >= 100 and np.isfinite(sd) and sd > 0 else np.nan)


def _sample(a: np.ndarray, x: float, y: float) -> float:
    """Bilinear sample; NaN outside the image or next to missing data."""
    n = a.shape[0]
    if not (0 <= x <= n - 1 and 0 <= y <= n - 1):
        return np.nan
    x0, y0 = min(int(x), n - 2), min(int(y), n - 2)
    fx, fy = x - x0, y - y0
    return float(a[y0, x0] * (1 - fx) * (1 - fy) + a[y0, x0 + 1] * fx * (1 - fy)
                 + a[y0 + 1, x0] * (1 - fx) * fy + a[y0 + 1, x0 + 1] * fx * fy)


def _peak_near(snr: np.ndarray, x0: float, y0: float, radius: float
               ) -> tuple[float, float, float] | None:
    """Brightest local maximum of an S/N map within ``radius`` pixels, sub-pixel position."""
    n = snr.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    near = (np.hypot(xx - x0, yy - y0) <= radius) & np.isfinite(snr)
    if not near.any():
        return None
    j = int(np.argmax(np.where(near, snr, -np.inf)))
    y, x = divmod(j, n)
    box = snr[max(y - 1, 0) : y + 2, max(x - 1, 0) : x + 2]
    if box.shape != (3, 3) or not np.isfinite(box).all():
        return float(x), float(y), float(snr[y, x])

    def vertex(lo: float, mid: float, hi: float) -> float:
        den = lo - 2 * mid + hi
        return 0.0 if den >= 0 else float(np.clip(0.5 * (lo - hi) / den, -0.5, 0.5))

    return (x + vertex(snr[y, x - 1], snr[y, x], snr[y, x + 1]),
            y + vertex(snr[y - 1, x], snr[y, x], snr[y + 1, x]), float(snr[y, x]))


def zero_point_search(snr_maps: list[np.ndarray], pred: list[tuple[float, float]],
                      radius: float, step: float = 0.25) -> tuple[float, float, float]:
    """Shift-and-stack along a known track with an unknown zero point.

    Every pass is sampled at its predicted position plus one common offset; the offset
    with the largest combined signal-to-noise is returned as (dx, dy, combined S/N).
    """
    offs = np.arange(-radius, radius + 1e-9, step)
    best = (0.0, 0.0, -np.inf)
    for dy in offs:
        for dx in offs:
            if dx * dx + dy * dy > radius * radius:
                continue
            v = [_sample(m, x + dx, y + dy) for m, (x, y) in zip(snr_maps, pred, strict=True)]
            if not np.isfinite(v).all():
                continue
            c = float(np.sum(v) / np.sqrt(len(v)))
            if c > best[2]:
                best = (float(dx), float(dy), c)
    return best


def combined_snr(snr_maps: list[np.ndarray], positions) -> float:
    """The shift-and-stack statistic at fixed positions: sum of the samples / sqrt(n)."""
    v = [_sample(m, float(x), float(y)) for m, (x, y) in zip(snr_maps, positions, strict=True)]
    return float(np.sum(v) / np.sqrt(len(v))) if np.isfinite(v).all() else float("nan")


def track_null_test(snr_maps: list[np.ndarray], pred, radius: float, at_track: float,
                    best: float, n_fixed: int = 2000, n_search: int = 200,
                    seed: int = 20261114) -> dict:
    """Empirical null distribution of the shift-and-stack statistic in the same maps.

    The per-pass difference maps are not independent (each is a pass minus the others),
    so the combined statistic is not a Gaussian sigma. Here the same statistic is
    evaluated for tracks that cannot contain the target: the real track shape (the
    pass-to-pass displacements) is rotated by a random angle and placed at a random zero
    point, away from the real track.

    * ``fixed``: ``n_fixed`` tracks evaluated at their own position, no search (at least
      10 pixels from the target) - to be compared with ``at_track``, the statistic at the
      catalogue prediction;
    * ``search``: ``n_search`` tracks with the full zero-point search of ``radius`` pixels
      (zero point at least ``radius + 6`` pixels from the target) - to be compared with
      ``best``, the maximum found by the real search.

    Returned are the scatter of the null and the fraction of null trials that reach the
    real values (the empirical false-alarm probabilities; with zero exceedances the
    probability is below about 3 / n at 95% confidence).
    """
    rng = np.random.default_rng(seed)
    pred = np.asarray(pred, float)
    rel = pred - pred.mean(axis=0)
    centre = pred.mean(axis=0)
    n = snr_maps[0].shape[0]

    def draw(margin: float, avoid: float) -> np.ndarray | None:
        th = rng.uniform(0.0, 2.0 * np.pi)
        c, s = np.cos(th), np.sin(th)
        z = rng.uniform(margin, n - 1 - margin, size=2)
        if np.hypot(*(z - centre)) < avoid:
            return None
        return z + rel @ np.array([[c, s], [-s, c]])

    fixed: list[float] = []
    for _ in range(20 * n_fixed):
        if len(fixed) >= n_fixed:
            break
        p = draw(6.0, 10.0)
        v = combined_snr(snr_maps, p) if p is not None else np.nan
        if np.isfinite(v):
            fixed.append(v)
    search: list[float] = []
    for _ in range(20 * n_search):
        if len(search) >= n_search:
            break
        p = draw(radius + 6.0, radius + 6.0)
        if p is None or not np.isfinite(combined_snr(snr_maps, p)):
            continue
        b = zero_point_search(snr_maps, [tuple(q) for q in p], radius)[2]
        if np.isfinite(b):
            search.append(b)
    out: dict = {"seed": seed, "nFixed": len(fixed), "nSearch": len(search),
                 "atTrack": at_track, "best": best, "searchRadiusPix": radius}
    if fixed:
        a = np.array(fixed)
        out.update(fixedStd=float(a.std()), fixedMadStd=robust_level(a)[1],
                   fixedP999=float(np.percentile(a, 99.9)), fixedMax=float(a.max()),
                   fixedExceed=int(np.sum(a >= at_track)), pFixed=float(np.mean(a >= at_track)),
                   pFixedAbove3=float(np.mean(a >= 3.0)))
    if search:
        b = np.array(search)
        out.update(searchMedian=float(np.median(b)), searchP99=float(np.percentile(b, 99)),
                   searchMax=float(b.max()), searchExceed=int(np.sum(b >= best)),
                   pSearch=float(np.mean(b >= best)))
    return out


def fit_moving_source(field: Field, target: Target, data: list[dict], sig: float, plx: float,
                      x0: float, y0: float, half: int = 6) -> dict | None:
    """Joint fit of one moving point source to the pass-minus-mean images.

    Subtracting the exposure-weighted mean of all passes removes every static source
    exactly, whatever its spectrum, and leaves F * [P(x - p_c) - mean_j P(x - p_j)] for a
    source of flux F at positions p_c. Flux, position at the mean epoch and proper motion
    are fitted to all passes at once (the parallax is fixed to the catalogue value), so
    the motion is not diluted by a static neighbour, unlike a centroid of the stack.
    ``x0, y0`` is the starting position at the epoch of the first pass in ``data``.
    """
    if len(data) < 2:
        return None
    w = np.array([d["nFrames"] for d in data], float)
    w /= w.sum()
    years = np.array([d["year"] for d in data])
    t0 = float((w * years).sum())
    pe, pn = parallax_factors(target.ra, target.dec, [d["mjd"] for d in data])
    mean = sum(np.nan_to_num(d["img"]) * wi for d, wi in zip(data, w, strict=True))
    valid = np.all([np.isfinite(d["img"]) for d in data], axis=0)
    xi, yi = round(x0), round(y0)
    n = field.n
    ys, xs = slice(max(yi - half, 0), min(yi + half + 1, n)), slice(max(xi - half, 0),
                                                                     min(xi + half + 1, n))
    yy, xx = np.mgrid[ys, xs]
    ok = valid[ys, xs]
    if ok.sum() < 50:
        return None
    dev, noise = [], []
    for d in data:
        full = np.where(valid, d["img"] - mean, np.nan)
        _, sd, _ = robust_level(full[np.isfinite(full)])
        dev.append(full[ys, xs][ok])
        noise.append(sd)
    cat = catalogue_motion(target, plx)
    e0, n0 = xy_to_offsets(field, x0, y0)
    dt0 = years[0] - t0
    p0 = np.array([0.02, float(e0) - cat["pmRa"] / 1e3 * dt0 - plx / 1e3 * pe[0],
                   float(n0) - cat["pmDec"] / 1e3 * dt0 - plx / 1e3 * pn[0],
                   cat["pmRa"] / 1e3, cat["pmDec"] / 1e3])

    def psfs(p: np.ndarray) -> list[np.ndarray]:
        out = []
        for k in range(len(data)):
            dt = years[k] - t0
            px, py = offsets_to_xy(field, p[1] + p[3] * dt + plx / 1e3 * pe[k],
                                   p[2] + p[4] * dt + plx / 1e3 * pn[k])
            g = np.exp(-0.5 * ((xx - px) ** 2 + (yy - py) ** 2) / sig**2) / (2 * np.pi * sig**2)
            out.append(g[ok])
        return out

    def resid(p: np.ndarray) -> np.ndarray:
        g = psfs(p)
        gm = sum(gi * wi for gi, wi in zip(g, w, strict=True))
        return np.concatenate([(p[0] * (gi - gm) - di) / ni
                               for gi, di, ni in zip(g, dev, noise, strict=True)])

    try:
        res = optimize.least_squares(resid, p0, x_scale=[0.02, 1.0, 1.0, 1.0, 1.0])
    except (ValueError, np.linalg.LinAlgError):
        return None
    if not res.success:
        return None
    npts = res.fun.size
    # The mean image costs one image worth of freedom; the remaining pixels are also
    # correlated by the bilinear resampling (about 2.3 output pixels per input pixel).
    dof = max(npts * (len(data) - 1) / len(data) / 2.3 - 5, 1.0)
    rchi2 = float((res.fun**2).sum() / 2.3 / dof)
    try:
        cov = np.linalg.inv(res.jac.T @ res.jac) * 2.3 * max(rchi2, 1.0)
    except np.linalg.LinAlgError:
        return None
    p = res.x
    ujy = ujy_per_mjysr(field.scale)
    out = {"t0": t0, "east0": float(p[1]), "north0": float(p[2]), "pmEast": float(p[3]),
           "pmNorth": float(p[4]), "ePmEast": float(np.sqrt(cov[3, 3])),
           "ePmNorth": float(np.sqrt(cov[4, 4])), "chi2": float((res.fun**2).sum() / 2.3),
           "dof": round(dof), "fluxUJy": float(p[0] * ujy),
           "fluxErrUJy": float(np.sqrt(cov[0, 0]) * ujy),
           "ePosArcsec": float(np.sqrt(cov[1, 1] + cov[2, 2]))}
    out.update(_polar(p[3], p[4], cov[3:5, 3:5]))
    out["track"] = []
    for k, d in enumerate(data):
        dt = years[k] - t0
        e = p[1] + p[3] * dt + plx / 1e3 * pe[k]
        nn = p[2] + p[4] * dt + plx / 1e3 * pn[k]
        px, py = offsets_to_xy(field, e, nn)
        ra, dec = field.wcs.all_pix2world(px, py, 0)
        ce, cn = catalogue_track(field, target, d["mjd"], plx)
        out["track"].append({"pass": d["pass"], "mjd": d["mjd"], "year": float(years[k]),
                             "x": float(px), "y": float(py), "east": float(e),
                             "north": float(nn), "ra": float(ra), "dec": float(dec),
                             "resEast": float(e - ce[0]), "resNorth": float(nn - cn[0])})
    return out


def faint_detection(field: Field, target: Target, parallax_mas: float | None = None,
                    dets: tuple[int, ...] = (5, 6), zero_point_radius: float = 8.0,
                    min_frames: int = 4, detect_snr: float = 5.0, null_test: bool = False,
                    control_dets: tuple[int, ...] = (1, 2, 3, 4)) -> dict:
    """Matched-filter search for a faint moving target in per-pass stacks.

    For each pass the selected detectors are stacked. Two maps are made: the stack
    itself ("direct") and the stack minus the stack of all other passes ("difference"),
    where static sources cancel and only something that moved survives. The catalogue
    proper motion fixes how the target moves from pass to pass, but its zero point may
    be off (old discovery positions), so the difference maps are shifted and stacked
    along the catalogue track for every common offset within ``zero_point_radius``
    pixels. The noise of every map is the robust scatter of the same estimator over the
    field, so it includes confusion by real sources.

    ``null_test=True`` adds ``nullTest``: the same statistic on random tracks in the same
    maps (``track_null_test``, about a minute), the reversed track and the statistic in
    ``control_dets``, where the target is expected to be absent.
    """
    plx = PARALLAX_MAS.get(target.key, (0.0, ""))[0] if parallax_mas is None else parallax_mas
    ujy = ujy_per_mjysr(field.scale)
    use = np.isin(field.det, dets)
    fwhm = float(np.nanmean(field.psf_fwhm[use])) if use.any() else 8.5
    sig = effective_sigma_pix(fwhm, field.scale)
    out: dict = {
        "method": "zero-sum Gaussian matched filter on per-pass stacks of detectors "
                  + "+".join(f"D{d}" for d in dets) + "; shift-and-stack of pass-difference "
                  "maps along the catalogue track; noise = robust scatter over the field",
        "detectors": list(dets), "psfFwhmArcsec": fwhm, "effectiveSigmaPix": sig,
        "catalogue": catalogue_motion(target, plx), "perPass": [], "notes": [],
        "detected": False,
    }
    data = _pass_maps(field, target, plx, use, sig, min_frames)
    if not data:
        out["notes"].append("No pass has enough frames in the chosen detectors.")
        return out
    key = "diff" if len(data) > 1 else "direct"
    maps = [d[key] / d[key + "Sd"] for d in data]
    pred = [(d["predX"], d["predY"]) for d in data]
    dx, dy, comb = zero_point_search(maps, pred, zero_point_radius)
    at_cat = float(np.sum([_sample(m, x, y) for m, (x, y) in zip(maps, pred, strict=True)])
                   / np.sqrt(len(maps)))
    found = bool(np.isfinite(comb) and comb >= detect_snr)
    off = (dx, dy) if found else (0.0, 0.0)
    out["zeroPoint"] = {
        "dxPix": dx, "dyPix": dy, "offsetArcsec": float(np.hypot(dx, dy) * field.scale),
        "eastArcsec": -dx * field.scale, "northArcsec": dy * field.scale,
        "combinedSnr": comb, "combinedSnrAtCatalogue": at_cat, "searchRadiusPix": zero_point_radius,
        "map": "pass-difference" if key == "diff" else "direct (single pass)",
        "trials": int(np.pi * zero_point_radius**2 / (2 * np.pi * sig**2)),
    }
    if null_test and len(data) > 1:
        out["nullTest"] = _null_block(field, target, plx, maps, pred, zero_point_radius, at_cat,
                                      comb, min_frames, control_dets)
    rows = []
    for d in data:
        x0, y0 = d["predX"] + off[0], d["predY"] + off[1]
        row = {k: d[k] for k in ("pass", "mjd", "year", "nFrames", "predX", "predY")}
        for tag in ("direct", "diff"):
            if tag not in d:
                continue
            sd = d[tag + "Sd"]
            row[tag + "ErrUJy"] = sd * ujy
            row[tag + "FluxAtCatalogueUJy"] = _sample(d[tag], d["predX"], d["predY"]) * ujy
            pk = _peak_near(d[tag] / sd, x0, y0, 1.5) if found else None
            if pk:
                row[tag + "X"], row[tag + "Y"], row[tag + "Snr"] = pk
                row[tag + "FluxUJy"] = pk[2] * sd * ujy
        if "diff" in d:
            row["selfSubtraction"] = d["overlap"]
        out["perPass"].append(row)
        if found:
            rows.extend(_faint_rows(field, target, d, sig, x0, y0))
    out["detected"] = found
    _faint_summary(field, target, plx, out, rows, found)
    if found and len(data) >= 2:
        _joint_summary(field, target, plx, out,
                       fit_moving_source(field, target, data, sig, plx,
                                         data[0]["predX"] + off[0], data[0]["predY"] + off[1]))
    return out


def _null_block(field: Field, target: Target, plx: float, maps: list, pred: list,
                radius: float, at_cat: float, comb: float, min_frames: int,
                control_dets: tuple[int, ...]) -> dict:
    """Null test of the track statistic plus two controls (reversed track, other detectors)."""
    out = track_null_test(maps, pred, radius, at_cat, comb)
    # the same positions visited in the opposite order: a mover gives a negative value,
    # a static source that merely changed brightness gives the same sign as forward
    out["reversedTrack"] = combined_snr(maps, pred[::-1])
    out["staticAtMeanPosition"] = combined_snr(
        maps, [tuple(np.mean(np.asarray(pred), axis=0))] * len(pred))
    use = np.isin(field.det, control_dets)
    if use.any():
        fwhm = float(np.nanmean(field.psf_fwhm[use]))
        ctl = _pass_maps(field, target, plx, use, effective_sigma_pix(fwhm, field.scale),
                         min_frames)
        if len(ctl) > 1:
            cmaps = [d["diff"] / d["diffSd"] for d in ctl]
            cpred = [(d["predX"], d["predY"]) for d in ctl]
            out["controlDetectors"] = {
                "detectors": list(control_dets), "atTrack": combined_snr(cmaps, cpred),
                "best": zero_point_search(cmaps, cpred, radius)[2]}
    return out


def _joint_summary(field: Field, target: Target, plx: float, out: dict,
                   joint: dict | None) -> None:
    """Make the joint moving-source fit the headline motion, keep the centroid fit beside it."""
    if joint is None:
        out["notes"].append("The joint moving-source fit did not converge; the motion is "
                            "from stack centroids and may be diluted by static neighbours.")
        return
    out["centroidFit"] = out.get("measured")
    meas = _as_mas(joint)
    meas.update(model="moving point source fitted jointly to the pass-minus-mean images; "
                      "catalogue parallax assumed", fluxUJy=joint["fluxUJy"],
                fluxErrUJy=joint["fluxErrUJy"], positionErrArcsec=joint["ePosArcsec"])
    out["measured"], out["track"] = meas, joint["track"]
    cat = out["catalogue"]
    d_ra, d_dec = meas["pmRa"] - cat["pmRa"], meas["pmDec"] - cat["pmDec"]
    res = out.setdefault("residual", {})
    res.update(dPmRa=d_ra, dPmDec=d_dec, dTotal=meas["total"] - cat["total"],
               dPa=float((meas["pa"] - cat["pa"] + 180) % 360 - 180),
               nSigma=float(np.hypot(d_ra / meas["ePmRa"], d_dec / meas["ePmDec"])),
               meanOffsetEast=float(np.mean([t["resEast"] for t in joint["track"]])),
               meanOffsetNorth=float(np.mean([t["resNorth"] for t in joint["track"]])))
    out["notes"].append(
        "Headline motion: joint fit of a moving point source to the pass-minus-mean images "
        "(static sources cancel exactly). The centroid-based fit is kept as 'centroidFit'.")


def _pass_maps(field: Field, target: Target, plx: float, use: np.ndarray, sig: float,
               min_frames: int) -> list[dict]:
    """Stack, predicted position and matched-filter maps of every usable pass."""
    data = []
    for c in range(int(field.campaign.max()) + 1):
        sel = use & (field.campaign == c)
        if sel.sum() < min_frames:
            continue
        mjd = float(field.mjd[sel].mean())
        ce, cn = catalogue_track(field, target, mjd, plx)
        x, y = offsets_to_xy(field, ce[0], cn[0])
        data.append({"pass": c, "mjd": mjd, "year": float(mjd_to_year(mjd)), "sel": sel,
                     "nFrames": int(sel.sum()), "predX": float(x), "predY": float(y),
                     "img": stack_frames(field.img[sel], field.var[sel], grow=0)[0]})
    for d in data:
        d["direct"], d["directSd"] = snr_map(d["img"], sig)
        others = [o for o in data if o is not d]
        if not others:
            continue
        w = np.array([o["nFrames"] for o in others], float)
        ok = np.all([np.isfinite(o["img"]) for o in others], axis=0)
        tpl = np.where(ok, sum(np.nan_to_num(o["img"]) * wi for o, wi in
                               zip(others, w, strict=True)) / w.sum(), np.nan)
        d["diff"], d["diffSd"] = snr_map(d["img"] - tpl, sig)
        sep = np.array([np.hypot(o["predX"] - d["predX"], o["predY"] - d["predY"]) for o in others])
        d["overlap"] = float((w * np.exp(-sep**2 / (4 * sig**2))).sum() / w.sum())
    return [d for d in data if np.isfinite(d["directSd"])]


def _faint_rows(field: Field, target: Target, d: dict, sig: float, x0: float, y0: float
                ) -> list[dict]:
    """One matched-filter position per detector for this pass (for the motion fit)."""
    rows = []
    for det in np.unique(field.det[d["sel"]]):
        sel = d["sel"] & (field.det == det)
        if sel.sum() < 3:
            continue
        flux, sd = snr_map(stack_frames(field.img[sel], field.var[sel], grow=0)[0], sig)
        pk = _peak_near(flux / sd, x0, y0, 1.5) if np.isfinite(sd) else None
        if pk is None or pk[2] < 4.0:
            continue
        rows.append({"pass": d["pass"], "det": int(det), "mjd": float(field.mjd[sel].mean()),
                     "nExp": int(sel.sum()), "x": pk[0], "y": pk[1], "snr": pk[2],
                     "coreMissing": False,
                     # Centroid error of a matched filter: about sigma_PSF / (S/N) per axis.
                     "formalErrPix": float(np.sqrt(2) * sig / pk[2])})
    return rows


def _faint_summary(field: Field, target: Target, plx: float, out: dict, rows: list[dict],
                   found: bool) -> None:
    ujy_err = [p["directErrUJy"] for p in out["perPass"]]
    err = float(1.0 / np.sqrt(np.sum(1.0 / np.square(ujy_err))))
    out["upperLimit3SigmaUJy"], out["upperLimit5SigmaUJy"] = 3 * err, 5 * err
    zp = out["zeroPoint"]
    if not found:
        out["notes"].append(
            f"No source moving along the catalogue track within {zp['searchRadiusPix']:.0f} "
            f"pixels: best combined S/N {zp['combinedSnr']:.1f}. Point-source upper limits "
            "are given for the stack of all passes.")
        return
    f = np.array([p.get("directFluxUJy", np.nan) for p in out["perPass"]])
    e = np.array(ujy_err)
    ok = np.isfinite(f)
    w = 1 / e[ok] ** 2
    out["fluxUJy"] = float((w * f[ok]).sum() / w.sum())
    out["fluxErrUJy"] = float(np.sqrt(1 / w.sum()))
    out["directSnr"] = out["fluxUJy"] / out["fluxErrUJy"]
    out["notes"].append(
        "Flux and S/N are from the direct per-pass stacks at the fitted peak (a peak flux is "
        "biased high by roughly one sigma); the pass-difference maps prove that the source "
        "moves, but their passes are not independent.")
    if zp["offsetArcsec"] > field.scale:
        yrs = zp["offsetArcsec"] / max(out["catalogue"]["total"], 1e-9)
        out["notes"].append(
            f"The source is {zp['offsetArcsec']:.1f} arcsec from the position predicted from "
            f"the catalogue entry ({zp['eastArcsec']:+.1f} east, {zp['northArcsec']:+.1f} north), "
            f"i.e. {yrs:.1f} years of proper motion: the catalogue epoch is probably wrong by "
            "that much.")
    reg = [{"dx": 0.0, "dy": 0.0, "ex": np.nan, "ey": np.nan, "n": 0}] * (
        int(field.campaign.max()) + 1)
    passes, sig_det = _pass_positions(field, rows, reg, target, plx)
    out["perDetector"], out["positions"] = rows, passes
    out["detectorScatterPix"] = sig_det
    if len(passes) < 2:
        out["measured"] = None
        out["notes"].append("Detected in fewer than two passes: no motion.")
        return
    fits = _solve(passes, plx)
    meas = _as_mas(_inflate(fits["fixed"]))
    meas["model"] = "proper motion with the catalogue parallax removed"
    out["measured"] = meas
    out["fits"] = {"annualTermFree": _as_mas(fits["free"]) if "free" in fits else None,
                   "parallaxFixed": _as_mas(fits["fixed"]), "linear": _as_mas(fits["linear"])}
    cat = out["catalogue"]
    d_ra, d_dec = meas["pmRa"] - cat["pmRa"], meas["pmDec"] - cat["pmDec"]
    out["residual"] = {
        "dPmRa": d_ra, "dPmDec": d_dec, "dTotal": meas["total"] - cat["total"],
        "dPa": float((meas["pa"] - cat["pa"] + 180) % 360 - 180),
        "nSigma": float(np.hypot(d_ra / meas["ePmRa"], d_dec / meas["ePmDec"])),
        "meanOffsetEast": float(np.mean([p["resEast"] for p in passes])),
        "meanOffsetNorth": float(np.mean([p["resNorth"] for p in passes])),
    }
    out["parallax"] = _parallax_verdict(fits, plx, len(passes), False)
    out["displacementPix"] = float(np.hypot(passes[-1]["x"] - passes[0]["x"],
                                            passes[-1]["y"] - passes[0]["y"]))
    out["baselineYears"] = passes[-1]["year"] - passes[0]["year"]
