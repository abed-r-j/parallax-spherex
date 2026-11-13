"""The ledger block, the pack products and the figures, on the synthetic field.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from parallax import diffim, export, ledger
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
    # the synthetic sky is static: colour floods the naive pair, not the template
    assert m["naive"]["falsePlain"]["perFrame"] > 2.0
    assert m["corrected"]["falsePlain"]["perFrame"] < 0.2
    assert m["corrected"]["falsePlain"]["perFrame"] <= m["gated"]["falsePlain"]["perFrame"]
    assert m["corrected"]["depthUJy"]["faint"] < m["gated"]["depthUJy"]["faint"]
    inj = led["injection"]
    assert set(inj) == {"atThreshold5", "atFixedRate"}
    assert m["naive"]["thresholdAtFixedRate"] >= 3.0


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
