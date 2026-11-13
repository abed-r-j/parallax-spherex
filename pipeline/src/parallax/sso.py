"""Known solar-system objects inside a field, frame by frame (the ``sso`` block).

Two services, used for what each does best:

* IMCCE **SkyBoT** cone search answers "which catalogued asteroids, comets and planets
  are near this sky position at this time?". It only knows ground observatories, so we
  ask for geocentric positions. One query per exposure would be far too many (a field has
  hundreds of frames), so exposures are grouped in time (default: up to 8 hours per
  group) and each group is one cone query with a radius that covers the field, the
  motion of an object during the group and the Earth-to-spacecraft parallax.
* JPL **Horizons** knows the SPHEREx spacecraft (body -163182), so every object SkyBoT
  puts in or near the field is re-computed at the exact time of each frame as seen from
  SPHEREx (observer ``500@-163182``). SPHEREx is in low Earth orbit, about 7000 km from
  the geocentre, so a geocentric position can be off by up to 9.65 arcsec / (distance in
  au): up to about 5 arcsec for a main-belt asteroid and far more for a near-Earth
  object. In practice SPHEREx looks away from the Earth, which keeps the offset well below
  that bound: we measured 0.2-0.5 arcsec for (52) Europa at 2.75 au (tests/test_sso.py).

Rates in the output are the *geocentric* sky rates from SkyBoT (arcsec/h, RA rate
includes cos(dec)). The instantaneous rate seen from SPHEREx wobbles by tens of arcsec/h
with the 98-minute orbit and would be misleading for linking detections hours apart.

Limitations: an object faster than ``rate_allow`` (default 120 arcsec/h) can leave the
search cone inside one time group and be missed; objects fainter than ``vmag_max`` are
dropped on purpose; if Horizons fails for an object its SkyBoT position is kept and the
``source`` field says so.

Citations:
  SkyBoT: Berthier J., Vachier F., Thuillot W., Fernique P., Ochsenbein F., Genova F.,
  Lainey V., Arlot J.-E. 2006, "SkyBoT, a new VO service to identify Solar System
  objects", ASP Conf. Ser. 351, 367 (IMCCE, Observatoire de Paris, CNRS).
  Horizons: Giorgini J.D., Yeomans D.K., Chamberlin A.B., et al. 1996, "JPL's On-Line
  Solar System Data Service", BAAS 28(3), 1158; JPL Horizons On-Line Ephemeris System,
  https://ssd.jpl.nasa.gov/horizons/ (Solar System Dynamics Group, Jet Propulsion
  Laboratory).

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .catalogs import WARNINGS, RejectedResponse, fetch_text
from .frames import grid_wcs

SKYBOT_RETRY_S = 2.0

SKYBOT_URL = "https://ssp.imcce.fr/webservices/skybot/api/conesearch.php"
HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
SPHEREX_CENTER = "500@-163182"
MJD_TO_JD = 2400000.5
LEO_PARALLAX_ARCSEC_AU = 9.65  # 7000 km seen from 1 au
SOURCE_HORIZONS = "JPL Horizons @SPHEREx (rates: SkyBoT, geocentric)"
SOURCE_SKYBOT = "IMCCE SkyBoT, geocentric (not refined)"
MAJOR_BODIES = {
    "mercury": "199", "venus": "299", "mars": "499", "jupiter": "599", "saturn": "699",
    "uranus": "799", "neptune": "899", "pluto": "999", "moon": "301",
}


class HorizonsError(RuntimeError):
    """Horizons answered without an ephemeris table (bad name, ambiguous name, ...)."""


@dataclass
class Ephemeris:
    """Apparent positions of one body. Angles in degrees (ICRF), rates in arcsec/h."""

    name: str
    jd: np.ndarray
    ra: np.ndarray
    dec: np.ndarray
    rate_ra: np.ndarray  # d(RA)/dt * cos(dec)
    rate_dec: np.ndarray
    vmag: np.ndarray  # apparent V (asteroids) or total magnitude (comets); nan if unknown
    r: np.ndarray  # heliocentric distance, au
    delta: np.ndarray  # observer distance, au
    elong: np.ndarray  # Sun-observer-target angle, deg

    def __len__(self) -> int:
        return len(self.jd)

    @property
    def mjd(self) -> np.ndarray:
        return self.jd - MJD_TO_JD

    def at(self, mjd) -> tuple[np.ndarray, np.ndarray]:
        """Linearly interpolated (ra, dec) at ``mjd`` (RA unwrapped across 0/360)."""
        ra = np.degrees(np.unwrap(np.radians(self.ra)))
        t = np.asarray(mjd, float)
        return np.interp(t, self.mjd, ra) % 360.0, np.interp(t, self.mjd, self.dec)


def horizons_command(name: str | int) -> str:
    """Translate a human object name into a Horizons COMMAND string.

    ``4`` or ``"4 Vesta"`` -> ``4;`` (numbered small body), ``"2008 SY56"`` ->
    ``DES=2008 SY56;``, ``"C/2025 N1"`` -> ``DES=C/2025 N1;CAP;NOFRAG`` (latest comet
    apparition), ``"Pluto"`` -> ``999``. Anything else is passed as a small-body name
    search (``Ceres;``). A string that already contains ``;`` or ``=`` is passed as is.
    """
    s = str(name).strip()
    if ";" in s or "=" in s:
        return s
    if s.lower() in MAJOR_BODIES:
        return MAJOR_BODIES[s.lower()]
    m = re.match(r"^(\d+)(\s+[A-Za-z].*)?$", s)
    if m and not re.match(r"^\d{4}\s+[A-Z]{1,2}\d*$", s):
        return f"{m.group(1)};"
    if re.match(r"^\d{4}\s+[A-Z]{1,2}\d*$", s):
        return f"DES={s};"
    if re.match(r"^\d+[PI]", s):  # numbered comet or interstellar object, e.g. 3I/ATLAS
        return f"DES={s.split('/')[0]};CAP;NOFRAG"
    if re.match(r"^[CPI]/", s):
        return f"DES={s};CAP;NOFRAG"
    return f"{s};"


def _horizons_params(command: str, center: str, time_args: dict[str, str]) -> dict[str, str]:
    return {
        "format": "text", "COMMAND": f"'{command}'", "OBJ_DATA": "NO", "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "OBSERVER", "CENTER": f"'{center}'", "QUANTITIES": "'1,3,9,19,20,23'",
        "ANG_FORMAT": "DEG", "CSV_FORMAT": "YES", "CAL_FORMAT": "JD", "EXTRA_PREC": "YES",
        **time_args,
    }


def _flt(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return float("nan")


def parse_horizons(text: str) -> Ephemeris:
    """Parse the CSV observer table of a Horizons text response."""
    if "$$SOE" not in text or "$$EOE" not in text:
        tail = " ".join(text.strip().splitlines()[-12:])[:400]
        raise HorizonsError(f"no ephemeris in Horizons response: {tail}")
    head, body = text.split("$$SOE", 1)
    cols = [c.strip() for c in head.rstrip().splitlines()[-2].split(",")]
    rows = [[c.strip() for c in ln.split(",")]
            for ln in body.split("$$EOE", 1)[0].strip().splitlines() if ln.strip()]

    def col(*names: str) -> np.ndarray:
        for nm in names:
            if nm in cols:
                i = cols.index(nm)
                return np.array([_flt(r[i]) for r in rows])
        return np.full(len(rows), np.nan)

    m = re.search(r"Target body name:\s*(.+?)\s*(\{|$)", text, re.M)
    return Ephemeris(
        name=m.group(1).strip() if m else "", jd=col("Date_________JDUT"),
        ra=col("R.A.___(ICRF)"), dec=col("DEC____(ICRF)"), rate_ra=col("dRA*cosD"),
        rate_dec=col("d(DEC)/dt"), vmag=col("APmag", "T-mag"), r=col("r"),
        delta=col("delta"), elong=col("S-O-T"),
    )


def _concat(parts: list[Ephemeris]) -> Ephemeris:
    f = lambda k: np.concatenate([getattr(p, k) for p in parts])  # noqa: E731
    return Ephemeris(parts[0].name, f("jd"), f("ra"), f("dec"), f("rate_ra"), f("rate_dec"),
                     f("vmag"), f("r"), f("delta"), f("elong"))


def horizons_range(name: str | int, mjd_start: float, mjd_stop: float, step: str = "1 h",
                   center: str = SPHEREX_CENTER, cache_dir: Path | None = None) -> Ephemeris:
    """Ephemeris on a regular grid between two MJDs (UT). ``step`` like ``1 h`` or ``1 d``."""
    args = {"START_TIME": f"'JD{mjd_start + MJD_TO_JD:.5f}'",
            "STOP_TIME": f"'JD{mjd_stop + MJD_TO_JD:.5f}'", "STEP_SIZE": f"'{step}'"}
    text = fetch_text("horizons", HORIZONS_URL,
                      _horizons_params(horizons_command(name), center, args),
                      cache_dir=cache_dir, accept=lambda t: "API VERSION" in t)
    return parse_horizons(text)


def horizons_at(name: str | int, mjd, center: str = SPHEREX_CENTER,
                cache_dir: Path | None = None, chunk: int = 40) -> Ephemeris:
    """Ephemeris at exact times ``mjd`` (UT), in the order given. One request per 40 times."""
    jd = np.atleast_1d(np.asarray(mjd, float)) + MJD_TO_JD
    parts = []
    for i in range(0, len(jd), chunk):
        tlist = " ".join(f"{t:.7f}" for t in jd[i:i + chunk])
        text = fetch_text("horizons", HORIZONS_URL,
                          _horizons_params(horizons_command(name), center,
                                           {"TLIST": f"'{tlist}'"}),
                          cache_dir=cache_dir, accept=lambda t: "API VERSION" in t)
        parts.append(parse_horizons(text))
    eph = _concat(parts)
    if len(eph) != len(jd):
        raise HorizonsError(f"asked for {len(jd)} times, Horizons returned {len(eph)}")
    return eph


def _sexa_deg(s: str, hours: bool) -> float:
    sign = -1.0 if s.strip().startswith("-") else 1.0
    a, b, c = (abs(float(x)) for x in s.split())
    return sign * (a + b / 60.0 + c / 3600.0) * (15.0 if hours else 1.0)


def parse_skybot(text: str) -> list[dict]:
    """SkyBoT JSON (``-output=all``) -> list of dicts with degrees and arcsec/h."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for o in data:
        if not isinstance(o, dict) or "RA (hms)" not in o:
            continue
        num = o.get("Num")
        out.append({
            "name": str(o.get("Name", "")).strip(),
            "number": int(num) if str(num or "").strip().isdigit() else None,
            "ra": _sexa_deg(o["RA (hms)"], True), "dec": _sexa_deg(o["DEC (dms)"], False),
            "cls": o.get("Class", ""), "vmag": _flt(str(o.get("VMag (mag)", "nan"))),
            "rate_ra": _flt(str(o.get("dRA (arcsec/h)", "nan"))),
            "rate_dec": _flt(str(o.get("dDEC (arcsec/h)", "nan"))),
            "dg": _flt(str(o.get("dg (ua)", "nan"))),
        })
    return out


