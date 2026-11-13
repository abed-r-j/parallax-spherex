/**
 * Sky geometry: gnomonic (TAN) projection both ways on the pack grid, proper-motion
 * propagation, separations and formatting. Pixel (x, y) is 0-based, x to the west (right),
 * y to the north (up), centre at c = (n - 1) / 2, matching pipeline grid_wcs().
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */

const D2R = Math.PI / 180

export interface Grid {
  ra0: number
  dec0: number
  n: number
  scale: number // arcsec per pixel
}

/** Sky (degrees) to pixel on the tangent grid. Returns null on the far hemisphere. */
export function skyToPix(g: Grid, ra: number, dec: number): { x: number; y: number } | null {
  const a = (ra - g.ra0) * D2R
  const d = dec * D2R
  const d0 = g.dec0 * D2R
  const cosc = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(a)
  if (cosc <= 1e-9) return null
  const xi = (Math.cos(d) * Math.sin(a)) / cosc
  const eta = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(a)) / cosc
  const c = (g.n - 1) / 2
  const s = (g.scale / 3600) * D2R
  return { x: c - xi / s, y: c + eta / s }
}

/** Pixel to sky (degrees), RA in [0, 360). */
export function pixToSky(g: Grid, x: number, y: number): { ra: number; dec: number } {
  const c = (g.n - 1) / 2
  const s = (g.scale / 3600) * D2R
  const xi = -(x - c) * s
  const eta = (y - c) * s
  const d0 = g.dec0 * D2R
  const den = Math.cos(d0) - eta * Math.sin(d0)
  const ra = g.ra0 + Math.atan2(xi, den) / D2R
  const dec = Math.atan2(Math.sin(d0) + eta * Math.cos(d0), Math.hypot(xi, den)) / D2R
  return { ra: ((ra % 360) + 360) % 360, dec }
}

/** Julian year of a Modified Julian Date. */
export function mjdToYear(mjd: number): number {
  return 2000 + (mjd - 51544.5) / 365.25
}

/** Move a position by its proper motion (mas/yr, pmRa includes cos dec) from epoch to year. */
export function propagate(
  ra: number,
  dec: number,
  pmRa: number | null | undefined,
  pmDec: number | null | undefined,
  epoch: number,
  year: number,
): { ra: number; dec: number } {
  const dt = year - epoch
  const cd = Math.max(Math.cos(dec * D2R), 1e-6)
  return { ra: ra + ((pmRa ?? 0) * dt) / 3.6e6 / cd, dec: dec + ((pmDec ?? 0) * dt) / 3.6e6 }
}

/** Great-circle separation in arcsec (haversine). */
export function separationArcsec(ra1: number, dec1: number, ra2: number, dec2: number): number {
  const dd = (dec2 - dec1) * D2R
  const da = (ra2 - ra1) * D2R
  const h = Math.sin(dd / 2) ** 2 + Math.cos(dec1 * D2R) * Math.cos(dec2 * D2R) * Math.sin(da / 2) ** 2
  return (2 * Math.asin(Math.min(1, Math.sqrt(h))) / D2R) * 3600
}

/** True if (ra, dec) falls on the n x n grid. */
export function insideGrid(g: Grid, ra: number, dec: number): boolean {
  const p = skyToPix(g, ra, dec)
  return !!p && p.x >= -0.5 && p.x <= g.n - 0.5 && p.y >= -0.5 && p.y <= g.n - 0.5
}

function sexa(v: number, places: number): string {
  const total = Math.round(Math.abs(v) * 3600 * 10 ** places)
  const s = (total % (60 * 10 ** places)) / 10 ** places
  const m = Math.floor(total / (60 * 10 ** places)) % 60
  const h = Math.floor(total / (3600 * 10 ** places))
  const p2 = (k: number) => String(k).padStart(2, '0')
  return `${p2(h)} ${p2(m)} ${s.toFixed(places).padStart(places + 3, '0')}`
}

/** "17 57 47.63" style right ascension from degrees. */
export function formatRa(ra: number): string {
  return sexa((((ra % 360) + 360) % 360) / 15, 2)
}

/** "+04 44 05.1" style declination from degrees. */
export function formatDec(dec: number): string {
  return (dec < 0 ? '-' : '+') + sexa(dec, 1)
}
