"""Injection-recovery machinery on the synthetic field.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import numpy as np
import pytest

from parallax import diffim, inject
from parallax.template import build_template
from test_template import make_field, star_pixels


@pytest.fixture(scope="module")
def setup():
    f = make_field(per_pass=24)
    tpl = build_template(f)
    return f, tpl, diffim.all_modes(f, tpl)


def test_psf_stamp_and_injected_flux():
    f = make_field(per_pass=4)
    _ys, _xs, g = inject.psf_stamp(31, 15.3, 14.6, 0.8)
    assert abs(g.sum() - 1.0) < 0.02
    im = inject.inject_image(f, 0, 15.3, 14.6, 1000.0)
    assert abs(im.sum() * diffim.UJY_PER_MJYSR - 1000.0) < 25
    y, x = np.unravel_index(np.argmax(im), im.shape)
    assert (y, x) == (15, 15)
    corner = inject.inject_image(f, 0, 0.2, 0.2, 1000.0)  # clipped at the edge, no crash
    assert 0 < corner.sum() * diffim.UJY_PER_MJYSR < 1000


def test_sites_are_where_they_should_be(setup):
    f, tpl, _ = setup
    blank, star = inject.site_maps(f, tpl.pred)
    stars = star_pixels(f)
    assert blank.any() and star.any()
    assert not (blank & stars[None]).any()
    assert not blank[:, :4].any() and not star[:, :, -4:].any()
    rng = np.random.default_rng(0)
    sites = inject.mover_sites(f, blank, star, 2, rng)
    assert {s[3] for s in sites} == {"blank", "star"}
    for i in (0, 7):
        pts = np.array([(s[1], s[2]) for s in sites if s[0] == i])
        d = np.hypot(pts[:, None, 0] - pts[None, :, 0], pts[:, None, 1] - pts[None, :, 1])
        assert d[np.triu_indices(len(pts), 1)].min() >= inject.SEPARATION
    fixed = inject.static_sites(f, blank, star, 2, rng)
    one = [(s[1], s[2]) for s in fixed if s[0] in (0, 1) and s[3] == "blank"]
    assert len(set(one)) == len(one) // 2  # the same positions in frames 0 and 1


def test_recovery_goes_from_zero_to_one_with_flux(setup):
    f, tpl, diffs = setup
    blank, star = inject.site_maps(f, tpl.pred)
    sites = inject.mover_sites(f, blank, star, 1, np.random.default_rng(1))
    d = diffs["corrected"]
    faint = inject.recover(f, d, sites, 5.0)
    bright = inject.recover(f, d, sites, 5000.0)
    assert (faint == 1).mean() < 0.02
    assert (bright == 1).mean() > 0.95
    assert set(np.unique(bright)) <= {-2, -1, 0, 1}


def test_unusable_frames_count_as_not_searchable(setup):
    f, tpl, _ = setup
    gated = diffim.gated_diff(f, gate=0.01)  # nothing passes the gate
    blank, star = inject.site_maps(f, tpl.pred)
    sites = inject.mover_sites(f, blank, star, 1, np.random.default_rng(2))
    assert (inject.recover(f, gated, sites, 5000.0) == -1).all()
    assert np.isnan(inject.threshold_for_rate(gated, 0.5))


def test_curves_f50_and_json(setup):
    f, tpl, diffs = setup
    res = inject.injection_recovery(f, diffs, tpl.pred, fluxes=(30.0, 150.0, 600.0, 3000.0),
                                    per_frame=1, per_pass=2, seed=3)
    assert res["fluxUJy"] == [30.0, 150.0, 600.0, 3000.0]
    for mode in diffim.MODES:
        c = res["modes"][mode]["mover"]["blank"]
        assert c["all"][0] < 0.1 and c["all"][-1] > 0.9
        assert 30 < c["f50"] < 3000
        assert c["n"] == len(f)
    # blank sky: the template is deeper than a pair (it averages several references)
    f50 = {m: res["modes"][m]["mover"]["blank"]["f50"] for m in diffim.MODES}
    assert f50["corrected"] < f50["naive"]
    import json

    json.dumps(res)


def test_flux_at_half():
    assert inject.flux_at_half([100, 200, 400], [0.0, 0.5, 1.0]) == pytest.approx(200.0)
    assert inject.flux_at_half([100, 400], [0.0, 1.0]) == pytest.approx(200.0)
    assert inject.flux_at_half([100, 200], [0.1, 0.2]) is None
    assert inject.flux_at_half([100, 200], [0.9, 1.0]) == 100.0


def test_threshold_for_rate_is_consistent(setup):
    _, _, diffs = setup
    d = diffs["naive"]
    r5 = inject.detection_rate(d, 5.0)
    thr = inject.threshold_for_rate(d, 0.25)
    assert inject.detection_rate(d, thr) <= 0.25
    if r5 > 0.25:
        assert thr > 5.0
    mask = np.ones(d.snr.shape, dtype=bool)
    assert inject.detection_rate(d, 5.0, exclude=mask) == 0.0