def skybot_cone(mjd: float, ra: float, dec: float, radius_deg: float,
                cache_dir: Path | None = None) -> list[dict]:
    """Asteroids, planets and comets within ``radius_deg`` of (ra, dec), geocentric.

    SkyBoT answers HTTP 204 with an empty body when the cone is empty, and now and then
    also when it is not (seen once in 15 queries), so an empty answer is asked again once
    and is never cached.
    """
    params = {
        "-ep": f"{mjd + MJD_TO_JD:.5f}", "-ra": f"{ra:.5f}", "-dec": f"{dec:.5f}",
        "-rd": f"{radius_deg:.4f}", "-mime": "json", "-output": "all", "-loc": "500",
        "-filter": "120", "-objFilter": "111", "-refsys": "EQJ2000",
        "-from": "ParallaX-SpaceApps2026",
    }
    ok = lambda t: t.lstrip().startswith(("[", "{")) or "No solar system object" in t  # noqa: E731
    for attempt in range(2):
        try:
            return parse_skybot(
                fetch_text("skybot", SKYBOT_URL, params, cache_dir=cache_dir, accept=ok))
        except RejectedResponse as e:
            if e.text.strip():
                raise
            if attempt == 0:
                time.sleep(SKYBOT_RETRY_S)
    return []


