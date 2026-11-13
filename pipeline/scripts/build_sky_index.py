"""Dump/update the IRSA SPHEREx image catalogue and build the static sky index.

Usage (from the ``pipeline`` folder, with the project's Python):

    python scripts/build_sky_index.py                 # update the cache, then build
    python scripts/build_sky_index.py --skip-dump     # build from what is cached
    python scripts/build_sky_index.py --dump-only     # only download (resumable)
    python scripts/build_sky_index.py --skip-dump --verify   # compare with live IRSA

The download is cut into one file per MJD day under ``data/cache/skyindex/chunks``; a
re-run fetches only days that are missing or were not complete yet, so picking up a new
data release is the same command again. Stop it any time (Ctrl+C) and start it again.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parallax import skyindex

VERIFY_POSITIONS = [
    ("Barnard's Star", 269.4463, 4.7680),
    ("M51", 202.4696, 47.1953),
    ("WISE 0855", 133.7688, -7.2429),
    ("near north ecliptic pole", 270.0, 66.56),
    ("near RA 0", 0.05, 10.0),
    ("south ecliptic pole region", 90.0, -66.56),
]


def say(*a) -> None:
    print(*a, flush=True)


def verify(index_dir: Path, cache: Path, positions=VERIFY_POSITIONS) -> list[dict]:
    """Compare ``SkyIndex.query`` with a live IRSA TAP footprint query, position by position.

    Only images whose MJD day is in the local cache can be in the index, so TAP rows from
    days not dumped yet are counted separately ("not dumped") instead of as misses.
    """
    from parallax.irsa import list_images

    idx = skyindex.SkyIndex(index_dir)
    out = []
    for name, ra, dec in positions:
        t0 = time.time()
        refs = list_images(ra, dec)
        tap = {r.uri.split("ibe/data/spherex/", 1)[1]: r for r in refs}
        tap_in = {
            k for k, r in tap.items()
            if skyindex.chunk_path(cache, math.floor(r.mjd_start)).exists()
        }
        rec, margin = idx.candidates(ra, dec)
        hits = idx.decode(rec, margin)
        cand = {h.s3_key: h for h in hits}
        mine = {k for k, h in cand.items() if h.margin_arcsec >= 0}
        miss = sorted(tap_in - mine)
        extra = sorted(mine - set(tap))
        miss_m = [cand[k].margin_arcsec if k in cand else float("nan") for k in miss]
        extra_m = [cand[k].margin_arcsec for k in extra]
        row = {
            "name": name, "ra": ra, "dec": dec,
            "tap": len(tap), "tap_in_dumped_days": len(tap_in), "index": len(mine),
            "match": len(mine & tap_in), "miss": len(miss), "extra": len(extra),
            "miss_not_in_shards": sum(1 for m in miss_m if math.isnan(m)),
            "miss_margin_arcsec": [round(m, 2) for m in miss_m[:12]],
            "extra_margin_arcsec": [round(m, 2) for m in extra_m[:12]],
            "miss_worst_arcsec": round(min(miss_m), 2) if miss_m else None,
            "extra_worst_arcsec": round(max(extra_m), 2) if extra_m else None,
            "candidates": len(rec),
            "shards": len(idx.shards_for(ra, dec)),
            "bytes_read": len(rec) * skyindex.RECORD_DTYPE.itemsize,
            "tap_seconds": round(time.time() - t0, 1),
        }
        out.append(row)
        say(
            f"{name:28s} ({ra:9.4f},{dec:+9.4f})  TAP {row['tap']:6d} "
            f"(in dumped days {row['tap_in_dumped_days']:6d})  index {row['index']:6d}  "
            f"match {row['match']:6d}  miss {row['miss']:4d}  extra {row['extra']:4d}  "
            f"[{row['shards']} shards, {row['bytes_read'] / 1e6:.2f} MB]"
        )
        if miss:
            say(f"    misses: edge margin arcsec {row['miss_margin_arcsec']}, "
                f"{row['miss_not_in_shards']} not found in the shards read; e.g. {miss[0]}")
        if extra:
            say(f"    extras: edge margin arcsec {row['extra_margin_arcsec']}; e.g. {extra[0]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cache", type=Path, default=skyindex.DEFAULT_CACHE)
    ap.add_argument("--out", type=Path, default=skyindex.DEFAULT_OUT)
    ap.add_argument("--skip-dump", action="store_true", help="do not contact IRSA")
    ap.add_argument("--dump-only", action="store_true", help="download, do not build")
    ap.add_argument("--refresh", action="store_true", help="download every day again")
    ap.add_argument("--max-chunks", type=int, default=None, help="stop after N day chunks")
    ap.add_argument("--newest-first", action="store_true", help="fetch recent days first")
    ap.add_argument("--workers", type=int, default=2, choices=(1, 2))
    ap.add_argument("--verify", action="store_true", help="compare with live IRSA TAP")
    a = ap.parse_args()

    if not a.skip_dump:
        s = skyindex.dump_catalogue(
            a.cache, workers=a.workers, refresh=a.refresh, max_chunks=a.max_chunks,
            newest_first=a.newest_first, progress=say,
        )
        say(
            f"dump: fetched {s['fetched']} chunks, {s['rows']} rows, {s['bytes'] / 1e6:.1f} MB "
            f"in {s['seconds']:.0f}s; cache holds {s['days_cached']}/{s['days_total']} days"
        )
        for d, e in s["failed"]:
            say(f"  FAILED day {d}: {e}  (run the command again to retry)")
    if a.dump_only:
        return 0
    m = skyindex.build_index(a.cache, a.out, progress=say)
    cov = m["coverage"]
    say(f"index in {a.out}: {m['rows']['total']} images; complete = {cov['complete']} "
        f"({cov['days_cached']}/{cov['days_in_archive_span']} days, "
        f"{len(cov['missing_days'])} missing)")
    for name, r in m["rows"]["by_collection"].items():
        say(f"  {name:18s} indexed {r['indexed']:8d} of {r['archive_rows_at_dump']} "
            f"in the archive, MJD {r['mjd_min']} .. {r['mjd_max']}")
    if a.verify:
        verify(a.out, a.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
