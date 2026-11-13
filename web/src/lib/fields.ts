/**
 * The five challenge targets and the matching of typed coordinates to precomputed fields.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import type { IndexField } from './types'
import { insideGrid, separationArcsec } from './wcs'

export interface Preset {
  key: string
  name: string
  /** catalogue position (degrees) at `epoch`, as given in the challenge or SIMBAD */
  ra: number
  dec: number
  epoch: number
  what: string
}

export const PRESETS: Preset[] = [
  { key: 'barnard', name: "Barnard's Star", ra: 269.452075, dec: 4.693391, epoch: 2000, what: 'fast-moving star' },
  { key: 'epsindi', name: 'Epsilon Indi B', ra: 331.043833, dec: -56.782694, epoch: 2000, what: 'brown-dwarf pair' },
  { key: 'wise0855', name: 'WISE 0855−0714', ra: 133.795129, dec: -7.245147, epoch: 2014.3, what: 'coldest brown dwarf' },
  { key: 'rwaur', name: 'RW Aurigae', ra: 76.956417, dec: 30.401417, epoch: 2000, what: 'young variable star' },
  { key: 'rdra', name: 'R Draconis', ra: 248.1675, dec: 66.755, epoch: 2000, what: 'pulsating red giant' },
]

/** The first field whose grid contains the position. */
export function fieldContaining(fields: IndexField[], ra: number, dec: number): IndexField | null {
  return fields.find((f) => insideGrid({ ra0: f.ra, dec0: f.dec, n: f.n, scale: f.scale }, ra, dec)) ?? null
}

/** Fields sorted by distance from the position (arcsec). */
export function nearestFields(fields: IndexField[], ra: number, dec: number, k = 3): { field: IndexField; sep: number }[] {
  return fields
    .map((field) => ({ field, sep: separationArcsec(ra, dec, field.ra, field.dec) }))
    .sort((a, b) => a.sep - b.sep)
    .slice(0, k)
}

/**
 * A challenge target whose catalogue position is within `tol` arcsec. Fast stars have left
 * their catalogue position, so a field can exist for a target even when the typed
 * coordinates fall outside it.
 */
export function presetNear(ra: number, dec: number, tol = 60): Preset | null {
  return PRESETS.find((p) => separationArcsec(ra, dec, p.ra, p.dec) <= tol) ?? null
}

/** Human-readable angular distance. */
export function formatSep(arcsec: number): string {
  if (arcsec < 90) return `${arcsec.toFixed(0)} arcsec`
  if (arcsec < 5400) return `${(arcsec / 60).toFixed(1)} arcmin`
  return `${(arcsec / 3600).toFixed(1)}°`
}
