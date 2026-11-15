// Build docs/ParallaX_Project_Report.pdf from docs/REPORT.md with installed Chrome (headless),
// through playwright-core from web/node_modules. No package beyond that is needed: the small
// Markdown converter below covers what REPORT.md uses (headings, paragraphs, lists, tables,
// images, bold, italic, code, links).
// Usage (from the repository root):  node docs/build_report_pdf.mjs
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { stampMetadata } from '../submission/stamp_pdf.mjs'
import { readFile, writeFile, rm } from 'node:fs/promises'

const here = dirname(fileURLToPath(import.meta.url))
const require = createRequire(join(here, '..', 'web', 'package.json'))
const { chromium } = require('playwright-core')

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
function inline(s) {
  const codes = []
  let t = s.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000` })
  t = esc(t)
  t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, '<img alt="$1" src="$2">')
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>')
  t = t.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
  t = t.replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\w)/g, '$1<em>$2</em>')
  return t.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${esc(codes[+i])}</code>`)
}
function toHtml(md) {
  const lines = md.replace(/\r\n/g, '\n').split('\n')
  const out = []
  let i = 0
  const cells = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
  while (i < lines.length) {
    const l = lines[i]
    if (!l.trim()) { i++; continue }
    const h = /^(#{1,3})\s+(.*)$/.exec(l)
    if (h) { out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); i++; continue }
    if (/^\|/.test(l) && /^\|[\s:|-]+\|$/.test((lines[i + 1] ?? '').trim())) {
      const head = cells(l)
      i += 2
      const rows = []
      while (i < lines.length && /^\|/.test(lines[i])) rows.push(cells(lines[i++]))
      out.push(`<table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`)
      continue
    }
    const li = /^(\*|-|\d+\.)\s+(.*)$/.exec(l)
    if (li) {
      const tag = /\d/.test(li[1]) ? 'ol' : 'ul'
      const items = []
      while (i < lines.length) {
        const m = /^(\*|-|\d+\.)\s+(.*)$/.exec(lines[i])
        if (m) { items.push(m[2]); i++ } else if (/^\s+\S/.test(lines[i]) && items.length) { items[items.length - 1] += ' ' + lines[i].trim(); i++ } else if (!lines[i].trim() && /^(\*|-|\d+\.)\s+/.test(lines[i + 1] ?? '')) i++
        else break
      }
      out.push(`<${tag}>${items.map((t) => `<li>${inline(t)}</li>`).join('')}</${tag}>`)
      continue
    }
    const para = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|\||(\*|-|\d+\.)\s)/.test(lines[i])) para.push(lines[i++].trim())
    if (!para.length) para.push(lines[i++].trim())
    out.push(`<p>${inline(para.join(' '))}</p>`)
  }
  return out.join('\n')
}

const css = `
@page { size: A4; margin: 17mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
html { font-family: 'Segoe UI', Arial, Helvetica, sans-serif; font-size: 10.2pt; line-height: 1.42; color: #16202b; }
body { margin: 0; }
h1 { font-size: 21pt; line-height: 1.15; margin: 0 0 6pt; color: #0d1b2a; }
h2 { font-size: 13.5pt; margin: 15pt 0 5pt; padding-bottom: 2pt; border-bottom: 1.2pt solid #c58a1a; color: #0d1b2a; break-after: avoid; }
h3 { font-size: 11pt; margin: 10pt 0 3pt; color: #0d1b2a; break-after: avoid; }
p { margin: 0 0 6pt; orphans: 3; widows: 3; }
ul, ol { margin: 0 0 6pt; padding-left: 16pt; }
li { margin: 0 0 2.2pt; }
code { font-family: Consolas, 'Courier New', monospace; font-size: 9pt; background: #eef1f4; padding: 0 2pt; border-radius: 2pt; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt; font-size: 8.9pt; break-inside: auto; }
th, td { border: 0.5pt solid #b9c2cc; padding: 2.4pt 4.5pt; text-align: left; vertical-align: top; }
th { background: #e9edf2; }
th:empty { display: none; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
img { display: block; max-width: 100%; max-height: 88mm; margin: 7pt auto 3pt; border: 0.5pt solid #b9c2cc; }
p:has(> img) { margin: 0; break-after: avoid; }
p:has(> img) + p em { display: block; font-size: 8.8pt; color: #3d4a57; text-align: left; margin-bottom: 4pt; }
p:has(> img) + p { break-before: avoid; }
a { color: #0b4f8a; text-decoration: none; }
`
const md = await readFile(join(here, 'REPORT.md'), 'utf8')
const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>ParallaX project report</title><style>${css}</style></head><body>${toHtml(md)}</body></html>`
const tmp = join(here, '_report_build.html') // next to REPORT.md so that img/... resolves
const pdf = resolve(here, 'ParallaX_Project_Report.pdf')
await writeFile(tmp, html, 'utf8')
const browser = await chromium.launch({ channel: 'chrome', headless: true })
try {
  const page = await (await browser.newContext({ offline: true })).newPage()
  await page.goto(pathToFileURL(tmp).href, { waitUntil: 'load' })
  const broken = await page.evaluate(() => [...document.images].filter((i) => !i.complete || i.naturalWidth === 0).map((i) => i.src))
  if (broken.length) throw new Error('missing images: ' + broken.join(', '))
  await page.pdf({
    path: pdf, format: 'A4', printBackground: true, displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate: '<div style="width:100%;font-size:7.5pt;font-family:Segoe UI,Arial;color:#566;padding:0 16mm;display:flex;justify-content:space-between"><span>ParallaX project report, team ZENITH LABS. Not affiliated with or endorsed by NASA.</span><span>page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>',
    margin: { top: '17mm', bottom: '18mm', left: '16mm', right: '16mm' },
  })
  stampMetadata(pdf) // Title, Author, Subject, Keywords, Comments (SI statement); see submission/set_metadata.py
  const bytes = await readFile(pdf)
  const pages = (bytes.toString('latin1').match(/\/Type\s*\/Page(?![s\w])/g) || []).length
  console.log(`wrote ${pdf}: ${bytes.length} bytes, ${pages} pages, ${md.split(/\s+/).length} words in REPORT.md`)
  if (process.argv[2]) { // optional: node docs/build_report_pdf.mjs <folder> writes one PNG per page for a visual check
    const view = await browser.newPage({ viewport: { width: 794, height: 1123 } })
    await view.goto(pathToFileURL(tmp).href, { waitUntil: 'load' })
    await view.emulateMedia({ media: 'screen' })
    const total = await view.evaluate(() => document.documentElement.scrollHeight)
    for (let y = 0, n = 1; y < total; y += 1123, n++) await view.screenshot({ path: join(resolve(process.argv[2]), `report-${n}.png`), clip: { x: 0, y, width: 794, height: Math.min(1123, total - y) }, fullPage: true })
    console.log('screen check images written to', resolve(process.argv[2]))
  }
} finally {
  await browser.close()
  await rm(tmp, { force: true })
}
