/**
 * Panels for the pack's candidates, science and ledger blocks. Documented keys get a
 * designed presentation; anything else is rendered generically so new pipeline output
 * shows up without a code change.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { useState, type ReactNode } from 'react'
import type { Candidate, Pack } from '../lib/types'
import { CompletenessChart, type Series } from './Charts'
import { CLASS_COLOURS } from './Overlays'

type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v)

function dig(v: unknown, ...path: string[]): unknown {
  let o = v
  for (const k of path) {
    if (!isObj(o)) return undefined
    o = o[k]
  }
  return o
}

const asNum = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

export function fmt(v: unknown, digits = 3): string {
  if (v === null || v === undefined) return '–'
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return '–'
    if (Number.isInteger(v)) return String(v)
    const a = Math.abs(v)
    if (a >= 1000) return v.toFixed(0)
    if (a >= 100) return v.toFixed(1)
    return String(+v.toPrecision(digits))
  }
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  return String(v)
}

/** camelCase or snake_case key to words. */
export function words(key: string): string {
  const s = key.replace(/_/g, ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2').toLowerCase()
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** Generic, recursive rendering of any JSON value. */
export function DataTree({ value, depth = 0 }: { value: unknown; depth?: number }): ReactNode {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="muted">none</span>
    if (value.every(isObj)) {
      const keys = [...new Set(value.flatMap((r) => Object.keys(r as Obj)))].slice(0, 9)
      return (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>{keys.map((k) => <th key={k}>{words(k)}</th>)}</tr>
            </thead>
            <tbody>
              {value.slice(0, 60).map((r, i) => (
                <tr key={i}>{keys.map((k) => <td key={k}><DataTree value={(r as Obj)[k]} depth={depth + 1} /></td>)}</tr>
              ))}
            </tbody>
          </table>
          {value.length > 60 && <p className="muted">{value.length - 60} more rows not shown.</p>}
        </div>
      )
    }
    if (value.every((v) => typeof v === 'string') && value.some((v) => (v as string).length > 40))
      return <ul className="notes">{value.map((v, i) => <li key={i}>{v as string}</li>)}</ul>
    const txt = value.length <= 12 ? value.map((v) => fmt(v)).join(', ') : `${value.slice(0, 5).map((v) => fmt(v)).join(', ')}, … ${fmt(value[value.length - 1])} (${value.length} values)`
    return <span className="num">{txt}</span>
  }
  if (isObj(value)) {
    const entries = Object.entries(value)
    if (!entries.length) return <span className="muted">empty</span>
    return (
      <dl className={depth ? 'tree nested' : 'tree'}>
        {entries.map(([k, v]) => (
          <div key={k}>
            <dt>{words(k)}</dt>
            <dd><DataTree value={v} depth={depth + 1} /></dd>
          </div>
        ))}
      </dl>
    )
  }
  return <span className={typeof value === 'number' ? 'num' : undefined}>{fmt(value)}</span>
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>
}

export function CandidatesPanel({ pack, selected, onSelect }: { pack: Pack; selected: string | null; onSelect: (c: Candidate) => void }) {
  const cands = pack.meta.candidates ?? []
  const nDet = pack.meta.detections?.length ?? 0
  if (!cands.length)
    return (
      <Empty>
        {nDet
          ? `The pipeline found ${nDet} single-frame detections in this field but linked none of them into a candidate.`
          : 'No candidates in this field yet. When the pipeline has searched the chromatic differences, anything that moves or varies is listed here.'}
      </Empty>
    )
  const extra = [...new Set(cands.flatMap((c) => Object.keys(c)))].filter((k) => ['verdict', 'chance', 'snr'].includes(k))
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Id</th><th>Kind</th>{extra.map((k) => <th key={k}>{words(k)}</th>)}<th>Sightings</th><th>Rate (″/h)</th><th>Direction (°)</th><th>Known object</th><th>Note</th>
          </tr>
        </thead>
        <tbody>
          {cands.map((c) => (
            <tr key={c.id} className={selected === c.id ? 'sel' : undefined}>
              <td><button className="link" onClick={() => onSelect(c)} aria-label={`Show candidate ${c.id}`}>{c.id}</button></td>
              <td><span className="chip" style={{ borderColor: CLASS_COLOURS[c.cls] ?? 'currentColor' }}>{c.cls}</span></td>
              {extra.map((k) => <td key={k} className="num">{fmt(c[k])}</td>)}
              <td className="num">{c.frames.length}</td>
              <td className="num">{fmt(c.rate)}</td>
              <td className="num">{fmt(c.pa)}</td>
              <td>{c.known ?? <span className="muted">no match</span>}</td>
              <td className="note">{c.note ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SciencePanel({ pack, quick }: { pack: Pack; quick: ReactNode }) {
  const sci = pack.meta.science ?? {}
  const keys = Object.keys(sci)
  const titles: Record<string, string> = {
    motion: 'Measured motion against the catalogue',
    lightcurve: 'Light curve at matched wavelength',
  }
  return (
    <div className="stack-gap">
      {keys.map((k) => (
        <section key={k}>
          <h3>{titles[k] ?? words(k)}</h3>
          <DataTree value={sci[k]} />
        </section>
      ))}
      {!keys.length && <Empty>The pipeline has not attached a science measurement to this field yet.</Empty>}
      {quick}
    </div>
  )
}

const MODE_LABEL: Record<string, string> = { naive: 'Naive pair', gated: 'Wavelength-gated pair', corrected: 'Chromatic template', chromatic: 'Chromatic template' }
const MODE_COLOUR: Record<string, string> = { naive: 'var(--m-naive)', gated: 'var(--m-gated)', corrected: 'var(--m-chroma)', chromatic: 'var(--m-chroma)' }

function LedgerCurves({ injection }: { injection: Obj }) {
  const runs = Object.keys(injection).filter((k) => isObj(dig(injection, k, 'modes')))
  const [run, setRun] = useState(runs.includes('atFixedRate') ? 'atFixedRate' : runs[0])
  const modes = (dig(injection, run, 'modes') ?? {}) as Obj
  const first = Object.values(modes).find(isObj) ?? {}
  const kinds = Object.keys(first).filter((k) => isObj(first[k]))
  const [kind, setKind] = useState(kinds[0] ?? '')
  const bgs = Object.keys((first[kind] as Obj) ?? {}).filter((k) => isObj(dig(first, kind, k)))
  const [bg, setBg] = useState(bgs[0] ?? '')
  const [count, setCount] = useState('all')
  const flux = dig(injection, run, 'fluxUJy')
  if (!Array.isArray(flux) || !flux.length || !kinds.length) return null
  const series: Series[] = Object.keys(modes).map((m) => ({
    label: MODE_LABEL[m] ?? m,
    colour: MODE_COLOUR[m] ?? 'currentColor',
    values: ((dig(modes, m, kind, bg, count) as unknown[]) ?? []).map(asNum),
  }))
  const runLabel: Record<string, string> = { atFixedRate: 'Same false-alarm rate for all three', atThreshold5: 'Same 5-sigma threshold for all three' }
  const pickers: [string, string, string[], (v: string) => void, Record<string, string>][] = [
    ['Comparison', run, runs, setRun, runLabel],
    ['Test source', kind, kinds, setKind, { mover: 'appears once (mover)', static: 'stays put (new source)' }],
    ['Placed on', bg, bgs, setBg, { blank: 'blank sky', star: 'top of a star' }],
    ['Counting', count, ['all', 'searchable'], setCount, { all: 'all frames', searchable: 'only frames with a result' }],
  ]
  return (
    <section>
      <h3>How faint a new source each method can find</h3>
      <p className="muted">Artificial point sources were added to the real frames and searched for again. The curves show the fraction found.</p>
      <div className="row wrap">
        {pickers.map(([label, val, opts, set, names]) => (
          <label key={label} className="field">
            <span>{label}</span>
            <select value={val} onChange={(e) => set(e.target.value)}>
              {opts.map((o) => <option key={o} value={o}>{names[o] ?? words(o)}</option>)}
            </select>
          </label>
        ))}
      </div>
      <CompletenessChart flux={flux as number[]} series={series} />
      <ul className="legend">
        {series.map((s) => <li key={s.label}><i style={{ background: s.colour }} />{s.label}</li>)}
      </ul>
    </section>
  )
}

export function LedgerPanel({ pack }: { pack: Pack }) {
  const led = pack.meta.ledger ?? {}
  if (!Object.keys(led).length)
    return <Empty>The three-way comparison (naive pair, gated pair, chromatic template) has not been measured for this field yet. It appears here when the pipeline adds it.</Empty>
  const modes = isObj(led.modes) ? led.modes : {}
  const names = Object.keys(modes)
  const inj = isObj(led.injection) ? led.injection : null
  const f50 = (m: string) => asNum(dig(inj, 'atFixedRate', 'modes', m, 'mover', 'blank', 'f50')) ?? asNum(dig(inj, 'atThreshold5', 'modes', m, 'mover', 'blank', 'f50'))
  const rows: [string, (m: string) => ReactNode][] = [
    ['Frames with a usable difference', (m) => `${fmt(dig(modes, m, 'usableFrames'))} of ${fmt(led.nFrames)} (${fmt((asNum(dig(modes, m, 'usableFraction')) ?? NaN) * 100)}%)`],
    ['False detections per square degree', (m) => fmt(dig(modes, m, 'false', 'perDeg2'))],
    ['False detections per frame', (m) => fmt(dig(modes, m, 'false', 'perFrame'))],
    ['Same, with plain noise only', (m) => fmt(dig(modes, m, 'falsePlain', 'perFrame'))],
    ['Depth, 1 sigma on faint sky (µJy per pixel)', (m) => fmt(dig(modes, m, 'depthUJy', 'faint'))],
    ['Flux found half the time, moving source (µJy)', (m) => fmt(f50(m))],
    ['Known target recovered', (m) => {
      const k = dig(modes, m, 'knownSignal')
      if (!isObj(k) || k.kind == null) return '–'
      return `${fmt(k.recovered)} (5 sigma in ${fmt((asNum(k.fractionAnyLobe5) ?? NaN) * 100)}% of frames)`
    }],
  ]
  const rest = Object.fromEntries(Object.entries(led).filter(([k]) => !['notes'].includes(k)))
  return (
    <div className="stack-gap">
      {names.length > 0 && (
        <section>
          <h3>Three ways to subtract the past, measured on this field</h3>
          <div className="table-wrap">
            <table className="ledger">
              <thead>
                <tr>
                  <th />
                  {names.map((m) => <th key={m}><i className="swatch" style={{ background: MODE_COLOUR[m] ?? 'currentColor' }} />{MODE_LABEL[m] ?? words(m)}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.map(([label, cell]) => (
                  <tr key={label}>
                    <th scope="row">{label}</th>
                    {names.map((m) => <td key={m} className="num">{cell(m)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">
            {led.target ? `Detections within ${fmt(led.excludedRadiusPix)} pixels of ${String(led.target)} are not counted as false. ` : ''}
            Threshold {fmt(led.threshold)} sigma, at least {fmt(led.minAreaPix)} pixels; field area {fmt(led.areaDeg2)} square degrees; template mode: {fmt(led.templateMode)}.
          </p>
        </section>
      )}
      {inj && <LedgerCurves injection={inj} />}
      {Array.isArray(led.notes) && (
        <section>
          <h3>Notes from the pipeline</h3>
          <DataTree value={led.notes} />
        </section>
      )}
      <details>
        <summary>All ledger numbers</summary>
        <DataTree value={rest} />
      </details>
    </div>
  )
}
