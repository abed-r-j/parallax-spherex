/**
 * Hand-written SVG charts: the time x wavelength map of all frames, the spectrum of a
 * pixel, its light curve, and completeness curves. Time axes are broken between survey
 * passes, which are about six months apart.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { useRef, useState, type PointerEvent } from 'react'
import type { SpecPoint } from '../lib/photometry'
import { percentiles } from '../lib/stretch'
import { DETECTOR_RANGE, type Pack } from '../lib/types'
import { PASS_COLOURS } from './Overlays'

export const DET_COLOURS = ['var(--d1)', 'var(--d2)', 'var(--d3)', 'var(--d4)', 'var(--d5)', 'var(--d6)']

const lin = (d0: number, d1: number, r0: number, r1: number) => (v: number) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0)

interface Segment {
  pass: number
  x0: number
  x1: number
  t0: number
  t1: number
  label: string
}

/** A time axis with the gaps between survey passes removed. */
export function brokenTime(pack: Pack, left: number, right: number): { segs: Segment[]; x: (mjd: number, pass: number) => number } {
  const f = pack.meta.frames
  const lo = new Map<number, number>()
  const hi = new Map<number, number>()
  const first = new Map<number, string>()
  f.mjd.forEach((t, i) => {
    const c = f.campaign[i]
    if (!lo.has(c) || t < lo.get(c)!) {
      lo.set(c, t)
      first.set(c, f.iso[i].slice(0, 10))
    }
    if (!hi.has(c) || t > hi.get(c)!) hi.set(c, t)
  })
  const passes = [...lo.keys()].sort((a, b) => a - b)
  const spans = passes.map((c) => hi.get(c)! - lo.get(c)!)
  const total = spans.reduce((a, b) => a + b, 0) || 1
  const weights = spans.map((s) => s + 0.25 * total)
  const wsum = weights.reduce((a, b) => a + b, 0)
  const gap = 14
  const usable = right - left - gap * (passes.length - 1)
  const segs: Segment[] = []
  let x = left
  passes.forEach((c, k) => {
    const w = (weights[k] / wsum) * usable
    const pad = Math.max(0.5, spans[k] * 0.04)
    segs.push({ pass: c, x0: x, x1: x + w, t0: lo.get(c)! - pad, t1: hi.get(c)! + pad, label: first.get(c) ?? '' })
    x += w + gap
  })
  const by = new Map(segs.map((s) => [s.pass, s]))
  return {
    segs,
    x: (mjd, pass) => {
      const s = by.get(pass)
      return s ? lin(s.t0, s.t1, s.x0, s.x1)(mjd) : left
    },
  }
}

function svgPoint(e: PointerEvent<SVGSVGElement>, w: number, h: number): [number, number] {
  const r = e.currentTarget.getBoundingClientRect()
  return [((e.clientX - r.left) / r.width) * w, ((e.clientY - r.top) / r.height) * h]
}

function TimeAxis({ segs, y0, y1 }: { segs: Segment[]; y0: number; y1: number }) {
  return (
    <g className="axis">
      {segs.map((s) => (
        <g key={s.pass}>
          <rect className="plot-bg" x={s.x0} y={y0} width={s.x1 - s.x0} height={y1 - y0} />
          <text x={(s.x0 + s.x1) / 2} y={y1 + 14} textAnchor="middle">
            pass {s.pass + 1}, from {s.label}
          </text>
        </g>
      ))}
    </g>
  )
}

interface MapProps {
  pack: Pack
  current: number | null
  active: Set<number>
  highlight: { pass: number; det: number } | null
  lamRange: [number, number]
  onJump: (frame: number) => void
}

