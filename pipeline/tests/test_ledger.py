"""The ledger block, the pack products and the figures, on the synthetic field.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from parallax import diffim, export, inject, ledger
from parallax.targets import TARGETS
from test_template import make_field


@pytest.fixture(scope="module")
def processed():
    f = make_field(per_pass=24)
    return f, ledger.process_field(f, with_injection=True)


def test_process_field_matches_the_data_contract(processed):
    f, out = processed
    shape = f.img.shape
    sec = out["extra_sections"]
    assert set(sec) == {"tpl", "snrCorr", "snrNaive", "snrGated"}
    assert sec["tpl"].dtype == np.dtype("<u2") and sec["tpl"].shape == shape
    for k in ("snrCorr", "snrNaive", "snrGated"):
        assert sec[k].dtype == np.dtype("i1") and sec[k].shape == shape
    fe = out["frame_extras"]
    assert set(fe) == {"naivePartner", "gatedPartner", "nRef"}
    assert all(len(v) == len(f) for v in fe.values())
    assert all(isinstance(v, int) for v in fe["naivePartner"])
    assert min(fe["nRef"]) > 1
    assert set(out["blocks"]) == {"detections", "candidates", "ledger"}
    json.dumps(export._clean(out["blocks"]))


def test_template_section_decodes_back(processed):
    f, out = processed
    soft, lo, hi = ledger.pack_encoding(f)
    back = export.decode_brightness(out["extra_sections"]["tpl"], soft, lo, hi)
    tpl = out["products"]["template"].pred
    ok = np.isfinite(tpl) & (tpl > np.sinh(lo) * soft) & (tpl < np.sinh(hi) * soft)
    assert np.allclose(back[ok], tpl[ok], atol=2e-3, rtol=2e-3)


def test_ledger_numbers(processed):
    f, out = processed
    led = out["blocks"]["ledger"]
    assert led["nFrames"] == len(f) and led["nPasses"] == 2
    assert led["templateMode"] == "cross-pass" and led["target"] is None
    assert led["areaDeg2"] == pytest.approx((31 * 6.15 / 3600) ** 2)
    m = led["modes"]
    assert set(m) == set(diffim.MODES)
    for e in m.values():
        assert e["usableFraction"] == 1.0
        assert e["depthUJy"]["all"] > 0
        assert e["false"]["perDeg2"] == pytest.approx(
            e["false"]["perFrame"] / led["areaDeg2"])
    # the synthetic sky is static and well sampled: colour floods the naive pair
    assert m["naive"]["falsePlain"]["perFrame"] > 2.0
    assert m["corrected"]["depthUJy"]["faint"] < m["gated"]["depthUJy"]["faint"]
    # the "plain" column is ONE purely statistical sigma for all three modes
    tpl = out["products"]["template"]
    plain = diffim.plain_modes(f, tpl)
    none = np.zeros(f.img.shape, bool)
    for mode, d in plain.items():
        assert d.info["star_noise"] is False
        assert m[mode]["falsePlain"]["perFrame"] == pytest.approx(
            inject.detection_rate(d, 5.0, none))
    assert plain["corrected"].info["model_error"] is False
    with_map = diffim.corrected_diff(f, tpl, star_noise=False)
    ok = np.isfinite(with_map.sigma) & np.isfinite(plain["corrected"].sigma)
    assert (plain["corrected"].sigma[ok] <= with_map.sigma[ok] * (1 + 1e-5)).all()
    c = m["corrected"]
    assert c["falsePlainModelError"]["perFrame"] <= c["falsePlain"]["perFrame"] + 1e-9
    assert "falsePairCalibration" in c and c["depthPairCalibrationUJy"]["all"] > 0
    assert "falsePlainModelError" not in m["gated"]
    for e in m.values():
        assert set(e["snrWidth"]) == {"faint", "mid", "bright"}
        assert 0.7 < e["snrWidth"]["faint"] < 1.3
        assert e["false"]["positivePerFrame"] <= e["false"]["perFrame"]
        assert e["falseUnitMad"]["perFrame"] >= 0
    inj = led["injection"]
    assert set(inj) == {"atThreshold5", "atFixedRate"}
    assert m["naive"]["thresholdAtFixedRate"] >= 3.0
    scan = led["rateScan"]
    assert scan["rates"] == [0.2, 0.5, 1.0]
    for mode in diffim.MODES:
        assert set(scan["byMode"][mode]) == {"0.2", "0.5", "1"}
        assert scan["byMode"][mode]["0.5"]["f50Blank"] == inj["atFixedRate"]["modes"][mode][
            "mover"]["blank"]["f50"]
        thr = [scan["byMode"][mode][r]["threshold"] for r in ("0.2", "0.5", "1")]
        assert thr[0] >= thr[1] >= thr[2]  # a lower false rate needs a higher threshold


def test_plain_column_floods_for_every_mode_on_undersampled_stars():
    # With pixel-phase jitter a purely statistical sigma floods the template as it floods
    # the pairs; only the template's measured model-error map keeps its count low. The
    # ledger must show both numbers and not present the second as "the same noise model".
    f = make_field(per_pass=24, jitter=0.15)
    led = ledger.compute_ledger(f, with_injection=False)
    m = led["modes"]
    assert m["gated"]["falsePlain"]["perFrame"] > 1.0
    assert m["corrected"]["falsePlain"]["perFrame"] > 1.0
    assert m["corrected"]["falsePlainModelError"]["perFrame"] < (
        0.5 * m["corrected"]["falsePlain"]["perFrame"])
    assert m["gated"]["snrWidth"]["bright"] is None or m["gated"]["snrWidth"]["bright"] > 0


def test_detection_rate_counts_only_usable_frames():
    snr = np.zeros((3, 9, 9), np.float32)
    snr[0, 4, 4:6] = 8.0
    snr[1, 4, 4:6] = -8.0
    snr[2, 4, 4:6] = 8.0  # frame 2 is not usable: its peak must not be counted
    z = np.zeros_like(snr)
    d = diffim.Diff("corrected", z, z + 1, snr, z, z, np.full(3, -1), np.array([True, True, False]))
    assert inject.detection_rate(d, 5.0) == pytest.approx(1.0)
    assert inject.detection_rate(d, 5.0, signs=(1.0,)) == pytest.approx(0.5)
    assert inject.detection_rate(d, 5.0, snr=snr / 2) == 0.0


def test_single_pass_field_is_reported_honestly():
    f = make_field(passes=1, per_pass=20)
    led = ledger.compute_ledger(f, with_injection=False)
    assert led["templateMode"] == "leave-one-visit-out"
    assert led["modes"]["naive"]["usableFraction"] == 0.0
    assert led["modes"]["gated"]["false"]["perFrame"] is None or np.isnan(
        led["modes"]["gated"]["false"]["perFrame"])
    assert led["modes"]["corrected"]["usableFraction"] > 0.9
    assert any("single survey pass" in n for n in led["notes"])
    json.dumps(export._clean(led))


def test_target_lookup_and_mask():
    f = make_field(per_pass=4)
    assert ledger.find_target(f) is None
    assert not ledger.target_mask(f, None).any()
    t = TARGETS["barnard"]
    f.ra0, f.dec0 = t.centre
    assert ledger.find_target(f) is t
    xy = ledger.target_xy(f, t)
    assert np.all(np.abs(xy - 15) < 2)  # the field centre, within the proper motion
    mask = ledger.target_mask(f, t, radius=3)
    assert mask[0, 15, 15] and not mask[0, 2, 2]


def test_figures_are_written(processed, tmp_path):
    f, out = processed
    p = out["products"]
    led = out["blocks"]["ledger"]
    made = ledger.make_figures(f, p["template"], p["diffs"], led, tmp_path)
    assert {"three_panel", "false_detections", "completeness", "template_spectrum"} <= set(made)
    for path in made.values():
        with open(path, "rb") as fh:
            assert fh.read(8) == b"\x89PNG\r\n\x1a\n"
    assert 0 <= led["figureFrame"] < len(f)
