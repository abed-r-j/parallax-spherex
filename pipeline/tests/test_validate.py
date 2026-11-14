"""Pieces of the validation that have their own statistics (no data needed).

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import numpy as np

from parallax import export, ledger, validate
from test_template import make_field


def test_period_bootstrap_reflects_the_scatter_between_bins():
    trial = np.arange(120.0, 500.1, 2.0)
    rng = np.random.default_rng(0)
    # every bin prefers a slightly different period around 250 d
    centres = 250.0 + rng.normal(0, 25.0, 40)
    scans = np.array([((trial - c) / 30.0) ** 2 for c in centres])
    b = validate.period_bootstrap(trial, scans)
    assert b["nBoot"] == 1000
    assert b["boot95"][0] <= b["boot68"][0] <= b["bootMedian"] <= b["boot68"][1] <= b["boot95"][1]
    assert abs(b["bootMedian"] - centres.mean()) < 6
    width = b["boot68"][1] - b["boot68"][0]
    assert 3 < width < 20  # about 2 x 25 / sqrt(40) = 8 d, on a 2 d grid
    # identical bins: no scatter at all
    same = validate.period_bootstrap(trial, np.array([((trial - 250.0) / 30.0) ** 2] * 40))
    assert same["boot95"] == [250.0, 250.0]
    assert validate.period_bootstrap(trial, scans) == b  # fixed seed


def test_brightness_encoding_clips_nothing_finite():
    f = make_field(per_pass=4)
    f.img[0, 3, 3] = -50.0  # a strongly negative artefact pixel
    f.img[1, 5, 5] = np.nan
    soft, lo, hi = ledger.pack_encoding(f)
    q = export.encode_brightness(f.img, soft, lo, hi)
    back = export.decode_brightness(q, soft, lo, hi)
    ok = np.isfinite(f.img)
    assert (np.isnan(back) == ~ok).all()
    assert q[ok].min() >= 1 and q[0, 3, 3] == 1  # the minimum itself, not a clipped value
    err = np.abs(back[ok] - f.img[ok])
    assert (err <= 1e-3 * np.maximum(np.abs(f.img[ok]), soft)).all()
    assert abs(back[0, 3, 3] + 50.0) < 0.05


def test_snr_encoding_saturates_but_detections_keep_the_real_value():
    s = np.array([np.nan, -40.0, 5.0, 500.0], np.float32)
    assert export.encode_snr(s).tolist() == [-128, -127, 20, 127]  # +-31.75 at most
    from parallax import detect

    d = detect.Detection(0, 1.0, 2.0, 10.0, 20.0, 186.45, 5e4, "mover", 20, "test")
    assert d.to_json()["snr"] == 186.4 or d.to_json()["snr"] == 186.5
