/**
 * The application shell: URL-backed view state, loading of the field index and packs,
 * navigation, sharing, theme and the embed mode.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { CoordBox, Home, Resolve } from './components/Home'
import { About, HowItWorks } from './components/Info'
import { Viewer } from './components/Viewer'
import { loadPack } from './lib/decode'
import { engineBase, engineDataBase } from './lib/engine'
import type { Pack, PackIndex } from './lib/types'
import { parseQuery, toQuery, type Page, type ViewState } from './lib/urlstate'

const STATIC_DATA = './data'

type Loaded = { key: string; pack: Pack | null; error: string | null }

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('parallax.theme') === 'light' ? 'light' : 'dark'
    } catch {
      return 'dark'
    }
  })
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('parallax.theme', theme)
    } catch {
      /* ignore */
    }
  }, [theme])
  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}

function Share({ s, onClose }: { s: ViewState; onClose: () => void }) {
  const url = `${location.origin}${location.pathname}?${toQuery(s)}`
  const embed = `<iframe src="${location.origin}${location.pathname}?${toQuery({ ...s, embed: true })}" width="640" height="820" style="border:0" title="ParallaX view" loading="lazy"></iframe>`
  const [done, setDone] = useState('')
  const copy = (text: string, what: string) => {
    const ok = () => setDone(`${what} copied.`)
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(ok, () => setDone('Copying was blocked; select the text and copy it by hand.'))
    else setDone('Select the text and copy it by hand.')
  }
  return (
    <div className="share-pop" role="dialog" aria-label="Share this view">
      <label className="field"><span>Link to exactly this view</span>
        <textarea readOnly rows={2} value={url} onFocus={(e) => e.target.select()} /></label>
      <label className="field"><span>Embed code (picture and player only)</span>
        <textarea readOnly rows={3} value={embed} onFocus={(e) => e.target.select()} /></label>
      <div className="row wrap">
        <button className="btn primary" onClick={() => copy(url, 'Link')}>Copy link</button>
        <button className="btn" onClick={() => copy(embed, 'Embed code')}>Copy embed code</button>
        <button className="btn" onClick={onClose}>Close</button>
        <span className="muted small" role="status">{done}</span>
      </div>
    </div>
  )
}

