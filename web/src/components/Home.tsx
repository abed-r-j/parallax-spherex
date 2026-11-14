/**
 * Entry: the coordinate box, the five challenge targets, the gallery of fields, and the
 * resolver that turns typed coordinates into a field (precomputed, or built by the engine).
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { parseCoords } from '../lib/coords'
import { loadPack, stackImage } from '../lib/decode'
import { JOB_DONE, JOB_FAILED, engineBase, engineHealthy, jobStatus, saveEngineBase, submitField, type JobStatus } from '../lib/engine'
import { PRESETS, fieldContaining, formatSep, nearestFields, presetNear } from '../lib/fields'
import { passEntries } from '../lib/products'
import { percentiles, renderRgba, upsampleBicubic } from '../lib/stretch'
import type { IndexField, Pack, PackIndex } from '../lib/types'
import type { ViewState } from '../lib/urlstate'
import { formatDec, formatRa, mjdToYear, propagate, skyToPix } from '../lib/wcs'
import { LiveOffer } from './Live'
import { SkyCanvas, type Raster } from './SkyCanvas'

type Update = (patch: Partial<ViewState>) => void
const OPEN: Partial<ViewState> = { page: 'view', frame: 0, mode: 'image', seq: null, det: 0, fov: 0, pix: null, overlays: null, cmap: null, smooth: null, live: null }

export function CoordBox({ index, update, big }: { index: PackIndex | null; update: Update; big?: boolean }) {
  const [text, setText] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const t = text.trim()
    if (!t) return
    const pos = parseCoords(t)
    if (pos) {
      setErr(null)
      update({ ...OPEN, field: null, ra: pos.ra, dec: pos.dec })
      return
    }
    const name = t.toLowerCase().replace(/[^a-z0-9]/g, '')
    const hit = index?.fields.find((f) => f.key === name || f.name.toLowerCase().replace(/[^a-z0-9]/g, '').includes(name))
    if (hit && name.length >= 3) {
      setErr(null)
      update({ ...OPEN, field: hit.key, ra: null, dec: null })
      return
    }
    setErr('That does not read as coordinates. Try decimal degrees "133.795 -7.245", or hours and degrees "08 55 10.83 -07 14 42.5" or "08h55m10.831s -7d14m42.53s".')
  }
  return (
    <form className="coord" onSubmit={submit} role="search">
      <input
        type="search"
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setErr(null)
        }}
        placeholder={big ? 'RA and Dec, for example 08 55 10.83 -07 14 42.5' : 'RA Dec, or a field name'}
        aria-label="Sky coordinates: right ascension and declination"
        aria-invalid={!!err}
        spellCheck={false}
        autoComplete="off"
      />
      <button className={big ? 'btn primary' : 'btn'} type="submit">Show this sky</button>
      {err && <p className="err" role="alert">{err}</p>}
    </form>
  )
}

/** The hero picture: a real field blinking between its survey passes. */
function HeroBlink({ field }: { field: IndexField }) {
  const [pack, setPack] = useState<Pack | null>(null)
  const [k, setK] = useState(0)
  const still = useMemo(() => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches, [])
  const [run, setRun] = useState(!still)
  useEffect(() => {
    const ctl = new AbortController()
    loadPack('./data', field.key, ctl.signal).then(setPack).catch(() => {})
    return () => ctl.abort()
  }, [field.key])
  const scene = useMemo(() => {
    if (!pack) return null
    const all = passEntries(pack, 0)
    const n = pack.n
    const t = pack.meta.target
    const mid = pack.meta.frames.mjd[pack.nFrames >> 1]
    const now = t ? propagate(t.ra, t.dec, t.pmRa, t.pmDec, t.epoch, mjdToYear(mid)) : null
    const p = now ? skyToPix(pack.meta, now.ra, now.dec) : null
    const k0 = p ? Math.round(p.y) * n + Math.round(p.x) : -1
    // prefer the detector seen in the most passes, and one where the target is not saturated
    const score = (d: number) => {
      const mine = all.filter((e) => e.det === d)
      const clean = mine.filter((e) => k0 < 0 || Number.isFinite(stackImage(pack, e.pass, e.det)?.[k0])).length
      return mine.length * 10 + clean
    }
    const det = [3, 2, 4, 1, 5, 6].reduce((a, b) => (score(b) > score(a) ? b : a))
    const list = all.filter((e) => e.det === det)
    if (!list.length) return null
    const half = Math.min(n / 2, 13)
    const cx = Math.min(n - 0.5 - half, Math.max(half - 0.5, p?.x ?? (n - 1) / 2))
    const cy = Math.min(n - 0.5 - half, Math.max(half - 0.5, p?.y ?? (n - 1) / 2))
    const imgs = list.map((e) => stackImage(pack, e.pass, e.det)!)
    const [lo, hi] = percentiles(imgs[0], [2, 99.9])
    const rasters: Raster[] = imgs.map((im) => ({ rgba: renderRgba(upsampleBicubic(im, n, 4), n * 4, n * 4, { kind: 'asinh', lo, hi, symmetric: false, cmap: 'grey' }), m: n * 4 }))
    return { list, rasters, view: { cx, cy, half }, det }
  }, [pack])
  const count = scene?.rasters.length ?? 0
  useEffect(() => {
    if (!run || count < 2) return
    const id = setInterval(() => setK((v) => v + 1), 800)
    return () => clearInterval(id)
  }, [run, count])
  if (!pack || !scene) return field.thumb ? <figure><img src={`./data/${field.thumb}`} alt={`SPHEREx image of ${field.name}`} style={{ width: '100%', imageRendering: 'pixelated' }} /></figure> : null
  const cur = scene.list[k % count]
  const camp = pack.meta.campaigns?.[cur.pass]
  return (
    <figure>
      <SkyCanvas n={pack.n} base={scene.rasters[k % count]} view={scene.view} smooth label={`${field.name} in survey pass ${cur.pass + 1}`} />
      <figcaption>
        {field.name}, detector {scene.det}, survey pass {cur.pass + 1}{camp ? ` (${camp.start.slice(0, 7)})` : ''}. Real SPHEREx data, {(scene.view.half * 2 * pack.meta.scale / 60).toFixed(1)} arcmin across.{' '}
        {count > 1 ? <button className="link" onClick={() => setRun((r) => !r)}>{run ? 'Pause' : 'Blink the passes'}</button> : null}
      </figcaption>
    </figure>
  )
}

