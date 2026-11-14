"""Find, measure, classify and link the sources left in a difference cube.

A *detection* is a connected group of pixels above ``thresh / 2`` in the SNR cube (of one
sign) whose peak reaches ``thresh``. Each detection gets a class together with the
evidence for it:

``motion-dipole``  a positive and a negative lobe of similar flux next to each other on a
                   static source: the source moved between the survey passes.
``variable``       a single-sign residual that keeps its sign through the frames (hence
                   wavelengths) of a survey pass: the source brightened, faded or is new.
``mover``          a positive point-like residual with no static counterpart that is not
                   there in the other frames of the pass: a solar-system object candidate.
``chromatic``      a residual on a static source where the subtracted data were more than
                   half a bandwidth away in wavelength: colour, not change.
``star-residual``  a residual on a static source at matched wavelength: imperfect
                   cancellation of an undersampled star.
``artifact``       flagged pixels, field edge, single-pixel spike, or a negative residual
                   with nothing static underneath (something was in the reference data).

``link_movers`` then joins ``mover`` detections of one survey pass into candidates when
at least three, at three different times, lie on a straight line at constant speed, and
estimates how often that would happen by chance.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import erf, exp, factorial, log, pi, sqrt

import numpy as np
from scipy import ndimage as ndi

from .diffim import UJY_PER_MJYSR, Diff
from .frames import BAD_HARD, BAD_SOFT, FLAG_BITS, Field

THRESH = 5.0
MIN_AREA = 2  # pixels above thresh / 2; a lone pixel is a spike
MAX_AREA = 30  # a faint "point-like" residual is not larger than this (pixels)
WING_MARGIN = 3.0  # allowance for the non-Gaussian PSF wings of a bright source (see max_area)
STATIC_RATIO = 3.0  # a residual above this many times the static flux is not a star residual
MAX_RATE = 170.0  # arcsec/hour: fastest motion the same-visit veto lets through (see link_movers)
EDGE = 2  # pixels
COUNTERPART_SNR = 5.0  # static source underneath: subtracted image above this many sigma
PERSIST_FRACTION = 0.7  # "keeps its sign": same sign in this fraction of the pass frames
PERSIST_MEDIAN = 1.5  # ... and a median signed SNR of at least this
PERSIST_MIN_FRAMES = 5
DIPOLE_RADIUS = 3  # pixels
VISIT_MINUTES = 6.0  # exposures closer in time than this belong to one visit
ARTIFACT_FLAGS = (BAD_SOFT & ~(1 << FLAG_BITS["OUTLIER"])) | BAD_HARD
_PLANE = np.zeros((3, 3, 3), dtype=bool)
_PLANE[1] = True  # connect pixels inside a frame, never across frames


@dataclass
class Detection:
    frame: int
    x: float
    y: float
    ra: float
    dec: float
    snr: float
    flux_ujy: float
    cls: str
    npix: int
    evidence: str
    known: str | None = None

    def to_json(self) -> dict:
        """The record the data contract asks for (plus ``npix`` and ``evidence``)."""
        d = asdict(self)
        return {
            "frame": d["frame"], "x": round(d["x"], 2), "y": round(d["y"], 2),
            "ra": round(d["ra"], 6), "dec": round(d["dec"], 6), "snr": round(d["snr"], 1),
            "fluxUJy": round(d["flux_ujy"], 1), "cls": d["cls"], "known": d["known"],
            "npix": d["npix"], "evidence": d["evidence"],
        }


def effective_sigma_pix(fwhm_arcsec: float, scale: float) -> float:
    """Gaussian sigma (pixels) of a point source on the resampled grid.

    Optical PSF (header ``PSF_FWHM``) broadened by the pixel itself (variance 1/12 px^2)
    and by the bilinear resampling onto the common grid (variance 1/6 px^2 on average).
    """
    fwhm = fwhm_arcsec if np.isfinite(fwhm_arcsec) else 7.5
    return float(sqrt((fwhm / 2.3548 / scale) ** 2 + 1.0 / 12.0 + 1.0 / 6.0))


def box_fraction(sigma_pix: float) -> float:
    """Fraction of a centred Gaussian's flux inside a 3x3 pixel box."""
    return erf(1.5 / (sqrt(2.0) * sigma_pix)) ** 2


