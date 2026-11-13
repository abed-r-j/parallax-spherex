"""Variability of a star whose every visit is at a different wavelength.

A raw SPHEREx light curve mixes colour with variability: two visits differ because the
star changed *and* because they looked through different parts of the filter. Two
products separate the two effects:

* ``lightcurve_by_wavelength``: one light curve per wavelength bin, built only from
  visits that fall in the same bin (same wavelength, different dates);
* ``ratio_spectrum``: for each group of visits (a survey pass, or a time bin), the ratio
  of every flux to the *reference* group's spectrum interpolated to that visit's
  wavelength, binned in wavelength. It is the brightness change in magnitudes as a
  function of wavelength.

``fit_sinusoid`` and ``period_scan`` compare a well-sampled star (R Draconis, near the
north ecliptic pole) with its known period.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import numpy as np

from .photometry import (
    CHANNELS_PER_DETECTOR,
    SUSPECT,
    Grid,
    Photometry,
    bin_values,
    channel_grid,
    combine,
)

MAG = 2.5 / np.log(10.0)  # 1.0857: magnitude error per fractional flux error


def usable(phot: Photometry, which: str = "flux", max_quality: int = SUSPECT
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Flux, error and mask of the frames that may enter a light curve."""
    v, e, ok = phot.values(which)
    if which != "wing":
        ok = (phot.quality <= max_quality) & np.isfinite(v) & np.isfinite(e)
    return v, e, ok & (v > 0) & (e > 0)


def epoch_groups(mjd: np.ndarray, width_days: float) -> np.ndarray:
    """Group index of fixed-width time bins, renumbered without gaps."""
    raw = np.floor((np.asarray(mjd) - np.min(mjd)) / width_days).astype(int)
    _, idx = np.unique(raw, return_inverse=True)
    return idx


def coarse_grid(per_detector: int = 3) -> Grid:
    """A few wide bins per detector: enough visits per bin for a light curve."""
    return channel_grid(per_detector)


def reference_sed(phot: Photometry, sel: np.ndarray, v: np.ndarray, e: np.ndarray,
                  per_detector: int = CHANNELS_PER_DETECTOR) -> dict:
    """Binned spectrum of the reference frames, one array set per detector."""
    b = bin_values(phot.lam[sel], phot.det[sel], v[sel], e[sel], channel_grid(per_detector))
    return {int(d): {k: b[k][(b["det"] == d) & (b["n"] > 0)] for k in ("lam", "value", "err")}
            for d in np.unique(b["det"])}


