/**
 * TAN-SIP world coordinates of a SPHEREx Level-2 image: pixel -> sky (SIP polynomial, then
 * the linear matrix, then the gnomonic projection) and sky -> pixel (the reverse, with the
 * AP/BP polynomials as a first guess when present and Newton iterations on the forward
 * polynomial, which is what astropy's all_world2pix converges to).
 * Pixel coordinates are 0-based, as in the pipeline.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { need, num, str, type FitsHeader } from './fits'

const D2R = Math.PI / 180

/** Polynomial sum over c[p][q] * u^p * v^q. */
type Poly = number[][]

export interface TanSip {
  crpix1: number
  crpix2: number
  crval1: number
  crval2: number
  /** degrees per pixel: [cd11, cd12, cd21, cd22] */
  cd: [number, number, number, number]
  inv: [number, number, number, number]
  a: Poly | null
  b: Poly | null
  ap: Poly | null
  bp: Poly | null
}

function poly(h: FitsHeader, name: string): Poly | null {
  const order = num(h, `${name}_ORDER`)
  if (order === undefined || order < 0 || order > 9) return null
  const c: Poly = []
  for (let p = 0; p <= order; p++) {
    c.push([])
    for (let q = 0; q <= order - p; q++) c[p].push(num(h, `${name}_${p}_${q}`) ?? 0)
  }
  return c
}

/** Build the transformation from an image header. Throws if it is not a TAN projection. */
export function wcsFromHeader(h: FitsHeader): TanSip {
  const c1 = str(h, 'CTYPE1') ?? ''
  const c2 = str(h, 'CTYPE2') ?? ''
  if (!c1.startsWith('RA---TAN') || !c2.startsWith('DEC--TAN')) throw new Error(`Unsupported sky projection (${c1}, ${c2}).`)
  let cd: [number, number, number, number]
  if (num(h, 'CD1_1') !== undefined) {
    cd = [need(h, 'CD1_1'), num(h, 'CD1_2') ?? 0, num(h, 'CD2_1') ?? 0, need(h, 'CD2_2')]
  } else {
    const d1 = num(h, 'CDELT1') ?? 1
    const d2 = num(h, 'CDELT2') ?? 1
    cd = [d1 * (num(h, 'PC1_1') ?? 1), d1 * (num(h, 'PC1_2') ?? 0), d2 * (num(h, 'PC2_1') ?? 0), d2 * (num(h, 'PC2_2') ?? 1)]
  }
  const det = cd[0] * cd[3] - cd[1] * cd[2]
  if (!Number.isFinite(det) || det === 0) throw new Error('The image has a singular coordinate matrix.')
  const sip = c1.endsWith('-SIP')
  return {
    crpix1: need(h, 'CRPIX1'),
    crpix2: need(h, 'CRPIX2'),
    crval1: need(h, 'CRVAL1'),
    crval2: need(h, 'CRVAL2'),
    cd,
    inv: [cd[3] / det, -cd[1] / det, -cd[2] / det, cd[0] / det],
    a: sip ? poly(h, 'A') : null,
    b: sip ? poly(h, 'B') : null,
    ap: sip ? poly(h, 'AP') : null,
    bp: sip ? poly(h, 'BP') : null,
  }
}

function evalPoly(c: Poly | null, u: number, v: number): number {
  if (!c) return 0
  let s = 0
  let up = 1
  for (let p = 0; p < c.length; p++) {
    let inner = 0
    const row = c[p]
    for (let q = row.length - 1; q >= 0; q--) inner = inner * v + row[q]
    s += up * inner
    up *= u
  }
  return s
}

/** Value and both partial derivatives. */
function evalPolyD(c: Poly | null, u: number, v: number): [number, number, number] {
  if (!c) return [0, 0, 0]
  let s = 0
  let du = 0
  let dv = 0
  let up = 1
  let upm = 0 // u^(p-1)
  for (let p = 0; p < c.length; p++) {
    const row = c[p]
    let inner = 0
    let dinner = 0
    for (let q = row.length - 1; q >= 0; q--) {
      dinner = dinner * v + inner
      inner = inner * v + row[q]
    }
    s += up * inner
    dv += up * dinner
    du += p * upm * inner
    upm = up
    up *= u
  }
  return [s, du, dv]
}

/** 0-based pixel to sky (degrees, RA in [0, 360)). */
export function pixToWorld(w: TanSip, x: number, y: number): { ra: number; dec: number } {
  const u = x + 1 - w.crpix1
  const v = y + 1 - w.crpix2
  const f = u + evalPoly(w.a, u, v)
  const g = v + evalPoly(w.b, u, v)
  const xi = (w.cd[0] * f + w.cd[1] * g) * D2R
  const eta = (w.cd[2] * f + w.cd[3] * g) * D2R
  const d0 = w.crval2 * D2R
  const den = Math.cos(d0) - eta * Math.sin(d0)
  const ra = w.crval1 + Math.atan2(xi, den) / D2R
  const dec = Math.atan2(Math.sin(d0) + eta * Math.cos(d0), Math.hypot(xi, den)) / D2R
  return { ra: ((ra % 360) + 360) % 360, dec }
}

/** Sky (degrees) to 0-based pixel; null on the far hemisphere or if the inversion fails. */
export function worldToPix(w: TanSip, ra: number, dec: number): { x: number; y: number } | null {
  const a = (ra - w.crval1) * D2R
  const d = dec * D2R
  const d0 = w.crval2 * D2R
  const cosc = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(a)
  if (cosc <= 1e-9) return null
  const xi = (Math.cos(d) * Math.sin(a)) / cosc / D2R
  const eta = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(a)) / cosc / D2R
  // linear part: intermediate pixel offsets (U, V) from the reference pixel
  const U = w.inv[0] * xi + w.inv[1] * eta
  const V = w.inv[2] * xi + w.inv[3] * eta
  let u = U
  let v = V
  if (w.a || w.b) {
    if (w.ap || w.bp) {
      u = U + evalPoly(w.ap, U, V)
      v = V + evalPoly(w.bp, U, V)
    }
    // Newton on u + A(u, v) = U, v + B(u, v) = V
    for (let it = 0; it < 12; it++) {
      const [fa, fau, fav] = evalPolyD(w.a, u, v)
      const [fb, fbu, fbv] = evalPolyD(w.b, u, v)
      const r1 = u + fa - U
      const r2 = v + fb - V
      const j11 = 1 + fau
      const j22 = 1 + fbv
      const det = j11 * j22 - fav * fbu
      if (!Number.isFinite(det) || det === 0) return null
      const du = (j22 * r1 - fav * r2) / det
      const dv = (j11 * r2 - fbu * r1) / det
      u -= du
      v -= dv
      if (Math.abs(du) < 1e-10 && Math.abs(dv) < 1e-10) break
    }
    if (!Number.isFinite(u) || !Number.isFinite(v)) return null
  }
  return { x: u + w.crpix1 - 1, y: v + w.crpix2 - 1 }
}
