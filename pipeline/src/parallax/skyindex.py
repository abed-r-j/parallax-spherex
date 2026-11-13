"""Static sky index: which SPHEREx Level-2 images cover a sky position, and when.

The public ParallaX site is static, and a browser cannot query NASA/IPAC IRSA (no CORS),
but it can read the public SPHEREx bucket on S3. This module turns the IRSA image
catalogue (about 1.6 million detector images) into a compact set of binary files that
the site ships, so a browser can answer "which images contain RA/Dec X?" by itself and
build the S3 URL of every one of them.

Three parts:

1. ``dump_catalogue``  copies the catalogue rows from the IRSA TAP service into a local
   cache, one raw CSV per MJD day, resumable and incremental.
2. ``build_index``     writes the index: 28-byte little-endian records, sharded by a
   declination-band sky grid on the footprint centre, time-sorted, plus ``manifest.json``.
3. ``SkyIndex.query``  reads the index back and returns the images whose footprint
   contains a point, with exactly the test the web client uses.

The byte-exact format and the client algorithm are in ``docs/SKY_INDEX.md``.

Data: SPHEREx Level-2 Spectral Images, NASA/IPAC Infrared Science Archive
(DR1 doi:10.26131/IRSA678, QR3 doi:10.26131/IRSA662).

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

import httpx
import numpy as np

TAP_SYNC = "https://irsa.ipac.caltech.edu/TAP/sync"
USER_AGENT = "ParallaX-SpaceApps2026/1.0"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE = REPO_ROOT / "data" / "cache" / "skyindex"
DEFAULT_OUT = REPO_ROOT / "web" / "public" / "skyindex"

CSV_HEADER = "obs_publisher_did,time_bounds_lower,poly,uri"


# --------------------------------------------------------------------------------------
# 1. Catalogue dump (resumable, one raw CSV per MJD day)
# --------------------------------------------------------------------------------------


def _tap_csv(client: httpx.Client, adql: str, retries: int = 6, progress=print) -> str:
    """Run one synchronous TAP query and return the CSV text (validated, with retries)."""
    err = ""
    for attempt in range(retries):
        try:
            r = client.get(
                TAP_SYNC,
                params={"QUERY": adql, "FORMAT": "CSV", "LANG": "ADQL", "MAXREC": 2000000},
            )
            r.raise_for_status()
            text = r.text
            first = text.split("\n", 1)[0].strip()
            if "<" in first or "," not in first:
                raise RuntimeError(f"not a CSV answer: {text[:200]!r}")
            if text and not text.endswith("\n"):
                raise RuntimeError("truncated answer (no final newline)")
            return text
        except Exception as e:  # network trouble or a server hiccup: back off, try again
            err = f"{type(e).__name__}: {str(e)[:160]}"
            progress(f"    retry {attempt + 1}/{retries} after error: {err}")
            time.sleep(min(120, 5 * 2**attempt))
    raise RuntimeError(f"TAP query failed after {retries} tries: {err}")


def archive_summary(client: httpx.Client, progress=print) -> dict[str, dict]:
    """Row count and time span of every collection, straight from IRSA (one slow query)."""
    text = _tap_csv(
        client,
        "SELECT obs_collection, COUNT(*) AS n, MIN(t_min) AS t0, MAX(t_min) AS t1 "
        "FROM spherex.obscore GROUP BY obs_collection",
        progress=progress,
    )
    out: dict[str, dict] = {}
    for line in text.strip().split("\n")[1:]:
        name, n, t0, t1 = (x.strip() for x in line.split(","))
        out[name] = {
            "rows": int(n),
            "mjd_min": float(t0) if t0 else None,
            "mjd_max": float(t1) if t1 else None,
        }
    return out


def chunk_path(cache: Path, day: int) -> Path:
    return Path(cache) / "chunks" / f"mjd_{day:05d}.csv"


def _load_state(cache: Path) -> dict:
    f = Path(cache) / "state.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"chunks": {}, "summary": {}}


def _save_state(cache: Path, state: dict) -> None:
    f = Path(cache) / "state.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(f)


def dump_catalogue(
    cache: Path = DEFAULT_CACHE,
    workers: int = 2,
    refresh: bool = False,
    max_chunks: int | None = None,
    newest_first: bool = False,
    batch_days: int = 5,
    progress=print,
) -> dict:
    """Bring the local copy of the IRSA SPHEREx image catalogue up to date.

    The catalogue is cut into one chunk per MJD day (``time_bounds_lower`` in [d, d+1)),
    saved as CSV rows exactly as the server sent them. A chunk is *final* once the archive
    holds data later than that day; final chunks are never fetched again unless
    ``refresh``. So a re-run after a new data release only downloads the new days.
    """
    cache = Path(cache)
    (cache / "chunks").mkdir(parents=True, exist_ok=True)
    state = _load_state(cache)
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=900, follow_redirects=True) as c0:
        progress("asking IRSA for the per-collection summary (about a minute) ...")
        summary = archive_summary(c0, progress)
    sci = {k: v for k, v in summary.items() if v["mjd_min"] is not None}
    t_lo = min(v["mjd_min"] for v in sci.values())
    t_hi = max(v["mjd_max"] for v in sci.values())
    state["summary"] = summary
    state["summary_fetched_unix"] = int(time.time())
    days = list(range(math.floor(t_lo), math.floor(t_hi) + 1))
    todo = []
    for d in days:
        ent = state["chunks"].get(str(d))
        ok = ent is not None and ent.get("final") and chunk_path(cache, d).exists()
        if refresh or not ok:
            todo.append(d)
    if newest_first:
        todo.reverse()
    if max_chunks is not None:
        todo = todo[:max_chunks]
    progress(
        f"archive spans MJD {t_lo:.3f} .. {t_hi:.3f} ({len(days)} day chunks); "
        f"{len(todo)} to fetch, {len(days) - len(todo)} already final in cache"
    )
    # one query covers up to ``batch_days`` consecutive days (each query costs several
    # seconds before the first byte, so fewer, larger queries are kinder and faster)
    batches: list[list[int]] = []
    for d in todo:
        last = batches[-1] if batches else None
        if last and len(last) < batch_days and abs(d - last[-1]) == 1:
            last.append(d)
        else:
            batches.append([d])
    lock = threading.Lock()
    local = threading.local()
    t0 = time.time()
    stats = {"fetched": 0, "rows": 0, "bytes": 0, "failed": []}

    def one(batch: list[int]) -> None:
        if not hasattr(local, "c"):
            local.c = httpx.Client(headers=headers, timeout=900, follow_redirects=True)
        lo, hi = min(batch), max(batch) + 1
        adql = (
            "SELECT p.obs_publisher_did, p.time_bounds_lower, p.poly, a.uri "
            "FROM spherex.plane AS p JOIN spherex.artifact AS a ON p.planeid = a.planeid "
            f"WHERE p.time_bounds_lower >= {lo} AND p.time_bounds_lower < {hi}"
        )
        try:
            text = _tap_csv(local.c, adql, progress=progress)
            lines = text.split("\n")
            if lines[0].strip() != CSV_HEADER:
                raise RuntimeError(f"unexpected header {text[:120]!r}")
            per_day: dict[int, list[str]] = {d: [] for d in batch}
            for line in lines[1:]:
                if line.strip():
                    per_day[math.floor(float(line.split(",", 2)[1]))].append(line.rstrip("\r"))
        except Exception as e:
            with lock:
                stats["failed"].append((lo, f"{type(e).__name__}: {str(e)[:200]}"))
            return
        with lock:
            for d, rows in per_day.items():
                body = "\n".join([CSV_HEADER, *rows]) + "\n"
                f = chunk_path(cache, d)
                tmp = f.with_suffix(".tmp")
                tmp.write_bytes(body.encode("utf-8"))
                tmp.replace(f)
                state["chunks"][str(d)] = {
                    "rows": len(rows),
                    "bytes": len(body),
                    "fetched_unix": int(time.time()),
                    "final": bool(d + 1 <= math.floor(t_hi)),
                }
                stats["fetched"] += 1
                stats["rows"] += len(rows)
                stats["bytes"] += len(body)
            _save_state(cache, state)
            k = stats["fetched"]
            el = time.time() - t0
            progress(
                f"  {k}/{len(todo)} days  {stats['rows']} rows  {stats['bytes'] / 1e6:.1f} MB  "
                f"{el:.0f}s  eta {el / k * (len(todo) - k) / 60:.0f} min"
            )
        time.sleep(1.0)  # be polite

    with ThreadPoolExecutor(max(1, min(2, workers))) as ex:
        list(ex.map(one, batches))
    _save_state(cache, state)
    stats["seconds"] = time.time() - t0
    stats["days_total"] = len(days)
    stats["days_cached"] = sum(1 for d in days if chunk_path(cache, d).exists())
    stats["cached_rows"] = sum(
        state["chunks"][str(d)]["rows"] for d in days if str(d) in state["chunks"]
    )
    stats["archive_rows"] = sum(v["rows"] for v in sci.values())
    if stats["days_cached"] == len(days) and stats["cached_rows"] != stats["archive_rows"]:
        progress(
            f"NOTE: the cache holds {stats['cached_rows']} rows but IRSA reports "
            f"{stats['archive_rows']}: older days changed at the archive (a re-release?). "
            "Run again with refresh=True (--refresh) to download everything afresh."
        )
    return stats


# --------------------------------------------------------------------------------------
# 2. Format constants and geometry shared by the builder and the reader
# --------------------------------------------------------------------------------------

FORMAT_NAME = "parallax-skyindex"
FORMAT_VERSION = 1
S3_ROOT = "https://nasa-irsa-spherex.s3.amazonaws.com/"
DOIS = {"dr1": "10.26131/IRSA678", "qr3": "10.26131/IRSA662"}

DEG_UNIT = 1e-7  # degrees per count of ra / dec
TAN_UNIT = 1.6e-6  # tangent-plane radians per count of a corner offset (0.33 arcsec)
ARCSEC_PER_RAD = 206264.80624709636
MJD_EPOCH = 60000.0
MJD_UNIT = 1e-6  # days per count of t (0.0864 s)
BAND_HEIGHT_DEG = 5.0
PART_MAX_RECORDS = 16384  # 458,752 bytes

# bit layout of the ``id`` word, least significant bit first
DET_BITS, SUFFIX_BITS, SEQ_BITS, PREFIX_BITS = 3, 3, 12, 14
SUFFIX_SHIFT = DET_BITS
SEQ_SHIFT = SUFFIX_SHIFT + SUFFIX_BITS
PREFIX_SHIFT = SEQ_SHIFT + SEQ_BITS

RECORD_DTYPE = np.dtype(
    [
        ("ra", "<u4"),
        ("dec", "<i4"),
        ("x1", "<i2"),
        ("y1", "<i2"),
        ("x2", "<i2"),
        ("y2", "<i2"),
        ("x3", "<i2"),
        ("y3", "<i2"),
        ("t", "<u4"),
        ("id", "<u4"),
    ]
)
assert RECORD_DTYPE.itemsize == 28

KEY_TEMPLATE = (
    "{release}/level2/{period}/{procver}/{det}/"
    "level2_{period}_{seq:04d}_{suffix}D{det}_spx_{procver}.fits"
)
SHARD_TEMPLATE = "b{band:02d}/c{cell:03d}_{part:03d}.bin"


def make_key(release: str, period: str, procver: str, det: int, seq: int, suffix: int) -> str:
    """S3 object key (also the IRSA path after ``ibe/data/spherex/``) of one image."""
    return KEY_TEMPLATE.format(
        release=release, period=period, procver=procver, det=det, seq=seq, suffix=suffix
    )


def grid_cells_per_band(band_height_deg: float = BAND_HEIGHT_DEG) -> list[int]:
    """Number of equal RA cells in every declination band, south to north."""
    nb = round(180.0 / band_height_deg)
    out = []
    for b in range(nb):
        mid = -90.0 + (b + 0.5) * band_height_deg
        out.append(max(1, round(360.0 * math.cos(math.radians(mid)) / band_height_deg)))
    return out


def cell_of(ra_deg, dec_deg, n_cells, band_height_deg: float = BAND_HEIGHT_DEG):
    """(band, cell) of positions; works on scalars and numpy arrays."""
    n = np.asarray(n_cells)
    band = np.clip(np.floor((np.asarray(dec_deg) + 90.0) / band_height_deg), 0, len(n) - 1)
    band = band.astype(np.int64)
    nc = n[band]
    cell = np.floor(np.mod(ra_deg, 360.0) / (360.0 / nc)).astype(np.int64)
    return band, np.minimum(cell, nc - 1)


def cells_for_point(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    n_cells: list[int],
    band_height_deg: float = BAND_HEIGHT_DEG,
) -> list[tuple[int, int]]:
    """Every (band, cell) that can hold a footprint centre within ``radius_deg`` of a point.

    This is the shard-selection rule of the format (conservative: it may name a cell that
    turns out to hold nothing relevant, never the opposite).
    """
    nb = len(n_cells)
    b0 = max(0, min(nb - 1, math.floor((dec_deg - radius_deg + 90.0) / band_height_deg)))
    b1 = max(0, min(nb - 1, math.floor((dec_deg + radius_deg + 90.0) / band_height_deg)))
    over_pole = dec_deg + radius_deg >= 90.0 or dec_deg - radius_deg <= -90.0
    if not over_pole:
        s = math.sin(math.radians(radius_deg)) / math.cos(math.radians(dec_deg))
        over_pole = s >= 1.0
    half = 360.0 if over_pole else math.degrees(math.asin(s))
    ra = ra_deg % 360.0
    out: list[tuple[int, int]] = []
    for b in range(b0, b1 + 1):
        n = n_cells[b]
        w = 360.0 / n
        k0 = math.floor((ra - half) / w)
        k1 = math.floor((ra + half) / w)
        if over_pole or k1 - k0 + 1 >= n:
            out.extend((b, k) for k in range(n))
        else:
            out.extend((b, k % n) for k in range(k0, k1 + 1))
    return out


def gnomonic(ra0, dec0, ra, dec):
    """Tangent-plane (xi east, eta north, cos c) of points about (ra0, dec0); radians in."""
    dra = ra - ra0
    sd0, cd0 = np.sin(dec0), np.cos(dec0)
    sd, cd = np.sin(dec), np.cos(dec)
    cdra = np.cos(dra)
    cosc = sd0 * sd + cd0 * cd * cdra
    safe = np.where(cosc > 1e-9, cosc, 1.0)
    xi = cd * np.sin(dra) / safe
    eta = (cd0 * sd - sd0 * cd * cdra) / safe
    return xi, eta, cosc


def footprint_margin(rec: np.ndarray, ra_deg: float, dec_deg: float) -> np.ndarray:
    """Signed distance (arcsec) from a point to the nearest edge of each record's footprint.

    Positive inside, negative outside, -inf on the far hemisphere. The footprint is the
    quadrilateral with great-circle edges through the four stored corners; in the tangent
    plane about the record centre those edges are straight lines, so this is plane geometry.
    """
    ra0 = np.radians(rec["ra"].astype(np.float64) * DEG_UNIT)
    dec0 = np.radians(rec["dec"].astype(np.float64) * DEG_UNIT)
    xi, eta, cosc = gnomonic(ra0, dec0, math.radians(ra_deg), math.radians(dec_deg))
    px, py = xi / TAN_UNIT, eta / TAN_UNIT
    x = [rec["x1"].astype(np.float64), rec["x2"].astype(np.float64), rec["x3"].astype(np.float64)]
    y = [rec["y1"].astype(np.float64), rec["y2"].astype(np.float64), rec["y3"].astype(np.float64)]
    x.append(-(x[0] + x[1] + x[2]))
    y.append(-(y[0] + y[1] + y[2]))
    area2 = np.zeros(len(rec))
    for k in range(4):
        j = (k + 1) % 4
        area2 += x[k] * y[j] - x[j] * y[k]
    # ring direction: +1 counter-clockwise (inside on the left of every edge), -1 clockwise
    sign = np.sign(area2)
    margin = np.full(len(rec), np.inf)
    for k in range(4):
        j = (k + 1) % 4
        ex, ey = x[j] - x[k], y[j] - y[k]
        cross = ex * (py - y[k]) - ey * (px - x[k])
        margin = np.minimum(margin, sign * cross / np.maximum(np.hypot(ex, ey), 1e-9))
    ok = (cosc > 1e-9) & (sign != 0)
    return np.where(ok, margin * (TAN_UNIT * ARCSEC_PER_RAD), -np.inf)


# --------------------------------------------------------------------------------------
# 3. Build
# --------------------------------------------------------------------------------------

_DID_RE = re.compile(r"^ivo://irsa\.ipac/(spherex_[a-z0-9_]+)\?.+/D([1-6])$")
_URI_RE = re.compile(
    r"^ibe/data/spherex/([^/]+)/level2/([^/]+)/([^/]+)/([1-6])/"
    r"level2_(.+)_(\d+)_(\d+)D([1-6])_spx_(.+)\.fits$"
)
_POLY_HEAD = "0103000020E61000000100000005000000"  # WKB polygon, SRID 4326, 1 ring, 5 points
_POLY_LEN = len(_POLY_HEAD) + 5 * 32


def load_catalogue(cache: Path = DEFAULT_CACHE, progress=print) -> dict:
    """Parse every cached chunk into arrays (one entry per unique image file)."""
    cache = Path(cache)
    files = sorted((cache / "chunks").glob("mjd_*.csv"))
    colls: list[str] = []
    prefixes: dict[tuple[int, str, str, str], int] = {}
    coll_i, pref_i, seq_l, suf_l, det_l, mjd_l, hex_l = [], [], [], [], [], [], []
    seen: set[str] = set()
    skipped = {"duplicate": 0, "bad_did": 0, "bad_uri": 0, "bad_poly": 0, "key_mismatch": 0}
    examples: list[str] = []
    for f in files:
        for line in f.read_text(encoding="utf-8").split("\n")[1:]:
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != 4:
                skipped["bad_uri"] += 1
                continue
            did, t, poly, uri = (p.strip() for p in parts)
            m = _DID_RE.match(did)
            u = _URI_RE.match(uri)
            why = ""
            if not m:
                why = "bad_did"
            elif not u:
                why = "bad_uri"
            elif len(poly) != _POLY_LEN or not poly.startswith(_POLY_HEAD):
                why = "bad_poly"
            if why:
                skipped[why] += 1
                if len(examples) < 5:
                    examples.append(f"{why}: {line[:200]}")
                continue
            release, period, procver, det, seq, suffix = u.group(1, 2, 3, 4, 6, 7)
            det_n, seq_n, suf_n = int(det), int(seq), int(suffix)
            # the path must be exactly what the client will rebuild from the tokens
            key = make_key(release, period, procver, det_n, seq_n, suf_n)
            if "ibe/data/spherex/" + key != uri or m.group(2) != det:
                skipped["key_mismatch"] += 1
                if len(examples) < 5:
                    examples.append(f"key_mismatch: {uri}")
                continue
            if uri in seen:
                skipped["duplicate"] += 1
                continue
            seen.add(uri)
            cname = m.group(1)
            if cname not in colls:
                colls.append(cname)
            pk = (colls.index(cname), release, period, procver)
            pi = prefixes.get(pk)
            if pi is None:
                pi = prefixes[pk] = len(prefixes)
            coll_i.append(pk[0])
            pref_i.append(pi)
            seq_l.append(seq_n)
            suf_l.append(suf_n)
            det_l.append(det_n)
            mjd_l.append(float(t))
            hex_l.append(poly[len(_POLY_HEAD) : len(_POLY_HEAD) + 128])
    n = len(mjd_l)
    corners = np.frombuffer(bytes.fromhex("".join(hex_l)), "<f8").reshape(n, 4, 2).copy()
    progress(f"parsed {len(files)} chunks: {n} images, skipped {skipped}")
    # deterministic tables: collections by name, prefixes by (period, release, collection, procver)
    colls_sorted = sorted(colls)
    c_map = np.array([colls_sorted.index(c) for c in colls] or [0], np.int64)
    named = [(k[2], k[1], colls[k[0]], k[3]) for k in prefixes]
    p_order = sorted(range(len(named)), key=lambda i: named[i])
    p_map = np.zeros(max(1, len(named)), np.int64)
    p_map[p_order] = np.arange(len(named))
    prefix_table = [
        [colls_sorted.index(named[i][2]), named[i][1], named[i][0], named[i][3]] for i in p_order
    ]
    return {
        "collections": colls_sorted,
        "prefixes": prefix_table,  # [collection index, release, period, procver]
        "coll": c_map[np.array(coll_i, np.int64)],
        "prefix": p_map[np.array(pref_i, np.int64)],
        "seq": np.array(seq_l, np.int64),
        "suffix": np.array(suf_l, np.int64),
        "det": np.array(det_l, np.int64),
        "mjd": np.array(mjd_l, np.float64),
        "corners": corners,  # (n, 4, 2) RA, Dec in degrees, ring order
        "skipped": skipped,
        "skipped_examples": examples,
        "n_chunks": len(files),
    }


def encode_footprints(corners_deg: np.ndarray) -> dict:
    """Centre and int16 corner offsets of footprints given as (n, 4, 2) RA/Dec degrees.

    The centre is the point about which the four tangent-plane corner offsets sum to
    zero, so the fourth corner need not be stored: it is minus the sum of the other three.
    """
    ra = np.radians(corners_deg[:, :, 0])
    dec = np.radians(corners_deg[:, :, 1])
    v = np.stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)], axis=-1)
    c = v.sum(axis=1)
    c /= np.linalg.norm(c, axis=1, keepdims=True)
    for _ in range(4):  # fixed point: move the centre to the mean of the corner offsets
        a0 = np.arctan2(c[:, 1], c[:, 0])
        d0 = np.arcsin(np.clip(c[:, 2], -1, 1))
        e = np.stack([-np.sin(a0), np.cos(a0), np.zeros_like(a0)], axis=-1)
        nrt = np.stack(
            [-np.sin(d0) * np.cos(a0), -np.sin(d0) * np.sin(a0), np.cos(d0)], axis=-1
        )
        w = np.einsum("nkj,nj->nk", v, c)
        xi = np.einsum("nkj,nj->nk", v, e) / w
        eta = np.einsum("nkj,nj->nk", v, nrt) / w
        c = c + xi.mean(axis=1)[:, None] * e + eta.mean(axis=1)[:, None] * nrt
        c /= np.linalg.norm(c, axis=1, keepdims=True)
    ra_q = np.round(np.degrees(np.arctan2(c[:, 1], c[:, 0])) % 360.0 / DEG_UNIT)
    ra_q = np.where(ra_q >= round(360.0 / DEG_UNIT), 0, ra_q).astype(np.int64)
    dec_q = np.round(np.degrees(np.arcsin(np.clip(c[:, 2], -1, 1))) / DEG_UNIT).astype(np.int64)
    ra0 = np.radians(ra_q * DEG_UNIT)[:, None]
    dec0 = np.radians(dec_q * DEG_UNIT)[:, None]
    xi, eta, cosc = gnomonic(ra0, dec0, ra, dec)
    fx, fy = xi / TAN_UNIT, eta / TAN_UNIT
    qx, qy = np.round(fx).astype(np.int64), np.round(fy).astype(np.int64)
    qx[:, 3] = -qx[:, :3].sum(axis=1)
    qy[:, 3] = -qy[:, :3].sum(axis=1)
    err = np.hypot(qx - fx, qy - fy).max(axis=1)  # worst corner error, counts
    radius = np.degrees(np.arccos(np.clip(cosc.min(axis=1), -1, 1)))
    cross = []
    for k in range(4):
        i, j = (k + 1) % 4, (k + 2) % 4
        cross.append(
            (qx[:, i] - qx[:, k]) * (qy[:, j] - qy[:, i])
            - (qy[:, i] - qy[:, k]) * (qx[:, j] - qx[:, i])
        )
    cross = np.stack(cross, axis=1)
    convex = np.all(cross > 0, axis=1) | np.all(cross < 0, axis=1)
    fits16 = (np.abs(qx).max(axis=1) <= 32767) & (np.abs(qy).max(axis=1) <= 32767)
    return {
        "ra": ra_q,
        "dec": dec_q,
        "x": qx,
        "y": qy,
        "err_counts": err,
        "radius_deg": radius,
        "ok": convex & fits16 & (cosc.min(axis=1) > 0.5),
    }


def build_index(
    cache: Path = DEFAULT_CACHE, out: Path = DEFAULT_OUT, progress=print
) -> dict:
    """Write shards and ``manifest.json`` from whatever the cache holds. Returns the manifest."""
    cache, out = Path(cache), Path(out)
    cat = load_catalogue(cache, progress)
    n_all = len(cat["mjd"])
    if n_all == 0:
        raise RuntimeError(f"no catalogue rows under {cache}; run the dump first")
    enc = encode_footprints(cat["corners"])
    t_q = np.round((cat["mjd"] - MJD_EPOCH) / MJD_UNIT).astype(np.int64)
    ok = enc["ok"] & (t_q >= 0) & (t_q < 2**32)
    ok &= (cat["seq"] < 2**SEQ_BITS) & (cat["suffix"] < 2**SUFFIX_BITS)
    ok &= cat["prefix"] < 2**PREFIX_BITS
    n_bad = int((~ok).sum())
    if n_bad:
        progress(f"WARNING: {n_bad} images cannot be encoded and are left out")
    n_cells = grid_cells_per_band()
    band, cell = cell_of(enc["ra"] * DEG_UNIT, enc["dec"] * DEG_UNIT, n_cells)
    order = np.lexsort(
        (cat["det"], cat["suffix"], cat["seq"], cat["prefix"], t_q, cell, band)
    )
    order = order[ok[order]]
    rec = np.zeros(len(order), RECORD_DTYPE)
    rec["ra"] = enc["ra"][order]
    rec["dec"] = enc["dec"][order]
    for k in range(3):
        rec[f"x{k + 1}"] = enc["x"][order, k]
        rec[f"y{k + 1}"] = enc["y"][order, k]
    rec["t"] = t_q[order]
    rec["id"] = (
        (cat["det"][order] - 1)
        | (cat["suffix"][order] << SUFFIX_SHIFT)
        | (cat["seq"][order] << SEQ_SHIFT)
        | (cat["prefix"][order] << PREFIX_SHIFT)
    )
    band_s, cell_s = band[order], cell[order]

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("b[0-9][0-9]/c*.bin"):  # our own previous build
        old.unlink()
    shards = []
    sizes = []
    cell_id = band_s * 100000 + cell_s
    starts = np.flatnonzero(np.r_[True, cell_id[1:] != cell_id[:-1]])
    ends = np.r_[starts[1:], len(rec)]
    for s, e in zip(starts, ends, strict=True):
        b, c = int(band_s[s]), int(cell_s[s])
        (out / f"b{b:02d}").mkdir(exist_ok=True)
        for part, p0 in enumerate(range(s, e, PART_MAX_RECORDS)):
            p1 = min(e, p0 + PART_MAX_RECORDS)
            chunk = rec[p0:p1]
            (out / SHARD_TEMPLATE.format(band=b, cell=c, part=part)).write_bytes(chunk.tobytes())
            t0 = MJD_EPOCH + float(chunk["t"][0]) * MJD_UNIT
            t1 = MJD_EPOCH + float(chunk["t"][-1]) * MJD_UNIT
            shards.append([b, c, part, int(p1 - p0), round(t0, 6), round(t1, 6)])
            sizes.append((p1 - p0) * RECORD_DTYPE.itemsize)

    okc = cat["coll"][ok]
    okm = cat["mjd"][ok]
    state = _load_state(cache)
    summary = state.get("summary", {})
    rows = {}
    for i, name in enumerate(cat["collections"]):
        sel = okc == i
        rows[name] = {
            "indexed": int(sel.sum()),
            "mjd_min": round(float(okm[sel].min()), 6) if sel.any() else None,
            "mjd_max": round(float(okm[sel].max()), 6) if sel.any() else None,
            "archive_rows_at_dump": summary.get(name, {}).get("rows"),
        }
    days = sorted(int(d) for d in state.get("chunks", {}))
    sci = [v for v in summary.values() if v.get("mjd_min") is not None]
    want = (
        list(range(math.floor(min(v["mjd_min"] for v in sci)),
                   math.floor(max(v["mjd_max"] for v in sci)) + 1))
        if sci else []
    )
    missing = [d for d in want if not chunk_path(cache, d).exists()]
    radius = float(enc["radius_deg"][ok].max())
    manifest = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "NASA/IPAC IRSA TAP, tables spherex.plane + spherex.artifact",
        "doi": DOIS,
        "s3_root": S3_ROOT,
        "key_template": KEY_TEMPLATE,
        "shard_template": SHARD_TEMPLATE,
        "record": {
            "size": RECORD_DTYPE.itemsize,
            "byte_order": "little",
            "fields": [
                {"name": nm, "offset": int(RECORD_DTYPE.fields[nm][1]),
                 "dtype": RECORD_DTYPE.fields[nm][0].str.lstrip("<")}
                for nm in RECORD_DTYPE.names
            ],
            "id_bits": {
                "det_minus_1": [0, DET_BITS],
                "suffix": [SUFFIX_SHIFT, SUFFIX_BITS],
                "seq": [SEQ_SHIFT, SEQ_BITS],
                "prefix": [PREFIX_SHIFT, PREFIX_BITS],
            },
        },
        "units": {
            "deg_per_count": DEG_UNIT,
            "tan_rad_per_count": TAN_UNIT,
            "mjd_epoch": MJD_EPOCH,
            "days_per_count": MJD_UNIT,
        },
        "grid": {"band_height_deg": BAND_HEIGHT_DEG, "cells_per_band": n_cells},
        "search_radius_deg": math.ceil((radius + 0.02) * 100) / 100,
        "max_centre_to_corner_deg": round(radius, 4),
        "part_max_records": PART_MAX_RECORDS,
        "collections": cat["collections"],
        "prefixes": cat["prefixes"],
        "rows": {"total": len(rec), "by_collection": rows},
        "coverage": {
            "days_cached": len(days),
            "days_in_archive_span": len(want),
            "missing_days": missing,
            "complete": bool(want) and not missing,
        },
        "quality": {
            "left_out_unencodable": n_bad,
            "skipped_on_parse": cat["skipped"],
            "max_corner_error_arcsec": round(
                float(enc["err_counts"][ok].max()) * TAN_UNIT * ARCSEC_PER_RAD, 4
            ),
        },
        "shards": shards,
    }
    tmp = out / "manifest.tmp"
    tmp.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    tmp.replace(out / "manifest.json")
    sz = np.array(sizes)
    progress(
        f"wrote {len(rec)} records in {len(shards)} shard files, "
        f"{sz.sum() / 1e6:.2f} MB; shard size median {np.median(sz) / 1e3:.1f} kB, "
        f"max {sz.max() / 1e3:.1f} kB; manifest {(out / 'manifest.json').stat().st_size / 1e3:.0f} kB"
    )
    return manifest


# --------------------------------------------------------------------------------------
# 4. Reader
# --------------------------------------------------------------------------------------


class Hit(NamedTuple):
    """One image whose footprint contains the query point."""

    s3_key: str  # append to https://nasa-irsa-spherex.s3.amazonaws.com/
    mjd: float  # start of the exposure
    detector: int  # 1..6 (band SPHEREx-D1..D6)
    collection: str  # e.g. spherex_dr1, spherex_qr3_deep
    margin_arcsec: float = 0.0  # distance from the point to the nearest footprint edge

    @property
    def url(self) -> str:
        return S3_ROOT + self.s3_key


class SkyIndex:
    """Reader of a built index directory (the Python twin of the web client)."""

    def __init__(self, root: Path = DEFAULT_OUT) -> None:
        self.root = Path(root)
        self.manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        m = self.manifest
        if m["format"] != FORMAT_NAME or m["version"] != FORMAT_VERSION:
            raise ValueError(f"unsupported index {m['format']} v{m['version']}")
        self.n_cells = m["grid"]["cells_per_band"]
        self.band_height = m["grid"]["band_height_deg"]
        self.radius = m["search_radius_deg"]
        self._parts: dict[tuple[int, int], list[list]] = {}
        for s in m["shards"]:
            self._parts.setdefault((s[0], s[1]), []).append(s)

    def shards_for(
        self, ra: float, dec: float, mjd_min: float | None = None, mjd_max: float | None = None
    ) -> list[list]:
        """Manifest entries [band, cell, part, count, mjd_min, mjd_max] to read for a point."""
        out = []
        for bc in cells_for_point(ra, dec, self.radius, self.n_cells, self.band_height):
            for s in self._parts.get(bc, []):
                if mjd_min is not None and s[5] < mjd_min:
                    continue
                if mjd_max is not None and s[4] > mjd_max:
                    continue
                out.append(s)
        return out

    def read_shard(self, band: int, cell: int, part: int) -> np.ndarray:
        name = self.manifest["shard_template"].format(band=band, cell=cell, part=part)
        return np.fromfile(self.root / name, RECORD_DTYPE)

    def decode(self, rec: np.ndarray, margin: np.ndarray | None = None) -> list[Hit]:
        colls = self.manifest["collections"]
        prefixes = self.manifest["prefixes"]
        out = []
        for i in range(len(rec)):
            w = int(rec["id"][i])
            det = (w & (2**DET_BITS - 1)) + 1
            suffix = (w >> SUFFIX_SHIFT) & (2**SUFFIX_BITS - 1)
            seq = (w >> SEQ_SHIFT) & (2**SEQ_BITS - 1)
            ci, release, period, procver = prefixes[w >> PREFIX_SHIFT]
            out.append(
                Hit(
                    make_key(release, period, procver, det, seq, suffix),
                    MJD_EPOCH + int(rec["t"][i]) * MJD_UNIT,
                    det,
                    colls[ci],
                    float(margin[i]) if margin is not None else 0.0,
                )
            )
        return out

    def candidates(
        self, ra: float, dec: float, mjd_min: float | None = None, mjd_max: float | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        """All records of the shards selected for a point, and their footprint margins."""
        parts = [self.read_shard(s[0], s[1], s[2]) for s in self.shards_for(ra, dec, mjd_min, mjd_max)]
        rec = np.concatenate(parts) if parts else np.zeros(0, RECORD_DTYPE)
        return rec, footprint_margin(rec, ra, dec)

    def query(
        self,
        ra: float,
        dec: float,
        mjd_min: float | None = None,
        mjd_max: float | None = None,
        min_margin_arcsec: float = 0.0,
    ) -> list[Hit]:
        """Images whose footprint contains (ra, dec) in degrees ICRS, oldest first.

        ``min_margin_arcsec`` > 0 keeps only images where the point is at least that far
        inside the footprint (useful to make sure a cutout fits on the detector).
        """
        rec, margin = self.candidates(ra, dec, mjd_min, mjd_max)
        keep = margin >= min_margin_arcsec
        if mjd_min is not None:
            keep &= MJD_EPOCH + rec["t"] * MJD_UNIT >= mjd_min
        if mjd_max is not None:
            keep &= MJD_EPOCH + rec["t"] * MJD_UNIT <= mjd_max
        idx = np.flatnonzero(keep)
        idx = idx[np.argsort(rec["t"][idx], kind="stable")]
        return self.decode(rec[idx], margin[idx])
