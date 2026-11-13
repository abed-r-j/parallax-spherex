"""Offline tests for parallax.movers (object-first image search).

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from parallax import catalogs, movers, sso
from parallax.irsa import ImageRef

FX = Path(__file__).parent / "fixtures"
STUB = json.loads((FX / "europa_stub.json").read_text(encoding="utf-8"))
# A real spherex.plane footprint (detector D2, 2025-09-01), as IRSA TAP returns it.
POLY = ("0103000020E6100000010000000500000074E4521FC2EF55C0C8006E86FC4952C0E0F006FB9EF952C0"
        "D3D1A93A533952C09CBAA71DD85152C00D49AD17DB1353C0687F6F67530B56C0B8E34E08D22853C0"
        "74E4521FC2EF55C0C8006E86FC4952C0")


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def test_parse_ewkb_polygon():
    p = movers.parse_ewkb_polygon(POLY)
    assert p.shape == (5, 2)
    assert np.allclose(p[0], p[-1])  # closed ring
    assert np.allclose(p[0], [-87.7462, -73.1561], atol=1e-4)
    assert np.all(np.abs(p[:, 1]) < 90)
    with pytest.raises(ValueError, match="not a WKB polygon"):
        movers.parse_ewkb_polygon("0101000020E610000000909602C35154C010A77F2256B552C0")


def test_footprint_margin_real_footprint():
    p = movers.parse_ewkb_polygon(POLY)
    # the image centre published in the same table row ("pt") is well inside ...
    centre = movers.footprint_margin(-81.277527, -74.833382, p)
    assert 5500 < centre < 6500  # about half of the 3.5-degree detector, in arcsec
    # ... a point 3 degrees further south is outside
    assert movers.footprint_margin(-81.277527, -77.9, p) < 0


def test_footprint_margin_square_any_winding():
    sq = np.array([[10.0, -1.0], [12.0, -1.0], [12.0, 1.0], [10.0, 1.0], [10.0, -1.0]])
    for poly in (sq, sq[::-1]):
        assert movers.footprint_margin(11.0, 0.0, poly) == pytest.approx(3600.0, rel=1e-3)
        assert movers.footprint_margin(10.1, 0.0, poly) == pytest.approx(360.0, rel=1e-3)
        assert movers.footprint_margin(9.9, 0.0, poly) == pytest.approx(-360.0, rel=1e-2)


def make_eph(n=240, rate_deg_h=0.01) -> sso.Ephemeris:
    t = np.arange(n) / 24.0
    z = np.zeros(n)
    elong = np.where((t > 2) & (t < 8), 90.0, 60.0)
    return sso.Ephemeris("test", t + 2400000.5 + 60000, (359.0 + rate_deg_h * np.arange(n)) % 360,
                         z + 5.0, z, z, z + 12, z + 3, z + 2.5, elong)


def test_track_chunks_respects_elongation_box_and_wrap():
    chunks = movers.track_chunks(make_eph(), max_box_deg=0.6)
    assert len(chunks) == 3  # 6 observable days x 0.24 deg/day = 1.43 deg -> 3 boxes
    assert chunks[0]["mjd0"] == pytest.approx(60002 + 1 / 24)
    assert chunks[-1]["mjd1"] == pytest.approx(60008 - 1 / 24)
    for a, b in zip(chunks[:-1], chunks[1:], strict=True):
        assert b["mjd0"] - a["mjd1"] == pytest.approx(1 / 24)  # no gap in time
        assert a["ra1"] - a["ra0"] <= 0.6 / np.cos(np.radians(5)) + 1e-9
    assert chunks[0]["ra0"] > 359 and chunks[-1]["ra1"] > 360  # unwrapped across RA 0
    assert "POLYGON('ICRS'" in movers._box_adql(chunks[-1], 0.05)
    assert movers.track_chunks(make_eph(), elong=(100, 120)) == []


def test_find_images_europa(monkeypatch, tmp_path):
    def request(method, url, params, timeout):
        if "irsa" in url:
            assert "INTERSECTS(p.poly, POLYGON('ICRS'" in params["QUERY"]
            return fx("plane_europa.csv")
        return fx("horizons_tlist_europa.txt" if "TLIST" in params
                  else "horizons_range_europa.txt")

    monkeypatch.setattr(catalogs, "_request", request)
    hits = movers.find_images("52 Europa", 60907.8, 60908.3, cache_dir=tmp_path)
    assert movers.hits_table(hits) == STUB["hits"]
    assert [h.det for h in hits] == [3, 6, 3, 6, 3, 6]
    assert all(h.collection.startswith("spherex_") and h.edge_arcsec > 800 for h in hits)
    assert hits[0].ref.url("s3").startswith("https://nasa-irsa-spherex.s3.amazonaws.com/")
    assert hits[0].vmag == pytest.approx(12.17, abs=0.01)


def hit(mjd: float, ra: float, dec: float = 10.0, det: int = 3) -> movers.MoverHit:
    return movers.MoverHit(f"x/level2_{mjd:.4f}_D{det}.fits", "spherex_qr", det, mjd, ra, dec,
                           12.0, 30.0, 0.0, 90.0, 2.5, 1000.0)


def test_best_fixed_field_picks_the_densest_stretch():
    # 30 arcsec/h eastward; visits every 1.6 h, but a 12-hour gap after the fourth one
    times = [0.0, 1.6, 3.2, 4.8, 16.8, 18.4, 20.0, 21.6, 23.2, 24.8]
    hits = [hit(60000 + t / 24, 50.0 + 30.0 * t / 3600 / np.cos(np.radians(10)), det=d)
            for t in times for d in (3, 6)]
    ra, dec, inside = movers.best_fixed_field(hits, size_pix=61)
    got = sorted({round((hits[i].mjd - 60000) * 24, 1) for i in inside})
    assert got == [16.8, 18.4, 20.0, 21.6, 23.2, 24.8]  # 8 h x 30"/h = 240" fits in 301"
    assert len(inside) == 12
    assert dec == pytest.approx(10.0)
    x, _ = movers._gnomonic([hits[i].ra for i in inside], [10.0] * 12, ra, dec)
    assert np.abs(x).max() <= (61 / 2 - 6) * 6.15 + 1e-6
    with pytest.raises(ValueError):
        movers.best_fixed_field([])


def test_select_refs_keeps_mandatory_and_filters_detectors():
    refs = [ImageRef(f"a/f{i}_D{d}.fits", 60000 + i, 60000 + i, f"SPHEREx-D{d}", "c")
            for i in range(30) for d in (1, 3, 6)]
    must = {"f2_D1.fits", "f3_D3.fits"}
    out = movers.select_refs(refs, must, 100, dets=(3, 6))
    assert len(out) == 2 + 59 and must <= {r.name for r in out}
    assert {r.band for r in out if r.name not in must} == {"SPHEREx-D3", "SPHEREx-D6"}
    capped = movers.select_refs(refs, must, 20)
    assert len(capped) <= 20 and must <= {r.name for r in capped}
    assert [r.mjd_start for r in capped] == sorted(r.mjd_start for r in capped)
    assert {r.name for r in movers.select_refs(refs, must, 1)} == must


def test_fixed_field_jobs_respects_detectors(monkeypatch):
    at_position = [ImageRef(f"a/f{i}_D{d}.fits", 60000 + i, 60000 + i, f"SPHEREx-D{d}", "c")
                   for i in range(10) for d in (2, 3, 6)]
    monkeypatch.setattr(movers, "list_images", lambda ra, dec: at_position)
    hits = [hit(60000.5, 50.0, det=3), hit(60000.5, 50.0, det=2)]
    jobs, n_all = movers.fixed_field_jobs(50.0, 10.0, hits, [0, 1], max_n=100, dets=(3, 6))
    assert n_all == 21 and len(jobs) == 21  # 20 at the position + the D3 hit; D2 hit dropped
    assert {j[0].band for j in jobs} == {"SPHEREx-D3", "SPHEREx-D6"}
    assert all(j[1:] == (50.0, 10.0) for j in jobs)
    jobs, n_all = movers.fixed_field_jobs(50.0, 10.0, hits, [0, 1], max_n=100)
    assert n_all == 32


def test_box_flux_recovers_a_point_source():
    rng = np.random.default_rng(1)
    img = 0.3 + 0.01 * rng.standard_normal((41, 41))
    yy, xx = np.mgrid[0:41, 0:41]
    img += 50.0 * np.exp(-((xx - 20) ** 2 + (yy - 20) ** 2) / (2 * 0.6**2)) / (2 * np.pi * 0.6**2)
    s, e, n_bad = movers.box_flux(img, 20, 20)
    assert s == pytest.approx(50.0, rel=0.01) and n_bad == 0
    assert e == pytest.approx(0.05, rel=0.4)  # 0.01 per pixel x sqrt(25)
    img[20, 21] = np.nan
    assert movers.box_flux(img, 20, 20)[2] == 1
    assert np.isnan(movers.box_flux(img, 1, 1)[0])  # box falls off the image


def test_most_cross_check_agrees_with_find_images(monkeypatch, tmp_path):
    """IRSA MOST lists the same images; its positions agree to better than 1 arcsec."""
    seen = {}

    def request(method, url, params, timeout):
        seen.update(params)
        return fx("most_europa.tbl")

    monkeypatch.setattr(catalogs, "_request", request)
    rows = movers.most_search(20000052, "2025-08-20", "2025-08-22", cache_dir=tmp_path)
    assert seen["obj_name"] == "20000052:NID" and seen["catalog"] == "spherex"
    assert len(rows) == 4
    assert all(r["name"].startswith("level2_2025W34_") and r["name"].endswith(".fits")
               for r in rows)
    assert all(60907.0 < r["mjd"] < 60909.0 and 12.0 < r["vmag"] < 12.6 for r in rows)
    assert all(abs(r["dec"] - 11.21) < 0.01 and 54.6 < r["ra"] < 55.0 for r in rows)
    assert movers.parse_ipac_table("no table here") == []


def test_register_target_replaces_by_key(tmp_path):
    fn = tmp_path / "extra_targets.json"
    movers.register_target(fn, {"key": "a", "ra": 1.0})
    movers.register_target(fn, {"key": "b", "ra": 2.0})
    movers.register_target(fn, {"key": "a", "ra": 3.0})
    assert json.loads(fn.read_text()) == [{"key": "b", "ra": 2.0}, {"key": "a", "ra": 3.0}]
