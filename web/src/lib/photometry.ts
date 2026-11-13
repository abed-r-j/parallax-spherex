/**
 * Measurements on pixels: per-pixel wavelength, aperture sums, spectra on the fly,
 * centroids and CSV export.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { decodeBrightness } from './decode'
import type { Pack } from './types'
import { ujyPerMjySr } from './types'

/** lambda(x, y) = a + bx (x - c) + by (y - c), c = (n - 1) / 2. NaN if the fit is missing. */
export function lamAt(fit: [number | null, number, number] | undefined, x: number, y: number, n: number): number {
  if (!fit || fit[0] == null) return NaN
  const c = (n - 1) / 2
  return fit[0] + fit[1] * (x - c) + fit[2] * (y - c)
}

/**
 * Sum of a (2 half + 1)^2 box centred on integer pixel (x, y). Returns null when the box
 * leaves the image or contains any pixel without data: a partial sum would not be a flux.
 */
export function apertureSum(
  get: (k: number) => number,
  n: number,
  x: number,
  y: number,
  half: number,
): { sum: number; npix: number } | null {
  if (x - half < 0 || y - half < 0 || x + half >= n || y + half >= n) return null
  let sum = 0
  for (let j = y - half; j <= y + half; j++) {
    for (let i = x - half; i <= x + half; i++) {
      const v = get(j * n + i)
      if (!Number.isFinite(v)) return null
      sum += v
    }
  }
  const side = 2 * half + 1
  return { sum, npix: side * side }
}

export interface SpecPoint {
  frame: number
  mjd: number
  iso: string
  det: number
  pass: number
  lam: number
  flux: number // microJy, aperture sum
  err: number // microJy, 1 sigma from frames.sigma
  flagged: boolean
}

/** Aperture flux of pixel (x, y) in every frame against that frame's wavelength there. */
export function spectrumAt(pack: Pack, x: number, y: number, half: number): { points: SpecPoint[]; skipped: number } {
  const { meta, n, img, flags } = pack
  const f = meta.frames
  const k = ujyPerMjySr(meta.scale)
  const nn = n * n
  const points: SpecPoint[] = []
  let skipped = 0
  for (let i = 0; i < pack.nFrames; i++) {
    const o = i * nn
    const ap = apertureSum((p) => decodeBrightness(img[o + p], meta.encoding), n, x, y, half)
    const lam = lamAt(f.lamFit[i], x, y, n)
    const sig = f.sigma[i]
    if (!ap || !Number.isFinite(lam)) {
      skipped++
      continue
    }
    let flagged = false
    if (flags) {
      for (let j = y - half; j <= y + half && !flagged; j++)
        for (let ii = x - half; ii <= x + half; ii++) if (flags[o + j * n + ii] & 10) flagged = true
    }
    points.push({
      frame: i,
      mjd: f.mjd[i],
      iso: f.iso[i],
      det: f.det[i],
      pass: f.campaign[i],
      lam,
      flux: ap.sum * k,
      err: sig == null ? NaN : sig * Math.sqrt(ap.npix) * k,
      flagged,
    })
  }
  return { points, skipped }
}

/** CSV text of a spectrum; `window` marks the points inside the chosen wavelength range. */
export function spectrumCsv(points: SpecPoint[], head: string[], window: [number, number] | null): string {
  const rows = [
    ...head.map((h) => `# ${h}`),
    'frame,mjd,date_utc,detector,survey_pass,wavelength_um,flux_uJy,flux_err_uJy,flagged,in_window',
  ]
  for (const p of points) {
    const inWin = window ? (p.lam >= window[0] && p.lam <= window[1] ? 1 : 0) : ''
    rows.push(
      [p.frame, p.mjd.toFixed(6), p.iso, p.det, p.pass + 1, p.lam.toFixed(5), p.flux.toFixed(2),
        Number.isFinite(p.err) ? p.err.toFixed(2) : '', p.flagged ? 1 : 0, inWin].join(','),
    )
  }
  return rows.join('\n') + '\n'
}

function median(v: number[]): number {
  if (!v.length) return NaN
  const s = [...v].sort((a, b) => a - b)
  const m = s.length >> 1
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

/**
 * Background-subtracted flux-weighted centroid within `r` pixels of (x0, y0), iterated
 * three times. The background is the median of the ring r+1 .. r+4. Returns null if the
 * aperture holds a pixel without data. Quick-look only:
 * SPHEREx images are undersampled, so expect errors of a few tenths of a pixel.
 */
export function centroid(
  img: ArrayLike<number>,
  n: number,
  x0: number,
  y0: number,
  r = 3,
): { x: number; y: number; flux: number; peakSnr: number } | null {
  let cx = x0
  let cy = y0
  let flux = 0
  let peak = 0
  let bgSig = NaN
  for (let it = 0; it < 3; it++) {
    const ring: number[] = []
    const x1 = Math.max(0, Math.floor(cx - r - 4))
    const x2 = Math.min(n - 1, Math.ceil(cx + r + 4))
    const y1 = Math.max(0, Math.floor(cy - r - 4))
    const y2 = Math.min(n - 1, Math.ceil(cy + r + 4))
    for (let y = y1; y <= y2; y++)
      for (let x = x1; x <= x2; x++) {
        const d = Math.hypot(x - cx, y - cy)
        const v = img[y * n + x]
        if (d > r + 1 && d <= r + 4 && Number.isFinite(v)) ring.push(v)
      }
    if (ring.length < 8) return null
    const bg = median(ring)
    bgSig = 1.4826 * median(ring.map((v) => Math.abs(v - bg)))
    let sx = 0
    let sy = 0
    let sw = 0
    peak = 0
    for (let y = y1; y <= y2; y++)
      for (let x = x1; x <= x2; x++) {
        const v = img[y * n + x]
        if (Math.hypot(x - cx, y - cy) > r) continue
        // a blank (saturated or masked) pixel inside the aperture would bias the centre
        if (!Number.isFinite(v)) return null
        const w = Math.max(0, v - bg)
        peak = Math.max(peak, w)
        sx += w * x
        sy += w * y
        sw += w
      }
    if (sw <= 0) return null
    cx = sx / sw
    cy = sy / sw
    flux = sw
  }
  return { x: cx, y: cy, flux, peakSnr: bgSig > 0 ? peak / bgSig : NaN }
}
