/**
 * Image products for every view mode: decoded frames, the three kinds of difference,
 * user stacks (Add), A - B (Subtract), the wavelength-mismatch map and flag overlays.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { decodeFrame, decodeSnr, snrAllUndefined, stackImage } from './decode'
import { lamAt } from './photometry'
import type { Pack, Selection } from './types'

export interface Product {
  data: Float32Array | null
  unit: 'MJy/sr' | 'SNR'
  /** shown under the picture when the product was derived in the browser */
  note?: string
  /** why there is no picture */
  missing?: string
  partner?: number
}

const frameCache = new WeakMap<Pack, Map<string, Float32Array>>()

function cached(pack: Pack, key: string, make: () => Float32Array): Float32Array {
  let m = frameCache.get(pack)
  if (!m) frameCache.set(pack, (m = new Map()))
  let a = m.get(key)
  if (!a) m.set(key, (a = make()))
  return a
}

/** Frame i in MJy/sr. */
export function frameImage(pack: Pack, i: number): Float32Array {
  return cached(pack, `i${i}`, () => decodeFrame(pack.img, i, pack.n, pack.meta.encoding))
}

function pairSnr(pack: Pack, i: number, j: number): Float32Array {
  const a = frameImage(pack, i)
  const b = frameImage(pack, j)
  const si = pack.meta.frames.sigma[i] ?? NaN
  const sj = pack.meta.frames.sigma[j] ?? NaN
  const s = Math.hypot(si, sj)
  const out = new Float32Array(a.length)
  for (let k = 0; k < a.length; k++) out[k] = (a[k] - b[k]) / s
  return out
}

const BROWSER_NOTE = 'Computed in your browser from the two frames and their median noise (the pipeline has not added its calibrated version to this field yet).'

function pairProduct(pack: Pack, i: number, j: number, cube: Int8Array | null, none: string): Product {
  if (j < 0) return { data: null, unit: 'SNR', missing: none }
  if (cube) {
    if (snrAllUndefined(cube, i, pack.n)) return { data: null, unit: 'SNR', missing: none, partner: j }
    return { data: decodeSnr(cube, i, pack.n), unit: 'SNR', partner: j }
  }
  return { data: pairSnr(pack, i, j), unit: 'SNR', partner: j, note: BROWSER_NOTE }
}

/** The chromatic difference (frame minus its chromatic template) as signal-to-noise. */
export function chromaProduct(pack: Pack, i: number): Product {
  const n = pack.n
  if (pack.snrCorr) {
    if (snrAllUndefined(pack.snrCorr, i, n))
      return { data: null, unit: 'SNR', missing: 'The pipeline could not predict this frame from the other survey passes.' }
    return { data: decodeSnr(pack.snrCorr, i, n), unit: 'SNR' }
  }
  if (pack.tpl) {
    const a = frameImage(pack, i)
    const t = decodeFrame(pack.tpl, i, n, pack.meta.encoding)
    const s = pack.meta.frames.sigma[i] ?? NaN
    const out = new Float32Array(a.length)
    for (let k = 0; k < a.length; k++) out[k] = (a[k] - t[k]) / s
    return { data: out, unit: 'SNR', note: 'Frame minus template, divided by the frame’s median noise in your browser.' }
  }
  return {
    data: null,
    unit: 'SNR',
    missing: 'This field does not carry a chromatic template yet. It appears here as soon as the pipeline adds it.',
  }
}

export function naiveProduct(pack: Pack, i: number): Product {
  return pairProduct(pack, i, pack.naivePartner[i], pack.snrNaive, 'No frame from another survey pass in this detector, so there is nothing to subtract.')
}

export function gatedProduct(pack: Pack, i: number): Product {
  return pairProduct(pack, i, pack.gatedPartner[i], pack.snrGated, 'No usable partner: no frame from another survey pass lies within half a bandwidth of this colour.')
}

/** The template image of frame i in MJy/sr, or null. */
export function templateImage(pack: Pack, i: number): Float32Array | null {
  return pack.tpl ? decodeFrame(pack.tpl, i, pack.n, pack.meta.encoding) : null
}

