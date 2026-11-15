"""Stamp the SI/provenance block into the published data packs, in place.

    python submission/stamp_packs.py           # stamp web/public/data and verify
    python submission/stamp_packs.py --check   # verify only

Adds one top-level key, "provenance", to web/public/data/index.json and to every
web/public/data/<field>/meta.json, and to web/public/skyindex/manifest.json. It is the same block that pipeline/src/parallax/export.py
writes from now on. The block is appended as text before the closing brace, so every other
byte of the file stays as the pipeline wrote it. Running it twice changes nothing.
The check compares every other key with the committed version (git HEAD) when git is available.
SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "public" / "data"
MANIFEST = ROOT / "web" / "public" / "skyindex" / "manifest.json"
SI_DISCLOSURE = (
    "Produced with the help of an SI coding assistant (Claude, Anthropic), directed and "
    "checked by the team; computed by the project's own code from real SPHEREx data."
)
SOURCE = "SPHEREx Level-2 spectral images, NASA/IPAC IRSA"


def block(version: str, dois) -> dict:
    return {"generator": f"parallax-spherex {version}", "siDisclosure": SI_DISCLOSURE,
            "source": SOURCE, "dois": sorted(dois)}


def stamp(path: Path, prov: dict, pretty: bool) -> str:
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)
    if doc.get("provenance") == prov:
        return "already stamped"
    if "provenance" in doc:  # an older block: rewrite the file in the pipeline's own style
        doc["provenance"] = prov
        new = json.dumps(doc, indent=1) if pretty else json.dumps(doc, separators=(",", ":"))
    else:
        body = text.rstrip()
        assert body.endswith("}"), path
        body = body[:-1].rstrip()
        if pretty:
            add = json.dumps({"provenance": prov}, indent=1)[1:-1].strip("\n")
            new = body + ",\n" + add + "\n}" + text[len(text.rstrip()):]
        else:
            new = body + "," + json.dumps({"provenance": prov}, separators=(",", ":"))[1:-1] + "}" + text[len(text.rstrip()):]
    after = json.loads(new)
    assert after.pop("provenance") == prov
    before = dict(doc)
    before.pop("provenance", None)
    assert json.dumps(after) == json.dumps(before), f"{path}: other keys changed"
    path.write_bytes(new.encode("utf-8"))
    return "stamped"


def committed(path: Path):
    rel = path.relative_to(ROOT).as_posix()
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{rel}"], capture_output=True, check=False)
    return json.loads(r.stdout.decode("utf-8")) if r.returncode == 0 else None


def main() -> int:
    check_only = "--check" in sys.argv
    index_path = DATA / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    version = index["pipeline"]
    metas = sorted(DATA.glob("*/meta.json"))
    assert {p.parent.name for p in metas} == {f["key"] for f in index["fields"]}, "index and folders differ"
    all_dois, bad = set(), 0
    for p in metas:
        dois = json.loads(p.read_text(encoding="utf-8")).get("release", {}).get("doi", [])
        all_dois.update(dois)
        todo = [(p, block(version, dois), False)]
        for path, prov, pretty in todo:
            if not check_only:
                print(f"{path.relative_to(ROOT).as_posix()}: {stamp(path, prov, pretty)}")
    if not check_only:
        print(f"{index_path.relative_to(ROOT).as_posix()}: {stamp(index_path, block(version, all_dois), True)}")
    # The sky index manifest: both readers (web/src/lib/skyindex.ts and
    # pipeline/src/parallax/skyindex.py) check only "format" and "version" and read named
    # keys, so one more top-level key is harmless. Its shards are not touched.
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    man_prov = {"generator": f"parallax-spherex {version}", "siDisclosure": SI_DISCLOSURE,
                "source": man["source"], "dois": sorted(man["doi"].values())}
    if not check_only:
        print(f"{MANIFEST.relative_to(ROOT).as_posix()}: {stamp(MANIFEST, man_prov, False)}")
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    old = committed(MANIFEST)
    okm = doc.pop("provenance", None) == man_prov and doc["format"] == "parallax-skyindex" and doc["version"] == 1
    if old is not None:
        old.pop("provenance", None)
        okm = okm and json.dumps(old) == json.dumps(doc)
    bad += not okm
    print(f"{'ok ' if okm else 'BAD'} {MANIFEST.relative_to(ROOT).as_posix()}: {len(doc)} other keys"
          f"{'' if old is None else ', compared with git HEAD'}")
    # verification: every file parses, carries the block, and nothing else differs from git HEAD
    for p in [*metas, index_path]:
        doc = json.loads(p.read_text(encoding="utf-8"))
        prov = doc.pop("provenance", None)
        ok = isinstance(prov, dict) and prov.get("siDisclosure") == SI_DISCLOSURE and prov.get("source") == SOURCE
        old = committed(p)
        same = "no committed copy to compare"
        if old is not None:
            old.pop("provenance", None)
            same = "other keys identical to git HEAD" if json.dumps(old) == json.dumps(doc) else "OTHER KEYS DIFFER FROM git HEAD"
            ok = ok and "DIFFER" not in same
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {p.relative_to(ROOT).as_posix()}: {len(doc)} other keys, dois {prov and prov.get('dois')}; {same}")
    print("all good" if not bad else f"{bad} file(s) failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