/** Every frame as a dot: when it was taken against the colour it was taken in. */
export function TimeLambdaMap({ pack, current, active, highlight, lamRange, onJump }: MapProps) {
  const W = 640
  const H = 250
  const f = pack.meta.frames
  const { segs, x } = brokenTime(pack, 44, W - 34)
  const y = lin(0.7, 5.1, H - 26, 8)
  const pts = f.mjd.map((t, i) => (f.lam[i] == null ? null : ([x(t, f.campaign[i]), y(f.lam[i]!)] as [number, number])))
  const jump = (e: PointerEvent<SVGSVGElement>) => {
    const [px, py] = svgPoint(e, W, H)
    let best = -1
    let bd = 30 * 30
    pts.forEach((p, i) => {
      if (!p) return
      const d = (p[0] - px) ** 2 + (p[1] - py) ** 2
      if (d < bd) {
        bd = d
        best = i
      }
    })
    if (best >= 0) onJump(best)
  }
  const cur = current !== null ? pts[current] : null
  return (
    <svg className="chart map" viewBox={`0 0 ${W} ${H}`} onPointerDown={jump} role="img"
      aria-label={`Time against wavelength for all ${pack.nFrames} frames. Each visit lands on a different wavelength. Use the frame slider to move between frames.`}>
      <TimeAxis segs={segs} y0={8} y1={H - 26} />
      {DETECTOR_RANGE.map(([a, b], d) => (
        <g key={d}>
          <rect x={W - 30} y={y(b)} width={5} height={y(a) - y(b)} fill={DET_COLOURS[d]} />
          <text className="tick" x={W - 21} y={(y(a) + y(b)) / 2 + 4}>D{d + 1}</text>
        </g>
      ))}
      {(lamRange[0] > 0.7 || lamRange[1] < 5.1) &&
        segs.map((s) => (
          <rect key={s.pass} className="band" x={s.x0} y={y(Math.min(5.1, lamRange[1]))} width={s.x1 - s.x0}
            height={Math.max(0, y(Math.max(0.7, lamRange[0])) - y(Math.min(5.1, lamRange[1])))} />
        ))}
      {[1, 2, 3, 4, 5].map((l) => (
        <g key={l} className="axis">
          <line className="grid" x1={44} x2={W - 34} y1={y(l)} y2={y(l)} />
          <text className="tick" x={38} y={y(l) + 4} textAnchor="end">{l}</text>
        </g>
      ))}
      <text className="tick" x={4} y={14}>µm</text>
      {pts.map((p, i) => {
        if (!p) return null
        const hl = highlight && f.campaign[i] === highlight.pass && f.det[i] === highlight.det
        return <circle key={i} cx={p[0]} cy={p[1]} r={hl ? 3 : 2.1} fill={DET_COLOURS[f.det[i] - 1]} opacity={active.has(i) ? (highlight && !hl ? 0.45 : 1) : 0.16} />
      })}
      {cur && (
        <g className="cursor">
          <line x1={cur[0]} x2={cur[0]} y1={8} y2={H - 26} />
          <line x1={44} x2={W - 34} y1={cur[1]} y2={cur[1]} />
          <circle cx={cur[0]} cy={cur[1]} r={6.5} />
        </g>
      )}
    </svg>
  )
}

function yRange(points: SpecPoint[]): [number, number] {
  const [a, b] = percentiles(points.map((p) => p.flux), [1, 99])
  const errs = percentiles(points.map((p) => p.err), [50])[0] || 0
  const lo = Math.min(0, a - errs)
  const hi = Math.max(b + errs, lo + 1)
  const pad = (hi - lo) * 0.08
  return [lo - pad, hi + pad]
}

function niceTicks(lo: number, hi: number, count = 4): number[] {
  const raw = (hi - lo) / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toPrecision(10))
  return out
}

/** Tick label for a flux in microJy, switching to mJy and Jy for bright sources. */
function fmtFlux(v: number): string {
  const a = Math.abs(v)
  if (a >= 1e6) return `${+(v / 1e6).toPrecision(3)} Jy`
  if (a >= 1e4) return `${+(v / 1e3).toPrecision(3)} mJy`
  return String(+v.toPrecision(3))
}

