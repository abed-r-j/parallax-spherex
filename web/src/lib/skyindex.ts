/**
 * Reader of the static sky index (docs/SKY_INDEX.md, format version 1): which SPHEREx
 * Level-2 images contain a sky position, when they were taken, and their S3 keys.
 * No server: a small manifest plus a handful of 28-byte-record shard files.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */

export interface SkyManifest {
  format: string
  version: number
  built_utc: string
  s3_root: string
  shard_template?: string
  grid: { band_height_deg: number; cells_per_band: number[] }
  search_radius_deg: number
  collections: string[]
  /** [collection index, release, period, processing version] */
  prefixes: [number, string, string, string][]
  doi?: Record<string, string>
  rows?: { total?: number; [collection: string]: unknown }
  coverage?: { days_cached?: number; days_in_archive_span?: number; missing_days?: number[]; complete?: boolean }
  /** [band, cell, part, count, mjd_min, mjd_max] */
  shards: [number, number, number, number, number, number][]
}

export interface SkyHit {
  key: string
  url: string
  /** start of the exposure (MJD) */
  mjd: number
  det: number
  collection: string
  release: string
  /** IRSA obs_id: period_seq_suffix */
  obsId: string
  /** distance from the point to the nearest footprint edge, arcsec (positive inside) */
  marginArcsec: number
}

export const RECORD_BYTES = 28
const TAN = 1.6e-6
const RAD = Math.PI / 180
const ARCSEC_PER_RAD = 206264.80624709636

/** Throws unless the manifest is a version-1 ParallaX sky index. */
export function checkManifest(m: SkyManifest): SkyManifest {
  if (!m || m.format !== 'parallax-skyindex' || m.version !== 1) throw new Error('The sky index on this site has an unknown format.')
  return m
}

/** Section 4 of the specification: every [band, cell] a disc of radius R about the point can touch. */
export function cellsForPoint(ra: number, dec: number, m: Pick<SkyManifest, 'grid' | 'search_radius_deg'>): [number, number][] {
  const H5 = m.grid.band_height_deg
  const n = m.grid.cells_per_band
  const NB = n.length
  const R = m.search_radius_deg
  const clamp = (v: number) => Math.max(0, Math.min(NB - 1, v))
  const b0 = clamp(Math.floor((dec - R + 90) / H5))
  const b1 = clamp(Math.floor((dec + R + 90) / H5))
  let overPole = dec + R >= 90 || dec - R <= -90
  let half = 360
  if (!overPole) {
    const s = Math.sin(R * RAD) / Math.cos(dec * RAD)
    if (s >= 1) overPole = true
    else half = Math.asin(s) / RAD
  }
  const r = ((ra % 360) + 360) % 360
  const out: [number, number][] = []
  for (let b = b0; b <= b1; b++) {
    const w = 360 / n[b]
    const k0 = Math.floor((r - half) / w)
    const k1 = Math.floor((r + half) / w)
    if (overPole || k1 - k0 + 1 >= n[b]) for (let k = 0; k < n[b]; k++) out.push([b, k])
    else for (let k = k0; k <= k1; k++) out.push([b, ((k % n[b]) + n[b]) % n[b]])
  }
  return out
}

export interface SkyRecord {
  ra: number
  dec: number
  /** corners 1..4 in tangent-plane counts (the fourth is derived) */
  x: [number, number, number, number]
  y: [number, number, number, number]
  mjd: number
  det: number
  suffix: number
  seq: number
  prefix: number
}

/** Decode the record that starts at byte `o` (section 3). */
export function readRecord(v: DataView, o: number): SkyRecord {
  const x1 = v.getInt16(o + 8, true)
  const y1 = v.getInt16(o + 10, true)
  const x2 = v.getInt16(o + 12, true)
  const y2 = v.getInt16(o + 14, true)
  const x3 = v.getInt16(o + 16, true)
  const y3 = v.getInt16(o + 18, true)
  const id = v.getUint32(o + 24, true)
  return {
    ra: v.getUint32(o, true) * 1e-7,
    dec: v.getInt32(o + 4, true) * 1e-7,
    x: [x1, x2, x3, -(x1 + x2 + x3)],
    y: [y1, y2, y3, -(y1 + y2 + y3)],
    mjd: 60000 + v.getUint32(o + 20, true) * 1e-6,
    det: (id & 7) + 1,
    suffix: (id >>> 3) & 7,
    seq: (id >>> 6) & 0xfff,
    prefix: id >>> 18,
  }
}

/** Section 5: the S3 key of a record. */
export function recordKey(r: Pick<SkyRecord, 'det' | 'seq' | 'suffix' | 'prefix'>, m: Pick<SkyManifest, 'prefixes'>): string {
  const p = m.prefixes[r.prefix]
  if (!p) throw new Error(`The sky index names an unknown path prefix (${r.prefix}).`)
  const [, release, period, procver] = p
  const seq = String(r.seq).padStart(4, '0')
  return `${release}/level2/${period}/${procver}/${r.det}/level2_${period}_${seq}_${r.suffix}D${r.det}_spx_${procver}.fits`
}

