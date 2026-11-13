/**
 * The small part of FITS that the live path needs: header cards to typed values
 * (HIERARCH tolerant), big-endian float32 / int32 readers, and the SPHEREx WCS-WAVE
 * binary table (wavelength and bandwidth on a coarse grid of detector control points).
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */

export const FITS_BLOCK = 2880
const CARD = 80

export type FitsValue = string | number | boolean

export interface FitsHeader {
  cards: Map<string, FitsValue>
  history: string[]
  /** bytes of the header including padding to a whole 2880-byte block */
  bytes: number
}

function ascii(buf: Uint8Array, a: number, b: number): string {
  let s = ''
  for (let i = a; i < b; i++) s += String.fromCharCode(buf[i])
  return s
}

function parseValue(text: string): FitsValue | null {
  const t = text.trimStart()
  if (t.startsWith("'")) {
    // a quoted string; a doubled quote is a literal quote
    let out = ''
    for (let i = 1; i < t.length; i++) {
      if (t[i] === "'") {
        if (t[i + 1] === "'") {
          out += "'"
          i++
        } else break
      } else out += t[i]
    }
    return out.trimEnd()
  }
  const slash = t.indexOf('/')
  const v = (slash >= 0 ? t.slice(0, slash) : t).trim()
  if (v === '') return null
  if (v === 'T') return true
  if (v === 'F') return false
  const x = Number(v.replace(/[dD]/, 'E'))
  return Number.isFinite(x) ? x : v
}

/**
 * Parse the header that starts at byte `offset`. Returns null when the END card is not
 * inside the buffer (the caller then fetches more bytes).
 */
export function parseHeader(buf: Uint8Array, offset = 0): FitsHeader | null {
  const cards = new Map<string, FitsValue>()
  const history: string[] = []
  for (let o = offset; o + CARD <= buf.length; o += CARD) {
    const key = ascii(buf, o, o + 8).trimEnd()
    if (key === 'END') {
      const used = o + CARD - offset
      return { cards, history, bytes: Math.ceil(used / FITS_BLOCK) * FITS_BLOCK }
    }
    const rest = ascii(buf, o + 8, o + CARD)
    if (key === 'HISTORY') {
      history.push(rest.trim())
      continue
    }
    if (key === '' || key === 'COMMENT' || key === 'CONTINUE') continue
    if (key === 'HIERARCH') {
      const eq = rest.indexOf('=')
      if (eq < 0) continue
      const name = rest.slice(0, eq).trim().replace(/\s+/g, ' ')
      const val = parseValue(rest.slice(eq + 1))
      if (name && val !== null) cards.set(name, val)
      continue
    }
    if (rest[0] !== '=') continue
    const val = parseValue(rest.slice(1))
    if (val !== null) cards.set(key, val)
  }
  return null
}

export function num(h: FitsHeader, key: string): number | undefined {
  const v = h.cards.get(key)
  return typeof v === 'number' ? v : undefined
}

export function need(h: FitsHeader, key: string): number {
  const v = num(h, key)
  if (v === undefined) throw new Error(`The FITS header has no usable ${key}.`)
  return v
}

export function str(h: FitsHeader, key: string): string | undefined {
  const v = h.cards.get(key)
  return v === undefined ? undefined : String(v)
}

/** Bytes of the data unit that follows a header, padded to whole blocks. */
export function dataBytes(h: FitsHeader): number {
  const naxis = num(h, 'NAXIS') ?? 0
  if (naxis === 0) return 0
  let n = 1
  for (let i = 1; i <= naxis; i++) n *= need(h, `NAXIS${i}`)
  const bytes = (Math.abs(need(h, 'BITPIX')) / 8) * (num(h, 'GCOUNT') ?? 1) * ((num(h, 'PCOUNT') ?? 0) + n)
  return Math.ceil(bytes / FITS_BLOCK) * FITS_BLOCK
}

/** `count` big-endian IEEE float32 values starting at byte `offset`. */
export function float32BE(buf: Uint8Array, offset: number, count: number): Float32Array {
  const v = new DataView(buf.buffer, buf.byteOffset + offset, count * 4)
  const out = new Float32Array(count)
  for (let i = 0; i < count; i++) out[i] = v.getFloat32(i * 4, false)
  return out
}

/** `count` big-endian int32 values starting at byte `offset`. */
export function int32BE(buf: Uint8Array, offset: number, count: number): Int32Array {
  const v = new DataView(buf.buffer, buf.byteOffset + offset, count * 4)
  const out = new Int32Array(count)
  for (let i = 0; i < count; i++) out[i] = v.getInt32(i * 4, false)
  return out
}

