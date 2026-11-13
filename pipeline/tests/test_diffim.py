"""The three difference modes share one interface; an injected mover survives the template.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import numpy as np
import pytest

from parallax import diffim
from parallax.inject import inject_image
from parallax.template import build_template
from test_template import BW, NOISE, make_field, star_pixels


@pytest.fixture(scope="module")
def field():
    return make_field()


def test_partners(field):
    nv = diffim.naive_partners(field)
    gt = diffim.gated_partners(field)
    first_of_pass1 = int(np.flatnonzero(field.campaign == 1)[0])
    assert (nv[field.campaign == 0] == first_of_pass1).all()  # nearest in time
    assert (field.campaign[nv] != field.campaign).all()
    assert (gt >= 0).all()
    assert np.all(np.abs(field.lam0[gt] - field.lam0) < diffim.GATE * BW)
    strict = diffim.gated_partners(field, gate=0.01)
    assert (strict == -1).all()
    single = make_field(passes=1, per_pass=10)
    assert (diffim.naive_partners(single) == -1).all()
    assert (diffim.gated_partners(single) == -1).all()


def test_mismatch_map(field):
    m = diffim.mismatch_map(field, 0, 5)
    assert m.shape == (field.n, field.n)
    assert np.allclose(m, (field.lam[0] - field.lam[5]) / BW, atol=1e-4)
    assert np.allclose(diffim.mismatch_map(field, 3, 3), 0.0)


def test_all_modes_share_shape_and_plain_sigma(field):
    tpl = build_template(field)
    diffs = diffim.all_modes(field, tpl, star_noise=False, rescale=False)
    assert set(diffs) == set(diffim.MODES)
    for d in diffs.values():
        assert d.resid.shape == d.sigma.shape == d.snr.shape == field.img.shape
        assert d.usable.shape == (len(field),)
    assert np.allclose(diffs["naive"].sigma, np.sqrt(2) * NOISE, rtol=1e-3)
    assert (diffs["corrected"].partner == -1).all()
    with pytest.raises(ValueError):
        diffim.difference(field, "blink")


def test_gated_mode_gives_no_result_outside_the_gate(field):
    d = diffim.gated_diff(field, gate=0.01)
    assert not d.usable.any()
    assert not np.isfinite(d.snr).any()


def test_corrected_beats_pairs_on_stars_and_noise_is_calibrated(field):
    diffs = diffim.all_modes(field, build_template(field), star_noise=False)
    stars = star_pixels(field)
    frac = {m: float(np.nanmean(np.abs(d.snr[:, stars]) > 5)) for m, d in diffs.items()}
    assert frac["naive"] > 0.5
    assert frac["corrected"] < 0.02
    assert frac["corrected"] < frac["gated"] < frac["naive"]
    for d in diffs.values():
        assert 0.85 < np.nanstd(d.snr[:, ~stars & (np.abs(d.snr) < 5).all(axis=0)]) < 1.15


def test_injected_mover_survives_the_template():
    f = make_field()
    frame, x, y = 12, 16.3, 14.8  # blank sky, a frame of pass 0
    f.img[frame] += inject_image(f, frame, x, y, 1500.0)  # 1.5 mJy
    others = np.delete(np.arange(len(f)), frame)
    ghosts = {}
    for mode in diffim.MODES:
        d = diffim.difference(f, mode, build_template(f))
        peak = float(np.nanmax(d.snr[frame, 13:17, 15:18]))
        assert peak > 8, mode
        ghosts[mode] = int((np.nanmin(d.snr[others][:, 13:17, 15:18], axis=(1, 2)) < -5).sum())
    # a mover sitting in a reference frame is rejected by the robust template, while the
    # pair that uses that frame as its partner shows it as a negative ghost
    assert ghosts["corrected"] == 0
    assert ghosts["gated"] == 1
    d = diffim.corrected_diff(f)
    assert np.nanmax(np.abs(d.snr[others][:, 13:17, 15:18])) < 5
    flux = float(np.nansum(d.resid[frame, 13:17, 14:19])) * diffim.UJY_PER_MJYSR
    assert 1100 < flux < 1700


def test_star_noise_term_absorbs_pixel_phase_scatter():
    f = make_field(jitter=0.15)  # stars land on a different sub-pixel position each frame
    stars = star_pixels(f)
    tpl = build_template(f)
    plain = diffim.gated_diff(f, star_noise=False)
    fitted = diffim.gated_diff(f, star_noise=True)
    frac_plain = np.nanmean(np.abs(plain.snr[:, stars]) > 5)
    frac_fitted = np.nanmean(np.abs(fitted.snr[:, stars]) > 5)
    assert frac_plain > 0.3
    assert frac_fitted < 0.25 * frac_plain
    assert fitted.info["star_gain"][2] > 0.02
    corr = diffim.corrected_diff(f, tpl)
    assert np.nanmean(np.abs(corr.snr[:, stars]) > 5) < 0.05
    # empty sky is untouched by the star term
    assert 0.85 < np.nanstd(fitted.snr[:, 14:18, 14:18]) < 1.15


def test_local_contrast():
    a = np.zeros((1, 7, 7), np.float32)
    a[0, 3, 3] = 2.0
    c = diffim.local_contrast(a)
    assert c[0, 3, 3] == 2.0 and c[0, 2, 2] == 2.0 and c[0, 0, 0] == 0.0
