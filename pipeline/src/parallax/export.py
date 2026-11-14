"""Write a :class:`~parallax.frames.Field` as a static data pack for the web app.

The format is specified in ``docs/DATA_CONTRACT.md``. Optional products (templates,
signal-to-noise cubes, overlays, detections, science blocks) are passed in by the caller
and simply recorded; this module does no science.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from astropy.time import Time
from PIL import Image

from . import __version__
from .frames import BAD_HARD, BAD_SOFT, FLAG_BITS, SOURCE, Field

DOI = {
    "spherex_dr1": "10.26131/IRSA678",
    "spherex_dr1_deep": "10.26131/IRSA678",
    "spherex_qr3": "10.26131/IRSA662",
    "spherex_qr3_deep": "10.26131/IRSA662",
    "spherex_qr2": "10.26131/IRSA652",
}


def _clean(o):
    """Make numpy values JSON-safe; NaN and infinities become null."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if np.isfinite(f) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def _round(a, nd):
    return [None if not np.isfinite(v) else round(float(v), nd) for v in np.asarray(a, float)]


def encode_brightness(v: np.ndarray, soft: float, lo: float, hi: float) -> np.ndarray:
    t = (np.arcsinh(np.nan_to_num(v, nan=0.0) / soft) - lo) / (hi - lo)
    q = 1 + np.rint(np.clip(t, 0, 1) * 65534)
    return np.where(np.isfinite(v), q, 0).astype("<u2")


def decode_brightness(q: np.ndarray, soft: float, lo: float, hi: float) -> np.ndarray:
    v = soft * np.sinh(lo + (q.astype(np.float64) - 1) / 65534 * (hi - lo))
    return np.where(q == 0, np.nan, v)


def encode_snr(s: np.ndarray) -> np.ndarray:
    q = np.clip(np.rint(np.nan_to_num(s, nan=0.0) * 4), -127, 127)
    return np.where(np.isfinite(s), q, -128).astype("i1")


def web_flags(flags: np.ndarray, img: np.ndarray) -> np.ndarray:
    out = np.zeros(flags.shape, dtype=np.uint8)
    out |= np.where(~np.isfinite(img) | ((flags & BAD_HARD) != 0), 1, 0).astype(np.uint8)
    soft = BAD_SOFT & ~(1 << FLAG_BITS["OUTLIER"])
    out |= np.where((flags & soft) != 0, 2, 0).astype(np.uint8)
    out |= np.where((flags & SOURCE) != 0, 4, 0).astype(np.uint8)
    out |= np.where((flags & (1 << FLAG_BITS["OUTLIER"])) != 0, 8, 0).astype(np.uint8)
    return out


def campaign_stacks(f: Field) -> np.ndarray:
    """Inverse-variance mean per survey pass and detector, shape (C, 6, n, n)."""
    ncamp = int(f.campaign.max()) + 1
    out = np.full((ncamp, 6, f.n, f.n), np.nan, dtype="<f4")
    usable = np.isfinite(f.img) & np.isfinite(f.var) & (f.var > 0) & ((f.flags & BAD_SOFT) == 0)
    for c in range(ncamp):
        for d in range(1, 7):
            sel = (f.campaign == c) & (f.det == d)
            if not sel.any():
                continue
            w = np.where(usable[sel], 1.0 / np.where(usable[sel], f.var[sel], 1.0), 0.0)
            num = (w * np.nan_to_num(f.img[sel])).sum(0)
            den = w.sum(0)
            with np.errstate(invalid="ignore", divide="ignore"):
                out[c, d - 1] = np.where(den > 0, num / den, np.nan)
    return out


def lam_fits(f: Field) -> list[list[float]]:
    """Plane fit lambda(x, y) = a + bx (x - c) + by (y - c) per frame."""
    c = (f.n - 1) / 2
    yy, xx = np.mgrid[0 : f.n, 0 : f.n]
    out = []
    for lam in f.lam:
        ok = np.isfinite(lam)
        if ok.sum() < 3:
            out.append([None, 0.0, 0.0])
            continue
        a = np.column_stack([np.ones(ok.sum()), xx[ok] - c, yy[ok] - c])
        coef, *_ = np.linalg.lstsq(a, lam[ok].astype(float), rcond=None)
        out.append([round(float(coef[0]), 6), round(float(coef[1]), 8), round(float(coef[2]), 8)])
    return out


def thumbnail(f: Field, path: Path, size: int = 192) -> None:
    """Small preview: median of the best-populated detector, asinh stretch."""
    dets, counts = np.unique(f.det, return_counts=True)
    d = dets[np.argmax(counts)]
    with np.errstate(all="ignore"):
        im = np.nanmedian(f.img[f.det == d], axis=0)
    lo, hi = np.nanpercentile(im, [10, 99.7])
    t = np.arcsinh(np.clip((np.nan_to_num(im, nan=lo) - lo) / (hi - lo + 1e-12), 0, None) * 12)
    t = (255 * t / (t.max() + 1e-12)).astype(np.uint8)
    Image.fromarray(t[::-1]).resize((size, size), Image.NEAREST).save(path)


