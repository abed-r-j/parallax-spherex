"""Object-first search: which SPHEREx Level-2 images actually contain a given asteroid,
comet or planet, and where to point a demo field so that the object crosses it.

How it works (all steps verified against the live services, November 2026):

1. JPL Horizons gives the hourly ephemeris of the object *as seen from SPHEREx*
   (observer ``500@-163182``) over the whole archive.
2. SPHEREx only looks roughly at right angles to the Sun (we measured solar elongations
   of 80-130 degrees in our own fields), so only the parts of the track inside an
   elongation window can have been imaged. Those parts are cut into chunks that fit in a
   small sky box, and each chunk is ONE query to the IRSA TAP table ``spherex.plane``:
   ``INTERSECTS(poly, POLYGON(box)) = 1 AND time_bounds_lower BETWEEN t0 AND t1``.
   (``INTERSECTS`` with a ``CIRCLE`` is rejected by IRSA TAP; with a ``POLYGON`` it works.)
3. Each returned image footprint (``poly``, an EWKB polygon) is tested locally against
   the ephemeris position at the mid-exposure time; hits are then re-computed with
   Horizons at the exact time (the hourly table cannot follow the 98-minute parallax
   wobble of a low-Earth-orbit observer, which is several arcsec for a main-belt object).

Two kinds of demo field can be built from the hits:

* a FIXED sky field that the object crosses (``best_fixed_field``): the object is in a
  few frames and absent from all others, the key test for the chromatic template;
* a CO-MOVING set of cutouts centred on the object in each image (its spectrum).

Data: SPHEREx Level-2 Spectral Images, NASA/IPAC Infrared Science Archive. Ephemerides:
JPL Horizons (see ``parallax.sso`` for citations).

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import csv
import io
import json
import re
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
import numpy as np

from .catalogs import IRSA_TAP, USER_AGENT, fetch_text
from .irsa import ImageRef, list_images, remote_cutout
from .sso import Ephemeris, horizons_at, horizons_range

ARCHIVE_MJD = (60789.0, 61320.0)  # first and last SPHEREx Level-2 image at IRSA (Nov 2026)
ELONG_WINDOW = (75.0, 135.0)
PIXEL_ARCSEC = 6.15


@dataclass(frozen=True)
class MoverHit:
    """One Level-2 image whose footprint contains the object at exposure time."""

    uri: str
    collection: str
    det: int
    mjd: float  # mid-exposure, UT
    ra: float  # object as seen from SPHEREx, ICRF degrees
    dec: float
    vmag: float
    rate_ra: float  # arcsec/h as seen from SPHEREx (includes spacecraft motion)
    rate_dec: float
    elong: float
    delta: float  # au
    edge_arcsec: float  # distance from the object to the nearest footprint edge

    @property
    def ref(self) -> ImageRef:
        return ImageRef(self.uri, self.mjd, self.mjd, f"SPHEREx-D{self.det}", self.collection)


def parse_ewkb_polygon(hexstr: str) -> np.ndarray:
    """Outer ring of a (E)WKB polygon as an (k, 2) array of (ra, dec) degrees."""
    b = bytes.fromhex(hexstr.strip())
    end = "<" if b[0] == 1 else ">"
    (typ,) = struct.unpack_from(end + "I", b, 1)
    off = 5 + (4 if typ & 0x20000000 else 0)
    if typ & 0xFF != 3:
        raise ValueError(f"not a WKB polygon (type {typ:#x})")
    _, npts = struct.unpack_from(end + "II", b, off)
    pts = struct.unpack_from(end + f"{2 * npts}d", b, off + 8)
    return np.array(pts, float).reshape(npts, 2)


def _gnomonic(ra, dec, ra0: float, dec0: float) -> tuple[np.ndarray, np.ndarray]:
    """Tangent-plane offsets (arcsec, east and north) of (ra, dec) about (ra0, dec0)."""
    a, d = np.radians(np.asarray(ra, float) - ra0), np.radians(np.asarray(dec, float))
    d0 = np.radians(dec0)
    c = np.sin(d0) * np.sin(d) + np.cos(d0) * np.cos(d) * np.cos(a)
    xi = np.cos(d) * np.sin(a) / c
    eta = (np.cos(d0) * np.sin(d) - np.sin(d0) * np.cos(d) * np.cos(a)) / c
    return np.degrees(xi) * 3600.0, np.degrees(eta) * 3600.0


def footprint_margin(ra: float, dec: float, poly: np.ndarray) -> float:
    """Signed distance (arcsec) from a point to the edge of a convex footprint.

    Positive inside, negative outside. The polygon is projected onto the tangent plane
    at the point, so the test is exact on the sphere for footprints a few degrees wide.
    """
    x, y = _gnomonic(poly[:, 0], poly[:, 1], ra, dec)
    if np.allclose([x[0], y[0]], [x[-1], y[-1]]):
        x, y = x[:-1], y[:-1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    cross = x * y2 - x2 * y  # twice the signed area of (origin, p_i, p_i+1)
    dist = cross / np.hypot(x2 - x, y2 - y)
    if np.sum(cross) < 0:
        dist = -dist
    return float(dist.min())


def track_chunks(eph: Ephemeris, elong: tuple[float, float] = ELONG_WINDOW,
                 max_box_deg: float = 4.0, max_days: float = 25.0) -> list[dict]:
    """Cut the observable part of an ephemeris into pieces that fit in a small sky box."""
    ra = np.degrees(np.unwrap(np.radians(eph.ra)))
    ok = (eph.elong >= elong[0]) & (eph.elong <= elong[1])
    chunks: list[dict] = []
    start = None
    for i in range(len(eph) + 1):
        if start is None:
            if i < len(eph) and ok[i]:
                start = i
            continue
        seg = slice(start, i + 1) if i < len(eph) else slice(start, i)
        cosd = np.cos(np.radians(eph.dec[start]))
        too_big = i < len(eph) and (
            (np.ptp(ra[seg]) * cosd > max_box_deg) or (np.ptp(eph.dec[seg]) > max_box_deg)
            or (eph.mjd[i] - eph.mjd[start] > max_days)
        )
        if i == len(eph) or not ok[i] or too_big:
            s = slice(start, i)
            chunks.append({
                "mjd0": float(eph.mjd[start]), "mjd1": float(eph.mjd[i - 1]),
                "ra0": float(ra[s].min()), "ra1": float(ra[s].max()),
                "dec0": float(eph.dec[s].min()), "dec1": float(eph.dec[s].max()),
            })
            start = i if (i < len(eph) and ok[i]) else None
    return chunks


def _box_adql(ch: dict, pad_deg: float) -> str:
    cosd = max(0.2, float(np.cos(np.radians(0.5 * (ch["dec0"] + ch["dec1"])))))
    r0, r1 = ch["ra0"] - pad_deg / cosd, ch["ra1"] + pad_deg / cosd
    d0, d1 = max(-89.9, ch["dec0"] - pad_deg), min(89.9, ch["dec1"] + pad_deg)
    corners = [(r0, d0), (r1, d0), (r1, d1), (r0, d1)]
    poly = ", ".join(f"{r % 360.0:.4f}, {d:.4f}" for r, d in corners)
    return (
        "SELECT p.obs_publisher_did, p.time_bounds_lower, p.time_bounds_upper, "
        "p.energy_bandpassname, p.poly, a.uri "
        "FROM spherex.plane AS p JOIN spherex.artifact AS a ON p.planeid = a.planeid "
        f"WHERE INTERSECTS(p.poly, POLYGON('ICRS', {poly})) = 1 "
        f"AND p.time_bounds_lower BETWEEN {ch['mjd0'] - 0.01:.4f} AND {ch['mjd1'] + 0.05:.4f}"
    )


def images_near_chunk(ch: dict, pad_deg: float = 0.05, cache_dir: Path | None = None,
                      timeout: float = 600.0) -> list[dict]:
    """All Level-2 images that touch the sky box of one track chunk during its time span."""
    text = fetch_text(
        "spherex_plane", IRSA_TAP,
        {"QUERY": _box_adql(ch, pad_deg), "FORMAT": "CSV", "LANG": "ADQL", "MAXREC": "200000"},
        cache_dir=cache_dir, timeout=timeout,
        accept=lambda t: t.lstrip().startswith("obs_publisher_did"),
    )
    out, seen = [], set()
    for row in csv.DictReader(io.StringIO(text.lstrip())):
        uri = row["uri"].strip()
        if not uri.endswith(".fits") or uri in seen:
            continue
        seen.add(uri)
        m = re.search(r"spherex_[a-z0-9_]+", row["obs_publisher_did"])
        d = re.search(r"D(\d)", row["energy_bandpassname"])
        out.append({
            "uri": uri, "collection": m.group(0) if m else "unknown",
            "det": int(d.group(1)) if d else 0,
            "mjd": 0.5 * (float(row["time_bounds_lower"]) + float(row["time_bounds_upper"])),
            "poly": parse_ewkb_polygon(row["poly"]),
        })
    return out


def _hits_from_images(images: list[dict], eph: Ephemeris, min_margin: float) -> list[dict]:
    hits = []
    for im in images:
        ra, dec = (float(v) for v in eph.at(im["mjd"]))
        if footprint_margin(ra, dec, im["poly"]) >= min_margin:
            hits.append(im)
    return hits


def find_images(name: str | int, mjd_start: float = ARCHIVE_MJD[0],
                mjd_stop: float = ARCHIVE_MJD[1], *, elong: tuple[float, float] = ELONG_WINDOW,
                cache_dir: Path | None = None, progress=None) -> list[MoverHit]:
    """SPHEREx Level-2 images that contain solar-system object ``name``, oldest first."""
    say = progress or (lambda m: None)
    eph = horizons_range(name, mjd_start, mjd_stop, "1 h", cache_dir=cache_dir)
    chunks = track_chunks(eph, elong)
    say(f"{eph.name}: {len(eph)} hourly positions, {len(chunks)} observable track chunks")
    rough: dict[str, dict] = {}
    for k, ch in enumerate(chunks):
        images = images_near_chunk(ch, cache_dir=cache_dir)
        got = _hits_from_images(images, eph, min_margin=-30.0)
        for im in got:
            rough[im["uri"]] = im
        say(f"  chunk {k + 1}/{len(chunks)} MJD {ch['mjd0']:.1f}-{ch['mjd1']:.1f}: "
            f"{len(images)} images nearby, {len(got)} contain the track")
    ims = sorted(rough.values(), key=lambda im: (im["mjd"], im["det"]))
    if not ims:
        return []
    exact = horizons_at(name, [im["mjd"] for im in ims], cache_dir=cache_dir)
    hits = []
    for i, im in enumerate(ims):
        margin = footprint_margin(float(exact.ra[i]), float(exact.dec[i]), im["poly"])
        if margin < 0:
            continue
        hits.append(MoverHit(
            uri=im["uri"], collection=im["collection"], det=im["det"], mjd=round(im["mjd"], 6),
            ra=round(float(exact.ra[i]), 6), dec=round(float(exact.dec[i]), 6),
            vmag=float(exact.vmag[i]), rate_ra=float(exact.rate_ra[i]),
            rate_dec=float(exact.rate_dec[i]), elong=float(exact.elong[i]),
            delta=float(exact.delta[i]), edge_arcsec=round(margin, 1),
        ))
    return hits


def best_fixed_field(hits: list[MoverHit], size_pix: int = 61, scale: float = PIXEL_ARCSEC,
                     margin_pix: float = 6.0, max_days: float = 45.0,
                     ) -> tuple[float, float, list[int]]:
    """Field centre (ra, dec) whose square field holds the most distinct visits.

    Candidate centres are the hit positions and the midpoints of pairs of hits less than
    ``max_days`` apart (one survey pass). The object must stay ``margin_pix`` inside the
    field edge. Ties are broken in favour of
    more hits, then of the object being farther from the image edges.
    Returns (ra, dec, indices of the hits inside the field).
    """
    if not hits:
        raise ValueError("no hits")
    ra = np.array([h.ra for h in hits])
    dec = np.array([h.dec for h in hits])
    mjd = np.array([h.mjd for h in hits])
    half = (size_pix / 2.0 - margin_pix) * scale
    best: tuple[tuple, float, float, np.ndarray] | None = None
    for i in range(len(hits)):
        near = np.flatnonzero(np.abs(mjd - mjd[i]) < max_days)
        for j in near[near >= i]:
            c_ra, c_dec = (float(v) for v in _midpoint(ra[i], dec[i], ra[j], dec[j]))
            x, y = _gnomonic(ra[near], dec[near], c_ra, c_dec)
            inside = near[(np.abs(x) <= half) & (np.abs(y) <= half)]
            visits = len(np.unique(np.round(mjd[inside] * 1440.0 / 5.0)))
            edge = float(np.mean([hits[k].edge_arcsec for k in inside])) if len(inside) else 0.0
            score = (visits, len(inside), edge)
            if best is None or score > best[0]:
                best = (score, c_ra, c_dec, inside)
    assert best is not None
    return round(best[1], 5), round(best[2], 5), [int(k) for k in best[3]]


def _midpoint(ra1, dec1, ra2, dec2) -> tuple[float, float]:
    dra = ((ra2 - ra1 + 180.0) % 360.0) - 180.0
    return (ra1 + dra / 2.0) % 360.0, (dec1 + dec2) / 2.0


def select_refs(all_refs: list[ImageRef], must: set[str], max_n: int,
                dets: tuple[int, ...] | None = None) -> list[ImageRef]:
    """Choose at most ``max_n`` images: every ``must`` image, then the rest thinned evenly.

    ``dets`` restricts the non-mandatory images to some detectors (a chromatic template
    for detector k only needs other-pass frames of detector k).
    """
    keep = [r for r in all_refs if r.name in must]
    rest = [r for r in all_refs if r.name not in must
            and (dets is None or int(r.band[-1]) in dets)]
    room = max(0, max_n - len(keep))
    if len(rest) > room:
        idx = np.unique(np.linspace(0, len(rest) - 1, room).round().astype(int)) if room else []
        rest = [rest[i] for i in idx]
    return sorted(keep + rest, key=lambda r: (r.mjd_start, r.band))


def download_cutouts(jobs: list[tuple[ImageRef, float, float]], size_pix: int, out_dir: Path,
                     mirror: str = "s3", threads: int = 3, progress=None) -> dict:
    """Download one cutout per (image, ra, dec) job into ``out_dir`` (existing files kept).

    Files are named like ``parallax.irsa.fetch_field`` names them, so
    ``parallax.frames.build_field`` reads the folder directly.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    say = progress or (lambda m: None)

    def one(job: tuple[ImageRef, float, float]) -> tuple[str, int, str]:
        ref, ra, dec = job
        fn = out_dir / ref.name.replace(".fits", f"_cut{size_pix}.fits")
        if fn.exists():
            return ref.name, 0, "exists"
        err = ""
        for attempt in range(3):
            try:
                with httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT}) as c:
                    hl, nb = remote_cutout(ref.url(mirror), ra, dec, size_pix, client=c,
                                           multirange=(mirror == "irsa"))
                hl[1].header["COLLECT"] = (ref.collection, "IRSA collection")
                tmp = fn.with_suffix(".tmp")
                hl.writeto(tmp, overwrite=True)
                tmp.replace(fn)
                return ref.name, nb, ""
            except ValueError as e:
                return ref.name, 0, f"skip: {e}"
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:120]}"
                time.sleep(2 * (attempt + 1))
        return ref.name, 0, err

    t0 = time.time()
    stats = {"requested": len(jobs), "downloaded": 0, "existing": 0, "skipped": 0,
             "failed": [], "bytes": 0}
    with ThreadPoolExecutor(threads) as ex:
        for k, (name, nb, err) in enumerate(ex.map(one, jobs), 1):
            stats["bytes"] += nb
            if not err:
                stats["downloaded"] += 1
            elif err == "exists":
                stats["existing"] += 1
            elif err.startswith("skip"):
                stats["skipped"] += 1
            else:
                stats["failed"].append([name, err])
            if k % 25 == 0 or k == len(jobs):
                say(f"  {k}/{len(jobs)}  {time.time() - t0:.0f}s  {stats['bytes'] / 1e6:.0f} MB")
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def fixed_field_jobs(ra: float, dec: float, hits: list[MoverHit], inside: list[int],
                     max_n: int, dets: tuple[int, ...] | None = None,
                     ) -> tuple[list[tuple[ImageRef, float, float]], int]:
    """Download jobs for a fixed field: every frame with the object, plus other visits.

    With ``dets`` only those detectors are used at all. Returns (jobs, number of images
    available at that position in those detectors before the cap).
    """
    refs = {r.name: r for r in list_images(ra, dec)}
    must = set()
    for k in inside:
        if dets is None or hits[k].det in dets:
            refs.setdefault(hits[k].ref.name, hits[k].ref)
            must.add(hits[k].ref.name)
    if dets is not None:
        refs = {k: r for k, r in refs.items() if int(r.band[-1]) in dets}
    chosen = select_refs(list(refs.values()), must, max_n, dets)
    return [(r, ra, dec) for r in chosen], len(refs)


