"""Offline tests of centroids, the motion fit and the faint-target search (synthetic data).

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import numpy as np
import pytest

from parallax import motion as mo
from parallax import photometry as ph
from parallax.frames import Field
from parallax.targets import Target

N = 51
SIGMA = 0.8
PASS_MJD = (61000.0, 61182.0, 61365.0)
TARGET = Target("synthetic", "Synthetic mover", "motion", 150.0, 20.0, 2026.5,
                pm_ra=-3000.0, pm_dec=9000.0)
REFS = [(10.3, 12.2), (40.6, 9.4), (8.5, 39.7), (41.2, 41.8), (25.4, 44.1), (43.3, 24.6)]


def gauss(x: float, y: float, amp_sum: float) -> np.ndarray:
    yy, xx = np.mgrid[0:N, 0:N]
    return amp_sum * np.exp(-0.5 * ((xx - x) ** 2 + (yy - y) ** 2) / SIGMA**2) / (
        2 * np.pi * SIGMA**2)


def empty_field(nf: int, det: np.ndarray, campaign: np.ndarray, mjd: np.ndarray,
                noise: float) -> Field:
    fwhm = np.sqrt(SIGMA**2 - 1 / 6) * 2.3548 * 6.15
    return Field(
        ra0=150.0, dec0=20.0, n=N, scale=6.15, img=np.zeros((nf, N, N), np.float32),
        var=np.full((nf, N, N), noise**2, np.float32),
        lam=np.ones((nf, N, N), np.float32), bw=np.full((nf, N, N), 0.02, np.float32),
        flags=np.zeros((nf, N, N), np.int32), mjd=mjd, det=det.astype(np.int16),
        campaign=campaign.astype(np.int16), sky=np.zeros(nf), zodi=np.zeros(nf),
        psf_fwhm=np.full(nf, fwhm), sc_xyz=np.zeros((nf, 3)),
        names=[""] * nf, obsid=[""] * nf, collection=[""] * nf,
    )


def moving_field(target_flux: float, noise: float, dets=(1, 2, 3, 4, 5, 6), per: int = 6,
                 static: bool = True, hole: float = 0.0, offset=(0.0, 0.0), seed: int = 3
                 ) -> Field:
    """Three passes of a star following TARGET's catalogue track (no parallax)."""
    rng = np.random.default_rng(seed)
    det = np.tile(np.repeat(dets, per), 3)
    nper = len(dets) * per
    campaign = np.repeat([0, 1, 2], nper)
    mjd = np.repeat(PASS_MJD, nper) + np.tile(np.arange(nper) * 0.05, 3)
    f = empty_field(len(det), det, campaign, mjd, noise)
    ce, cn = mo.catalogue_track(f, TARGET, mjd)
    x, y = mo.offsets_to_xy(f, ce, cn)
    yy, xx = np.mgrid[0:N, 0:N]
    for i in range(len(det)):
        img = gauss(x[i] + offset[0], y[i] + offset[1], target_flux)
        if static:
            for k, (rx, ry) in enumerate(REFS):
                img = img + gauss(rx, ry, 4.0 + k)
        img = img + rng.normal(0, noise, (N, N))
        if hole:
            img[np.hypot(xx - x[i] - offset[0], yy - y[i] - offset[1]) < hole] = np.nan
        f.img[i] = img
    return f


def test_fit_centre_complete_and_saturated():
    rng = np.random.default_rng(0)
    img = gauss(25.37, 24.81, 50.0) + 0.01 + rng.normal(0, 0.002, (N, N))
    var = np.full((N, N), 0.002**2)
    c = mo.fit_centre(img, var, 25.0, 25.0)
    assert c is not None and not c.core_missing
    assert c.x == pytest.approx(25.37, abs=0.02) and c.y == pytest.approx(24.81, abs=0.02)
    assert c.fwhm == pytest.approx(2.3548 * SIGMA, rel=0.15)
    w = mo.windowed_centroid(img, 25.0, 25.0)
    assert w is not None and w[0] == pytest.approx(25.37, abs=0.02)
    yy, xx = np.mgrid[0:N, 0:N]
    holed = np.where(np.hypot(xx - 25.37, yy - 24.81) < 2.2, np.nan, gauss(25.37, 24.81, 5000.0)
                     + rng.normal(0, 0.002, (N, N)))
    c2 = mo.fit_centre(holed, var, 25.0, 25.0, radius=7.0)
    assert c2 is not None and c2.core_missing
    assert np.hypot(c2.x - 25.37, c2.y - 24.81) < 0.1
    assert mo.windowed_centroid(holed, 25.0, 25.0) is None
    assert mo.fit_centre(np.full((N, N), np.nan), var, 25.0, 25.0) is None


