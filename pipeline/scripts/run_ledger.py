"""Run the three-way ledger (naive / gated / chromatic template) on real fields.

Usage (from the repository root, with the pipeline virtual environment):

    python pipeline/scripts/run_ledger.py barnard            # one field
    python pipeline/scripts/run_ledger.py                    # every field with raw data
    python pipeline/scripts/run_ledger.py barnard --no-injection --rebuild

Reads ``data/raw/<key>/*.fits``, caches the aligned cube in ``data/cache/<key>_field.npz``
(rebuilt when the number of raw files changed), writes ``data/ledger/<key>.json`` and the
figures in ``data/figures/<key>/``, and prints the headline numbers.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from parallax import ledger  # noqa: E402
from parallax.export import _clean  # noqa: E402
from parallax.frames import Field, build_field  # noqa: E402
from parallax.targets import TARGETS  # noqa: E402

MIN_FILES = 20


def load_field(key: str, rebuild: bool = False) -> Field | None:
    raw = ROOT / "data" / "raw" / key
    nfiles = len(list(raw.glob("*.fits")))
    if nfiles < MIN_FILES:
        print(f"[{key}] only {nfiles} raw files - skipped")
        return None
    cache = ROOT / "data" / "cache" / f"{key}_field.npz"
    stamp = cache.with_suffix(".count")
    if cache.exists() and not rebuild and stamp.exists() and stamp.read_text() == str(nfiles):
        return Field.load(cache)
    t = TARGETS[key]
    f = build_field(raw, *t.centre, t.size_pix)
    cache.parent.mkdir(parents=True, exist_ok=True)
    f.save(cache)
    stamp.write_text(str(nfiles))
    print(f"[{key}] built field from {nfiles} files: {len(f)} frames")
    return f


def _fmt(v, nd=0):
    return "-" if v is None or not np.isfinite(v) else f"{v:.{nd}f}"


def summary(key: str, led: dict) -> str:
    rows = [f"[{key}] {led['nFrames']} frames, {led['nPasses']} passes, template "
            f"{led['templateMode']}; false detections outside {led['excludedRadiusPix']:.0f} px "
            f"of {led['target']}",
            "mode       usable  depth  faint | false/frame  /deg2 (plain sigma) | thr@rate "
            "f50 blank/star @rate | f50 blank/star @5 | known signal"]
    inj = led.get("injection")
    for m, e in led["modes"].items():
        f50 = ["-"] * 4
        if inj and "mover" in inj["atFixedRate"]["modes"][m]:
            a, b = inj["atFixedRate"]["modes"][m]["mover"], inj["atThreshold5"]["modes"][m]["mover"]
            f50 = [_fmt(a["blank"]["f50"]), _fmt(a["star"]["f50"]),
                   _fmt(b["blank"]["f50"]), _fmt(b["star"]["f50"])]
        ks = e["knownSignal"]
        kst = "-" if not ks.get("kind") else (
            f"+{_fmt(ks['medianPositiveSNR'], 1)}/{_fmt(ks['medianNegativeSNR'], 1)} "
            f"both>5 in {100 * (ks['fractionBothLobes5'] or 0):.0f}% {ks['fractionFramesByClass']}")
        rows.append(
            f"{m:9s}  {100 * e['usableFraction']:5.1f}% {_fmt(e['depthUJy']['all'], 1):>6} "
            f"{_fmt(e['depthUJy']['faint'], 1):>6} | {_fmt(e['false']['perFrame'], 2):>6} "
            f"{_fmt(e['false']['perDeg2']):>6} ({_fmt(e['falsePlain']['perFrame'], 2)}, "
            f"{_fmt(e['falsePlain']['perDeg2'])}) | {_fmt(e.get('thresholdAtFixedRate'), 2):>5} "
            f"{f50[0]}/{f50[1]} | {f50[2]}/{f50[3]} | {kst}")
    return "\n".join(rows)


def run(key: str, injection: bool = True, rebuild: bool = False) -> dict | None:
    f = load_field(key, rebuild)
    if f is None:
        return None
    t0 = time.time()
    out = ledger.process_field(f, with_injection=injection)
    led = out["blocks"]["ledger"]
    p = out["products"]
    print(summary(key, led), flush=True)
    figs = ledger.make_figures(f, p["template"], p["diffs"], led, ROOT / "data" / "figures" / key)
    led["runtimeSeconds"] = round(time.time() - t0, 1)
    dest = ROOT / "data" / "ledger" / f"{key}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = {"ledger": led, "candidates": out["blocks"]["candidates"],
           "nDetections": len(out["blocks"]["detections"]), "figures": figs}
    dest.write_text(json.dumps(_clean(doc), indent=1))
    print(f"[{key}] {len(out['blocks']['detections'])} detections, "
          f"{len(out['blocks']['candidates'])} candidates, {led['runtimeSeconds']} s -> {dest}")
    return led


def main(argv: list[str]) -> int:
    warnings.simplefilter("ignore")
    flags = {a for a in argv if a.startswith("--")}
    keys = [a for a in argv if not a.startswith("--")] or list(TARGETS)
    for key in keys:
        if key not in TARGETS:
            print(f"unknown field {key!r}; known: {', '.join(TARGETS)}")
            return 2
        run(key, injection="--no-injection" not in flags, rebuild="--rebuild" in flags)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
