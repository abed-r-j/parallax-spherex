/**
 * The live path: build a field for any sky position in the browser, with no server.
 * The static sky index says which SPHEREx Level-2 images cover the position; from each
 * 65 MB file in the public NASA/IPAC IRSA bucket on AWS only three small byte ranges
 * travel: the header, the detector rows that the field needs, and (once per detector
 * calibration) the wavelength table. Every image is resampled bilinearly onto the same
 * north-up tangent grid the precomputed packs use, and the result is an ordinary Pack.
 *
 * What is different from the Python pipeline, on purpose (to keep the download small):
 * the FLAGS, VARIANCE and ZODI planes are not fetched. Instead of the zodiacal model plus
 * a residual sky, one robust sky level per frame is removed (clipped median of a detector
 * window about 31 arcmin wide around the field); the noise is the robust scatter of
 * neighbouring detector pixels; pixels are flagged only where there is no data.
 * The chromatic template is not computed here: that needs the pipeline (the engine).
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { deriveGatedPartners, deriveNaivePartners, encodeBrightness } from './decode'
import { FITS_BLOCK, dataBytes, need, num, parseHeader, readWaveTable, waveAt, type FitsHeader, type WaveTable } from './fits'
import { worldToPix, wcsFromHeader, type TanSip } from './sip'
import { querySkyIndex, type SkyHit, type SkyQuery } from './skyindex'
import type { Frames, LiveInfo, Meta, Pack } from './types'
import { formatDec, formatRa, pixToSky } from './wcs'

export const LIVE_SCALE = 6.15
export const LIVE_SIZES = [3, 6, 9] as const
export const LIVE_DEFAULT_SIZE = 3
export const LIVE_DEFAULT_DETECTORS = [2, 5]
export const LIVE_DEFAULT_MAX = 360
export const LIVE_BASE = 'live'
/** One fixed encoding for every live field: 0.05 percent steps from -1000 to 1e6 MJy/sr. */
export const LIVE_ENCODING = { soft: 0.01, lo: -Math.asinh(1e3 / 0.01), hi: Math.asinh(1e6 / 0.01) }
const MIN_COVERAGE = 0.6
const CAMPAIGN_GAP_DAYS = 30
const HEAD_BYTES = 28800
const TAIL_BYTES = 2 * FITS_BLOCK
/** half-width, in detector pixels (6.15 arcsec each), of the window the sky level is measured on */
const SKY_HALF_WIDTH = 150

export interface LiveSpec {
  ra: number
  dec: number
  sizeArcmin: number
  /** detectors to fetch, 1..6; empty = all six */
  detectors: number[]
  maxImages: number
}

export interface LiveProgress {
  phase: 'index' | 'frames' | 'done'
  message: string
  /** images that cover the position, all detectors */
  available: number
  /** of those, in the chosen detectors */
  matching: number
  /** images this run fetches (after the maxImages cut) */
  total: number
  done: number
  loaded: number
  skipped: number
  failed: number
  bytes: number
  requests: number
  seconds: number
  /** the most recent snapshot of the field (null until a few frames exist) */
  pack: Pack | null
  /** the frame that just arrived, for a thumbnail */
  last: { img: Float32Array; n: number; det: number; mjd: number; lam: number } | null
}

export interface LiveOptions extends Partial<LiveSpec> {
  ra: number
  dec: number
  onProgress?: (p: LiveProgress) => void
  signal?: AbortSignal
  /** simultaneous requests to the archive (1..6, default 5) */
  concurrency?: number
  /** minimum time between two snapshots handed to onProgress, ms */
  snapshotMs?: number
  indexBase?: string
  /** test hooks */
  fetchImpl?: typeof fetch
  query?: (ra: number, dec: number, signal?: AbortSignal) => Promise<SkyQuery>
  retryBaseMs?: number
}

/** Odd grid size that covers at least `sizeArcmin`. */
export function liveGridN(sizeArcmin: number): number {
  const want = (sizeArcmin * 60) / LIVE_SCALE
  return Math.max(9, Math.min(201, 2 * Math.ceil((want - 1) / 2) + 1))
}

export function normaliseSpec(o: Partial<LiveSpec> & { ra: number; dec: number }): LiveSpec {
  const dets = [...new Set((o.detectors ?? LIVE_DEFAULT_DETECTORS).filter((d) => Number.isInteger(d) && d >= 1 && d <= 6))].sort((a, b) => a - b)
  const size = o.sizeArcmin && o.sizeArcmin > 0 ? Math.min(20, Math.max(0.5, o.sizeArcmin)) : LIVE_DEFAULT_SIZE
  const max = o.maxImages && o.maxImages > 0 ? Math.floor(o.maxImages) : LIVE_DEFAULT_MAX
  return { ra: ((o.ra % 360) + 360) % 360, dec: o.dec, sizeArcmin: size, detectors: dets.length === 6 ? [] : dets, maxImages: max }
}

