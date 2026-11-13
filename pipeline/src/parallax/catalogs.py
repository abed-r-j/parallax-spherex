"""Catalogue overlays for a field: Gaia DR3 stars and CatWISE2020 infrared sources.

Both functions return plain lists of dicts in the shapes of ``docs/DATA_CONTRACT.md`` plus
a warning string (empty on success). They never raise: if a service is down the list is
empty and the warning says why, so the pipeline can still publish the field.

* Gaia DR3 (``gaia[]``): ``{id, ra, dec, pmRa, pmDec, plx, g}``, position at epoch 2016.0,
  proper motions in mas/yr (pmRa includes cos(dec)), parallax in mas. ``id`` is a string
  because Gaia source ids do not fit in a JavaScript number.
  Primary service: ESA Gaia archive TAP, table ``gaiadr3.gaia_source``. That service
  limits all anonymous users together to 50 queued jobs and answers HTTP 429 when the
  queue is full, so the IRSA copy of the same table (``gaia_dr3_source``) is the fallback.
* CatWISE2020 (``wise[]``): ``{id, ra, dec, w1, w2, pmRa, pmDec}`` from IRSA table
  ``catwise_2020``. Position is the motion-fit position ``ra_pm``/``dec_pm`` (epoch
  MJD 57170 = 2015.4), magnitudes are ``w1mpro``/``w2mpro`` (Vega), proper motions are
  converted from the catalogue's arcsec/yr to mas/yr to match Gaia. CatWISE motions are
  noisy and wrong for blended or saturated stars; use Gaia where both exist.

Every HTTP response is cached on disk (``data/cache/<service>/``), keyed by the request.

Credits: ESA Gaia mission and DPAC (Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1);
CatWISE2020 (Marocco et al. 2021, ApJS 253, 8; doi:10.26131/IRSA551), served by the
NASA/IPAC Infrared Science Archive.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from math import cos, hypot, radians
from pathlib import Path
from typing import Any

import httpx

USER_AGENT = "ParallaX-SpaceApps2026/1.0"
GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
IRSA_TAP = "https://irsa.ipac.caltech.edu/TAP/sync"
CATWISE_EPOCH_MJD = 57170.0
GAIA_EPOCH = 2016.0
PIXEL_ARCSEC = 6.15


def default_cache_dir() -> Path:
    """``$PARALLAX_CACHE`` if set, else ``<repo>/data/cache``."""
    env = os.environ.get("PARALLAX_CACHE")
    return Path(env) if env else Path(__file__).resolve().parents[3] / "data" / "cache"


class RejectedResponse(RuntimeError):
    """A service answered, but not with the expected kind of body (kept in ``text``)."""

    def __init__(self, service: str, text: str):
        super().__init__(f"{service}: unexpected response: {text[:200]!r}")
        self.text = text


def _request(method: str, url: str, params: dict[str, str], timeout: float) -> str:
    """The only function that touches the network (tests replace it)."""
    kw: dict[str, Any] = {"data": params} if method == "POST" else {"params": params}
    r = httpx.request(method, url, headers={"User-Agent": USER_AGENT}, timeout=timeout,
                      follow_redirects=True, **kw)
    r.raise_for_status()
    return r.text


def fetch_text(service: str, url: str, params: dict[str, str], *, method: str = "GET",
               cache_dir: Path | None = None, timeout: float = 180.0,
               accept=None) -> str:
    """GET/POST ``url`` and return the body, reading and writing the on-disk cache.

    ``accept(text)`` may reject a body (return False) so that error pages are not cached;
    a rejected body raises :class:`RejectedResponse`.
    """
    root = (cache_dir or default_cache_dir()) / service
    key = hashlib.sha1(json.dumps([method, url, params], sort_keys=True).encode()).hexdigest()
    fn = root / f"{key[:20]}.txt"
    if fn.exists():
        return fn.read_text(encoding="utf-8")
    text = _request(method, url, params, timeout)
    if accept is not None and not accept(text):
        raise RejectedResponse(service, text)
    root.mkdir(parents=True, exist_ok=True)
    tmp = fn.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(fn)
    return text


def _csv_rows(text: str, first_column: str) -> list[dict[str, str]]:
    if not text.lstrip().lower().startswith(first_column):
        raise RuntimeError(f"not a CSV table: {text[:160]!r}")
    return list(csv.DictReader(io.StringIO(text.lstrip())))


def _num(s: str | None, digits: int) -> float | None:
    """Float rounded to ``digits``, or None for empty / null / NaN cells."""
    try:
        v = float(s)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return round(v, digits) if v == v else None


def _is_csv(first_column: str):
    return lambda text: text.lstrip().lower().startswith(first_column)


def _gaia_adql(table: str, ra: float, dec: float, radius: float, gmax: float, top: int) -> str:
    return (
        f"SELECT TOP {int(top)} source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag "
        f"FROM {table} "
        f"WHERE CONTAINS(POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {ra:.6f}, {dec:.6f}, {radius:.5f})) = 1 "
        f"AND phot_g_mean_mag < {gmax:.2f} ORDER BY phot_g_mean_mag"
    )


def _gaia_rows(text: str) -> list[dict]:
    out = []
    for r in _csv_rows(text, "source_id"):
        out.append({
            "id": r["source_id"].strip(), "ra": _num(r["ra"], 7), "dec": _num(r["dec"], 7),
            "pmRa": _num(r["pmra"], 3), "pmDec": _num(r["pmdec"], 3),
            "plx": _num(r["parallax"], 3), "g": _num(r["phot_g_mean_mag"], 3),
        })
    return out


def gaia_cone(ra: float, dec: float, radius_deg: float, gmax: float = 19.0, top: int = 400,
              cache_dir: Path | None = None) -> tuple[list[dict], str]:
    """The ``top`` brightest Gaia DR3 sources with G < ``gmax`` within ``radius_deg``.

    Returns (rows, warning). Tries the ESA archive, then the IRSA copy of the table.
    """
    errors = []
    attempts = [
        ("gaia_esa", GAIA_TAP, "gaiadr3.gaia_source", "POST",
         lambda q: {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": q}),
        ("gaia_irsa", IRSA_TAP, "gaia_dr3_source", "GET",
         lambda q: {"QUERY": q, "FORMAT": "CSV"}),
    ]
    for service, url, table, method, make in attempts:
        q = _gaia_adql(table, ra, dec, radius_deg, gmax, top)
        try:
            text = fetch_text(service, url, make(q), method=method, cache_dir=cache_dir,
                              accept=_is_csv("source_id"))
            rows = _gaia_rows(text)
        except Exception as e:  # service trouble must never stop the pipeline
            errors.append(f"{service}: {type(e).__name__}: {str(e)[:120]}")
            continue
        warn = f"Gaia: used fallback after {errors[0]}" if errors else ""
        return rows, warn
    return [], "Gaia DR3 unavailable (" + "; ".join(errors) + ")"


def catwise_cone(ra: float, dec: float, radius_deg: float, w1max: float = 17.5,
                 top: int = 400, cache_dir: Path | None = None) -> tuple[list[dict], str]:
    """The ``top`` brightest CatWISE2020 sources with W1 < ``w1max`` within ``radius_deg``."""
    q = (
        f"SELECT TOP {int(top)} source_name, ra_pm, dec_pm, w1mpro, w2mpro, pmra, pmdec "
        "FROM catwise_2020 "
        f"WHERE CONTAINS(POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {ra:.6f}, {dec:.6f}, {radius_deg:.5f})) = 1 "
        f"AND w1mpro < {w1max:.2f} ORDER BY w1mpro"
    )
    try:
        text = fetch_text("catwise", IRSA_TAP, {"QUERY": q, "FORMAT": "CSV"},
                          cache_dir=cache_dir, accept=_is_csv("source_name"))
        rows = _csv_rows(text, "source_name")
    except Exception as e:
        return [], f"CatWISE2020 unavailable ({type(e).__name__}: {str(e)[:120]})"
    out = []
    for r in rows:
        pmra, pmdec = _num(r["pmra"], 6), _num(r["pmdec"], 6)
        out.append({
            "id": r["source_name"].strip(), "ra": _num(r["ra_pm"], 7),
            "dec": _num(r["dec_pm"], 7), "w1": _num(r["w1mpro"], 3),
            "w2": _num(r["w2mpro"], 3),
            "pmRa": None if pmra is None else round(pmra * 1000.0, 1),
            "pmDec": None if pmdec is None else round(pmdec * 1000.0, 1),
        })
    return out, ""


def field_radius_deg(n: int, scale: float = PIXEL_ARCSEC, margin_pix: float = 2.0) -> float:
    """Radius of the circle that contains an n x n pixel field plus a margin."""
    return (n / 2.0 + margin_pix) * scale * 2**0.5 / 3600.0


def in_field(row: dict, ra0: float, dec0: float, n: int, scale: float = PIXEL_ARCSEC,
             margin_pix: float = 2.0) -> bool:
    """True if a catalogue row falls inside the square field (small-angle test)."""
    half = (n / 2.0 + margin_pix) * scale / 3600.0
    dx = ((row["ra"] - ra0 + 180.0) % 360.0 - 180.0) * cos(radians(dec0))
    dy = row["dec"] - dec0
    return abs(dx) <= half and abs(dy) <= half


def overlays_for_field(ra0: float, dec0: float, n: int, scale: float = PIXEL_ARCSEC,
                       cache_dir: Path | None = None) -> dict:
    """``{"gaia": [...], "wise": [...], "warnings": [...]}`` for one field.

    The margin (two pixels, plus 25 arcsec for Gaia so that fast stars that have moved
    into the field since 2016.0 are kept) is wider than the field on purpose.
    """
    r = field_radius_deg(n, scale)
    gaia, w1 = gaia_cone(ra0, dec0, r + 25.0 / 3600.0, cache_dir=cache_dir)
    wise, w2 = catwise_cone(ra0, dec0, r, cache_dir=cache_dir)
    gaia = [g for g in gaia if in_field(g, ra0, dec0, n, scale, margin_pix=2.0 + 25.0 / scale)]
    wise = [w for w in wise if in_field(w, ra0, dec0, n, scale)]
    return {"gaia": gaia, "wise": wise, "warnings": [w for w in (w1, w2) if w]}


def nearest(rows: list[dict], ra: float, dec: float) -> tuple[dict | None, float]:
    """Closest row to (ra, dec) and its distance in arcsec (small-angle)."""
    best, dmin = None, float("inf")
    for r in rows:
        d = 3600.0 * hypot(((r["ra"] - ra + 180.0) % 360.0 - 180.0) * cos(radians(dec)),
                           r["dec"] - dec)
        if d < dmin:
            best, dmin = r, d
    return best, dmin