export default function App() {
  const [s, setS] = useState<ViewState>(() => parseQuery(location.search))
  const update = useCallback((patch: Partial<ViewState>) => setS((prev) => ({ ...prev, ...patch })), [])
  const [index, setIndex] = useState<PackIndex | null>(null)
  const [indexError, setIndexError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [share, setShare] = useState(false)
  const [theme, flipTheme] = useTheme()

  // URL <-> state. A new page or field makes a history entry; everything else replaces it.
  const last = useRef<{ page: Page; field: string | null } | null>(null)
  useEffect(() => {
    const q = toQuery(s)
    const url = q ? `?${q}` : location.pathname
    const prev = last.current
    if (prev && (prev.page !== s.page || prev.field !== s.field)) history.pushState(null, '', url)
    else history.replaceState(null, '', url)
    last.current = { page: s.page, field: s.field }
  }, [s])
  useEffect(() => {
    const pop = () => {
      const next = parseQuery(location.search)
      last.current = { page: next.page, field: next.field }
      setS(next)
    }
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])

  useEffect(() => {
    fetch(`${STATIC_DATA}/index.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: PackIndex) => setIndex({ ...j, fields: Array.isArray(j.fields) ? j.fields : [] }))
      .catch((e: Error) => {
        setIndexError(e.message)
        setIndex({ fields: [] })
      })
  }, [])

  const key = s.field
  const inStatic = !!index?.fields.some((f) => f.key === key)
  useEffect(() => {
    if (!key || !index) return
    const ctl = new AbortController()
    const base = inStatic ? STATIC_DATA : engineDataBase(engineBase(s.engine))
    loadPack(base, key, ctl.signal)
      .then((pack) => setLoaded({ key, pack, error: null }))
      .catch((e: Error) => {
        if (ctl.signal.aborted) return
        const why = inStatic ? e.message : `"${key}" is not one of the precomputed fields, and the live engine did not provide it (${e.message}).`
        setLoaded({ key, pack: null, error: why })
      })
    return () => ctl.abort()
  }, [key, index, inStatic, s.engine])

  const go = (page: Page) => {
    setShare(false)
    if (page === 'home') {
      setNotice(null)
      update({ page, field: null, ra: null, dec: null })
    } else if (page === 'view') update({ page })
    else update({ page })
  }
  const current = loaded && loaded.key === key ? loaded : null
  const pack = current?.pack ?? null
  const dois = pack?.meta.release?.doi ?? []
  const viewing = s.page === 'view'

  let body
  if (s.page === 'how') body = <HowItWorks />
  else if (s.page === 'about') body = <About index={index} dois={dois.length ? dois : ['10.26131/IRSA678']} />
  else if (viewing && key) {
    if (pack) body = <Viewer key={pack.meta.key + pack.base} pack={pack} s={s} update={update} notice={notice} />
    else if (current?.error)
      body = (
        <div className="resolve">
          <h1>This field could not be opened</h1>
          <p role="alert">{current.error}</p>
          <p><button className="btn" onClick={() => go('home')}>Back to all fields</button></p>
        </div>
      )
    else body = <div className="resolve"><p role="status">Loading the field.</p><div className="bar busy"><i /></div></div>
  } else if (viewing && s.ra !== null && s.dec !== null) {
    body = index ? <Resolve index={index} s={s} update={update} onNotice={setNotice} /> : <div className="resolve"><p role="status">Loading the list of fields.</p></div>
  } else body = <Home index={index} indexError={indexError} update={update} />

  if (s.embed)
    return (
      <div className="shell">
        <main id="main">{body}</main>
        <p className="embed-foot">
          <a href={`?${toQuery({ ...s, embed: false })}`} target="_blank" rel="noreferrer">Open in ParallaX</a>. SPHEREx data via IRSA. Not affiliated with or endorsed by NASA.
        </p>
      </div>
    )

  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to the content</a>
      <header className="top">
        <button className="brand" onClick={() => go('home')} aria-label="ParallaX, all fields">
          <svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="12" cy="18" r="6" fill="none" stroke="var(--pass2)" strokeWidth="2.5" /><circle cx="19.5" cy="12.5" r="6" fill="var(--accent)" /></svg>
          ParallaX
        </button>
        {s.page !== 'home' && <CoordBox index={index} update={update} />}
        <nav aria-label="Pages">
          <button className={s.page === 'home' ? 'navlink on' : 'navlink'} onClick={() => go('home')}>Fields</button>
          <button className={s.page === 'how' ? 'navlink on' : 'navlink'} onClick={() => go('how')}>How it works</button>
          <button className={s.page === 'about' ? 'navlink on' : 'navlink'} onClick={() => go('about')}>About and credits</button>
          {(s.page === 'how' || s.page === 'about') && key && <button className="navlink" onClick={() => go('view')}>Back to {pack?.meta.name ?? 'the field'}</button>}
          {viewing && pack && <button className="btn" onClick={() => setShare((v) => !v)} aria-expanded={share}>Share</button>}
          <button className="btn" onClick={flipTheme} aria-label={`Switch to the ${theme === 'dark' ? 'light' : 'dark'} theme`}>{theme === 'dark' ? 'Light' : 'Dark'}</button>
        </nav>
        {share && <Share s={s} onClose={() => setShare(false)} />}
      </header>
      <main id="main">{body}</main>
      <footer>
        <span><strong>Not affiliated with or endorsed by NASA.</strong></span>
        <span>SPHEREx data from the NASA/IPAC Infrared Science Archive. Team ZENITH LABS, NASA Space Apps Challenge 2026, Beirut.</span>
        <span>Code under Apache-2.0.</span>
      </footer>
    </div>
  )
}
