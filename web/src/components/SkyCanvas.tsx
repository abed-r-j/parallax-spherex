/**
 * One sky picture: a canvas (north up, east left) with an SVG overlay in the same frame.
 * The backing store is an integer multiple of the visible pixels so that pixel-perfect
 * mode stays crisp at any zoom.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { useEffect, useRef, type PointerEvent, type ReactNode } from 'react'

/** An m x m RGBA picture, row 0 = north. */
export interface Raster {
  rgba: Uint8ClampedArray<ArrayBuffer>
  m: number
}

/** The visible window in pixel-centre coordinates: [cx - half, cx + half] x [cy - half, cy + half]. */
export interface View {
  cx: number
  cy: number
  half: number
}

export interface PixelPos {
  x: number
  y: number
}

/** Map a pack pixel position to the 1000-unit overlay square. */
export function toOverlay(view: View, x: number, y: number): [number, number] {
  return [((x - (view.cx - view.half)) / (2 * view.half)) * 1000, ((view.cy + view.half - y) / (2 * view.half)) * 1000]
}

function toCanvas(r: Raster): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = r.m
  c.height = r.m
  c.getContext('2d')!.putImageData(new ImageData(r.rgba, r.m, r.m), 0, 0)
  return c
}

function blit(ctx: CanvasRenderingContext2D, r: Raster, n: number, view: View, W: number, smooth: boolean): void {
  const f = r.m / n
  const sw = 2 * view.half * f
  const sx0 = (view.cx - view.half + 0.5) * f
  const sy0 = (n - 0.5 - (view.cy + view.half)) * f
  const x0 = Math.max(0, sx0)
  const x1 = Math.min(r.m, sx0 + sw)
  const y0 = Math.max(0, sy0)
  const y1 = Math.min(r.m, sy0 + sw)
  if (x1 <= x0 || y1 <= y0) return
  ctx.imageSmoothingEnabled = smooth
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(toCanvas(r), x0, y0, x1 - x0, y1 - y0, ((x0 - sx0) / sw) * W, ((y0 - sy0) / sw) * W, ((x1 - x0) / sw) * W, ((y1 - y0) / sw) * W)
}

interface Props {
  n: number
  base: Raster | null
  over?: Raster | null
  view: View
  smooth: boolean
  label: string
  message?: string
  onHover?: (p: PixelPos | null) => void
  onPick?: (p: PixelPos) => void
  children?: ReactNode
}

export function SkyCanvas({ n, base, over, view, smooth, label, message, onHover, onPick, children }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)
  const vis = Math.max(1, Math.round(2 * view.half))
  const W = Math.ceil(880 / vis) * vis

  useEffect(() => {
    const cnv = ref.current
    if (!cnv) return
    const ctx = cnv.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, W, W)
    if (base) blit(ctx, base, n, view, W, smooth)
    if (over) blit(ctx, over, n, view, W, false)
  }, [base, over, n, view, W, smooth])

  const at = (e: PointerEvent): PixelPos | null => {
    const r = e.currentTarget.getBoundingClientRect()
    const x = Math.round(view.cx - view.half + ((e.clientX - r.left) / r.width) * 2 * view.half)
    const y = Math.round(view.cy + view.half - ((e.clientY - r.top) / r.height) * 2 * view.half)
    return x >= 0 && y >= 0 && x < n && y < n ? { x, y } : null
  }

  return (
    <div className="sky">
      <canvas
        ref={ref}
        width={W}
        height={W}
        role="img"
        aria-label={label}
        className={onPick ? 'pickable' : undefined}
        onPointerMove={onHover ? (e) => onHover(at(e)) : undefined}
        onPointerLeave={onHover ? () => onHover(null) : undefined}
        onClick={
          onPick
            ? (e) => {
                const p = at(e as unknown as PointerEvent)
                if (p) onPick(p)
              }
            : undefined
        }
      />
      <svg className="sky-ov" viewBox="0 0 1000 1000" aria-hidden="true">
        {children}
      </svg>
      {message && (
        <div className="sky-msg" role="status">
          <p>{message}</p>
        </div>
      )}
    </div>
  )
}
