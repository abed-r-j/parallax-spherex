"""Object-first search for moving-object demo fields.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.

    find_mover_fields.py search  NAME [NAME ...]
        Which SPHEREx Level-2 images contain each object (hits are cached as JSON).
    find_mover_fields.py fixed   NAME KEY [--size 61] [--max 200] [--dets 1,2,3] [--dry]
        Best FIXED sky field the object crosses; downloads all (or --max) frames of that
        position into data/raw/KEY and registers KEY in data/extra_targets.json.
    find_mover_fields.py comoving NAME KEY [--size 41] [--max 40] [--from MJD --to MJD]
        Cutouts centred on the object in each image, into data/raw/KEY, plus manifest.

NAME is anything JPL Horizons understands through parallax.sso.horizons_command, e.g.
"52 Europa", "Pluto", "3I/ATLAS". Downloads use the public S3 mirror, one cutout at a time
per thread, so they do not compete with IRSA cutout traffic.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from astropy.time import Time

from parallax import movers

DATA = Path(__file__).resolve().parents[2] / "data"


def say(msg: str) -> None:
    print(msg, flush=True)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_hits(name: str) -> list[movers.MoverHit]:
    fn = DATA / "cache" / "movers" / f"{slug(name)}_hits.json"
    if fn.exists():
        return [movers.MoverHit(**h) for h in json.loads(fn.read_text())]
    hits = movers.find_images(name, progress=say)
    fn.parent.mkdir(parents=True, exist_ok=True)
    fn.write_text(json.dumps(movers.hits_table(hits), indent=1))
    return hits


def iso(mjd: float) -> str:
    return Time(mjd, format="mjd").isot[:16]


def summary(name: str, hits: list[movers.MoverHit]) -> None:
    say(f"== {name}: {len(hits)} Level-2 images contain it")
    if not hits:
        return
    mjd = np.array([h.mjd for h in hits])
    runs = np.split(np.arange(len(hits)), np.flatnonzero(np.diff(mjd) > 20.0) + 1)
    for r in runs:
        h = [hits[i] for i in r]
        v = np.array([x.vmag for x in h])
        say(f"   {iso(h[0].mjd)} .. {iso(h[-1].mjd)}  {len(h):4d} images  "
            f"V {np.nanmin(v):.1f}-{np.nanmax(v):.1f}  elong {h[0].elong:.0f}-{h[-1].elong:.0f}  "
            f"RA {h[0].ra:.3f}->{h[-1].ra:.3f}  Dec {h[0].dec:.3f}->{h[-1].dec:.3f}  "
            f"dets {dict(sorted(Counter(x.det for x in h).items()))}")


def cmd_search(a: argparse.Namespace) -> None:
    for name in a.names:
        summary(name, load_hits(name))


def cmd_fixed(a: argparse.Namespace) -> None:
    hits = load_hits(a.name)
    summary(a.name, hits)
    ra, dec, inside = movers.best_fixed_field(hits, a.size)
    h = [hits[i] for i in inside]
    say(f"best fixed field: RA {ra:.5f} Dec {dec:.5f}, {a.size} px; object inside in "
        f"{len(h)} images, {iso(h[0].mjd)} .. {iso(h[-1].mjd)}")
    for x in h:
        say(f"   {iso(x.mjd)} D{x.det}  RA {x.ra:.5f} Dec {x.dec:+.5f}  V {x.vmag:.2f}  "
            f"rate {x.rate_ra:+.1f} {x.rate_dec:+.1f} arcsec/h  {x.uri.rsplit('/', 1)[1]}")
    dets = tuple(int(d) for d in a.dets.split(",")) if a.dets else None
    jobs = movers.fixed_field_jobs(ra, dec, hits, inside, a.max, dets)
    say(f"{len(jobs)} cutouts selected (cap {a.max}, detectors {dets or 'all'})")
    if a.dry:
        return
    out = DATA / "raw" / a.key
    stats = movers.download_cutouts(jobs, a.size, out, progress=say)
    say(json.dumps({k: v for k, v in stats.items() if k != "failed"}) + f" failed={len(stats['failed'])}")
    manifest = {"object": a.name, "ra": ra, "dec": dec, "size_pix": a.size,
                "hits_inside": movers.hits_table(h), "download": stats}
    (out / "_mover.json").write_text(json.dumps(manifest, indent=1))
    movers.register_target(DATA / "extra_targets.json", {
        "key": a.key, "name": a.label or f"{a.name} crossing", "kind": "mover",
        "ra": ra, "dec": dec, "epoch": 2000.0, "pm_ra": 0.0, "pm_dec": 0.0,
        "size_pix": a.size, "max_images": None,
        "blurb": a.blurb or (f"A fixed patch of sky that asteroid {a.name} crosses between "
                             f"{iso(h[0].mjd)} and {iso(h[-1].mjd)} UT: present in "
                             f"{len(h)} frames, absent from all the others."),
        "source": "JPL Horizons ephemeris as seen from SPHEREx (500@-163182); "
                  "IRSA TAP spherex.plane footprints",
    })


def cmd_comoving(a: argparse.Namespace) -> None:
    hits = [h for h in load_hits(a.name)
            if a.t0 <= h.mjd <= a.t1 and h.edge_arcsec > a.size * 3.1]
    if len(hits) > a.max:
        hits = [hits[i] for i in np.unique(np.linspace(0, len(hits) - 1, a.max).round().astype(int))]
    say(f"{len(hits)} co-moving cutouts of {a.name}")
    if a.dry:
        return
    out = DATA / "raw" / a.key
    stats = movers.download_cutouts([(h.ref, h.ra, h.dec) for h in hits], a.size, out, progress=say)
    say(json.dumps({k: v for k, v in stats.items() if k != "failed"}) + f" failed={len(stats['failed'])}")
    (out / "_mover.json").write_text(json.dumps(
        {"object": a.name, "comoving": True, "size_pix": a.size,
         "hits": movers.hits_table(hits), "download": stats}, indent=1))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(required=True)
    s = sub.add_parser("search")
    s.add_argument("names", nargs="+")
    s.set_defaults(fn=cmd_search)
    f = sub.add_parser("fixed")
    f.add_argument("name")
    f.add_argument("key")
    f.add_argument("--size", type=int, default=61)
    f.add_argument("--max", type=int, default=200)
    f.add_argument("--dets", default="")
    f.add_argument("--label", default="")
    f.add_argument("--blurb", default="")
    f.add_argument("--dry", action="store_true")
    f.set_defaults(fn=cmd_fixed)
    c = sub.add_parser("comoving")
    c.add_argument("name")
    c.add_argument("key")
    c.add_argument("--size", type=int, default=41)
    c.add_argument("--max", type=int, default=40)
    c.add_argument("--from", dest="t0", type=float, default=0.0)
    c.add_argument("--to", dest="t1", type=float, default=1e9)
    c.add_argument("--dry", action="store_true")
    c.set_defaults(fn=cmd_comoving)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