/** A stable key for a request (also the pack key). */
export function liveKey(s: LiveSpec): string {
  const sign = s.dec < 0 ? 'm' : 'p'
  const dets = s.detectors.length ? s.detectors.join('') : 'all'
  return `live_${s.ra.toFixed(5)}_${sign}${Math.abs(s.dec).toFixed(5)}_${+s.sizeArcmin.toFixed(2)}am_d${dets}_x${s.maxImages}`
}

/** At most `max` items, evenly spaced over the list (the pipeline's rule for fetch_field). */
export function subsetEvenly<T>(items: T[], max: number): T[] {
  if (max <= 0 || items.length <= max) return items
  if (max === 1) return [items[0]]
  const idx = new Set<number>()
  for (let i = 0; i < max; i++) idx.add(Math.round((i * (items.length - 1)) / (max - 1)))
  return [...idx].sort((a, b) => a - b).map((i) => items[i])
}

/** Survey pass of each exposure (times ascending): a new pass starts after a 30-day gap. */
export function assignCampaigns(mjdSorted: number[], gap = CAMPAIGN_GAP_DAYS): number[] {
  const out: number[] = []
  let c = 0
  for (let i = 0; i < mjdSorted.length; i++) {
    if (i > 0 && mjdSorted[i] - mjdSorted[i - 1] > gap) c++
    out.push(c)
  }
  return out
}

function medianSorted(v: ArrayLike<number>, len: number): number {
  if (!len) return NaN
  const m = len >> 1
  return len % 2 ? v[m] : (v[m - 1] + v[m]) / 2
}

/**
 * Robust sky level and noise of a frame: the median after three rounds of 3-sigma
 * clipping (sigma = 1.4826 x median absolute deviation), and the clipped scatter.
 */
export function robustSky(img: ArrayLike<number>): { sky: number; sigma: number } {
  const fin: number[] = []
  for (let k = 0; k < img.length; k++) if (Number.isFinite(img[k])) fin.push(img[k])
  let v = Float64Array.from(fin).sort()
  if (v.length < 8) return { sky: v.length ? medianSorted(v, v.length) : 0, sigma: NaN }
  let med = medianSorted(v, v.length)
  let mad = 0
  for (let it = 0; it < 4; it++) {
    const dev = Float64Array.from(v, (x) => Math.abs(x - med)).sort()
    mad = 1.4826 * medianSorted(dev, dev.length) + 1e-12
    if (it === 3) break
    v = v.filter((x) => Math.abs(x - med) < 3 * mad)
    med = medianSorted(v, v.length)
  }
  return { sky: med, sigma: mad }
}

/**
 * Noise of a detector window (rows x cols, row-major) from second differences along the
 * rows, v[c] - (v[c-1] + v[c+1]) / 2: 1.4826 x MAD / sqrt(1.5). Smooth light (sky, a
 * galaxy) cancels, and stars and hot pixels are a minority that the median ignores.
 */
export function neighbourNoise(win: ArrayLike<number>, rows: number, cols: number): number {
  const d: number[] = []
  for (let r = 0; r < rows; r++)
    for (let c = 1 + (r % 3); c + 1 < cols; c += 3) {
      const v = win[r * cols + c] - (win[r * cols + c - 1] + win[r * cols + c + 1]) / 2
      if (Number.isFinite(v)) d.push(v)
    }
  if (d.length < 8) return NaN
  const s = Float64Array.from(d).sort()
  const med = medianSorted(s, s.length)
  const dev = s.map((v) => Math.abs(v - med)).sort()
  return (1.4826 * medianSorted(dev, dev.length)) / Math.sqrt(1.5)
}

/** Least-squares plane lambda = a + bx (x - c) + by (y - c), c = (n - 1) / 2, over finite pixels. */
export function planeFit(lam: ArrayLike<number>, n: number): [number | null, number, number] {
  const c = (n - 1) / 2
  let s1 = 0, sx = 0, sy = 0, sxx = 0, sxy = 0, syy = 0, sl = 0, slx = 0, sly = 0
  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++) {
      const l = lam[y * n + x]
      if (!Number.isFinite(l)) continue
      const dx = x - c
      const dy = y - c
      s1++; sx += dx; sy += dy; sxx += dx * dx; sxy += dx * dy; syy += dy * dy
      sl += l; slx += l * dx; sly += l * dy
    }
  if (s1 < 3) return [null, 0, 0]
  // solve the 3 x 3 normal equations by Cramer's rule
  const det = s1 * (sxx * syy - sxy * sxy) - sx * (sx * syy - sxy * sy) + sy * (sx * sxy - sxx * sy)
  if (!Number.isFinite(det) || Math.abs(det) < 1e-9) return [sl / s1, 0, 0]
  const a = (sl * (sxx * syy - sxy * sxy) - sx * (slx * syy - sxy * sly) + sy * (slx * sxy - sxx * sly)) / det
  const bx = (s1 * (slx * syy - sly * sxy) - sl * (sx * syy - sxy * sy) + sy * (sx * sly - slx * sy)) / det
  const by = (s1 * (sxx * sly - sxy * slx) - sx * (sx * sly - slx * sy) + sl * (sx * sxy - sxx * sy)) / det
  return [+a.toFixed(6), +bx.toFixed(8), +by.toFixed(8)]
}

