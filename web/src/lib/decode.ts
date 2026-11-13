/**
 * Decoding of cube.bin: typed-array views located by offset, brightness decoding,
 * signal-to-noise cubes, per-pass stacks, and fallback partner lists.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import type { Frames, Meta, Pack, SectionMeta, TypedArray } from './types'

const CTORS: Record<string, { new (b: ArrayBuffer, o?: number, l?: number): TypedArray; BYTES_PER_ELEMENT: number }> = {
  uint16: Uint16Array,
  uint8: Uint8Array,
  int8: Int8Array,
  float32: Float32Array,
}

/** A typed-array view of one section, or null if it is absent, malformed or out of bounds. */
export function sectionView(buf: ArrayBuffer, sec: SectionMeta | undefined, dtype: string): TypedArray | null {
  if (!sec || sec.dtype !== dtype) return null
  const ctor = CTORS[dtype]
  if (!ctor) return null
  const len = sec.shape.reduce((a, b) => a * b, 1)
  const bytes = len * ctor.BYTES_PER_ELEMENT
  if (len === 0 || sec.offset < 0 || sec.offset + bytes > buf.byteLength) return null
  if (sec.offset % ctor.BYTES_PER_ELEMENT !== 0) {
    return new ctor(buf.slice(sec.offset, sec.offset + bytes))
  }
  return new ctor(buf, sec.offset, len)
}

/** v = soft * sinh(lo + (q - 1) / 65534 * (hi - lo)); q = 0 means no data (NaN). */
export function decodeBrightness(q: number, enc: Meta['encoding']): number {
  if (q === 0) return NaN
  return enc.soft * Math.sinh(enc.lo + ((q - 1) / 65534) * (enc.hi - enc.lo))
}

/** Inverse of decodeBrightness (used by tests and synthetic fixtures). */
export function encodeBrightness(v: number, enc: Meta['encoding']): number {
  if (!Number.isFinite(v)) return 0
  const t = (Math.asinh(v / enc.soft) - enc.lo) / (enc.hi - enc.lo)
  return 1 + Math.round(Math.min(1, Math.max(0, t)) * 65534)
}

const lutCache = new WeakMap<object, Float32Array>()

function brightnessLut(enc: Meta['encoding']): Float32Array {
  let lut = lutCache.get(enc)
  if (!lut) {
    lut = new Float32Array(65536)
    for (let q = 0; q < 65536; q++) lut[q] = decodeBrightness(q, enc)
    lutCache.set(enc, lut)
  }
  return lut
}

/** Decode frame i of an encoded uint16 cube into MJy/sr (NaN = no data). */
export function decodeFrame(cube: Uint16Array, i: number, n: number, enc: Meta['encoding']): Float32Array {
  const lut = brightnessLut(enc)
  const out = new Float32Array(n * n)
  const o = i * n * n
  for (let k = 0; k < n * n; k++) out[k] = lut[cube[o + k]]
  return out
}

/** Decode frame i of an int8 signal-to-noise cube (value * 4, -128 = undefined). */
export function decodeSnr(cube: Int8Array, i: number, n: number): Float32Array {
  const out = new Float32Array(n * n)
  const o = i * n * n
  for (let k = 0; k < n * n; k++) {
    const q = cube[o + k]
    out[k] = q === -128 ? NaN : q / 4
  }
  return out
}

/** True if every value of frame i in an int8 SNR cube is undefined. */
export function snrAllUndefined(cube: Int8Array, i: number, n: number): boolean {
  const o = i * n * n
  for (let k = 0; k < n * n; k++) if (cube[o + k] !== -128) return false
  return true
}

/** The per-pass, per-detector stack image (pass c, detector d = 1..6), or null. */
export function stackImage(pack: Pack, c: number, d: number): Float32Array | null {
  if (!pack.stack || c < 0 || c >= pack.nCampaigns || d < 1 || d > 6) return null
  const nn = pack.n * pack.n
  const o = (c * 6 + (d - 1)) * nn
  const a = pack.stack.subarray(o, o + nn)
  for (let k = 0; k < nn; k++) if (Number.isFinite(a[k])) return a
  return null
}

