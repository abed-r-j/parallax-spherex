/**
 * Session store of live fields: one job per request, kept in memory so that a finished
 * field opens at once when it is asked for again, and a running one keeps running while
 * the reader looks at another page. Starting a new request cancels the others, to stay
 * gentle with the public archive.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { buildLiveField, liveKey, normaliseSpec, type LiveProgress, type LiveSpec } from './live'
import type { Pack } from './types'

export type LiveState = 'running' | 'done' | 'failed' | 'cancelled'
export type Thumb = NonNullable<LiveProgress['last']>

export interface LiveJob {
  key: string
  spec: LiveSpec
  state: LiveState
  progress: LiveProgress | null
  /** the newest picture of the field: a snapshot while running, the full field when done */
  pack: Pack | null
  error: string | null
  /** the most recent frames, newest last, for the progress panel */
  thumbs: Thumb[]
  /** changes whenever anything above changes */
  version: number
  controller: AbortController
  listeners: Set<() => void>
}

const jobs = new Map<string, LiveJob>()
const KEEP = 4

function touch(job: LiveJob): void {
  job.version++
  for (const fn of job.listeners) fn()
}

/** The job for a request: the running or finished one if it exists, otherwise a new one. */
export function startLive(request: Partial<LiveSpec> & { ra: number; dec: number }, restart = false): LiveJob {
  const spec = normaliseSpec(request)
  const key = liveKey(spec)
  const old = jobs.get(key)
  if (old && (old.state === 'running' || old.state === 'done' || !restart)) return old
  for (const other of jobs.values()) if (other.state === 'running') cancelLive(other.key)
  const job: LiveJob = {
    key, spec, state: 'running', progress: null, pack: null, error: null, thumbs: [], version: 0,
    controller: new AbortController(), listeners: new Set(),
  }
  jobs.delete(key)
  jobs.set(key, job)
  // bound the memory: forget the oldest finished fields
  for (const [k, j] of jobs) {
    if (jobs.size <= KEEP) break
    if (j.state !== 'running' && k !== key) jobs.delete(k)
  }
  buildLiveField({
    ...spec,
    signal: job.controller.signal,
    onProgress: (p) => {
      if (job.state !== 'running') return
      if (p.last && p.last !== job.progress?.last) job.thumbs = [...job.thumbs.slice(-11), p.last]
      job.progress = p
      if (p.pack) job.pack = p.pack
      touch(job)
    },
  }).then(
    (r) => {
      job.state = 'done'
      job.pack = r.pack
      touch(job)
    },
    (e: unknown) => {
      if (job.state !== 'running') return
      const aborted = e instanceof DOMException && e.name === 'AbortError'
      job.state = aborted ? 'cancelled' : 'failed'
      job.error = aborted ? null : e instanceof Error ? e.message : String(e)
      touch(job)
    },
  )
  return job
}

/** Stop a running job. What it has fetched so far stays visible. */
export function cancelLive(key: string): void {
  const job = jobs.get(key)
  if (!job || job.state !== 'running') return
  job.state = 'cancelled'
  job.controller.abort()
  touch(job)
}

export function subscribeLive(job: LiveJob, fn: () => void): () => void {
  job.listeners.add(fn)
  return () => job.listeners.delete(fn)
}
