/**
 * The live route: the offer (which detectors, how large, how long it will take), and the
 * field itself while it is fetched in the browser from the public SPHEREx archive: a
 * progress panel with the frames as they arrive, then the ordinary viewer, filling in.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { LIVE_DEFAULT_DETECTORS, LIVE_DEFAULT_MAX, LIVE_DEFAULT_SIZE, LIVE_SIZES, estimateLive, liveGridN, LIVE_SCALE } from '../lib/live'
import { cancelLive, startLive, subscribeLive, type LiveJob, type Thumb } from '../lib/liveStore'
import { querySkyIndex, type SkyQuery } from '../lib/skyindex'
import { percentiles, renderRgba } from '../lib/stretch'
import { DETECTOR_RANGE } from '../lib/types'
import type { LiveRequest, ViewState } from '../lib/urlstate'
import { formatDec, formatRa } from '../lib/wcs'
import { Viewer } from './Viewer'

type Update = (patch: Partial<ViewState>) => void

/** ?probe in the address the page was opened with: expose the live job to the verification script. */
const PROBE = typeof location !== 'undefined' && new URLSearchParams(location.search).has('probe')

const mb = (bytes: number) => (bytes / 1e6).toFixed(bytes < 1e7 ? 1 : 0)
const dateOf = (mjd: number) => new Date((mjd - 40587) * 86400000).toISOString().slice(0, 10)

function duration(seconds: number): string {
  if (!Number.isFinite(seconds)) return ''
  if (seconds < 90) return `${Math.max(1, Math.round(seconds))} s`
  return `${(seconds / 60).toFixed(seconds < 600 ? 1 : 0)} min`
}

/** The choice shown for coordinates that no precomputed field covers. */
export function LiveOffer({ ra, dec, update }: { ra: number; dec: number; update: Update }) {
  const [found, setFound] = useState<SkyQuery | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [size, setSize] = useState<number>(LIVE_DEFAULT_SIZE)
  const [picked, setPicked] = useState<number[] | null>(null)

  useEffect(() => {
    const ctl = new AbortController()
    querySkyIndex(ra, dec, { signal: ctl.signal }).then(
      (q) => setFound(q),
      (e: Error) => !ctl.signal.aborted && setError(e.message),
    )
    return () => ctl.abort()
  }, [ra, dec])

  const counts = useMemo(() => {
    const c = new Array<number>(7).fill(0)
    for (const h of found?.hits ?? []) c[h.det]++
    return c
  }, [found])
  if (error) return <section className="card"><h2>Fetch live from NASA&rsquo;s public archive</h2><p role="alert">The sky index of this site could not be read ({error}), so the live route is not available here.</p></section>
  if (!found) return <section className="card"><h2>Fetch live from NASA&rsquo;s public archive</h2><p role="status" className="muted">Looking up which SPHEREx images cover this position.</p><div className="bar busy"><i /></div></section>

  const hits = found.hits
  const built = found.manifest.built_utc.slice(0, 10)
  if (!hits.length)
    return (
      <section className="card">
        <h2>Fetch live from NASA&rsquo;s public archive</h2>
        <p role="alert">SPHEREx has no image of this position in the index of this site (public data up to {built}). There is nothing to fetch.</p>
      </section>
    )
  const dets = (picked ?? LIVE_DEFAULT_DETECTORS).filter((d) => counts[d] > 0)
  const matching = dets.reduce((a, d) => a + counts[d], 0)
  const used = Math.min(matching, LIVE_DEFAULT_MAX)
  const est = estimateLive(used, size)
  const toggle = (d: number) => setPicked(dets.includes(d) ? dets.filter((x) => x !== d) : [...dets, d].sort((a, b) => a - b))
  const start = () => {
    const live: LiveRequest = { sizeArcmin: size, detectors: dets.length === 6 ? [] : dets, maxImages: LIVE_DEFAULT_MAX }
    update({ live, frame: 0, mode: 'image', seq: null, det: 0, fov: 0, pix: null })
  }
  return (
    <section className="card live-offer">
      <h2>Fetch live from NASA&rsquo;s public archive, in your browser</h2>
      <p>
        SPHEREx photographed this position <b>{hits.length}</b> times between {dateOf(hits[0].mjd)} and {dateOf(hits[hits.length - 1].mjd)}.
        This page can read just the pixels it needs straight from the public SPHEREx archive (NASA/IPAC IRSA, hosted on AWS). No server of ours is involved.
      </p>
      <fieldset className="sel live-dets">
        <legend>Detectors (each sees its own range of infrared colours)</legend>
        {DETECTOR_RANGE.map(([a, b], i) => (
          <label key={i} className={counts[i + 1] ? 'check' : 'check off'}>
            <input type="checkbox" checked={dets.includes(i + 1)} disabled={!counts[i + 1]} onChange={() => toggle(i + 1)} />
            <span>D{i + 1}, {a}&ndash;{b} µm <em>{counts[i + 1]} image{counts[i + 1] === 1 ? '' : 's'}</em></span>
          </label>
        ))}
      </fieldset>
      <div className="row wrap">
        <label className="field">
          <span>Size of the field</span>
          <select value={size} onChange={(e) => setSize(Number(e.target.value))}>
            {LIVE_SIZES.map((v) => <option key={v} value={v}>{v} arcmin ({liveGridN(v)} × {liveGridN(v)} pixels of {LIVE_SCALE} arcsec)</option>)}
          </select>
        </label>
        <button className="btn primary" onClick={start} disabled={!matching}>Fetch {used} image{used === 1 ? '' : 's'} live</button>
      </div>
      <p className="muted small" role="status">
        {matching
          ? <>About {mb(est.bytes)} MB to download: {duration(est.secondsFast)} on a fast connection, up to {duration(est.secondsSlow)} on a slow one (the archive served us 0.3 to 0.5 MB per second). The pictures appear as they arrive, and you can stop at any time.</>
          : 'Choose at least one detector that has images.'}
        {matching > used ? ` Only ${used} of the ${matching} images are fetched, evenly spaced in time; ${matching - used} are left out.` : ''}
      </p>
      <p className="muted small">
        A live field gives you the frames, the per-pass stacks, spectra, add and subtract, and the naive and gated pair differences. One sky level per frame is removed and pixels are not flag-masked.
        The chromatic template and the searches are made by the Python pipeline: for those, use a ParallaX engine.
      </p>
    </section>
  )
}