def group_times(mjd: np.ndarray, max_span_h: float = 8.0) -> list[list[int]]:
    """Split frame indices into runs whose first-to-last time span is <= ``max_span_h``."""
    groups: list[list[int]] = []
    for i in np.argsort(mjd, kind="stable"):
        if groups and (mjd[i] - mjd[groups[-1][0]]) * 24.0 <= max_span_h:
            groups[-1].append(int(i))
        else:
            groups.append([int(i)])
    return groups


def _offset(ra: float, dec: float, dra_arcsec: float, ddec_arcsec: float) -> tuple[float, float]:
    d = dec + ddec_arcsec / 3600.0
    return ra + dra_arcsec / 3600.0 / np.cos(np.radians(dec)), d


def _horizons_name(obj: dict) -> str | None:
    """Horizons lookup string for a SkyBoT object, or None if we do not know one."""
    if obj["cls"].lower().startswith("planet"):
        return obj["name"] if obj["name"].lower() in MAJOR_BODIES else None
    if obj["number"] is not None and not obj["cls"].lower().startswith("comet"):
        return str(obj["number"])
    return obj["name"] or None


def _candidates(field, cache_dir, max_span_h, rate_allow, vmag_max, warnings) -> dict[str, dict]:
    """SkyBoT pass: objects whose geocentric track comes near the field, per frame."""
    wcs = grid_wcs(field.ra0, field.dec0, field.n, field.scale)
    half_diag = field.n * field.scale * 2**0.5 / 2.0
    cands: dict[str, dict] = {}
    for grp in group_times(np.asarray(field.mjd), max_span_h):
        t = np.asarray(field.mjd)[grp]
        mid = 0.5 * (t.min() + t.max())
        span_h = (t.max() - t.min()) * 24.0
        radius = (half_diag + rate_allow * span_h / 2.0 + 60.0) / 3600.0
        try:
            objs = skybot_cone(float(mid), field.ra0, field.dec0, radius, cache_dir)
        except Exception as e:
            warnings.append(f"SkyBoT failed at MJD {mid:.3f}: {type(e).__name__}: {str(e)[:80]}")
            continue
        for o in objs:
            if o["vmag"] > vmag_max:
                continue
            pad = 2.0 + LEO_PARALLAX_ARCSEC_AU / max(o["dg"], 0.01) / field.scale
            for i, ti in zip(grp, t, strict=True):
                dt = (ti - mid) * 24.0
                ra, dec = _offset(o["ra"], o["dec"], o["rate_ra"] * dt, o["rate_dec"] * dt)
                x, y = (float(v) for v in wcs.all_world2pix(ra, dec, 0))
                if -pad - 0.5 <= x <= field.n - 0.5 + pad and -pad - 0.5 <= y <= field.n - 0.5 + pad:
                    c = cands.setdefault(o["name"], {"obj": o, "frames": {}})
                    c["frames"][i] = (ra, dec, o["vmag"], o["rate_ra"], o["rate_dec"])
    return cands