def max_area(snr: float, sigma_pix: float, thresh: float = THRESH) -> float:
    """Largest footprint (pixels above ``thresh / 2``) a point source of peak ``snr`` may have.

    A Gaussian of peak S/N ``S`` and width ``sigma_pix`` stays above ``thresh / 2`` inside
    r^2 < 2 sigma^2 ln(2 S / thresh), an area of 2 pi sigma^2 ln(2 S / thresh) pixels: the
    footprint of a point source grows with its brightness. The real SPHEREx PSF has wings
    beyond a Gaussian, so ``WING_MARGIN`` times that area is allowed on top of the fixed
    ``MAX_AREA`` (measured on asteroid (52) Europa: 30 to 75 pixels at S/N 110 to 235,
    where the Gaussian areas are 14 to 20 pixels).
    """
    s = abs(float(snr))
    if not s > thresh / 2.0:
        return float(MAX_AREA)
    return MAX_AREA + WING_MARGIN * 2.0 * pi * sigma_pix**2 * log(2.0 * s / thresh)


def find_peaks(snr: np.ndarray, thresh: float = THRESH, min_area: int = 1,
               signs: tuple[float, ...] = (1.0, -1.0)):
    """Connected residual sources of both signs in an SNR cube (N, n, n).

    Returns arrays (frame, y, x, peak_snr, npix): the peak pixel of every connected
    component above ``thresh / 2`` whose peak reaches ``thresh`` and that has at least
    ``min_area`` pixels. ``peak_snr`` is signed.
    """
    out = []
    z = np.nan_to_num(snr, nan=0.0)
    for sign in signs:
        s = z * sign
        lab, nlab = ndi.label(s > thresh / 2.0, structure=_PLANE)
        if nlab == 0:
            continue
        idx = np.arange(1, nlab + 1)
        peak = ndi.maximum(s, lab, idx)
        keep = peak >= thresh
        if not keep.any():
            continue
        npix = ndi.sum(np.ones_like(lab, dtype=np.int32), lab, idx)
        keep &= npix >= min_area
        pos = np.array(ndi.maximum_position(s, lab, idx[keep])).reshape(-1, 3)
        out.append(np.column_stack([pos, sign * peak[keep], npix[keep]]))
    if not out:
        return np.zeros((0, 5))
    return np.concatenate(out)


def _box(a: np.ndarray, y: int, x: int, r: int = 1) -> np.ndarray:
    return a[max(y - r, 0): y + r + 1, max(x - r, 0): x + r + 1]


def _centroid(snr2d, y, x, sign):
    """SNR-weighted centroid of the 3x3 box around the peak (same-sign pixels only)."""
    n = snr2d.shape[0]
    ys = slice(max(y - 1, 0), min(y + 2, n))
    xs = slice(max(x - 1, 0), min(x + 2, n))
    w = np.clip(np.nan_to_num(snr2d[ys, xs]) * sign, 0, None)
    gy, gx = np.mgrid[ys, xs]
    tot = w.sum()
    return (float((w * gy).sum() / tot), float((w * gx).sum() / tot)) if tot > 0 else (y, x)


def _persistence(f: Field, d: Diff, frame: int, y: int, x: int, sign: float):
    """Does the residual keep its sign through the usable frames of the survey pass?"""
    sel = d.usable & (f.campaign == f.campaign[frame])
    s = d.snr[sel][:, max(y - 1, 0): y + 2, max(x - 1, 0): x + 2] * sign
    with np.errstate(all="ignore"):
        s = np.nanmean(s.reshape(len(s), -1), axis=1)
    s = s[np.isfinite(s)]
    if len(s) < PERSIST_MIN_FRAMES:
        return False, 0.0, 0.0, len(s)
    frac, med = float(np.mean(s > 0)), float(np.median(s))
    return frac >= PERSIST_FRACTION and med >= PERSIST_MEDIAN, frac, med, len(s)


