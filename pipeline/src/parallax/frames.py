"""Turn a folder of SPHEREx Level-2 cutouts into one aligned data cube.

Every Level-2 image is a single 2-D exposure taken through a linear variable filter, so
*each pixel has its own wavelength*. ``build_field`` resamples every cutout onto one
north-up tangent-plane grid and carries the per-pixel wavelength and bandwidth along, so
that later steps can compare like with like.

The result is a :class:`Field`: arrays of shape (n_frames, n, n) plus one row of
metadata per frame.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS, FITSFixedWarning

warnings.simplefilter("ignore", FITSFixedWarning)

PIXEL_ARCSEC = 6.15

# SPHEREx Level-2 FLAGS bit numbers (SPHEREx Explanatory Supplement, "Flags").
FLAG_BITS = {
    "TRANSIENT": 0,
    "OVERFLOW": 1,
    "SUR_ERROR": 2,
    "NONFUNC": 6,
    "DICHROIC": 7,
    "MISSING_DATA": 9,
    "HOT": 10,
    "COLD": 11,
    "FULLSAMPLE": 12,
    "PHANMISS": 14,
    "NONLINEAR": 15,
    "PERSIST": 17,
    "OUTLIER": 19,
    "SOURCE": 21,
}


def bitmask(*names: str) -> int:
    return int(sum(1 << FLAG_BITS[n] for n in names))


# Pixels that carry no usable measurement at all.
BAD_HARD = bitmask("SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD", "PHANMISS")
# Pixels that are measured but suspect. They stay visible, but never feed a template.
# OUTLIER is deliberately *not* removed from the image being searched: a real moving
# object is, by construction, an outlier with respect to the other visits.
BAD_SOFT = bitmask("TRANSIENT", "OVERFLOW", "DICHROIC", "NONLINEAR", "PERSIST", "OUTLIER")
SOURCE = bitmask("SOURCE")

CAMPAIGN_GAP_DAYS = 30.0


@dataclass
class Field:
    """All SPHEREx frames of one sky patch on a common grid."""

    ra0: float
    dec0: float
    n: int
    scale: float  # arcsec per pixel
    img: np.ndarray  # (N, n, n) MJy/sr, zodiacal light and residual sky removed
    var: np.ndarray  # (N, n, n) MJy^2/sr^2
    lam: np.ndarray  # (N, n, n) micron, wavelength seen by each pixel
    bw: np.ndarray  # (N, n, n) micron, filter bandwidth at each pixel
    flags: np.ndarray  # (N, n, n) int32, OR of the flags of contributing pixels
    mjd: np.ndarray  # (N,)
    det: np.ndarray  # (N,) 1..6
    campaign: np.ndarray  # (N,) 0-based index of the survey pass
    sky: np.ndarray  # (N,) residual sky level removed, MJy/sr
    zodi: np.ndarray  # (N,) median zodiacal model removed, MJy/sr
    psf_fwhm: np.ndarray  # (N,) arcsec, from the header (nan if absent)
    sc_xyz: np.ndarray  # (N, 3) geocentric spacecraft position, km
    names: list[str] = field(default_factory=list)
    obsid: list[str] = field(default_factory=list)
    collection: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.mjd)

    @property
    def wcs(self) -> WCS:
        return grid_wcs(self.ra0, self.dec0, self.n, self.scale)

    @property
    def lam0(self) -> np.ndarray:
        """Wavelength at the field centre for each frame."""
        c = self.n // 2
        return self.lam[:, c, c]

    def save(self, path: Path) -> None:
        np.savez_compressed(
            path, ra0=self.ra0, dec0=self.dec0, n=self.n, scale=self.scale, img=self.img,
            var=self.var, lam=self.lam, bw=self.bw, flags=self.flags, mjd=self.mjd,
            det=self.det, campaign=self.campaign, sky=self.sky, zodi=self.zodi,
            psf_fwhm=self.psf_fwhm, sc_xyz=self.sc_xyz, names=np.array(self.names),
            obsid=np.array(self.obsid), collection=np.array(self.collection),
        )

    @classmethod
    def load(cls, path: Path) -> Field:
        z = np.load(path, allow_pickle=False)
        return cls(
            ra0=float(z["ra0"]), dec0=float(z["dec0"]), n=int(z["n"]), scale=float(z["scale"]),
            img=z["img"], var=z["var"], lam=z["lam"], bw=z["bw"], flags=z["flags"],
            mjd=z["mjd"], det=z["det"], campaign=z["campaign"], sky=z["sky"], zodi=z["zodi"],
            psf_fwhm=z["psf_fwhm"], sc_xyz=z["sc_xyz"], names=[str(s) for s in z["names"]],
            obsid=[str(s) for s in z["obsid"]], collection=[str(s) for s in z["collection"]],
        )

    def select(self, keep: np.ndarray) -> Field:
        keep = np.asarray(keep)
        idx = np.flatnonzero(keep) if keep.dtype == bool else keep
        return Field(
            self.ra0, self.dec0, self.n, self.scale, self.img[idx], self.var[idx],
            self.lam[idx], self.bw[idx], self.flags[idx], self.mjd[idx], self.det[idx],
            self.campaign[idx], self.sky[idx], self.zodi[idx], self.psf_fwhm[idx],
            self.sc_xyz[idx], [self.names[i] for i in idx], [self.obsid[i] for i in idx],
            [self.collection[i] for i in idx],
        )


def grid_wcs(ra0: float, dec0: float, n: int, scale: float = PIXEL_ARCSEC) -> WCS:
    """North-up, east-left gnomonic grid of n x n pixels centred on (ra0, dec0)."""
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra0, dec0]
    w.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
    w.wcs.cdelt = [-scale / 3600.0, scale / 3600.0]
    return w


def wavelength_at(wave_hdu, header, px: np.ndarray, py: np.ndarray):
    """Wavelength and bandwidth (micron) at 0-based cutout pixel coordinates (px, py).

    The WCS-WAVE table holds wavelength and bandwidth on a coarse grid of control points
    in full-detector pixel coordinates; the alternate WCS 'W' in the image header says
    where the cutout sits on the detector. We interpolate bilinearly, as the FITS -TAB
    convention prescribes.
    """
    xd = header["CRVAL1W"] + (np.asarray(px, float) + 1.0 - header["CRPIX1W"])
    yd = header["CRVAL2W"] + (np.asarray(py, float) + 1.0 - header["CRPIX2W"])
    row = wave_hdu.data
    gx = np.asarray(row["X"][0], float)
    gy = np.asarray(row["Y"][0], float)
    vals = np.asarray(row["VALUES"][0], float)  # (ny_ctrl, nx_ctrl, 2)
    ix = np.clip(np.searchsorted(gx, xd) - 1, 0, len(gx) - 2)
    iy = np.clip(np.searchsorted(gy, yd) - 1, 0, len(gy) - 2)
    tx = (xd - gx[ix]) / (gx[ix + 1] - gx[ix])
    ty = (yd - gy[iy]) / (gy[iy + 1] - gy[iy])
    out = []
    for k in (0, 1):
        v = vals[:, :, k]
        out.append(
            v[iy, ix] * (1 - tx) * (1 - ty) + v[iy, ix + 1] * tx * (1 - ty)
            + v[iy + 1, ix] * (1 - tx) * ty + v[iy + 1, ix + 1] * tx * ty
        )
    return out[0], out[1]


def _bilinear(px, py, shape):
    """Indices and weights of the four neighbours of fractional pixel positions."""
    x0 = np.floor(px).astype(int)
    y0 = np.floor(py).astype(int)
    fx, fy = px - x0, py - y0
    inside = (x0 >= 0) & (y0 >= 0) & (x0 + 1 < shape[1]) & (y0 + 1 < shape[0])
    x0c = np.clip(x0, 0, shape[1] - 2)
    y0c = np.clip(y0, 0, shape[0] - 2)
    nb = [
        (y0c, x0c, (1 - fx) * (1 - fy)),
        (y0c, x0c + 1, fx * (1 - fy)),
        (y0c + 1, x0c, (1 - fx) * fy),
        (y0c + 1, x0c + 1, fx * fy),
    ]
    return nb, inside


def resample_cutout(hdul, target: WCS, n: int):
    """Resample one cutout onto the common grid. Returns img, var, lam, bw, flags."""
    hdr = hdul["IMAGE"].header
    img = hdul["IMAGE"].data.astype(np.float64)
    var = hdul["VARIANCE"].data.astype(np.float64)
    zod = hdul["ZODI"].data.astype(np.float64)
    flg = hdul["FLAGS"].data.astype(np.int64)
    yy, xx = np.mgrid[0:n, 0:n]
    ra, dec = target.all_pix2world(xx, yy, 0)
    px, py = WCS(hdr).all_world2pix(ra, dec, 0, quiet=True)
    nb, inside = _bilinear(px, py, img.shape)
    good = np.isfinite(img) & np.isfinite(var) & (var > 0) & ((flg & BAD_HARD) == 0)
    sig = np.where(good, img - zod, 0.0)
    v = np.where(good, var, 0.0)
    num = np.zeros((n, n))
    wsum = np.zeros((n, n))
    vnum = np.zeros((n, n))
    fl = np.zeros((n, n), dtype=np.int64)
    for iy, ix, w in nb:
        g = good[iy, ix]
        num += w * sig[iy, ix] * g
        vnum += (w * g) ** 2 * v[iy, ix]
        wsum += w * g
        fl |= np.where(w > 0.05, flg[iy, ix], 0)
    ok = inside & (wsum > 0.75)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(ok, num / wsum, np.nan)
        vout = np.where(ok, vnum / wsum**2, np.nan)
    lam, bw = wavelength_at(hdul["WCS-WAVE"], hdr, px, py)
    lam = np.where(inside, lam, np.nan)
    bw = np.where(inside, bw, np.nan)
    return out, vout, lam, bw, fl.astype(np.int32), float(np.nanmedian(zod))


def _sky_level(img: np.ndarray, flags: np.ndarray) -> float:
    """Residual sky after zodiacal-model subtraction: clipped median of source-free pixels."""
    ok = np.isfinite(img)
    free = ok & ((flags & (SOURCE | BAD_SOFT | BAD_HARD)) == 0)
    v = img[free] if free.sum() >= 50 else img[ok]
    if v.size == 0:
        return 0.0
    if free.sum() < 50:  # crowded field: use the faint end of the distribution
        return float(np.percentile(v, 20))
    for _ in range(3):
        med = np.median(v)
        mad = 1.4826 * np.median(np.abs(v - med)) + 1e-12
        v = v[np.abs(v - med) < 3 * mad]
    return float(np.median(v))


def assign_campaigns(mjd: np.ndarray, gap: float = CAMPAIGN_GAP_DAYS) -> np.ndarray:
    """Group exposures into survey passes: a new pass starts after a gap of ``gap`` days."""
    order = np.argsort(mjd)
    out = np.zeros(len(mjd), dtype=np.int16)
    c = 0
    for a, b in zip(order[:-1], order[1:], strict=False):
        if mjd[b] - mjd[a] > gap:
            c += 1
        out[b] = c
    return out


def build_field(raw_dir: Path, ra0: float, dec0: float, n: int, min_coverage: float = 0.6,
                progress=None) -> Field:
    """Read every cutout in ``raw_dir`` and stack them on one grid, sorted by time."""
    target = grid_wcs(ra0, dec0, n)
    rows = []
    files = sorted(Path(raw_dir).glob("*.fits"))
    for i, fn in enumerate(files):
        try:
            with fits.open(fn) as h:
                hdr = h["IMAGE"].header
                img, var, lam, bw, fl, zmed = resample_cutout(h, target, n)
        except Exception as e:  # a truncated download must not stop the whole field
            if progress:
                progress(f"skipping {fn.name}: {type(e).__name__}: {e}")
            continue
        if np.isfinite(img).mean() < min_coverage:
            continue  # the patch falls mostly off this detector
        sky = _sky_level(img, fl)
        rows.append(
            dict(
                img=(img - sky).astype(np.float32), var=var.astype(np.float32),
                lam=lam.astype(np.float32), bw=bw.astype(np.float32), flags=fl,
                mjd=float(hdr["MJD-AVG"]), det=int(hdr["DETECTOR"]), sky=sky, zodi=zmed,
                fwhm=float(hdr.get("PSF_FWHM", np.nan) or np.nan),
                xyz=[float(hdr.get(k, np.nan)) for k in ("X_SC", "Y_SC", "Z_SC")],
                name=str(hdr.get("SRCFILE", fn.name)), obsid=str(hdr.get("OBSID", "")),
                coll=str(hdr.get("COLLECT", "")),
            )
        )
        if progress and (i + 1) % 100 == 0:
            progress(f"  resampled {i + 1}/{len(files)}")
    if not rows:
        raise RuntimeError(f"no usable cutouts in {raw_dir}")
    rows.sort(key=lambda r: (r["mjd"], r["det"]))
    mjd = np.array([r["mjd"] for r in rows])
    return Field(
        ra0=ra0, dec0=dec0, n=n, scale=PIXEL_ARCSEC,
        img=np.stack([r["img"] for r in rows]), var=np.stack([r["var"] for r in rows]),
        lam=np.stack([r["lam"] for r in rows]), bw=np.stack([r["bw"] for r in rows]),
        flags=np.stack([r["flags"] for r in rows]), mjd=mjd,
        det=np.array([r["det"] for r in rows], dtype=np.int16),
        campaign=assign_campaigns(mjd), sky=np.array([r["sky"] for r in rows]),
        zodi=np.array([r["zodi"] for r in rows]),
        psf_fwhm=np.array([r["fwhm"] for r in rows]),
        sc_xyz=np.array([r["xyz"] for r in rows]),
        names=[r["name"] for r in rows], obsid=[r["obsid"] for r in rows],
        collection=[r["coll"] for r in rows],
    )
