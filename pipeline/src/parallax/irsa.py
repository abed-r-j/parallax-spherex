"""Access to SPHEREx Level-2 spectral images at NASA/IPAC IRSA.

Two things live here:

* ``list_images`` asks the IRSA TAP service which Level-2 images cover a sky position.
* ``remote_cutout`` pulls a small cutout out of a 65 MB Level-2 file with HTTP range
  requests, so only the needed pixel rows travel over the wire (about 0.5 MB instead of
  65 MB). The result has the same pixels as the IRSA cutout service, without the PSF HDU.

Data: SPHEREx Level-2 Spectral Images, NASA/IPAC Infrared Science Archive
(DR1 doi:10.26131/IRSA678, QR3 doi:10.26131/IRSA662).

SI disclosure: this file was written with the help of an SI coding assistant (Claude) and
reviewed by the team.
"""

from __future__ import annotations

import csv
import io
import re
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS, FITSFixedWarning

warnings.simplefilter("ignore", FITSFixedWarning)

TAP_SYNC = "https://irsa.ipac.caltech.edu/TAP/sync"
IRSA_ROOT = "https://irsa.ipac.caltech.edu/"
S3_ROOT = "https://nasa-irsa-spherex.s3.amazonaws.com/"
USER_AGENT = "ParallaX-SpaceApps2026/1.0 (SPHEREx blink comparator; research use)"
BLK = 2880


@dataclass(frozen=True)
class ImageRef:
    """One Level-2 detector image that covers the requested position."""

    uri: str  # site-relative, e.g. ibe/data/spherex/dr1/level2/.../level2_..._1D3_spx_....fits
    mjd_start: float
    mjd_end: float
    band: str  # SPHEREx-D1 .. SPHEREx-D6
    collection: str

    @property
    def name(self) -> str:
        return self.uri.rsplit("/", 1)[1]

    def url(self, mirror: str = "irsa") -> str:
        if self.uri.startswith("http"):
            return self.uri
        if mirror == "s3":
            return S3_ROOT + self.uri.split("ibe/data/spherex/", 1)[1]
        return IRSA_ROOT + self.uri


def list_images(ra: float, dec: float, timeout: float = 600.0) -> list[ImageRef]:
    """All SPHEREx Level-2 images whose footprint contains (ra, dec), oldest first."""
    adql = (
        "SELECT p.obs_publisher_did, p.time_bounds_lower, p.time_bounds_upper, "
        "p.energy_bandpassname, a.uri "
        "FROM spherex.plane AS p JOIN spherex.artifact AS a ON p.planeid = a.planeid "
        f"WHERE CONTAINS(POINT('ICRS', {ra:.6f}, {dec:.6f}), p.poly) = 1 "
        "ORDER BY p.time_bounds_lower"
    )
    r = httpx.get(
        TAP_SYNC,
        params={"QUERY": adql, "FORMAT": "CSV", "LANG": "ADQL", "MAXREC": 200000},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )
    r.raise_for_status()
    out: list[ImageRef] = []
    seen: set[str] = set()
    for row in csv.DictReader(io.StringIO(r.text)):
        uri = row["uri"].strip()
        if not uri or not uri.endswith(".fits") or uri in seen:
            continue
        seen.add(uri)
        did = row["obs_publisher_did"]
        m = re.search(r"spherex_[a-z0-9_]+", did)
        out.append(
            ImageRef(
                uri=uri,
                mjd_start=float(row["time_bounds_lower"]),
                mjd_end=float(row["time_bounds_upper"]),
                band=row["energy_bandpassname"].strip(),
                collection=m.group(0) if m else "unknown",
            )
        )
    return out


class _Counter:
    def __init__(self) -> None:
        self.bytes = 0
        self.requests = 0


def _get(c: httpx.Client, url: str, a: int, b: int, cnt: _Counter) -> httpx.Response:
    r = c.get(url, headers={"Range": f"bytes={a}-{b}"})
    r.raise_for_status()
    cnt.bytes += len(r.content)
    cnt.requests += 1
    return r


