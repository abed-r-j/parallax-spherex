// Shared helpers for the ParallaX screen captures: a static server for the built site,
// headless Chrome through playwright-core, a drawn mouse pointer, and a recorder that saves
// a screenshot sequence with per-frame durations and encodes it with ffmpeg
// (constant 30 frames per second, 1920x1080, H.264, no audio).
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { createServer } from 'node:http'
import { readFile, mkdir, writeFile, rm } from 'node:fs/promises'
import { extname, join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { chromium } from 'playwright-core'

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.woff': 'font/woff', '.bin': 'application/octet-stream' }

export async function serve(dist) {
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url, 'http://x').pathname)
    const file = join(dist, path.endsWith('/') ? path + 'index.html' : path)
    try {
      if (!file.startsWith(dist)) throw new Error('outside')
      const body = await readFile(file)
      res.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream' })
      res.end(body)
    } catch {
      res.writeHead(404)
      res.end('not found')
    }
  })
  await new Promise((r) => server.listen(0, '127.0.0.1', r))
  return { server, origin: `http://127.0.0.1:${server.address().port}` }
}

// 1600x900 CSS pixels at 1.2x = 1920x1080 image pixels: the whole viewer fits and the text stays readable.
export const VIEW = { width: 1600, height: 900 }
export const SCALE = 1.2
export const FPS = 30

export async function open() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  const ctx = await browser.newContext({ viewport: VIEW, deviceScaleFactor: SCALE })
  return { browser, ctx }
}

/** A drawn pointer, because headless Chrome shows none. It follows the real mouse events. */
export async function addPointer(page) {
  await page.addInitScript(() => {
    const make = () => {
      if (document.getElementById('__ptr')) return
      const d = document.createElement('div')
      d.id = '__ptr'
      d.innerHTML = '<svg width="22" height="30" viewBox="0 0 22 30"><path d="M2 2 L2 23 L7.5 18 L11.5 27 L15 25.5 L11 16.5 L18.5 16.5 Z" fill="#ffffff" stroke="#10161f" stroke-width="1.6" stroke-linejoin="round"/></svg>'
      d.style.cssText = 'position:fixed;left:-50px;top:-50px;z-index:2147483647;pointer-events:none;filter:drop-shadow(0 1px 2px rgba(0,0,0,.6))'
      document.documentElement.appendChild(d)
      window.addEventListener('mousemove', (e) => { d.style.left = e.clientX - 2 + 'px'; d.style.top = e.clientY - 2 + 'px' }, true)
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', make)
    else make()
  })
}

export class Recorder {
  constructor(page, dir, name) {
    this.page = page
    this.dir = join(dir, '_frames', name)
    this.out = join(dir, `${name}.mp4`)
    this.name = name
    this.items = [] // [file, frames]
    this.mouse = [VIEW.width / 2, VIEW.height / 2]
  }
  async start() {
    await rm(this.dir, { recursive: true, force: true })
    await mkdir(this.dir, { recursive: true })
  }
  /** Take one screenshot and show it for `frames` video frames. */
  async hold(frames = 1) {
    const file = `f${String(this.items.length).padStart(5, '0')}.png`
    await this.page.screenshot({ path: join(this.dir, file) })
    this.items.push([file, Math.max(1, Math.round(frames))])
  }
  async holdSec(seconds) { await this.hold(seconds * FPS) }
  /** Move the pointer smoothly to (x, y) in CSS pixels over `seconds`. */
  async moveTo(x, y, seconds = 0.6) {
    const steps = Math.max(2, Math.round((seconds * FPS) / 2))
    const [x0, y0] = this.mouse
    for (let i = 1; i <= steps; i++) {
      const t = i / steps
      const e = t * t * (3 - 2 * t)
      await this.page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
      await this.hold(2)
    }
    this.mouse = [x, y]
  }
  async moveToLocator(loc, seconds = 0.6, fx = 0.5, fy = 0.5) {
    const b = await loc.boundingBox()
    await this.moveTo(b.x + b.width * fx, b.y + b.height * fy, seconds)
    return b
  }
  async click() { await this.page.mouse.click(this.mouse[0], this.mouse[1]) }
  /** Type text one character at a time, about 11 characters per second. */
  async type(text, framesPerChar = 3) {
    for (const ch of text) {
      await this.page.keyboard.type(ch)
      await this.hold(framesPerChar)
    }
  }
  /** Real-time capture: screenshot as fast as possible until `until()` is true; durations are the real elapsed times. */
  async live(until, maxSeconds = 120, speed = 1) {
    const t0 = Date.now()
    let last = t0
    for (;;) {
      const file = `f${String(this.items.length).padStart(5, '0')}.png`
      await this.page.screenshot({ path: join(this.dir, file) })
      const now = Date.now()
      this.items.push([file, Math.max(1, Math.round((((now - last) / 1000) * FPS) / speed))])
      last = now
      if (await until()) break
      if ((now - t0) / 1000 > maxSeconds) break
    }
    return (Date.now() - t0) / 1000
  }
  async finish() {
    const list = this.items.map(([f, n]) => `file '${f}'\nduration ${(n / FPS).toFixed(6)}`).join('\n') + `\nfile '${this.items.at(-1)[0]}'\n`
    await writeFile(join(this.dir, 'list.txt'), list)
    const frames = this.items.reduce((a, [, n]) => a + n, 0)
    const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-vf', `fps=${FPS},scale=1920:1080:flags=lanczos,format=yuv420p`, '-frames:v', String(frames), '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-movflags', '+faststart', '-an',
      '-metadata', 'title=ParallaX screen capture: ' + this.name, '-metadata', 'comment=Scripted capture of the real ParallaX web app (no SI-generated imagery). Team ZENITH LABS.', this.out], { cwd: this.dir, encoding: 'utf8' })
    if (r.status !== 0) throw new Error(`ffmpeg failed for ${this.name}: ${r.stderr}`)
    console.log(`${this.name}.mp4  ${frames} frames  ${(frames / FPS).toFixed(2)} s  (${this.items.length} screenshots)`)
    return frames / FPS
  }
}
