"""Figures for the ParallaX paper (paper/figures/*.png).

Nothing here alters data: the script re-plots numbers the pipeline already wrote
(data/ledger/*.json, data/science/*.json), re-runs the project's own template code on the
cached Barnard field for the one-pixel spectrum, copies the three-panel residual figure,
and re-arranges the panels of the two quick-look figures with larger labels.

Run (from the repository root, with the pipeline's Python):  python paper/make_figures.py

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "figures"
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

COL = {"naive": "#D55E00", "gated": "#0072B2", "corrected": "#009E73"}
LAB = {"naive": "naive pair", "gated": "gated pair", "corrected": "chromatic template"}
MODES = ("naive", "gated", "corrected")
plt.rcParams.update({
    "font.size": 7.5, "font.family": "DejaVu Sans", "axes.spines.top": False,
    "axes.spines.right": False, "axes.linewidth": 0.6, "xtick.major.width": 0.6,
    "ytick.major.width": 0.6, "savefig.dpi": 300, "legend.frameon": False,
})
FULL, COLW = 7.1, 3.45  # inches: text width and column width


def fig_ledger() -> None:
    led = json.loads((DATA / "ledger" / "barnard.json").read_text())["ledger"]
    fig, axes = plt.subplots(1, 3, figsize=(FULL, 1.82), constrained_layout=True,
                             gridspec_kw={"width_ratios": [1.0, 1.0, 1.0]})
    ax = axes[0]
    x = np.arange(3)
    # falsePlain: one purely statistical sigma for all three; false: each method's own noise
    # model (star-noise term; the template also has its model-error map)
    for k, (key, hatch, lab) in enumerate((("falsePlain", "////", "one statistical sigma for all"),
                                           ("false", "", "each method's noise model"))):
        vals = [led["modes"][m][key]["perDeg2"] for m in MODES]
        bars = ax.bar(x + (k - 0.5) * 0.4, vals, 0.36, color=[COL[m] for m in MODES],
                      hatch=hatch, edgecolor="white", linewidth=0.5,
                      alpha=0.55 if hatch else 1.0)
        for b, v in zip(bars, vals, strict=True):
            ax.annotate(f"{v:.0f}", (b.get_x() + b.get_width() / 2, v), ha="center",
                        va="bottom", fontsize=6.5, xytext=(0, 1.5), textcoords="offset points")
        ax.bar([0], [0], color="#777777", hatch=hatch, edgecolor="white",
               alpha=0.55 if hatch else 1.0, label=lab)
    ax.set_yscale("log")
    ax.set_ylim(60, 60000)
    ax.set_xticks(x, ["naive\npair", "gated\npair", "chromatic\ntemplate"])
    ax.set_ylabel("false detections\nper deg$^2$ per frame")
    ax.legend(fontsize=6.5, loc="upper left", handlelength=1.4, borderaxespad=0.1)
    ax.set_title("(a) false detections, |S/N| > 5", fontsize=7.5, loc="left")
    inj = led["injection"]["atFixedRate"]
    for ax, site, ttl in zip(axes[1:], ("blank", "star"),
                             ("(b) recovery on blank sky", "(c) recovery within 2 px of a star"),
                             strict=True):
        for m in MODES:
            c = inj["modes"][m]["mover"][site]
            ax.plot(inj["fluxUJy"], c["all"], "-o", ms=2.4, lw=1.2, color=COL[m],
                    label=f"{LAB[m]} (S/N > {inj['modes'][m]['threshold']:.1f})")
        ax.axhline(0.5, color="#888888", lw=0.5, ls=":")
        ax.set_xscale("log")
        ax.set_ylim(0, 1.02)
        ax.set_xlabel(r"injected flux ($\mu$Jy)")
        ax.set_title(ttl, fontsize=7.5, loc="left")
    axes[1].set_ylabel("fraction of injected\nsources recovered")
    axes[2].legend(fontsize=6.0, loc="upper left", handlelength=1.4, borderaxespad=0.0)
    fig.savefig(OUT / "fig2_ledger_barnard.png")
    plt.close(fig)


def fig_template_spectrum() -> None:
    from parallax.frames import Field
    from parallax.template import build_template, pixel_spectrum

    led = json.loads((DATA / "ledger" / "barnard.json").read_text())["ledger"]
    y, x = led["spectrumPixel"]["y"], led["spectrumPixel"]["x"]
    f = Field.load(DATA / "cache" / "barnard_field.npz")
    c = int(np.argmax(np.bincount(f.campaign.astype(int))))  # same choice as ledger.fig_spectrum
    own = np.flatnonzero(f.campaign == c)
    tpl = build_template(f, frames=own)
    s = pixel_spectrum(f, tpl, int(own[0]), y, x)
    k = 889.86 / 1000.0  # mJy per pixel for 1 MJy/sr
    fig, ax = plt.subplots(figsize=(COLW, 1.65), constrained_layout=True)
    ax.errorbar(s["lam_ref"], s["flux_ref"] * k, s["err_ref"] * k, fmt="o", ms=2.2, lw=0.5,
                color="#0072B2", label="other passes (reference samples)")
    ax.errorbar(s["lam_own"], s["flux_own"] * k, s["err_own"] * k, fmt="s", ms=2.4, lw=0.5,
                color="#D55E00", mfc="none", mew=0.6, label="this pass (measured)")
    ax.plot(s["lam_own"], s["pred_own"] * k, "-", lw=1.2, color="#009E73",
            label="chromatic template")
    ax.fill_between(s["lam_own"], (s["pred_own"] - s["err_pred"]) * k,
                    (s["pred_own"] + s["err_pred"]) * k, color="#009E73", alpha=0.22, lw=0)
    ax.set_xlabel(r"wavelength ($\mu$m)")
    ax.set_ylabel("flux in one pixel (mJy)")
    ax.legend(fontsize=6.5, loc="upper right")
    fig.savefig(OUT / "fig1_template_spectrum.png")
    plt.close(fig)


def fig_europa_spectrum() -> None:
    rows = json.loads((DATA / "science" / "europa52_comoving_spectrum.json").read_text())
    clean = [r for r in rows if r["n_bad"] == 0]
    print("europa spectrum: points", len(rows), "clean", len(clean))
    okabe = {1: "#0072B2", 2: "#56B4E9", 3: "#009E73", 4: "#E69F00", 5: "#D55E00", 6: "#CC79A7"}
    fig, ax = plt.subplots(figsize=(COLW, 1.58), constrained_layout=True)
    for d in range(1, 7):
        rr = [r for r in clean if r["det"] == d]
        ax.plot([r["lam"] for r in rr], [r["flux_mjy"] for r in rr], "o", ms=2.8,
                color=okabe[d], label=f"D{d}")
    ax.set_yscale("log")
    ax.set_yticks([30, 50, 100, 200, 400], ["30", "50", "100", "200", "400"])
    ax.minorticks_off()
    ax.set_xlabel(r"wavelength ($\mu$m)")
    ax.set_ylabel("flux in 5x5 px box (mJy)")
    ax.legend(fontsize=6.5, ncol=3, loc="upper left", title="detector", title_fontsize=6.5,
              columnspacing=1.0, handletextpad=0.2)
    fig.savefig(OUT / "fig5_europa_spectrum.png")
    plt.close(fig)


def _panels(path: Path) -> list[np.ndarray]:
    """Cut the image panels out of a quick-look figure (dark frames on a white page)."""
    im = np.asarray(Image.open(path).convert("RGB"))
    g = im.mean(axis=2)
    body = g[60:420]
    cols = (body < 250).mean(axis=0) > 0.75
    edges = np.flatnonzero(np.diff(np.concatenate([[0], cols.astype(int), [0]])))
    runs = [(a, b) for a, b in zip(edges[::2], edges[1::2], strict=True) if b - a > 200]
    out = []
    for a, b in runs:
        rows = (g[:, a:b] < 250).mean(axis=1) > 0.75
        r = np.flatnonzero(rows)
        out.append(im[r.min(): r.max() + 1, a:b])
    return out


def fig_movers() -> None:
    eu = _panels(DATA / "figures" / "europa52_quicklook.png")
    pl = _panels(DATA / "figures" / "pluto_quicklook.png")
    assert len(eu) == 4 and len(pl) == 4, (len(eu), len(pl))
    # labels transcribed from the titles of the original quick-look figures
    eu_lab = ["MJD 60907.930, D3, 1.66 $\\mu$m", "MJD 60908.135, D3, 1.82 $\\mu$m",
              "MJD 60908.339, D3, 2.21 $\\mu$m", "MJD 61271.250, D3, 2.04 $\\mu$m\n(a later pass)"]
    pl_lab = ["MJD 60952.184, D2, 1.56 $\\mu$m", "MJD 60954.561, D2, 1.28 $\\mu$m",
              "MJD 60958.569, D2, 1.55 $\\mu$m", "MJD 61157.882, D2, 1.16 $\\mu$m\n(a later pass)"]
    fig, axes = plt.subplots(1, 6, figsize=(FULL, 1.72), constrained_layout=True)
    pans = eu[:3] + pl[:3]
    labs = [s.replace(", D", "\nD") for s in eu_lab[:3] + pl_lab[:3]]
    names = ["(52) Europa\n"] * 3 + ["Pluto\n"] * 3
    for ax, p, lab, name in zip(axes, pans, labs, names, strict=True):
        ax.imshow(p, interpolation="lanczos")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(True)
            sp.set_linewidth(0.5)
        ax.set_title(name + lab, fontsize=6.2, pad=2, linespacing=1.05)
    fig.savefig(OUT / "fig4_movers.png")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DATA / "figures" / "barnard" / "three_panel.png",
                    OUT / "fig3_three_panel_barnard.png")
    fig_ledger()
    fig_europa_spectrum()
    fig_movers()
    fig_template_spectrum()
    print("figures written to", OUT)


if __name__ == "__main__":
    main()







