"""Chromatic template on a synthetic field with a known spectrum in every pixel.

The synthetic field built here is also imported by the other differencing tests.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import time

import numpy as np

from parallax import diffim
from parallax.frames import BAD_SOFT, Field, bitmask
from parallax.template import (
    CROSS_PASS,
    LEAVE_VISIT_OUT,
    build_template,
    pixel_spectrum,
    reference_frames,
)

NOISE = 0.01  # MJy/sr per pixel
BW = 0.03  # micron
PSF_SIGMA = 0.9  # pixels
# (x, y, amplitude MJy/sr, spectral slope, absorption depth, absorption centre)
STARS = [
    (8.0, 9.0, 3.0, 3.5, 0.0, 1.3),
    (21.3, 7.6, 2.0, -3.0, 0.4, 1.35),
    (11.5, 22.2, 4.0, 1.5, 0.5, 1.25),
    (23.0, 23.0, 1.0, -4.0, 0.0, 1.3),
]


def star_image(n, x, y, amp, lam, slope, depth, centre):
    """A Gaussian star whose brightness follows a known spectrum at per-pixel wavelength."""
    gy, gx = np.mgrid[0:n, 0:n]
    sed = (lam / 1.3) ** slope * (1.0 - depth * np.exp(-0.5 * ((lam - centre) / 0.05) ** 2))
    return amp * sed * np.exp(-0.5 * ((gx - x) ** 2 + (gy - y) ** 2) / PSF_SIGMA**2)


def make_field(n: int = 31, per_pass: int = 40, passes: int = 2, seed: int = 1,
               moved: bool = False, variable: bool = False, noise: float = NOISE,
               jitter: float = 0.0) -> Field:
    """Static stars with known spectra, seen at different wavelengths in each pass.

    ``moved`` shifts star 0 by 1.5 px in the passes after the first; ``variable`` makes
    star 3 brighter by 60% there. Pass k observes wavelengths offset by k half-steps and
    in reversed time order, so that the frame nearest in time is far away in wavelength.
    ``jitter`` (pixels, rms) shifts all stars by a random sub-pixel offset per frame, which
    mimics the pixel-phase noise of undersampled images.
    """
    rng = np.random.default_rng(seed)
    step = 0.4 / (per_pass - 1)
    gy = np.mgrid[0:n, 0:n][0]
    img, lam, mjd, camp = [], [], [], []
    for c in range(passes):
        lam0 = 1.15 + step * np.arange(per_pass) + 0.5 * step * c
        if c % 2:
            lam0 = lam0[::-1]
        for i in range(per_pass):
            lam_px = lam0[i] + 0.0003 * (gy - (n - 1) / 2)
            im = np.zeros((n, n))
            jx, jy = rng.normal(0, jitter, 2) if jitter else (0.0, 0.0)
            for k, (x, y, amp, slope, depth, centre) in enumerate(STARS):
                dx = 1.5 if (moved and k == 0 and c > 0) else 0.0
                boost = 1.6 if (variable and k == 3 and c > 0) else 1.0
                im += star_image(n, x + dx + jx, y + jy, amp * boost, lam_px, slope, depth,
                                 centre)
            img.append(im + rng.normal(0, noise, (n, n)))
            lam.append(lam_px)
            mjd.append(61000.0 + 180.0 * c + 0.07 * i)
            camp.append(c)
    nf = len(img)
    return Field(
        ra0=150.0, dec0=20.0, n=n, scale=6.15,
        img=np.array(img, dtype=np.float32), var=np.full((nf, n, n), noise**2, np.float32),
        lam=np.array(lam, dtype=np.float32), bw=np.full((nf, n, n), BW, np.float32),
        flags=np.zeros((nf, n, n), np.int32), mjd=np.array(mjd),
        det=np.full(nf, 2, np.int16), campaign=np.array(camp, dtype=np.int16),
        sky=np.zeros(nf), zodi=np.zeros(nf), psf_fwhm=np.full(nf, 7.5),
        sc_xyz=np.zeros((nf, 3)), names=[f"f{i}" for i in range(nf)],
        obsid=[""] * nf, collection=["synthetic"] * nf,
    )


def star_pixels(f: Field) -> np.ndarray:
    """Mask (n, n) of pixels within 1.5 px of a synthetic star."""
    gy, gx = np.mgrid[0: f.n, 0: f.n]
    return np.any([np.hypot(gx - s[0], gy - s[1]) < 1.5 for s in STARS], axis=0)


def test_template_removes_chromatic_difference_that_naive_leaves():
    f = make_field()
    tpl = build_template(f)
    assert tpl.mode == CROSS_PASS
    stars = star_pixels(f)
    inner = (f.lam0 > 1.18) & (f.lam0 < 1.52)  # away from the ends of the band
    corrected = (f.img - tpl.pred)[:, stars]
    naive = diffim.naive_diff(f, star_noise=False, rescale=False, match_background=False)
    assert naive.usable.all()
    rms_corr = float(np.sqrt(np.nanmean(corrected[inner] ** 2)))
    rms_naive = float(np.sqrt(np.nanmean(naive.resid[inner][:, stars] ** 2)))
    assert rms_naive > 20 * NOISE  # colour masquerades as change
    assert rms_corr < 2 * NOISE  # the template follows the spectrum down to the noise
    assert rms_naive > 15 * rms_corr
    # at the ends of the band the fit is one-sided: a few percent of the star, no more
    assert float(np.sqrt(np.nanmean(corrected**2))) < 0.02 * max(s[2] for s in STARS)
    # interior wavelengths: the residual is consistent with the quoted uncertainty
    z = (f.img - tpl.pred)[inner] / np.sqrt(f.var + tpl.var + tpl.model_err**2)[inner]
    assert 0.8 < np.nanstd(z[:, ~stars]) < 1.2
    assert np.nanmean(np.abs(z[:, stars]) > 5) < 0.01


def test_template_uses_only_other_passes():
    f = make_field(passes=3, per_pass=20)
    for t in (0, 25, 59):
        refs = reference_frames(f, t)
        assert len(refs) == 40
        assert (f.campaign[refs] != f.campaign[t]).all()


def test_outlier_in_a_reference_frame_is_rejected():
    f = make_field()
    y, x = 15, 15  # blank sky
    hit = 50  # a frame of pass 1
    f.img[hit, y, x] += 500 * NOISE  # unflagged cosmic ray
    tpl = build_template(f)
    targets = np.flatnonzero(f.campaign == 0)
    assert np.nanmax(np.abs(tpl.pred[targets, y, x])) < 5 * NOISE
    plain = build_template(f, robust=False)
    assert np.nanmax(np.abs(plain.pred[targets, y, x])) > 20 * NOISE


def test_flagged_and_nan_reference_pixels_are_excluded():
    f = make_field()
    f.img[45, 16, 16] = 99.0  # blank sky
    f.flags[45, 16, 16] = bitmask("TRANSIENT")
    assert f.flags[45, 16, 16] & BAD_SOFT
    f.img[46, 15, 17] = np.nan
    tpl = build_template(f, robust=False)  # the flag alone must keep it out
    targets = np.flatnonzero(f.campaign == 0)
    assert np.nanmax(np.abs(tpl.pred[targets, 16, 16])) < 5 * NOISE
    assert np.isfinite(tpl.pred[targets, 15, 17]).mean() > 0.9


def test_no_prediction_without_references_in_wavelength():
    f = make_field()
    f.lam[f.campaign == 1] += 1.0  # the other pass saw a completely different band
    tpl = build_template(f)
    assert not np.isfinite(tpl.pred).any()
    assert not tpl.usable().any()
    assert (tpl.n_ref_per_frame() == 0).all()


def test_single_pass_falls_back_to_leave_one_visit_out():
    f = make_field(passes=1)
    tpl = build_template(f)
    assert tpl.mode == LEAVE_VISIT_OUT
    assert 0 not in reference_frames(f, 0)
    assert np.isfinite(tpl.pred).mean() > 0.9


def test_model_error_grows_where_the_fit_cannot_follow():
    f = make_field()
    rng = np.random.default_rng(5)
    y, x = 9, 8  # core of star 0: add frame-to-frame scatter like pixel-phase noise
    f.img[:, y, x] *= 1.0 + 0.2 * rng.normal(size=len(f))
    tpl = build_template(f)
    core = np.nanmedian(tpl.model_err[:, y, x])
    sky = np.nanmedian(tpl.model_err[:, 15, 15])
    assert core > 10 * NOISE
    assert sky < NOISE


def test_change_between_reference_passes_does_not_hide_itself():
    f = make_field(passes=3, per_pass=24, variable=True)  # star 3: 1.0, 1.6, 1.6
    y, x = round(STARS[3][1]), round(STARS[3][0])
    target = np.flatnonzero(f.campaign == 1)  # references: one faint pass, one bright
    within = build_template(f, frames=target)
    pooled = build_template(f, frames=target, within_pass=False)
    m_within = np.nanmedian(within.model_err[target, y, x])
    m_pooled = np.nanmedian(pooled.model_err[target, y, x])
    assert m_pooled > 0.1 * STARS[3][2]  # the 60% change counted as "scatter"
    assert m_within < 0.2 * m_pooled
    resid = np.nanmedian((f.img - within.pred)[target, y, x])
    assert resid > 0.15 * STARS[3][2]  # brighter than the mean of the other passes


def test_pixel_spectrum_and_speed():
    f = make_field()
    t0 = time.time()
    tpl = build_template(f)
    assert time.time() - t0 < 20
    s = pixel_spectrum(f, tpl, 0, 9, 8)
    assert len(s["lam_ref"]) == 40 and len(s["lam_own"]) == 40
    assert np.all(np.diff(s["lam_own"]) > 0)
