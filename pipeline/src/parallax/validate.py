"""Run the right measurement for each built-in target and compare with ground truth.

``validate_target`` returns the JSON-safe ``science`` block of the data pack:

    {"motion": {...}, "lightcurve": {...}, "spectrum": {...}, "notes": [...], "verdict": "..."}

and writes the paper figures (PNG, 200 dpi, Okabe-Ito colour-blind-safe palette) to
``data/figures/<key>/``. Moving targets get per-pass positions and a proper motion
against the catalogue; variable stars get a per-wavelength light curve and a ratio
spectrum; every target gets its spectrum by survey pass.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import lightcurve as lc
from . import motion as mo
from . import photometry as ph
from .frames import Field, build_field
from .targets import TARGETS, Target

ROOT = Path(__file__).resolve().parents[3]
MIN_FILES = 20
USER_AGENT = "ParallaX-SpaceApps2026/1.0"
# Okabe-Ito palette (colour-blind safe).
COLOURS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#000000"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X"]
KNOWN_PERIOD_DAYS = {"rdra": (245.6, "AAVSO VSX catalogue value")}
LONG_PASS_DAYS = 60.0  # a "pass" longer than this is really continuous coverage


# ------------------------------------------------------------------------ utilities


def json_safe(o):
    """Numpy to plain Python; NaN and infinities become None; floats keep 6 significant digits."""
    if isinstance(o, dict):
        return {str(k): json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    if isinstance(o, np.ndarray):
        return json_safe(o.tolist())
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return float(f"{f:.6g}") if np.isfinite(f) else None
    return o


def raw_count(key: str) -> int:
    return len(list((ROOT / "data" / "raw" / key).glob("*.fits")))


def load_field(key: str, rebuild: bool = False) -> Field | None:
    """Aligned cube of a built-in target, cached in ``data/cache`` (same convention as
    ``scripts/run_ledger.py``: rebuilt when the number of raw files changed)."""
    nfiles = raw_count(key)
    if nfiles < MIN_FILES:
        return None
    cache = ROOT / "data" / "cache" / f"{key}_field.npz"
    stamp = cache.with_suffix(".count")
    if cache.exists() and not rebuild and stamp.exists() and stamp.read_text() == str(nfiles):
        return Field.load(cache)
    t = TARGETS[key]
    f = build_field(ROOT / "data" / "raw" / key, *t.centre, t.size_pix)
    cache.parent.mkdir(parents=True, exist_ok=True)
    f.save(cache)
    stamp.write_text(str(nfiles))
    return f


def pass_table(field: Field) -> list[dict]:
    from astropy.time import Time

    out = []
    for c in range(int(field.campaign.max()) + 1):
        m = field.mjd[field.campaign == c]
        out.append({"index": c, "start": Time(m.min(), format="mjd").isot[:10],
                    "end": Time(m.max(), format="mjd").isot[:10], "nFrames": len(m),
                    "spanDays": float(np.ptp(m)), "mjd": float(m.mean()),
                    "perDetector": [int(((field.campaign == c) & (field.det == d)).sum())
                                    for d in range(1, 7)]})
    return out


def fetch_vsx(name: str) -> dict | None:
    """Period and epoch of maximum from the AAVSO VSX (cached on disk; None if offline)."""
    cache = ROOT / "data" / "cache" / f"vsx_{name.replace(' ', '_')}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    try:
        import httpx

        r = httpx.get("https://www.aavso.org/vsx/index.php",
                      params={"view": "api.object", "ident": name, "format": "json"},
                      headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True)
        r.raise_for_status()
        obj = r.json().get("VSXObject", {})
    except Exception:
        return None
    if not obj:
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(obj))
    return obj


# ------------------------------------------------------------------------- spectrum


def _spectrum_rows(spec: list[dict]) -> list[dict]:
    rows = []
    for s in spec:
        keep = s["n"] > 0
        rows.append({"pass": s["group"], "mjd": s["mjd"], "nFrames": s["n_frames"],
                     "lam": s["lam"][keep], "fluxUJy": s["value"][keep],
                     "errUJy": s["err"][keep], "n": s["n"][keep], "det": s["det"][keep]})
    return rows


def spectrum_block(phot: ph.Photometry, which: str, groups: np.ndarray | None = None) -> dict:
    """Spectrum by survey pass on the 102-channel grid and on a regular R = 40 grid."""
    label = {"flux": f"aperture, radius {phot.r_ap:g} pixels",
             "psf": "PSF-weighted (Gaussian)",
             "wing": f"wing ring {phot.wing[0]:g}-{phot.wing[1]:g} pixels (relative only)"}[which]
    return {
        "which": which, "measurement": label, "unit": "microJy",
        "absolute": which != "wing",
        "channels": _spectrum_rows(ph.spectra_by_group(phot, groups, ph.channel_grid(), which)),
        "r40": _spectrum_rows(ph.spectra_by_group(phot, groups, ph.regular_grid(40.0), which)),
        "quality": ph.quality_report(phot),
    }


# --------------------------------------------------------------------------- motion


def _track_radec(field: Field, target: Target, positions: list[dict]) -> tuple:
    """Per-frame sky position: the measured pass position, else the catalogue track."""
    plx = mo.PARALLAX_MAS.get(target.key, (0.0, ""))[0]
    ce, cn = mo.catalogue_track(field, target, field.mjd, plx)
    x, y = mo.offsets_to_xy(field, ce, cn)
    for p in positions:
        sel = field.campaign == p["pass"]
        x[sel], y[sel] = p["x"], p["y"]
    return field.wcs.all_pix2world(x, y, 0)


def validate_motion(key: str, field: Field) -> dict:
    target = TARGETS[key]
    notes: list[str] = []
    if key == "wise0855":
        motion = mo.faint_detection(field, target, null_test=True)
        motion["mode"] = "faint"
        nt = motion.get("nullTest")
        if nt and "pFixed" in nt:
            notes.append(
                f"The combined statistic ({nt['best']:.1f}; {nt['atTrack']:.1f} at the catalogue "
                "position without a search) is not a Gaussian sigma: on random tracks in the "
                f"same maps it scatters by {nt['fixedStd']:.2f}. Empirical false-alarm "
                f"probability: {nt['fixedExceed']} of {nt['nFixed']} random tracks reach the "
                f"value at the catalogue position, {nt.get('searchExceed', 0)} of "
                f"{nt.get('nSearch', 0)} reach the maximum of the {nt['searchRadiusPix']:.0f}-pixel "
                f"zero-point search. Reversed track: {nt['reversedTrack']:.1f}.")
        positions = motion.get("track") or []
        which = "psf"
    else:
        motion = mo.measure_motion(field, target)
        motion["mode"] = "bright"
        positions = motion["perPass"]
        which = "wing" if motion["saturatedCore"] else "flux"
    ra, dec = _track_radec(field, target, positions)
    phot = ph.photometry(field, ra, dec)
    if which == "flux" and phot.good(ph.SUSPECT).mean() < 0.3:
        which = "wing"
    spectrum = spectrum_block(phot, which)
    if key == "wise0855" and motion.get("detected"):
        spectrum["coarse"] = _faint_spectrum(phot)
        blue = spectrum["coarse"]["det"] <= 3
        if blue.any():
            f, e, _ = ph.combine(spectrum["coarse"]["fluxUJy"][blue], spectrum["coarse"]["errUJy"][blue])
            motion["staticNeighbourUJy"] = {"flux": f, "err": e, "band": "0.74-2.4 micron"}
            if e > 0 and f / e > 3:
                notes.append(
                    f"A static source of {f:.0f} +- {e:.0f} microJy at 0.74-2.4 micron lies "
                    "within the PSF of the track (the target itself is dark there). It inflates "
                    "the direct-stack flux and S/N and dilutes stack centroids; only the "
                    "moving-source numbers (pass differences, joint fit) describe the target.")
    notes.extend(motion.get("notes", []))
    if which == "wing":
        notes.append("Spectrum from the unsaturated wings (ring medians): correct shape "
                     "between passes at one wavelength, but not an absolute flux.")
    return {"motion": motion, "spectrum": spectrum, "notes": notes, "_phot": phot}


def _faint_spectrum(phot: ph.Photometry) -> dict:
    """All passes together, six bins per detector: the only way a 0.4 mJy source shows a spectrum."""
    v, e, ok = phot.values("psf")
    ok = ok | ((phot.quality <= ph.SUSPECT) & np.isfinite(v))
    b = ph.bin_values(phot.lam[ok], phot.det[ok], v[ok], e[ok], ph.channel_grid(6))
    keep = b["n"] > 0
    return {"lam": b["lam"][keep], "fluxUJy": b["value"][keep], "errUJy": b["err"][keep],
            "n": b["n"][keep], "det": b["det"][keep]}


# ------------------------------------------------------------------------ variables


def _refine_centre(field: Field, target: Target) -> tuple[float, float, float]:
    """Sky position of the star in the all-frame stack (falls back to the catalogue)."""
    img, var, _ = mo.stack_frames(field.img, field.var, grow=0)
    x0, y0 = ph.pixel_xy(field, target.ra, target.dec)
    f = mo.fit_centre(img, var, float(x0), float(y0), radius=9.0, max_shift=2.0)
    if f is None:
        return target.ra, target.dec, 0.0
    ra, dec = field.wcs.all_pix2world(f.x, f.y, 0)
    return float(ra), float(dec), float(np.hypot(f.x - x0, f.y - y0) * field.scale)


def _wing_radii(field: Field, hole95: float) -> tuple[tuple[float, float], tuple[float, float]]:
    r_in = max(4.0, np.ceil(hole95) + 2.0)
    far = min(r_in + 10.0, field.n / 2 - 8.0)
    return (r_in, r_in + 3.0), (far, far + 5.0)


def _ratio_rows(r: dict) -> list[dict]:
    keys = ("group", "mjd", "nFrames", "lam", "det", "n", "ratio", "ratioErr", "dmag", "dmagErr",
            "meanDmag", "meanDmagErr", "perDetector", "slopeMagPerMicron", "slopeErr")
    return [{k: g[k] for k in keys} for g in r["groups"]]


def _analysis(phot: ph.Photometry, groups: np.ndarray, which: str) -> dict:
    ratio = lc.ratio_spectrum(phot, groups, which=which)
    curves = lc.lightcurve_by_wavelength(phot, groups, which=which)
    return {"which": which, "ref": ratio["ref"], "refMjd": ratio.get("refMjd"),
            "ratio": _ratio_rows(ratio),
            "byWavelength": [{k: c[k] for k in ("lam", "lamLo", "lamHi", "det", "group", "mjd",
                                               "flux", "err", "mag", "magErr", "n")}
                             for c in curves]}


def _control_star(field: Field, target_xy: tuple[float, float], groups: np.ndarray) -> dict | None:
    """The same ratio analysis on a constant-looking field star: the calibration floor."""
    img, var, _ = mo.stack_frames(field.img, field.var, grow=0)
    refs = mo.find_reference_stars(img, var, target_xy, avoid_r=12.0, edge=9, min_snr=30.0)
    for x, y in refs[:3]:
        ra, dec = field.wcs.all_pix2world(x, y, 0)
        p = ph.photometry(field, float(ra), float(dec))
        if p.good(ph.SUSPECT).mean() < 0.6:
            continue
        r = lc.ratio_spectrum(p, groups, which="flux")
        if not r["groups"]:
            continue
        d = np.array([g["meanDmag"] for g in r["groups"]])
        return {"x": x, "y": y, "medianFluxUJy": float(np.nanmedian(p.flux[p.good(ph.SUSPECT)])),
                "meanDmag": d, "meanDmagErr": [g["meanDmagErr"] for g in r["groups"]],
                "group": [g["group"] for g in r["groups"]], "ref": r["ref"],
                "mjd": [g["mjd"] for g in r["groups"]],
                "rmsDmag": float(np.sqrt(np.nanmean(d**2)))}
    return None


def _period_block(key: str, name: str, phot: ph.Photometry, which: str) -> dict | None:
    if key not in KNOWN_PERIOD_DAYS:
        return None
    period, source = KNOWN_PERIOD_DAYS[key]
    vsx = fetch_vsx(name)
    epoch = None
    if vsx:
        try:
            period = float(vsx.get("Period", period))
            epoch = float(vsx["Epoch"]) - 2400000.5  # JD to MJD
            source = "AAVSO VSX (online)"
        except (KeyError, TypeError, ValueError):
            epoch = None
    curves = lc.lightcurve_by_wavelength(phot, lc.epoch_groups(phot.mjd, 5.0), which=which,
                                         min_groups=5)
    out = lc.phase_analysis(curves, period, epoch_max=epoch)
    out.update(source=source, epochMaxMjd=epoch, binDays=5.0,
               spanDays=float(np.ptp(phot.mjd)), cycles=float(np.ptp(phot.mjd) / period))
    # No detector is excluded: every wavelength bin that is sampled well enough counts.
    out["excludedDetectors"] = []
    out["byDetector"] = {
        str(d): {"significant": sum(1 for r in out["bins"] if r["det"] == d
                                    and r["significance"] >= 3.0),
                 "bins": sum(1 for r in out["bins"] if r["det"] == d)}
        for d in sorted({r["det"] for r in out["bins"]})}
    trial = np.arange(120.0, 500.1, 2.0)
    chi, scans, spans = np.zeros_like(trial), [], []
    for c in curves:
        if len(c["mjd"]) >= 6 and np.ptp(c["mjd"]) >= 0.6 * period:
            s = lc.period_scan(c["mjd"], c["mag"], c["magErr"], trial)
            if np.isfinite(s["chi2"]).all():
                chi += s["chi2"]
                scans.append(s["chi2"])
                spans.append(float(np.ptp(c["mjd"])))
    if scans:
        j = int(np.argmin(chi))
        dof = max(sum(len(c["mjd"]) - 3 for c in curves if len(c["mjd"]) >= 6), 1)
        inside = trial[chi <= chi[j] + max(chi[j] / dof, 1.0)]
        out["scan"] = {"periods": trial, "chi2": chi, "best": float(trial[j]),
                       "lo": float(inside.min()), "hi": float(inside.max()),
                       "nBins": len(scans)}
        out["scan"].update(period_bootstrap(trial, np.array(scans)))
        cyc = np.array(spans) / float(trial[j])
        out["scan"]["binSpanCycles"] = {"min": float(cyc.min()), "median": float(np.median(cyc)),
                                        "max": float(cyc.max())}
        out["scan"]["note"] = (
            "lo/hi is the formal chi-square range and is too narrow (the sinusoid is a poor "
            "formal fit); boot68/boot95 resample the wavelength bins and are the ranges to "
            "quote. No single bin covers the whole data span: see binSpanCycles.")
    return out


def period_bootstrap(trial: np.ndarray, scans: np.ndarray, n_boot: int = 1000,
                     seed: int = 20261114) -> dict:
    """Uncertainty of the summed-chi-square period from resampling the wavelength bins.

    ``scans`` holds one chi-square curve per wavelength bin (rows) over the trial periods.
    Each bootstrap draw sums a random sample (with replacement) of the bins and takes the
    period of its minimum; the 68% and 95% ranges of those periods are returned. This
    measures how much the answer depends on which bins happen to be in the sample, which
    the formal chi-square range does not.
    """
    rng = np.random.default_rng(seed)
    n = len(scans)
    best = np.array([trial[int(np.argmin(scans[rng.integers(n, size=n)].sum(axis=0)))]
                     for _ in range(n_boot)])
    p = np.percentile(best, [2.5, 16.0, 50.0, 84.0, 97.5])
    return {"bootMedian": float(p[2]), "boot68": [float(p[1]), float(p[3])],
            "boot95": [float(p[0]), float(p[4])], "nBoot": n_boot, "bootSeed": seed}


def validate_variable(key: str, field: Field) -> dict:
    target = TARGETS[key]
    notes: list[str] = []
    ra, dec, shift = _refine_centre(field, target)
    first = ph.photometry(field, ra, dec)
    hole95 = float(np.percentile(first.hole, 95))
    wing, wing_bkg = _wing_radii(field, hole95)
    phot = ph.photometry(field, ra, dec, wing=wing, wing_bkg=wing_bkg)
    quality = ph.quality_report(phot)
    sat = quality["saturatedFraction"]
    usable_ap = float(phot.good(ph.SUSPECT).mean())
    primary = "flux" if usable_ap >= 0.5 else "wing"
    passes = pass_table(field)
    continuous = max(p["spanDays"] for p in passes) > LONG_PASS_DAYS
    groups = lc.epoch_groups(field.mjd, 20.0) if continuous else field.campaign.astype(int)
    block: dict = {
        "primary": primary, "centreShiftArcsec": shift, "quality": quality,
        "saturatedFraction": sat, "apertureUsableFraction": usable_ap,
        "holeRadiusPix95": hole95, "wingRingPix": list(wing),
        "grouping": "time bins of 20 days" if continuous else "survey passes",
        "groups": [{"index": int(g), "mjd": float(field.mjd[groups == g].mean()),
                    "nFrames": int((groups == g).sum())} for g in np.unique(groups)],
        "wing": _analysis(phot, groups, "wing"),
    }
    if usable_ap >= 0.15:
        block["aperture"] = _analysis(phot, groups, "flux")
    x0, y0 = ph.pixel_xy(field, ra, dec)
    block["control"] = _control_star(field, (float(x0), float(y0)), groups)
    block["period"] = _period_block(key, target.name, phot, primary)
    if continuous:
        notes.append("The field is visited almost continuously (near an ecliptic pole), so "
                     "frames are grouped in 20-day bins instead of survey passes.")
    if sat > 0.05:
        dets = [d for d, q in quality["perDetector"].items()
                if q["saturated"] > 0.5 * q["frames"]]
        notes.append(f"The core is saturated in {100 * sat:.0f} % of the frames"
                     + (f" (most frames of detector(s) {', '.join(dets)})" if dets else "")
                     + "; those frames only enter the wing-ring photometry.")
    if primary == "wing":
        notes.append("Headline numbers use wing-ring photometry: valid for brightness "
                     "ratios at a fixed wavelength, not for absolute fluxes.")
    return {"lightcurve": block, "spectrum": spectrum_block(phot, primary, groups),
            "notes": notes, "_phot": phot, "_groups": groups}


# -------------------------------------------------------------------------- verdicts


def _f(v, nd: int = 2) -> str:
    return "n/a" if v is None or not np.isfinite(v) else f"{v:.{nd}f}"


def motion_verdict(name: str, m: dict) -> str:
    cat = m["catalogue"]
    truth = f"catalogue {cat['total']:.2f} at {cat['pa']:.1f}"
    meas = m.get("measured")
    if m.get("mode") == "faint":
        zp = m.get("zeroPoint", {})
        if not m.get("detected"):
            return (f"{name}: not detected (best track S/N {_f(zp.get('combinedSnr'), 1)}); "
                    f"5-sigma limit {_f(m.get('upperLimit5SigmaUJy'), 0)} microJy; {truth}")
        flux = (f"{meas['fluxUJy']:.0f} +- {meas['fluxErrUJy']:.0f} microJy"
                if meas and "fluxUJy" in meas else f"{_f(m.get('fluxUJy'), 0)} microJy (direct)")
        nt = m.get("nullTest") or {}
        null = ""
        if "pFixed" in nt:
            null = (f"; not a Gaussian sigma: random tracks scatter by {nt['fixedStd']:.2f}, "
                    f"{nt['fixedExceed']}/{nt['nFixed']} reach it at a fixed position and "
                    f"{nt.get('searchExceed', 0)}/{nt.get('nSearch', 0)} with the search")
        head = (f"{name}: moving source detected in D5+D6 pass-difference stacks, combined "
                f"statistic {_f(zp.get('combinedSnr'), 1)}{null} ({flux}), "
                f"{_f(zp.get('offsetArcsec'), 1)} arcsec from the catalogue prediction")
        if not meas:
            return head + f"; no motion fit; {truth}"
        return (f"{head}; measured {meas['total']:.2f} +- {meas['eTotal']:.2f} arcsec/yr at PA "
                f"{meas['pa']:.1f} +- {meas['ePa']:.1f} vs {truth}")
    if not meas:
        return f"{name}: fewer than two usable passes, no motion; {truth}"
    err = ""
    if meas.get("errorSource") == "detector scatter":
        err = (f" (scatter between {meas['nDetectorsForError']} detectors; formal "
               f"{meas['eTotalFormal']:.2f})")
    return (f"{name}: measured {meas['total']:.2f} +- {meas['eTotal']:.2f} arcsec/yr{err} at PA "
            f"{meas['pa']:.1f} +- {meas['ePa']:.1f} vs {truth} "
            f"({m['residual']['nSigma']:.1f} sigma, {m['nPasses']} passes, "
            f"shift {m['displacementPix']:.2f} px"
            + (", saturated core" if m["saturatedCore"] else "") + ")")


def variable_verdict(name: str, b: dict) -> str:
    a = b.get("aperture" if b["primary"] == "flux" else "wing") or b["wing"]
    kind = "aperture" if b["primary"] == "flux" else "wing-ring"
    sat = f"saturated in {100 * b['saturatedFraction']:.0f} % of frames"
    per = b.get("period")
    if per and per.get("nSignificant"):
        scan = per.get("scan") or {}
        return (f"{name}: {sat}; {kind} photometry; sinusoid of P = {per['period']:.1f} d "
                f"significant in {per['nSignificant']}/{per['nBins']} wavelength bins, median "
                f"peak-to-peak {per['medianPeakToPeak']:.2f} mag, maximum near MJD "
                f"{per['tMaxMean']:.0f}; free period {_f(scan.get('best'), 0)} d "
                + (f"({scan['boot95'][0]:.0f}-{scan['boot95'][1]:.0f} d, 95%, bootstrap over "
                   f"{scan['nBins']} wavelength bins; each bin spans "
                   f"{scan['binSpanCycles']['min']:.1f} to {scan['binSpanCycles']['max']:.1f} "
                   f"cycles, the whole data set {per['cycles']:.1f})" if "boot95" in scan else
                   f"({_f(scan.get('lo'), 0)}-{_f(scan.get('hi'), 0)}) over "
                   f"{per['cycles']:.1f} cycles"))
    rows = a["ratio"]
    if not rows:
        return f"{name}: {sat}; fewer than two groups with usable photometry"
    parts = []
    for r in rows[:4]:
        dets = sorted(r["perDetector"])
        ends = ", ".join(f"D{d} {r['perDetector'][d]['dmag']:+.2f} +- {r['perDetector'][d]['err']:.2f}"
                         for d in dict.fromkeys([dets[0], dets[-1]]))
        parts.append(f"pass {r['group']} minus pass {a['ref']}: {ends} mag (slope "
                     f"{_f(r['slopeMagPerMicron'])} +- {_f(r['slopeErr'])} mag/micron)")
    ctl = b.get("control")
    tail = f"; control star rms {ctl['rmsDmag']:.3f} mag" if ctl else "; no control star"
    return f"{name}: {sat}; {kind} photometry; " + "; ".join(parts) + tail


# --------------------------------------------------------------------------- figures


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 8, "axes.grid": True, "grid.alpha": 0.25,
                         "savefig.dpi": 200, "figure.dpi": 100, "axes.axisbelow": True})
    return plt


def _show(ax, img: np.ndarray, x0: float, y0: float, half: float, diverging: bool = False):
    """Zoomed image, bicubic display (the data are under-sampled), north up, east left."""
    sub = img[max(int(y0 - half - 2), 0) : int(y0 + half + 3),
              max(int(x0 - half - 2), 0) : int(x0 + half + 3)]
    fin = sub[np.isfinite(sub)]
    if fin.size == 0:
        return
    if diverging:
        v = np.percentile(np.abs(fin), 99.5)
        kw = {"cmap": "RdBu_r", "vmin": -v, "vmax": v}
        data = img
    else:
        lo, hi = np.percentile(fin, [5, 99.8])
        data = np.arcsinh((img - lo) / max(hi - lo, 1e-9) * 10)
        kw = {"cmap": "cividis", "vmin": 0, "vmax": np.arcsinh(10)}
    cm = ax.imshow(data, origin="lower", interpolation="bicubic", **kw)
    cm.cmap.set_bad("0.6")
    ax.set_xlim(x0 - half, x0 + half)
    ax.set_ylim(y0 - half, y0 + half)
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])


def fig_stacks(key: str, field: Field, m: dict, out: Path) -> Path:
    """Per-pass stacks with the measured positions and the catalogue track."""
    plt = _plt()
    faint = m.get("mode") == "faint"
    rows = (m.get("track") or []) if faint else m["perPass"]
    target = TARGETS[key]
    plx = mo.PARALLAX_MAS.get(key, (0.0, ""))[0]
    ncamp = int(field.campaign.max()) + 1
    dets = tuple(m["detectors"]) if faint else (1, 2, 3, 4, 5, 6)
    imgs = []
    for c in range(ncamp):
        sel = (field.campaign == c) & np.isin(field.det, dets)
        imgs.append(mo.stack_frames(field.img[sel], field.var[sel], grow=0)[0]
                    if sel.sum() >= 2 else np.full((field.n, field.n), np.nan))
    mjds = [float(field.mjd[field.campaign == c].mean()) for c in range(ncamp)]
    ce, cn = mo.catalogue_track(field, target, mjds, plx)
    cx, cy = mo.offsets_to_xy(field, ce, cn)
    mx = [r["x"] for r in rows] or list(cx)
    my = [r["y"] for r in rows] or list(cy)
    x0, y0 = float(np.mean(mx)), float(np.mean(my))
    half = 7.0
    nrow = 2 if faint and ncamp > 1 else 1
    fig, axes = plt.subplots(nrow, ncamp, figsize=(2.3 * ncamp, 2.5 * nrow), squeeze=False)
    for c in range(ncamp):
        ax = axes[0, c]
        _show(ax, imgs[c], x0, y0, half)
        ax.plot(cx, cy, "-", color="white", lw=0.8)
        ax.plot(cx[c], cy[c], "s", mfc="none", mec="white", ms=9, mew=1.0)
        for r in rows:
            cur = r["pass"] == c
            ax.plot(r["x"], r["y"], "+", color=COLOURS[5] if cur else COLOURS[1],
                    ms=11 if cur else 6, mew=1.4 if cur else 0.8)
        ax.set_title(f"pass {c}  ({mo.mjd_to_year(mjds[c]):.2f})", fontsize=8)
        if nrow == 2:
            others = [imgs[k] for k in range(ncamp) if k != c and np.isfinite(imgs[k]).any()]
            if others:
                _show(axes[1, c], imgs[c] - np.mean(others, axis=0), x0, y0, half, diverging=True)
                for r in rows:
                    if r["pass"] == c:
                        axes[1, c].plot(r["x"], r["y"], "o", mfc="none", mec="k", ms=12, mew=0.9)
                axes[1, c].text(0.03, 0.95, "pass minus other passes", fontsize=7,
                                transform=axes[1, c].transAxes, va="top")
    label = "+".join(f"D{d}" for d in dets) if faint else "all detectors"
    fig.suptitle(f"{target.name}: stacks per survey pass ({label}); cross = measured, "
                 f"square/line = catalogue; {2 * half * field.scale / 60:.1f} arcmin wide",
                 fontsize=8)
    fig.tight_layout()
    path = out / "stacks.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_motion(key: str, field: Field, m: dict, out: Path) -> Path | None:
    """East and north offsets against time: measurements, fitted motion, catalogue."""
    faint = m.get("mode") == "faint"
    rows = m.get("positions" if faint else "perPass") or []
    meas = m.get("measured")
    if len(rows) < 2 or not meas:
        return None
    plt = _plt()
    target = TARGETS[key]
    plx = mo.PARALLAX_MAS.get(key, (0.0, ""))[0]
    yr = np.array([r["year"] for r in rows])
    grid_mjd = np.linspace(min(r["mjd"] for r in rows) - 40, max(r["mjd"] for r in rows) + 40, 200)
    gy = mo.mjd_to_year(grid_mjd)
    ce, cn = mo.catalogue_track(field, target, grid_mjd, plx)
    shift_e = float(np.mean([r["resEast"] for r in rows]))
    shift_n = float(np.mean([r["resNorth"] for r in rows]))
    fig, axes = plt.subplots(1, 3, figsize=(9.5, 3.0))
    for ax, k, ek, cat, sh, lab in ((axes[0], "east", "eEast", ce, shift_e, "east"),
                                    (axes[1], "north", "eNorth", cn, shift_n, "north")):
        ax.errorbar(yr, [r[k] for r in rows], [r[ek] for r in rows], fmt="o", color=COLOURS[0],
                    ms=4, capsize=2, label="measured (per pass)", zorder=3)
        ax.plot(gy, cat + sh, "-", color=COLOURS[1], lw=1.2,
                label=f"catalogue track, shifted {sh:+.1f} arcsec")
        if faint and m.get("track"):
            ax.plot([t["year"] for t in m["track"]], [t[k] for t in m["track"]], "D",
                    mfc="none", mec=COLOURS[5], ms=6, label="joint moving-source fit")
        ax.set_xlabel("year")
        ax.locator_params(axis="x", nbins=5)
        ax.set_ylabel(f"offset {lab} (arcsec)")
        ax.legend(fontsize=6)
    ax = axes[2]
    ax.plot(ce + shift_e, cn + shift_n, "-", color=COLOURS[1], lw=1.2)
    ax.errorbar([r["east"] for r in rows], [r["north"] for r in rows],
                [r["eNorth"] for r in rows], [r["eEast"] for r in rows], fmt="o",
                color=COLOURS[0], ms=4, capsize=2, zorder=3)
    for r in rows:
        ax.annotate(str(r["pass"]), (r["east"], r["north"]), textcoords="offset points",
                    xytext=(5, 4), fontsize=7)
    ax.invert_xaxis()
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("east (arcsec)")
    ax.set_ylabel("north (arcsec)")
    cat = m["catalogue"]
    fig.suptitle(f"{target.name}: {meas['total']:.2f} +- {meas['eTotal']:.2f} arcsec/yr at PA "
                 f"{meas['pa']:.1f} +- {meas['ePa']:.1f} deg (catalogue {cat['total']:.2f} at "
                 f"{cat['pa']:.1f}); one pixel = {field.scale} arcsec", fontsize=8)
    fig.tight_layout()
    path = out / "motion.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_spectrum(name: str, spec: dict, out: Path) -> Path:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7.0, 3.2))
    rows = spec["channels"]
    step = max(len(rows) // 6, 1)
    for i, s in enumerate(rows[::step][:7]):
        if len(s["lam"]) == 0:
            continue
        ax.errorbar(s["lam"], np.asarray(s["fluxUJy"]) / 1e3, np.asarray(s["errUJy"]) / 1e3,
                    fmt=MARKERS[i % 7], color=COLOURS[i % 7], ms=3, lw=0.6, capsize=1.5,
                    label=f"group {s['pass']} (MJD {s['mjd']:.0f}, {s['nFrames']} frames)")
    if spec.get("coarse"):
        c = spec["coarse"]
        ax.errorbar(c["lam"], np.asarray(c["fluxUJy"]) / 1e3, np.asarray(c["errUJy"]) / 1e3,
                    fmt="k-D", ms=4, lw=1.0, capsize=2, label="all passes, 6 bins per detector")
    for d, (a, _) in ph.DETECTOR_BANDS.items():
        ax.axvline(a, color="0.7", lw=0.5, ls=":")
        ax.text(a + 0.01, 0.98, f"D{d}", transform=ax.get_xaxis_transform(), fontsize=6,
                va="top", color="0.4")
    ax.set_xlabel("wavelength (micron)")
    ax.set_ylabel("flux (mJy)" if spec["absolute"] else "wing-ring flux (mJy, relative)")
    vals = np.concatenate([np.asarray(s["fluxUJy"], float) for s in rows if len(s["lam"])] or [[1.0]])
    if not spec.get("coarse") and np.nanmin(vals) > 0:
        ax.set_yscale("log")
    ax.set_title(f"{name}: spectrum per group of visits ({spec['measurement']})", fontsize=8)
    ax.legend(fontsize=6, ncol=2)
    fig.tight_layout()
    path = out / "spectrum.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_ratio(name: str, b: dict, out: Path) -> Path | None:
    """Brightness change against wavelength (ratio spectrum), and against time."""
    a = b.get("aperture" if b["primary"] == "flux" else "wing") or b["wing"]
    if not a["ratio"]:
        return None
    plt = _plt()
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.2))
    rows = a["ratio"]
    step = max(len(rows) // 6, 1)
    for i, r in enumerate(rows[::step][:7]):
        axes[0].errorbar(r["lam"], r["dmag"], r["dmagErr"], fmt=MARKERS[i % 7],
                         color=COLOURS[i % 7], ms=3, lw=0, elinewidth=0.6, capsize=1.5,
                         label=f"group {r['group']} (MJD {r['mjd']:.0f})")
    axes[0].axhline(0, color="k", lw=0.6)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("wavelength (micron)")
    axes[0].set_ylabel(f"magnitude change vs group {a['ref']}")
    axes[0].legend(fontsize=6)
    axes[0].set_title("ratio spectrum (brighter is up)", fontsize=8)
    for d in range(1, 7):
        pts = [(r["mjd"], r["perDetector"][str(d)]["dmag"], r["perDetector"][str(d)]["err"])
               for r in rows if str(d) in r["perDetector"]]
        pts.append((a["refMjd"], 0.0, 0.0))
        t, v, e = (np.array(c) for c in zip(*sorted(pts), strict=True))
        lo, hi = ph.DETECTOR_BANDS[d]
        axes[1].errorbar(t, v, e, fmt=MARKERS[d - 1] + "-", color=COLOURS[d - 1], ms=3, lw=0.7,
                         capsize=1.5, label=f"D{d} {lo:.1f}-{hi:.1f} um")
    ctl = b.get("control")
    if ctl:
        axes[1].plot(ctl["mjd"], ctl["meanDmag"], "x", color="0.4", ms=6,
                     label=f"control star (vs group {ctl['ref']})")
    axes[1].invert_yaxis()
    axes[1].set_xlabel("MJD")
    axes[1].set_ylabel("mean magnitude change")
    axes[1].legend(fontsize=6, ncol=2)
    axes[1].set_title("same-wavelength light curve per detector", fontsize=8)
    kind = "aperture" if b["primary"] == "flux" else "wing-ring"
    fig.suptitle(f"{name}: brightness change at matched wavelength ({kind} photometry, "
                 f"{b['grouping']})", fontsize=8)
    fig.tight_layout()
    path = out / "ratio.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_period(name: str, b: dict, out: Path) -> Path | None:
    per = b.get("period")
    if not per or not per["bins"]:
        return None
    plt = _plt()
    a = b.get("aperture" if b["primary"] == "flux" else "wing") or b["wing"]
    fig, axes = plt.subplots(1, 3, figsize=(10.0, 3.0))
    best = sorted(per["bins"], key=lambda r: -r["significance"])[:5]
    period = per["period"]
    for i, r in enumerate(best):
        c = min(a["byWavelength"], key=lambda q: abs(q["lam"] - r["lam"]) + 9 * (q["det"] != r["det"]))
        t = np.linspace(min(c["mjd"]), max(c["mjd"]), 200)
        axes[0].errorbar(c["mjd"], c["mag"], c["magErr"], fmt=MARKERS[i], color=COLOURS[i], ms=3,
                         lw=0, elinewidth=0.6, label=f"{r['lam']:.2f} um")
        axes[0].plot(t, r["mean"] - r["amplitude"] * np.cos(2 * np.pi * (t - r["tMax"]) / period),
                     "-", color=COLOURS[i], lw=0.8)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("MJD")
    axes[0].set_ylabel("magnitude relative to bin mean")
    axes[0].legend(fontsize=6)
    axes[0].set_title(f"5-day bins with a sinusoid of P = {period:.1f} d", fontsize=8)
    lam = [r["lam"] for r in per["bins"]]
    axes[1].errorbar(lam, [r["peakToPeak"] for r in per["bins"]],
                     [2 * r["amplitudeErr"] for r in per["bins"]], fmt="o", color=COLOURS[0], ms=3,
                     capsize=1.5)
    axes[1].set_xlabel("wavelength (micron)")
    axes[1].set_ylabel("peak-to-peak amplitude (mag)")
    axes[1].set_title("amplitude against wavelength", fontsize=8)
    scan = per.get("scan")
    if scan:
        axes[2].plot(scan["periods"], scan["chi2"], "-", color=COLOURS[0])
        axes[2].axvline(period, color=COLOURS[5], ls="--", lw=1, label=f"known {period:.1f} d")
        axes[2].axvspan(scan["lo"], scan["hi"], color=COLOURS[1], alpha=0.3,
                        label=f"best {scan['best']:.0f} d")
        axes[2].set_xlabel("trial period (days)")
        axes[2].set_ylabel("summed chi-square")
        axes[2].legend(fontsize=6)
        axes[2].set_title("period scan", fontsize=8)
    fig.suptitle(f"{name}: periodic variation at matched wavelength", fontsize=8)
    fig.tight_layout()
    path = out / "period.png"
    fig.savefig(path)
    plt.close(fig)
    return path


# ------------------------------------------------------------------------- top level


def validate_target(key: str, field: Field | None = None, figures: bool = True,
                    out_root: Path | None = None) -> dict | None:
    """Measure one built-in target. Returns the ``science`` block, or None without data."""
    field = field if field is not None else load_field(key)
    if field is None:
        return None
    target = TARGETS[key]
    passes = pass_table(field)
    res = validate_motion(key, field) if target.kind == "motion" else validate_variable(key, field)
    science: dict = {"target": target.name, "kind": target.kind, "nFrames": len(field),
                     "nRawFiles": raw_count(key), "nPasses": len(passes), "passes": passes}
    science.update({k: v for k, v in res.items() if not k.startswith("_")})
    if target.kind == "motion":
        science["verdict"] = motion_verdict(target.name, science["motion"])
    else:
        science["verdict"] = variable_verdict(target.name, science["lightcurve"])
    if len(passes) < 2:
        science["notes"].append("Single survey pass: neither a motion nor a change between "
                                "passes can be measured.")
    if figures:
        out = (out_root or ROOT / "data" / "figures") / key
        out.mkdir(parents=True, exist_ok=True)
        made = [fig_spectrum(target.name, science["spectrum"], out)]
        if target.kind == "motion":
            made += [fig_stacks(key, field, science["motion"], out),
                     fig_motion(key, field, science["motion"], out)]
        else:
            made += [fig_ratio(target.name, science["lightcurve"], out),
                     fig_period(target.name, science["lightcurve"], out)]
        science["figures"] = [p.name for p in made if p is not None]
    return json_safe(science)


def validate_all(keys: list[str] | None = None, figures: bool = True) -> dict[str, dict]:
    out = {}
    for key in keys or list(TARGETS):
        sci = validate_target(key, figures=figures)
        if sci is not None:
            out[key] = sci
    return out