/** Same detector, another survey pass, nearest in time; -1 if none (contract definition). */
export function deriveNaivePartners(f: Frames): Int32Array {
  const N = f.mjd.length
  const out = new Int32Array(N).fill(-1)
  for (let i = 0; i < N; i++) {
    let best = -1
    let bd = Infinity
    for (let j = 0; j < N; j++) {
      if (f.det[j] !== f.det[i] || f.campaign[j] === f.campaign[i]) continue
      const d = Math.abs(f.mjd[j] - f.mjd[i])
      if (d < bd) {
        bd = d
        best = j
      }
    }
    out[i] = best
  }
  return out
}

/** Other-pass frame closest in centre wavelength, accepted within gate * bandwidth; else -1. */
export function deriveGatedPartners(f: Frames, gate = 0.5): Int32Array {
  const N = f.mjd.length
  const out = new Int32Array(N).fill(-1)
  for (let i = 0; i < N; i++) {
    const li = f.lam[i]
    const bw = f.bw[i]
    if (li == null || bw == null) continue
    let best = -1
    let bd = Infinity
    for (let j = 0; j < N; j++) {
      const lj = f.lam[j]
      if (lj == null || f.campaign[j] === f.campaign[i]) continue
      const d = Math.abs(lj - li)
      if (d < bd) {
        bd = d
        best = j
      }
    }
    if (best >= 0 && bd < gate * bw) out[i] = best
  }
  return out
}

function partnerList(list: number[] | undefined, N: number): Int32Array | null {
  if (!Array.isArray(list) || list.length !== N) return null
  return Int32Array.from(list, (v) => (Number.isInteger(v) && v >= 0 && v < N ? v : -1))
}

/** Assemble a Pack from meta.json and the cube.bin buffer. Throws only if 'img' is unusable. */
export function buildPack(meta: Meta, buf: ArrayBuffer, base: string): Pack {
  const s = meta.sections ?? {}
  const img = sectionView(buf, s.img, 'uint16') as Uint16Array | null
  if (!img || !s.img || s.img.shape.length !== 3) throw new Error('The data pack has no usable image section.')
  const [N, n] = s.img.shape
  const same = (sec: SectionMeta | undefined) => !!sec && sec.shape.length === 3 && sec.shape[0] === N && sec.shape[1] === n
  const opt = <T extends TypedArray>(name: string, dtype: string): T | null =>
    same(s[name]) ? (sectionView(buf, s[name], dtype) as T | null) : null
  const stackOk = !!s.stack && s.stack.shape.length === 4 && s.stack.shape[1] === 6 && s.stack.shape[2] === n
  const stack = stackOk ? (sectionView(buf, s.stack, 'float32') as Float32Array | null) : null
  const naive = partnerList(meta.frames.naivePartner, N)
  const gated = partnerList(meta.frames.gatedPartner, N)
  return {
    meta,
    base,
    nFrames: N,
    n,
    img,
    flags: opt<Uint8Array>('flags', 'uint8'),
    tpl: opt<Uint16Array>('tpl', 'uint16'),
    snrCorr: opt<Int8Array>('snrCorr', 'int8'),
    snrNaive: opt<Int8Array>('snrNaive', 'int8'),
    snrGated: opt<Int8Array>('snrGated', 'int8'),
    stack,
    nCampaigns: stack && s.stack ? s.stack.shape[0] : Math.max(0, ...meta.frames.campaign) + 1,
    naivePartner: naive ?? deriveNaivePartners(meta.frames),
    gatedPartner: gated ?? deriveGatedPartners(meta.frames),
    partnersDerived: !naive || !gated,
  }
}

/** Fetch and assemble a pack from `${base}/${key}/`. */
export async function loadPack(base: string, key: string, signal?: AbortSignal): Promise<Pack> {
  const root = `${base.replace(/\/$/, '')}/${encodeURIComponent(key)}`
  const [mr, cr] = await Promise.all([fetch(`${root}/meta.json`, { signal }), fetch(`${root}/cube.bin`, { signal })])
  if (!mr.ok) throw new Error(`Field "${key}" was not found (meta.json: HTTP ${mr.status}).`)
  if (!cr.ok) throw new Error(`Field "${key}" has no pixel data (cube.bin: HTTP ${cr.status}).`)
  const meta = (await mr.json()) as Meta
  return buildPack(meta, await cr.arrayBuffer(), base)
}