export interface LiveGrid {
  ra0: number
  dec0: number
  n: number
  scale: number
  /** sky position of every grid pixel, [y][x] */
  ra: Float64Array
  dec: Float64Array
}

export function makeGrid(ra0: number, dec0: number, n: number, scale = LIVE_SCALE): LiveGrid {
  const ra = new Float64Array(n * n)
  const dec = new Float64Array(n * n)
  const g = { ra0, dec0, n, scale }
  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++) {
      const p = pixToSky(g, x, y)
      ra[y * n + x] = p.ra
      dec[y * n + x] = p.dec
    }
  return { ...g, ra, dec }
}

export interface Footprint {
  /** detector pixel position (0-based, fractional) of every grid pixel; NaN if unreachable */
  px: Float64Array
  py: Float64Array
  /** fraction of grid pixels whose four detector neighbours are on the detector */
  coverage: number
  /** detector rows and columns the resampling needs (inclusive), or null if none */
  box: { x0: number; x1: number; y0: number; y1: number } | null
}

/** Where the grid falls on a detector of nx x ny pixels. */
export function footprintOnDetector(grid: LiveGrid, w: TanSip, nx: number, ny: number): Footprint {
  const nn = grid.n * grid.n
  const px = new Float64Array(nn)
  const py = new Float64Array(nn)
  let inside = 0
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
  for (let k = 0; k < nn; k++) {
    const p = worldToPix(w, grid.ra[k], grid.dec[k])
    px[k] = p ? p.x : NaN
    py[k] = p ? p.y : NaN
    if (!p) continue
    const ix = Math.floor(p.x)
    const iy = Math.floor(p.y)
    if (ix < 0 || iy < 0 || ix + 1 >= nx || iy + 1 >= ny) continue
    inside++
    if (ix < x0) x0 = ix
    if (ix + 1 > x1) x1 = ix + 1
    if (iy < y0) y0 = iy
    if (iy + 1 > y1) y1 = iy + 1
  }
  return { px, py, coverage: inside / nn, box: inside ? { x0, x1, y0, y1 } : null }
}

/**
 * Bilinear resampling of a detector strip onto the grid (the pipeline's resample_cutout
 * without flags and variance): a grid pixel is kept when its four neighbours are on the
 * detector and at least 75 percent of the weight comes from finite pixels.
 * `strip` holds rows box.y0..box.y1, columns box.x0..box.x1.
 */
export function resampleStrip(strip: Float32Array, box: NonNullable<Footprint['box']>, fp: Footprint, nx: number, ny: number): Float32Array {
  const cols = box.x1 - box.x0 + 1
  const out = new Float32Array(fp.px.length).fill(NaN)
  for (let k = 0; k < out.length; k++) {
    const x = fp.px[k]
    const y = fp.py[k]
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue
    const ix = Math.floor(x)
    const iy = Math.floor(y)
    if (ix < 0 || iy < 0 || ix + 1 >= nx || iy + 1 >= ny) continue
    const fx = x - ix
    const fy = y - iy
    const o = (iy - box.y0) * cols + (ix - box.x0)
    let sum = 0
    let wsum = 0
    const v00 = strip[o]
    const v10 = strip[o + 1]
    const v01 = strip[o + cols]
    const v11 = strip[o + cols + 1]
    if (Number.isFinite(v00)) { const w = (1 - fx) * (1 - fy); sum += w * v00; wsum += w }
    if (Number.isFinite(v10)) { const w = fx * (1 - fy); sum += w * v10; wsum += w }
    if (Number.isFinite(v01)) { const w = (1 - fx) * fy; sum += w * v01; wsum += w }
    if (Number.isFinite(v11)) { const w = fx * fy; sum += w * v11; wsum += w }
    if (wsum > 0.75) out[k] = sum / wsum
  }
  return out
}

// ---- network ---------------------------------------------------------------------------

class Semaphore {
  private waiting: (() => void)[] = []
  private free: number
  constructor(n: number) {
    this.free = n
  }
  async run<T>(fn: () => Promise<T>): Promise<T> {
    if (this.free > 0) this.free--
    else await new Promise<void>((r) => this.waiting.push(r))
    try {
      return await fn()
    } finally {
      const next = this.waiting.shift()
      if (next) next()
      else this.free++
    }
  }
}

