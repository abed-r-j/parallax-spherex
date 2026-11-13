// Real-network check of the live path: serve web/dist statically, drive it with installed
// Chrome through playwright-core, run live fetches from the public SPHEREx bucket, save
// screenshots to data/screens/live-*.png and the fetched numbers to data/live/probe-*.json
// (compared with the Python pipeline by data/live_compare.py).
// Usage: node scripts/live-check.mjs [m51|cosmos|all] [dist-dir]
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { createServer } from 'node:http'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { extname, join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const here = dirname(fileURLToPath(import.meta.url))
const which = process.argv[2] ?? 'all'
const dist = resolve(process.argv[3] ?? join(here, '..', 'dist'))
const shots = resolve(here, '..', '..', 'data', 'screens')
const probes = resolve(here, '..', '..', 'data', 'live')
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.woff': 'font/woff', '.bin': 'application/octet-stream' }

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
const origin = `http://127.0.0.1:${server.address().port}`
await mkdir(shots, { recursive: true })
await mkdir(probes, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const problems = []
const check = (name, ok, detail = '') => {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name} ${detail}`)
  if (!ok) problems.push(name)
}

function watch(page, tag) {
  const net = { s3: 0, s3Failed: 0, index: 0, other: new Set(), preflight: 0 }
  // the optional engine check at 127.0.0.1:8000 is refused when no engine runs: not a problem
  page.on('console', (m) => m.type() === 'error' && !/ERR_CONNECTION_REFUSED/.test(m.text()) && problems.push(`${tag}: console: ${m.text()}`))
  page.on('pageerror', (e) => problems.push(`${tag}: pageerror: ${e.message}`))
  page.on('request', (r) => {
    const u = r.url()
    if (u.startsWith('https://nasa-irsa-spherex.s3.amazonaws.com/')) {
      net.s3++
      if (r.method() === 'OPTIONS') net.preflight++
    } else if (u.startsWith(`${origin}/skyindex/`)) net.index++
    else if (!u.startsWith(origin) && !u.startsWith('data:') && !u.startsWith('blob:') && !u.startsWith('http://127.0.0.1:8000')) net.other.add(u)
  })
  page.on('requestfailed', (r) => r.url().includes('s3.amazonaws.com') && net.s3Failed++)
  return net
}

/** The field as the viewer holds it: frame table, a few decoded frames, the stacks. */
const probe = () => {
  const job = window.__parallaxLive
  const pack = job?.pack
  if (!pack) return null
  const { soft, lo, hi } = pack.meta.encoding
  const nn = pack.n * pack.n
  const dec = (i) => Array.from(pack.img.subarray(i * nn, (i + 1) * nn), (q) => (q === 0 ? null : soft * Math.sinh(lo + ((q - 1) / 65534) * (hi - lo))))
  const pick = [...new Set([0, 1, 2, Math.floor(pack.nFrames / 2), pack.nFrames - 2, pack.nFrames - 1].filter((i) => i >= 0 && i < pack.nFrames))]
  const stacks = []
  for (let c = 0; c < pack.nCampaigns; c++)
    for (let d = 0; d < 6; d++) {
      const a = pack.stack.subarray((c * 6 + d) * nn, (c * 6 + d + 1) * nn)
      const finite = Array.from(a).filter(Number.isFinite).length
      if (finite) stacks.push({ pass: c, det: d + 1, finite })
    }
  return {
    state: job.state, key: job.key, n: pack.n, nFrames: pack.nFrames, nCampaigns: pack.nCampaigns, ra0: pack.meta.ra0, dec0: pack.meta.dec0, scale: pack.meta.scale,
    live: pack.meta.live, frames: pack.meta.frames, campaigns: pack.meta.campaigns, release: pack.meta.release, stacks,
    images: pick.map((i) => ({ frame: i, name: pack.meta.frames.name[i], data: dec(i) })),
  }
}

async function runLive(page, net, tag, expectFrames) {
  const t0 = Date.now()
  await page.waitForSelector('[role=progressbar]', { timeout: 20000 })
  await page.waitForFunction(() => document.querySelectorAll('.live-thumb').length >= 2 || document.querySelector('.viewer'), null, { timeout: 180000 })
  await page.screenshot({ path: join(shots, `live-${tag}-progress.png`) })
  await page.waitForSelector('.viewer', { timeout: 240000 })
  const tViewer = (Date.now() - t0) / 1000
  await page.waitForTimeout(1500)
  await page.screenshot({ path: join(shots, `live-${tag}-partial.png`) })
  const partial = await page.evaluate(() => window.__parallaxLive?.pack?.nFrames ?? 0)
  await page.waitForFunction(() => window.__parallaxLive?.state !== 'running', null, { timeout: 1500000, polling: 500 })
  const tDone = (Date.now() - t0) / 1000
  await page.waitForTimeout(800)
  const p = await page.evaluate(probe)
  await writeFile(join(probes, `probe-${tag}.json`), JSON.stringify(p))
  check(`${tag}: live field finished`, p?.state === 'done', `${p?.nFrames} frames in ${p?.nCampaigns} passes; viewer after ${tViewer.toFixed(1)} s with ${partial} frames; done after ${tDone.toFixed(1)} s`)
  const L = p.live
  console.log(`     ${tag}: available ${L.available}, matching ${L.matching}, requested ${L.requested}, dropped ${L.dropped}, loaded ${L.loaded}, skipped ${L.skipped}, failed ${L.failed}`)
  console.log(`     ${tag}: ${(L.bytes / 1e6).toFixed(2)} MB in ${L.requests} requests, ${L.seconds.toFixed(1)} s => ${(L.bytes / 1e6 / L.seconds).toFixed(2)} MB/s, ${(L.seconds / L.requested).toFixed(2)} s per image; browser saw ${net.s3} S3 requests (${net.preflight} preflights, ${net.s3Failed} failed), ${net.index} sky-index requests`)
  console.log(`     ${tag}: stacks ${p.stacks.map((s) => `pass${s.pass + 1}/D${s.det}`).join(' ')}; passes ${p.campaigns.map((c) => `${c.start}..${c.end} (${c.nFrames})`).join(', ')}`)
  if (expectFrames) check(`${tag}: frame count`, p.nFrames >= expectFrames[0] && p.nFrames <= expectFrames[1], `${p.nFrames}`)
  check(`${tag}: nothing left the site except the archive`, net.other.size === 0, [...net.other].join(' '))
  await page.screenshot({ path: join(shots, `live-${tag}-done.png`) })
  return p
}

async function tour(page, tag) {
  const label = () => page.locator('.frame-label').innerText()
  const a = await label()
  await page.keyboard.press('ArrowRight')
  await page.waitForTimeout(200)
  check(`${tag}: stepping frames`, (await label()) !== a, JSON.stringify((await label()).replace(/\s+/g, ' ')))
  const box = await page.locator('.sky canvas').first().boundingBox()
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5)
  await page.waitForTimeout(500)
  check(`${tag}: spectrum on the fly`, (await page.locator('svg').count()) > 2 && /pix=/.test(page.url()), page.url().split('?')[1])
  await page.screenshot({ path: join(shots, `live-${tag}-spectrum.png`) })
  await page.keyboard.press('p')
  await page.waitForTimeout(500)
  check(`${tag}: by-pass stacks`, /Survey pass/.test(await label()), JSON.stringify((await label()).replace(/\s+/g, ' ')))
  await page.screenshot({ path: join(shots, `live-${tag}-passes.png`) })
  await page.keyboard.press('n')
  await page.waitForTimeout(500)
  await page.screenshot({ path: join(shots, `live-${tag}-naive.png`) })
  check(`${tag}: naive pair difference`, page.url().includes('mode=naive') && (await page.locator('.sky-msg').count()) === 0)
  await page.keyboard.press('g')
  await page.waitForTimeout(400)
  await page.screenshot({ path: join(shots, `live-${tag}-gated.png`) })
  await page.keyboard.press('c')
  await page.waitForTimeout(400)
  const msg = (await page.locator('.sky-msg').first().innerText().catch(() => '')) || ''
  check(`${tag}: chromatic view explains itself`, /engine/i.test(msg) && /pipeline/i.test(msg), JSON.stringify(msg.slice(0, 90)))
  await page.screenshot({ path: join(shots, `live-${tag}-chroma.png`) })
  await page.keyboard.press('s')
  await page.waitForTimeout(500)
  await page.screenshot({ path: join(shots, `live-${tag}-subtract.png`) })
  await page.keyboard.press('a')
  await page.waitForTimeout(500)
  await page.screenshot({ path: join(shots, `live-${tag}-add.png`) })
  await page.keyboard.press('i')
  await page.getByRole('tab', { name: 'Frame' }).click()
  await page.waitForTimeout(300)
  await page.screenshot({ path: join(shots, `live-${tag}-frame-info.png`) })
}

try {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  if (which === 'all' || which === 'm51') {
    // 1. a shared link re-runs the fetch: M51, 3 arcmin, one detector
    const page = await ctx.newPage()
    const net = watch(page, 'm51')
    await page.goto(`${origin}/?ra=202.4696&dec=47.1953&live=1&size=3&dets=3&probe=1`, { waitUntil: 'domcontentloaded' })
    await runLive(page, net, 'm51', [40, 60])
    await tour(page, 'm51')
    // session cache: leave for the About page and come back; no new archive request
    const before = net.s3
    await page.getByRole('button', { name: 'About and credits' }).click()
    await page.waitForTimeout(800)
    await page.screenshot({ path: join(shots, 'live-about.png'), fullPage: true })
    check('about page names the archive and the index', /nasa-irsa-spherex/.test(await page.locator('main').innerText()) && /index on this site was built on \d{4}-\d\d-\d\d and lists 1,628,230 images/.test(await page.locator('main').innerText()))
    await page.getByRole('button', { name: /^Back to/ }).click()
    await page.waitForSelector('.viewer', { timeout: 5000 })
    await page.waitForTimeout(500)
    check('m51: session cache (no new archive request on return)', net.s3 === before, `${net.s3 - before} new`)
    check('m51: the address carries the request', /live=1/.test(page.url()) && /size=3/.test(page.url()) && /dets=3/.test(page.url()), page.url().split('?')[1])
    await page.close()
  }
  if (which === 'all' || which === 'cosmos') {
    // 2. typed coordinates outside every field: the choice page, then the default live fetch
    const page = await ctx.newPage()
    const net = watch(page, 'cosmos')
    await page.goto(`${origin}/?probe=1`, { waitUntil: 'networkidle' })
    await page.getByRole('searchbox').fill('150.0 2.2')
    await page.keyboard.press('Enter')
    await page.waitForSelector('.live-offer', { timeout: 20000 })
    await page.waitForTimeout(3200) // the engine check gives up after 2.5 s
    await page.screenshot({ path: join(shots, 'live-offer.png'), fullPage: true })
    const offer = await page.locator('.live-offer').innerText()
    check('offer shows both routes', /Fetch live from NASA/.test(offer) && (await page.getByRole('heading', { name: 'Use a ParallaX engine' }).count()) === 1, JSON.stringify(offer.split('\n')[1]?.slice(0, 120)))
    check('offer needs only the sky index', net.s3 === 0 && net.index >= 2, `${net.index} index requests`)
    console.log(`     offer text: ${offer.replace(/\s+/g, ' ').slice(0, 700)}`)
    await page.getByRole('button', { name: /^Fetch \d+ images? live$/ }).click()
    const p = await runLive(page, net, 'cosmos')
    check('cosmos: default detectors are 2 and 5', JSON.stringify(p.live.detectors) === '[2,5]')
    check('cosmos: the address carries the request', /ra=150\.00000&dec=2\.20000/.test(page.url()) && /live=1&size=3&dets=2%2C5/.test(page.url()), page.url().split('?')[1])
    await tour(page, 'cosmos')
    await page.close()
    // 3. phone layout of the offer and of a running fetch (stopped at once, to spare the archive)
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
    const pp = await phone.newPage()
    watch(pp, 'phone')
    await pp.goto(`${origin}/?ra=150.0&dec=2.2`, { waitUntil: 'networkidle' })
    await pp.waitForSelector('.live-offer', { timeout: 20000 })
    await pp.waitForTimeout(3000)
    const overflow = await pp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    check('phone: offer has no horizontal overflow', overflow <= 1, `${overflow}px`)
    await pp.screenshot({ path: join(shots, 'live-offer-phone.png'), fullPage: true })
    await phone.close()
  }
  await ctx.close()
} finally {
  await browser.close()
  server.close()
}
console.log(problems.length ? `PROBLEMS:\n${problems.join('\n')}` : 'no problems')
process.exitCode = problems.length ? 1 : 0
