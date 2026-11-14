// Serve web/dist from a plain static server, drive it with installed Chrome through
// playwright-core, save screenshots to data/screens and report console errors and any
// request that leaves the site. Usage: node scripts/shots.mjs [name-filter] [dist-dir]
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { createServer } from 'node:http'
import { readFile, mkdir } from 'node:fs/promises'
import { extname, join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const here = dirname(fileURLToPath(import.meta.url))
const dist = resolve(process.argv[3] ?? join(here, '..', 'dist'))
const out = resolve(here, '..', '..', 'data', 'screens')
const filter = process.argv[2] && process.argv[2] !== 'all' ? process.argv[2] : ''
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
const base = `${origin}/sub/dir/` // not used: the site is served at the root; relative paths are checked by the build

const SHOTS = [
  ['home', ''],
  ['field-default', '?field=barnard'],
  ['frames-image', '?field=barnard&seq=frames&frame=40'],
  ['threeway', '?field=barnard&mode=compare&frame=40'],
  ['chroma', '?field=barnard&mode=chroma&frame=40'],
  ['naive-mismatch', '?field=barnard&mode=naive&frame=40&ov=target,gaia,mismatch,flags'],
  ['subtract', '?field=barnard&mode=sub&fov=2'],
  ['zoom-pixels', '?field=barnard&fov=2&sm=0&cm=perceptual'],
  ['ledger', '?field=barnard&seq=frames&frame=10', 'Ledger'],
  ['science', '?field=barnard', 'Science'],
  ['frame-info', '?field=barnard&seq=frames&frame=10', 'Frame'],
  ['overlays', '?field=barnard&seq=frames&frame=10', 'Overlays'],
  ['display', '?field=barnard&seq=frames&frame=10', 'Display'],
  ['candidates', '?field=barnard&seq=frames&frame=10', 'Candidates'],
  ['coords-inside', '?ra=269.4470&dec=4.7700&fov=4'],
  ['coords-outside', '?ra=10.5&dec=-20.25'],
  ['how', '?page=how'],
  ['about', '?page=about'],
  ['embed', '?field=barnard&fov=4&embed=1'],
  ['light', '?field=barnard&mode=compare&frame=40', null, 'light'],
  ['rwaur', '?field=rwaur&frame=100&pix=30,30'],
  ['wise0855', '?field=wise0855&det=6&fov=4'],
].filter(([name]) => !filter || name.includes(filter))

void base

// ---- behaviour checks: keyboard, pixel pick, CSV, URL restore, mock live engine -------
let mock = null
async function interact() {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
  const page = await ctx.newPage()
  page.on('pageerror', (e) => problems.push(`interact: pageerror: ${e.message}`))
  const check = (name, ok, detail = '') => console.log(`${ok ? 'ok  ' : 'FAIL'} ${name} ${detail}`)
  await page.goto(`${origin}/?field=barnard&seq=frames`, { waitUntil: 'networkidle' })
  const label = () => page.locator('.frame-label').innerText()
  const a = await label()
  await page.keyboard.press('ArrowRight')
  const b = await label()
  check('right arrow steps one frame', a !== b && /frame 2 of/.test(b), JSON.stringify(b.replace(/\s+/g, ' ')))
  await page.keyboard.press('Space')
  await page.waitForTimeout(1200)
  await page.keyboard.press('Space')
  const c = await label()
  check('space plays and pauses', c !== b, JSON.stringify(c.replace(/\s+/g, ' ')))
  check('URL follows the frame', /frame=\d+/.test(page.url()), page.url().split('?')[1])
  await page.keyboard.press('t')
  check('T opens the three-way view', (await page.locator('.trio figure').count()) === 3 && page.url().includes('mode=compare'))
  await page.keyboard.press('i')
  const box = await page.locator('.sky canvas').first().boundingBox()
  await page.mouse.click(box.x + box.width * 0.25, box.y + box.height * 0.25)
  check('click picks a pixel', /pix=\d+%2C\d+|pix=\d+,\d+/.test(page.url()), page.url().split('?')[1])
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download CSV' }).click()])
  const csv = (await readFile(await dl.path(), 'utf8')).split('\n')
  check('CSV downloads', csv.length > 20 && csv.some((l) => l.startsWith('frame,mjd')), `${dl.suggestedFilename()} ${csv.length} lines; ${csv[5]}`)
  const url = page.url()
  const p2 = await ctx.newPage()
  await p2.goto(url, { waitUntil: 'networkidle' })
  check('URL restores the view', (await p2.locator('.frame-label').innerText()) === (await label()) && (await p2.locator('input[type=number]').first().inputValue()) === (await page.locator('input[type=number]').first().inputValue()))
  await p2.close()
  // typed coordinates in three notations
  for (const text of ['08h55m10.831s -7d14m42.53s', '08 55 10.83 -07 14 42.5', '133.795 -7.245', '17 57 47.1 +04 46 05']) {
    await page.goto(`${origin}/`, { waitUntil: 'networkidle' })
    await page.getByRole('searchbox').fill(text)
    await page.keyboard.press('Enter')
    await page.waitForTimeout(600)
    check(`typed "${text}"`, /ra=\d/.test(page.url()) || /field=/.test(page.url()), page.url().split('?')[1])
  }
  // mock live engine: health, POST with CORS preflight, job polling, pack served from /data
  const packDir = join(dist, 'data', 'barnard')
  let polls = 0
  const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'content-type', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' }
  mock = createServer(async (req, res) => {
    const path = new URL(req.url, 'http://x').pathname
    const json = (o) => { res.writeHead(200, { ...cors, 'Content-Type': 'application/json' }); res.end(JSON.stringify(o)) }
    if (req.method === 'OPTIONS') { res.writeHead(204, cors); return res.end() }
    if (path === '/api/health') return json({ ok: true })
    if (path === '/api/field') return json({ id: 'job1' })
    if (path === '/api/job/job1') { polls++; return json(polls < 3 ? { state: 'running', progress: polls / 3, message: `downloading cutouts ${polls * 40}/120`, key: null } : { state: 'done', progress: 1, message: 'ready', key: 'live_test' }) }
    if (path.startsWith('/data/live_test/')) {
      try { const body = await readFile(join(packDir, path.split('/').pop())); res.writeHead(200, cors); return res.end(body) } catch { /* fall through */ }
    }
    res.writeHead(404, cors); res.end()
  })
  await new Promise((r) => mock.listen(0, '127.0.0.1', r))
  const eng = `http://127.0.0.1:${mock.address().port}`
  await page.goto(`${origin}/?ra=10.5&dec=-20.25&engine=${encodeURIComponent(eng)}`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('[role=progressbar]', { timeout: 8000 })
  await page.screenshot({ path: join(out, 'desktop-engine-progress.png') })
  await page.waitForSelector('.viewer', { timeout: 15000 })
  await page.waitForTimeout(500)
  check('mock engine builds and opens a field', page.url().includes('field=live_test'), `${polls} polls; ${page.url().split('?')[1]}`)
  await page.screenshot({ path: join(out, 'desktop-engine-done.png') })
  await ctx.close()
}
await mkdir(out, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const problems = []
const outside = new Set()
try {
  for (const [vw, vh, tag] of [[1440, 900, 'desktop'], [390, 844, 'phone']]) {
    const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, deviceScaleFactor: tag === 'phone' ? 2 : 1 })
    for (const [name, query, tab, theme] of SHOTS) {
      const page = await ctx.newPage()
      page.on('console', (m) => m.type() === 'error' && problems.push(`${tag}/${name}: console: ${m.text()}`))
      page.on('pageerror', (e) => problems.push(`${tag}/${name}: pageerror: ${e.message}`))
      page.on('request', (r) => !r.url().startsWith(origin) && !r.url().startsWith('data:') && !r.url().startsWith('blob:') && outside.add(`${name}: ${r.url()}`))
      if (theme) await page.addInitScript((t) => localStorage.setItem('parallax.theme', t), theme)
      await page.goto(`${origin}/${query}`, { waitUntil: 'networkidle' })
      if (name === 'coords-outside') await page.waitForTimeout(3500)
      if (tab) await page.getByRole('tab', { name: tab, exact: false }).first().click()
      await page.waitForTimeout(500)
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      if (overflow > 1) {
      // name the widest offender so the layout bug can be found without guessing
      const who = await page.evaluate(() => {
        const w = window.innerWidth
        let worst = null
        for (const el of document.querySelectorAll('body *')) {
          const r = el.getBoundingClientRect()
          if (r.right > w + 1 && (!worst || r.right > worst.right) && !el.closest('.table-wrap > table'))
            worst = { right: Math.round(r.right), tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0, 60), text: (el.textContent || '').slice(0, 50) }
        }
        return worst
      })
      problems.push(`${tag}/${name}: horizontal overflow of ${overflow}px (${who ? `${who.tag}.${who.cls} "${who.text}"` : 'unknown element'})`)
    }
      await page.screenshot({ path: join(out, `${tag}-${name}.png`), fullPage: tag === 'phone' || ['how', 'about', 'ledger', 'science', 'home'].includes(name) })
      await page.close()
    }
    await ctx.close()
  }
  if (!filter || filter === 'interact') await interact()
} finally {
  if (mock) mock.close()
  await browser.close()
  server.close()
}
console.log(`shots: ${SHOTS.length} views x 2 sizes -> ${out}`)
console.log(`requests leaving the site: ${outside.size ? [...outside].join(' | ') : 'none'}`)
console.log(problems.length ? `PROBLEMS:\n${problems.join('\n')}` : 'console: no errors')