class PermanentError extends Error {}

interface Net {
  fetch: typeof fetch
  sem: Semaphore
  signal?: AbortSignal
  retryBaseMs: number
  bytes: number
  requests: number
}

function abortError(): Error {
  return new DOMException('The live fetch was cancelled.', 'AbortError')
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError())
    const t = setTimeout(() => {
      signal?.removeEventListener('abort', stop)
      resolve()
    }, ms)
    const stop = () => {
      clearTimeout(t)
      reject(abortError())
    }
    signal?.addEventListener('abort', stop, { once: true })
  })
}

/**
 * One contiguous byte range of a file, with up to four attempts and exponential back-off.
 * `range` is the Range header value; `expect` the number of bytes it must return.
 */
async function getRange(net: Net, url: string, range: string, expect: number | null): Promise<Uint8Array> {
  let last: unknown
  for (let attempt = 0; attempt < 4; attempt++) {
    if (net.signal?.aborted) throw abortError()
    if (attempt) await sleep(net.retryBaseMs * 2 ** (attempt - 1) * (1 + Math.random() * 0.5), net.signal)
    const ctl = new AbortController()
    const stop = () => ctl.abort()
    net.signal?.addEventListener('abort', stop, { once: true })
    const timer = setTimeout(stop, 90000)
    try {
      const body = await net.sem.run(async () => {
        const r = await net.fetch(url, { headers: { Range: range }, signal: ctl.signal })
        net.requests++
        if (r.status === 403 || r.status === 404) throw new PermanentError(`the archive does not have this file (HTTP ${r.status})`)
        if (r.status !== 206) {
          void r.body?.cancel().catch(() => {})
          throw new Error(`unexpected HTTP ${r.status}`)
        }
        return new Uint8Array(await r.arrayBuffer())
      })
      net.bytes += body.length
      if (expect !== null && body.length !== expect) throw new Error(`short answer (${body.length} of ${expect} bytes)`)
      return body
    } catch (e) {
      if (net.signal?.aborted) throw abortError()
      if (e instanceof PermanentError) throw e
      last = e
    } finally {
      clearTimeout(timer)
      net.signal?.removeEventListener('abort', stop)
    }
  }
  throw new Error(`The archive did not answer after four attempts (${last instanceof Error ? last.message : String(last)}).`)
}

// ---- one image ---------------------------------------------------------------------------

export interface LiveFrame {
  hit: SkyHit
  img: Float32Array
  q: Uint16Array
  mjd: number
  det: number
  lam: number
  bw: number
  lamFit: [number | null, number, number]
  sigma: number
  sky: number
  fwhm: number
  name: string
}

export type FrameOutcome = { frame: LiveFrame } | { skip: string }

function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.length + b.length)
  out.set(a)
  out.set(b, a.length)
  return out
}

/** The image HDU header of a Level-2 file and the byte offset of its pixels. */
async function imageHeader(net: Net, url: string): Promise<{ h: FitsHeader; dataOffset: number }> {
  let buf = await getRange(net, url, `bytes=0-${HEAD_BYTES - 1}`, HEAD_BYTES)
  for (let more = 0; ; more++) {
    const prim = parseHeader(buf, 0)
    const off = prim ? prim.bytes + dataBytes(prim) : -1
    const h = off >= 0 ? parseHeader(buf, off) : null
    if (h) return { h, dataOffset: off + h.bytes }
    if (more >= 3) throw new PermanentError('the file does not start like a SPHEREx Level-2 image')
    buf = concat(buf, await getRange(net, url, `bytes=${buf.length}-${buf.length + HEAD_BYTES - 1}`, HEAD_BYTES))
  }
}

function waveTable(net: Net, cache: Map<string, Promise<WaveTable>>, url: string, det: number, h: FitsHeader): Promise<WaveTable> {
  // the table is a calibration product: identical for every file that names the same id
  const id = h.history.map((l) => /\[CALIB\]\s+spectral_wcs\s+(\S+)/.exec(l)?.[1]).filter(Boolean).pop()
  const key = id ? `${det}|${id}` : url
  let p = cache.get(key)
  if (!p) {
    p = (async () => {
      try {
        return readWaveTable(await getRange(net, url, `bytes=-${TAIL_BYTES}`, TAIL_BYTES))
      } catch (e) {
        if (e instanceof DOMException) throw e
        return readWaveTable(await getRange(net, url, `bytes=-${5 * FITS_BLOCK}`, 5 * FITS_BLOCK))
      }
    })()
    cache.set(key, p)
    p.catch(() => cache.delete(key))
  }
  return p
}

