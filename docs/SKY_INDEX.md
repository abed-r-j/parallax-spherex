# ParallaX static sky index (format version 1)

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.

The sky index answers one question without any server: **which SPHEREx Level-2 images
contain a given RA/Dec, when were they taken, and what is the S3 URL of each?**

It exists because the public site is static and a browser cannot query NASA/IPAC IRSA
(no CORS), while the public bucket `https://nasa-irsa-spherex.s3.amazonaws.com/` does
allow cross-origin GET requests with `Range`. The index is a copy of the geometry and
file-name columns of the IRSA image catalogue, cut into small binary files.

- Builder and Python reader: `pipeline/src/parallax/skyindex.py`
- Command: `pipeline/scripts/build_sky_index.py`
- Output folder: `web/public/skyindex/` (served as `<site>/skyindex/`)
- Tests: `pipeline/tests/test_skyindex.py`

Data credit: SPHEREx Level-2 Spectral Images, NASA/IPAC Infrared Science Archive,
DR1 doi:10.26131/IRSA678 and QR3 doi:10.26131/IRSA662.

This document is the complete specification. A client needs nothing else.

---

## 1. Files

```
skyindex/
  manifest.json            small JSON, read first
  b00/ ... b35/            one folder per declination band (only bands that hold data)
    cCCC_PPP.bin           shard: band BB, RA cell CCC, time part PPP
```

A shard file name is `b{band:02d}/c{cell:03d}_{part:03d}.bin` (zero-padded decimal), also
given as `shard_template` in the manifest. A shard is a plain array of fixed-width
records with **no header**: `file size = 28 * count`.

All images whose footprint **centre** falls in one sky cell are in that cell's shards.
Within a cell the records are sorted by time (oldest first) and cut into parts of at
most `part_max_records` = 16384 records (458,752 bytes). Part 000 is the oldest.

## 2. `manifest.json`

| key | meaning |
|---|---|
| `format`, `version` | `"parallax-skyindex"`, `1`. Refuse anything else. |
| `built_utc` | build time, ISO 8601. Use it as a cache-busting query string for shard URLs. |
| `s3_root` | `"https://nasa-irsa-spherex.s3.amazonaws.com/"` |
| `key_template` | how an S3 key is assembled, see section 5 |
| `shard_template` | `"b{band:02d}/c{cell:03d}_{part:03d}.bin"` |
| `record` | `size` (28), `byte_order` (`"little"`), `fields` (name, byte offset, dtype) and `id_bits` (first bit, bit count); the same information as section 3 |
| `units` | `deg_per_count` 1e-7, `tan_rad_per_count` 1.6e-6, `mjd_epoch` 60000, `days_per_count` 1e-6 |
| `grid` | `band_height_deg` (5) and `cells_per_band` (36 integers, south to north) |
| `search_radius_deg` | radius R of the shard-selection rule, section 4 |
| `max_centre_to_corner_deg` | largest centre-to-corner distance found in the data (R is this plus a small margin) |
| `part_max_records` | 16384 |
| `collections` | array of collection names, e.g. `["spherex_dr1","spherex_dr1_deep","spherex_qr3","spherex_qr3_deep"]` |
| `prefixes` | array of `[collection_index, release, period, procver]`, e.g. `[0,"dr1","2025W17_4B","l2b-v27-2026-196"]`; a record points into this array |
| `doi` | `{"dr1":"10.26131/IRSA678","qr3":"10.26131/IRSA662"}`, keyed by `release` |
| `rows` | `total` and, per collection, `indexed`, `mjd_min`, `mjd_max`, `archive_rows_at_dump` |
| `coverage` | `days_cached`, `days_in_archive_span`, `missing_days` (MJD days not downloaded yet), `complete` (true when nothing is missing) |
| `quality` | counts of rows skipped and the largest corner rounding error in arcsec |
| `shards` | array of `[band, cell, part, count, mjd_min, mjd_max]`, one entry per shard file, sorted by band, cell, part |

A cell that has no entry in `shards` holds no images: do not request it.

## 3. Record layout (28 bytes, little-endian, no padding)

