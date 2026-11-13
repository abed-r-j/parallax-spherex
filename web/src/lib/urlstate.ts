/**
 * The view state and its round trip through the page URL, so that any view can be
 * shared or embedded: ?field=&ra=&dec=&fov=&det=&mode=&frame=&embed=1 (plus display extras).
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import type { CmapName, Mode, Seq, StretchKind } from './types'

export type Page = 'home' | 'view' | 'how' | 'about'

export const OVERLAYS = ['target', 'track', 'gaia', 'wise', 'sso', 'flags', 'mismatch', 'detections', 'candidates'] as const
export type OverlayName = (typeof OVERLAYS)[number]

export interface ViewState {
  page: Page
  field: string | null
  ra: number | null
  dec: number | null
  fov: number // arcmin, 0 = whole field
  det: number // 0 = all detectors
  mode: Mode
  frame: number
  seq: Seq | null // null = the field's default
  embed: boolean
  engine: string | null
  stretch: StretchKind
  cmap: CmapName | null // null = default for the mode
  pLo: number
  pHi: number
  smooth: boolean | null // null = the field's default
  lamMin: number
  lamMax: number
  overlays: OverlayName[] | null // null = defaults
  pix: [number, number] | null // pixel picked for the spectrum
  ap: number // aperture half-width in pixels
}

export const DEFAULT_STATE: ViewState = {
  page: 'home',
  field: null,
  ra: null,
  dec: null,
  fov: 0,
  det: 0,
  mode: 'image',
  frame: 0,
  seq: null,
  embed: false,
  engine: null,
  stretch: 'asinh',
  cmap: null,
  pLo: 1,
  pHi: 99.7,
  smooth: null,
  lamMin: 0.7,
  lamMax: 5.1,
  overlays: null,
  pix: null,
  ap: 1,
}

const MODES: Mode[] = ['image', 'chroma', 'naive', 'gated', 'compare', 'add', 'sub']
const STRETCHES: StretchKind[] = ['asinh', 'linear', 'log']
const CMAPS: CmapName[] = ['grey', 'perceptual', 'diverging']

function num(v: string | null): number | null {
  if (v === null || v.trim() === '') return null
  const x = Number(v)
  return Number.isFinite(x) ? x : null
}

function pick<T extends string>(v: string | null, list: readonly T[]): T | null {
  return v !== null && (list as readonly string[]).includes(v) ? (v as T) : null
}

/** Read a view state from a query string ("?a=b" or "a=b"). Unknown or bad values fall back. */
export function parseQuery(query: string): ViewState {
  const q = new URLSearchParams(query)
  const s: ViewState = { ...DEFAULT_STATE }
  const ra = num(q.get('ra'))
  const dec = num(q.get('dec'))
  if (ra !== null && dec !== null && ra >= 0 && ra < 360 && dec >= -90 && dec <= 90) {
    s.ra = ra
    s.dec = dec
  }
  const field = q.get('field')
  if (field && /^[\w.-]{1,64}$/.test(field)) s.field = field
  s.fov = Math.max(0, num(q.get('fov')) ?? 0)
  const det = num(q.get('det'))
  s.det = det !== null && Number.isInteger(det) && det >= 1 && det <= 6 ? det : 0
  s.mode = pick(q.get('mode'), MODES) ?? 'image'
  const frame = num(q.get('frame'))
  s.frame = frame !== null && frame >= 0 ? Math.floor(frame) : 0
  s.seq = pick(q.get('seq'), ['frames', 'passes'] as const)
  s.embed = q.get('embed') === '1'
  const engine = q.get('engine')
  if (engine && /^https?:\/\/[^\s]+$/.test(engine)) s.engine = engine.replace(/\/+$/, '')
  s.stretch = pick(q.get('st'), STRETCHES) ?? 'asinh'
  s.cmap = pick(q.get('cm'), CMAPS)
  const lim = (q.get('lim') ?? '').split(',').map(Number)
  if (lim.length === 2 && lim.every(Number.isFinite) && lim[0] >= 0 && lim[1] <= 100 && lim[0] < lim[1]) {
    s.pLo = lim[0]
    s.pHi = lim[1]
  }
  const sm = q.get('sm')
  s.smooth = sm === '1' ? true : sm === '0' ? false : null
  const lam = (q.get('lam') ?? '').split(',').map(Number)
  if (lam.length === 2 && lam.every(Number.isFinite) && lam[0] < lam[1]) {
    s.lamMin = lam[0]
    s.lamMax = lam[1]
  }
  const ov = q.get('ov')
  if (ov !== null) s.overlays = ov.split(',').filter((o): o is OverlayName => (OVERLAYS as readonly string[]).includes(o))
  const pix = (q.get('pix') ?? '').split(',').map(Number)
  if (pix.length === 2 && pix.every((v) => Number.isInteger(v) && v >= 0)) s.pix = [pix[0], pix[1]]
  const ap = num(q.get('ap'))
  if (ap !== null && [0, 1, 2].includes(ap)) s.ap = ap
  const page = pick(q.get('page'), ['how', 'about'] as const)
  s.page = page ?? (s.field || s.ra !== null ? 'view' : 'home')
  return s
}

/** Write a view state as a query string (without "?"); defaults are left out. */
export function toQuery(s: ViewState): string {
  const q = new URLSearchParams()
  const d = DEFAULT_STATE
  if (s.page === 'how' || s.page === 'about') q.set('page', s.page)
  if (s.field) q.set('field', s.field)
  if (s.ra !== null && s.dec !== null) {
    q.set('ra', s.ra.toFixed(5))
    q.set('dec', s.dec.toFixed(5))
  }
  if (s.page === 'view' || s.field) {
    if (s.fov > 0) q.set('fov', String(+s.fov.toFixed(2)))
    if (s.det) q.set('det', String(s.det))
    if (s.mode !== d.mode) q.set('mode', s.mode)
    if (s.frame) q.set('frame', String(s.frame))
    if (s.seq) q.set('seq', s.seq)
    if (s.stretch !== d.stretch) q.set('st', s.stretch)
    if (s.cmap) q.set('cm', s.cmap)
    if (s.pLo !== d.pLo || s.pHi !== d.pHi) q.set('lim', `${s.pLo},${s.pHi}`)
    if (s.smooth !== null) q.set('sm', s.smooth ? '1' : '0')
    if (s.lamMin !== d.lamMin || s.lamMax !== d.lamMax) q.set('lam', `${s.lamMin},${s.lamMax}`)
    if (s.overlays) q.set('ov', s.overlays.join(','))
    if (s.pix) q.set('pix', s.pix.join(','))
    if (s.ap !== d.ap) q.set('ap', String(s.ap))
  }
  if (s.engine) q.set('engine', s.engine)
  if (s.embed) q.set('embed', '1')
  return q.toString()
}
