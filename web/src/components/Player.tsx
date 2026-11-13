/**
 * The blink player: play / pause, step, speed, loop and a scrubber over the current
 * sequence, with keyboard shortcuts handled by the viewer.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { useEffect, useRef } from 'react'

interface Props {
  length: number
  pos: number
  playing: boolean
  fps: number
  loop: boolean
  label: string
  disabled?: boolean
  onPos: (p: number) => void
  onPlaying: (p: boolean) => void
  onFps: (f: number) => void
  onLoop: (l: boolean) => void
}

export const SPEEDS = [0.5, 1, 2, 4, 8, 15, 30]

export function Player({ length, pos, playing, fps, loop, label, disabled, onPos, onPlaying, onFps, onLoop }: Props) {
  const tick = useRef<() => void>(() => {})
  useEffect(() => {
    tick.current = () => {
      if (pos + 1 < length) onPos(pos + 1)
      else if (loop && length > 1) onPos(0)
      else onPlaying(false)
    }
  })
  useEffect(() => {
    if (!playing || disabled || length < 2) return
    const id = setInterval(() => tick.current(), 1000 / fps)
    return () => clearInterval(id)
  }, [playing, fps, disabled, length])

  const step = (d: number) => {
    onPlaying(false)
    onPos(loop ? (pos + d + length) % length : Math.min(length - 1, Math.max(0, pos + d)))
  }
  const off = disabled || length < 2
  return (
    <div className="player" role="group" aria-label="Blink player">
      <button className="btn icon" onClick={() => step(-1)} disabled={off} aria-label="Previous" title="Previous (left arrow)">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M13 4l-7 6 7 6zM5 4v12" /></svg>
      </button>
      <button className="btn icon primary" onClick={() => onPlaying(!playing)} disabled={off} aria-label={playing ? 'Pause' : 'Play'} title="Play or pause (space)">
        <svg viewBox="0 0 20 20" aria-hidden="true">{playing ? <path d="M6 4v12M14 4v12" /> : <path d="M6 4l10 6-10 6z" className="solid" />}</svg>
      </button>
      <button className="btn icon" onClick={() => step(1)} disabled={off} aria-label="Next" title="Next (right arrow)">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 4l7 6-7 6zM15 4v12" /></svg>
      </button>
      <input
        className="scrub"
        type="range"
        min={0}
        max={Math.max(0, length - 1)}
        value={Math.min(pos, Math.max(0, length - 1))}
        disabled={off}
        aria-label="Position in the sequence"
        aria-valuetext={label}
        onChange={(e) => {
          onPlaying(false)
          onPos(Number(e.target.value))
        }}
      />
      <span className="count num">{length ? pos + 1 : 0} / {length}</span>
      <label className="field inline">
        <span>Speed</span>
        <select value={fps} onChange={(e) => onFps(Number(e.target.value))} title="Frames per second ([ and ])">
          {SPEEDS.map((v) => <option key={v} value={v}>{v} per second</option>)}
        </select>
      </label>
      <label className="check" title="Loop (L)">
        <input type="checkbox" checked={loop} onChange={(e) => onLoop(e.target.checked)} />
        <span>Loop</span>
      </label>
    </div>
  )
}
