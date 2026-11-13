// Scripted screen captures of the REAL ParallaX web app, for the two videos and the slides.
//
//   node video/capture.mjs [site-dir] [filter]
//
// site-dir: a built copy of the web app (default ../web/dist, made by "npm run build" in web/).
// filter:   parts of shot names, comma-separated (for example "blink,live"), "stills" for the slide
//           screenshots only, or nothing for everything.
//
// Each shot drives the app in headless Chrome (playwright-core, channel "chrome"), saves a
// screenshot sequence to video/_frames/<shot>/ and encodes it with ffmpeg to
// video/<shot>.mp4: silent, 1920x1080, 30 frames per second. Playwright's recordVideo is not used.
// Only shot_11_live_fetch needs the network (it reads the public SPHEREx archive bucket).
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'
import { serve, open, addPointer, Recorder, VIEW } from './lib.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const dist = resolve(process.argv[2] ?? join(here, '..', '..', 'web', 'dist'))
const filter = process.argv[3] ?? ''
const assets = resolve(here, '..', 'assets')
const { server, origin } = await serve(dist)
const { browser, ctx } = await open()
const lengths = {}

async function go(page, query) {
  await page.goto(`${origin}/${query}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(500)
}
/** Scroll just enough for the whole sky picture to be on screen. */
async function frameCanvas(page, bottomAt = VIEW.height - 24) {
  const b = await page.locator('.sky canvas').first().boundingBox()
  let y = Math.max(0, Math.round(b.y + b.height - bottomAt))
  // never leave a sliver of the page header at the top
  if (y > 0) y = Math.max(y, await page.evaluate(() => (document.querySelector('header')?.offsetHeight ?? 70) + 2))
  await page.evaluate((v) => window.scrollTo(0, v), y)
  await page.waitForTimeout(200)
}
async function step(page, rec, n, hold, key = 'ArrowRight') {
  for (let i = 0; i < n; i++) {
    await page.keyboard.press(key)
    await page.waitForTimeout(60)
    await rec.hold(hold)
  }
}
const label = (page) => page.locator('.frame-label').innerText().then((t) => t.replace(/\s+/g, ' '))

const SHOTS = {
  // Typing the challenge coordinates of WISE 0855-0714 and landing on the field.
  async shot_01_type_coordinates(page, rec) {
    await go(page, '')
    await page.mouse.move(820, 560)
    rec.mouse = [820, 560]
    await rec.hold(20)
    const box = page.getByRole('searchbox')
    await rec.moveToLocator(box, 0.8, 0.3, 0.5)
    await rec.click()
    await rec.hold(8)
    await rec.type('08 55 10.83 -07 14 42.5')
    await rec.hold(14)
    await page.keyboard.press('Enter')
    await page.waitForSelector('.viewer', { timeout: 20000 })
    await page.waitForTimeout(700)
    await rec.hold(40)
    await frameCanvas(page)
    await rec.hold(20)
    await step(page, rec, 6, 10)
    await rec.hold(40)
    console.log('  landed on', page.url().split('?')[1], '|', await label(page))
  },
  // Barnard's Star: blink of the three survey passes, one detector, smooth 4x display.
  async shot_02_blink_barnard(page, rec) {
    await go(page, '?field=barnard&seq=passes&fov=2&det=3')
    await frameCanvas(page)
    await rec.hold(24)
    await step(page, rec, 20, 12)
    console.log('  ', await label(page))
  },
  // The time x wavelength map: every frame at another wavelength.
  async shot_03_time_wavelength(page, rec) {
    await go(page, '?field=barnard&seq=frames')
    await frameCanvas(page)
    await rec.hold(24)
    await step(page, rec, 84, 3)
    await rec.hold(24)
    console.log('  ', await label(page))
  },
  // The naive pair difference: stars light up as false alarms.
  async shot_04_naive_false_alarms(page, rec) {
    await go(page, '?field=barnard&mode=naive&seq=frames&frame=92')
    await frameCanvas(page)
    await rec.hold(20)
    await step(page, rec, 8, 12)
    await rec.hold(36)
    await step(page, rec, 8, 12)
    console.log('  ', await label(page))
  },
  // The same frame differenced three ways.
  async shot_05_three_way(page, rec) {
    await go(page, '?field=barnard&mode=compare&seq=frames&frame=95')
    await rec.hold(24)
    await step(page, rec, 5, 16)
    await rec.hold(60) // frame 101 of 357: naive halo, clean template
    await step(page, rec, 6, 16)
    console.log('  ', await label(page))
  },
  // The chromatic difference alone.
  async shot_06_chromatic(page, rec) {
    await go(page, '?field=barnard&mode=chroma&seq=frames&frame=92')
    await frameCanvas(page)
    await rec.hold(20)
    await step(page, rec, 16, 12)
    console.log('  ', await label(page))
  },
  // Click a star, get its spectrum.
  async shot_07_click_spectrum(page, rec) {
    await go(page, '?field=rwaur&seq=frames&frame=100')
    await page.evaluate(() => window.scrollTo(0, 290))
    await page.waitForTimeout(200)
    await page.mouse.move(900, 300)
    rec.mouse = [900, 300]
    await rec.hold(20)
    const canvas = page.locator('.sky canvas').first()
    await rec.moveToLocator(canvas, 0.8, 0.325, 0.765)
    await rec.click()
    await page.waitForTimeout(400)
    await rec.hold(70)
    console.log('  picked', page.url().split('?')[1])
    await rec.moveTo(1120, 400, 0.9) // point at the spectrum
    await rec.hold(70)
  },
  // Per-pass stacks subtracted: a star that moved shows a bright and a dark lobe.
  async shot_08_subtract_passes(page, rec) {
    await go(page, '?field=barnard&mode=sub&fov=2')
    await frameCanvas(page)
    await page.mouse.move(900, 300)
    rec.mouse = [900, 300]
    await rec.hold(30)
    await rec.moveToLocator(page.locator('.sky canvas').first(), 1.0, 0.62, 0.62)
    await rec.hold(90)
    console.log('  ', await label(page))
  },
  // The ledger tab: the three-way numbers for this field.
  async shot_09_ledger(page, rec) {
    await go(page, '?field=barnard&mode=compare&seq=frames&frame=100')
    await page.mouse.move(1000, 420)
    rec.mouse = [1000, 420]
    await rec.hold(20)
    await rec.moveToLocator(page.getByRole('tab', { name: 'Ledger' }), 0.7)
    await rec.click()
    await page.waitForTimeout(300)
    await rec.hold(20)
    for (let y = 0; y <= 600; y += 12) {
      await page.evaluate((v) => window.scrollTo(0, v), y)
      await rec.hold(2)
    }
    await rec.hold(110)
  },
  // WISE 0855-0714, detector 6: blink of the three survey passes.
  async shot_10_wise0855_blink(page, rec) {
    await go(page, '?field=wise0855&seq=passes&det=6&fov=4')
    await frameCanvas(page)
    await rec.hold(24)
    await step(page, rec, 15, 14)
    console.log('  ', await label(page))
  },
  // Asteroid (52) Europa crossing a fixed field on 2025-08-20/21, under its known-object label
  // (JPL Horizons as seen from SPHEREx); frames 11 to 34 of 111, detectors 3 and 6.
  async shot_12_asteroid_europa(page, rec) {
    await go(page, '?field=europa52&seq=frames&frame=10&ov=target,sso')
    await frameCanvas(page)
    await rec.hold(30)
    await step(page, rec, 23, 9)
    await rec.hold(30)
    console.log('  ', await label(page))
  },
  // Pluto drifting 12 pixels in 6.4 days (4 to 10 October 2025), detector 2; frames 1 to 18 of 46.
  async shot_13_pluto(page, rec) {
    await go(page, '?field=pluto&seq=frames&frame=0&ov=target,sso')
    await frameCanvas(page)
    await rec.hold(30)
    await step(page, rec, 17, 10)
    await rec.hold(20)
    await step(page, rec, 17, 6, 'ArrowLeft')
    await rec.hold(20)
    console.log('  ', await label(page))
  },
  // Live: a position outside the precomputed fields (M51), fetched in the browser from the
  // public archive. Real network; captured in real time.
  async shot_11_live_fetch(page, rec) {
    await go(page, '')
    await page.mouse.move(820, 560)
    rec.mouse = [820, 560]
    await rec.hold(15)
    await rec.moveToLocator(page.getByRole('searchbox'), 0.7, 0.3, 0.5)
    await rec.click()
    await rec.type('13 29 52.7 +47 11 43')
    await rec.hold(10)
    await page.keyboard.press('Enter')
    await page.waitForSelector('.live-offer', { timeout: 30000 })
    await page.waitForTimeout(3200) // the optional engine check gives up after 2.5 s
    await rec.hold(50)
    // choose one detector (D3) to keep the download small
    for (const d of ['D2', 'D5', 'D3']) {
      await rec.moveToLocator(page.locator('.live-offer label', { hasText: new RegExp(`^${d},`) }).locator('input'), 0.45)
      await rec.click()
      await page.waitForTimeout(150)
      await rec.hold(10)
    }
    const fetchBtn = page.getByRole('button', { name: /^Fetch \d+ images? live$/ })
    console.log('  button:', await fetchBtn.innerText())
    await rec.moveToLocator(fetchBtn, 0.5)
    await rec.hold(20)
    await rec.click()
    const seconds = await rec.live(async () => (await page.locator('.viewer').count()) > 0 && (await page.locator('[role=progressbar]').count()) === 0, 240)
    console.log(`  live fetch took ${seconds.toFixed(1)} s on this connection (real time in the clip)`)
    await page.waitForTimeout(600)
    await rec.hold(50)
    await step(page, rec, 12, 8)
    await rec.hold(40)
    console.log('  ', page.url().split('?')[1], '|', await label(page))
  },
}

async function stills() {
  await mkdir(assets, { recursive: true })
  const c2 = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 2 })
  const page = await c2.newPage()
  const shot = (name) => page.screenshot({ path: join(assets, name) })
  await go(page, '')
  await shot('app_home.png')
  await go(page, '?field=barnard&mode=compare&seq=frames&frame=100')
  await shot('app_threeway.png')
  const figs = page.locator('.trio figure')
  await figs.nth(0).locator('canvas').first().screenshot({ path: join(assets, 'diff_naive.png') })
  await figs.nth(1).locator('canvas').first().screenshot({ path: join(assets, 'diff_gated.png') })
  await figs.nth(2).locator('canvas').first().screenshot({ path: join(assets, 'diff_chromatic.png') })
  const caption = (await page.locator('.trio').innerText()).replace(/\s+/g, ' ')
  const lab = await label(page)
  await page.locator('.card', { hasText: 'When and at what colour' }).first().screenshot({ path: join(assets, 'time_wavelength.png') })
  await go(page, '?field=barnard&seq=frames&frame=100')
  await page.locator('.sky canvas').first().screenshot({ path: join(assets, 'frame_image.png') })
  await go(page, '?field=barnard&seq=passes&fov=2&det=3')
  await frameCanvas(page)
  await shot('app_blink.png')
  await go(page, '?field=rwaur&seq=frames&frame=100')
  await page.evaluate(() => window.scrollTo(0, 330))
  await page.waitForTimeout(300)
  await shot('app_spectrum.png')
  await writeFile(join(assets, 'stills.json'), JSON.stringify({ field: 'barnard', frame: lab, threeWayCaption: caption }, null, 1))
  console.log('stills ->', assets, '|', lab, '|', caption)
  await c2.close()
}

try {
  if (!filter || filter === 'stills') await stills()
  for (const [name, fn] of Object.entries(SHOTS)) {
    if (filter === 'stills' || (filter && !filter.split(',').some((f) => name.includes(f)))) continue
    const page = await ctx.newPage()
    page.on('pageerror', (e) => console.log(`  ${name}: pageerror: ${e.message}`))
    await addPointer(page)
    const rec = new Recorder(page, here, name)
    await rec.start()
    try {
      await fn(page, rec)
      lengths[name] = await rec.finish()
    } catch (e) {
      console.log(`FAILED ${name}: ${e.message.split('\n')[0]}`)
      if (rec.items.length > 5) { rec.name = name; lengths[name + ' (partial)'] = await rec.finish().catch(() => 0) }
    }
    await page.close()
  }
} finally {
  await browser.close()
  server.close()
}
void chromium
console.log(JSON.stringify(lengths))
