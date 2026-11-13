"""Build the static data packs that the web app reads.

``publish_field`` runs the whole chain for one field:

    raw cutouts -> aligned cube -> chromatic template + three-way differences ->
    detections -> measurements -> catalogue overlays -> data pack

``publish`` does it for a list of fields and rewrites ``index.json``. Re-running it after
``parallax fetch`` has downloaded newly released images is all that is needed to bring
the site up to date with a new SPHEREx data release.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import asdict
from pathlib import Path

from . import ledger
from .export import write_index, write_pack
from .frames import Field, build_field
from .targets import TARGETS, Target


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def all_targets(data_dir: Path) -> dict[str, Target]:
    """Built-in targets plus any registered in ``data/extra_targets.json``."""
    out = dict(TARGETS)
    extra = data_dir / "extra_targets.json"
    if extra.exists():
        allowed = set(Target.__dataclass_fields__)
        for row in json.loads(extra.read_text()):
            t = Target(**{k: v for k, v in row.items() if k in allowed})
            out[t.key] = t
    return out


def load_field(key: str, target: Target, data_dir: Path, rebuild: bool = False) -> Field | None:
    """Aligned cube for a field, cached in ``data/cache`` and rebuilt when raw files change."""
    raw = data_dir / "raw" / key
    nfiles = len(list(raw.glob("*.fits")))
    if nfiles < 4:
        return None
    cache = data_dir / "cache" / f"{key}_field.npz"
    stamp = cache.with_suffix(".count")
    if cache.exists() and not rebuild and stamp.exists() and stamp.read_text() == str(nfiles):
        return Field.load(cache)
    f = build_field(raw, *target.centre, target.size_pix)
    cache.parent.mkdir(parents=True, exist_ok=True)
    f.save(cache)
    stamp.write_text(str(nfiles))
    return f


def _optional(label: str, fn, default, log):
    """Run an optional enrichment step; a failure is reported and never stops the pack."""
    try:
        return fn()
    except Exception as e:  # network trouble, missing module, odd data: degrade, do not die
        log(f"    {label}: skipped ({type(e).__name__}: {str(e)[:140]})")
        return default


def _science(key: str, f: Field, data_dir: Path, log) -> dict:
    stored = data_dir / "science" / f"{key}.json"
    if stored.exists():
        return json.loads(stored.read_text())

    def run():
        from . import validate

        return validate.validate_target(key, f, figures=False)

    return _optional("measurements", run, {}, log)


def _overlays(f: Field, data_dir: Path, online: bool, log) -> dict:
    blocks: dict = {"gaia": [], "wise": [], "sso": []}
    if not online:
        return blocks

    def gaia():
        from . import catalogs

        return catalogs.gaia_dr3(f.ra0, f.dec0, f.n * f.scale / 2 * 1.5, cache_dir=data_dir / "cache")

    def wise():
        from . import catalogs

        return catalogs.catwise(f.ra0, f.dec0, f.n * f.scale / 2 * 1.5, cache_dir=data_dir / "cache")

    def sso():
        from . import sso as sso_mod

        return sso_mod.known_objects(f, cache_dir=data_dir / "cache")

    blocks["gaia"] = _optional("Gaia DR3", gaia, [], log)
    blocks["wise"] = _optional("CatWISE2020", wise, [], log)
    blocks["sso"] = _optional("known solar-system objects", sso, [], log)
    return blocks


def publish_field(
    key: str,
    target: Target,
    data_dir: Path,
    out_root: Path,
    with_injection: bool = False,
    online: bool = True,
    rebuild: bool = False,
    log=print,
) -> dict | None:
    """Write the pack for one field and return its index entry (None if there is no data)."""
    t0 = time.time()
    f = load_field(key, target, data_dir, rebuild)
    if f is None:
        log(f"[{key}] no raw data - skipped")
        return None
    log(f"[{key}] {len(f)} frames, {int(f.campaign.max()) + 1} survey passes")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = ledger.process_field(f, with_injection=with_injection)
    blocks = dict(out["blocks"])
    stored = data_dir / "ledger" / f"{key}.json"
    if not with_injection and stored.exists():  # reuse the full ledger (with injection tests)
        blocks["ledger"] = json.loads(stored.read_text())["ledger"]
    blocks["science"] = _science(key, f, data_dir, log)
    blocks.update(_overlays(f, data_dir, online, log))
    _label_known(blocks)
    tgt = {"name": target.name, "ra": target.ra, "dec": target.dec, "epoch": target.epoch,
           "pmRa": target.pm_ra, "pmDec": target.pm_dec, "source": target.source}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        entry = write_pack(
            f, out_root, key, target.name, target.kind, target.blurb, target=tgt,
            extra_sections=out["extra_sections"], frame_extras=out["frame_extras"],
            blocks=blocks,
        )
    log(f"[{key}] pack written in {time.time() - t0:.0f} s: "
        f"{len(blocks['detections'])} detections, {len(blocks['candidates'])} candidates, "
        f"{len(blocks['gaia'])} Gaia stars, {len(blocks['sso'])} known-object predictions")
    return entry


def _label_known(blocks: dict, radius_pix: float = 2.5, max_vmag: float = 17.5) -> None:
    """Attach the name of a predicted solar-system object to detections that sit on it."""
    by_frame: dict[int, list[dict]] = {}
    for o in blocks.get("sso", []):
        # Objects fainter than V ~ 17.5 are below the single-frame depth: a residual that
        # happens to sit near one is far more likely to be noise than the object itself.
        if o.get("vmag") is not None and o["vmag"] > max_vmag:
            continue
        by_frame.setdefault(int(o["frame"]), []).append(o)
    for d in blocks.get("detections", []):
        if d.get("snr", 0) <= 0:
            continue
        for o in by_frame.get(int(d["frame"]), []):
            if abs(d["x"] - o["x"]) <= radius_pix and abs(d["y"] - o["y"]) <= radius_pix:
                d["known"] = o["name"]
                d["cls"] = "mover"
                break


def publish(
    keys: list[str] | None = None,
    data_dir: Path | None = None,
    out_root: Path | None = None,
    **kw,
) -> list[dict]:
    """Publish several fields and rewrite ``index.json`` (existing other fields are kept)."""
    root = repo_root()
    data_dir = Path(data_dir or root / "data")
    out_root = Path(out_root or root / "web" / "public" / "data")
    out_root.mkdir(parents=True, exist_ok=True)
    targets = all_targets(data_dir)
    keys = keys or [k for k in targets if (data_dir / "raw" / k).is_dir()]
    index = out_root / "index.json"
    entries = {e["key"]: e for e in json.loads(index.read_text())["fields"]} if index.exists() else {}
    for k in keys:
        if k not in targets:
            raise KeyError(f"unknown field {k!r}; known: {', '.join(targets)}")
        e = publish_field(k, targets[k], data_dir, out_root, **kw)
        if e:
            entries[k] = e
    order = [k for k in targets if k in entries] + [k for k in entries if k not in targets]
    write_index(out_root, [entries[k] for k in order])
    return [entries[k] for k in order]


def describe(target: Target) -> dict:
    return asdict(target)