function Dots({ points, X, Y, current, clampTo }: { points: SpecPoint[]; X: (p: SpecPoint) => number; Y: (v: number) => number; current: number | null; clampTo: [number, number] }) {
  const cl = (v: number) => Math.min(clampTo[0], Math.max(clampTo[1], v))
  return (
    <>
      {points.map((p) => {
        const x = X(p)
        const col = PASS_COLOURS[p.pass % 4]
        return (
          <g key={p.frame} opacity={p.flagged ? 0.35 : 0.9}>
            {Number.isFinite(p.err) && <line x1={x} x2={x} y1={cl(Y(p.flux - p.err))} y2={cl(Y(p.flux + p.err))} stroke={col} strokeWidth={0.8} />}
            <circle cx={x} cy={cl(Y(p.flux))} r={p.frame === current ? 4.5 : 2.2} fill={col} className={p.frame === current ? 'cur-dot' : undefined} />
          </g>
        )
      })}
    </>
  )
}

interface SpecProps {
  points: SpecPoint[]
  window: [number, number] | null
  current: number | null
  onWindow: (w: [number, number]) => void
  onJump: (frame: number) => void
}

/** Flux of the picked aperture against wavelength; drag to choose a wavelength window. */
export function SpectrumChart({ points, window: win, current, onWindow, onJump }: SpecProps) {
  const W = 640
  const H = 270
  const L = 62
  const R = W - 10
  const T = 10
  const B = H - 34
  const drag = useRef<number | null>(null)
  const [live, setLive] = useState<[number, number] | null>(null)
  const lams = points.map((p) => p.lam)
  const l0 = Math.min(...lams)
  const l1 = Math.max(...lams)
  const padL = (l1 - l0) * 0.03 || 0.05
  const x = lin(l0 - padL, l1 + padL, L, R)
  const inv = lin(L, R, l0 - padL, l1 + padL)
  const [y0, y1] = yRange(points)
  const y = lin(y0, y1, B, T)
  const shown = live ?? win
  const down = (e: PointerEvent<SVGSVGElement>) => {
    drag.current = svgPoint(e, W, H)[0]
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const move = (e: PointerEvent<SVGSVGElement>) => {
    if (drag.current === null) return
    const px = svgPoint(e, W, H)[0]
    if (Math.abs(px - drag.current) > 4) setLive([inv(Math.min(px, drag.current)), inv(Math.max(px, drag.current))])
  }
  const up = (e: PointerEvent<SVGSVGElement>) => {
    if (drag.current === null) return
    const [px, py] = svgPoint(e, W, H)
    if (live) onWindow([+live[0].toFixed(4), +live[1].toFixed(4)])
    else {
      let best: SpecPoint | null = null
      let bd = 20 * 20
      for (const p of points) {
        const d = (x(p.lam) - px) ** 2 + (y(p.flux) - py) ** 2
        if (d < bd) {
          bd = d
          best = p
        }
      }
      if (best) onJump(best.frame)
    }
    drag.current = null
    setLive(null)
  }
  return (
    <svg className="chart spec" viewBox={`0 0 ${W} ${H}`} onPointerDown={down} onPointerMove={move} onPointerUp={up} role="img"
      aria-label={`Spectrum of the picked pixel: ${points.length} measurements between ${l0.toFixed(2)} and ${l1.toFixed(2)} micron.`}>
      <rect className="plot-bg" x={L} y={T} width={R - L} height={B - T} />
      {shown && <rect className="band" x={x(shown[0])} y={T} width={Math.max(1, x(shown[1]) - x(shown[0]))} height={B - T} />}
      {niceTicks(y0, y1).map((v) => (
        <g key={v} className="axis">
          <line className="grid" x1={L} x2={R} y1={y(v)} y2={y(v)} />
          <text className="tick" x={L - 6} y={y(v) + 4} textAnchor="end">{fmtFlux(v)}</text>
        </g>
      ))}
      {niceTicks(l0, l1, 6).map((v) => (
        <text key={v} className="tick" x={x(v)} y={B + 14} textAnchor="middle">{v}</text>
      ))}
      <text className="tick" x={(L + R) / 2} y={H - 4} textAnchor="middle">wavelength at this pixel (µm)</text>
      <text className="tick" x={4} y={T + 8}>µJy</text>
      <Dots points={points} X={(p) => x(p.lam)} Y={y} current={current} clampTo={[B, T]} />
    </svg>
  )
}

interface CurveProps {
  pack: Pack
  points: SpecPoint[]
  current: number | null
  onJump: (frame: number) => void
}

/** Flux against date for the measurements inside the wavelength window. */
export function LightCurve({ pack, points, current, onJump }: CurveProps) {
  const W = 640
  const H = 210
  const T = 10
  const B = H - 26
  const { segs, x } = brokenTime(pack, 62, W - 10)
  const [y0, y1] = yRange(points)
  const y = lin(y0, y1, B, T)
  const means = segs.map((s) => {
    const v = points.filter((p) => p.pass === s.pass && !p.flagged).map((p) => p.flux)
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
  })
  const jump = (e: PointerEvent<SVGSVGElement>) => {
    const [px, py] = svgPoint(e, W, H)
    let best: SpecPoint | null = null
    let bd = 20 * 20
    for (const p of points) {
      const d = (x(p.mjd, p.pass) - px) ** 2 + (y(p.flux) - py) ** 2
      if (d < bd) {
        bd = d
        best = p
      }
    }
    if (best) onJump(best.frame)
  }
  return (
    <svg className="chart curve" viewBox={`0 0 ${W} ${H}`} onPointerDown={jump} role="img"
      aria-label={`Light curve: ${points.length} measurements inside the wavelength window, by date.`}>
      <TimeAxis segs={segs} y0={T} y1={B} />
      {niceTicks(y0, y1).map((v) => (
        <g key={v} className="axis">
          <line className="grid" x1={62} x2={W - 10} y1={y(v)} y2={y(v)} />
          <text className="tick" x={56} y={y(v) + 4} textAnchor="end">{fmtFlux(v)}</text>
        </g>
      ))}
      <text className="tick" x={4} y={T + 8}>µJy</text>
      {segs.map((s, k) => means[k] !== null && <line key={s.pass} className="mean" x1={s.x0} x2={s.x1} y1={y(means[k]!)} y2={y(means[k]!)} stroke={PASS_COLOURS[s.pass % 4]} />)}
      <Dots points={points} X={(p) => x(p.mjd, p.pass)} Y={y} current={current} clampTo={[B, T]} />
    </svg>
  )
}

export interface Series {
  label: string
  colour: string
  values: (number | null)[]
}

/** Completeness (0..1) against injected flux on a logarithmic axis. */
export function CompletenessChart({ flux, series }: { flux: number[]; series: Series[] }) {
  const W = 640
  const H = 230
  const L = 44
  const R = W - 12
  const T = 10
  const B = H - 34
  const x = (v: number) => lin(Math.log10(flux[0]), Math.log10(flux[flux.length - 1]), L, R)(Math.log10(v))
  const y = lin(0, 1, B, T)
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Fraction of injected test sources recovered against their flux, for each difference method.">
      <rect className="plot-bg" x={L} y={T} width={R - L} height={B - T} />
      {[0, 0.25, 0.5, 0.75, 1].map((v) => (
        <g key={v} className="axis">
          <line className="grid" x1={L} x2={R} y1={y(v)} y2={y(v)} />
          <text className="tick" x={L - 6} y={y(v) + 4} textAnchor="end">{v * 100}%</text>
        </g>
      ))}
      {flux.map((v, i) => (i % 2 === 0 || flux.length < 8 ? <text key={v} className="tick" x={x(v)} y={B + 14} textAnchor="middle">{v}</text> : null))}
      <text className="tick" x={(L + R) / 2} y={H - 4} textAnchor="middle">injected flux (µJy)</text>
      {series.map((s) => {
        const pts = s.values.map((v, i) => (v == null ? null : `${x(flux[i])},${y(v)}`)).filter(Boolean)
        return (
          <g key={s.label}>
            <polyline points={pts.join(' ')} fill="none" stroke={s.colour} strokeWidth={2} />
            {s.values.map((v, i) => (v == null ? null : <circle key={i} cx={x(flux[i])} cy={y(v)} r={2.6} fill={s.colour} />))}
          </g>
        )
      })}
    </svg>
  )
}
