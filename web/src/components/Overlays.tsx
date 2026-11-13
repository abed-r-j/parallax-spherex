/**
 * Everything drawn on top of a sky picture: catalogue stars moved to the frame date,
 * solar-system objects, detections, candidates, the target's predicted and measured
 * positions, the picked aperture, a compass and a scale bar.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import type { ReactNode } from 'react'
import type { Pack } from '../lib/types'
import type { OverlayName } from '../lib/urlstate'
import { mjdToYear, propagate, skyToPix } from '../lib/wcs'
import { toOverlay, type PixelPos, type View } from './SkyCanvas'

export const PASS_COLOURS = ['var(--pass1)', 'var(--pass2)', 'var(--pass3)', 'var(--pass4)']
export const CLASS_COLOURS: Record<string, string> = {
  mover: '#ffd166',
  variable: '#ff7ad9',
  'motion-dipole': '#5cc8ff',
  chromatic: '#b39ddb',
  'star-residual': '#9aa7b8',
  artifact: '#7c8798',
}

export interface TrackPoint {
  pass: number
  x: number
  y: number
  px: number // catalogue-predicted position at the pass date
  py: number
}

interface Props {
  pack: Pack
  view: View
  mjd: number
  frame: number | null
  on: Set<OverlayName>
  track: TrackPoint[]
  pick: PixelPos | null
  apHalf: number
  request: { ra: number; dec: number } | null
  selCand: string | null
  furniture: boolean
}

const CATWISE_EPOCH = 2015.4

function niceBar(widthArcsec: number): number {
  const opts = [2, 5, 10, 20, 30, 60, 120, 180, 300, 600]
  let best = opts[0]
  for (const o of opts) if (o <= widthArcsec * 0.3) best = o
  return best
}

export function Overlays({ pack, view, mjd, frame, on, track, pick, apHalf, request, selCand, furniture }: Props) {
  const { meta } = pack
  const year = mjdToYear(mjd)
  const u = 1000 / (2 * view.half) // overlay units per pixel
  const P = (x: number, y: number) => toOverlay(view, x, y)
  const inside = (x: number, y: number) => Math.abs(x - view.cx) <= view.half && Math.abs(y - view.cy) <= view.half
  const sky = (ra: number, dec: number) => skyToPix(meta, ra, dec)
  const out: ReactNode[] = []

  if (on.has('wise'))
    for (const [i, w] of (meta.wise ?? []).entries()) {
      const s = propagate(w.ra, w.dec, w.pmRa, w.pmDec, CATWISE_EPOCH, year)
      const p = sky(s.ra, s.dec)
      if (!p || !inside(p.x, p.y)) continue
      const [X, Y] = P(p.x, p.y)
      out.push(
        <rect key={`w${i}`} className="ov-wise pe" x={X - 9} y={Y - 9} width={18} height={18}>
          <title>{`CatWISE ${w.id ?? ''}  W1 ${w.w1 ?? '?'}  W2 ${w.w2 ?? '?'}`}</title>
        </rect>,
      )
    }

  if (on.has('gaia'))
    for (const [i, g] of (meta.gaia ?? []).entries()) {
      const s = propagate(g.ra, g.dec, g.pmRa, g.pmDec, 2016.0, year)
      const p = sky(s.ra, s.dec)
      if (!p || !inside(p.x, p.y)) continue
      const [X, Y] = P(p.x, p.y)
      const r = Math.min(20, Math.max(7, 20 - ((g.g ?? 18) - 8) * 1.3))
      out.push(
        <circle key={`g${i}`} className="ov-gaia pe" cx={X} cy={Y} r={r}>
          <title>{`Gaia DR3 ${g.id ?? ''}  G ${g.g?.toFixed(1) ?? '?'}  pm ${(g.pmRa ?? 0).toFixed(0)}, ${(g.pmDec ?? 0).toFixed(0)} mas/yr`}</title>
        </circle>,
      )
    }

  if (on.has('candidates'))
    for (const c of meta.candidates ?? []) {
      const pts = c.ra.map((ra, k) => sky(ra, c.dec[k])).filter((p): p is PixelPos => !!p)
      if (!pts.length) continue
      const col = CLASS_COLOURS[c.cls] ?? '#ffffff'
      const sel = selCand === c.id
      const [LX, LY] = P(pts[pts.length - 1].x, pts[pts.length - 1].y)
      out.push(
        <g key={`c${c.id}`} className={sel ? 'ov-cand sel' : 'ov-cand'} stroke={col} fill="none">
          {pts.length > 1 && <polyline points={pts.map((p) => P(p.x, p.y).join(',')).join(' ')} />}
          {pts.map((p, k) => {
            const [X, Y] = P(p.x, p.y)
            return <circle key={k} cx={X} cy={Y} r={sel ? 7 : 5} />
          })}
          <text x={LX + 14} y={LY - 12} fill={col} stroke="none">
            {c.id}
          </text>
        </g>,
      )
    }

  if (on.has('detections') && frame !== null)
    for (const [i, d] of (meta.detections ?? []).entries()) {
      if (d.frame !== frame || !inside(d.x, d.y)) continue
      const [X, Y] = P(d.x, d.y)
      out.push(
        <rect key={`d${i}`} className="ov-det pe" x={X - 13} y={Y - 13} width={26} height={26} stroke={CLASS_COLOURS[d.cls] ?? '#fff'} transform={`rotate(45 ${X} ${Y})`}>
          <title>{`${d.cls}  SNR ${d.snr}${d.fluxUJy != null ? `  ${d.fluxUJy} µJy` : ''}${d.known ? `  = ${d.known}` : ''}`}</title>
        </rect>,
      )
    }

  if (on.has('sso') && frame !== null)
    for (const [i, o] of (meta.sso ?? []).entries()) {
      if (o.frame !== frame || !inside(o.x, o.y)) continue
      const [X, Y] = P(o.x, o.y)
      // one hour of motion: east is -x, north is +y
      const dx = (-(o.rateRa ?? 0) / meta.scale) * u
      const dy = (-(o.rateDec ?? 0) / meta.scale) * u
      out.push(
        <g key={`s${i}`} className="ov-sso">
          <circle cx={X} cy={Y} r={17} />
          {(dx || dy) && <line x1={X} y1={Y} x2={X + dx} y2={Y + dy} />}
          <text x={X + 22} y={Y + 5}>
            {o.name}
            {o.vmag != null ? ` V${o.vmag.toFixed(1)}` : ''}
          </text>
        </g>,
      )
    }

  if (on.has('track') && track.length) {
    const seen = track.map((t) => P(t.x, t.y))
    const pred = track.map((t) => P(t.px, t.py))
    out.push(
      <g key="track" className="ov-track">
        <polyline className="pred" points={pred.map((p) => p.join(',')).join(' ')} />
        {pred.map((p, k) => (
          <path key={`p${k}`} className="pred" d={`M${p[0]} ${p[1] - 9}L${p[0] + 9} ${p[1]}L${p[0]} ${p[1] + 9}L${p[0] - 9} ${p[1]}Z`} />
        ))}
        <polyline className="seen" points={seen.map((p) => p.join(',')).join(' ')} />
        {seen.map((p, k) => (
          <circle key={`s${k}`} cx={p[0]} cy={p[1]} r={8} fill={PASS_COLOURS[track[k].pass % 4]} />
        ))}
      </g>,
    )
  }

  const t = meta.target
  if (on.has('target') && t) {
    const s = propagate(t.ra, t.dec, t.pmRa, t.pmDec, t.epoch, year)
    const p = sky(s.ra, s.dec)
    if (p && inside(p.x, p.y)) {
      const [X, Y] = P(p.x, p.y)
      const a = Math.max(26, 2.2 * u)
      const b = a + 30
      out.push(
        <g key="target" className="ov-target">
          <path d={`M${X - b} ${Y}H${X - a}M${X + a} ${Y}H${X + b}M${X} ${Y - b}V${Y - a}M${X} ${Y + a}V${Y + b}`} />
          <text x={X > 560 ? X - a - 6 : X + a + 6} y={Y - a - 6} textAnchor={X > 560 ? 'end' : 'start'}>
            {t.name}, catalogue position {year.toFixed(2)}
          </text>
        </g>,
      )
    }
  }

  if (request) {
    const p = sky(request.ra, request.dec)
    if (p && inside(p.x, p.y)) {
      const [X, Y] = P(p.x, p.y)
      out.push(<path key="req" className="ov-req" d={`M${X - 16} ${Y - 16}L${X + 16} ${Y + 16}M${X - 16} ${Y + 16}L${X + 16} ${Y - 16}`} />)
    }
  }

  if (pick && inside(pick.x, pick.y)) {
    const [X, Y] = P(pick.x - apHalf - 0.5, pick.y + apHalf + 0.5)
    const side = (2 * apHalf + 1) * u
    out.push(<rect key="pick" className="ov-pick" x={X} y={Y} width={side} height={side} />)
  }

  if (furniture) {
    const bar = niceBar(2 * view.half * meta.scale)
    const len = (bar / meta.scale) * u
    out.push(
      <g key="furn" className="ov-furn">
        <line x1={40} y1={960} x2={40 + len} y2={960} />
        <text x={40} y={942}>{bar < 60 ? `${bar} arcsec` : `${bar / 60} arcmin`}</text>
        <path d="M940 110V40M940 40l-9 16M940 40l9 16M940 110H870M870 110l16 -9M870 110l16 9" />
        <text x={934} y={30}>N</text>
        <text x={846} y={116}>E</text>
      </g>,
    )
  }
  return <>{out}</>
}