export interface WaveTable {
  /** control points in detector (1-based FITS) pixel coordinates */
  x: Float64Array
  y: Float64Array
  /** [iy][ix][k]: k = 0 wavelength, 1 bandwidth (micron) */
  values: Float32Array
}

/** Offset of the last HDU inside a buffer that ends at the end of the file, or -1. */
export function lastHduOffset(tail: Uint8Array): number {
  for (let o = tail.length - 2 * FITS_BLOCK; o >= 0; o -= FITS_BLOCK) {
    if (ascii(tail, o, o + 8) !== 'XTENSION') continue
    const h = parseHeader(tail, o)
    if (h && o + h.bytes + dataBytes(h) === tail.length) return o
  }
  return -1
}

/**
 * Read the WCS-WAVE table from the tail of a Level-2 file (the buffer must end at the end
 * of the file). One row: X (nx int32), Y (ny int32), VALUES (ny x nx x 2 float32).
 */
export function readWaveTable(tail: Uint8Array): WaveTable {
  const o = lastHduOffset(tail)
  const h = o < 0 ? null : parseHeader(tail, o)
  if (!h || str(h, 'EXTNAME') !== 'WCS-WAVE') throw new Error('The last part of the file is not the WCS-WAVE wavelength table.')
  const cols: Record<string, { offset: number; count: number; type: string }> = {}
  let at = o + h.bytes
  for (let i = 1; i <= need(h, 'TFIELDS'); i++) {
    const m = /^(\d*)([A-Z])/.exec(str(h, `TFORM${i}`) ?? '')
    if (!m) throw new Error(`The wavelength table has an unreadable column format (TFORM${i}).`)
    const count = m[1] === '' ? 1 : Number(m[1])
    const size = ({ J: 4, E: 4, D: 8, I: 2, K: 8, B: 1, L: 1, A: 1 } as Record<string, number>)[m[2]]
    if (!size) throw new Error(`The wavelength table has an unsupported column type ${m[2]}.`)
    cols[str(h, `TTYPE${i}`) ?? `COL${i}`] = { offset: at, count, type: m[2] }
    at += count * size
  }
  const X = cols.X
  const Y = cols.Y
  const V = cols.VALUES
  if (!X || !Y || !V || X.type !== 'J' || Y.type !== 'J' || V.type !== 'E') throw new Error('The wavelength table lacks the X, Y or VALUES column.')
  if (V.count !== 2 * X.count * Y.count || X.count < 2 || Y.count < 2) throw new Error('The wavelength table has an unexpected shape.')
  return {
    x: Float64Array.from(int32BE(tail, X.offset, X.count)),
    y: Float64Array.from(int32BE(tail, Y.offset, Y.count)),
    values: float32BE(tail, V.offset, V.count),
  }
}

/** Index of the grid interval that holds v: clip(searchsorted(g, v) - 1, 0, len - 2). */
function interval(g: Float64Array, v: number): number {
  let lo = 0
  let hi = g.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (g[mid] < v) lo = mid + 1
    else hi = mid
  }
  return Math.max(0, Math.min(g.length - 2, lo - 1))
}

/**
 * Wavelength and bandwidth (micron) at detector coordinates (xd, yd) in 1-based FITS
 * pixels: bilinear interpolation between control points, extrapolating linearly past
 * the outermost ones (as the pipeline's wavelength_at does).
 */
export function waveAt(t: WaveTable, xd: number, yd: number): [number, number] {
  const nx = t.x.length
  const ix = interval(t.x, xd)
  const iy = interval(t.y, yd)
  const tx = (xd - t.x[ix]) / (t.x[ix + 1] - t.x[ix])
  const ty = (yd - t.y[iy]) / (t.y[iy + 1] - t.y[iy])
  const a = (iy * nx + ix) * 2
  const b = a + 2
  const c = ((iy + 1) * nx + ix) * 2
  const d = c + 2
  const v = t.values
  const w00 = (1 - tx) * (1 - ty)
  const w10 = tx * (1 - ty)
  const w01 = (1 - tx) * ty
  const w11 = tx * ty
  return [v[a] * w00 + v[b] * w10 + v[c] * w01 + v[d] * w11, v[a + 1] * w00 + v[b + 1] * w10 + v[c + 1] * w01 + v[d + 1] * w11]
}