| offset | type | name | meaning |
|---:|---|---|---|
| 0 | uint32 | `ra` | centre right ascension = `ra * 1e-7` degrees, 0 <= value < 360 |
| 4 | int32 | `dec` | centre declination = `dec * 1e-7` degrees |
| 8 | int16 | `x1` | corner 1, tangent-plane east offset, in counts |
| 10 | int16 | `y1` | corner 1, tangent-plane north offset, in counts |
| 12 | int16 | `x2` | corner 2 east |
| 14 | int16 | `y2` | corner 2 north |
| 16 | int16 | `x3` | corner 3 east |
| 18 | int16 | `y3` | corner 3 north |
| 20 | uint32 | `t` | exposure start: `MJD = 60000 + t * 1e-6` (TDB-free plain MJD as published by IRSA in `time_bounds_lower` / `t_min`) |
| 24 | uint32 | `id` | bit field, see below |

`id` bits (bit 0 is the least significant):

| bits | width | name | meaning |
|---|---:|---|---|
| 0-2 | 3 | `det_minus_1` | detector number minus 1 (0..5), detector = band `SPHEREx-D1`..`D6` |
| 3-5 | 3 | `suffix` | last number of the observation id (1..4 so far) |
| 6-17 | 12 | `seq` | four-digit sequence number of the observation id (0..4095) |
| 18-31 | 14 | `prefix` | index into `manifest.prefixes` |

In JavaScript: `det = (id & 7) + 1; suffix = (id >>> 3) & 7; seq = (id >>> 6) & 0xFFF;
prefix = id >>> 18;` (read `id` with `DataView.getUint32(offset + 24, true)`).

### Corners and the fourth corner