def test_stack_frames_rejects_outliers():
    rng = np.random.default_rng(1)
    img = rng.normal(1.0, 0.01, (12, 9, 9))
    img[3, 4, 4] = 50.0
    img[5, 2, 2] = np.nan
    mean, var, cov = mo.stack_frames(img, np.full(img.shape, 1e-4), grow=0)
    assert mean[4, 4] == pytest.approx(1.0, abs=0.02)
    assert cov[2, 2] == pytest.approx(11 / 12) and cov[0, 0] == 1.0
    assert var[0, 0] == pytest.approx(1e-4 / 12, rel=1e-3)


def test_fit_motion_exact_and_parallax():
    t = np.array([2025.4, 2025.9, 2026.4, 2026.9])
    pe, pn = np.array([0.9, -0.9, 0.9, -0.9]), np.array([0.3, -0.3, 0.3, -0.3])
    east = 1.0 + 4.0 * (t - 2026) + 0.5 * pe
    north = -2.0 - 2.5 * (t - 2026) + 0.5 * pn
    e = np.full(4, 0.1)
    free = mo.fit_motion(t, east, north, e, e, pe, pn, free_parallax=True)
    assert free["pmEast"] == pytest.approx(4.0) and free["pmNorth"] == pytest.approx(-2.5)
    assert free["parallax"] == pytest.approx(0.5) and free["dof"] == 3
    fixed = mo.fit_motion(t, east, north, e, e, pe, pn, parallax=0.5)
    assert fixed["total"] == pytest.approx(np.hypot(4.0, 2.5)) and fixed["chi2"] < 1e-9
    assert fixed["pa"] == pytest.approx(np.degrees(np.arctan2(4.0, -2.5)) % 360)
    assert mo.fit_motion(t, east, north, e, e)["chi2"] > 10  # ignoring parallax fits badly
    with pytest.raises(ValueError):
        mo.fit_motion(t[:2], east[:2], north[:2], e[:2], e[:2], pe[:2], pn[:2], free_parallax=True)


def test_parallax_factors_alternate_at_quadrature():
    # RA 18h, on the ecliptic: quadrature near the equinoxes, six months apart.
    pe, pn = mo.parallax_factors(270.0, -23.4, np.array([61120.0, 61303.0]))
    assert np.all(np.hypot(pe, pn) < 1.03)
    assert pe[0] * pe[1] < -0.8


def test_measure_motion_recovers_catalogue():
    f = moving_field(60.0, 0.004)
    r = mo.measure_motion(f, TARGET, parallax_mas=0.0)
    assert r["nPasses"] == 3 and not r["saturatedCore"]
    assert r["nReferenceStars"] >= 4
    m = r["measured"]
    assert m["total"] == pytest.approx(r["catalogue"]["total"], abs=max(4 * m["eTotal"], 0.15))
    assert abs(r["residual"]["dPa"]) < max(4 * m["ePa"], 1.5)
    assert r["displacementPix"] == pytest.approx(9.487 * 1.0 / 6.15, rel=0.1)
    assert abs(r["residual"]["meanOffsetEast"]) < 0.3
    assert r["detectorScatterPix"] < 0.05
    assert r["parallax"]["nPasses"] == 3


def test_measure_motion_saturated_core():
    f = moving_field(6000.0, 0.004, hole=2.2)
    r = mo.measure_motion(f, TARGET, parallax_mas=0.0)
    assert r["saturatedCore"]
    assert r["measured"]["total"] == pytest.approx(r["catalogue"]["total"], abs=0.5)
    assert not r["parallax"]["supported"]


def test_two_passes_need_the_catalogue_parallax():
    f = moving_field(60.0, 0.004)
    r = mo.measure_motion(f.select(f.campaign < 2), TARGET, parallax_mas=0.0)
    assert r["nPasses"] == 2 and r["measured"]["dof"] == 0
    assert r["parallax"]["supported"] is False and "cannot be separated" in r["parallax"]["note"]
    one = mo.measure_motion(f.select(f.campaign == 0), TARGET, parallax_mas=0.0)
    assert one["measured"] is None


def test_matched_filter_flux_and_background():
    img = gauss(20.0, 20.0, 3.0) + 7.0
    sig = ph.effective_sigma_pix(float(np.sqrt(SIGMA**2 - 1 / 6) * 2.3548 * 6.15), 6.15)
    flux = mo.matched_filter(img, sig)
    assert flux[20, 20] == pytest.approx(3.0, rel=0.02)
    assert abs(flux[40, 40]) < 1e-6
    assert np.isnan(flux[0, 0])


