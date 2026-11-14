"""Injection-recovery on the real frames: how faint a new source can each mode find?

Synthetic point sources (a Gaussian with the frame's ``PSF_FWHM``, broadened by the pixel
and by the resampling) are added to the *target* frames only - never to the frames that
serve as partner or as template reference - and the three difference modes are searched
again. Because every mode subtracts data from another survey pass, adding a source to a
target frame changes its residual by exactly the injected image; the sigma maps (which
depend only on the subtracted data and the frame noise) stay as they are. The injected
SNR cube is therefore ``snr + injected / sigma`` and many trials are cheap.

Two kinds of source:

``mover``   a new random position in every frame (an asteroid moves many pixels between
            SPHEREx visits);
``static``  the same sky position in every frame of one survey pass ("static but new":
            a source that was not there in the other passes).

Two kinds of site, judged on the chromatic template of the frame: ``blank`` sky (nothing
above 3 sigma within 2 pixels) and ``star`` (within 2 pixels of a pixel above 10 sigma).

A source counts as recovered when the search returns a positive detection within 1.5
pixels of it *and* there was no detection within 2.5 pixels before the injection (a
source on top of an existing false residual could not be told apart from it).

Completeness is reported at a common threshold (|SNR| > 5) and at a per-mode threshold
that gives every mode the same false-detection rate on the real, un-injected frames.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi

from .detect import MIN_AREA, THRESH, effective_sigma_pix, find_peaks
from .diffim import UJY_PER_MJYSR, Diff
from .frames import Field

FLUXES = (50.0, 80.0, 120.0, 180.0, 270.0, 400.0, 600.0, 900.0, 1400.0, 2000.0, 3000.0)
MATCH_RADIUS = 1.5  # pixels
CONFUSION_RADIUS = 2.5  # pixels
MARGIN = 4  # pixels kept free at the field edge
SEPARATION = 8.0  # minimum distance between two injections in one frame, pixels
STAMP = 4  # half-size of the injected stamp, pixels


def psf_stamp(n: int, x: float, y: float, sigma_pix: float) -> tuple[slice, slice, np.ndarray]:
    """Unit-flux Gaussian centred on (x, y): the slices of an n x n image and the stamp."""
    x0, y0 = round(x), round(y)
    ys = slice(max(y0 - STAMP, 0), min(y0 + STAMP + 1, n))
    xs = slice(max(x0 - STAMP, 0), min(x0 + STAMP + 1, n))
    gy, gx = np.mgrid[ys, xs]
    g = np.exp(-0.5 * ((gx - x) ** 2 + (gy - y) ** 2) / sigma_pix**2)
    return ys, xs, g / (2.0 * np.pi * sigma_pix**2)


def inject_image(f: Field, frame: int, x: float, y: float, flux_ujy: float) -> np.ndarray:
    """Image (n, n, MJy/sr) of one point source of ``flux_ujy`` in ``frame``."""
    out = np.zeros((f.n, f.n), dtype=np.float32)
    ys, xs, g = psf_stamp(f.n, x, y, effective_sigma_pix(float(f.psf_fwhm[frame]), f.scale))
    out[ys, xs] = g * flux_ujy / UJY_PER_MJYSR
    return out


def site_maps(f: Field, static: np.ndarray, exclude: np.ndarray | None = None):
    """Boolean cubes (blank, star) of allowed injection pixels, from the static sky."""
    with np.errstate(all="ignore"):
        s = np.nan_to_num(static / np.sqrt(f.var), nan=np.inf)  # unknown counts as occupied
    foot = np.ones((1, 5, 5), dtype=bool)
    occupied = ndi.maximum_filter(s, footprint=foot, mode="nearest") > 3.0
    finite = np.isfinite(static) & np.isfinite(f.img)
    solid = ndi.minimum_filter(finite, footprint=foot, mode="nearest")
    bright = np.where(np.isfinite(s), s, 0.0) > 10.0
    near = ndi.maximum_filter(bright, footprint=foot, mode="nearest")
    inner = np.zeros(static.shape, dtype=bool)
    inner[:, MARGIN:-MARGIN, MARGIN:-MARGIN] = True
    ok = solid & inner
    if exclude is not None:
        ok &= ~exclude
    return ok & ~occupied, ok & near


def _pick(mask2d: np.ndarray, k: int, rng: np.random.Generator, taken: list) -> list:
    """Up to ``k`` random sub-pixel positions on ``mask2d``, apart from ``taken``."""
    ys, xs = np.nonzero(mask2d)
    out = []
    for j in rng.permutation(len(ys))[: 20 * k]:
        if len(out) >= k:
            break
        x, y = xs[j] + rng.uniform(-0.5, 0.5), ys[j] + rng.uniform(-0.5, 0.5)
        if all(np.hypot(x - a, y - b) >= SEPARATION for a, b in taken + out):
            out.append((float(x), float(y)))
    return out


def mover_sites(f: Field, blank, star, per_frame: int, rng) -> list[tuple[int, float, float, str]]:
    """Independent random positions in every frame: (frame, x, y, site)."""
    sites = []
    for i in range(len(f)):
        b = _pick(blank[i], per_frame, rng, [])
        s = _pick(star[i], per_frame, rng, b)
        sites += [(i, x, y, "blank") for x, y in b] + [(i, x, y, "star") for x, y in s]
    return sites


def static_sites(f: Field, blank, star, per_pass: int, rng) -> list[tuple[int, float, float, str]]:
    """Fixed sky positions through every frame of one pass: (frame, x, y, site)."""
    sites = []
    for c in np.unique(f.campaign):
        fr = np.flatnonzero(f.campaign == c)
        always_blank = blank[fr].mean(axis=0) > 0.8
        always_star = star[fr].mean(axis=0) > 0.8
        b = _pick(always_blank, per_pass, rng, [])
        s = _pick(always_star, per_pass, rng, b)
        for kind, pts in (("blank", b), ("star", s)):
            sites += [(int(i), x, y, kind) for x, y in pts for i in fr]
    return sites


def detection_rate(d: Diff, thresh: float = THRESH, exclude: np.ndarray | None = None,
                   min_area: int = MIN_AREA, signs: tuple[float, ...] = (1.0, -1.0),
                   snr: np.ndarray | None = None) -> float:
    """Detections per usable frame in the real cube (peaks inside ``exclude`` ignored).

    Only peaks in usable frames are counted, so numerator and denominator refer to the
    same frames. ``signs=(1.0,)`` counts positive detections only; ``snr`` replaces the
    cube that is searched (e.g. a rescaled copy of ``d.snr``).
    """
    nu = int(d.usable.sum())
    if nu == 0:
        return float("nan")
    p = find_peaks(d.snr if snr is None else snr, thresh, min_area, signs=signs)
    if len(p):
        p = p[d.usable[p[:, 0].astype(int)]]
    if exclude is not None and len(p):
        p = p[~exclude[p[:, 0].astype(int), p[:, 1].astype(int), p[:, 2].astype(int)]]
    return len(p) / nu


def threshold_for_rate(d: Diff, rate: float, exclude: np.ndarray | None = None,
                       lo: float = 3.0, hi: float = 200.0) -> float:
    """SNR threshold at which the real cube gives ``rate`` detections per usable frame."""
    if not d.usable.any():
        return float("nan")
    for _ in range(10):
        mid = float(np.sqrt(lo * hi))
        if detection_rate(d, mid, exclude) > rate:
            lo = mid
        else:
            hi = mid
    return hi


def recover(f: Field, d: Diff, sites: list, flux_ujy: float, thresh: float = THRESH,
            min_area: int = MIN_AREA, base: np.ndarray | None = None) -> np.ndarray:
    """Inject ``flux_ujy`` at every site and say which ones the search finds.

    Returns an int array per site: 1 recovered, 0 missed, -1 not searchable in this
    mode (the frame has no result there), -2 confused with an existing detection.
    ``base`` may carry ``find_peaks(d.snr, thresh, 1)`` to avoid recomputing it.
    """
    out = np.zeros(len(sites), dtype=np.int8)
    snr = d.snr.copy()
    for k, (i, x, y, _) in enumerate(sites):
        sig = d.sigma[i, round(y), round(x)]
        if not d.usable[i] or not np.isfinite(sig):
            out[k] = -1
            continue
        with np.errstate(all="ignore"):
            snr[i] += inject_image(f, i, x, y, flux_ujy) / d.sigma[i]
    if base is None:
        base = find_peaks(d.snr, thresh, 1)
    found = find_peaks(snr, thresh, min_area, signs=(1.0,))
    for k, (i, x, y, _) in enumerate(sites):
        if out[k] < 0:
            continue
        b = base[base[:, 0] == i]
        if len(b) and np.min(np.hypot(b[:, 2] - x, b[:, 1] - y)) <= CONFUSION_RADIUS:
            out[k] = -2
            continue
        g = found[found[:, 0] == i]
        if len(g) and np.min(np.hypot(g[:, 2] - x, g[:, 1] - y)) <= MATCH_RADIUS:
            out[k] = 1
    return out


def flux_at_half(fluxes, completeness) -> float | None:
    """Flux where completeness first crosses 50% (log-linear interpolation), or None."""
    fl, c = np.asarray(fluxes, float), np.asarray(completeness, float)
    for a in range(len(fl) - 1):
        if c[a] < 0.5 <= c[a + 1]:
            t = (0.5 - c[a]) / (c[a + 1] - c[a])
            return float(np.exp(np.log(fl[a]) + t * (np.log(fl[a + 1]) - np.log(fl[a]))))
    return float(fl[0]) if len(c) and c[0] >= 0.5 else None


def _curves(f, d, sites, fluxes, thresh):
    """Completeness per site type: over all injections and over searchable ones only."""
    kinds = np.array([s[3] for s in sites])
    base = find_peaks(d.snr, thresh, 1)
    res = np.stack([recover(f, d, sites, fl, thresh, base=base) for fl in fluxes])  # (F, S)
    out = {}
    for kind in ("blank", "star"):
        m = kinds == kind
        r = res[:, m]
        n = int(m.sum())
        searchable = (r != -1).sum(axis=1)
        with np.errstate(all="ignore"):
            out[kind] = {
                "n": n,
                "all": ((r == 1).sum(axis=1) / max(n, 1)).round(4).tolist(),
                "searchable": np.nan_to_num((r == 1).sum(axis=1) / searchable).round(4).tolist(),
                "notSearchable": float(np.mean(r[0] == -1)) if n else None,
                "confused": float(np.mean(r[0] == -2)) if n else None,
            }
        out[kind]["f50"] = flux_at_half(fluxes, out[kind]["all"])
        out[kind]["f50Searchable"] = flux_at_half(fluxes, out[kind]["searchable"])
    return out


def injection_recovery(f: Field, diffs: dict[str, Diff], static: np.ndarray,
                       fluxes=FLUXES, per_frame: int = 2, per_pass: int = 4,
                       thresholds: dict[str, float] | None = None,
                       exclude: np.ndarray | None = None, seed: int = 20261113,
                       kinds: tuple[str, ...] = ("mover", "static")) -> dict:
    """Completeness versus flux for every mode in ``diffs``.

    ``static`` is the cube that defines blank-sky and near-star sites (the chromatic
    template); the same sites are used for every mode. ``thresholds`` maps a mode to its
    SNR threshold (default 5 for all). ``kinds`` selects the source kinds that are run
    (the sites of a kind do not depend on which kinds are run). Returns a JSON-safe dict.
    """
    rng = np.random.default_rng(seed)
    blank, star = site_maps(f, static, exclude)
    sites = {
        "mover": mover_sites(f, blank, star, per_frame, rng),
        "static": static_sites(f, blank, star, per_pass, rng),
    }
    sites = {k: v for k, v in sites.items() if k in kinds}
    out: dict = {"fluxUJy": [float(x) for x in fluxes], "seed": seed, "modes": {}}
    for mode, d in diffs.items():
        thr = float((thresholds or {}).get(mode, THRESH))
        out["modes"][mode] = {"threshold": round(thr, 2)}
        if not np.isfinite(thr):
            continue
        for kind, s in sites.items():
            out["modes"][mode][kind] = _curves(f, d, s, fluxes, thr)
    return out