Corner offsets are gnomonic (tangent-plane) coordinates about the record centre:
one count is `1.6e-6` radian of tangent-plane distance (0.33 arcsec), `x` towards
increasing RA (east), `y` towards increasing Dec (north). The footprint is the
quadrilateral corner 1 -> 2 -> 3 -> 4 -> 1 in that order (the order of IRSA's polygon).

**The fourth corner is not stored.** The centre is defined as the point about which the
four corner offsets sum to zero, so

```
x4 = -(x1 + x2 + x3)        y4 = -(y1 + y2 + y3)
```

(integer arithmetic, exact by construction; the result always fits int16.) The centre
is therefore the mean of the corners in the tangent plane, about 1 arcsec or less from
IRSA's `s_ra`, `s_dec`; it is a centre for this index, not a replacement for the WCS.

Rounding: each stored corner is within 0.24 arcsec of IRSA's corner, the derived fourth
corner within about 0.7 arcsec (0.1 SPHEREx pixel; pixels are 6.15 arcsec). The exact
worst case of a build is `quality.max_corner_error_arcsec`.

Orientation, if wanted: the position angle of the edge corner 1 -> corner 2 is
`atan2(x2 - x1, y2 - y1)` (east of north). Which corner is detector pixel (0, 0) is not
stated by IRSA's polygon; read the image WCS for pixel work.

## 4. Which shards to read for a position (shard selection)

The sky is cut into `NB = 180 / band_height_deg = 36` declination bands of 5 degrees;
band `b` covers `-90 + 5b <= Dec < -90 + 5(b+1)` (the last band includes Dec = +90).
Band `b` is cut into `n = cells_per_band[b]` equal RA cells of width `w = 360 / n`
degrees; cell `k` covers `k*w <= RA < (k+1)*w`. Always take `n` from the manifest.

A footprint is about 3.5 x 3.5 degrees, so its centre can be up to
`R = search_radius_deg` (about 2.56 degrees) from a point it contains. To find every
image containing the point (RA, Dec), read every cell that a disc of radius R about the
point can touch. Rule (all angles in degrees, `floor` rounds towards minus infinity):

```
b0 = clamp(floor((Dec - R + 90) / 5), 0, NB-1)
b1 = clamp(floor((Dec + R + 90) / 5), 0, NB-1)

overPole = (Dec + R >= 90) or (Dec - R <= -90)
if not overPole:
    s = sin(R) / cos(Dec)
    if s >= 1: overPole = true
    else:      H = asin(s)            # half-width of the disc in RA, degrees

ra = RA mod 360   (into 0 <= ra < 360)
for b in b0..b1:
    n = cells_per_band[b];  w = 360 / n
    if overPole:
        take every cell 0..n-1 of band b
    else:
        k0 = floor((ra - H) / w);  k1 = floor((ra + H) / w)
        if k1 - k0 + 1 >= n: take every cell 0..n-1
        else: take cells (k mod n) for k = k0..k1      # mod result in 0..n-1; handles RA wrap
```

Then, for every selected (band, cell), read all its parts listed in `manifest.shards`
(or only the parts whose `[mjd_min, mjd_max]` overlaps the time span of interest).

Properties: the rule never misses a cell (it is conservative, the RA half-width is the
exact extreme of a small circle and is applied to all bands); away from the poles it
selects 1 to 6 cells, typically 2 to 4; within R of a pole it selects whole bands, which
are short there (3 and 9 cells for the two bands nearest a pole). RA wrap-around at 0/360
needs nothing special beyond the `mod n`.

### Dense regions (the deep fields at the ecliptic poles)

Near the ecliptic poles (RA 270, Dec +66.56 and RA 90, Dec -66.56) SPHEREx observes all
the time, and a single point is covered by tens of thousands of images. Cells there
have many parts. Because parts are time-ordered and the manifest gives each part's MJD
range, a client can:

- show the count and time span immediately from the manifest alone (sum of `count`);
- load only parts overlapping a chosen time window;
- or subsample: load every N-th part for an even spread in time, and refine on demand.

Every part is at most 459 kB, so no single request is large.

## 5. From a record to an S3 URL

```
[collection_index, release, period, procver] = manifest.prefixes[prefix]
collection = manifest.collections[collection_index]
seq4 = seq as 4 digits with leading zeros
key  = release + "/level2/" + period + "/" + procver + "/" + det
       + "/level2_" + period + "_" + seq4 + "_" + suffix + "D" + det + "_spx_" + procver + ".fits"
url  = "https://nasa-irsa-spherex.s3.amazonaws.com/" + key
```

Example: `prefix -> [0,"dr1","2025W33_2C","l2b-v27-2026-228"]`, `det = 6`, `seq = 321`,
`suffix = 1` gives

`dr1/level2/2025W33_2C/l2b-v27-2026-228/6/level2_2025W33_2C_0321_1D6_spx_l2b-v27-2026-228.fits`

The same key after `https://irsa.ipac.caltech.edu/ibe/data/spherex/` is the IRSA URL.
The observation id (IRSA `obs_id`) is `period + "_" + seq4 + "_" + suffix`.

Why a prefix table: the processing-version string (`procver`) is **not** constant within
a planning period. Most files of a period share one string, but some are re-processed
(for example `l2b_retry-v27-2026-197` next to `l2b-v27-2026-196`), per file, not per
detector. So each distinct (collection, release, period, procver) is one table entry and
every record names its entry. The deep-field collections use the same `release` folder
as the main survey (`dr1`, `qr3`); the collection is only a label.

## 6. Does the footprint contain the point? (exact test)

Inputs: the query point (RA, Dec) and one record. Work in radians.

```
a0 = ra  * 1e-7 * pi/180        d0 = dec * 1e-7 * pi/180        # record centre
a  = RA  * pi/180               d  = Dec * pi/180               # query point

cosc = sin(d0)*sin(d) + cos(d0)*cos(d)*cos(a - a0)
if cosc <= 1e-9: the point is not in the footprint (more than 90 degrees away). Stop.

xi  =  cos(d)*sin(a - a0) / cosc                                # east
eta = (cos(d0)*sin(d) - sin(d0)*cos(d)*cos(a - a0)) / cosc      # north

px = xi  / 1.6e-6               py = eta / 1.6e-6               # in counts

(X1,Y1) = (x1,y1); (X2,Y2) = (x2,y2); (X3,Y3) = (x3,y3)
(X4,Y4) = (-(x1+x2+x3), -(y1+y2+y3))

A = sum over k=1..4 of ( Xk*Y(k+1) - X(k+1)*Yk )     # with corner 5 = corner 1
g = +1 if A > 0, -1 if A < 0;  if A == 0 the record is degenerate: not contained

for k = 1..4 (corner 5 = corner 1):
    ex = X(k+1) - Xk;   ey = Y(k+1) - Yk
    m_k = g * ( ex*(py - Yk) - ey*(px - Xk) ) / sqrt(ex*ex + ey*ey)

margin = min(m_1, m_2, m_3, m_4)            # counts; multiply by 0.330024 for arcsec
contained  <=>  margin >= 0
```

`margin` is the distance from the point to the nearest edge (positive inside). In
arcseconds it is `margin * 1.6e-6 * 206264.806`. Use `margin >= some arcsec` to demand
that a cutout of a given half-size fits on the detector (a 6.15 arcsec pixel:
`margin_arcsec >= 6.15 * half_size_pixels`).

Why this is right: the gnomonic projection turns great circles into straight lines, so
this plane test is exactly "inside the spherical quadrilateral with great-circle edges".
It has no special cases at RA 0/360 or at the poles (a footprint that contains a pole
works like any other). In real data `A < 0` for every record (IRSA lists corners
clockwise as seen with east to the left), but the test does not rely on it.

Use double precision (JavaScript numbers are fine).

## 7. Reference client (TypeScript sketch)

```ts
type Manifest = { /* section 2 */ };
type Hit = { key: string; url: string; mjd: number; det: number; collection: string; marginArcsec: number };

const REC = 28, TAN = 1.6e-6, RAD = Math.PI / 180;

function cellsForPoint(ra: number, dec: number, m: Manifest): [number, number][] {
  const H5 = m.grid.band_height_deg, n = m.grid.cells_per_band, NB = n.length, R = m.search_radius_deg;
  const clamp = (v: number) => Math.max(0, Math.min(NB - 1, v));
  const b0 = clamp(Math.floor((dec - R + 90) / H5)), b1 = clamp(Math.floor((dec + R + 90) / H5));
  let overPole = dec + R >= 90 || dec - R <= -90, half = 360;
  if (!overPole) {
    const s = Math.sin(R * RAD) / Math.cos(dec * RAD);
    if (s >= 1) overPole = true; else half = Math.asin(s) / RAD;
  }
  const r = ((ra % 360) + 360) % 360, out: [number, number][] = [];
  for (let b = b0; b <= b1; b++) {
    const w = 360 / n[b], k0 = Math.floor((r - half) / w), k1 = Math.floor((r + half) / w);
    if (overPole || k1 - k0 + 1 >= n[b]) for (let k = 0; k < n[b]; k++) out.push([b, k]);
    else for (let k = k0; k <= k1; k++) out.push([b, ((k % n[b]) + n[b]) % n[b]]);
  }
  return out;
}

function scanShard(buf: ArrayBuffer, ra: number, dec: number, m: Manifest, out: Hit[]) {
  const v = new DataView(buf), a = ra * RAD, d = dec * RAD, sd = Math.sin(d), cd = Math.cos(d);
  for (let o = 0; o + REC <= buf.byteLength; o += REC) {
    const a0 = v.getUint32(o, true) * 1e-7 * RAD, d0 = v.getInt32(o + 4, true) * 1e-7 * RAD;
    const sd0 = Math.sin(d0), cd0 = Math.cos(d0), cda = Math.cos(a - a0);
    const cosc = sd0 * sd + cd0 * cd * cda;
    if (cosc <= 1e-9) continue;
    const px = (cd * Math.sin(a - a0)) / cosc / TAN, py = (cd0 * sd - sd0 * cd * cda) / cosc / TAN;
    const X = [v.getInt16(o + 8, true), v.getInt16(o + 12, true), v.getInt16(o + 16, true), 0];
    const Y = [v.getInt16(o + 10, true), v.getInt16(o + 14, true), v.getInt16(o + 18, true), 0];
    X[3] = -(X[0] + X[1] + X[2]); Y[3] = -(Y[0] + Y[1] + Y[2]);
    let A = 0;
    for (let k = 0; k < 4; k++) { const j = (k + 1) % 4; A += X[k] * Y[j] - X[j] * Y[k]; }
    if (A === 0) continue;
    const g = A > 0 ? 1 : -1;
    let margin = Infinity;
    for (let k = 0; k < 4; k++) {
      const j = (k + 1) % 4, ex = X[j] - X[k], ey = Y[j] - Y[k];
      margin = Math.min(margin, (g * (ex * (py - Y[k]) - ey * (px - X[k]))) / Math.hypot(ex, ey));
    }
    if (margin < 0) continue;
    const id = v.getUint32(o + 24, true), det = (id & 7) + 1, suffix = (id >>> 3) & 7;
    const seq = String((id >>> 6) & 0xfff).padStart(4, "0");
    const [ci, release, period, procver] = m.prefixes[id >>> 18];
    const key = `${release}/level2/${period}/${procver}/${det}/level2_${period}_${seq}_${suffix}D${det}_spx_${procver}.fits`;
    out.push({ key, url: m.s3_root + key, mjd: 60000 + v.getUint32(o + 20, true) * 1e-6, det,
               collection: m.collections[ci], marginArcsec: margin * TAN * 206264.80624709636 });
  }
}

async function query(base: string, m: Manifest, ra: number, dec: number): Promise<Hit[]> {
  const want = new Set(cellsForPoint(ra, dec, m).map(([b, c]) => `${b},${c}`));
  const pad = (v: number, n: number) => String(v).padStart(n, "0");
  const files = m.shards.filter(([b, c]) => want.has(`${b},${c}`))
    .map(([b, c, p]) => `${base}/b${pad(b, 2)}/c${pad(c, 3)}_${pad(p, 3)}.bin?v=${encodeURIComponent(m.built_utc)}`);
  const out: Hit[] = [];
  for (const f of files) scanShard(await (await fetch(f)).arrayBuffer(), ra, dec, m, out);
  return out.sort((p, q) => p.mjd - q.mjd);
}
```

(For dense regions fetch `files` a few at a time and filter by the manifest's MJD range
first; see section 4.)

## 8. Limits of version 1

- Time: `t` is a uint32 of micro-days from MJD 60000, so it reaches MJD 64294.96
  (November 2034). The builder leaves out (and counts) anything outside.
- `seq` <= 4095, `suffix` <= 7, at most 16384 prefix entries, corner offsets within
  +-3.0 degrees of the centre. The builder checks every row and reports rows it cannot
  encode in `quality.left_out_unencodable` (0 in the shipped build).
- The footprint is IRSA's four-corner polygon; real detector edges are not perfectly
  straight (optical distortion), so within a few arcsec of an edge the true answer can
  differ. Use the margin when it matters.
- IRSA's own `CONTAINS(POINT, poly)` and this test can disagree for points within a
  rounding distance of an edge; see section 10 for what was measured.

## 9. Keeping it up to date

```
cd pipeline
.venv\Scripts\python.exe scripts\build_sky_index.py
```

does both steps: it asks IRSA for the time span of every collection, downloads only
the MJD days that are missing or were incomplete last time (one CSV per day under
`data/cache/skyindex/chunks/`, bookkeeping in `data/cache/skyindex/state.json`), then
rebuilds all shards from the cache (the build itself takes well under a minute).
Interrupt it at any moment; run it again to continue. Options: `--skip-dump` (build
only), `--dump-only`, `--refresh` (download everything again, for when IRSA replaces
old files, for example when a quick release is superseded by a data release),
`--verify` (compare six positions with a live IRSA query), `--newest-first`,
`--max-chunks N`, `--workers 1|2`.

The download is polite on purpose: at most two connections, one query per five days of
data, a pause between queries, and the User-Agent `ParallaX-SpaceApps2026/1.0`.

Shard files are replaced as a whole by a rebuild, and part boundaries can move when
new data arrive, so a client must not cache shards across different `built_utc` values.
