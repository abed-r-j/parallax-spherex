// Render every page of paper/ParallaX_IEEE.pdf to paper/pages/page-N.png with Chrome's own
// PDF viewer (headless, through playwright-core from web/node_modules), for visual checks.
// Usage (from the repository root):  node paper/render_pages.mjs [pages]
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { mkdir, readFile } from 'node:fs/promises'

const here = dirname(fileURLToPath(import.meta.url))
const require = createRequire(join(here, '..', 'web', 'package.json'))
const { chromium } = require('playwright-core')
const pdf = resolve(here, 'ParallaX_IEEE.pdf')
const out = resolve(here, 'pages')
await mkdir(out, { recursive: true })
const bytes = await readFile(pdf)
const n = Number(process.argv[2]) ||
  (bytes.toString('latin1').match(/\/Type\s*\/Page(?![s\w])/g) || []).length
const W = 1020, H = 1320 // 8.5 x 11 in at 120 px/in
const browser = await chromium.launch({ channel: 'chrome', headless: true })
try {
  for (let p = 1; p <= n; p++) {
    const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1.5 })
    await page.goto(`${pathToFileURL(pdf).href}#page=${p}&toolbar=0&navpanes=0&view=Fit`)
    await page.waitForTimeout(2500)
    await page.screenshot({ path: join(out, `page-${p}.png`) })
    await page.close()
  }
  console.log(`rendered ${n} pages to ${out}`)
} finally {
  await browser.close()
}