/** Frames picked by a selection (`current` resolves kind 'frame' with frame < 0). */
export function selectionFrames(pack: Pack, sel: Selection, current: number): number[] {
  if (sel.kind === 'frame') return [sel.frame >= 0 && sel.frame < pack.nFrames ? sel.frame : current]
  const f = pack.meta.frames
  const out: number[] = []
  for (let i = 0; i < pack.nFrames; i++) {
    if (sel.pass >= 0 && f.campaign[i] !== sel.pass) continue
    if (sel.det > 0 && f.det[i] !== sel.det) continue
    out.push(i)
  }
  return out
}

/** Plain mean of the given frames, ignoring pixels without data. */
export function meanImage(pack: Pack, frames: number[]): Float32Array | null {
  if (!frames.length) return null
  const nn = pack.n * pack.n
  const sum = new Float64Array(nn)
  const cnt = new Uint16Array(nn)
  for (const i of frames) {
    const a = frameImage(pack, i)
    for (let k = 0; k < nn; k++)
      if (Number.isFinite(a[k])) {
        sum[k] += a[k]
        cnt[k]++
      }
  }
  const out = new Float32Array(nn)
  for (let k = 0; k < nn; k++) out[k] = cnt[k] ? sum[k] / cnt[k] : NaN
  return out
}

export function subtractImages(a: Float32Array, b: Float32Array): Float32Array {
  const out = new Float32Array(a.length)
  for (let k = 0; k < a.length; k++) out[k] = a[k] - b[k]
  return out
}

/** Per-pixel wavelength mismatch of frames i and j in units of frame i's bandwidth. */
export function mismatchMap(pack: Pack, i: number, j: number): Float32Array | null {
  const f = pack.meta.frames
  const bw = f.bw[i]
  if (j < 0 || bw == null || f.lamFit[i]?.[0] == null || f.lamFit[j]?.[0] == null) return null
  const n = pack.n
  const out = new Float32Array(n * n)
  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++) out[y * n + x] = (lamAt(f.lamFit[i], x, y, n) - lamAt(f.lamFit[j], x, y, n)) / bw
  return out
}

/** Colours of the four web flag bits (r, g, b, alpha 0..255). */
export const FLAG_STYLE: { bit: number; label: string; rgba: [number, number, number, number] }[] = [
  { bit: 1, label: 'No data / dead pixel', rgba: [150, 150, 170, 190] },
  { bit: 2, label: 'Suspect (transient, overflow, non-linear, persistence)', rgba: [240, 80, 70, 170] },
  { bit: 8, label: 'Pipeline outlier', rgba: [226, 96, 220, 170] },
  { bit: 4, label: 'Catalogued source', rgba: [70, 200, 220, 90] },
]

/** RGBA overlay (north up) of the flags of frame i; the first matching bit in FLAG_STYLE wins. */
export function flagsRgba(flags: Uint8Array, i: number, n: number): Uint8ClampedArray<ArrayBuffer> {
  const out = new Uint8ClampedArray(new ArrayBuffer(n * n * 4))
  const o = i * n * n
  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++) {
      const v = flags[o + y * n + x]
      if (!v) continue
      const st = FLAG_STYLE.find((s) => v & s.bit)
      if (!st) continue
      out.set(st.rgba, ((n - 1 - y) * n + x) * 4)
    }
  return out
}

export interface PassEntry {
  pass: number
  det: number
}

/** (pass, detector) stacks that hold data, ordered by detector then pass. */
export function passEntries(pack: Pack, det: number): PassEntry[] {
  const out: PassEntry[] = []
  for (let d = 1; d <= 6; d++) {
    if (det > 0 && d !== det) continue
    for (let c = 0; c < pack.nCampaigns; c++) if (stackImage(pack, c, d)) out.push({ pass: c, det: d })
  }
  return out
}

/** Indices of frames that pass the detector and wavelength filters, in time order. */
export function filterFrames(pack: Pack, det: number, lamMin: number, lamMax: number): number[] {
  const f = pack.meta.frames
  const out: number[] = []
  for (let i = 0; i < pack.nFrames; i++) {
    if (det > 0 && f.det[i] !== det) continue
    const l = f.lam[i]
    if (l != null && (l < lamMin || l > lamMax)) continue
    out.push(i)
  }
  return out
}