def _row(frame, obj, ra, dec, x, y, vmag, rate_ra, rate_dec, source) -> dict:
    v = None if not np.isfinite(vmag) else round(float(vmag), 2)
    return {
        "frame": int(frame), "name": obj["name"], "number": obj["number"],
        "ra": round(float(ra), 6), "dec": round(float(dec), 6),
        "x": round(float(x), 2), "y": round(float(y), 2), "vmag": v,
        "rateRa": round(float(rate_ra), 2), "rateDec": round(float(rate_dec), 2),
        "source": source,
    }


def known_objects(field, cache_dir: Path | None = None, **kwargs) -> list[dict]:
    """List-only form of :func:`sso_for_field` used by ``parallax.publish``.

    Warnings go to ``parallax.catalogs.WARNINGS`` and to the ``parallax.sso`` logger.
    """
    rows, warnings = sso_for_field(field, cache_dir, **kwargs)
    for w in warnings:
        WARNINGS.append(w)
        logging.getLogger("parallax.sso").warning(w)
    return rows


def sso_for_field(field, cache_dir: Path | None = None, *, refine: bool = True,
                  max_span_h: float = 8.0, rate_allow: float = 120.0,
                  vmag_max: float = 20.5) -> tuple[list[dict], list[str]]:
    """The ``sso`` block of the data contract for a :class:`parallax.frames.Field`.

    ``field`` only needs ``ra0, dec0, n, scale, mjd`` (frame order = contract order).
    Returns (rows, warnings); never raises for service failures.
    """
    warnings: list[str] = []
    wcs = grid_wcs(field.ra0, field.dec0, field.n, field.scale)
    rows: list[dict] = []
    cands = _candidates(field, cache_dir, max_span_h, rate_allow, vmag_max, warnings)
    for name, c in sorted(cands.items()):
        obj, frames = c["obj"], sorted(c["frames"])
        geo = [c["frames"][i] for i in frames]
        pos = [(g[0], g[1], g[2]) for g in geo]
        source = SOURCE_SKYBOT
        hname = _horizons_name(obj) if refine else None
        if hname is not None:
            try:
                eph = horizons_at(hname, np.asarray(field.mjd)[frames], cache_dir=cache_dir)
                pos = list(zip(eph.ra, eph.dec, eph.vmag, strict=True))
                source = SOURCE_HORIZONS
            except Exception as e:
                warnings.append(f"Horizons failed for {name}: {type(e).__name__}: {str(e)[:80]}")
        for i, (ra, dec, vmag), g in zip(frames, pos, geo, strict=True):
            x, y = (float(v) for v in wcs.all_world2pix(ra, dec, 0))
            if -0.5 <= x <= field.n - 0.5 and -0.5 <= y <= field.n - 0.5:
                vm = vmag if np.isfinite(vmag) else g[2]
                rows.append(_row(i, obj, ra, dec, x, y, vm, g[3], g[4], source))
    rows.sort(key=lambda r: (r["frame"], r["name"]))
    return rows, warnings