export function Home({ index, indexError, update }: { index: PackIndex | null; indexError: string | null; update: Update }) {
  const fields = index?.fields ?? []
  const heroField = fields.find((f) => f.kind === 'motion') ?? fields[0]
  const have = new Set(fields.map((f) => f.key))
  return (
    <>
      <section className="hero">
        <div>
          <h1>Every time SPHEREx looks back at a star, it looks in a different colour.</h1>
          <p className="lede">
            ParallaX plays the SPHEREx infrared sky as a little video, and works out what each frame should have looked like at its own colours,
            so that fainter real changes stand out from the false alarms.
          </p>
          <CoordBox index={index} update={update} big />
          <p className="hint">Decimal degrees or hours-minutes-seconds, ICRS. A field name works too.</p>
          <div className="presets" aria-label="Challenge targets">
            {PRESETS.map((p) => (
              <button key={p.key} className={have.has(p.key) ? 'btn preset' : 'btn preset missing'}
                onClick={() => (have.has(p.key) ? update({ ...OPEN, field: p.key, ra: null, dec: null }) : update({ ...OPEN, field: null, ra: p.ra, dec: p.dec }))}>
                {p.name}
                <small>{p.what}{have.has(p.key) ? '' : ', not precomputed yet'}</small>
              </button>
            ))}
          </div>
        </div>
        {heroField && <HeroBlink field={heroField} />}
      </section>

      <h2 className="section-title">Fields ready to explore</h2>
      {indexError && <p className="empty" role="alert">The list of fields could not be loaded ({indexError}). If you opened this page straight from a folder, serve it with any static web server instead.</p>}
      {!indexError && !index && <p className="muted">Loading the list of fields.</p>}
      {index && !fields.length && <p className="empty">No fields have been published yet.</p>}
      <ul className="gallery">
        {fields.map((f) => (
          <li key={f.key}>
            <button onClick={() => update({ ...OPEN, field: f.key, ra: null, dec: null })}>
              {f.thumb ? <img src={`./data/${f.thumb}`} alt="" loading="lazy" /> : <span />}
              <span>
                <b>{f.name}</b>
                <span>{f.blurb}</span>
                <span className="num">{f.nFrames} frames, {f.nCampaigns} pass{f.nCampaigns === 1 ? '' : 'es'}</span>
                <span className="kind">{f.kind}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </>
  )
}

type Phase =
  | { kind: 'checking' }
  | { kind: 'ready' }
  | { kind: 'working'; job: JobStatus }
  | { kind: 'none' }
  | { kind: 'failed'; why: string }

/**
 * Coordinates without a field: open the precomputed field if one covers them; otherwise
 * offer the two ways to get one: fetch it live in the browser, or ask a ParallaX engine.
 */
export function Resolve({ index, s, update, onNotice }: { index: PackIndex; s: ViewState; update: Update; onNotice: (n: string | null) => void }) {
  const ra = s.ra!
  const dec = s.dec!
  const [base, setBase] = useState(() => engineBase(s.engine))
  const [draft, setDraft] = useState(base)
  const [attempt, setAttempt] = useState(0)
  // an engine named in the address is used at once; otherwise the reader chooses
  const [useEngine, setUseEngine] = useState(!!s.engine)
  const [phase, setPhase] = useState<Phase>({ kind: 'checking' })

  useEffect(() => {
    const hit = fieldContaining(index.fields, ra, dec)
    if (hit) {
      onNotice(null)
      update({ field: hit.key })
      return
    }
    const pre = presetNear(ra, dec)
    if (pre && index.fields.some((f) => f.key === pre.key)) {
      onNotice(`These are the catalogue coordinates of ${pre.name} for the year ${pre.epoch}. It has moved since, so the field is centred where it is now.`)
      update({ field: pre.key, ra: null, dec: null })
      return
    }
    let stop = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const run = async () => {
      setPhase({ kind: 'checking' })
      if (!(await engineHealthy(base))) {
        if (!stop) setPhase({ kind: 'none' })
        return
      }
      if (!useEngine) {
        if (!stop) setPhase({ kind: 'ready' })
        return
      }
      try {
        const id = await submitField(base, ra, dec, s.fov > 0 ? s.fov : 6.25)
        const poll = async () => {
          if (stop) return
          const job = await jobStatus(base, id)
          if (stop) return
          if (JOB_DONE.includes(job.state) && job.key) {
            onNotice('This field was built just now by the live engine.')
            update({ field: job.key, engine: base })
          } else if (JOB_FAILED.includes(job.state)) {
            setPhase({ kind: 'failed', why: job.message || 'The engine could not build this field.' })
          } else {
            setPhase({ kind: 'working', job })
            timer = setTimeout(() => poll().catch((e: Error) => !stop && setPhase({ kind: 'failed', why: e.message })), 1500)
          }
        }
        await poll()
      } catch (e) {
        if (!stop) setPhase({ kind: 'failed', why: e instanceof Error ? e.message : String(e) })
      }
    }
    void run()
    return () => {
      stop = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, ra, dec, base, attempt, useEngine])

  const near = nearestFields(index.fields, ra, dec, 4)
  const working = phase.kind === 'working' || (useEngine && phase.kind === 'checking')
  return (
    <div className="resolve">
      <h1>{formatRa(ra)} {formatDec(dec)}</h1>
      <p className="muted num">RA {ra.toFixed(5)}, Dec {dec.toFixed(5)} degrees</p>
      {!working && <p>These coordinates are outside the fields that were computed in advance. There are two ways to see this patch of sky.</p>}
      {!working && <LiveOffer ra={ra} dec={dec} update={update} />}
      <section className="card">
        <h2>Use a ParallaX engine</h2>
        {!working && (
          <p className="muted small">
            The engine is the full Python pipeline running on a computer: it also builds the chromatic template, the three-way comparison and the searches. It takes several minutes per field.
          </p>
        )}
        {phase.kind === 'checking' && (
          <>
            <p role="status">Looking for an engine at {base}.</p>
            <div className="bar busy"><i /></div>
          </>
        )}
        {phase.kind === 'ready' && (
          <div className="row wrap">
            <span className="grow">An engine answers at {base}.</span>
            <button className="btn" onClick={() => setUseEngine(true)}>Build this field with the engine</button>
          </div>
        )}
        {phase.kind === 'working' && (
          <>
            <p role="status">The engine is fetching SPHEREx cutouts for this position and building the field. This takes a few minutes: the archive serves about one frame every ten seconds.</p>
            <div className={phase.job.progress === null ? 'bar busy' : 'bar'} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={phase.job.progress === null ? undefined : Math.round(phase.job.progress * 100)}>
              <i style={phase.job.progress === null ? undefined : { width: `${phase.job.progress * 100}%` }} />
            </div>
            <p className="muted">{phase.job.message || phase.job.state}{phase.job.progress !== null ? ` (${Math.round(phase.job.progress * 100)}%)` : ''}</p>
          </>
        )}
        {(phase.kind === 'none' || phase.kind === 'failed') && (
          <>
            <p role={phase.kind === 'failed' ? 'alert' : 'status'}>
              {phase.kind === 'none'
                ? `No engine answered at ${base}. If you run one on your computer or elsewhere, give its address.`
                : `The engine at ${base} could not build this field: ${phase.why}`}
            </p>
            <form className="row wrap" onSubmit={(e) => { e.preventDefault(); const b = draft.trim().replace(/\/+$/, ''); saveEngineBase(b); setBase(b || engineBase()); setAttempt((a) => a + 1) }}>
              <label className="field grow"><span>Engine address</span>
                <input type="url" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="http://127.0.0.1:8000" /></label>
              <button className="btn" type="submit">Try again</button>
            </form>
          </>
        )}
      </section>
      {near.length > 0 && (
        <>
          <h2>Nearest fields that are ready</h2>
          <ul className="near">
            {near.map(({ field, sep }) => (
              <li key={field.key}>
                <button className="link" onClick={() => update({ field: field.key, ra: null, dec: null })}>{field.name}</button>
                <span className="muted">, {formatSep(sep)} away</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p><button className="btn" onClick={() => update({ page: 'home', ra: null, dec: null, field: null, live: null })}>Back to all fields</button></p>
    </div>
  )
}
