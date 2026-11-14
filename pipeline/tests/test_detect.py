"""Detection, classification with evidence, and linking of movers.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import numpy as np

from parallax import detect, diffim
from parallax.frames import bitmask
from parallax.inject import inject_image
from test_template import STARS, make_field


def near(dets, x, y, r=2.0):
    return [q for q in dets if np.hypot(q.x - x, q.y - y) <= r]


def test_find_peaks_signs_and_footprint():
    z = np.zeros((2, 15, 15), np.float32)
    z[0, 4, 4] = 9.0  # lone spike
    z[0, 10, 9:12] = [4.0, 7.0, 4.0]  # 3-pixel source
    z[1, 6, 6:8] = [-6.0, -3.0]  # negative, 2 pixels
    z[1, 12, 12] = 4.0  # below threshold
    p = detect.find_peaks(z, 5.0, 1)
    assert len(p) == 3
    p2 = detect.find_peaks(z, 5.0, 2)
    assert {(int(a), int(b), int(c)) for a, b, c in p2[:, :3]} == {(0, 10, 10), (1, 6, 6)}
    assert sorted(p2[:, 3].tolist()) == [-6.0, 7.0]
    assert len(detect.find_peaks(z, 5.0, 2, signs=(1.0,))) == 1
    assert len(detect.find_peaks(np.full((1, 5, 5), np.nan), 5.0)) == 0


def test_mover_is_found_measured_and_classified():
    f = make_field()
    frame, x, y = 12, 16.3, 14.8
    f.img[frame] += inject_image(f, frame, x, y, 2000.0)
    d = diffim.corrected_diff(f)
    dets = detect.detect(f, d)
    hit = near([q for q in dets if q.frame == frame], x, y)
    assert len(hit) == 1
    q = hit[0]
    assert q.cls == "mover" and q.snr > 8
    assert "no static counterpart" in q.evidence
    assert abs(q.x - x) < 0.6 and abs(q.y - y) < 0.6
    assert 1300 < q.flux_ujy < 2700
    ra, dec = f.wcs.all_pix2world(x, y, 0)
    assert abs(q.dec - dec) * 3600 < 4 and abs(q.ra - ra) * 3600 * np.cos(np.radians(dec)) < 4
    rec = q.to_json()
    assert {"frame", "x", "y", "ra", "dec", "snr", "fluxUJy", "cls", "known"} <= set(rec)
    # nothing else in the field is called a mover
    assert sum(q.cls == "mover" for q in dets) == 1


def test_bright_mover_is_still_a_mover():
    # A point source of S/N > 100 covers more pixels above half the threshold than the
    # fixed 30-pixel limit once the PSF has wings; it must not be called "extended".
    f = make_field()
    frame, x, y = 12, 16.3, 14.8
    star = inject_image(f, frame, x, y, 30000.0)  # 30 mJy
    gy, gx = np.mgrid[0: f.n, 0: f.n]
    wings = 0.02 * star.max() * np.exp(-0.5 * ((gx - x) ** 2 + (gy - y) ** 2) / 2.5**2)
    f.img[frame] += star + wings.astype(np.float32)
    dets = detect.detect(f, diffim.corrected_diff(f))
    q = max(near([q for q in dets if q.frame == frame], x, y), key=lambda q: q.snr)
    assert q.snr > 100
    assert q.npix > detect.MAX_AREA  # the old fixed limit would have rejected it
    assert q.npix <= detect.max_area(q.snr, detect.effective_sigma_pix(7.5, f.scale))
    assert q.cls == "mover", q.evidence
    # a faint residual of the same footprint is still not point-like
    assert detect.max_area(6.0, 0.72) < 40 < detect.max_area(200.0, 0.72)
    assert detect.max_area(2.0, 0.72) == detect.MAX_AREA


def test_mover_on_a_faint_static_source_is_a_mover():
    f = make_field()
    frame, x, y = 12, 16.3, 14.8
    for i in range(len(f)):  # a faint static star (about 8 sigma at its peak) in every frame
        f.img[i] += inject_image(f, i, x, y, 230.0)
    quiet = detect.detect(f, diffim.corrected_diff(f))
    assert not near(quiet, x, y)  # the static star alone cancels
    f.img[frame] += inject_image(f, frame, x, y, 2000.0)  # the mover, about 9 times brighter
    d = diffim.corrected_diff(f)
    assert np.nanmax(d.static[frame, 13:17, 15:18]) > 5 * 0.01  # there is a static counterpart
    q = near([q for q in detect.detect(f, d) if q.frame == frame], x, y)[0]
    assert q.cls == "mover", q.evidence
    assert "faint static source underneath" in q.evidence
    # a residual comparable to the star stays a star residual
    g = make_field()
    sx, sy = STARS[3][0], STARS[3][1]
    g.img[frame] += inject_image(g, frame, sx, sy, 1200.0)  # about half of that star's flux
    q = near([q for q in detect.detect(g, diffim.corrected_diff(g)) if q.frame == frame], sx, sy)
    assert q and q[0].cls in {"star-residual", "chromatic"}


def test_linker_speed_limit_matches_the_same_visit_veto():
    # one pixel in the 2.15 minutes between consecutive exposures
    import inspect

    assert detect.MAX_RATE <= 6.15 / (2.15 / 60.0) + 1e-9
    assert inspect.signature(detect.link_movers).parameters["max_rate"].default == detect.MAX_RATE
    # a track faster than the limit is not linked: 6 px in 0.2 h = 184 arcsec/hour
    f = make_field()
    f.mjd[3], f.mjd[4] = f.mjd[2] + 0.2 / 24, f.mjd[2] + 0.4 / 24
    fast = _mover_dets(f, [2, 3, 4], [5.0, 11.0, 17.0], [6.0, 6.0, 6.0])
    assert detect.link_movers(f, fast) == []
    assert len(detect.link_movers(f, fast, max_rate=240.0)) == 1


def test_transient_not_repeated_minutes_later_is_an_artifact():
    f = make_field()
    f.mjd[13] = f.mjd[12] + 2.0 / 1440.0  # frame 13 is the next exposure of the same visit
    f.img[12] += inject_image(f, 12, 16.3, 14.8, 2000.0)  # only in frame 12: cosmic ray
    dets = detect.detect(f, diffim.corrected_diff(f))
    q = near([q for q in dets if q.frame == 12], 16.3, 14.8)[0]
    assert q.cls == "artifact" and "not repeated" in q.evidence
    f.img[13] += inject_image(f, 13, 16.3, 14.8, 2000.0)  # in both: a real source
    dets = detect.detect(f, diffim.corrected_diff(f))
    q = near([q for q in dets if q.frame == 12], 16.3, 14.8)[0]
    assert q.cls == "mover" and "confirmed in the same visit" in q.evidence


def test_moved_star_is_a_motion_dipole():
    f = make_field(moved=True)
    dets = detect.detect(f, diffim.corrected_diff(f))
    x, y = STARS[0][0], STARS[0][1]
    at_star = near(dets, x + 0.75, y, 3.0)
    assert len(at_star) > 40
    assert np.mean([q.cls == "motion-dipole" for q in at_star]) > 0.9
    assert "opposite lobe" in at_star[0].evidence
    groups = detect.group_static(f, dets, "motion-dipole")
    assert groups and groups[0]["rate"] is None and len(groups[0]["frames"]) >= 3


def test_brightened_star_is_variable_and_static_stars_are_quiet():
    f = make_field(variable=True)
    dets = detect.detect(f, diffim.corrected_diff(f))
    x, y = STARS[3][0], STARS[3][1]
    at_star = near(dets, x, y)
    assert len(at_star) > 20
    assert np.mean([q.cls == "variable" for q in at_star]) > 0.9
    later = [q for q in at_star if f.campaign[q.frame] == 1]
    assert later and all(q.snr > 0 for q in later)  # brighter in the second pass
    assert "same sign" in at_star[0].evidence
    assert len(dets) - len(at_star) < 0.05 * len(f)  # the other three stars cancel


def test_flagged_and_edge_detections_are_artifacts():
    f = make_field()
    f.img[5] += inject_image(f, 5, 15.0, 15.0, 3000.0)
    f.flags[5, 15, 15] = bitmask("PERSIST")
    f.img[6] += inject_image(f, 6, 0.6, 15.0, 5000.0)
    dets = detect.detect(f, diffim.corrected_diff(f))
    a = near([q for q in dets if q.frame == 5], 15, 15)[0]
    b = near([q for q in dets if q.frame == 6], 0.6, 15, 2.5)[0]
    assert a.cls == "artifact" and "flag" in a.evidence
    assert b.cls == "artifact" and "edge" in b.evidence


def _mover_dets(f, frames, xs, ys):
    out = []
    for i, x, y in zip(frames, xs, ys, strict=True):
        ra, dec = f.wcs.all_pix2world(x, y, 0)
        out.append(detect.Detection(int(i), float(x), float(y), float(ra), float(dec), 9.0,
                                    500.0, "mover", 4, "test"))
    return out


def test_link_movers_rate_angle_and_chance():
    f = make_field()
    frames = np.array([2, 4, 6, 9])  # 0.07 d = 1.68 h apart
    hours = (f.mjd[frames] - f.mjd[frames[0]]) * 24
    rate_pix = 1.2  # pixels per hour, towards +x (west) and +y (north)
    xs = 5.0 + rate_pix * hours * np.cos(np.radians(30))
    ys = 6.0 + rate_pix * hours * np.sin(np.radians(30))
    dets = _mover_dets(f, frames, xs, ys)
    dets += _mover_dets(f, [20, 30], [25.0, 3.0], [4.0, 27.0])  # unrelated
    cands = detect.link_movers(f, dets)
    assert len(cands) == 1
    c = cands[0]
    assert c["frames"] == frames.tolist() and c["cls"] == "mover"
    assert abs(c["rate"] - rate_pix * f.scale) < 0.3
    assert abs(c["pa"] - 300.0) < 3.0  # west of north: PA = 360 - 60
    assert c["chance"] < 0.05 and "chance" in c["note"]
    assert {"id", "cls", "frames", "ra", "dec", "mjd", "rate", "pa", "known", "note"} <= set(c)


def test_two_detections_or_one_visit_do_not_make_a_candidate():
    f = make_field()
    assert detect.link_movers(f, _mover_dets(f, [2, 4], [5.0, 8.0], [6.0, 8.0])) == []
    f.mjd[3] = f.mjd[2] + 2 / 1440  # same visit as frame 2
    three = _mover_dets(f, [2, 3, 6], [5.0, 5.02, 9.0], [6.0, 6.0, 6.0])
    assert detect.link_movers(f, three) == []


def test_effective_psf():
    s = detect.effective_sigma_pix(7.5, 6.15)
    assert 0.6 < s < 0.9
    assert detect.effective_sigma_pix(float("nan"), 6.15) == s
    assert 0.85 < detect.box_fraction(s) < 1.0
