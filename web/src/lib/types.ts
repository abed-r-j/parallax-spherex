/**
 * Types of the ParallaX data pack (see docs/DATA_CONTRACT.md) and of the view state.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */

export interface IndexField {
  key: string
  name: string
  kind: string
  ra: number
  dec: number
  n: number
  scale: number
  nFrames: number
  nCampaigns: number
  blurb?: string
  thumb?: string
}

export interface PackIndex {
  generated?: string
  pipeline?: string
  fields: IndexField[]
}

export interface SectionMeta {
  offset: number
  dtype: string
  shape: number[]
}

export interface Frames {
  mjd: number[]
  iso: string[]
  det: number[]
  campaign: number[]
  lam: (number | null)[]
  bw: (number | null)[]
  lamFit: [number | null, number, number][]
  sigma: (number | null)[]
  sky?: (number | null)[]
  zodi?: (number | null)[]
  fwhm?: (number | null)[]
  name?: string[]
  collection?: string[]
  naivePartner?: number[]
  gatedPartner?: number[]
  nRef?: (number | null)[]
}

export interface Target {
  name: string
  ra: number
  dec: number
  epoch: number
  pmRa: number
  pmDec: number
}

export interface GaiaStar {
  id?: string | number
  ra: number
  dec: number
  pmRa?: number | null
  pmDec?: number | null
  plx?: number | null
  g?: number | null
}

export interface WiseSource {
  id?: string | number
  ra: number
  dec: number
  w1?: number | null
  w2?: number | null
  pmRa?: number | null
  pmDec?: number | null
}

export interface SsoObject {
  frame: number
  name: string
  number?: number | string | null
  ra: number
  dec: number
  x: number
  y: number
  vmag?: number | null
  rateRa?: number | null
  rateDec?: number | null
  source?: string
}

export interface Detection {
  frame: number
  x: number
  y: number
  ra: number
  dec: number
  snr: number
  fluxUJy?: number | null
  cls: string
  known?: string | null
}

export interface Candidate {
  id: string
  cls: string
  frames: number[]
  ra: number[]
  dec: number[]
  mjd: number[]
  rate?: number | null
  pa?: number | null
  known?: string | null
  note?: string
  [k: string]: unknown
}

export interface Campaign {
  index: number
  start: string
  end: string
  nFrames: number
}

export interface Meta {
  key: string
  name: string
  kind: string
  blurb?: string
  ra0: number
  dec0: number
  n: number
  scale: number
  target?: Target | null
  release?: { collections?: string[]; doi?: string[]; retrieved?: string }
  encoding: { soft: number; lo: number; hi: number }
  sections: Record<string, SectionMeta>
  frames: Frames
  campaigns?: Campaign[]
  gaia?: GaiaStar[]
  wise?: WiseSource[]
  sso?: SsoObject[]
  detections?: Detection[]
  candidates?: Candidate[]
  science?: Record<string, unknown>
  ledger?: Record<string, unknown>
  /** present only on fields built in the browser from the public archive (lib/live.ts) */
  live?: LiveInfo
}

/** How a live field was built: counts, cost and what it lacks compared with a pipeline pack. */
export interface LiveInfo {
  source: string
  /** false while frames are still arriving */
  complete: boolean
  /** images that cover the position, all detectors */
  available: number
  /** of those, in the chosen detectors */
  matching: number
  /** images requested after the maximum-count cut (evenly spaced in time) */
  requested: number
  /** matching - requested */
  dropped: number
  loaded: number
  /** the field falls mostly off the detector */
  skipped: number
  /** network errors after all retries */
  failed: number
  bytes: number
  requests: number
  seconds: number
  detectors: number[]
  sizeArcmin: number
  /** build time of the sky index that listed the images */
  indexBuilt: string
}

export type TypedArray = Uint16Array | Uint8Array | Int8Array | Float32Array

/** A loaded field: metadata plus typed-array views over cube.bin. */
export interface Pack {
  meta: Meta
  /** where the pack came from (static site or live engine) */
  base: string
  nFrames: number
  n: number
  img: Uint16Array
  flags: Uint8Array | null
  tpl: Uint16Array | null
  snrCorr: Int8Array | null
  snrNaive: Int8Array | null
  snrGated: Int8Array | null
  stack: Float32Array | null
  nCampaigns: number
  naivePartner: Int32Array
  gatedPartner: Int32Array
  /** true when the partner lists were derived in the browser, not by the pipeline */
  partnersDerived: boolean
}

export type Mode = 'image' | 'chroma' | 'naive' | 'gated' | 'compare' | 'add' | 'sub'
export type Seq = 'frames' | 'passes'
export type StretchKind = 'asinh' | 'linear' | 'log'
export type CmapName = 'grey' | 'perceptual' | 'diverging'

/** A pick for Add / Subtract: one frame, or all frames of a pass and/or detector. */
export interface Selection {
  kind: 'frame' | 'group'
  frame: number
  pass: number // -1 = any
  det: number // 0 = any
}

export const UJY_PER_MJYSR_615 = 889.86

/** microJy per pixel for 1 MJy/sr at the given pixel scale (arcsec). */
export function ujyPerMjySr(scale: number): number {
  return UJY_PER_MJYSR_615 * (scale / 6.15) ** 2
}

export const DETECTOR_RANGE: [number, number][] = [
  [0.74, 1.11],
  [1.1, 1.66],
  [1.62, 2.41],
  [2.42, 3.8],
  [3.82, 4.43],
  [4.41, 5.0],
]
