// Builds the project-page media kit in submission/media/ from the REAL ParallaX web app
// (the built site in web/dist, served locally) with headless Chrome and ffmpeg.
//
//   node submission/make_media.mjs            (from the repository root; needs web/dist)
//
// Every picture is a screen capture of the running app showing real SPHEREx data, or a copy
// of a plot/screenshot already in the repository. Nothing here is made by an SI image or
// video generator. Needs no network.
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { mkdir, rm, copyFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { serve, open } from '../presentation/video/lib.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const out = join(here, 'media')
const tmp = join(out, '_frames')
await mkdir(out, { recursive: true })
const { server, origin } = await serve(resolve(root, 'web', 'dist'))
const { browser } = await open()
const VIEW = { width: 1600, height: 900 }

async function newPage(scale, view = VIEW) {
  const ctx = await browser.newContext({ viewport: view, deviceScaleFactor: scale })
  const page = await ctx.newPage()
  page.on('pageerror', (e) => console.log('pageerror:', e.message))
  return page
}
async function go(page, query) {
  await page.goto(`${origin}/${query}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(600)
}
const label = (page) => page.locator('.frame-label').innerText().then((t) => t.replace(/\s+/g, ' '))
/** Page rectangle covering the date/detector label and the sky picture, with a small margin. */
async function pictureClip(page, pad = 10) {
  return page.evaluate((p) => {
    const a = document.querySelector('.frame-label').getBoundingClientRect()
    const b = document.querySelector('.sky canvas').getBoundingClientRect()
    const x = Math.min(a.left, b.left) - p + scrollX
    const y = a.top - 4 + scrollY // a small top margin only: the play buttons sit just above
    return { x, y, width: Math.max(a.right, b.right) - Math.min(a.left, b.left) + 2 * p, height: b.bottom - a.top + 4 + p }
  }, pad)
}
function gif(dir, fps, name, width) {
  const vf = `scale=${width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=255:stats_mode=full[p];[b][p]paletteuse=dither=sierra2_4a`
  const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(fps), '-i', 'f%03d.png', '-filter_complex', vf, '-loop', '0', join(out, name)], { cwd: dir, encoding: 'utf8' })
  if (r.status !== 0) throw new Error('ffmpeg: ' + r.stderr)
}
/** Step through `n` frames of the app with the right-arrow key; one screenshot each (`repeat` copies). */
async function sequence(page, name, n, repeat = 1) {
  const dir = join(tmp, name)
  await rm(dir, { recursive: true, force: true })
  await mkdir(dir, { recursive: true })
  const clip = await pictureClip(page)
  let k = 0
  for (let i = 0; i < n; i++) {
    if (i) { await page.keyboard.press('ArrowRight'); await page.waitForTimeout(120) }
    const file = join(dir, `f${String(k++).padStart(3, '0')}.png`)
    await page.screenshot({ path: file, clip, fullPage: true })
    for (let j = 1; j < repeat; j++) await copyFile(file, join(dir, `f${String(k++).padStart(3, '0')}.png`))
    console.log(`  ${name} ${i + 1}/${n}: ${await label(page)}`)
  }
  return dir
}

try {
  // 01 hero: the three-way view on Barnard's Star, 1600 px wide
  let page = await newPage(1)
  await go(page, '?field=barnard&mode=compare&seq=frames&frame=100')
  await page.screenshot({ path: join(out, '01_hero.png') })
  console.log('01', await label(page))
  await page.context().close()

  // 04 three-way panels only, 06 time x wavelength map
  page = await newPage(2)
  await go(page, '?field=barnard&mode=compare&seq=frames&frame=100')
  const clip4 = await page.evaluate(() => {
    const a = document.querySelector('.frame-label').getBoundingClientRect()
    const b = document.querySelector('.trio').getBoundingClientRect()
    return { x: b.left - 12, y: a.top - 4 + scrollY, width: b.width + 24, height: b.bottom - a.top + 16 }
  })
  await page.screenshot({ path: join(out, '04_three_way.png'), clip: clip4, fullPage: true })
  console.log('04', (await page.locator('.trio').innerText()).replace(/\s+/g, ' '))
  await page.locator('.card', { hasText: 'When and at what colour' }).first().screenshot({ path: join(out, '06_time_wavelength.png') })
  await page.context().close()

  // 05 spectrum after clicking a star (RW Aurigae field), 1600 px wide
  page = await newPage(1, { width: 1600, height: 1000 })
  await go(page, '?field=rwaur&seq=frames&frame=100')
  const b = await page.locator('.sky canvas').first().boundingBox()
  await page.mouse.click(b.x + b.width * 0.325, b.y + b.height * 0.765)
  await page.waitForTimeout(600)
  await page.mouse.move(1500, 80)
  await page.evaluate(() => window.scrollTo(0, 150))
  await page.waitForTimeout(300)
  await page.screenshot({ path: join(out, '05_spectrum_on_click.png') })
  console.log('05', page.url().split('?')[1])
  await page.context().close()

  // 02 Barnard's Star: blink of the three survey passes (one detector), looping
  page = await newPage(1.6)
  await go(page, '?field=barnard&seq=passes&fov=2&det=3')
  gif(await sequence(page, 'barnard', 3, 1), 1.5, '02_little_video_barnard.gif', 900)
  // 03 asteroid (52) Europa crossing its field under the known-object label
  await go(page, '?field=europa52&seq=frames&frame=10&ov=target,sso')
  gif(await sequence(page, 'europa', 24, 1), 4, '03_asteroid_europa.gif', 900)
  await page.context().close()

  // 08: an existing real screenshot of a live in-browser field (taken with the network on)
  await copyFile(join(root, 'docs', 'img', 'live-m51.png'), join(out, '08_live_fetch.png'))
} finally {
  await browser.close()
  server.close()
  await rm(tmp, { recursive: true, force: true })
}
console.log('done ->', out)
