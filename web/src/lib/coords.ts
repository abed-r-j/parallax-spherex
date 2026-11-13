/**
 * Parsing of sky coordinates typed by a person: decimal degrees or sexagesimal.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */

export interface SkyPos {
  ra: number
  dec: number
}

const NUM = /[+-]?\d+(?:\.\d*)?|[+-]?\.\d+/g

function sexagesimal(parts: string[]): number | null {
  const neg = parts[0].trim().startsWith('-')
  const v = parts.map((p) => Math.abs(Number(p)))
  if (v.some((x) => !Number.isFinite(x))) return null
  if (v.slice(1).some((x) => x >= 60)) return null
  const val = v[0] + (v[1] ?? 0) / 60 + (v[2] ?? 0) / 3600
  return neg ? -val : val
}

/**
 * Parse "08h55m10.831s -7d14m42.53s", "08 55 10.83 -07 14 42.5", "08:55:10.8 -07:14:42",
 * "133.795 -7.245", "133.795, -7.245" or "8.9197h -7.245d". Returns degrees (ICRS) or null.
 */
export function parseCoords(text: string): SkyPos | null {
  const t = text.trim().toLowerCase().replace(/[−–]/g, '-')
  if (!t || /[^0-9hmsd°'":+\-.,\s]/.test(t)) return null
  const nums = t.match(NUM)
  if (!nums) return null
  let ra: number | null
  let dec: number | null
  if (nums.length === 2) {
    const raHours = /^[+-]?[\d.]+\s*h/.test(t)
    ra = Number(nums[0]) * (raHours ? 15 : 1)
    dec = Number(nums[1])
  } else if (nums.length === 4 || nums.length === 6) {
    const half = nums.length / 2
    const h = sexagesimal(nums.slice(0, half))
    ra = h === null || h < 0 ? null : h * 15
    dec = sexagesimal(nums.slice(half))
  } else {
    return null
  }
  if (ra === null || dec === null || !Number.isFinite(ra) || !Number.isFinite(dec)) return null
  if (ra < 0 || ra >= 360 || dec < -90 || dec > 90) return null
  return { ra, dec }
}
