// Build paper/ParallaX_IEEE.pdf from paper/paper.html with installed Chrome (headless),
// through playwright-core from web/node_modules. No network access is needed or allowed.
// Usage (from the repository root):  node paper/build_pdf.mjs
// Then run  node paper/render_pages.mjs  to get paper/pages/page-N.png for a visual check.
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { stampMetadata } from '../submission/stamp_pdf.mjs'
import { readFile } from 'node:fs/promises'

const here = dirname(fileURLToPath(import.meta.url))
const require = createRequire(join(here, '..', 'web', 'package.json'))
const { chromium } = require('playwright-core')

const html = resolve(here, 'paper.html')
const pdf = resolve(here, 'ParallaX_IEEE.pdf')

const browser = await chromium.launch({ channel: 'chrome', headless: true })
try {
  const context = await browser.newContext({ offline: true })
  const page = await context.newPage()
  const external = []
  page.on('request', (r) => { if (!r.url().startsWith('file:')) external.push(r.url()) })
  page.on('console', (m) => { if (m.type() === 'error') console.log('console error:', m.text()) })
  await page.goto(pathToFileURL(html).href, { waitUntil: 'load' })
  await page.emulateMedia({ media: 'print' })
  const broken = await page.evaluate(() =>
    [...document.images].filter((i) => !i.complete || i.naturalWidth === 0).map((i) => i.src))
  if (broken.length) throw new Error('missing images: ' + broken.join(', '))
  await page.pdf({ path: pdf, preferCSSPageSize: true, printBackground: true,
    displayHeaderFooter: false, tagged: true })
  stampMetadata(pdf) // Title, Author, Subject, Keywords, Comments (SI statement); see submission/set_metadata.py
  const bytes = await readFile(pdf)
  const pages = (bytes.toString('latin1').match(/\/Type\s*\/Page(?![s\w])/g) || []).length
  console.log(`wrote ${pdf}: ${bytes.length} bytes, ${pages} pages`)
  if (external.length) console.log('WARNING external requests:', external)
} finally {
  await browser.close()
}