/** Fetch and resample one image. */
export async function fetchFrame(net: Net, waves: Map<string, Promise<WaveTable>>, hit: SkyHit, grid: LiveGrid): Promise<FrameOutcome> {
  const { h, dataOffset } = await imageHeader(net, hit.url)
  const nx = need(h, 'NAXIS1')
  const ny = need(h, 'NAXIS2')
  if (num(h, 'NAXIS') !== 2 || num(h, 'BITPIX') !== -32) throw new PermanentError('the image is not a 2-D float32 array')
  const fp = footprintOnDetector(grid, wcsFromHeader(h), nx, ny)
  if (!fp.box || fp.coverage < MIN_COVERAGE) return { skip: 'the field falls mostly off this detector' }
  const box = fp.box
  const det = num(h, 'DETECTOR') ?? hit.det
  const rows = box.y1 - box.y0 + 1
  // one contiguous range: whole detector rows (the bucket does not serve multi-range requests)
  const a = dataOffset + 4 * nx * box.y0
  const [raw, table] = await Promise.all([
    getRange(net, hit.url, `bytes=${a}-${a + 4 * nx * rows - 1}`, 4 * nx * rows),
    waveTable(net, waves, hit.url, det, h),
  ])
  // The rows arrive at full detector width. Decode a window wider than the field: its extra
  // columns cost nothing and give a sky level that a large object in the field cannot bias.
  const mid = Math.round((box.x0 + box.x1) / 2)
  const wide = { x0: Math.max(0, Math.min(box.x0, mid - SKY_HALF_WIDTH)), x1: Math.min(nx - 1, Math.max(box.x1, mid + SKY_HALF_WIDTH)), y0: box.y0, y1: box.y1 }
  const cols = wide.x1 - wide.x0 + 1
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength)
  const strip = new Float32Array(rows * cols)
  for (let r = 0; r < rows; r++) {
    const o = (r * nx + wide.x0) * 4
    for (let c = 0; c < cols; c++) strip[r * cols + c] = view.getFloat32(o + c * 4, false)
  }
  const img = resampleStrip(strip, wide, fp, nx, ny)
  let finite = 0
  for (let k = 0; k < img.length; k++) if (Number.isFinite(img[k])) finite++
  if (finite / img.length < MIN_COVERAGE) return { skip: 'too few usable pixels in this exposure' }

  // per-pixel wavelength: where each grid pixel sits on the detector (alternate WCS 'W')
  const n = grid.n
  const cx = (num(h, 'CRVAL1W') ?? 1) + 1 - (num(h, 'CRPIX1W') ?? 1)
  const cy = (num(h, 'CRVAL2W') ?? 1) + 1 - (num(h, 'CRPIX2W') ?? 1)
  const lam = new Float32Array(n * n).fill(NaN)
  const bw = new Float32Array(n * n).fill(NaN)
  const w2: number[] = []
  for (let k = 0; k < lam.length; k++) {
    const x = fp.px[k]
    const y = fp.py[k]
    const ix = Math.floor(x)
    const iy = Math.floor(y)
    if (!(ix >= 0 && iy >= 0 && ix + 1 < nx && iy + 1 < ny)) continue
    const [l, b] = waveAt(table, cx + x, cy + y)
    lam[k] = l
    bw[k] = b
    const fx = x - ix
    const fy = y - iy
    w2.push(((1 - fx) ** 2 + fx ** 2) * ((1 - fy) ** 2 + fy ** 2))
  }
  // sky from the wide detector window; noise from neighbour differences there, scaled by the
  // typical sum of squared bilinear weights (what the pipeline's variance propagation gives)
  const { sky } = robustSky(strip)
  const raw1 = neighbourNoise(strip, rows, cols)
  w2.sort((p, r) => p - r)
  let sigma = raw1 * Math.sqrt(medianSorted(w2, w2.length))
  if (!(sigma > 0)) sigma = robustSky(img).sigma
  const q = new Uint16Array(n * n)
  for (let k = 0; k < img.length; k++) {
    img[k] -= sky
    q[k] = encodeBrightness(img[k], LIVE_ENCODING)
  }
  const c = (n >> 1) * n + (n >> 1)
  return {
    frame: {
      hit, img, q, det,
      mjd: num(h, 'MJD-AVG') ?? hit.mjd,
      lam: lam[c], bw: bw[c], lamFit: planeFit(lam, n),
      sigma, sky,
      fwhm: num(h, 'PSF_FWHM') ?? NaN,
      name: hit.key.slice(hit.key.lastIndexOf('/') + 1),
    },
  }
}

// ---- assembling a Pack -------------------------------------------------------------------

function isoOf(mjd: number): string {
  return new Date((mjd - 40587) * 86400000).toISOString().slice(0, 19)
}

const r5 = (v: number): number | null => (Number.isFinite(v) ? +v.toFixed(5) : null)

