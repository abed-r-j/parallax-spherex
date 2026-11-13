/**
 * Display stretch: percentile limits, transfer functions, colour maps and RGBA rendering.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import type { CmapName, StretchKind } from './types'

/** Percentiles (0..100) of the finite values, linear interpolation. NaN if there are none. */
export function percentiles(data: ArrayLike<number>, ps: number[]): number[] {
  const v: number[] = []
  for (let i = 0; i < data.length; i++) if (Number.isFinite(data[i])) v.push(data[i])
  if (!v.length) return ps.map(() => NaN)
  const s = Float64Array.from(v).sort()
  return ps.map((p) => {
    const r = (Math.min(100, Math.max(0, p)) / 100) * (s.length - 1)
    const i = Math.floor(r)
    const f = r - i
    return i + 1 < s.length ? s[i] * (1 - f) + s[i + 1] * f : s[i]
  })
}

/** Transfer function on t in [0, 1] (values outside are clipped). */
export function stretchUnit(kind: StretchKind, t: number): number {
  const c = t <= 0 ? 0 : t >= 1 ? 1 : t
  if (kind === 'asinh') return Math.asinh(c * 10) / Math.asinh(10)
  if (kind === 'log') return Math.log1p(c * 100) / Math.log1p(100)
  return c
}

/** Map a value to [0, 1] between limits; for symmetric limits the stretch acts on |v|. */
export function normalise(kind: StretchKind, v: number, lo: number, hi: number, symmetric: boolean): number {
  if (symmetric) {
    const m = Math.max(Math.abs(lo), Math.abs(hi)) || 1
    const s = stretchUnit(kind, Math.abs(v) / m)
    return 0.5 + (v < 0 ? -0.5 : 0.5) * s
  }
  return stretchUnit(kind, (v - lo) / (hi - lo || 1))
}

type Stop = [number, number, number, number]

const STOPS: Record<CmapName, Stop[]> = {
  grey: [
    [0, 6, 8, 12],
    [1, 250, 248, 240],
  ],
  // dark blue -> teal -> amber -> pale yellow: monotonic in lightness
  perceptual: [
    [0, 5, 8, 20],
    [0.2, 28, 38, 96],
    [0.4, 30, 96, 140],
    [0.6, 54, 156, 136],
    [0.8, 204, 186, 84],
    [1, 252, 244, 190],
  ],
  // negative blue, zero dark neutral, positive amber
  diverging: [
    [0, 176, 222, 255],
    [0.25, 52, 124, 196],
    [0.5, 22, 27, 34],
    [0.75, 196, 116, 36],
    [1, 255, 226, 150],
  ],
}

const lutCache = new Map<CmapName, Uint8Array>()

/** 256-entry RGB lookup table of a colour map. */
export function cmapLut(name: CmapName): Uint8Array {
  const hit = lutCache.get(name)
  if (hit) return hit
  const stops = STOPS[name]
  const lut = new Uint8Array(768)
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    let k = 0
    while (k < stops.length - 2 && t > stops[k + 1][0]) k++
    const a = stops[k]
    const b = stops[k + 1]
    const f = Math.min(1, Math.max(0, (t - a[0]) / (b[0] - a[0])))
    for (let c = 0; c < 3; c++) lut[i * 3 + c] = Math.round(a[c + 1] + (b[c + 1] - a[c + 1]) * f)
  }
  lutCache.set(name, lut)
  return lut
}

export interface RenderOpts {
  kind: StretchKind
  lo: number
  hi: number
  symmetric: boolean
  cmap: CmapName
}

/**
 * Paint a w x h float image (row 0 = south) into RGBA with row 0 at the bottom of the
 * picture (north up). NaN pixels are drawn in a muted hatch colour.
 */
export function renderRgba(data: ArrayLike<number>, w: number, h: number, o: RenderOpts): Uint8ClampedArray<ArrayBuffer> {
  const out = new Uint8ClampedArray(new ArrayBuffer(w * h * 4))
  const lut = cmapLut(o.cmap)
  for (let y = 0; y < h; y++) {
    const row = (h - 1 - y) * w * 4
    for (let x = 0; x < w; x++) {
      const v = data[y * w + x]
      const p = row + x * 4
      if (!Number.isFinite(v)) {
        const on = ((x + y) & 1) === 0
        out[p] = on ? 58 : 48
        out[p + 1] = on ? 50 : 42
        out[p + 2] = on ? 66 : 56
      } else {
        const k = Math.round(normalise(o.kind, v, o.lo, o.hi, o.symmetric) * 255) * 3
        out[p] = lut[k]
        out[p + 1] = lut[k + 1]
        out[p + 2] = lut[k + 2]
      }
      out[p + 3] = 255
    }
  }
  return out
}

/**
 * Catmull-Rom (bicubic) up-sampling by an integer factor. NaN samples are left out and the
 * weights renormalised; an output pixel is NaN when its nearest input pixel is NaN.
 */
export function upsampleBicubic(src: ArrayLike<number>, n: number, k: number): Float32Array {
  const m = n * k
  const out = new Float32Array(m * m)
  const w = (t: number): number => {
    const a = Math.abs(t)
    if (a < 1) return 1.5 * a * a * a - 2.5 * a * a + 1
    if (a < 2) return -0.5 * a * a * a + 2.5 * a * a - 4 * a + 2
    return 0
  }
  for (let oy = 0; oy < m; oy++) {
    const sy = (oy + 0.5) / k - 0.5
    const iy = Math.floor(sy)
    for (let ox = 0; ox < m; ox++) {
      const sx = (ox + 0.5) / k - 0.5
      const ix = Math.floor(sx)
      const near = src[Math.min(n - 1, Math.max(0, Math.round(sy))) * n + Math.min(n - 1, Math.max(0, Math.round(sx)))]
      if (!Number.isFinite(near)) {
        out[oy * m + ox] = NaN
        continue
      }
      let acc = 0
      let ws = 0
      for (let j = -1; j <= 2; j++) {
        const yy = Math.min(n - 1, Math.max(0, iy + j))
        const wy = w(sy - (iy + j))
        for (let i = -1; i <= 2; i++) {
          const xx = Math.min(n - 1, Math.max(0, ix + i))
          const v = src[yy * n + xx]
          if (!Number.isFinite(v)) continue
          const ww = wy * w(sx - (ix + i))
          acc += ww * v
          ws += ww
        }
      }
      out[oy * m + ox] = ws > 0.3 ? acc / ws : near
    }
  }
  return out
}