def _dipole(d: Diff, frame: int, y: int, x: int, sign: float, flux: float):
    """Opposite-sign lobe of similar flux close by, or None.

    Normally the lobe must lie within DIPOLE_RADIUS pixels and carry 1/3 to 3 times the
    flux. Around a saturated star the core is missing data, so the two lobes are searched
    across the hole (twice the radius) and the flux ratio may be 1/6 to 6.
    """
    n = d.snr.shape[1]
    hole = not np.isfinite(_box(d.snr[frame], y, x, DIPOLE_RADIUS)).all()
    r, lim = (2 * DIPOLE_RADIUS, 6.0) if hole else (DIPOLE_RADIUS, 3.0)
    ys, xs = slice(max(y - r, 0), min(y + r + 1, n)), slice(max(x - r, 0), min(x + r + 1, n))
    win = np.nan_to_num(d.snr[frame, ys, xs]) * -sign
    j = np.unravel_index(int(np.argmax(win)), win.shape)
    if win[j] < max(3.0, 0.2 * abs(d.snr[frame, y, x])):
        return None
    oy, ox = j[0] + ys.start, j[1] + xs.start
    oflux = float(np.nansum(_box(d.resid[frame], oy, ox)))
    ratio = abs(oflux) / max(abs(flux), 1e-12)
    if not (1 / lim <= ratio <= lim) or oflux * flux >= 0:
        return None
    return oy, ox, ratio, hole


def _same_visit(f: Field, d: Diff, frame: int, y: int, x: int):
    """Peak SNR at this position in the other exposures of the same visit.

    SPHEREx steps the sky across its detectors, so a position is usually exposed again
    about two minutes later, and simultaneously in the detector that shares the field
    through the dichroic. Nothing in the sky moves a pixel in two minutes; a residual
    that is absent from the next exposure of the same detector is a cosmic ray or a
    detector transient. Returns a list of (frame, detector, snr).
    """
    near = np.flatnonzero((np.abs(f.mjd - f.mjd[frame]) < VISIT_MINUTES / 1440.0) & d.usable)
    out = []
    for t in near:
        if t == frame:
            continue
        box = _box(d.snr[t], y, x)
        if np.isfinite(box).any():
            out.append((int(t), int(f.det[t]), float(np.nanmax(box))))
    return out


def classify(f: Field, d: Diff, frame: int, y: int, x: int, snr: float, npix: int,
             min_area: int = MIN_AREA) -> tuple[str, str]:
    """Class and evidence of the detection whose peak pixel is (frame, y, x)."""
    sign = 1.0 if snr > 0 else -1.0
    n = f.n
    if min(y, x) < EDGE or max(y, x) >= n - EDGE:
        return "artifact", "at the field edge"
    flux = float(np.nansum(_box(d.resid[frame], y, x)))
    static_box = _box(d.static[frame], y, x)
    noise = float(np.sqrt(np.nanmedian(f.var[frame])))
    with np.errstate(all="ignore"):
        static_peak = float(np.nan_to_num(np.nanmax(static_box), nan=0.0))
    has_static = static_peak > COUNTERPART_SNR * noise
    dip = _dipole(d, frame, y, x, sign, flux)
    if dip is not None:
        oy, ox, ratio, hole = dip
        with np.errstate(all="ignore"):
            other = float(np.nan_to_num(np.nanmax(_box(d.static[frame], oy, ox)), nan=0.0))
        if has_static or other > COUNTERPART_SNR * noise:
            return "motion-dipole", (
                f"opposite lobe {ox - x:+d},{oy - y:+d} px away, flux ratio {ratio:.2f}, "
                + ("across the saturated core of a static source" if hole
                   else "on a static source"))
    if not np.isfinite(_box(d.snr[frame], y, x)).all():
        return "artifact", "next to missing data"
    if (_box(f.flags[frame], y, x) & ARTIFACT_FLAGS).any():
        return "artifact", "suspect-pixel flag set within one pixel"
    if npix < min_area:
        return "artifact", f"single-pixel spike ({npix} px above half threshold)"
    persistent, frac, med, nfr = _persistence(f, d, frame, y, x, sign)
    ptxt = f"same sign in {100 * frac:.0f}% of {nfr} frames of the pass, median SNR {med:.1f}"
    counterpart = "no static counterpart"
    if has_static:
        rel = abs(flux) / max(float(np.nansum(np.clip(static_box, 0, None))), 1e-12)
        if persistent:
            return "variable", f"{ptxt}; {100 * rel:.0f}% of the static flux"
        # Imperfect cancellation of a star leaves a fraction of its flux. A positive
        # residual several times brighter than everything static in the same 3x3 box is
        # not that: it is a new source that happens to lie on a faint one.
        if not (sign > 0 and rel > STATIC_RATIO):
            mism = float(np.nan_to_num(abs(d.mismatch[frame, y, x])))
            if mism > 0.5:
                return "chromatic", (
                    f"on a static source, subtracted data {mism:.1f} bandwidths away in "
                    "wavelength")
            return "star-residual", (
                f"{100 * rel:.0f}% of the static flux, wavelength matched to {mism:.2f} "
                "bandwidths")
        counterpart = f"{rel:.0f} times the faint static source underneath"
    elif persistent:
        what = "new or strongly brightened" if sign > 0 else "faded"
        return "variable", f"{ptxt}; no static counterpart: {what} source"
    if sign < 0:
        return "artifact", "negative residual with no static source underneath"
    limit = max_area(snr, effective_sigma_pix(float(f.psf_fwhm[frame]), f.scale))
    if npix > limit:
        return "artifact", (f"extended ({npix} px, more than the {limit:.0f} px a point source "
                            f"of this brightness covers), not point-like")
    visit = _same_visit(f, d, frame, y, x)
    same = [s for _, dd, s in visit if dd == f.det[frame]]
    if same and max(same) < 0.5 * abs(snr):
        return "artifact", (
            f"not repeated in the next exposure of detector {int(f.det[frame])} minutes "
            f"later (SNR {max(same):.1f}): cosmic ray or detector transient")
    seen = [f"D{dd} SNR {s:.1f}" for _, dd, s in visit if s >= 3.0]
    missed = [f"D{dd}" for _, dd, s in visit if s < 3.0]
    vtxt = ("confirmed in the same visit: " + ", ".join(seen)) if seen else (
        "no other exposure of the same visit to confirm it" if not visit
        else "not seen in the same-visit exposures of " + ", ".join(missed))
    return "mover", f"point-like ({npix} px), {counterpart}; {vtxt}"


