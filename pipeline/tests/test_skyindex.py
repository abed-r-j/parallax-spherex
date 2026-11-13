"""Offline tests of the static sky index: a small synthetic catalogue, no network.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
import math
import struct

import numpy as np
import pytest

from parallax import skyindex as si

HALF = math.radians(3.485 / 2)  # half side of a detector footprint


def _vec(ra_deg, dec_deg):
    a, d = np.radians(ra_deg), np.radians(dec_deg)
    return np.stack([np.cos(d) * np.cos(a), np.cos(d) * np.sin(a), np.sin(d)], axis=-1)


def _square(ra0, dec0, pa_deg):
    """Corners (RA, Dec in degrees, RA in -180..180 like IRSA) of a square footprint."""
    a0, d0, pa = math.radians(ra0), math.radians(dec0), math.radians(pa_deg)
    c = _vec(ra0, dec0)
    e = np.array([-math.sin(a0), math.cos(a0), 0.0])
    n = np.array([-math.sin(d0) * math.cos(a0), -math.sin(d0) * math.sin(a0), math.cos(d0)])
    out = []
    for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1)):  # clockwise seen east-left, like IRSA
        x = math.tan(HALF) * (sx * math.cos(pa) - sy * math.sin(pa))
        y = math.tan(HALF) * (sx * math.sin(pa) + sy * math.cos(pa))
        v = c + x * e + y * n
        v /= np.linalg.norm(v)
        out.append((math.degrees(math.atan2(v[1], v[0])), math.degrees(math.asin(v[2]))))
    return out


def _wkb_hex(corners):
    ring = [*corners, corners[0]]
    raw = struct.pack("<BIII", 1, 0x20000003, 4326, 1) + struct.pack("<I", 5)
    raw += b"".join(struct.pack("<dd", ra, dec) for ra, dec in ring)
    return raw.hex().upper()


def _inside_sphere(corners, ra, dec):
    """Independent test: the point is on the centre's side of all four great-circle edges.

    ``corners`` is (n, 4, 2) degrees; returns (inside, distance to the nearest edge circle
    in radians), each of length n. No tangent plane is involved.
    """
    v = _vec(corners[:, :, 0], corners[:, :, 1])  # (n, 4, 3)
    normals = np.cross(v, np.roll(v, -1, axis=1))
    s = normals @ _vec(ra, dec)
    m = np.einsum("nkj,nj->nk", normals, v.sum(axis=1))
    return np.all(s * m > 0, axis=1), np.abs(s).min(axis=1) / np.linalg.norm(normals, axis=2).min()


def _catalogue():
    """(collection, release, period, procver, seq, suffix, det, mjd, corners) rows."""
    rng = np.random.default_rng(42)
    rows = []
    centres = [
        (10.0, 20.0), (0.4, 10.0), (359.2, 10.5), (180.0, -30.0), (179.5, 0.0),
        (123.0, 89.2), (300.0, 88.0), (50.0, -89.5), (270.0, 66.56), (269.0, 67.0),
        (271.5, 65.5), (90.0, -66.56), (45.0, 84.9), (45.0, 85.1), (200.0, -85.0),
    ]
    centres += [(float(rng.uniform(0, 360)), float(np.degrees(np.arcsin(rng.uniform(-1, 1)))))
                for _ in range(400)]
    for i, (ra, dec) in enumerate(centres):
        deep = i % 7 == 0
        qr3 = i % 3 == 0
        rows.append((
            ("spherex_qr3" if qr3 else "spherex_dr1") + ("_deep" if deep else ""),
            "qr3" if qr3 else "dr1",
            f"2025W{17 + i % 30:02d}_{1 + i % 4}{'ABC'[i % 3]}",
            "l2b_retry-v27-2026-197" if i % 11 == 0 else "l2b-v27-2026-196",
            1 + (i * 37) % 3000,
            1 + i % 4,
            1 + i % 6,
            60790.0 + i * 0.731 + (400.0 if qr3 else 0.0),
            _square(ra, dec, float(rng.uniform(0, 360))),
        ))
    return rows


def _uri(r):
    return "ibe/data/spherex/" + si.make_key(r[1], r[2], r[3], r[6], r[4], r[5])


def _write_cache(cache, rows):
    (cache / "chunks").mkdir(parents=True)
    by_day: dict[int, list[str]] = {}
    for r in rows:
        did = f"ivo://irsa.ipac/{r[0]}?{r[2]}_{r[4]:04d}_{r[5]}/D{r[6]}"
        line = f"{did},{r[7]:.6f},{_wkb_hex(r[8])},{_uri(r)}"
        by_day.setdefault(math.floor(r[7]), []).append(line)
    for day, lines in by_day.items():
        si.chunk_path(cache, day).write_text(
            "\n".join([si.CSV_HEADER, *lines]) + "\n", encoding="utf-8"
        )


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("skyindex")
    rows = _catalogue()
    _write_cache(root / "cache", rows)
    manifest = si.build_index(root / "cache", root / "out", progress=lambda *a: None)
    return rows, manifest, si.SkyIndex(root / "out"), root / "out"


def test_record_layout_is_28_bytes_little_endian():
    assert si.RECORD_DTYPE.itemsize == 28
    offs = {n: si.RECORD_DTYPE.fields[n][1] for n in si.RECORD_DTYPE.names}
    assert offs == {"ra": 0, "dec": 4, "x1": 8, "y1": 10, "x2": 12, "y2": 14,
                    "x3": 16, "y3": 18, "t": 20, "id": 24}
    assert si.DET_BITS + si.SUFFIX_BITS + si.SEQ_BITS + si.PREFIX_BITS == 32


def test_manifest_and_files_agree(built):
    rows, manifest, _, out = built
    assert manifest["rows"]["total"] == len(rows)
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8")) == manifest
    total = 0
    for b, c, part, count, t0, t1 in manifest["shards"]:
        f = out / manifest["shard_template"].format(band=b, cell=c, part=part)
        assert f.stat().st_size == count * 28
        rec = np.fromfile(f, si.RECORD_DTYPE)
        t = si.MJD_EPOCH + rec["t"] * si.MJD_UNIT
        assert np.all(np.diff(rec["t"].astype(np.int64)) >= 0)  # time-sorted
        assert t0 == pytest.approx(t.min(), abs=1e-6) and t1 == pytest.approx(t.max(), abs=1e-6)
        band, cell = si.cell_of(rec["ra"] * si.DEG_UNIT, rec["dec"] * si.DEG_UNIT,
                                manifest["grid"]["cells_per_band"])
        assert np.all(band == b) and np.all(cell == c)
        total += count
    assert total == len(rows)


def test_round_trip_every_image_is_found_at_its_centre(built):
    rows, _, idx, _ = built
    for r in rows:
        v = _vec(np.array([c[0] for c in r[8]]), np.array([c[1] for c in r[8]])).sum(axis=0)
        ra = math.degrees(math.atan2(v[1], v[0])) % 360.0
        dec = math.degrees(math.asin(v[2] / np.linalg.norm(v)))
        hits = {h.s3_key: h for h in idx.query(ra, dec)}
        key = _uri(r).split("ibe/data/spherex/")[1]
        assert key in hits, (ra, dec)
        h = hits[key]
        assert h.mjd == pytest.approx(r[7], abs=1e-6)
        assert h.detector == r[6] and h.collection == r[0]
        assert h.url == si.S3_ROOT + key
        assert h.margin_arcsec == pytest.approx(3.485 / 2 * 3600, rel=2e-3)


def test_query_matches_independent_spherical_test(built):
    rows, _, idx, _ = built
    rng = np.random.default_rng(7)
    points = [(0.05, 10.0), (359.97, 10.2), (180.0, -30.5), (-0.3 % 360, 9.0),
              (10.0, 89.9), (200.0, 89.5), (0.0, 90.0), (77.0, -89.9), (0.0, -90.0),
              (270.0, 66.56), (90.0, -66.56), (45.0, 85.0)]
    points += [(float(rng.uniform(0, 360)), float(np.degrees(np.arcsin(rng.uniform(-1, 1)))))
               for _ in range(300)]
    # also points around every footprint corner, where a wrong test would show first
    for r in rows[:60]:
        for ra, dec in r[8]:
            points.append(((ra + float(rng.normal(0, 0.05))) % 360.0,
                           float(np.clip(dec + rng.normal(0, 0.05), -90, 90))))
    n_inside = 0
    corners = np.array([r[8] for r in rows])
    keys = np.array([_uri(r).split("ibe/data/spherex/")[1] for r in rows])
    for ra, dec in points:
        got = {h.s3_key for h in idx.query(ra, dec)}
        inside, edge = _inside_sphere(corners, ra, dec)
        near = edge < 1e-5  # within 2 arcsec of an edge: either answer is fine
        close = set(keys[near])
        want = set(keys[inside & ~near])
        assert want - got == set(), (ra, dec)
        assert got - want - close == set(), (ra, dec)
        n_inside += len(want)
    assert n_inside > 100


def test_pole_and_ra_wrap_footprints(built):
    _, _, idx, _ = built
    # the footprint centred at (123, 89.2) contains the north pole itself
    assert any(h.s3_key for h in idx.query(0.0, 90.0))
    assert len(idx.query(250.0, 89.6)) >= 1
    assert len(idx.query(0.0, -90.0)) >= 1
    # footprints centred at RA 0.4 and 359.2 are both seen from either side of RA = 0
    for ra in (0.05, 359.95, 0.0, 360.0):
        assert len(idx.query(ra, 10.2)) == 2, ra
    # RA = 180, where IRSA's own polygons switch from +180 to -180
    assert len(idx.query(180.3, -30.0)) == 1 and len(idx.query(179.7, -30.0)) == 1


def test_shard_selection_never_loses_a_centre():
    n_cells = si.grid_cells_per_band()
    assert len(n_cells) == 36 and n_cells[0] == n_cells[-1] and min(n_cells) >= 1
    rng = np.random.default_rng(3)
    radius = 2.56
    for _ in range(4000):
        ra = float(rng.uniform(0, 360))
        dec = float(rng.choice([rng.uniform(-90, 90), rng.uniform(84, 90), rng.uniform(-90, -84)]))
        # a random centre within the radius of the query point
        d, th = math.radians(radius * math.sqrt(rng.uniform(0, 1)) * 0.999), rng.uniform(0, 6.2832)
        p = _vec(ra, dec)
        a0, d0 = math.radians(ra), math.radians(dec)
        e = np.array([-math.sin(a0), math.cos(a0), 0.0])
        n = np.array([-math.sin(d0) * math.cos(a0), -math.sin(d0) * math.sin(a0), math.cos(d0)])
        c = math.cos(d) * p + math.sin(d) * (math.cos(th) * e + math.sin(th) * n)
        cra, cdec = math.degrees(math.atan2(c[1], c[0])) % 360.0, math.degrees(math.asin(c[2]))
        band, cell = si.cell_of(cra, cdec, n_cells)
        assert (int(band), int(cell)) in si.cells_for_point(ra, dec, radius, n_cells)
    # away from the poles only a few cells are needed
    assert len(si.cells_for_point(100.0, 0.0, radius, n_cells)) <= 6
    assert len(set(si.cells_for_point(0.1, 30.0, radius, n_cells))) == len(
        si.cells_for_point(0.1, 30.0, radius, n_cells)
    )


def test_time_filter_and_margin(built):
    rows, _, idx, _ = built
    r = rows[8]  # centred on (270, 66.56)
    allhits = idx.query(270.0, 66.56)
    assert len(allhits) >= 2
    assert [h.mjd for h in allhits] == sorted(h.mjd for h in allhits)
    one = idx.query(270.0, 66.56, mjd_min=r[7] - 0.01, mjd_max=r[7] + 0.01)
    assert [h.s3_key for h in one] == [_uri(r).split("ibe/data/spherex/")[1]]
    assert len(idx.query(270.0, 66.56, min_margin_arcsec=1e6)) == 0


def test_fourth_corner_is_recovered(built):
    rows, manifest, _, _ = built
    corners = np.array([r[8] for r in rows])
    enc = si.encode_footprints(corners)
    assert enc["ok"].all()
    assert np.all(enc["x"].sum(axis=1) == 0) and np.all(enc["y"].sum(axis=1) == 0)
    assert enc["err_counts"].max() < 2.2  # counts of 0.33 arcsec
    assert manifest["quality"]["max_corner_error_arcsec"] < 0.75
    assert 2.4 < manifest["max_centre_to_corner_deg"] < manifest["search_radius_deg"] < 2.7


def test_build_is_incremental_friendly(built, tmp_path):
    """Adding a later day to the cache and building again keeps every old image."""
    rows, _, _, _ = built
    _write_cache(tmp_path / "cache", rows[:100])
    m1 = si.build_index(tmp_path / "cache", tmp_path / "out", progress=lambda *a: None)
    extra = list(rows[100])
    extra[7] = 62000.25
    did = f"ivo://irsa.ipac/{extra[0]}?{extra[2]}_{extra[4]:04d}_{extra[5]}/D{extra[6]}"
    si.chunk_path(tmp_path / "cache", 62000).write_text(
        f"{si.CSV_HEADER}\n{did},{extra[7]:.6f},{_wkb_hex(extra[8])},{_uri(tuple(extra))}\n",
        encoding="utf-8",
    )
    m2 = si.build_index(tmp_path / "cache", tmp_path / "out", progress=lambda *a: None)
    assert m2["rows"]["total"] == m1["rows"]["total"] + 1
    n_files = len(list((tmp_path / "out").glob("b*/c*.bin")))
    assert n_files == len(m2["shards"])