def _header_at(c: httpx.Client, url: str, off: int, guess: int, cnt: _Counter):
    """Read a FITS header that starts at byte ``off``. Returns (Header, header_nbytes)."""
    buf = b""
    while True:
        buf += _get(c, url, off + len(buf), off + len(buf) + guess - 1, cnt).content
        for i in range(0, len(buf), 80):
            if buf[i : i + 8] == b"END     ":
                n = ((i + 80 + BLK - 1) // BLK) * BLK
                return fits.Header.fromstring(buf[:n].decode("ascii")), n
        guess = BLK * 4


def _rows(c, url, data_off, x0, x1, y0, y1, nx_full, cnt, multirange) -> bytes:
    """Rows y0..y1-1, columns x0..x1-1 of a 4-byte image, as raw big-endian bytes."""
    rng = [
        (data_off + 4 * (y * nx_full + x0), data_off + 4 * (y * nx_full + x1) - 1)
        for y in range(y0, y1)
    ]
    if not multirange:  # one contiguous block (S3 does not support multi-range), then slice
        r = _get(c, url, rng[0][0] - 4 * x0, rng[-1][1] + 4 * (nx_full - x1), cnt)
        a = np.frombuffer(r.content, ">u4").reshape(y1 - y0, nx_full)[:, x0:x1]
        return a.tobytes()
    r = c.get(url, headers={"Range": "bytes=" + ",".join(f"{a}-{b}" for a, b in rng)})
    r.raise_for_status()
    cnt.bytes += len(r.content)
    cnt.requests += 1
    ctype = r.headers.get("Content-Type", "")
    m = re.search(r"boundary=(\S+)", ctype)
    if not m:  # server ignored multi-range
        raise RuntimeError("server did not return multipart/byteranges")
    bnd = b"--" + m.group(1).encode()
    out = [p.split(b"\r\n\r\n", 1)[1][: 4 * (x1 - x0)] for p in r.content.split(bnd)[1:-1]]
    if len(out) != len(rng):
        raise RuntimeError(f"expected {len(rng)} byte ranges, got {len(out)}")
    return b"".join(out)


def remote_cutout(
    url: str,
    ra: float,
    dec: float,
    size_pix: int,
    client: httpx.Client | None = None,
    multirange: bool = True,
) -> tuple[fits.HDUList, int]:
    """Cut ``size_pix`` x ``size_pix`` detector pixels around (ra, dec) out of a remote file.

    Returns (HDUList with PRIMARY, IMAGE, FLAGS, VARIANCE, ZODI, WCS-WAVE; bytes downloaded).
    CRPIX of the spatial WCS and of the alternate WCS 'A' and 'W' are shifted exactly as the
    IRSA cutout service does, so the wavelength lookup keeps working on the cutout.
    """
    own = client is None
    c = client or httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT})
    cnt = _Counter()
    try:
        r = _get(c, url, 0, 28799, cnt)
        total = int(r.headers["Content-Range"].split("/")[1])
        buf = r.content
        prim = buf[:BLK]
        end = next(i for i in range(BLK, len(buf), 80) if buf[i : i + 8] == b"END     ")
        nh = ((end + 80 - BLK + BLK - 1) // BLK) * BLK
        hdr = fits.Header.fromstring(buf[BLK : BLK + nh].decode("ascii"))
        nx_full, ny_full = hdr["NAXIS1"], hdr["NAXIS2"]
        img_off = BLK + nh
        img_size = ((nx_full * ny_full * 4 + BLK - 1) // BLK) * BLK
        px, py = WCS(hdr).all_world2pix(ra, dec, 0)
        half = size_pix // 2
        x0, y0 = int(round(float(px))) - half, int(round(float(py))) - half
        x1, y1 = min(nx_full, x0 + size_pix), min(ny_full, y0 + size_pix)
        x0, y0 = max(0, x0), max(0, y0)
        if x1 <= x0 or y1 <= y0:
            raise ValueError("position outside detector")
        nx, ny = x1 - x0, y1 - y0

        # FLAGS: tile-compressed (RICE_1), one tile per detector row.
        f_off = img_off + img_size
        fh, fn = _header_at(c, url, f_off, BLK * 7, cnt)
        f_data = f_off + fn
        f_tab = fh["NAXIS1"] * fh["NAXIS2"]
        f_size = ((f_tab + fh["PCOUNT"] + BLK - 1) // BLK) * BLK
        desc = np.frombuffer(
            _get(c, url, f_data + 8 * y0, f_data + 8 * y1 - 1, cnt).content, ">i4"
        ).reshape(ny, 2)
        h0 = int(desc[0, 1])
        h1 = int(desc[-1, 1] + desc[-1, 0])
        theap = fh.get("THEAP", f_tab)
        heap = _get(c, url, f_data + theap + h0, f_data + theap + h1 - 1, cnt).content
        d2 = desc.copy()
        d2[:, 1] -= h0
        fh2 = fh.copy()
        fh2["NAXIS2"] = ny
        fh2["ZNAXIS2"] = ny
        fh2["PCOUNT"] = len(heap)
        fh2.pop("THEAP", None)
        body = d2.astype(">i4").tobytes() + heap
        body += b"\0" * (-len(body) % BLK)
        with fits.open(io.BytesIO(prim + fh2.tostring().encode("ascii") + body)) as ff:
            flags = ff[1].data[:, x0:x1].copy()

        v_off = f_data + f_size
        vh, vn = _header_at(c, url, v_off, BLK * 5, cnt)
        z_off = v_off + vn + img_size
        zh, zn = _header_at(c, url, z_off, BLK * 5, cnt)
        shape = (ny, nx)
        img = np.frombuffer(
            _rows(c, url, img_off, x0, x1, y0, y1, nx_full, cnt, multirange), ">f4"
        ).reshape(shape)
        var = np.frombuffer(
            _rows(c, url, v_off + vn, x0, x1, y0, y1, nx_full, cnt, multirange), ">f4"
        ).reshape(shape)
        zod = np.frombuffer(
            _rows(c, url, z_off + zn, x0, x1, y0, y1, nx_full, cnt, multirange), ">f4"
        ).reshape(shape)

        # WCS-WAVE is the last HDU: 2880-byte header + 2880 bytes of data.
        tail = _get(c, url, total - 2 * BLK, total - 1, cnt).content
        with fits.open(io.BytesIO(prim + tail)) as tf:
            wave = fits.BinTableHDU(tf[1].data.copy(), tf[1].header.copy())
        if wave.header.get("EXTNAME") != "WCS-WAVE":
            raise RuntimeError(f"last HDU is {wave.header.get('EXTNAME')!r}, not WCS-WAVE")

        def shift(h: fits.Header) -> fits.Header:
            h = h.copy()
            for k in ("", "A", "W"):
                if f"CRPIX1{k}" in h:
                    h[f"CRPIX1{k}"] = h[f"CRPIX1{k}"] - x0
                    h[f"CRPIX2{k}"] = h[f"CRPIX2{k}"] - y0
            return h

        fhi = fits.ImageHDU(flags).header
        skip = ("Z", "TTYPE", "TFORM", "TFIELDS", "PCOUNT", "GCOUNT", "THEAP", "NAXIS",
                "BITPIX", "XTENSION", "COMMENT", "HISTORY")
        for k, v in fh.items():
            if k and k not in fhi and not k.startswith(skip):
                fhi[k] = v
        hl = fits.HDUList(
            [
                fits.PrimaryHDU(header=fits.Header.fromstring(prim.decode("ascii"))),
                fits.ImageHDU(img, shift(hdr)),
                fits.ImageHDU(flags, shift(fhi), name="FLAGS"),
                fits.ImageHDU(var, shift(vh)),
                fits.ImageHDU(zod, shift(zh)),
                wave,
            ]
        )
        hl[1].header["SRCFILE"] = (url.rsplit("/", 1)[1][:68], "source Level-2 file")
        hl[1].header["CUTX0"] = (x0, "0-based detector x of cutout origin")
        hl[1].header["CUTY0"] = (y0, "0-based detector y of cutout origin")
        return hl, cnt.bytes
    finally:
        if own:
            c.close()


def fetch_field(
    ra: float,
    dec: float,
    size_pix: int,
    out_dir: Path,
    threads: int = 6,
    max_images: int | None = None,
    mirror: str = "irsa",
    progress=print,
) -> dict:
    """Download a cutout of every Level-2 image covering (ra, dec) into ``out_dir``.

    Already-downloaded files are skipped, so the call can be repeated to pick up newly
    released data. If ``max_images`` is set and more images exist, an evenly spaced
    subset in time is taken (and the number dropped is reported).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    refs = list_images(ra, dec)
    n_all = len(refs)
    if max_images and n_all > max_images:
        idx = np.unique(np.linspace(0, n_all - 1, max_images).round().astype(int))
        refs = [refs[i] for i in idx]
        progress(f"{n_all} images cover the position; keeping {len(refs)} evenly spaced in time")
    local = threading.local()

    def client() -> httpx.Client:
        if not hasattr(local, "c"):
            local.c = httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT})
        return local.c

    def one(ref: ImageRef) -> tuple[str, int, str]:
        fn = out_dir / ref.name.replace(".fits", f"_cut{size_pix}.fits")
        if fn.exists():
            return ref.name, 0, ""
        err = ""
        for attempt in range(4):
            try:
                hl, nb = remote_cutout(
                    ref.url(mirror), ra, dec, size_pix, client=client(),
                    multirange=(mirror == "irsa"),
                )
                hl[1].header["COLLECT"] = (ref.collection, "IRSA collection")
                tmp = fn.with_suffix(".tmp")
                hl.writeto(tmp, overwrite=True)
                tmp.replace(fn)
                return ref.name, nb, ""
            except ValueError as e:  # position falls off this detector: not an error
                return ref.name, 0, f"skip: {e}"
            except Exception as e:  # network trouble: back off and retry
                err = f"{type(e).__name__}: {str(e)[:120]}"
                time.sleep(3 * (attempt + 1))
        return ref.name, 0, err

    t0 = time.time()
    done = nbytes = 0
    failed: list[tuple[str, str]] = []
    with ThreadPoolExecutor(threads) as ex:
        for name, nb, err in ex.map(one, refs):
            done += 1
            nbytes += nb
            if err and not err.startswith("skip"):
                failed.append((name, err))
            if done % 25 == 0 or done == len(refs):
                progress(f"  {done}/{len(refs)}  {time.time() - t0:.0f}s  {nbytes / 1e6:.1f} MB")
    return {
        "n_available": n_all,
        "n_requested": len(refs),
        "n_failed": len(failed),
        "failed": failed,
        "seconds": time.time() - t0,
        "bytes": nbytes,
    }