def detect(f: Field, d: Diff, thresh: float = THRESH, min_area: int = MIN_AREA,
           frames: np.ndarray | None = None) -> list[Detection]:
    """All detections of a difference cube, classified, ordered by frame."""
    snr = d.snr if frames is None else d.snr[frames]
    peaks = find_peaks(snr, thresh, 1)
    fmap = np.arange(len(f)) if frames is None else np.asarray(frames)
    wcs = f.wcs
    out: list[Detection] = []
    for fr, y, x, s, npix in peaks:
        i, y, x, npix = int(fmap[int(fr)]), int(y), int(x), int(npix)
        sig = effective_sigma_pix(float(f.psf_fwhm[i]), f.scale)
        cy, cx = _centroid(d.snr[i], y, x, np.sign(s))
        ra, dec = wcs.all_pix2world(cx, cy, 0)
        flux = float(np.nansum(_box(d.resid[i], y, x))) * UJY_PER_MJYSR / box_fraction(sig)
        cls, why = classify(f, d, i, y, x, float(s), npix, min_area)
        out.append(Detection(i, cx, cy, float(ra), float(dec), float(s), flux, cls, npix, why))
    out.sort(key=lambda q: (q.frame, -abs(q.snr)))
    return out


def _tangent(f: Field, dets: list[Detection]):
    """East/north offsets (arcsec) from the field centre, and time in hours."""
    c = (f.n - 1) / 2
    east = np.array([-(q.x - c) * f.scale for q in dets])
    north = np.array([(q.y - c) * f.scale for q in dets])
    hours = np.array([f.mjd[q.frame] * 24.0 for q in dets])
    return east, north, hours


def _poisson_tail(lam: float, k: int) -> float:
    """P(X >= k) for a Poisson variable of mean ``lam``."""
    if k <= 0:
        return 1.0
    return max(0.0, 1.0 - sum(exp(-lam) * lam**i / factorial(i) for i in range(k)))


def _n_visits(hours: np.ndarray) -> int:
    """Number of distinct visits among exposure times (hours)."""
    t = np.sort(np.asarray(hours, float))
    return int(1 + np.sum(np.diff(t) > VISIT_MINUTES / 60.0)) if len(t) else 0


def _fit_track(east, north, hours):
    t = hours - hours.mean()
    den = float((t * t).sum())
    ve, vn = float((t * east).sum() / den), float((t * north).sum() / den)
    res = np.hypot(east - east.mean() - ve * t, north - north.mean() - vn * t)
    return ve, vn, float(np.sqrt(np.mean(res**2)))


