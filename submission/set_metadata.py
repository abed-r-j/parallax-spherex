"""Stamp document properties into the ParallaX deliverables, then copy the deck PDF to the site.

    pipeline/.venv/Scripts/python submission/set_metadata.py            # everything, then the copy
    pipeline/.venv/Scripts/python submission/set_metadata.py <file>...  # only these files, no copy
    pipeline/.venv/Scripts/python submission/set_metadata.py --check    # read back only

Run it after every deck build (node build_deck.mjs, then export_deck.ps1): both rewrite the
files and drop these properties. paper/build_pdf.mjs and docs/build_report_pdf.mjs call it
themselves for their own PDF.

What it writes (Title, Author, Subject, Keywords, and Comments carrying the SI statement):
  presentation/ParallaX_ZENITH_LABS.pptx   core properties (python-pptx)
  presentation/ParallaX_ZENITH_LABS.pdf    PDF document information (pypdf)
  paper/ParallaX_IEEE.pdf                  PDF document information
  docs/ParallaX_Project_Report.pdf         PDF document information
and, as the last step of a full run, it copies the deck PDF to
web/public/ParallaX_ZENITH_LABS.pdf so that the site serves it.

Any existing property whose value holds a local file path or the name of the user account
running the script is removed. In a PDF the XMP packet, when present, is rewritten to match.
Pages, tags, links and bookmarks are kept. Needs pypdf and python-pptx (pure Python):
    uv pip install --python pipeline/.venv/Scripts/python.exe pypdf python-pptx
SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""
import getpass
import logging
import os
import re
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

logging.getLogger("pypdf").setLevel(logging.ERROR)  # Chrome PDFs trigger a harmless size warning
ROOT = Path(__file__).resolve().parent.parent
AUTHOR = "ZENITH LABS: Abed El Rahmane Jaafir; former member: Mohamad Alayli"
SI = (
    "Produced with the help of an SI coding assistant (Claude, Anthropic), directed and "
    "checked by the team; computed by the project's own code from real SPHEREx data."
)
EVENT = "NASA Space Apps Challenge 2026, Beirut. Challenge: Planet X and SPHEREx."
NOTE = "Not affiliated with or endorsed by NASA."
KEYWORDS = (
    "ParallaX, ZENITH LABS, NASA Space Apps Challenge 2026, Planet X and SPHEREx, SPHEREx, "
    "infrared, time-domain astronomy, difference imaging, chromatic template, moving objects, "
    "variable stars, open data, SI-assisted"
)
DECK = ROOT / "presentation" / "ParallaX_ZENITH_LABS.pdf"
SITE_COPY = ROOT / "web" / "public" / "ParallaX_ZENITH_LABS.pdf"
DOCS = {
    ROOT / "presentation" / "ParallaX_ZENITH_LABS.pptx": (
        "ParallaX: chromatic difference imaging for the SPHEREx sky",
        f"Project demo slides, team ZENITH LABS. {EVENT}"),
    DECK: (
        "ParallaX: chromatic difference imaging for the SPHEREx sky",
        f"Project demo slides, team ZENITH LABS. {EVENT}"),
    ROOT / "paper" / "ParallaX_IEEE.pdf": (
        "ParallaX: Chromatic Template Differencing for Time-Domain Exploration of the SPHEREx All-Sky Spectral Survey",
        f"Research paper, team ZENITH LABS. {EVENT}"),
    ROOT / "docs" / "ParallaX_Project_Report.pdf": (
        "ParallaX project report",
        f"Project report, team ZENITH LABS. {EVENT}"),
}


def _private(value: str) -> bool:
    """True if a property value holds a local path or the account name of whoever runs this."""
    v = str(value)
    names = {getpass.getuser(), os.environ.get("USERNAME", ""), os.environ.get("USER", ""), Path.home().name}
    if any(len(n) >= 3 and n.lower() in v.lower() for n in names):
        return True
    return bool(re.search(r"[A-Za-z]:[\\/]|\\\\[^\\]+\\|/(Users|home)/|file://", v))


def _xmp(title: str, subject: str, producer: str, creator_tool: str, when: str) -> bytes:
    kw = "".join(f"<rdf:li>{escape(k.strip())}</rdf:li>" for k in KEYWORDS.split(","))
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:pdf="http://ns.adobe.com/pdf/1.3/" xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
        f'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{escape(title)}</rdf:li></rdf:Alt></dc:title>'
        f"<dc:creator><rdf:Seq><rdf:li>{escape(AUTHOR)}</rdf:li></rdf:Seq></dc:creator>"
        f'<dc:description><rdf:Alt><rdf:li xml:lang="x-default">{escape(subject + " " + SI + " " + NOTE)}</rdf:li></rdf:Alt></dc:description>'
        f"<dc:subject><rdf:Bag>{kw}</rdf:Bag></dc:subject>"
        f"<pdf:Keywords>{escape(KEYWORDS)}</pdf:Keywords><pdf:Producer>{escape(producer)}</pdf:Producer>"
        f"<xmp:CreatorTool>{escape(creator_tool)}</xmp:CreatorTool><xmp:MetadataDate>{when}</xmp:MetadataDate>"
        "</rdf:Description></rdf:RDF></x:xmpmeta>"
        '<?xpacket end="w"?>'
    ).encode()


def stamp_pdf(path: Path, title: str, subject: str) -> list[str]:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(path))
    n_pages = len(reader.pages)
    old = {k: str(v) for k, v in (reader.metadata or {}).items()}
    removed = [k for k, v in old.items() if _private(v)]
    keep = {k: v for k, v in old.items() if k not in removed}
    writer = PdfWriter(clone_from=reader)
    creator = keep.get("/Creator", "")
    if "HeadlessChrome" in creator:  # a browser user-agent string says nothing useful
        creator = "ParallaX build scripts (headless Chrome)"
    now = datetime.now(UTC)
    info = {
        **keep,
        "/Title": title, "/Author": AUTHOR, "/Subject": subject, "/Keywords": KEYWORDS,
        "/Comments": f"{SI} {NOTE}", "/Description": f"{SI} {NOTE}", "/SIDisclosure": SI,
        "/Creator": creator or "ParallaX build scripts",
        "/ModDate": now.strftime("D:%Y%m%d%H%M%S+00'00'"),
    }
    writer.metadata = info  # replaces the whole information dictionary
    writer.xmp_metadata = _xmp(title, subject, keep.get("/Producer", ""), info["/Creator"], now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        writer.write(fh)
    check = PdfReader(str(tmp))
    assert len(check.pages) == n_pages, f"{path}: page count changed"
    assert ("/StructTreeRoot" in reader.trailer["/Root"]) == ("/StructTreeRoot" in check.trailer["/Root"]), f"{path}: tags lost"
    assert len(check.outline) == len(reader.outline), f"{path}: bookmarks lost"
    reader.stream.close()
    check.stream.close()
    os.replace(tmp, path)
    return removed


def stamp_pptx(path: Path, title: str, subject: str) -> list[str]:
    from pptx import Presentation

    prs = Presentation(str(path))
    n = len(prs.slides)
    cp = prs.core_properties
    removed = []
    for name in ("author", "category", "comments", "content_status", "identifier", "keywords",
                 "language", "last_modified_by", "subject", "title", "version"):
        if _private(getattr(cp, name) or ""):
            setattr(cp, name, "")
            removed.append(name)
    cp.title, cp.author, cp.subject, cp.keywords = title, AUTHOR, subject, KEYWORDS
    cp.comments = f"{SI} {NOTE}"
    cp.last_modified_by = "ZENITH LABS"
    cp.category = "NASA Space Apps Challenge 2026 project demo"
    cp.language = "en-US"
    tmp = path.with_name(path.name + ".tmp")
    prs.save(str(tmp))
    assert len(Presentation(str(tmp)).slides) == n, f"{path}: slide count changed"
    os.replace(tmp, path)
    return removed


def read_back(path: Path) -> dict:
    if path.suffix.lower() == ".pptx":
        from pptx import Presentation

        cp = Presentation(str(path)).core_properties
        props = {k: getattr(cp, k) for k in ("title", "author", "subject", "keywords", "comments", "last_modified_by", "category")}
        with zipfile.ZipFile(path) as z:
            xml = "".join(z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.startswith("docProps/") and n.endswith(".xml"))
        props["_private_text_in_docProps"] = _private(re.sub(r'xmlns(:\w+)?="[^"]*"', "", xml).replace("http://", ""))
        return props
    from pypdf import PdfReader

    r = PdfReader(str(path))
    props = {k: str(v) for k, v in (r.metadata or {}).items()}
    meta = r.trailer["/Root"].get("/Metadata")
    xmp = meta.get_object().get_data().decode("utf-8", "replace") if meta is not None else ""
    props["_pages"] = len(r.pages)
    props["_xmp_has_si_statement"] = escape(SI) in xmp
    props["_private_text_in_xmp"] = _private(re.sub(r'xmlns:\w+="[^"]*"', "", xmp).replace("http://", ""))
    r.stream.close()
    return props


def verify(path: Path, title: str) -> bool:
    p = read_back(path)
    get = (lambda k: p.get(k.lower())) if path.suffix.lower() == ".pptx" else (lambda k: p.get("/" + k))
    ok = (get("Title") == title and get("Author") == AUTHOR and SI in (get("Comments") or "")
          and "SI-assisted" in (get("Keywords") or "") and bool(get("Subject"))
          and not any(_private(v) for k, v in p.items() if isinstance(v, str))
          and not p.get("_private_text_in_xmp") and not p.get("_private_text_in_docProps")
          and p.get("_xmp_has_si_statement", True))
    print(f"{'ok ' if ok else 'BAD'} {path.relative_to(ROOT).as_posix()}")
    for k, v in p.items():
        print(f"      {k}: {v}")
    return ok


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check_only = "--check" in sys.argv
    full = not args
    targets = {Path(a).resolve(): None for a in args} if args else dict.fromkeys(DOCS)
    bad = 0
    for path in targets:
        known = DOCS.get(path) or (DOCS[DECK] if path == SITE_COPY.resolve() else None)
        if known is None:
            print(f"skipped {path}: not one of the ParallaX documents")
            bad += 1
            continue
        if not path.is_file():
            print(f"missing {path.relative_to(ROOT).as_posix()}")
            bad += 1
            continue
        if not check_only:
            removed = (stamp_pptx if path.suffix.lower() == ".pptx" else stamp_pdf)(path, *known)
            if removed:
                print(f"   removed private properties from {path.name}: {removed}")
        bad += not verify(path, known[0])
    if full and DECK.is_file():
        if not check_only:
            shutil.copyfile(DECK, SITE_COPY)
            print(f"copied {DECK.relative_to(ROOT).as_posix()} -> {SITE_COPY.relative_to(ROOT).as_posix()}")
        if SITE_COPY.is_file():
            same = SITE_COPY.read_bytes() == DECK.read_bytes()
            print(f"{'ok ' if same else 'BAD'} site copy is {'identical to' if same else 'DIFFERENT from'} the deck PDF")
            bad += not same
        else:
            print("BAD site copy is missing")
            bad += 1
    print("all good" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