def box_flux(img: np.ndarray, cx: int, cy: int, half: int = 2, gap: int = 2,
             width: int = 3) -> tuple[float, float, int]:
    """Background-subtracted sum in a (2*half+1)^2 box, in MJy/sr * pixels.

    The background is the median of a square ring ``gap`` pixels outside the box and
    ``width`` pixels wide; the error is the ring scatter times sqrt(box area). Returns
    (sum, error, number of non-finite box pixels). A deliberately simple estimator: no
    PSF fit, no aperture correction (the 5x5 box is 31 arcsec across).
    """
    r_out = half + gap + width
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    cheb = np.maximum(np.abs(xx - cx), np.abs(yy - cy))
    box = cheb <= half
    ring = (cheb > half + gap) & (cheb <= r_out) & np.isfinite(img)
    if box.sum() < (2 * half + 1) ** 2 or ring.sum() < 20:
        return float("nan"), float("nan"), int(box.sum())
    bkg = float(np.median(img[ring]))
    sd = 1.4826 * float(np.median(np.abs(img[ring] - bkg)))
    vals = img[box]
    n_bad = int((~np.isfinite(vals)).sum())
    return float(np.nansum(vals - bkg)), sd * float(np.sqrt(box.sum())), n_bad


def comoving_spectrum(raw_dir: Path, ujy_per_mjysr: float = 889.86) -> list[dict]:
    """Box photometry of the object in every co-moving cutout of ``raw_dir``.

    Reads the ``_mover.json`` manifest written by ``scripts/find_mover_fields.py comoving``
    and returns one dict per usable cutout, sorted by wavelength:
    ``{lam, bw, flux_mjy, err_mjy, mjd, det, vmag, delta, n_bad, name}``. The object is
    located from the Horizons position through the cutout's own WCS. Cutouts with missing
    pixels or pixels flagged as bad or suspect (cosmic-ray transients, non-linear, ...)
    inside the box are kept but carry ``n_bad`` > 0; plot only ``n_bad == 0``.
    """
    from astropy.io import fits  # local imports keep the search functions light
    from astropy.wcs import WCS

    from .frames import BAD_HARD, bitmask, wavelength_at

    raw_dir = Path(raw_dir)
    manifest = json.loads((raw_dir / "_mover.json").read_text(encoding="utf-8"))
    size = manifest["size_pix"]
    out = []
    for h in manifest["hits"]:
        fn = raw_dir / h["uri"].rsplit("/", 1)[1].replace(".fits", f"_cut{size}.fits")
        if not fn.exists():
            continue
        with fits.open(fn) as hl:
            hdr = hl["IMAGE"].header
            img = hl["IMAGE"].data.astype(float) - hl["ZODI"].data.astype(float)
            flg = hl["FLAGS"].data.astype(np.int64)
            px, py = (float(v) for v in WCS(hdr).all_world2pix(h["ra"], h["dec"], 0))
            lam, bw = wavelength_at(hl["WCS-WAVE"], hdr, np.array(px), np.array(py))
        cx, cy = round(px), round(py)
        s, e, n_bad = box_flux(img, cx, cy)
        if not np.isfinite(s):
            continue
        # OUTLIER and SOURCE are not counted: the archive pipeline sets them on the moving
        # object itself (half of the box pixels of (52) Europa carry OUTLIER).
        suspect = BAD_HARD | bitmask("TRANSIENT", "OVERFLOW", "NONLINEAR", "PERSIST")
        n_bad += int(((flg[cy - 2:cy + 3, cx - 2:cx + 3] & suspect) != 0).sum())
        out.append({
            "lam": round(float(lam), 4), "bw": round(float(bw), 4),
            "flux_mjy": round(s * ujy_per_mjysr / 1000.0, 3),
            "err_mjy": round(e * ujy_per_mjysr / 1000.0, 3), "mjd": h["mjd"], "det": h["det"],
            "vmag": h["vmag"], "delta": h["delta"], "n_bad": n_bad,
            "name": fn.name,
        })
    return sorted(out, key=lambda r: r["lam"])


def register_target(path: Path, entry: dict) -> None:
    """Add or replace one entry (same fields as ``parallax.targets.Target``) in a JSON list."""
    path = Path(path)
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    items = [e for e in items if e.get("key") != entry["key"]] + [entry]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=1), encoding="utf-8")


def hits_table(hits: list[MoverHit]) -> list[dict]:
    """JSON-ready list of hits (for manifests and reports)."""
    return [asdict(h) for h in hits]