/**
 * Per survey pass and detector: mean of the frames weighted by 1 / sigma^2, after
 * rejecting values more than five robust deviations from the per-pixel median (cosmic
 * rays and hot pixels, which the unfetched FLAGS plane would otherwise mark).
 */
export function robustStack(frames: { img: Float32Array; sigma: number }[], nn: number): Float32Array {
  const out = new Float32Array(nn).fill(NaN)
  const m = frames.length
  if (!m) return out
  const w = frames.map((f) => (Number.isFinite(f.sigma) && f.sigma > 0 ? 1 / (f.sigma * f.sigma) : 0))
  const useW = w.some((x) => x > 0)
  const vals = new Float64Array(m)
  const dev = new Float64Array(m)
  for (let k = 0; k < nn; k++) {
    let c = 0
    for (let i = 0; i < m; i++) {
      const v = frames[i].img[k]
      if (Number.isFinite(v)) vals[c++] = v
    }
    if (!c) continue
    let lo = -Infinity
    let hi = Infinity
    if (c >= 4) {
      const s = vals.subarray(0, c).sort()
      const med = medianSorted(s, c)
      for (let i = 0; i < c; i++) dev[i] = Math.abs(s[i] - med)
      const mad = 1.4826 * medianSorted(dev.subarray(0, c).sort(), c)
      let floor = 0
      for (let i = 0; i < m; i++) if (Number.isFinite(frames[i].sigma)) floor = Math.max(floor, frames[i].sigma)
      const t = 5 * Math.max(mad, floor)
      lo = med - t
      hi = med + t
    }
    let sum = 0
    let den = 0
    for (let i = 0; i < m; i++) {
      const v = frames[i].img[k]
      if (!Number.isFinite(v) || v < lo || v > hi) continue
      const wi = useW ? w[i] : 1
      sum += wi * v
      den += wi
    }
    if (den > 0) out[k] = sum / den
  }
  return out
}

interface Plan {
  spec: LiveSpec
  key: string
  grid: LiveGrid
  hits: SkyHit[]
  /** planned survey pass of every requested image (by S3 key) */
  planned: Map<string, number>
  plannedPasses: { start: number; end: number }[]
  doi: Record<string, string>
  indexBuilt: string
  available: number
  matching: number
}

class Assembler {
  frames: LiveFrame[] = []
  private stacks = new Map<string, Float32Array>()
  private dirty = new Set<string>()
  private readonly plan: Plan
  constructor(plan: Plan) {
    this.plan = plan
  }

  add(f: LiveFrame): void {
    this.frames.push(f)
    this.dirty.add(`${this.plan.planned.get(f.hit.key) ?? 0},${f.det}`)
  }

