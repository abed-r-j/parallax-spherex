"""Offline tests for parallax.catalogs, driven by recorded real service responses.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from parallax import catalogs

FX = Path(__file__).parent / "fixtures"
BARNARD = (269.4486, 4.7379)


class FakeNet:
    """Stand-in for catalogs._request: serves fixtures by URL, counts calls."""

    def __init__(self, routes: dict[str, str | Exception]):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, method, url, params, timeout):
        self.calls.append((url, params))
        for key, val in self.routes.items():
            if key in url:
                if isinstance(val, Exception):
                    raise val
                return val
        raise AssertionError(f"unexpected request to {url}")


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def test_gaia_rows_from_esa(monkeypatch, tmp_path):
    net = FakeNet({"esac.esa.int": fx("gaia_esa_barnard.csv")})
    monkeypatch.setattr(catalogs, "_request", net)
    rows, warn = catalogs.gaia_cone(*BARNARD, 0.03, cache_dir=tmp_path)
    assert warn == ""
    assert len(rows) == 73
    star = rows[0]  # brightest = Barnard's Star
    assert star["id"] == "4472832130942575872" and isinstance(star["id"], str)
    assert star["pmDec"] == pytest.approx(10362.394)
    assert star["plx"] == pytest.approx(546.976)
    assert set(star) == {"id", "ra", "dec", "pmRa", "pmDec", "plx", "g"}
    assert all(r["g"] < 19 for r in rows)
    assert [r["g"] for r in rows] == sorted(r["g"] for r in rows)
    adql = net.calls[0][1]["QUERY"]
    assert "gaiadr3.gaia_source" in adql and "TOP 400" in adql


def test_gaia_is_cached_on_disk(monkeypatch, tmp_path):
    net = FakeNet({"esac.esa.int": fx("gaia_esa_barnard.csv")})
    monkeypatch.setattr(catalogs, "_request", net)
    a, _ = catalogs.gaia_cone(*BARNARD, 0.03, cache_dir=tmp_path)
    b, _ = catalogs.gaia_cone(*BARNARD, 0.03, cache_dir=tmp_path)
    assert a == b and len(net.calls) == 1
    assert len(list((tmp_path / "gaia_esa").glob("*.txt"))) == 1


def test_gaia_falls_back_to_irsa(monkeypatch, tmp_path):
    busy = httpx.HTTPStatusError("429", request=None, response=None)
    net = FakeNet({"esac.esa.int": busy, "irsa.ipac": fx("gaia_irsa_barnard.csv")})
    monkeypatch.setattr(catalogs, "_request", net)
    rows, warn = catalogs.gaia_cone(*BARNARD, 0.03, cache_dir=tmp_path)
    assert rows and rows[0]["id"] == "4472832130942575872"
    assert "fallback" in warn
    assert "gaia_dr3_source" in net.calls[1][1]["QUERY"]


def test_gaia_never_raises(monkeypatch, tmp_path):
    net = FakeNet({"esac.esa.int": httpx.ConnectError("down"),
                   "irsa.ipac": "<VOTABLE>QUERY_STATUS ERROR</VOTABLE>"})
    monkeypatch.setattr(catalogs, "_request", net)
    rows, warn = catalogs.gaia_cone(*BARNARD, 0.03, cache_dir=tmp_path)
    assert rows == [] and "unavailable" in warn
    assert not list(tmp_path.rglob("*.txt"))  # error pages are not cached


def test_catwise_rows(monkeypatch, tmp_path):
    net = FakeNet({"irsa.ipac": fx("catwise_barnard.csv")})
    monkeypatch.setattr(catalogs, "_request", net)
    rows, warn = catalogs.catwise_cone(*BARNARD, 0.03, cache_dir=tmp_path)
    assert warn == "" and len(rows) == 114
    assert set(rows[0]) == {"id", "ra", "dec", "w1", "w2", "pmRa", "pmDec"}
    assert rows[0]["id"] == "J175746.89+044440.6"
    assert rows[0]["pmRa"] == pytest.approx(-1878.1)  # arcsec/yr in the table -> mas/yr
    assert "catwise_2020" in net.calls[0][1]["QUERY"]


def test_catwise_never_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(catalogs, "_request", FakeNet({"irsa": httpx.ReadTimeout("slow")}))
    rows, warn = catalogs.catwise_cone(*BARNARD, 0.03, cache_dir=tmp_path)
    assert rows == [] and warn.startswith("CatWISE2020 unavailable")


def test_catwise_hole_falls_back_to_allwise(monkeypatch, tmp_path):
    """Real case: CatWISE2020 is empty within 4.8 arcmin of R Draconis.

    The empty CatWISE answer is the recorded one. The AllWISE body is SYNTHETIC (IRSA TAP
    was timing out when the fixtures were recorded), so this checks the code path only.
    """
    allwise = ("designation,ra,dec,w1mpro,w2mpro,pmra,pmdec\n"
               "J163240.21+664518.0,248.1675,66.7550,-1.9,-2.1,12,-30\n"
               "J163251.00+664601.2,248.2125,66.7670,11.234,11.301,,\n")

    def request(method, url, params, timeout):
        return allwise if "allwise_p3as_psd" in params["QUERY"] else fx("catwise_rdra_empty.csv")

    monkeypatch.setattr(catalogs, "_request", request)
    rows, warn = catalogs.catwise_cone(248.1675, 66.755, 0.03, cache_dir=tmp_path)
    assert len(rows) == 2 and "AllWISE" in warn
    assert set(rows[0]) == {"id", "ra", "dec", "w1", "w2", "pmRa", "pmDec"}
    assert rows[0]["pmDec"] == -30.0 and rows[1]["pmRa"] is None


def test_overlays_limited_to_field(monkeypatch, tmp_path):
    net = FakeNet({"esac.esa.int": fx("gaia_esa_barnard.csv"),
                   "irsa.ipac": fx("catwise_barnard.csv")})
    monkeypatch.setattr(catalogs, "_request", net)
    out = catalogs.overlays_for_field(*BARNARD, n=21, cache_dir=tmp_path)
    assert out["warnings"] == []
    assert 0 < len(out["wise"]) < 114
    half = (21 / 2 + 2) * 6.15 / 3600
    assert all(abs(w["dec"] - BARNARD[1]) <= half for w in out["wise"])
    star, dist = catalogs.nearest(out["gaia"], 269.44850, 4.73942)
    assert star["id"] == "4472832130942575872" and dist < 0.1


def test_publish_interface(monkeypatch, tmp_path):
    """parallax.publish calls gaia_dr3 / catwise with a radius in arcsec and expects lists."""
    net = FakeNet({"esac.esa.int": fx("gaia_esa_barnard.csv"),
                   "irsa.ipac": httpx.ReadTimeout("slow")})
    monkeypatch.setattr(catalogs, "_request", net)
    before = len(catalogs.WARNINGS)
    gaia = catalogs.gaia_dr3(*BARNARD, 108.0, cache_dir=tmp_path)
    assert len(gaia) == 73 and "0.03000" in net.calls[0][1]["QUERY"]
    assert catalogs.catwise(*BARNARD, 108.0, cache_dir=tmp_path) == []
    assert catalogs.WARNINGS[before:] and "CatWISE2020 unavailable" in catalogs.WARNINGS[-1]
    del catalogs.WARNINGS[before:]


def test_geometry_helpers():
    assert catalogs.field_radius_deg(61) == pytest.approx(0.0785, abs=2e-4)
    assert catalogs.in_field({"ra": 10.0, "dec": 60.0}, 10.0, 60.0, 61)
    assert catalogs.in_field({"ra": 10.1, "dec": 60.0}, 10.0, 60.0, 61)  # 0.05 deg on sky
    assert not catalogs.in_field({"ra": 10.2, "dec": 60.0}, 10.0, 60.0, 61)
    assert catalogs.in_field({"ra": 0.01, "dec": 0.0}, 359.99, 0.0, 61)  # RA wrap


@pytest.mark.network
@pytest.mark.skipif(not os.environ.get("PARALLAX_NETWORK"), reason="set PARALLAX_NETWORK=1")
def test_live_services(tmp_path):
    gaia, w1 = catalogs.gaia_cone(*BARNARD, 0.03, cache_dir=tmp_path)
    wise, w2 = catalogs.catwise_cone(*BARNARD, 0.03, cache_dir=tmp_path)
    assert gaia and gaia[0]["id"] == "4472832130942575872", w1
    assert wise, w2
