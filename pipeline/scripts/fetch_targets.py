"""Download cutouts for built-in targets.  usage: fetch_targets.py DATA_DIR MIRROR key [key ...]

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

import json
import sys
from pathlib import Path

from parallax.irsa import fetch_field
from parallax.targets import TARGETS

data, mirror, keys = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
for k in keys:
    t = TARGETS[k]
    ra, dec = t.centre
    print(f"== {t.name}: centre {ra:.5f} {dec:.5f}, {t.size_pix} px, mirror {mirror}", flush=True)
    res = fetch_field(ra, dec, t.size_pix, data / "raw" / k, threads=6,
                      max_images=t.max_images, mirror=mirror,
                      progress=lambda m: print(m, flush=True))
    res.pop("failed_detail", None)
    (data / "raw" / k / "_fetch.json").write_text(json.dumps(res, indent=1))
    print(f"   done: {res['n_requested']} requested, {res['n_failed']} failed, "
          f"{res['seconds']:.0f}s, {res['bytes'] / 1e6:.1f} MB", flush=True)
