/**
 * Client of the optional live engine that builds a field for coordinates outside the
 * precomputed ones. The base URL lives here and nowhere else.
 *   GET  {base}/api/health
 *   POST {base}/api/field   {ra, dec, size_arcmin}  ->  job id
 *   GET  {base}/api/job/<id>  ->  {state, progress, message, key}
 *   packs at {base}/data/<key>/...
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */

export const DEFAULT_ENGINE_URL = 'http://127.0.0.1:8000'
const STORE_KEY = 'parallax.engine'

export interface JobStatus {
  state: string
  progress: number | null
  message: string
  key: string | null
}

/** The engine base URL: explicit override, else the saved one, else the default. */
export function engineBase(override?: string | null): string {
  if (override) return override.replace(/\/+$/, '')
  try {
    const saved = localStorage.getItem(STORE_KEY)
    if (saved) return saved.replace(/\/+$/, '')
  } catch {
    /* storage may be unavailable (embedded, private mode) */
  }
  return DEFAULT_ENGINE_URL
}

export function saveEngineBase(url: string): void {
  try {
    if (url && url !== DEFAULT_ENGINE_URL) localStorage.setItem(STORE_KEY, url)
    else localStorage.removeItem(STORE_KEY)
  } catch {
    /* ignore */
  }
}

export function engineDataBase(base: string): string {
  return `${base}/data`
}

async function withTimeout<T>(ms: number, run: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), ms)
  try {
    return await run(ctl.signal)
  } finally {
    clearTimeout(timer)
  }
}

/** True if an engine answers at `base` within the timeout. Never throws. */
export async function engineHealthy(base: string, timeoutMs = 2500): Promise<boolean> {
  try {
    return await withTimeout(timeoutMs, async (signal) => (await fetch(`${base}/api/health`, { signal })).ok)
  } catch {
    return false
  }
}

/** Normalise whatever the engine returns for a job into a JobStatus. */
export function parseJob(raw: unknown): JobStatus {
  const o = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const p = typeof o.progress === 'number' && Number.isFinite(o.progress) ? o.progress : null
  return {
    state: typeof o.state === 'string' ? o.state.toLowerCase() : 'unknown',
    progress: p === null ? null : Math.min(1, Math.max(0, p > 1 ? p / 100 : p)),
    message: typeof o.message === 'string' ? o.message : '',
    key: typeof o.key === 'string' && o.key ? o.key : null,
  }
}

/** Extract the job id from the POST /api/field reply (a string, or {id | job | job_id}). */
export function parseJobId(raw: unknown): string | null {
  if (typeof raw === 'string' || typeof raw === 'number') return String(raw)
  const o = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  for (const k of ['id', 'job', 'job_id', 'jobId']) {
    const v = o[k]
    if (typeof v === 'string' || typeof v === 'number') return String(v)
  }
  return null
}

export async function submitField(base: string, ra: number, dec: number, sizeArcmin: number): Promise<string> {
  const r = await withTimeout(15000, (signal) =>
    fetch(`${base}/api/field`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ra, dec, size_arcmin: sizeArcmin }),
      signal,
    }),
  )
  if (!r.ok) throw new Error(`The engine refused the request (HTTP ${r.status}).`)
  const id = parseJobId(await r.json())
  if (!id) throw new Error('The engine did not return a job id.')
  return id
}

export async function jobStatus(base: string, id: string): Promise<JobStatus> {
  const r = await withTimeout(15000, (signal) => fetch(`${base}/api/job/${encodeURIComponent(id)}`, { signal }))
  if (!r.ok) throw new Error(`The engine lost the job (HTTP ${r.status}).`)
  return parseJob(await r.json())
}

export const JOB_DONE = ['done', 'finished', 'complete', 'completed', 'success', 'ready']
export const JOB_FAILED = ['error', 'failed', 'failure', 'cancelled', 'canceled']