function ThumbCanvas({ t }: { t: Thumb }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const ctx = ref.current?.getContext('2d')
    if (!ctx) return
    const [lo, hi] = percentiles(t.img, [5, 99.5])
    ctx.putImageData(new ImageData(renderRgba(t.img, t.n, t.n, { kind: 'asinh', lo, hi: hi > lo ? hi : lo + 1e-6, symmetric: false, cmap: 'grey' }), t.n, t.n), 0, 0)
  }, [t])
  return (
    <figure className="live-thumb">
      <canvas ref={ref} width={t.n} height={t.n} role="img" aria-label={`Frame of ${dateOf(t.mjd)}, detector ${t.det}`} />
      <figcaption className="num">D{t.det} {Number.isFinite(t.lam) ? `${t.lam.toFixed(2)} µm` : ''}</figcaption>
    </figure>
  )
}

function useJob(job: LiveJob): number {
  return useSyncExternalStore((cb) => subscribeLive(job, cb), () => job.version)
}

function progressLine(job: LiveJob): string {
  const p = job.progress
  if (!p || p.phase === 'index') return 'Reading the sky index of this site.'
  const rate = p.seconds > 2 && p.done > 0 ? p.done / p.seconds : 0
  const left = rate > 0 && p.done < p.total ? `, about ${duration((p.total - p.done) / rate)} left` : ''
  const odd = [p.skipped ? `${p.skipped} off the detector edge` : '', p.failed ? `${p.failed} failed` : ''].filter(Boolean).join(', ')
  return `${p.done} of ${p.total} images, ${mb(p.bytes)} MB in ${duration(p.seconds)}${left}${odd ? ` (${odd})` : ''}`
}