def write_pack(
    f: Field,
    out_root: Path,
    key: str,
    name: str,
    kind: str,
    blurb: str = "",
    target: dict | None = None,
    extra_sections: dict[str, np.ndarray] | None = None,
    frame_extras: dict[str, list] | None = None,
    blocks: dict | None = None,
) -> dict:
    """Write ``<out_root>/<key>/{meta.json,cube.bin,thumb.png}`` and return the index entry.

    ``extra_sections`` maps a section name (``tpl``, ``snrCorr``, ``snrNaive``,
    ``snrGated``) to an already-encoded array. ``frame_extras`` adds per-frame lists
    (``naivePartner``, ``gatedPartner``, ``nRef``). ``blocks`` adds top-level blocks
    (``gaia``, ``wise``, ``sso``, ``detections``, ``candidates``, ``science``, ``ledger``).
    """
    out = Path(out_root) / key
    out.mkdir(parents=True, exist_ok=True)
    finite = f.img[np.isfinite(f.img)]
    sigma = np.sqrt(np.nanmedian(f.var.reshape(len(f), -1), axis=1))
    soft = float(max(np.nanmedian(sigma), 1e-4))
    lo = float(np.arcsinh(finite.min() / soft))  # the true minimum: nothing finite is clipped
    hi = float(np.arcsinh(finite.max() / soft))
    sections: dict[str, np.ndarray] = {
        "img": encode_brightness(f.img, soft, lo, hi),
        "flags": web_flags(f.flags, f.img),
        "stack": campaign_stacks(f),
    }
    for k, v in (extra_sections or {}).items():
        sections[k] = v
    sec_meta, offset = {}, 0
    with open(out / "cube.bin", "wb") as fh:
        for k, a in sections.items():
            a = np.ascontiguousarray(a)
            dt = a.dtype.newbyteorder("<") if a.dtype.itemsize > 1 else a.dtype
            b = a.astype(dt, copy=False).tobytes()
            pad = (-offset) % 4  # keep every section 4-byte aligned for typed arrays
            fh.write(b"\0" * pad)
            offset += pad
            sec_meta[k] = {"offset": offset, "dtype": a.dtype.name, "shape": list(a.shape)}
            fh.write(b)
            offset += len(b)
    iso = Time(f.mjd, format="mjd").isot
    ncamp = int(f.campaign.max()) + 1
    c = f.n // 2
    frames = {
        "mjd": _round(f.mjd, 6),
        "iso": [s[:19] for s in iso],
        "det": f.det.tolist(),
        "campaign": f.campaign.tolist(),
        "lam": _round(f.lam[:, c, c], 5),
        "bw": _round(f.bw[:, c, c], 5),
        "lamFit": lam_fits(f),
        "sigma": _round(sigma, 5),
        "sky": _round(f.sky, 5),
        "zodi": _round(f.zodi, 5),
        "fwhm": _round(f.psf_fwhm, 2),
        "name": f.names,
        "collection": f.collection,
    }
    frames.update(frame_extras or {})
    colls = sorted(set(f.collection) - {""})
    meta = {
        "key": key, "name": name, "kind": kind, "blurb": blurb,
        "ra0": f.ra0, "dec0": f.dec0, "n": f.n, "scale": f.scale,
        "target": target,
        "release": {
            "collections": colls,
            "doi": sorted({DOI[c] for c in colls if c in DOI}),
            "retrieved": datetime.now(UTC).strftime("%Y-%m-%d"),
        },
        "encoding": {"soft": soft, "lo": lo, "hi": hi},
        "sections": sec_meta,
        "frames": frames,
        "campaigns": [
            {
                "index": i,
                "start": sorted(iso[f.campaign == i].tolist())[0][:10],
                "end": sorted(iso[f.campaign == i].tolist())[-1][:10],
                "nFrames": int((f.campaign == i).sum()),
            }
            for i in range(ncamp)
        ],
        "gaia": [], "wise": [], "sso": [], "detections": [], "candidates": [],
        "science": {}, "ledger": {},
    }
    meta.update(blocks or {})
    (out / "meta.json").write_text(json.dumps(_clean(meta), separators=(",", ":")))
    thumbnail(f, out / "thumb.png")
    return {
        "key": key, "name": name, "kind": kind, "ra": round(f.ra0, 6), "dec": round(f.dec0, 6),
        "n": f.n, "scale": f.scale, "nFrames": len(f), "nCampaigns": ncamp, "blurb": blurb,
        "thumb": f"{key}/thumb.png",
    }


def write_index(out_root: Path, entries: list[dict]) -> None:
    doc = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline": __version__,
        "fields": entries,
    }
    (Path(out_root) / "index.json").write_text(json.dumps(_clean(doc), indent=1))