/**
 * Section 6: signed distance (in counts) from the point to the nearest edge of the
 * record's footprint, positive inside; -Infinity when the point is on the far hemisphere
 * or the footprint is degenerate.
 */
export function footprintMargin(r: Pick<SkyRecord, 'ra' | 'dec' | 'x' | 'y'>, ra: number, dec: number): number {
  const a0 = r.ra * RAD
  const d0 = r.dec * RAD
  const a = ra * RAD
  const d = dec * RAD
  const cda = Math.cos(a - a0)
  const cosc = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * cda
  if (cosc <= 1e-9) return -Infinity
  const px = (Math.cos(d) * Math.sin(a - a0)) / cosc / TAN
  const py = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * cda) / cosc / TAN
  const X = r.x
  const Y = r.y
  let A = 0
  for (let k = 0; k < 4; k++) {
    const j = (k + 1) % 4
    A += X[k] * Y[j] - X[j] * Y[k]
  }
  if (A === 0) return -Infinity
  const g = A > 0 ? 1 : -1
  let margin = Infinity
  for (let k = 0; k < 4; k++) {
    const j = (k + 1) % 4
    const ex = X[j] - X[k]
    const ey = Y[j] - Y[k]
    margin = Math.min(margin, (g * (ex * (py - Y[k]) - ey * (px - X[k]))) / Math.hypot(ex, ey))
  }
  return margin
}

/** Append every record of one shard whose footprint contains the point. */
export function scanShard(buf: ArrayBuffer, ra: number, dec: number, m: SkyManifest, out: SkyHit[]): void {
  const v = new DataView(buf)
  for (let o = 0; o + RECORD_BYTES <= buf.byteLength; o += RECORD_BYTES) {
    const r = readRecord(v, o)
    const margin = footprintMargin(r, ra, dec)
    if (!(margin >= 0)) continue
    const key = recordKey(r, m)
    const [ci, release, period] = m.prefixes[r.prefix]
    out.push({
      key,
      url: m.s3_root + key,
      mjd: r.mjd,
      det: r.det,
      collection: m.collections[ci] ?? 'unknown',
      release,
      obsId: `${period}_${String(r.seq).padStart(4, '0')}_${r.suffix}`,
      marginArcsec: margin * TAN * ARCSEC_PER_RAD,
    })
  }
}

export function shardName(band: number, cell: number, part: number): string {
  const pad = (v: number, n: number) => String(v).padStart(n, '0')
  return `b${pad(band, 2)}/c${pad(cell, 3)}_${pad(part, 3)}.bin`
}

/** Manifest entries of the shards to read for a point. */
export function shardsForPoint(m: SkyManifest, ra: number, dec: number): SkyManifest['shards'] {
  const want = new Set(cellsForPoint(ra, dec, m).map(([b, c]) => `${b},${c}`))
  return m.shards.filter(([b, c]) => want.has(`${b},${c}`))
}

export const SKYINDEX_BASE = './skyindex'
const manifests = new Map<string, Promise<SkyManifest>>()

/** Fetch (once per session) and validate the manifest. */
export function loadManifest(base = SKYINDEX_BASE, signal?: AbortSignal): Promise<SkyManifest> {
  let p = manifests.get(base)
  if (!p) {
    p = fetch(`${base}/manifest.json`, { signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`The sky index is missing from this site (manifest.json: HTTP ${r.status}).`))))
      .then((j: SkyManifest) => checkManifest(j))
    manifests.set(base, p)
    p.catch(() => manifests.delete(base))
  }
  return p
}

export interface SkyQuery {
  hits: SkyHit[]
  shardsRead: number
  bytes: number
  manifest: SkyManifest
}

/** Every indexed image whose footprint contains (ra, dec), oldest first. */
export async function querySkyIndex(ra: number, dec: number, opts: { base?: string; signal?: AbortSignal } = {}): Promise<SkyQuery> {
  const base = opts.base ?? SKYINDEX_BASE
  const m = await loadManifest(base, opts.signal)
  const files = shardsForPoint(m, ra, dec)
  const hits: SkyHit[] = []
  let bytes = 0
  const v = encodeURIComponent(m.built_utc)
  // a few at a time: a normal position needs about four shards, the ecliptic poles a few dozen
  for (let i = 0; i < files.length; i += 4) {
    const bufs = await Promise.all(
      files.slice(i, i + 4).map(async ([b, c, p]) => {
        const r = await fetch(`${base}/${shardName(b, c, p)}?v=${v}`, { signal: opts.signal })
        if (!r.ok) throw new Error(`A sky-index file could not be read (${shardName(b, c, p)}: HTTP ${r.status}).`)
        return r.arrayBuffer()
      }),
    )
    for (const buf of bufs) {
      bytes += buf.byteLength
      scanShard(buf, ra, dec, m, hits)
    }
  }
  hits.sort((p, q) => p.mjd - q.mjd)
  return { hits, shardsRead: files.length, bytes, manifest: m }
}