/** A field being built in the browser: progress first, then the viewer while it fills in. */
export function LiveField({ s, update }: { s: ViewState; update: Update }) {
  const request = useMemo(() => ({ ra: s.ra!, dec: s.dec!, ...s.live! }), [s.ra, s.dec, s.live])
  const [job, setJob] = useState(() => startLive(request))
  useJob(job)
  const p = job.progress
  const pack = job.pack
  const running = job.state === 'running'
  const frac = p && p.total ? p.done / p.total : 0
  const retry = () => setJob(startLive(request, true))
  const back = () => update({ live: null })

  useEffect(() => {
    // a hook for the verification scripts (scripts/live-check.mjs): the field as the viewer sees it
    if (PROBE) (window as unknown as { __parallaxLive?: LiveJob }).__parallaxLive = job
  }, [job])

  const bar = (
    <div className={p && p.phase !== 'index' ? 'bar' : 'bar busy'} role="progressbar" aria-label="Live fetch progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(frac * 100)}>
      <i style={p && p.phase !== 'index' ? { width: `${frac * 100}%` } : undefined} />
    </div>
  )

  if (pack && pack.nFrames >= 3) {
    const info = pack.meta.live!
    const left = info.dropped ? ` ${info.dropped} more images of these detectors exist; ${info.requested} evenly spaced in time were used.` : ''
    const odd = [info.skipped ? `${info.skipped} fell off the detector edge` : '', info.failed ? `${info.failed} could not be fetched` : ''].filter(Boolean).join('; ')
    const done =
      `Fetched live in your browser from NASA's public SPHEREx archive: ${info.loaded} images, ${mb(info.bytes)} MB in ${duration(info.seconds)}.` +
      `${odd ? ` ${odd[0].toUpperCase()}${odd.slice(1)}.` : ''}${left} The chromatic template is not part of a live field.`
    return (
      <>
        {job.state !== 'done' && !s.embed && (
          <div className="live-banner" role="status">
            {running ? (
              <>
                <span><b>Fetching live from NASA&rsquo;s public archive.</b> {progressLine(job)}. The field fills in as frames arrive.</span>
                {bar}
                <button className="btn" onClick={() => cancelLive(job.key)}>Stop</button>
              </>
            ) : (
              <>
                <span>
                  {job.state === 'failed' ? `The live fetch stopped: ${job.error}` : 'The live fetch was stopped.'} Showing the {pack.nFrames} frames that arrived{p ? ` (of ${p.total})` : ''}.
                </span>
                <button className="btn" onClick={retry}>Fetch the rest</button>
              </>
            )}
          </div>
        )}
        <Viewer key={job.key} pack={pack} s={s} update={update} notice={job.state === 'done' ? done : null} />
      </>
    )
  }

  return (
    <div className="resolve">
      <h1>{formatRa(s.ra!)} {formatDec(s.dec!)}</h1>
      <p className="muted num">RA {s.ra!.toFixed(5)}, Dec {s.dec!.toFixed(5)} degrees</p>
      {running && (
        <>
          <p role="status">
            <b>Fetching live from NASA&rsquo;s public archive.</b> Your browser is reading the SPHEREx Level-2 images of this position straight from the NASA/IPAC IRSA bucket on AWS:
            only the header and the few detector rows it needs from each 65 MB file.
          </p>
          {bar}
          <p className="muted num">{progressLine(job)}</p>
          {p && p.phase !== 'index' && <p className="muted small">{p.message} The viewer opens as soon as three frames are in.</p>}
        </>
      )}
      {job.state === 'failed' && <p role="alert">The live fetch did not work: {job.error}</p>}
      {job.state === 'cancelled' && <p role="status">The live fetch was stopped before enough frames arrived.</p>}
      {job.thumbs.length > 0 && (
        <div className="live-thumbs" aria-label="The most recent frames">
          {job.thumbs.map((t, i) => <ThumbCanvas key={`${t.mjd}-${t.det}-${i}`} t={t} />)}
        </div>
      )}
      <div className="row wrap">
        {running ? <button className="btn" onClick={() => cancelLive(job.key)}>Stop</button> : <button className="btn primary" onClick={retry}>Try again</button>}
        <button className="btn" onClick={back}>Other options for this position</button>
      </div>
    </div>
  )
}
