"""The three-way ledger: naive pair / wavelength-gated pair / chromatic template, measured.

For one field this module runs the three difference modes on the real frames and reports,
for each mode:

* the fraction of frames that get a result at all;
* the median 1-sigma depth of the difference image (microJy per pixel);
* the number of |SNR| > 5 residual detections per frame and per square degree. Away
  from the field's known changing target nothing should change, so these are false
  detections. They are given twice: with the plain statistical sigma, and with the
  star-noise term that ``diffim`` fits for every mode;
* the SNR threshold each mode needs to reach one common false-detection rate, and the
  injection-recovery completeness curve and 50% completeness flux at that threshold
  and at |SNR| > 5;
* whether the known signal of the field is recovered.

``process_field`` returns everything ``export.write_pack`` needs; ``make_figures`` writes
the figures for the paper.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

from . import detect, diffim, inject
from .export import encode_brightness, encode_snr
from .frames import Field
from .targets import TARGETS, Target
from .template import Template, build_template, pixel_spectrum

FIXED_RATE = 0.5  # common false-detection rate, detections per usable frame
TARGET_RADIUS = 14.0  # pixels around the known target left out of the false-detection count
LOBE_RADIUS = 6.0  # pixels around the target searched for its signal
COLOURS = {"naive": "#D55E00", "gated": "#0072B2", "corrected": "#009E73"}  # Okabe-Ito
LABELS = {"naive": "naive pair", "gated": "wavelength-gated pair",
          "corrected": "chromatic template"}


def find_target(f: Field) -> Target | None:
    """The built-in target this field was cut around, if any (centre within 1 arcmin)."""
    for t in TARGETS.values():
        ra, dec = t.centre
        d = np.hypot((ra - f.ra0) * np.cos(np.radians(dec)), dec - f.dec0)
        if d < 1.0 / 60.0:
            return t
    return None


def target_xy(f: Field, target: Target) -> np.ndarray:
    """Pixel position (x, y) of the target in every frame, proper motion applied."""
    year = 2000.0 + (f.mjd - 51544.5) / 365.25
    pos = np.array([target.at(float(y)) for y in year])
    x, y = f.wcs.all_world2pix(pos[:, 0], pos[:, 1], 0)
    return np.column_stack([x, y])


def target_mask(f: Field, target: Target | None, radius: float = TARGET_RADIUS) -> np.ndarray:
    """Boolean cube: pixels within ``radius`` of the known changing target."""
    mask = np.zeros(f.img.shape, dtype=bool)
    if target is None or target.kind == "static":
        return mask
    xy = target_xy(f, target)
    yy, xx = np.mgrid[0: f.n, 0: f.n]
    return np.hypot(xx[None] - xy[:, 0, None, None], yy[None] - xy[:, 1, None, None]) <= radius


def pack_encoding(f: Field) -> tuple[float, float, float]:
    """(soft, lo, hi) exactly as ``export.write_pack`` derives them for the ``img`` section."""
    finite = f.img[np.isfinite(f.img)]
    sigma = np.sqrt(np.nanmedian(f.var.reshape(len(f), -1), axis=1))
    soft = float(max(np.nanmedian(sigma), 1e-4))
    return soft, float(np.arcsinh(np.percentile(finite, 0.01) / soft)), float(
        np.arcsinh(finite.max() / soft))


def area_deg2(f: Field) -> float:
    return float((f.n * f.scale / 3600.0) ** 2)


def _depth(d: diffim.Diff) -> dict:
    """Median 1-sigma of the difference, microJy per pixel: all pixels and faint sky."""
    if not d.usable.any():
        return {"all": None, "faint": None}
    sig = d.sigma[d.usable]
    with np.errstate(all="ignore"):
        faint = np.abs(d.static[d.usable]) < diffim.FAINT_SNR * sig
    return {
        "all": float(np.nanmedian(sig) * diffim.UJY_PER_MJYSR),
        "faint": float(np.nanmedian(sig[faint & np.isfinite(sig)]) * diffim.UJY_PER_MJYSR),
    }


def _rates(f: Field, d: diffim.Diff, exclude: np.ndarray) -> dict:
    per_frame = inject.detection_rate(d, detect.THRESH, exclude)
    free = 1.0 - float(exclude.mean())
    z = d.snr[d.usable]
    ok = np.isfinite(z) & ~exclude[d.usable]
    return {
        "perFrame": per_frame,
        "perDeg2": per_frame / (area_deg2(f) * free) if np.isfinite(per_frame) else None,
        "pixelFraction": float(np.mean(np.abs(z[ok]) > detect.THRESH)) if ok.any() else None,
    }


def known_signal(f: Field, d: diffim.Diff, target: Target | None,
                 dets: list[detect.Detection]) -> dict:
    """Is the field's known change seen? Measured at the target's predicted position."""
    if target is None or target.kind == "static" or not d.usable.any():
        return {"kind": None}
    xy = target_xy(f, target)
    yy, xx = np.mgrid[0: f.n, 0: f.n]
    pos, neg = [], []
    for i in np.flatnonzero(d.usable):
        near = np.hypot(xx - xy[i, 0], yy - xy[i, 1]) <= LOBE_RADIUS
        z = d.snr[i][near]
        z = z[np.isfinite(z)]
        if z.size:
            pos.append(float(z.max()))
            neg.append(float(z.min()))
    pos, neg = np.array(pos), np.array(neg)
    cls = {}
    for q in dets:
        if np.hypot(q.x - xy[q.frame, 0], q.y - xy[q.frame, 1]) <= LOBE_RADIUS + 2:
            cls.setdefault(q.cls, set()).add(q.frame)
    n = max(int(d.usable.sum()), 1)
    out = {
        "kind": target.kind, "target": target.name, "framesMeasured": len(pos),
        "medianPositiveSNR": float(np.median(pos)) if len(pos) else None,
        "medianNegativeSNR": float(np.median(neg)) if len(neg) else None,
        "fractionBothLobes5": float(np.mean((pos >= 5) & (neg <= -5))) if len(pos) else None,
        "fractionAnyLobe5": float(np.mean((pos >= 5) | (neg <= -5))) if len(pos) else None,
        "fractionFramesByClass": {k: round(len(v) / n, 3) for k, v in sorted(cls.items())},
    }
    want = "motion-dipole" if target.kind == "motion" else "variable"
    out["recovered"] = bool(out["fractionFramesByClass"].get(want, 0.0) >= 0.25)
    return out


def _mode_entry(f, d, plain, exclude, target, dets) -> dict:
    far = [q for q in dets if not exclude[q.frame, round(q.y), round(q.x)]]
    nu = max(int(d.usable.sum()), 1)
    by_cls = Counter(q.cls for q in far)
    gains = d.info.get("star_gain", {})
    return {
        "usableFraction": float(d.usable.mean()),
        "usableFrames": int(d.usable.sum()),
        "depthUJy": _depth(d),
        "depthPlainUJy": _depth(plain),
        "false": _rates(f, d, exclude),
        "falsePlain": _rates(f, plain, exclude),
        "detectionsByClassPerFrame": {k: round(v / nu, 4) for k, v in sorted(by_cls.items())},
        "starNoiseGain": {str(k): round(float(v), 4) for k, v in gains.items()},
        "knownSignal": known_signal(f, d, target, dets),
    }


def compute_ledger(f: Field, tpl: Template | None = None,
                   diffs: dict[str, diffim.Diff] | None = None,
                   detections: dict[str, list[detect.Detection]] | None = None,
                   target: Target | None = None, with_injection: bool = True,
                   fixed_rate: float = FIXED_RATE, seed: int = 20261113) -> dict:
    """The JSON-safe ``ledger`` block of the data pack for field ``f``."""
    tpl = tpl or build_template(f)
    target = target or find_target(f)
    exclude = target_mask(f, target)
    diffs = diffs or diffim.all_modes(f, tpl, exclude=exclude)
    plain = diffim.all_modes(f, tpl, star_noise=False)
    detections = detections or {m: detect.detect(f, d) for m, d in diffs.items()}
    out: dict = {
        "nFrames": len(f), "nPasses": len(np.unique(f.campaign)),
        "templateMode": tpl.mode, "areaDeg2": area_deg2(f), "threshold": detect.THRESH,
        "minAreaPix": detect.MIN_AREA, "fixedRatePerFrame": fixed_rate,
        "target": target.name if target else None,
        "excludedRadiusPix": TARGET_RADIUS if exclude.any() else 0.0,
        "gate": diffim.GATE,
        "modes": {m: _mode_entry(f, diffs[m], plain[m], exclude, target, detections[m])
                  for m in diffs},
        "notes": [
            "false = detections per usable frame outside the excluded radius around the "
            "target; falsePlain uses the plain statistical sigma (no star-noise term).",
            "depth = median 1-sigma of the difference image in microJy per 6.15 arcsec pixel.",
            "completeness: fraction of injected point sources recovered; 'all' counts frames "
            "without a result as misses, 'searchable' leaves them out.",
        ],
    }
    if tpl.mode != "cross-pass":
        out["notes"].append(
            "single survey pass: the template is leave-one-visit-out within the pass, so "
            "only changes faster than the pass are visible; pair modes have no partner.")
    if with_injection:
        thr = {m: inject.threshold_for_rate(d, fixed_rate, exclude) for m, d in diffs.items()}
        out["injection"] = {
            "atThreshold5": inject.injection_recovery(f, diffs, tpl.pred, exclude=exclude,
                                                      seed=seed),
            "atFixedRate": inject.injection_recovery(f, diffs, tpl.pred, thresholds=thr,
                                                     exclude=exclude, seed=seed),
        }
        for m in diffs:
            out["modes"][m]["thresholdAtFixedRate"] = (
                round(thr[m], 2) if np.isfinite(thr[m]) else None)
    return out


def process_field(f: Field, with_injection: bool = True) -> dict:
    """Everything ``export.write_pack`` needs from the differencing for field ``f``.

    Returns ``extra_sections`` (tpl, snrCorr, snrNaive, snrGated, already encoded),
    ``frame_extras`` (naivePartner, gatedPartner, nRef) and ``blocks`` (detections,
    candidates, ledger), plus the in-memory products under ``products`` for figures.
    """
    tpl = build_template(f)
    # the known target's own change must not be fitted away as star noise
    diffs = diffim.all_modes(f, tpl, exclude=target_mask(f, find_target(f)))
    dets = {m: detect.detect(f, d) for m, d in diffs.items()}
    led = compute_ledger(f, tpl, diffs, dets, with_injection=with_injection)
    soft, lo, hi = pack_encoding(f)
    corr = dets["corrected"]
    return {
        "extra_sections": {
            "tpl": encode_brightness(tpl.pred, soft, lo, hi),
            "snrCorr": encode_snr(diffs["corrected"].snr),
            "snrNaive": encode_snr(diffs["naive"].snr),
            "snrGated": encode_snr(diffs["gated"].snr),
        },
        "frame_extras": {
            "naivePartner": diffs["naive"].partner.tolist(),
            "gatedPartner": diffs["gated"].partner.tolist(),
            "nRef": [round(float(v), 1) for v in tpl.n_ref_per_frame()],
        },
        "blocks": {
            "detections": [q.to_json() for q in corr],
            "candidates": detect.candidates(f, corr),
            "ledger": led,
        },
        "products": {"template": tpl, "diffs": diffs, "detections": dets},
    }


# ----------------------------------------------------------------------------- figures


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.8, "savefig.dpi": 200, "savefig.bbox": "tight",
    })
    return plt


def figure_frame(diffs: dict[str, diffim.Diff]) -> int | None:
    """A typical frame usable in all modes: the median naive wavelength mismatch."""
    both = np.flatnonzero(np.all([d.usable for d in diffs.values()], axis=0))
    if len(both) == 0:
        return None
    mism = diffs["naive"].mismatch[both]
    with np.errstate(all="ignore"):
        m = np.nanmedian(np.abs(mism).reshape(len(both), -1), axis=1)
    return int(both[np.argsort(m)[len(both) // 2]])


def fig_three_panel(f: Field, diffs, frame: int, path: Path) -> None:
    plt = _plt()
    half = f.n * f.scale / 120.0
    fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.5), sharey=True, constrained_layout=True)
    cmap = plt.get_cmap("RdBu_r").with_extremes(bad="#bdbdbd")
    for ax, m in zip(axes, diffim.MODES, strict=True):
        im = ax.imshow(diffs[m].snr[frame], origin="lower", cmap=cmap, vmin=-8, vmax=8,
                       extent=[half, -half, -half, half], interpolation="nearest")
        ax.set_xlabel(f"{LABELS[m]}: east offset (arcmin)")
    axes[0].set_ylabel("north offset (arcmin)")
    fig.colorbar(im, ax=axes, shrink=0.85, label="residual / sigma")
    fig.savefig(path)
    plt.close(fig)


def fig_false_detections(led: dict, path: Path) -> None:
    plt = _plt()
    modes = [m for m in diffim.MODES if m in led["modes"]]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    x = np.arange(len(modes))
    for k, (key, hatch, lab) in enumerate((("falsePlain", "//", "plain statistical sigma"),
                                           ("false", "", "with fitted star-noise term"))):
        vals = [led["modes"][m][key]["perDeg2"] or 0.0 for m in modes]
        bars = ax.bar(x + (k - 0.5) * 0.38, vals, 0.34, color=[COLOURS[m] for m in modes],
                      hatch=hatch, edgecolor="white", linewidth=0.8,
                      alpha=0.55 if hatch else 1.0)
        for b, v in zip(bars, vals, strict=True):
            ax.annotate(f"{v:.0f}", (b.get_x() + b.get_width() / 2, v), ha="center",
                        va="bottom", fontsize=8, xytext=(0, 2), textcoords="offset points")
        ax.bar([0], [0], color="#777777", hatch=hatch, edgecolor="white",
               alpha=0.55 if hatch else 1.0, label=lab)
    ax.set_yscale("log")
    ax.set_xticks(x, [LABELS[m] for m in modes])
    ax.set_ylabel("false detections, |SNR| > 5 (per square degree per frame)")
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(path)
    plt.close(fig)


def fig_completeness(led: dict, path: Path, which: str = "atFixedRate") -> None:
    plt = _plt()
    inj = led["injection"][which]
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.3), sharey=True, constrained_layout=True)
    for ax, site, lab in zip(axes, ("blank", "star"), ("blank sky", "within 2 px of a star"),
                             strict=True):
        for m in diffim.MODES:
            c = inj["modes"].get(m, {}).get("mover")
            if not c:
                continue
            ax.plot(inj["fluxUJy"], c[site]["all"], "-o", ms=3.5, lw=1.8, color=COLOURS[m],
                    label=f"{LABELS[m]} (SNR > {inj['modes'][m]['threshold']:.1f})")
        ax.axhline(0.5, color="#999999", lw=0.6, ls=":")
        ax.set_xscale("log")
        ax.set_xlabel(f"injected flux (microJy), {lab}")
    axes[0].set_ylabel("fraction of injected sources recovered")
    axes[0].set_ylim(0, 1.02)
    axes[0].legend(frameon=False, fontsize=7.5, loc="upper left")
    fig.savefig(path)
    plt.close(fig)


def spectrum_pixel(f: Field, tpl: Template, exclude: np.ndarray) -> tuple[int, int] | None:
    """Brightest pixel that is never missing and lies outside the excluded region."""
    ok = (np.isfinite(f.img).mean(axis=0) > 0.97) & (np.isfinite(tpl.pred).mean(axis=0) > 0.9)
    ok &= ~exclude.any(axis=0)
    if not ok.any():
        return None
    with np.errstate(all="ignore"):
        med = np.where(ok, np.nanmedian(f.img, axis=0), -np.inf)
    y, x = np.unravel_index(int(np.argmax(med)), med.shape)
    return int(y), int(x)


def fig_spectrum(f: Field, tpl: Template, y: int, x: int, path: Path) -> None:
    plt = _plt()
    t = int(np.argmax(np.bincount(f.campaign.astype(int))))  # a frame of the largest pass
    t = int(np.flatnonzero(f.campaign == t)[0])
    s = pixel_spectrum(f, tpl, t, y, x)
    k = diffim.UJY_PER_MJYSR / 1000.0  # mJy per pixel
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    ax.errorbar(s["lam_ref"], s["flux_ref"] * k, s["err_ref"] * k, fmt="o", ms=3.5, lw=0.8,
                color="#0072B2", label="other passes (reference samples)")
    ax.errorbar(s["lam_own"], s["flux_own"] * k, s["err_own"] * k, fmt="s", ms=3.5, lw=0.8,
                color="#D55E00", mfc="none", label="this pass (measured)")
    ax.plot(s["lam_own"], s["pred_own"] * k, "-", lw=1.6, color="#009E73",
            label="chromatic template at this pass's wavelengths")
    ax.fill_between(s["lam_own"], (s["pred_own"] - s["err_pred"]) * k,
                    (s["pred_own"] + s["err_pred"]) * k, color="#009E73", alpha=0.2, lw=0)
    ax.set_xlabel("wavelength (micron)")
    ax.set_ylabel("flux in one pixel (mJy)")
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(path)
    plt.close(fig)


def make_figures(f: Field, tpl: Template, diffs: dict[str, diffim.Diff], led: dict,
                 outdir: Path) -> dict[str, str]:
    """Write the paper figures (PNG, 200 dpi) into ``outdir``; returns name -> path."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    made: dict[str, str] = {}
    frame = figure_frame(diffs)
    if frame is not None:
        fig_three_panel(f, diffs, frame, outdir / "three_panel.png")
        made["three_panel"] = str(outdir / "three_panel.png")
        led["figureFrame"] = frame
    fig_false_detections(led, outdir / "false_detections.png")
    made["false_detections"] = str(outdir / "false_detections.png")
    if "injection" in led:
        for which, name in (("atFixedRate", "completeness"), ("atThreshold5", "completeness_snr5")):
            fig_completeness(led, outdir / f"{name}.png", which)
            made[name] = str(outdir / f"{name}.png")
    pix = spectrum_pixel(f, tpl, target_mask(f, find_target(f)))
    if pix is not None:
        fig_spectrum(f, tpl, pix[0], pix[1], outdir / "template_spectrum.png")
        made["template_spectrum"] = str(outdir / "template_spectrum.png")
        led["spectrumPixel"] = {"x": pix[1], "y": pix[0]}
    return made
