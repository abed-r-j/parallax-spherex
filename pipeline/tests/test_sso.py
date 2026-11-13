"""Offline tests for parallax.sso, driven by recorded SkyBoT and Horizons responses.

The fixtures are the real answers for asteroid (52) Europa on 20-21 August 2025, when it
crossed the ``europa52`` demo field.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from parallax import catalogs, sso

FX = Path(__file__).parent / "fixtures"
STUB = json.loads((FX / "europa_stub.json").read_text(encoding="utf-8"))


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def stub_field() -> SimpleNamespace:
    return SimpleNamespace(ra0=54.84575, dec0=11.20935, n=61, scale=6.15,
                           mjd=np.array(STUB["mjd"]))


def fake_net(skybot=None, horizons=None, calls=None):
    def request(method, url, params, timeout):
        if calls is not None:
            calls.append(url)
        val = skybot if "skybot" in url else horizons
        if isinstance(val, Exception):
            raise val
        return val
    return request


@pytest.mark.parametrize(("name", "command"), [
    (52, "52;"), ("52 Europa", "52;"), ("Ceres", "Ceres;"), ("2008 SY56", "DES=2008 SY56;"),
    ("Pluto", "999"), ("3I/ATLAS", "DES=3I;CAP;NOFRAG"), ("C/2025 N1", "DES=C/2025 N1;CAP;NOFRAG"),
    ("1P/Halley", "DES=1P;CAP;NOFRAG"), ("DES=2001 AB;", "DES=2001 AB;"),
])
def test_horizons_command(name, command):
    assert sso.horizons_command(name) == command


def test_parse_horizons_range():
    eph = sso.parse_horizons(fx("horizons_range_europa.txt"))
    assert eph.name.startswith("52 Europa")
    assert len(eph) == 13
    assert np.allclose(np.diff(eph.mjd), 1 / 24, atol=1e-6)
    assert eph.mjd[0] == pytest.approx(60907.8, abs=1e-5)
    assert 54.7 < eph.ra[0] < eph.ra[-1] < 54.9  # moving east
    assert np.all((eph.vmag > 12.1) & (eph.vmag < 12.3))
    assert np.all((eph.elong > 90) & (eph.elong < 100))
    assert np.all((eph.delta > 2.6) & (eph.delta < 2.9))
    ra, dec = eph.at(eph.mjd[3] + 0.5 / 24)
    assert ra == pytest.approx(0.5 * (eph.ra[3] + eph.ra[4]))
    assert dec == pytest.approx(0.5 * (eph.dec[3] + eph.dec[4]))


def test_parse_horizons_rejects_error_text():
    with pytest.raises(sso.HorizonsError, match="no ephemeris"):
        sso.parse_horizons("API VERSION: 1.2\nMultiple major-bodies match string\n")


def test_horizons_at_checks_row_count(monkeypatch, tmp_path):
    monkeypatch.setattr(catalogs, "_request", fake_net(horizons=fx("horizons_tlist_europa.txt")))
    eph = sso.horizons_at("52 Europa", STUB["mjd"], cache_dir=tmp_path)
    assert len(eph) == 6 and eph.mjd == pytest.approx(STUB["mjd"], abs=1e-6)
    with pytest.raises(sso.HorizonsError, match="asked for 2"):
        sso.horizons_at("52 Europa", STUB["mjd"][:2], cache_dir=tmp_path / "other")


def test_parse_skybot():
    objs = sso.parse_skybot(fx("skybot_europa.json"))
    assert len(objs) == 8
    eu = objs[0]
    assert (eu["name"], eu["number"], eu["cls"]) == ("Europa", 52, "MB>Outer")
    assert eu["ra"] == pytest.approx(54.82297, abs=1e-5)
    assert eu["dec"] == pytest.approx(11.21043, abs=1e-5)
    assert eu["rate_ra"] == pytest.approx(28.3686)
    assert eu["dg"] == pytest.approx(2.7508, abs=1e-4)
    assert [o["number"] for o in objs].count(None) == 3  # unnumbered objects
    assert sso.parse_skybot("No solar system object was found in the requested FOV") == []
    assert sso.parse_skybot('{"error": "x"}') == []


def test_sexagesimal():
    assert sso._sexa_deg("01 59 48.1381", True) == pytest.approx(29.950575, abs=1e-6)
    assert sso._sexa_deg("-00 30 00.0", False) == pytest.approx(-0.5)


def test_group_times():
    mjd = np.array([0.0, 0.001, 0.2, 0.34, 0.9, 0.9004, 5.0])
    assert sso.group_times(mjd, 8.0) == [[0, 1, 2], [3], [4, 5], [6]]
    assert sso.group_times(mjd[::-1], 8.0)[0] == [6, 5, 4]
    assert len(sso.group_times(mjd, 0.001)) == 7


def test_sso_block_for_europa_field(monkeypatch, tmp_path):
    calls: list[str] = []
    monkeypatch.setattr(catalogs, "_request", fake_net(
        fx("skybot_europa.json"), fx("horizons_tlist_europa_sso.txt"), calls))
    rows, warnings = sso.sso_for_field(stub_field(), cache_dir=tmp_path)
    assert warnings == []
    assert len(calls) == 2  # one SkyBoT cone for the whole 5-hour group, one Horizons TLIST
    assert rows == STUB["sso"]
    assert [r["frame"] for r in rows] == [0, 1, 2, 3, 4, 5]
    r = rows[0]
    assert set(r) == {"frame", "name", "number", "ra", "dec", "x", "y", "vmag", "rateRa",
                      "rateDec", "source"}
    assert (r["name"], r["number"]) == ("Europa", 52)
    assert "Horizons" in r["source"]
    # the asteroid moves east = towards smaller x, about 23 pixels in the 4.9 hours
    assert rows[0]["x"] - rows[4]["x"] == pytest.approx(22.7, abs=0.2)
    # the 22nd-magnitude neighbours in the SkyBoT cone are dropped (vmag_max)
    assert {r["name"] for r in rows} == {"Europa"}


def test_refinement_matters(monkeypatch, tmp_path):
    """Geocentric SkyBoT positions differ measurably from SPHEREx-centric ones.

    Measured here: 0.2-0.5 arcsec at 2.75 au, well inside the 3.5 arcsec geometric bound,
    because SPHEREx points away from the Earth.
    """
    monkeypatch.setattr(catalogs, "_request", fake_net(fx("skybot_europa.json")))
    geo, _ = sso.sso_for_field(stub_field(), cache_dir=tmp_path, refine=False)
    assert all("not refined" in r["source"] for r in geo)
    d = [np.hypot(g["x"] - r["x"], g["y"] - r["y"]) * 6.15
         for g, r in zip(geo, STUB["sso"], strict=True)]
    assert min(d) > 0.1 and max(d) < sso.LEO_PARALLAX_ARCSEC_AU / 2.75


def test_horizons_failure_keeps_skybot_position(monkeypatch, tmp_path):
    monkeypatch.setattr(catalogs, "_request", fake_net(
        fx("skybot_europa.json"), httpx.ConnectError("down")))
    rows, warnings = sso.sso_for_field(stub_field(), cache_dir=tmp_path)
    assert len(rows) == 6 and all("not refined" in r["source"] for r in rows)
    assert len(warnings) == 1 and "Horizons failed for Europa" in warnings[0]


def test_skybot_failure_gives_empty_block(monkeypatch, tmp_path):
    monkeypatch.setattr(catalogs, "_request", fake_net(httpx.ReadTimeout("slow")))
    rows, warnings = sso.sso_for_field(stub_field(), cache_dir=tmp_path)
    assert rows == [] and len(warnings) == 1 and "SkyBoT failed" in warnings[0]


def test_publish_interface(monkeypatch, tmp_path):
    """parallax.publish calls sso.known_objects(field, cache_dir=...) and expects a list."""
    monkeypatch.setattr(catalogs, "_request", fake_net(
        fx("skybot_europa.json"), httpx.ConnectError("down")))
    before = len(catalogs.WARNINGS)
    rows = sso.known_objects(stub_field(), cache_dir=tmp_path)
    assert isinstance(rows, list) and len(rows) == 6
    assert "Horizons failed for Europa" in catalogs.WARNINGS[-1]
    del catalogs.WARNINGS[before:]


def test_empty_skybot_answer_means_no_objects_and_is_not_cached(monkeypatch, tmp_path):
    calls: list[str] = []
    monkeypatch.setattr(catalogs, "_request", fake_net("", calls=calls))
    monkeypatch.setattr(sso, "SKYBOT_RETRY_S", 0.0)
    rows, warnings = sso.sso_for_field(stub_field(), cache_dir=tmp_path)
    assert rows == [] and warnings == []
    assert len(calls) == 2  # asked twice
    assert not list(tmp_path.rglob("*.txt"))


@pytest.mark.network
@pytest.mark.skipif(not os.environ.get("PARALLAX_NETWORK"), reason="set PARALLAX_NETWORK=1")
def test_live_europa(tmp_path):
    rows, warnings = sso.sso_for_field(stub_field(), cache_dir=tmp_path, vmag_max=14.0)
    assert warnings == [] and len(rows) == 6
    assert rows[0]["x"] == pytest.approx(STUB["sso"][0]["x"], abs=0.2)