def link_movers(f: Field, dets: list[Detection], tol_pix: float = 1.5,
                min_rate: float = 1.0, max_rate: float = MAX_RATE, min_det: int = 3) -> list[dict]:
    """Join ``mover`` detections of one survey pass into linear-motion candidates.

    ``max_rate`` defaults to ``MAX_RATE`` (170 arcsec/hour), the speed limit of the
    classifier itself: the same-visit veto of ``classify`` looks for the source in the
    3x3 pixels around its peak in the next exposure about 2.15 minutes later, so anything
    moving more than about one pixel (6.15 arcsec) in that time, i.e. faster than about
    170 arcsec/hour, is already called a cosmic ray and never reaches the linker. The
    linker therefore does not claim a range the classifier cannot deliver.

    Rates are in arcsec/hour, position angles in degrees east of north. A candidate
    needs detections in ``min_det`` different visits within ``tol_pix`` of a
    constant-velocity track. ``chance`` is the expected number of such alignments in
    the pass if the mover detections were scattered at random over the field.
    """
    movers = [q for q in dets if q.cls == "mover"]
    cands: list[dict] = []
    tol = tol_pix * f.scale
    area = (f.n * f.scale) ** 2
    for c in np.unique(f.campaign):
        m = [q for q in movers if f.campaign[q.frame] == c]
        if len(m) < min_det:
            continue
        e, nn, h = _tangent(f, m)
        found: list[tuple[set, float]] = []
        pairs = 0
        for a in range(len(m)):
            for b in range(len(m)):
                dt = h[b] - h[a]
                if dt <= 1 / 60:
                    continue
                rate = np.hypot(e[b] - e[a], nn[b] - nn[a]) / dt
                if not (min_rate <= rate <= max_rate):
                    continue
                pairs += 1
                ve, vn = (e[b] - e[a]) / dt, (nn[b] - nn[a]) / dt
                dist = np.hypot(e - e[a] - ve * (h - h[a]), nn - nn[a] - vn * (h - h[a]))
                members = set(np.flatnonzero(dist <= tol).tolist())
                if _n_visits(h[sorted(members)]) < min_det:
                    continue
                others = len(m) - len(members)
                lam = others * pi * tol**2 / area
                found.append((members, _poisson_tail(lam, len(members) - 2)))
        taken: set = set()
        for members, p in sorted(found, key=lambda s: -len(s[0])):
            if len(members & taken) > 0:
                continue
            taken |= members
            k = sorted(members, key=lambda i: h[i])
            ve, vn, rms = _fit_track(e[k], nn[k], h[k])
            chance = pairs * p
            cands.append({
                "id": f"M{len(cands) + 1}", "cls": "mover",
                "frames": [m[i].frame for i in k], "ra": [round(m[i].ra, 6) for i in k],
                "dec": [round(m[i].dec, 6) for i in k],
                "mjd": [round(float(f.mjd[m[i].frame]), 6) for i in k],
                "rate": round(float(np.hypot(ve, vn)), 2),
                "pa": round(float(np.degrees(np.arctan2(ve, vn)) % 360), 1),
                "known": None, "chance": float(chance),
                "note": (f"{len(k)} detections on a line (rms {rms:.1f} arcsec) in pass {int(c)}; "
                         f"expected chance alignments in this pass: {chance:.2g}"),
            })
    return cands


def group_static(f: Field, dets: list[Detection], cls: str, radius_pix: float = 2.0,
                 min_det: int = 3) -> list[dict]:
    """Group detections of class ``cls`` that sit at the same sky position."""
    pool = sorted((q for q in dets if q.cls == cls), key=lambda q: -abs(q.snr))
    groups: list[list[Detection]] = []
    for q in pool:
        for g in groups:
            if np.hypot(q.x - g[0].x, q.y - g[0].y) <= radius_pix:
                g.append(q)
                break
        else:
            groups.append([q])
    out = []
    prefix = {"motion-dipole": "D", "variable": "V"}.get(cls, "G")
    for g in groups:
        if len(g) < min_det:
            continue
        g.sort(key=lambda q: q.frame)
        out.append({
            "id": f"{prefix}{len(out) + 1}", "cls": cls, "frames": [q.frame for q in g],
            "ra": [round(q.ra, 6) for q in g], "dec": [round(q.dec, 6) for q in g],
            "mjd": [round(float(f.mjd[q.frame]), 6) for q in g], "rate": None, "pa": None,
            "known": None,
            "note": f"{len(g)} detections at one position, median |SNR| "
                    f"{np.median([abs(q.snr) for q in g]):.1f}",
        })
    return out


def candidates(f: Field, dets: list[Detection]) -> list[dict]:
    """Linked movers plus repeated motion-dipole and variable detections."""
    return (link_movers(f, dets) + group_static(f, dets, "motion-dipole")
            + group_static(f, dets, "variable"))
