/**
 * The field viewer: view modes, the blink player, the time x wavelength map, display and
 * overlay controls, cursor read-out, spectra on the fly and the pipeline's panels.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { stackImage } from '../lib/decode'
import { centroid, lamAt, spectrumAt, spectrumCsv } from '../lib/photometry'
import {
  FLAG_STYLE, chromaProduct, filterFrames, flagsRgba, frameImage, gatedProduct, meanImage, mismatchMap,
  naiveProduct, passEntries, selectionFrames, subtractImages, type Product,
} from '../lib/products'
import { cmapLut, percentiles, renderRgba, upsampleBicubic } from '../lib/stretch'
import { DETECTOR_RANGE, ujyPerMjySr, type Candidate, type CmapName, type Mode, type Pack, type Selection, type Seq } from '../lib/types'
import { OVERLAYS, type OverlayName, type ViewState } from '../lib/urlstate'
import { formatDec, formatRa, mjdToYear, pixToSky, propagate, skyToPix } from '../lib/wcs'
import { DET_COLOURS, LightCurve, SpectrumChart, TimeLambdaMap } from './Charts'
import { Overlays, PASS_COLOURS, type TrackPoint } from './Overlays'
import { CandidatesPanel, LedgerPanel, SciencePanel, fmt } from './Panels'
import { Player, SPEEDS } from './Player'
import { SkyCanvas, type PixelPos, type Raster, type View } from './SkyCanvas'

const MODES: { id: Mode; label: string; key: string; about: string }[] = [
  { id: 'image', label: 'Image', key: 'I', about: 'The sky as SPHEREx saw it. Every frame is taken at a different infrared colour.' },
  { id: 'chroma', label: 'Chromatic difference', key: 'C', about: 'The frame minus what an unchanging sky would look like at exactly this frame’s colours, predicted from the other survey passes. What is left has really changed.' },
  { id: 'naive', label: 'Naive pair', key: 'N', about: 'The frame minus the nearest frame from another survey pass in the same detector, ignoring that the two were taken at different colours.' },
  { id: 'gated', label: 'Gated pair', key: 'G', about: 'The frame minus a frame from another pass, used only if their colours agree within half a bandwidth.' },
  { id: 'compare', label: 'Three-way', key: 'T', about: 'The same frame differenced three ways, on one scale. Colour mismatch shows up as false signal on every star in the naive panel.' },
  { id: 'add', label: 'Add', key: 'A', about: 'Stack any set of frames to go deeper. Stacking mixes colours unless you keep to one detector.' },
  { id: 'sub', label: 'Subtract', key: 'S', about: 'One selection minus another. A star that moved shows a bright and a dark lobe side by side.' },
]

const OVERLAY_LABEL: Record<OverlayName, string> = {
  target: 'Catalogue position of the target',
  track: 'Measured position in each survey pass',
  gaia: 'Gaia DR3 stars, moved to the frame date',
  wise: 'CatWISE sources',
  sso: 'Known solar-system objects in this frame',
  flags: 'Pixel flags',
  mismatch: 'Wavelength mismatch with the partner frame',
  detections: 'Detections in this frame',
  candidates: 'Linked candidates',
}

const TABS = ['Spectrum', 'Display', 'Overlays', 'Frame', 'Candidates', 'Science', 'Ledger'] as const
type Tab = (typeof TABS)[number]

function rasterise(data: Float32Array, n: number, lo: number, hi: number, symmetric: boolean, s: ViewState, cmap: CmapName, smooth: boolean): Raster {
  const m = smooth ? n * 4 : n
  const src = smooth ? upsampleBicubic(data, n, 4) : data
  return { rgba: renderRgba(src, m, m, { kind: symmetric ? 'linear' : s.stretch, lo, hi, symmetric, cmap }), m }
}

function symLimit(data: Float32Array, pHi: number, floor: number): number {
  const abs = Float32Array.from(data, (v) => Math.abs(v))
  const p = percentiles(abs, [pHi])[0]
  return Math.max(floor, Number.isFinite(p) ? p : floor)
}

function gradient(cmap: CmapName): string {
  const lut = cmapLut(cmap)
  const stops: string[] = []
  for (let i = 0; i <= 8; i++) {
    const k = Math.round((i / 8) * 255) * 3
    stops.push(`rgb(${lut[k]},${lut[k + 1]},${lut[k + 2]}) ${(i / 8) * 100}%`)
  }
  return `linear-gradient(90deg, ${stops.join(',')})`
}

function ColourBar({ lo, hi, cmap, unit }: { lo: number; hi: number; cmap: CmapName; unit: string }) {
  return (
    <div className="cbar" aria-label={`Colour scale from ${fmt(lo)} to ${fmt(hi)} ${unit}`}>
      <span className="num">{fmt(lo)}</span>
      <i style={{ background: gradient(cmap) }} />
      <span className="num">{fmt(hi)} {unit}</span>
    </div>
  )
}

function SelPicker({ label, sel, set, pack }: { label: string; sel: Selection; set: (s: Selection) => void; pack: Pack }) {
  return (
    <fieldset className="sel">
      <legend>{label}</legend>
      <select aria-label={`${label}: what to use`} value={sel.kind} onChange={(e) => set({ ...sel, kind: e.target.value as Selection['kind'] })}>
        <option value="group">A group of frames</option>
        <option value="frame">The frame at the slider</option>
      </select>
      {sel.kind === 'group' && (
        <>
          <select aria-label={`${label}: survey pass`} value={sel.pass} onChange={(e) => set({ ...sel, pass: Number(e.target.value) })}>
            <option value={-1}>All passes</option>
            {Array.from({ length: pack.nCampaigns }, (_, c) => <option key={c} value={c}>Pass {c + 1}</option>)}
          </select>
          <select aria-label={`${label}: detector`} value={sel.det} onChange={(e) => set({ ...sel, det: Number(e.target.value) })}>
            <option value={0}>All detectors</option>
            {DETECTOR_RANGE.map(([a, b], d) => <option key={d} value={d + 1}>D{d + 1} ({a}&ndash;{b} µm)</option>)}
          </select>
        </>
      )}
    </fieldset>
  )
}

interface Props {
  pack: Pack
  s: ViewState
  update: (patch: Partial<ViewState>) => void
  notice: string | null
}

export function Viewer({ pack, s, update, notice }: Props) {
  const { meta, n } = pack
  const f = meta.frames
  const kUJy = ujyPerMjySr(meta.scale)
  const motion = meta.kind === 'motion'

  const bestDet = useMemo(() => {
    const c = new Array(7).fill(0)
    f.det.forEach((d) => c[d]++)
    return c.indexOf(Math.max(...c.slice(1)), 1)
  }, [f])
  const passMjd = useMemo(() => {
    const sum = new Array(pack.nCampaigns).fill(0)
    const cnt = new Array(pack.nCampaigns).fill(0)
    f.mjd.forEach((t, i) => {
      sum[f.campaign[i]] += t
      cnt[f.campaign[i]]++
    })
    return sum.map((v, i) => (cnt[i] ? v / cnt[i] : f.mjd[0]))
  }, [f, pack.nCampaigns])

  // ---- sequence ----------------------------------------------------------------------
  const allPasses = useMemo(() => passEntries(pack, 0), [pack])
  const passes = useMemo(() => passEntries(pack, s.det), [pack, s.det])
  const frames = useMemo(() => filterFrames(pack, s.det, s.lamMin, s.lamMax), [pack, s.det, s.lamMin, s.lamMax])
  const diffMode = s.mode === 'chroma' || s.mode === 'naive' || s.mode === 'gated' || s.mode === 'compare'
  const seqDefault: Seq = motion && allPasses.length >= 2 ? 'passes' : 'frames'
  const seq: Seq = diffMode || !passes.length ? 'frames' : (s.seq ?? seqDefault)
  const length = seq === 'passes' ? passes.length : frames.length
  const pos = useMemo(() => {
    if (seq === 'passes') return Math.min(Math.max(0, s.frame), Math.max(0, passes.length - 1))
    const k = frames.findIndex((i) => i >= s.frame)
    return k < 0 ? Math.max(0, frames.length - 1) : k
  }, [seq, s.frame, passes.length, frames])
  const fi: number | null = seq === 'frames' && frames.length ? frames[pos] : null
  const pe = seq === 'passes' ? passes[pos] : null
  const mjd = fi !== null ? f.mjd[fi] : pe ? passMjd[pe.pass] : f.mjd[0]
  const det = fi !== null ? f.det[fi] : pe ? pe.det : s.det || bestDet
  const setPos = useCallback((p: number) => update({ frame: seq === 'passes' ? p : (frames[p] ?? 0) }), [update, seq, frames])

  const [playing, setPlaying] = useState(false)
  const [fps, setFps] = useState(seqDefault === 'passes' ? 2 : 8)
  const [loop, setLoop] = useState(true)
  const [tab, setTab] = useState<Tab>('Spectrum')
  const [hover, setHover] = useState<PixelPos | null>(null)
  const [lock, setLock] = useState<[number, number] | null>(null)
  const [selCand, setSelCand] = useState<string | null>(null)
  const [lamWin, setLamWin] = useState<[number, number] | null>(null)
  const [selA, setSelA] = useState<Selection>({ kind: 'group', frame: -1, pass: Math.max(0, pack.nCampaigns - 1), det: bestDet })
  const [selB, setSelB] = useState<Selection>({ kind: 'group', frame: -1, pass: 0, det: bestDet })
  const [help, setHelp] = useState(false)

  const setMode = (m: Mode) => {
    const toDiff = m === 'chroma' || m === 'naive' || m === 'gated' || m === 'compare'
    const patch: Partial<ViewState> = { mode: m, cmap: null }
    if (toDiff && seq === 'passes' && pe) {
      const first = f.det.findIndex((d, i) => d === pe.det && f.campaign[i] === pe.pass)
      patch.frame = Math.max(0, first)
    }
    setLock(null)
    update(patch)
  }
  const setSeq = (q: Seq) => {
    if (q === seq) return
    let frame = 0
    if (q === 'passes' && fi !== null) frame = Math.max(0, passes.findIndex((p) => p.det === f.det[fi] && p.pass === f.campaign[fi]))
    if (q === 'frames' && pe) frame = Math.max(0, f.det.findIndex((d, i) => d === pe.det && f.campaign[i] === pe.pass))
    setFps(q === 'passes' ? 2 : 8)
    setLock(null)
    update({ seq: q, frame })
  }

  // ---- geometry ----------------------------------------------------------------------
  const view: View = useMemo(() => {
    const full = n / 2
    const half = s.fov > 0 ? Math.min(full, (s.fov * 60) / meta.scale / 2) : full
    let cx = (n - 1) / 2
    let cy = cx
    if (half < full && s.ra !== null && s.dec !== null) {
      const p = skyToPix(meta, s.ra, s.dec)
      if (p) {
        cx = Math.min(n - 0.5 - half, Math.max(half - 0.5, p.x))
        cy = Math.min(n - 0.5 - half, Math.max(half - 0.5, p.y))
      }
    }
    return { cx, cy, half }
  }, [n, meta, s.fov, s.ra, s.dec])
  const fullArcmin = (n * meta.scale) / 60
  const targetPix = useMemo(() => {
    const t = meta.target
    if (!t) return null
    const p = propagate(t.ra, t.dec, t.pmRa, t.pmDec, t.epoch, mjdToYear(mjd))
    return skyToPix(meta, p.ra, p.dec)
  }, [meta, mjd])

  // ---- overlays ----------------------------------------------------------------------
  const available: Record<OverlayName, boolean> = {
    target: !!meta.target,
    track: motion && !!meta.target && allPasses.length >= 2,
    gaia: !!meta.gaia?.length,
    wise: !!meta.wise?.length,
    sso: !!meta.sso?.length,
    flags: !!pack.flags,
    mismatch: true,
    detections: !!meta.detections?.length,
    candidates: !!meta.candidates?.length,
  }
  const on = useMemo(() => new Set<OverlayName>(s.overlays ?? ['target', 'track', 'gaia', 'sso', 'detections']), [s.overlays])
  const toggle = (o: OverlayName) => {
    const next = new Set(on)
    if (next.has(o)) next.delete(o)
    else next.add(o)
    update({ overlays: OVERLAYS.filter((x) => next.has(x)) })
  }

  const tracks = useMemo(() => {
    const t = meta.target
    const out: TrackPoint[][] = [[], [], [], [], [], [], []]
    if (!t || !motion) return out
    for (const e of allPasses) {
      const img = stackImage(pack, e.pass, e.det)
      const p = propagate(t.ra, t.dec, t.pmRa, t.pmDec, t.epoch, mjdToYear(passMjd[e.pass]))
      const pp = skyToPix(meta, p.ra, p.dec)
      if (!img || !pp) continue
      const c = centroid(img, n, pp.x, pp.y, 3)
      // keep only clear detections close to the prediction, so noise is never drawn as a position
      if (c && c.peakSnr > 8 && Math.hypot(c.x - pp.x, c.y - pp.y) < 2) out[e.det].push({ pass: e.pass, x: c.x, y: c.y, px: pp.x, py: pp.y })
    }
    return out
  }, [meta, motion, allPasses, pack, passMjd, n])

  // ---- the picture -------------------------------------------------------------------
  const smooth = s.smooth ?? (motion && !diffMode) // differences default to exact pixels: smoothing makes noise look like sources
  const product: Product & { title: string } = useMemo(() => {
    if (s.mode === 'add') {
      const list = selectionFrames(pack, selA, fi ?? 0)
      const data = meanImage(pack, list)
      return { data, unit: 'MJy/sr', title: `Mean of ${list.length} frame${list.length === 1 ? '' : 's'}`, missing: data ? undefined : 'No frames match this selection.' }
    }
    if (s.mode === 'sub') {
      const la = selectionFrames(pack, selA, fi ?? 0)
      const lb = selectionFrames(pack, selB, fi ?? 0)
      const a = meanImage(pack, la)
      const b = meanImage(pack, lb)
      return {
        data: a && b ? subtractImages(a, b) : null, unit: 'MJy/sr', title: `A (${la.length} frame${la.length === 1 ? '' : 's'}) minus B (${lb.length})`,
        missing: a && b ? undefined : 'One of the two selections has no frames.',
      }
    }
    if (pe) return { data: stackImage(pack, pe.pass, pe.det), unit: 'MJy/sr', title: 'Stack of one survey pass' }
    if (fi === null) return { data: null, unit: 'MJy/sr', title: '', missing: 'No frames match the detector and wavelength filters.' }
    if (s.mode === 'chroma') return { ...chromaProduct(pack, fi), title: 'Frame minus chromatic template' }
    if (s.mode === 'naive') return { ...naiveProduct(pack, fi), title: 'Frame minus naive partner' }
    if (s.mode === 'gated') return { ...gatedProduct(pack, fi), title: 'Frame minus gated partner' }
    return { data: frameImage(pack, fi), unit: 'MJy/sr', title: 'Calibrated image' }
  }, [s.mode, pack, selA, selB, fi, pe])
  const trio = useMemo(
    () => (s.mode === 'compare' && fi !== null ? [naiveProduct(pack, fi), gatedProduct(pack, fi), chromaProduct(pack, fi)] : null),
    [s.mode, fi, pack],
  )

  const symmetric = product.unit === 'SNR' || s.mode === 'sub' || s.mode === 'compare'
  const cmap: CmapName = s.cmap ?? (symmetric ? 'diverging' : 'grey')
  const limits: [number, number] = useMemo(() => {
    if (lock) return lock
    if (trio) {
      const ref = trio[2].data ?? trio[1].data ?? trio[0].data
      const L = ref ? symLimit(ref, s.pHi, 5) : 5
      return [-L, L]
    }
    if (!product.data) return [0, 1]
    if (symmetric) {
      const L = symLimit(product.data, s.pHi, product.unit === 'SNR' ? 5 : 1e-6)
      return [-L, L]
    }
    const [a, b] = percentiles(product.data, [s.pLo, s.pHi])
    return [a, b > a ? b : a + 1e-6]
  }, [lock, trio, product, symmetric, s.pLo, s.pHi])

  const base = useMemo(
    () => (product.data && !trio ? rasterise(product.data, n, limits[0], limits[1], symmetric, s, cmap, smooth) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [product.data, trio, n, limits, symmetric, s.stretch, cmap, smooth],
  )
  const trioRasters = useMemo(
    () => trio?.map((p) => (p.data ? rasterise(p.data, n, limits[0], limits[1], true, s, cmap, smooth) : null)) ?? null,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [trio, n, limits, s.stretch, cmap, smooth],
  )

  const partner = fi === null ? -1 : s.mode === 'gated' ? pack.gatedPartner[fi] : pack.naivePartner[fi]
  const mismatch = useMemo(() => (fi !== null && partner >= 0 ? mismatchMap(pack, fi, partner) : null), [pack, fi, partner])
  const over: Raster | null = useMemo(() => {
    const showMis = on.has('mismatch') && mismatch
    const showFlags = on.has('flags') && pack.flags && fi !== null
    if (!showMis && !showFlags) return null
    let rgba: Uint8ClampedArray<ArrayBuffer>
    if (showMis) {
      rgba = renderRgba(mismatch, n, n, { kind: 'linear', lo: -1, hi: 1, symmetric: true, cmap: 'diverging' })
      for (let k = 3; k < rgba.length; k += 4) rgba[k] = 150
    } else rgba = new Uint8ClampedArray(new ArrayBuffer(n * n * 4))
    if (showFlags) {
      const fl = flagsRgba(pack.flags!, fi!, n)
      for (let k = 0; k < fl.length; k += 4) if (fl[k + 3]) rgba.set(fl.subarray(k, k + 4), k)
    }
    return { rgba, m: n }
  }, [on, mismatch, pack.flags, fi, n])

  // ---- spectrum ----------------------------------------------------------------------
  const pick: PixelPos | null = useMemo(() => {
    if (s.pix && s.pix[0] < n && s.pix[1] < n) return { x: s.pix[0], y: s.pix[1] }
    if (!targetPix) return null
    const x = Math.round(targetPix.x)
    const y = Math.round(targetPix.y)
    return x >= 0 && y >= 0 && x < n && y < n ? { x, y } : null
  }, [s.pix, targetPix, n])
  const spec = useMemo(() => (pick ? spectrumAt(pack, pick.x, pick.y, s.ap) : null), [pack, pick, s.ap])
  const win: [number, number] | null = useMemo(() => {
    if (lamWin) return lamWin
    if (!pick) return null
    const i = fi ?? f.det.findIndex((d) => d === det)
    let l = lamAt(f.lamFit[i], pick.x, pick.y, n)
    const bw = f.bw[i] ?? 0.05
    if (!Number.isFinite(l)) return null
    // if nothing was measured near that wavelength, start at the nearest measurement
    const pts = spec?.points ?? []
    if (pts.length && !pts.some((p) => Math.abs(p.lam - l) <= 1.5 * bw)) l = pts.reduce((a, b) => (Math.abs(b.lam - l) < Math.abs(a.lam - l) ? b : a)).lam
    return [+(l - 1.5 * bw).toFixed(4), +(l + 1.5 * bw).toFixed(4)]
  }, [lamWin, pick, fi, f, det, n, spec])
  const inWin = useMemo(() => (spec && win ? spec.points.filter((p) => p.lam >= win[0] && p.lam <= win[1]) : []), [spec, win])
  const pickSky = pick ? pixToSky(meta, pick.x, pick.y) : null
  const download = () => {
    if (!spec || !pick || !pickSky) return
    const side = 2 * s.ap + 1
    const head = [
      `ParallaX spectrum, field ${meta.key} (${meta.name})`,
      `pixel x=${pick.x} y=${pick.y}, RA=${pickSky.ra.toFixed(6)} Dec=${pickSky.dec.toFixed(6)} deg (ICRS)`,
      `aperture ${side}x${side} pixels of ${meta.scale} arcsec, sum in microJy; error = frame median sigma * sqrt(npix)`,
      `wavelength = per-pixel value of each frame (linear variable filter); SPHEREx data: ${(meta.release?.doi ?? []).map((d) => `doi:${d}`).join(' ')}`,
    ]
    const url = URL.createObjectURL(new Blob([spectrumCsv(spec.points, head, win)], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `parallax_${meta.key}_x${pick.x}_y${pick.y}_spectrum.csv`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  // ---- keyboard ----------------------------------------------------------------------
  const keys = useRef<(e: KeyboardEvent) => void>(() => {})
  useEffect(() => {
    keys.current = (e) => {
      const t = e.target as HTMLElement | null
      const tag = t?.tagName
      if (e.ctrlKey || e.metaKey || e.altKey || tag === 'SELECT' || tag === 'TEXTAREA') return
      if (tag === 'INPUT') {
        const type = (t as HTMLInputElement).type
        if (type !== 'range' && type !== 'checkbox') return
        if (type === 'range' && /^(Arrow|Home|End)/.test(e.key)) return
        if (type === 'checkbox' && e.key === ' ') return
      }
      if ((tag === 'BUTTON' || tag === 'A' || tag === 'SUMMARY') && (e.key === ' ' || e.key === 'Enter')) return
      const stepBy = (d: number) => {
        setPlaying(false)
        if (length) setPos(loop ? (pos + d + length * 10) % length : Math.min(length - 1, Math.max(0, pos + d)))
      }
      const k = e.key
      if (k === ' ') setPlaying((p) => !p)
      else if (k === 'ArrowRight') stepBy(e.shiftKey ? 10 : 1)
      else if (k === 'ArrowLeft') stepBy(e.shiftKey ? -10 : -1)
      else if (k === 'Home') setPos(0)
      else if (k === 'End') setPos(Math.max(0, length - 1))
      else if (k === ']') setFps(SPEEDS[Math.min(SPEEDS.length - 1, SPEEDS.indexOf(fps) + 1)])
      else if (k === '[') setFps(SPEEDS[Math.max(0, SPEEDS.indexOf(fps) - 1)])
      else if (k === 'l' || k === 'L') setLoop((v) => !v)
      else if (k === 'p' || k === 'P') setSeq(seq === 'passes' ? 'frames' : 'passes')
      else if (k === 'x' || k === 'X') update({ smooth: !smooth })
      else if (k >= '0' && k <= '6') update({ det: Number(k) })
      else if (k === '?') setHelp((h) => !h)
      else {
        const m = MODES.find((x) => x.key === k.toUpperCase())
        if (!m) return
        setMode(m.id)
      }
      e.preventDefault()
    }
  })
  useEffect(() => {
    const h = (e: KeyboardEvent) => keys.current(e)
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  // ---- labels ------------------------------------------------------------------------
  const label: ReactNode = fi !== null ? (
    <>
      <b>{f.iso[fi].replace('T', ' ').slice(0, 16)} UTC</b>
      <span><i className="dot" style={{ background: DET_COLOURS[f.det[fi] - 1] }} />detector {f.det[fi]}</span>
      <span>{f.lam[fi]?.toFixed(3)} µm</span>
      <span>pass {f.campaign[fi] + 1}</span>
      <span className="muted">frame {fi + 1} of {pack.nFrames}</span>
    </>
  ) : pe ? (
    <>
      <b>Survey pass {pe.pass + 1}</b>
      <span>{meta.campaigns?.[pe.pass] ? `${meta.campaigns[pe.pass].start} to ${meta.campaigns[pe.pass].end}` : ''}</span>
      <span><i className="dot" style={{ background: DET_COLOURS[pe.det - 1] }} />detector {pe.det} stack, {DETECTOR_RANGE[pe.det - 1][0]}&ndash;{DETECTOR_RANGE[pe.det - 1][1]} µm</span>
      <span className="muted">{f.det.filter((d, i) => d === pe.det && f.campaign[i] === pe.pass).length} frames</span>
    </>
  ) : <span className="muted">Nothing to show</span>
  const labelText = fi !== null ? `${f.iso[fi]} detector ${f.det[fi]} ${f.lam[fi]} micron` : pe ? `pass ${pe.pass + 1} detector ${pe.det}` : ''

  const shown = hover ?? pick
  const readout = (() => {
    if (!shown) return null
    const sk = pixToSky(meta, shown.x, shown.y)
    const k = shown.y * n + shown.x
    const lam = fi !== null ? lamAt(f.lamFit[fi], shown.x, shown.y, n) : NaN
    const vals: string[] = []
    if (trio) vals.push(...trio.map((p, i) => `${['naive', 'gated', 'chromatic'][i]} ${p.data ? fmt(p.data[k]) : '–'} σ`))
    else if (product.data) {
      const v = product.data[k]
      vals.push(product.unit === 'SNR' ? `${fmt(v)} σ` : `${fmt(v, 4)} MJy/sr`)
      if (product.unit !== 'SNR') vals.push(`${fmt(v * kUJy, 4)} µJy per pixel`)
    }
    if (on.has('mismatch') && mismatch) vals.push(`colour mismatch ${fmt(mismatch[k])} bandwidths`)
    return (
      <>
        <span>RA {formatRa(sk.ra)}</span>
        <span>Dec {formatDec(sk.dec)}</span>
        <span className="muted">({sk.ra.toFixed(5)}, {sk.dec.toFixed(5)})</span>
        <span>pixel {shown.x}, {shown.y}</span>
        {Number.isFinite(lam) && <span>{lam.toFixed(4)} µm here</span>}
        {vals.map((v) => <span key={v}>{v}</span>)}
        {!hover && <span className="muted">picked pixel</span>}
      </>
    )
  })()

  const ovProps = {
    pack, view, mjd, frame: fi, on, track: tracks[det] ?? [], pick, apHalf: s.ap,
    request: s.ra !== null && s.dec !== null ? { ra: s.ra, dec: s.dec } : null, selCand,
  }
  const onPick = (p: PixelPos) => {
    setLamWin(null)
    update({ pix: [p.x, p.y] })
    setTab('Spectrum')
  }
  const jumpFrame = (i: number) => {
    setPlaying(false)
    const patch: Partial<ViewState> = { frame: i, seq: 'frames' }
    if (s.det && f.det[i] !== s.det) patch.det = 0
    const l = f.lam[i]
    if (l != null && (l < s.lamMin || l > s.lamMax)) {
      patch.lamMin = 0.7
      patch.lamMax = 5.1
    }
    if (s.mode === 'add' || s.mode === 'sub') patch.mode = 'image'
    update(patch)
  }
  const selectCandidate = (c: Candidate) => {
    setSelCand(c.id)
    if (!on.has('candidates')) toggle('candidates')
    if (c.frames.length) jumpFrame(c.frames[0])
    update({ ra: c.ra[0], dec: c.dec[0], frame: c.frames[0] ?? 0, seq: 'frames', mode: pack.snrCorr ? 'chroma' : 'image' })
  }
  const partnerLine = (j: number, what: string) => {
    if (fi === null || j < 0) return null
    const dl = ((f.lam[fi] ?? NaN) - (f.lam[j] ?? NaN)) / (f.bw[fi] ?? NaN)
    return `${what}: frame ${j + 1}, ${Math.abs(f.mjd[fi] - f.mjd[j]).toFixed(0)} days apart, colour off by ${fmt(Math.abs(dl), 2)} bandwidths`
  }
  const active = useMemo(() => new Set(frames), [frames])
  const about = MODES.find((m) => m.id === s.mode)!.about
  const staticMode = s.mode === 'add' || s.mode === 'sub'
  const fovOptions = [1, 2, 4, 6].filter((v) => v < fullArcmin - 0.2)

  const quick = motion && meta.target ? (
    <section>
      <h3>Quick look: where the star sits in each pass</h3>
      <p className="muted">
        Flux-weighted centre of the star in each per-pass stack, measured in your browser. SPHEREx pixels ({meta.scale} arcsec) are larger than
        the star image is sharp, so each centre is only good to a few tenths of a pixel; the pipeline&rsquo;s fitted measurement, when present above, supersedes this.
      </p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Detector</th><th>Passes</th><th>Measured shift (arcsec)</th><th>Catalogue predicts</th><th>Difference</th></tr></thead>
          <tbody>
            {tracks.map((t, d) => {
              if (t.length < 2) return null
              const a = t[0]
              const b = t[t.length - 1]
              const me = [-(b.x - a.x) * meta.scale, (b.y - a.y) * meta.scale]
              const pr = [-(b.px - a.px) * meta.scale, (b.py - a.py) * meta.scale]
              return (
                <tr key={d}>
                  <td><i className="dot" style={{ background: DET_COLOURS[d - 1] }} />D{d}</td>
                  <td>{a.pass + 1} to {b.pass + 1}</td>
                  <td className="num">{me[0].toFixed(1)} E, {me[1].toFixed(1)} N</td>
                  <td className="num">{pr[0].toFixed(1)} E, {pr[1].toFixed(1)} N</td>
                  <td className="num">{Math.hypot(me[0] - pr[0], me[1] - pr[1]).toFixed(1)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {tracks.every((t) => t.length < 2) && <p className="empty">The star is not detected clearly enough in two passes of one detector to measure a shift here.</p>}
    </section>
  ) : null

  const flagStats = fi !== null && pack.flags ? FLAG_STYLE.map((st) => {
    let c = 0
    const o = fi * n * n
    for (let k = 0; k < n * n; k++) if (pack.flags![o + k] & st.bit) c++
    return { ...st, frac: c / (n * n) }
  }) : null

  return (
    <div className={s.embed ? 'viewer embed' : 'viewer'}>
      {!s.embed && (
        <div className="field-head">
          <h1>{meta.name}</h1>
          <p>{meta.blurb}</p>
          <p className="muted">
            {pack.nFrames} frames in {pack.nCampaigns} survey pass{pack.nCampaigns === 1 ? '' : 'es'}, {fullArcmin.toFixed(1)} arcmin across, centred on {formatRa(meta.ra0)} {formatDec(meta.dec0)}
          </p>
          {notice && <p className="notice" role="status">{notice}</p>}
        </div>
      )}
      <div className="cols">
        <section className="stage" aria-label="Sky view">
          <div className="modes" role="tablist" aria-label="View mode">
            {MODES.map((m) => (
              <button key={m.id} role="tab" aria-selected={s.mode === m.id} className={s.mode === m.id ? 'tab on' : 'tab'} onClick={() => setMode(m.id)} title={`Shortcut: ${m.key}`}>
                {m.label}
              </button>
            ))}
          </div>
          {!s.embed && <p className="about">{about}</p>}
          {staticMode && (
            <div className="row wrap">
              <SelPicker label={s.mode === 'sub' ? 'A' : 'Stack'} sel={selA} set={setSelA} pack={pack} />
              {s.mode === 'sub' && <SelPicker label="minus B" sel={selB} set={setSelB} pack={pack} />}
            </div>
          )}
          <Player length={staticMode ? 0 : length} pos={pos} playing={playing} fps={fps} loop={loop} label={labelText} disabled={staticMode}
            onPos={setPos} onPlaying={setPlaying} onFps={setFps} onLoop={setLoop} />
          <div className="frame-label" aria-live="off">{staticMode ? <b>{product.title}</b> : label}</div>

          {trio && trioRasters ? (
            <div className="trio">
              {(['Naive pair', 'Gated pair', 'Chromatic template'] as const).map((name, i) => (
                <figure key={name}>
                  <figcaption><i className="swatch" style={{ background: ['var(--m-naive)', 'var(--m-gated)', 'var(--m-chroma)'][i] }} />{name}</figcaption>
                  <SkyCanvas n={n} base={trioRasters[i]} view={view} smooth={smooth} label={`${name} difference of frame ${fi! + 1}`} message={trio[i].missing} onHover={setHover} onPick={onPick}>
                    <Overlays {...ovProps} furniture={i === 0} />
                  </SkyCanvas>
                  <p className="muted small">
                    {i === 0 && partnerLine(trio[0].partner ?? -1, 'Partner')}
                    {i === 1 && partnerLine(trio[1].partner ?? -1, 'Partner')}
                    {i === 2 && !trio[2].missing && (f.nRef?.[fi!] != null ? `Predicted from about ${fmt(f.nRef[fi!])} frames of the other passes` : 'Predicted from the other survey passes')}
                    {trio[i].note ? ` ${trio[i].note}` : ''}
                  </p>
                </figure>
              ))}
            </div>
          ) : (
            <SkyCanvas n={n} base={base} over={over} view={view} smooth={smooth} label={`${product.title}, ${labelText}`} message={product.missing} onHover={setHover} onPick={onPick}>
              <Overlays {...ovProps} furniture />
            </SkyCanvas>
          )}

          <div className="under">
            <ColourBar lo={limits[0]} hi={limits[1]} cmap={cmap} unit={symmetric && s.mode !== 'sub' ? 'σ' : 'MJy/sr'} />
            {(s.mode === 'naive' || s.mode === 'gated') && <p className="muted small">{partnerLine(product.partner ?? -1, 'Partner')}</p>}
            {product.note && !trio && <p className="muted small">{product.note}</p>}
            {pack.partnersDerived && diffMode && <p className="muted small">Partner frames were chosen in your browser by the published rule, because this field does not list them yet.</p>}
            <div className="readout num" aria-live="off">{readout ?? <span className="muted">Move over the picture to read coordinates, wavelength and brightness. Click a pixel for its spectrum.</span>}</div>
          </div>


          <div className="row wrap filters">
            <label className="field">
              <span>Sequence</span>
              <select value={seq} onChange={(e) => setSeq(e.target.value as Seq)} disabled={diffMode || staticMode || !allPasses.length}>
                <option value="passes">By survey pass (stacks)</option>
                <option value="frames">Every frame, in time order</option>
              </select>
            </label>
            <label className="field">
              <span>Detector</span>
              <select value={s.det} onChange={(e) => update({ det: Number(e.target.value) })}>
                <option value={0}>All six</option>
                {DETECTOR_RANGE.map(([a, b], d) => <option key={d} value={d + 1}>D{d + 1}, {a}&ndash;{b} µm</option>)}
              </select>
            </label>
            <label className="field narrow">
              <span>From (µm)</span>
              <input type="number" min={0.7} max={5.1} step={0.05} value={s.lamMin} disabled={seq === 'passes'} onChange={(e) => update({ lamMin: Number(e.target.value) || 0.7 })} />
            </label>
            <label className="field narrow">
              <span>To (µm)</span>
              <input type="number" min={0.7} max={5.1} step={0.05} value={s.lamMax} disabled={seq === 'passes'} onChange={(e) => update({ lamMax: Number(e.target.value) || 5.1 })} />
            </label>
            <label className="field">
              <span>Field of view</span>
              <select value={s.fov > 0 && s.fov < fullArcmin ? s.fov : 0} onChange={(e) => {
                const fov = Number(e.target.value)
                const patch: Partial<ViewState> = { fov }
                if (fov && s.ra === null) {
                  const c = targetPix ? pixToSky(meta, targetPix.x, targetPix.y) : { ra: meta.ra0, dec: meta.dec0 }
                  patch.ra = c.ra
                  patch.dec = c.dec
                }
                update(patch)
              }}>
                {fovOptions.map((v) => <option key={v} value={v}>{v} arcmin</option>)}
                {s.fov > 0 && !fovOptions.includes(s.fov) && s.fov < fullArcmin && <option value={s.fov}>{s.fov} arcmin</option>}
                <option value={0}>Whole field ({fullArcmin.toFixed(1)} arcmin)</option>
              </select>
            </label>
            <button className="btn" onClick={() => setHelp((h) => !h)} aria-expanded={help}>Keyboard shortcuts</button>
          </div>
          {help && (
            <dl className="keys">
              {[['Space', 'play or pause'], ['← →', 'step (with Shift: ten at a time)'], ['Home, End', 'first, last'], ['[ ]', 'slower, faster'], ['L', 'loop'],
                ['P', 'by pass or every frame'], ['0–6', 'detector (0 = all)'], ['I C N G T A S', 'view modes'], ['X', 'smooth or exact pixels'], ['?', 'this list']].map(([k, v]) => (
                <div key={k}><dt><kbd>{k}</kbd></dt><dd>{v}</dd></div>
              ))}
            </dl>
          )}
        </section>

        {!s.embed && (
          <section className="side" aria-label="Measurements">
            <div className="card">
              <h2>When and at what colour</h2>
              <p className="muted small">Each dot is one frame. No two visits to this patch of sky share a wavelength, so two dates never show the same colour. Click a dot to jump to it.</p>
              <TimeLambdaMap pack={pack} current={fi} active={active} highlight={pe} lamRange={[s.lamMin, s.lamMax]} onJump={jumpFrame} />
            </div>

            <div className="card">
              <div className="tabs" role="tablist" aria-label="Panels">
                {TABS.map((t) => (
                  <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? 'tab on' : 'tab'} onClick={() => setTab(t)}>
                    {t}
                    {t === 'Candidates' && meta.candidates?.length ? <span className="badge">{meta.candidates.length}</span> : null}
                  </button>
                ))}
              </div>

              {tab === 'Spectrum' && (
                <div className="stack-gap" role="tabpanel">
                  <div className="row wrap">
                    <label className="field narrow"><span>Pixel x</span>
                      <input type="number" min={0} max={n - 1} value={pick?.x ?? ''} onChange={(e) => update({ pix: [Math.min(n - 1, Math.max(0, Math.round(Number(e.target.value)))), pick?.y ?? 0] })} /></label>
                    <label className="field narrow"><span>Pixel y</span>
                      <input type="number" min={0} max={n - 1} value={pick?.y ?? ''} onChange={(e) => update({ pix: [pick?.x ?? 0, Math.min(n - 1, Math.max(0, Math.round(Number(e.target.value))))] })} /></label>
                    <label className="field"><span>Aperture</span>
                      <select value={s.ap} onChange={(e) => update({ ap: Number(e.target.value) })}>
                        <option value={0}>1 pixel</option><option value={1}>3 × 3 pixels</option><option value={2}>5 × 5 pixels</option>
                      </select></label>
                    {s.pix && targetPix && <button className="btn" onClick={() => update({ pix: null })}>Back to the target</button>}
                    <button className="btn" onClick={download} disabled={!spec?.points.length}>Download CSV</button>
                  </div>
                  {!pick && <p className="empty">Click any pixel of the picture, or type its position, to build its spectrum from every frame.</p>}
                  {spec && pickSky && (
                    <>
                      <p className="muted small">
                        Sum of {(2 * s.ap + 1) ** 2} pixel{s.ap ? 's' : ''} at {formatRa(pickSky.ra)} {formatDec(pickSky.dec)} in {spec.points.length} frames, each at its own wavelength.
                        {spec.skipped ? ` ${spec.skipped} frames have no data there (saturated, masked or off the edge).` : ''}{spec.skipped > 0.8 * pack.nFrames ? ' Very bright stars saturate: their cores are blank. Click a pixel on the star\u2019s wing, or another star.' : ''} Bars are 1 sigma from each frame&rsquo;s noise. Drag across the plot to choose a wavelength window.
                      </p>
                      {spec.points.length > 1 ? <SpectrumChart points={spec.points} window={win} current={fi} onWindow={setLamWin} onJump={jumpFrame} /> : <p className="empty">Not enough frames with data at this pixel.</p>}
                      <ul className="legend">
                        {Array.from({ length: pack.nCampaigns }, (_, c) => <li key={c}><i style={{ background: PASS_COLOURS[c % 4] }} />pass {c + 1}{meta.campaigns?.[c] ? `, ${meta.campaigns[c].start.slice(0, 7)}` : ''}</li>)}
                      </ul>
                      {win && (
                        <>
                          <h3>Light curve inside the window</h3>
                          <div className="row wrap">
                            <label className="field narrow"><span>From (µm)</span>
                              <input type="number" step={0.01} value={win[0]} onChange={(e) => setLamWin([Number(e.target.value), win[1]])} /></label>
                            <label className="field narrow"><span>To (µm)</span>
                              <input type="number" step={0.01} value={win[1]} onChange={(e) => setLamWin([win[0], Number(e.target.value)])} /></label>
                            <span className="muted small grow">{inWin.length} measurements. Even inside a narrow window the colours differ slightly, so compare with care.</span>
                          </div>
                          {inWin.length > 0 ? <LightCurve pack={pack} points={inWin} current={fi} onJump={jumpFrame} /> : <p className="empty">No frame saw this pixel at a wavelength inside the window. Widen it or drag elsewhere.</p>}
                        </>
                      )}
                    </>
                  )}
                </div>
              )}

              {tab === 'Display' && (
                <div className="stack-gap" role="tabpanel">
                  <div className="row wrap">
                    <label className="field"><span>Stretch (images)</span>
                      <select value={s.stretch} onChange={(e) => update({ stretch: e.target.value as ViewState['stretch'] })}>
                        <option value="asinh">Asinh (faint and bright together)</option><option value="linear">Linear</option><option value="log">Logarithmic</option>
                      </select></label>
                    <label className="field"><span>Colours</span>
                      <select value={cmap} onChange={(e) => update({ cmap: e.target.value as CmapName })}>
                        <option value="grey">Grey</option><option value="perceptual">Blue to yellow (perceptual)</option><option value="diverging">Blue / amber (differences)</option>
                      </select></label>
                    <label className="field narrow"><span>Low limit (%)</span>
                      <input type="number" min={0} max={50} step={0.5} value={s.pLo} onChange={(e) => { setLock(null); update({ pLo: Math.min(Number(e.target.value), s.pHi - 0.1) }) }} /></label>
                    <label className="field narrow"><span>High limit (%)</span>
                      <input type="number" min={50} max={100} step={0.1} value={s.pHi} onChange={(e) => { setLock(null); update({ pHi: Math.max(Number(e.target.value), s.pLo + 0.1) }) }} /></label>
                  </div>
                  <label className="check"><input type="checkbox" checked={smooth} onChange={(e) => update({ smooth: e.target.checked })} />
                    <span>Smooth (4× bicubic) instead of exact pixels. Easier to see a sub-pixel shift; the measured values do not change.</span></label>
                  <label className="check"><input type="checkbox" checked={!!lock} onChange={(e) => setLock(e.target.checked ? limits : null)} />
                    <span>Hold these limits while blinking ({fmt(limits[0])} to {fmt(limits[1])}). Otherwise each picture is scaled to its own percentiles.</span></label>
                  {s.fov > 0 && targetPix && (
                    <button className="btn" onClick={() => { const c = pixToSky(meta, targetPix.x, targetPix.y); update({ ra: c.ra, dec: c.dec }) }}>Centre the view on the target</button>
                  )}
                  {s.fov > 0 && pick && (
                    <button className="btn" onClick={() => { const c = pixToSky(meta, pick.x, pick.y); update({ ra: c.ra, dec: c.dec }) }}>Centre the view on the picked pixel</button>
                  )}
                </div>
              )}

              {tab === 'Overlays' && (
                <div className="stack-gap" role="tabpanel">
                  {OVERLAYS.map((o) => {
                    const need = o === 'mismatch' ? (fi === null ? 'Needs a single frame (not a stack).' : partner < 0 ? 'This frame has no partner.' : null)
                      : !available[o] ? (o === 'track' ? 'Only for fields with a moving target and two passes.' : 'Not in this field’s data yet.') : null
                    return (
                      <label key={o} className={need ? 'check off' : 'check'}>
                        <input type="checkbox" checked={on.has(o)} onChange={() => toggle(o)} />
                        <span>{OVERLAY_LABEL[o]}{need && <em> {need}</em>}</span>
                      </label>
                    )
                  })}
                  {on.has('mismatch') && mismatch && fi !== null && (
                    <p className="muted small">
                      Tint: blue where this frame is bluer than its partner (frame {partner + 1}), amber where redder, full colour at one bandwidth.
                      Median mismatch here {fmt(percentiles(Float32Array.from(mismatch, Math.abs), [50])[0], 2)} bandwidths.
                    </p>
                  )}
                  {on.has('flags') && (
                    <ul className="legend col">
                      {FLAG_STYLE.map((st) => <li key={st.bit}><i style={{ background: `rgb(${st.rgba.slice(0, 3).join(',')})` }} />{st.label}</li>)}
                    </ul>
                  )}
                  <ul className="legend col">
                    <li><i className="ring gaia" />Gaia star</li><li><i className="ring wise" />CatWISE source</li><li><i className="ring sso" />Solar-system object</li>
                    <li><i className="ring target" />Catalogue position of the target at the frame date</li>
                  </ul>
                </div>
              )}

              {tab === 'Frame' && (
                <div role="tabpanel">
                  {fi === null ? <p className="empty">Switch the sequence to &ldquo;Every frame&rdquo; to see the details of a single exposure.</p> : (
                    <dl className="tree">
                      {([
                        ['Date (UTC)', f.iso[fi].replace('T', ' ')], ['Modified Julian Date', f.mjd[fi].toFixed(6)], ['Survey pass', String(f.campaign[fi] + 1)],
                        ['Detector', `D${f.det[fi]}`], ['Wavelength at field centre', `${fmt(f.lam[fi], 5)} µm`],
                        ['Bandwidth', `${fmt(f.bw[fi], 3)} µm (resolving power ${fmt((f.lam[fi] ?? NaN) / (f.bw[fi] ?? NaN), 3)})`],
                        ['Wavelength across the field', `${fmt(lamAt(f.lamFit[fi], 0, 0, n), 5)} to ${fmt(lamAt(f.lamFit[fi], n - 1, n - 1, n), 5)} µm, corner to corner`],
                        ['Noise, 1 sigma per pixel', `${fmt(f.sigma[fi])} MJy/sr = ${fmt((f.sigma[fi] ?? NaN) * kUJy)} µJy`],
                        ['Residual sky removed', f.sky ? `${fmt(f.sky[fi])} MJy/sr` : null], ['Zodiacal light removed', f.zodi ? `${fmt(f.zodi[fi])} MJy/sr` : null],
                        ['Star image width (FWHM)', f.fwhm ? `${fmt(f.fwhm[fi])} arcsec` : null],
                        ['Frames behind the template', f.nRef ? fmt(f.nRef[fi]) : null],
                        ['Naive partner', partnerLine(pack.naivePartner[fi], 'Chosen') ?? 'none'], ['Gated partner', partnerLine(pack.gatedPartner[fi], 'Chosen') ?? 'none within half a bandwidth'],
                        ['Source file', f.name?.[fi] ?? null], ['Data release', f.collection?.[fi] ?? null],
                      ] as [string, string | null][]).filter(([, v]) => v !== null).map(([k, v]) => <div key={k}><dt>{k}</dt><dd className="num">{v}</dd></div>)}
                      {flagStats && <div><dt>Flagged pixels</dt><dd>{flagStats.map((st) => <span key={st.bit} className="flagstat"><i className="dot" style={{ background: `rgb(${st.rgba.slice(0, 3).join(',')})` }} />{st.label.split(' (')[0]}: {(st.frac * 100).toFixed(1)}%</span>)}</dd></div>}
                    </dl>
                  )}
                </div>
              )}

              {tab === 'Candidates' && <div role="tabpanel"><CandidatesPanel pack={pack} selected={selCand} onSelect={selectCandidate} /></div>}
              {tab === 'Science' && <div role="tabpanel"><SciencePanel pack={pack} quick={quick} /></div>}
              {tab === 'Ledger' && <div role="tabpanel"><LedgerPanel pack={pack} /></div>}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