  build(final: boolean, counts: { skipped: number; failed: number; bytes: number; requests: number; seconds: number }): Pack {
    const { plan } = this
    const n = plan.grid.n
    const nn = n * n
    const fr = [...this.frames].sort((a, b) => a.mjd - b.mjd || a.det - b.det)
    const N = fr.length
    const mjd = fr.map((f) => f.mjd)
    const campaign = final ? assignCampaigns(mjd) : fr.map((f) => plan.planned.get(f.hit.key) ?? 0)
    const C = final ? Math.max(0, ...campaign) + 1 : Math.max(1, plan.plannedPasses.length)

    if (final) {
      this.stacks.clear()
      this.dirty.clear()
      for (let i = 0; i < N; i++) this.dirty.add(`${campaign[i]},${fr[i].det}`)
    }
    for (const g of this.dirty) {
      const [c, d] = g.split(',').map(Number)
      this.stacks.set(g, robustStack(fr.filter((f, i) => campaign[i] === c && f.det === d), nn))
    }
    this.dirty.clear()
    const stack = new Float32Array(C * 6 * nn).fill(NaN)
    for (const [g, a] of this.stacks) {
      const [c, d] = g.split(',').map(Number)
      if (c < C) stack.set(a, (c * 6 + d - 1) * nn)
    }

    const img = new Uint16Array(N * nn)
    const flags = new Uint8Array(N * nn)
    for (let i = 0; i < N; i++) {
      img.set(fr[i].q, i * nn)
      const q = fr[i].q
      for (let k = 0; k < nn; k++) if (q[k] === 0) flags[i * nn + k] = 1
    }
    const frames: Frames = {
      mjd: mjd.map((t) => +t.toFixed(6)),
      iso: mjd.map(isoOf),
      det: fr.map((f) => f.det),
      campaign,
      lam: fr.map((f) => r5(f.lam)),
      bw: fr.map((f) => r5(f.bw)),
      lamFit: fr.map((f) => f.lamFit),
      sigma: fr.map((f) => (Number.isFinite(f.sigma) ? +f.sigma.toPrecision(5) : null)),
      sky: fr.map((f) => r5(f.sky)),
      fwhm: fr.map((f) => (Number.isFinite(f.fwhm) ? +f.fwhm.toFixed(2) : null)),
      name: fr.map((f) => f.name),
      collection: fr.map((f) => f.hit.collection),
    }
    const campaigns = Array.from({ length: C }, (_, c) => {
      const mine = mjd.filter((_t, i) => campaign[i] === c)
      const p = plan.plannedPasses[c]
      const a = mine.length ? mine[0] : p?.start
      const b = mine.length ? mine[mine.length - 1] : p?.end
      return { index: c, start: a === undefined ? '' : isoOf(a).slice(0, 10), end: b === undefined ? '' : isoOf(b).slice(0, 10), nFrames: mine.length }
    })
    const colls = [...new Set(fr.map((f) => f.hit.collection))].sort()
    const dois = [...new Set(fr.map((f) => plan.doi[f.hit.release]).filter(Boolean))].sort()
    const { spec } = plan
    const live: LiveInfo = {
      source: 'SPHEREx Level-2 images, NASA/IPAC IRSA public bucket on AWS (nasa-irsa-spherex)',
      complete: final,
      available: plan.available,
      matching: plan.matching,
      requested: plan.hits.length,
      dropped: plan.matching - plan.hits.length,
      loaded: N,
      skipped: counts.skipped,
      failed: counts.failed,
      bytes: counts.bytes,
      requests: counts.requests,
      seconds: counts.seconds,
      detectors: spec.detectors.length ? spec.detectors : [1, 2, 3, 4, 5, 6],
      sizeArcmin: spec.sizeArcmin,
      indexBuilt: plan.indexBuilt,
    }
    const sizeTxt = `${((n * LIVE_SCALE) / 60).toFixed(1)} arcmin`
    const meta: Meta = {
      key: plan.key,
      name: `Live field at ${formatRa(spec.ra)} ${formatDec(spec.dec)}`,
      kind: 'custom',
      blurb:
        `Built in your browser from ${N} SPHEREx Level-2 image${N === 1 ? '' : 's'} in NASA's public archive (detector${live.detectors.length === 1 ? '' : 's'} ${live.detectors.join(', ')}; ${sizeTxt} across). ` +
        'One robust sky level per frame has been removed; pixels are not flag-masked, and the chromatic template needs the ParallaX engine.',
      ra0: spec.ra,
      dec0: spec.dec,
      n,
      scale: LIVE_SCALE,
      target: null,
      release: { collections: colls, doi: dois, retrieved: new Date().toISOString().slice(0, 10) },
      encoding: LIVE_ENCODING,
      sections: {
        img: { offset: 0, dtype: 'uint16', shape: [N, n, n] },
        flags: { offset: 2 * N * nn, dtype: 'uint8', shape: [N, n, n] },
        stack: { offset: 4 * Math.ceil((3 * N * nn) / 4), dtype: 'float32', shape: [C, 6, n, n] },
      },
      frames,
      campaigns,
      gaia: [], wise: [], sso: [], detections: [], candidates: [],
      science: {}, ledger: {},
      live,
    }
    return {
      meta, base: LIVE_BASE, nFrames: N, n, img, flags,
      tpl: null, snrCorr: null, snrNaive: null, snrGated: null,
      stack, nCampaigns: C,
      naivePartner: deriveNaivePartners(frames),
      gatedPartner: deriveGatedPartners(frames),
      partnersDerived: true,
    }
  }
}

// ---- the whole field ---------------------------------------------------------------------

/** Bytes one image costs, on average over detector orientations (rows needed ~ 1.27 n + 2). */
export function bytesPerImage(n: number): number {
  return HEAD_BYTES + 4 * 2040 * Math.min(2040, Math.ceil(1.27 * n) + 2)
}

/** Honest download estimate for `images` images of a field of `sizeArcmin`. */
export function estimateLive(images: number, sizeArcmin: number): { bytes: number; secondsFast: number; secondsSlow: number } {
  const bytes = images * bytesPerImage(liveGridN(sizeArcmin))
  // the bucket served 0.3 to 0.5 MB/s to the team's network; a good connection manages a few MB/s
  return { bytes, secondsFast: bytes / 2e6 + images * 0.08, secondsSlow: bytes / 0.35e6 }
}

export interface LiveResult {
  pack: Pack
  info: LiveInfo
  /** why images were left out: skipped (off the detector) and failed (network) */
  problems: { key: string; why: string; failed: boolean }[]
}

/**
 * Build a field around (ra, dec) from the public archive. Progressive: `onProgress`
 * receives counts after every image and, every `snapshotMs`, a Pack of the frames so far.
 * Rejects with an AbortError when `signal` aborts, and with an Error when no image is usable.
 */