def test_faint_detection_finds_offset_mover_and_ignores_static():
    off = (4.0, -1.0)
    f = moving_field(0.25, 0.02, dets=(5, 6), per=20, offset=off, seed=5)
    r = mo.faint_detection(f, TARGET, parallax_mas=0.0)
    assert r["detected"]
    zp = r["zeroPoint"]
    assert zp["dxPix"] == pytest.approx(off[0], abs=0.5) and zp["dyPix"] == pytest.approx(off[1], abs=0.5)
    assert zp["combinedSnrAtCatalogue"] < 3
    m = r["measured"]
    assert m["fluxUJy"] == pytest.approx(0.25 * ph.ujy_per_mjysr(6.15), rel=0.35)
    assert m["total"] == pytest.approx(r["catalogue"]["total"], abs=max(4 * m["eTotal"], 1.0))
    # Nothing moves in a field of static stars only.
    g = moving_field(0.0, 0.02, dets=(5, 6), per=20, seed=6)
    none = mo.faint_detection(g, TARGET, parallax_mas=0.0)
    assert not none["detected"] and none["upperLimit5SigmaUJy"] > 0


def test_error_is_the_larger_of_formal_and_detector_scatter():
    meas = {"total": 10.2, "pa": 356.0, "eTotal": 0.26, "ePa": 1.5, "ePmRa": 260.0, "ePmDec": 260.0}
    fits = [{"det": d, "total": t, "pa": p, "pmRa": -500.0 + 100 * d, "pmDec": 1e3 * t}
            for d, t, p in zip(range(1, 7), (9.75, 7.42, 10.16, 10.95, 10.19, 10.33),
                               (353.6, 357.0, 359.2, 357.7, 356.2, 358.7), strict=True)]
    out = mo._with_detector_scatter(meas, {"fits": fits})
    assert out["eTotalFormal"] == 0.26 and out["eTotalDetectors"] == pytest.approx(0.494, abs=0.01)
    assert out["eTotal"] == out["eTotalDetectors"] and out["errorSource"] == "detector scatter"
    assert out["ePa"] == 1.5 and out["ePaDetectors"] < 1.5  # the formal one is larger here
    assert out["total"] == 10.2 and out["pa"] == 356.0  # the estimator is untouched
    # position angles that straddle north do not blow up the scatter
    wrap = [dict(f, pa=p) for f, p in zip(fits, (359.0, 1.0, 0.5, 359.5, 0.0, 358.5), strict=True)]
    assert mo._with_detector_scatter(dict(meas, pa=0.0), {"fits": wrap})["ePaDetectors"] < 1.0
    # fewer than three detectors: formal error only
    two = mo._with_detector_scatter(meas, {"fits": fits[:2]})
    assert two["eTotal"] == 0.26 and two["errorSource"] == "formal" and "eTotalDetectors" not in two
    # and the full measurement carries both
    r = mo.measure_motion(moving_field(60.0, 0.004), TARGET, parallax_mas=0.0)
    m = r["measured"]
    assert m["eTotal"] == max(m["eTotalFormal"], m["eTotalDetectors"])
    assert m["nDetectorsForError"] == 6


def test_track_null_test_calibrates_the_combined_statistic():
    f = moving_field(0.25, 0.02, dets=(5, 6), per=20, seed=5)
    r = mo.faint_detection(f, TARGET, parallax_mas=0.0)
    assert "nullTest" not in r  # off by default: it costs about a minute on a real field
    use = np.isin(f.det, (5, 6))
    sig = ph.effective_sigma_pix(float(np.nanmean(f.psf_fwhm[use])), f.scale)
    data = mo._pass_maps(f, TARGET, 0.0, use, sig, 4)
    maps = [d["diff"] / d["diffSd"] for d in data]
    pred = [(d["predX"], d["predY"]) for d in data]
    at = mo.combined_snr(maps, pred)
    assert at == pytest.approx(r["zeroPoint"]["combinedSnrAtCatalogue"])
    assert mo.combined_snr(maps, pred[::-1]) < 0 < at  # a mover: reversed order is negative
    nt = mo.track_null_test(maps, pred, 4.0, at, r["zeroPoint"]["combinedSnr"], n_fixed=300,
                            n_search=12)
    assert nt["nFixed"] == 300 and nt["nSearch"] == 12
    assert 0.2 < nt["fixedStd"] < 2.0
    assert nt["pFixed"] < 0.02 and nt["fixedExceed"] == round(nt["pFixed"] * 300)
    assert nt["searchMedian"] > 0  # a maximum over many offsets is biased positive
    assert nt["pSearch"] <= 0.1
    again = mo.track_null_test(maps, pred, 4.0, at, r["zeroPoint"]["combinedSnr"], n_fixed=300,
                               n_search=0)
    assert again["fixedStd"] == nt["fixedStd"]  # fixed seed
    assert np.isnan(mo.combined_snr(maps, [(-5.0, 2.0)] * len(maps)))