def interpolate_sed(sed: dict, lam: np.ndarray, det: np.ndarray, max_gap: float = 0.15
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Reference flux and error at each (wavelength, detector), log-linear in flux.

    No extrapolation, and no interpolation across a gap wider than ``max_gap`` micron.
    """
    out, err = np.full(lam.shape, np.nan), np.full(lam.shape, np.nan)
    for d, s in sed.items():
        m = det == d
        if not m.any() or len(s["lam"]) < 2:
            continue
        x, y = s["lam"], np.log(np.maximum(s["value"], 1e-30))
        ok = s["value"] > 0
        if ok.sum() < 2:
            continue
        x, y, rel = x[ok], y[ok], (s["err"] / s["value"])[ok]
        lm = lam[m]
        val = np.exp(np.interp(lm, x, y, left=np.nan, right=np.nan))
        j = np.clip(np.searchsorted(x, lm), 1, len(x) - 1)
        val[(x[j] - x[j - 1]) > max_gap] = np.nan
        out[m], err[m] = val, val * np.interp(lm, x, rel)
    return out, err


def ratio_spectrum(phot: Photometry, groups: np.ndarray | None = None, ref: int | None = None,
                   which: str = "flux", max_quality: int = SUSPECT, grid: Grid | None = None
                   ) -> dict:
    """Brightness change of every group relative to a reference group, per wavelength.

    Returns ``{"ref": g0, "groups": [{group, mjd, lam, ratio, ratioErr, dmag, dmagErr, n,
    det, meanDmag, meanDmagErr, perDetector}]}``. ``dmag`` is negative when the star is
    brighter than in the reference group.
    """
    groups = phot.campaign if groups is None else np.asarray(groups)
    grid = grid or channel_grid(6)
    v, e, ok = usable(phot, which, max_quality)
    ids = [int(g) for g in np.unique(groups[ok])]
    out: dict = {"ref": None, "which": which, "grid": grid.name, "groups": []}
    if len(ids) < 2:
        return out
    if ref is None:  # the best-populated group
        ref = max(ids, key=lambda g: int((ok & (groups == g)).sum()))
    out["ref"] = int(ref)
    out["refMjd"] = float(np.mean(phot.mjd[ok & (groups == ref)]))
    sed = reference_sed(phot, ok & (groups == ref), v, e)
    s, se = interpolate_sed(sed, phot.lam, phot.det)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = v / s
        re = r * np.sqrt((e / v) ** 2 + (se / s) ** 2)
    for g in ids:
        if g == ref:
            continue
        sel = ok & (groups == g) & np.isfinite(r) & np.isfinite(re)
        if not sel.any():
            continue
        b = bin_values(phot.lam[sel], phot.det[sel], r[sel], re[sel], grid)
        keep = b["n"] > 0
        ratio, rerr = b["value"][keep], b["err"][keep]
        row = {
            "group": g, "mjd": float(np.mean(phot.mjd[sel])), "nFrames": int(sel.sum()),
            "lam": b["lam"][keep], "det": b["det"][keep], "n": b["n"][keep],
            "ratio": ratio, "ratioErr": rerr,
            "dmag": -2.5 * np.log10(np.maximum(ratio, 1e-30)), "dmagErr": MAG * rerr / ratio,
            "perDetector": {},
        }
        for d in np.unique(row["det"]):
            m = row["det"] == d
            mean, err, n = combine(row["dmag"][m], row["dmagErr"][m])
            row["perDetector"][str(int(d))] = {"dmag": mean, "err": err, "nBins": n}
        row["meanDmag"], row["meanDmagErr"], _ = combine(row["dmag"], row["dmagErr"])
        row["slopeMagPerMicron"], row["slopeErr"] = _slope(row["lam"], row["dmag"], row["dmagErr"])
        out["groups"].append(row)
    return out


def _slope(x: np.ndarray, y: np.ndarray, e: np.ndarray) -> tuple[float, float]:
    """Weighted straight-line slope of y(x), error scaled by the scatter about the line."""
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(e) & (e > 0)
    if ok.sum() < 3:
        return np.nan, np.nan
    x, y, w = x[ok], y[ok], 1 / e[ok] ** 2
    a = np.column_stack([np.ones_like(x), x - x.mean()])
    cov = np.linalg.inv(a.T @ (a * w[:, None]))
    p = cov @ (a.T @ (w * y))
    chi2 = float((w * (y - a @ p) ** 2).sum()) / max(ok.sum() - 2, 1)
    return float(p[1]), float(np.sqrt(cov[1, 1] * max(chi2, 1.0)))


def lightcurve_by_wavelength(phot: Photometry, groups: np.ndarray | None = None,
                             which: str = "flux", max_quality: int = SUSPECT,
                             grid: Grid | None = None, min_groups: int = 2) -> list[dict]:
    """One light curve per wavelength bin from same-wavelength visits in different groups.

    Each returned bin holds the group mean date, flux, error, number of frames and the
    magnitude relative to the bin's weighted mean flux. The default bins are the 102
    narrow channels, so that no assumption about the spectrum inside a bin is needed.
    """
    groups = phot.campaign if groups is None else np.asarray(groups)
    grid = grid or channel_grid()
    v, e, ok = usable(phot, which, max_quality)
    out = []
    for k in range(len(grid)):
        inbin = ok & (phot.det == grid.det[k]) & (phot.lam >= grid.lo[k]) & (phot.lam < grid.hi[k])
        rows = []
        for g in np.unique(groups[inbin]):
            sel = inbin & (groups == g)
            f, fe, n = combine(v[sel], e[sel])
            if n:
                rows.append((int(g), float(np.mean(phot.mjd[sel])), f, fe, n,
                             float(np.mean(phot.lam[sel]))))
        if len(rows) < min_groups:
            continue
        g, t, f, fe, n, lam = (np.array(c) for c in zip(*rows, strict=True))
        mean = float(np.sum(f / fe**2) / np.sum(1 / fe**2))
        out.append({
            "lamLo": float(grid.lo[k]), "lamHi": float(grid.hi[k]), "det": int(grid.det[k]),
            "lam": float(np.mean(lam)), "group": g.astype(int), "mjd": t, "flux": f, "err": fe,
            "n": n.astype(int), "groupLam": lam,
            "mag": -2.5 * np.log10(f / mean), "magErr": MAG * fe / f, "meanFlux": mean,
            "which": which,
        })
    return out


# -------------------------------------------------------------- periodic variables


def fit_sinusoid(t: np.ndarray, mag: np.ndarray, err: np.ndarray, period: float) -> dict | None:
    """Fit mag = m0 - A cos(2 pi (t - t_max) / P) for a fixed period (maximum light at t_max)."""
    ok = np.isfinite(t) & np.isfinite(mag) & np.isfinite(err) & (err > 0)
    if ok.sum() < 4:
        return None
    t, mag, w = t[ok], mag[ok], 1 / err[ok] ** 2
    ph = 2 * np.pi * (t - t.min()) / period
    a = np.column_stack([np.ones_like(ph), np.cos(ph), np.sin(ph)])
    try:
        cov = np.linalg.inv(a.T @ (a * w[:, None]))
    except np.linalg.LinAlgError:
        return None
    p = cov @ (a.T @ (w * mag))
    chi2 = float((w * (mag - a @ p) ** 2).sum())
    dof = int(ok.sum() - 3)
    k = max(chi2 / dof, 1.0) if dof > 0 else 1.0
    amp = float(np.hypot(p[1], p[2]))
    # mag = m0 + c cos(ph) + s sin(ph) is faintest at ph = atan2(s, c); brightest half a cycle away.
    phase_max = (np.arctan2(p[2], p[1]) + np.pi) % (2 * np.pi)
    grad = np.array([-p[2], p[1]]) / max(amp**2, 1e-30)
    e_phase = float(np.sqrt(grad @ cov[1:, 1:] @ grad * k))
    g = np.array([p[1], p[2]]) / max(amp, 1e-30)
    return {
        "period": period, "amplitude": amp, "amplitudeErr": float(np.sqrt(g @ cov[1:, 1:] @ g * k)),
        "peakToPeak": 2 * amp, "tMax": float(t.min() + phase_max / (2 * np.pi) * period),
        "tMaxErr": e_phase / (2 * np.pi) * period, "mean": float(p[0]),
        "chi2": chi2, "dof": dof, "n": int(ok.sum()), "spanDays": float(np.ptp(t)),
        "chi2Constant": float((w * (mag - (w * mag).sum() / w.sum()) ** 2).sum()),
    }


def period_scan(t: np.ndarray, mag: np.ndarray, err: np.ndarray, periods: np.ndarray) -> dict:
    """Chi-square of a sinusoid for every trial period; the best one and its 1-sigma range."""
    chi = np.array([(fit_sinusoid(t, mag, err, float(p)) or {"chi2": np.nan})["chi2"]
                    for p in periods])
    if not np.isfinite(chi).any():
        return {"periods": periods, "chi2": chi, "best": np.nan, "lo": np.nan, "hi": np.nan}
    j = int(np.nanargmin(chi))
    best = fit_sinusoid(t, mag, err, float(periods[j]))
    scale = max(chi[j] / max(best["dof"], 1), 1.0)
    inside = periods[chi <= chi[j] + scale]
    return {"periods": periods, "chi2": chi, "best": float(periods[j]),
            "lo": float(inside.min()), "hi": float(inside.max()), "chi2Min": float(chi[j])}


def phase_analysis(curves: list[dict], period: float, min_points: int = 5,
                   min_span: float = 0.6, epoch_max: float | None = None) -> dict:
    """Sinusoid of the known period in every wavelength bin that is sampled well enough.

    ``epoch_max`` (MJD of a catalogued visual maximum) turns each time of maximum into a
    phase lag in cycles; without it only the differences between bins are meaningful.
    """
    rows = []
    for c in curves:
        if len(c["mjd"]) < min_points or np.ptp(c["mjd"]) < min_span * period:
            continue
        f = fit_sinusoid(c["mjd"], c["mag"], c["magErr"], period)
        if f is None or f["dof"] < 1:
            continue
        f.update(lam=c["lam"], det=c["det"], lamLo=c["lamLo"], lamHi=c["lamHi"],
                 significance=f["amplitude"] / f["amplitudeErr"] if f["amplitudeErr"] > 0 else 0.0)
        if epoch_max is not None:
            lag = ((f["tMax"] - epoch_max) / period) % 1.0
            f["phaseLag"] = float(lag if lag <= 0.5 else lag - 1.0)
            f["phaseLagErr"] = f["tMaxErr"] / period
        rows.append(f)
    out: dict = {"period": period, "bins": rows, "nBins": len(rows)}
    good = [r for r in rows if r["significance"] >= 3.0]
    out["nSignificant"] = len(good)
    if good:
        t = np.array([r["tMax"] for r in good])
        ref = t[0]
        t = ref + ((t - ref + period / 2) % period) - period / 2  # same cycle as the first
        e = np.maximum([r["tMaxErr"] for r in good], 1e-3)
        w = 1 / e**2
        out["tMaxMean"] = float((w * t).sum() / w.sum())
        out["tMaxScatterDays"] = float(np.std(t)) if len(t) > 1 else 0.0
        out["medianPeakToPeak"] = float(np.median([r["peakToPeak"] for r in good]))
    return out
