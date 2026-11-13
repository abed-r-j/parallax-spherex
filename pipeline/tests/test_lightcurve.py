"""Offline tests of the matched-wavelength light curves and ratio spectra.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import numpy as np
import pytest

from parallax import lightcurve as lc
from parallax import photometry as ph


def make_phot(mjd: np.ndarray, det: np.ndarray, lam: np.ndarray, flux: np.ndarray,
              campaign: np.ndarray, rel_err: float = 0.01, seed: int = 0,
              quality: np.ndarray | None = None) -> ph.Photometry:
    rng = np.random.default_rng(seed)
    n = len(mjd)
    err = rel_err * flux
    obs = flux + rng.normal(0, 1, n) * err
    nan = np.full(n, np.nan)
    return ph.Photometry(
        x=np.zeros(n), y=np.zeros(n), mjd=mjd, det=det, campaign=campaign, lam=lam,
        bw=np.full(n, 0.02), flux=obs, err=err, flux_psf=obs, err_psf=err, flux_wing=obs * 0.05,
        err_wing=err * 0.05, bkg=np.zeros(n),
        quality=np.zeros(n, int) if quality is None else quality, hole=np.zeros(n), r_ap=2.5,
        wing=(4.0, 7.0),
    ) if n else nan


def three_passes(change=(0.0, -0.5, 0.3), chromatic: float = 0.0, per: int = 18, seed: int = 0):
    """A red star seen in three passes; pass k is ``change[k]`` mag away from pass 0,
    plus ``chromatic`` mag per micron. Each pass samples different wavelengths."""
    rng = np.random.default_rng(seed)
    mjd, det, lam, flux, camp = [], [], [], [], []
    for c, dm in enumerate(change):
        for d, (a, b) in ph.DETECTOR_BANDS.items():
            w = np.sort(rng.uniform(a + 0.002, b - 0.002, per))
            sed = 1e5 * w**1.7 * (1 + 0.3 * np.sin(6 * w))
            m = dm + chromatic * (w - 2.5) * (c > 0)
            mjd.append(61000 + 180 * c + rng.uniform(0, 10, per))
            det.append(np.full(per, d))
            lam.append(w)
            flux.append(sed * 10 ** (-0.4 * m))
            camp.append(np.full(per, c))
    cat = [np.concatenate(v) for v in (mjd, det, lam, flux, camp)]
    return make_phot(cat[0], cat[1].astype(int), cat[2], cat[3], cat[4].astype(int), seed=seed)


def test_naive_light_curve_is_dominated_by_colour():
    p = three_passes(change=(0.0, 0.0, 0.0))
    raw = -2.5 * np.log10(p.flux / np.median(p.flux))
    assert np.std(raw) > 0.5  # the "variability" of a constant star without matching
    r = lc.ratio_spectrum(p, ref=0)
    assert all(abs(g["meanDmag"]) < 0.02 for g in r["groups"])


def test_ratio_spectrum_recovers_grey_change():
    r = lc.ratio_spectrum(three_passes(), ref=0)
    assert r["ref"] == 0 and [g["group"] for g in r["groups"]] == [1, 2]
    for g, truth in zip(r["groups"], (-0.5, 0.3), strict=True):
        assert g["meanDmag"] == pytest.approx(truth, abs=0.02)
        assert np.median(g["dmag"]) == pytest.approx(truth, abs=0.03)
        assert abs(g["slopeMagPerMicron"]) < 0.02
        assert set(g["perDetector"]) == {"1", "2", "3", "4", "5", "6"}
        assert g["ratio"][0] == pytest.approx(10 ** (-0.4 * truth), rel=0.05)


def test_ratio_spectrum_recovers_colour_change():
    r = lc.ratio_spectrum(three_passes(change=(0.0, 0.1, 0.1), chromatic=-0.2), ref=0)
    g = r["groups"][0]
    assert g["slopeMagPerMicron"] == pytest.approx(-0.2, abs=0.02)
    assert g["perDetector"]["1"]["dmag"] > g["perDetector"]["6"]["dmag"] + 0.5


def test_reference_defaults_to_best_populated_group_and_needs_two():
    p = three_passes()
    keep = ~((p.campaign == 0) & (p.det > 3))
    q = make_phot(p.mjd[keep], p.det[keep], p.lam[keep], p.flux[keep], p.campaign[keep])
    assert lc.ratio_spectrum(q)["ref"] in (1, 2)
    single = p.campaign == 0
    one = make_phot(p.mjd[single], p.det[single], p.lam[single], p.flux[single],
                    p.campaign[single])
    assert lc.ratio_spectrum(one)["groups"] == []


def test_saturated_frames_are_left_out():
    p = three_passes()
    p.quality[p.det == 4] = ph.SATURATED
    r = lc.ratio_spectrum(p, ref=0)
    assert "4" not in r["groups"][0]["perDetector"]
    wing = lc.ratio_spectrum(p, ref=0, which="wing")
    assert "4" in wing["groups"][0]["perDetector"]
    assert wing["groups"][0]["meanDmag"] == pytest.approx(-0.5, abs=0.03)


def test_no_extrapolation_beyond_reference_coverage():
    p = three_passes()
    ok = np.ones(len(p), bool)
    sed = lc.reference_sed(p, ok & (p.campaign == 0) & (p.lam < 3.0), p.flux, p.err)
    s, _ = lc.interpolate_sed(sed, np.array([0.9, 4.6]), np.array([1, 6]))
    assert np.isfinite(s[0]) and np.isnan(s[1])


def test_lightcurve_by_wavelength():
    curves = lc.lightcurve_by_wavelength(three_passes(per=40), grid=lc.coarse_grid(3))
    assert len(curves) == 18
    for c in curves:
        assert list(c["group"]) == [0, 1, 2]
        # Wide bins are only rough: each pass samples the bin at other wavelengths.
        assert c["mag"][1] - c["mag"][0] == pytest.approx(-0.5, abs=0.3)
    narrow = lc.lightcurve_by_wavelength(three_passes(per=40))
    assert len(narrow) > 60 and all(c["lamHi"] - c["lamLo"] < 0.1 for c in narrow)
    full = [c for c in narrow if list(c["group"]) == [0, 1, 2]]
    assert np.median([c["mag"][1] - c["mag"][0] for c in full]) == pytest.approx(-0.5, abs=0.05)
    assert np.median([c["mag"][2] - c["mag"][0] for c in full]) == pytest.approx(0.3, abs=0.05)


def test_epoch_groups():
    g = lc.epoch_groups(np.array([0.0, 3.0, 21.0, 81.0, 99.0]), 20.0)
    assert g.tolist() == [0, 0, 1, 2, 2]


def test_fit_sinusoid_and_period_scan():
    rng = np.random.default_rng(2)
    t = np.sort(rng.uniform(60800, 61300, 40))
    period, t_max, amp = 246.0, 60850.0, 0.6
    mag = 0.1 - amp * np.cos(2 * np.pi * (t - t_max) / period) + rng.normal(0, 0.03, t.size)
    err = np.full(t.size, 0.03)
    f = lc.fit_sinusoid(t, mag, err, period)
    assert f["amplitude"] == pytest.approx(amp, abs=0.03) and f["peakToPeak"] == 2 * f["amplitude"]
    assert ((f["tMax"] - t_max + period / 2) % period) - period / 2 == pytest.approx(0, abs=4)
    assert f["chi2"] < 0.1 * f["chi2Constant"]
    s = lc.period_scan(t, mag, err, np.arange(150.0, 400.0, 2.0))
    assert s["lo"] - 2 <= period <= s["hi"] + 2 and abs(s["best"] - period) < 8
    assert lc.fit_sinusoid(t[:3], mag[:3], err[:3], period) is None


def test_phase_analysis_reports_lag():
    rng = np.random.default_rng(4)
    period = 246.0
    curves = []
    for k, lag in enumerate((0.0, 0.1)):
        t = np.sort(rng.uniform(60800, 61300, 12))
        mag = -0.5 * np.cos(2 * np.pi * ((t - 60850.0) / period - lag)) + rng.normal(0, 0.02, 12)
        curves.append({"mjd": t, "mag": mag, "magErr": np.full(12, 0.02), "lam": 1.0 + k,
                       "det": 1 + k, "lamLo": 0.9 + k, "lamHi": 1.1 + k})
    curves.append({"mjd": t[:3], "mag": mag[:3], "magErr": np.full(3, 0.02), "lam": 4.0, "det": 5,
                   "lamLo": 3.9, "lamHi": 4.1})  # too few points: skipped
    out = lc.phase_analysis(curves, period, epoch_max=60850.0 - 3 * period)
    assert out["nBins"] == 2 and out["nSignificant"] == 2
    assert out["bins"][0]["phaseLag"] == pytest.approx(0.0, abs=0.02)
    assert out["bins"][1]["phaseLag"] == pytest.approx(0.1, abs=0.02)
    assert out["medianPeakToPeak"] == pytest.approx(1.0, abs=0.06)
