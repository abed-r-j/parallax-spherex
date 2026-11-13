"""Offline tests of the per-frame photometry on a synthetic field.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import numpy as np
import pytest

from parallax import photometry as ph
from parallax.frames import Field, bitmask

N = 41
SIGMA = 0.8  # pixels


def star(x: float, y: float, flux_ujy: float, n: int = N) -> np.ndarray:
    """Pixel-sampled Gaussian star in MJy/sr."""
    yy, xx = np.mgrid[0:n, 0:n]
    g = np.exp(-0.5 * ((xx - x) ** 2 + (yy - y) ** 2) / SIGMA**2) / (2 * np.pi * SIGMA**2)
    return flux_ujy * g / ph.ujy_per_mjysr(6.15)


def make_field(fluxes: np.ndarray, det: np.ndarray, campaign: np.ndarray, lam: np.ndarray,
               xy: tuple[float, float] = (20.3, 19.6), noise: float = 0.002, seed: int = 1) -> Field:
    rng = np.random.default_rng(seed)
    nf = len(fluxes)
    img = np.stack([star(*xy, f) for f in fluxes]) + rng.normal(0, noise, (nf, N, N))
    fwhm = np.sqrt(SIGMA**2 - 1 / 6) * 2.3548 * 6.15  # so that effective_sigma_pix == SIGMA
    return Field(
        ra0=10.0, dec0=20.0, n=N, scale=6.15, img=img.astype(np.float32),
        var=np.full((nf, N, N), noise**2, np.float32),
        lam=np.broadcast_to(lam[:, None, None], (nf, N, N)).astype(np.float32).copy(),
        bw=np.full((nf, N, N), 0.02, np.float32), flags=np.zeros((nf, N, N), np.int32),
        mjd=61000.0 + 180.0 * campaign + np.arange(nf) * 0.01, det=det.astype(np.int16),
        campaign=campaign.astype(np.int16), sky=np.zeros(nf), zodi=np.zeros(nf),
        psf_fwhm=np.full(nf, fwhm), sc_xyz=np.zeros((nf, 3)),
        names=[""] * nf, obsid=[""] * nf, collection=[""] * nf,
    )


@pytest.fixture(scope="module")
def field() -> Field:
    det = np.tile(np.repeat(np.arange(1, 7), 8), 2)
    campaign = np.repeat([0, 1], 48)
    lam = np.concatenate([np.linspace(a + 0.005, b - 0.005, 8)
                          for a, b in ph.DETECTOR_BANDS.values()] * 2)
    flux = 5000.0 * lam * np.where(campaign == 1, 1.5, 1.0)  # microJy, pass 1 is 1.5x brighter
    return make_field(flux, det, campaign, lam)


def sky(field: Field, x: float = 20.3, y: float = 19.6) -> tuple[float, float]:
    ra, dec = field.wcs.all_pix2world(x, y, 0)
    return float(ra), float(dec)


def test_unit_conversion():
    assert ph.ujy_per_mjysr(6.15) == pytest.approx(889.86, rel=1e-3)


def test_aperture_weights_area():
    w = ph.aperture_weights((21, 21), 10.3, 9.7, 2.5)
    assert w.sum() == pytest.approx(np.pi * 2.5**2, rel=0.02)
    assert w.max() == 1.0 and w.min() == 0.0


def test_fluxes_recovered(field):
    p = ph.photometry(field, *sky(field))
    truth = 5000.0 * p.lam * np.where(p.campaign == 1, 1.5, 1.0)
    assert (p.quality == ph.GOOD).all()
    # A 2.5 pixel aperture holds 99 % of a sigma = 0.8 pixel Gaussian.
    assert np.median(p.flux / truth) == pytest.approx(0.99, abs=0.015)
    assert np.median(p.flux_psf / truth) == pytest.approx(1.0, abs=0.02)
    pull = (p.flux - np.median(p.flux / truth) * truth) / p.err
    assert 0.5 < np.std(pull) < 2.0
    assert np.allclose(p.lam, field.lam[:, 20, 20])


def test_saturated_core_is_flagged_and_wing_survives(field):
    f = field.select(np.arange(len(field)))
    f.img[:, 18:22, 19:23] = np.nan
    f.flags[:, 17:23, 18:24] |= bitmask("OVERFLOW")
    p = ph.photometry(f, *sky(f), wing=(3.0, 6.0))
    assert (p.quality == ph.SATURATED).all()
    assert np.isnan(p.flux).all()
    assert (p.hole >= 1.0).all()
    assert np.isfinite(p.flux_wing).mean() > 0.9
    rep = ph.quality_report(p)
    assert rep["saturatedFraction"] == 1.0 and rep["usableRanges"] == []


def test_dead_pixel_is_no_data_not_saturated(field):
    f = field.select(np.arange(4))
    f.img[:, 20, 20] = np.nan
    p = ph.photometry(f, *sky(f))
    assert (p.quality == ph.NODATA).all()


def test_suspect_flag(field):
    f = field.select(np.arange(4))
    f.flags[:, 20, 20] |= bitmask("NONLINEAR")
    p = ph.photometry(f, *sky(f))
    assert (p.quality == ph.SUSPECT).all() and np.isfinite(p.flux).all()


def test_moving_position_per_frame(field):
    ra, dec = sky(field)
    ra2, dec2 = sky(field, 30.0, 30.0)
    p = ph.photometry(field, np.where(field.campaign == 0, ra, ra2),
                      np.where(field.campaign == 0, dec, dec2))
    assert np.median(p.flux[p.campaign == 0]) > 1000
    assert abs(np.median(p.flux[p.campaign == 1])) < 50


def test_grids():
    g = ph.channel_grid()
    assert len(g) == 102 and set(g.det) == {1, 2, 3, 4, 5, 6}
    r = ph.regular_grid(40.0)
    assert np.allclose(r.centre / (r.hi - r.lo), 40.0, rtol=0.02)
    assert r.lo[0] == pytest.approx(0.74) and r.hi[-1] >= 5.0


def test_spectra_by_pass(field):
    p = ph.photometry(field, *sky(field))
    spec = ph.spectra_by_group(p)
    assert [s["group"] for s in spec] == [0, 1]
    ok = (spec[0]["n"] > 0) & (spec[1]["n"] > 0)
    assert ok.sum() >= 40
    assert np.median(spec[1]["value"][ok] / spec[0]["value"][ok]) == pytest.approx(1.5, abs=0.03)
    slope = np.polyfit(spec[0]["lam"][ok], spec[0]["value"][ok], 1)[0]
    assert slope == pytest.approx(5000.0 * 0.99, rel=0.03)
    r40 = ph.spectra_by_group(p, grid=ph.regular_grid(40.0))
    assert (r40[0]["n"] > 0).sum() >= 30


def test_combine_uses_scatter():
    v = np.array([1.0, 2.0, 3.0, 2.0, 2.0])
    mean, err, n = ph.combine(v, np.full(5, 1e-3))
    assert n == 5 and mean == pytest.approx(2.0)
    assert err == pytest.approx(np.std(v, ddof=1) / np.sqrt(5))
    assert ph.combine(np.array([np.nan]), np.array([1.0])) == (pytest.approx(np.nan, nan_ok=True),
                                                             pytest.approx(np.nan, nan_ok=True), 0)


def test_merge_ranges():
    assert ph.merge_ranges([(1.0, 1.2), (1.2, 1.5), (2.0, 2.1)]) == [[1.0, 1.5], [2.0, 2.1]]