export async function buildLiveField(opts: LiveOptions): Promise<LiveResult> {
  const spec = normaliseSpec(opts)
  const t0 = Date.now()
  const seconds = () => (Date.now() - t0) / 1000
  const concurrency = Math.max(1, Math.min(6, Math.floor(opts.concurrency ?? 5)))
  const net: Net = {
    fetch: opts.fetchImpl ?? ((input, init) => fetch(input, init)),
    sem: new Semaphore(concurrency),
    signal: opts.signal,
    retryBaseMs: opts.retryBaseMs ?? 700,
    bytes: 0,
    requests: 0,
  }
  const prog: LiveProgress = {
    phase: 'index', message: 'Reading the sky index.', available: 0, matching: 0, total: 0, done: 0, loaded: 0, skipped: 0, failed: 0,
    bytes: 0, requests: 0, seconds: 0, pack: null, last: null,
  }
  const emit = () => opts.onProgress?.({ ...prog, bytes: net.bytes, requests: net.requests, seconds: seconds() })
  emit()

  const found = await (opts.query ? opts.query(spec.ra, spec.dec, opts.signal) : querySkyIndex(spec.ra, spec.dec, { base: opts.indexBase, signal: opts.signal }))
  if (opts.signal?.aborted) throw abortError()
  const built = found.manifest.built_utc
  if (!found.hits.length) throw new Error(`SPHEREx has no image of this position in the index of this site (built ${built.slice(0, 10)}).`)
  const matching = spec.detectors.length ? found.hits.filter((h) => spec.detectors.includes(h.det)) : found.hits
  if (!matching.length) throw new Error(`None of the ${found.hits.length} images of this position is from detector ${spec.detectors.join(', ')}.`)
  const hits = subsetEvenly(matching, spec.maxImages)
  const passOf = assignCampaigns(hits.map((h) => h.mjd))
  const plannedPasses: Plan['plannedPasses'] = []
  hits.forEach((h, i) => {
    const p = (plannedPasses[passOf[i]] ??= { start: h.mjd, end: h.mjd })
    p.end = h.mjd
  })
  const plan: Plan = {
    spec, key: liveKey(spec), grid: makeGrid(spec.ra, spec.dec, liveGridN(spec.sizeArcmin)), hits,
    planned: new Map(hits.map((h, i) => [h.key, passOf[i]])), plannedPasses,
    doi: found.manifest.doi ?? {}, indexBuilt: built, available: found.hits.length, matching: matching.length,
  }
  const asm = new Assembler(plan)
  const waves = new Map<string, Promise<WaveTable>>()
  const problems: LiveResult['problems'] = []
  const dropped = matching.length - hits.length
  Object.assign(prog, {
    phase: 'frames', available: found.hits.length, matching: matching.length, total: hits.length,
    message: dropped ? `${matching.length} images match; fetching ${hits.length} evenly spaced in time (${dropped} left out).` : `Fetching ${hits.length} images.`,
  })
  emit()

  const snapshotMs = opts.snapshotMs ?? 1500
  let lastSnap = 0
  let next = 0
  let fatal: unknown = null
  const counts = () => ({ skipped: prog.skipped, failed: prog.failed, bytes: net.bytes, requests: net.requests, seconds: seconds() })
  const worker = async () => {
    while (!fatal && next < hits.length) {
      const hit = hits[next++]
      try {
        const r = await fetchFrame(net, waves, hit, plan.grid)
        if ('frame' in r) {
          asm.add(r.frame)
          prog.loaded++
          prog.last = { img: r.frame.img, n: plan.grid.n, det: r.frame.det, mjd: r.frame.mjd, lam: r.frame.lam }
        } else {
          prog.skipped++
          problems.push({ key: hit.key, why: r.skip, failed: false })
        }
      } catch (e) {
        if (opts.signal?.aborted || (e instanceof DOMException && e.name === 'AbortError')) {
          fatal = abortError()
          return
        }
        prog.failed++
        problems.push({ key: hit.key, why: e instanceof Error ? e.message : String(e), failed: true })
      }
      prog.done++
      if (fatal) return
      if (prog.loaded >= 3 && Date.now() - lastSnap >= snapshotMs && prog.done < hits.length) {
        lastSnap = Date.now()
        prog.pack = asm.build(false, counts())
      }
      emit()
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, hits.length) }, worker))
  if (fatal) throw fatal
  if (opts.signal?.aborted) throw abortError()
  if (!asm.frames.length) {
    const why = problems.find((p) => p.failed)?.why ?? problems[0]?.why ?? 'nothing was returned'
    throw new Error(`None of the ${hits.length} images could be used (${why}).`)
  }
  const pack = asm.build(true, counts())
  Object.assign(prog, { phase: 'done', pack, message: `Done: ${pack.nFrames} frames.` })
  emit()
  return { pack, info: pack.meta.live!, problems }
}
