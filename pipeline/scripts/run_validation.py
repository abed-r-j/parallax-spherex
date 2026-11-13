"""Measure the challenge targets on real SPHEREx data and compare with ground truth.

Usage (with the pipeline virtual environment):

    python pipeline/scripts/run_validation.py                 # every target with raw data
    python pipeline/scripts/run_validation.py barnard rwaur   # chosen targets
    python pipeline/scripts/run_validation.py --no-figures

Reads ``data/raw/<key>/*.fits`` (aligned cube cached in ``data/cache/<key>_field.npz``,
rebuilt when the number of raw files changed), writes ``data/science/<key>.json`` (the
'science' block of the data pack) and the figures in ``data/figures/<key>/``, and prints
a one-line verdict per target.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from parallax import validate  # noqa: E402
from parallax.targets import TARGETS  # noqa: E402


def main(argv: list[str]) -> int:
    figures = "--no-figures" not in argv
    keys = [a for a in argv if not a.startswith("--")] or list(TARGETS)
    unknown = [k for k in keys if k not in TARGETS]
    if unknown:
        print(f"unknown target(s): {', '.join(unknown)}; choose from {', '.join(TARGETS)}")
        return 2
    out_dir = ROOT / "data" / "science"
    out_dir.mkdir(parents=True, exist_ok=True)
    verdicts = []
    warnings.simplefilter("ignore", RuntimeWarning)
    for key in keys:
        t0 = time.time()
        nraw = validate.raw_count(key)
        if nraw < validate.MIN_FILES:
            print(f"[{key}] only {nraw} raw files - skipped")
            continue
        sci = validate.validate_target(key, figures=figures)
        (out_dir / f"{key}.json").write_text(json.dumps(sci, separators=(",", ":")))
        print(f"[{key}] {nraw} raw files, {sci['nFrames']} frames, {sci['nPasses']} passes, "
              f"{time.time() - t0:.0f} s -> data/science/{key}.json")
        for note in sci["notes"]:
            print(f"    note: {note}")
        verdicts.append(sci["verdict"])
    print()
    for v in verdicts:
        print(v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
