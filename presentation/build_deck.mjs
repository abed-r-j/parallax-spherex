// Builds the ParallaX slide deck (exactly 7 slides, 16:9) and the speaker script.
//
//   node build_deck.mjs            (from the presentation/ folder, after "npm install")
//
// Writes ParallaX_ZENITH_LABS.pptx and SPEAKER_SCRIPT.md. The images come from assets/:
// app screenshots made by video/capture.mjs (stills) and the chart made by make_charts.py.
// Every number on the slides is from docs/RESULTS.md. Export to PDF and PNG with export_deck.ps1.
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import pptxgen from 'pptxgenjs'

const here = dirname(fileURLToPath(import.meta.url))
const A = (f) => join(here, 'assets', f)

// Set to true only after the europa52 and pluto packs are published in web/public/data and
// someone has LOOKED at the object under the known-object label (see build_catalogs.md).
const MOVERS_VERIFIED_IN_PUBLISHED_PACKS = true // checked on 14 Nov 2026 in the app: see video/shot_12 and shot_13

// ---- colours and type (same palette as web/src/styles.css, dark theme) -------------------
const C = { bg: '10161F', panel: '17202C', panel2: '1E2937', line: '2C3A4D', ink: 'EBE7DC', muted: '97A3B4', accent: 'E8B04A', naive: 'E9793F', gated: '4AA3E0', chroma: '2FC59A', blue: '5CC8FF' }
const SANS = 'Segoe UI'
const HEAD = 'Segoe UI Semibold'
const MONO = 'Consolas'
const W = 13.333
const H = 7.5
const M = 0.6 // side margin

const SPHEREX_ACK = 'This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration.'
const IRSA_ACK = 'This research has made use of the NASA/IPAC Infrared Science Archive, which is funded by the National Aeronautics and Space Administration and operated by the California Institute of Technology.'

// ---- the talk: one entry per slide; this is also what goes into the speaker notes ---------
const ABED = 'Abed'
const MOHAMAD = 'Mohamad'
const TALK = [
  { who: ABED, text: 'Hello, we are ZENITH LABS. I am Abed El Rahmane Jaafir, and this is Mohamad Alayli. Our project is ParallaX, for the challenge Planet X and SPHEREx.' },
  { who: MOHAMAD, text: 'Pluto, the original Planet X, was found by blinking two photographs of the same sky. Today the SPHEREx telescope images the whole sky in the infrared, again and again. The challenge asks for a public tool that shows how that sky changes, so anyone can spot what moves or varies.' },
  { who: ABED, text: 'Here is the catch. SPHEREx never photographs the same spot in the same colour twice. On the left, each dot is one exposure, each at another wavelength. So when you subtract two dates, stars light up as false alarms, as on the right.' },
  { who: ABED, text: 'Our answer is a chromatic template. For every frame, we predict what an unchanging sky would look like at that frame’s own wavelengths, from the spectrum each pixel showed in the other survey passes. Then we subtract. And anyone can type coordinates and watch that sky in the browser, with no server.' },
  { who: MOHAMAD, text: 'We measured it on real frames, against two baselines. At the same false-alarm rate, the template finds moving sources 1.2 to 1.8 times fainter than a wavelength-matched pair. We also measured all five challenge targets against catalogues: for Barnard’s Star we get 10.2 arcseconds per year, and Gaia says 10.4.' },
  { who: MOHAMAD, text: 'Everything runs on open data: SPHEREx images from the NASA/IPAC archive, plus Gaia, CatWISE, JPL Horizons and SkyBoT. We state our limits: this is not a Planet Nine detector, and bright stars saturate. We used an SI coding assistant, and we directed and checked its work.' },
  { who: ABED, text: 'ParallaX lets anyone, from students to researchers, blink the infrared sky and check what they see. The code is open source and every number can be reproduced. Thank you.' },
]
const ELEVATOR = 'Pluto was found by blinking two photographs. SPHEREx photographs the whole infrared sky, but never the same spot in the same colour twice, so a simple blink fills with false alarms. ParallaX predicts each frame at its own colours and subtracts it, so what is left really moved or changed. Type any coordinates and watch, in your browser. It is built on NASA open data, and it is open source.'
const words = (t) => t.split(/\s+/).filter((w) => /[A-Za-z0-9]/.test(w)).length

// ---- helpers --------------------------------------------------------------------------------
function pngSize(file) {
  const b = readFileSync(file)
  return [b.readUInt32BE(16), b.readUInt32BE(20)]
}
/** Place an image inside a box, keeping its shape; returns the rectangle used. */
function fit(slide, file, x, y, w, h, { align = 'center', valign = 'middle', frame = true } = {}) {
  const [pw, ph] = pngSize(file)
  const s = Math.min(w / pw, h / ph)
  const iw = pw * s
  const ih = ph * s
  const ix = align === 'left' ? x : align === 'right' ? x + w - iw : x + (w - iw) / 2
  const iy = valign === 'top' ? y : valign === 'bottom' ? y + h - ih : y + (h - ih) / 2
  slide.addImage({ path: file, x: ix, y: iy, w: iw, h: ih })
  if (frame) slide.addShape('rect', { x: ix, y: iy, w: iw, h: ih, fill: { type: 'none' }, line: { color: C.line, width: 1 } })
  return { x: ix, y: iy, w: iw, h: ih }
}
const pptx = new pptxgen()
pptx.defineLayout({ name: 'WIDE', width: W, height: H })
pptx.layout = 'WIDE'
pptx.author = 'ZENITH LABS'
pptx.company = 'ZENITH LABS'
pptx.title = 'ParallaX: chromatic difference imaging for the SPHEREx sky'
pptx.subject = 'NASA Space Apps Challenge 2026 - Beirut. Challenge: Planet X and SPHEREx. Made with the help of an SI coding assistant (Claude, by Anthropic), directed and checked by the team.'

function base(n, kicker, title) {
  const s = pptx.addSlide()
  s.background = { color: C.bg }
  s.addText(`${String(n).padStart(2, '0')} / 07   ${kicker}`, { x: M, y: 0.36, w: 9, h: 0.34, fontFace: MONO, fontSize: 14, color: C.accent, charSpacing: 1.5, margin: 0 })
  if (title) s.addText(title, { x: M, y: 0.74, w: W - 2 * M, h: 0.86, fontFace: HEAD, fontSize: 34, color: C.ink, margin: 0, valign: 'middle', fit: 'shrink' })
  const t = TALK[n - 1]
  s.addNotes(`${t.who.toUpperCase()} (${words(t.text)} words):\n${t.text}`)
  return s
}
function mark(s, x, y, d) { // the two-dot mark of the web app, drawn as shapes (no logo files)
  s.addShape('ellipse', { x, y: y + d * 0.28, w: d * 0.72, h: d * 0.72, fill: { type: 'none' }, line: { color: C.blue, width: 3 } })
  s.addShape('ellipse', { x: x + d * 0.42, y, w: d * 0.58, h: d * 0.58, fill: { color: C.accent }, line: { color: C.bg, width: 2 } })
}
const body = (extra = {}) => ({ fontFace: SANS, fontSize: 18, color: C.ink, margin: 0, valign: 'top', paraSpaceAfter: 8, ...extra })

// ---- 1. Title ---------------------------------------------------------------------------------
{
  const s = pptx.addSlide()
  s.background = { color: C.bg }
  s.addNotes(`${TALK[0].who.toUpperCase()} (${words(TALK[0].text)} words):\n${TALK[0].text}`)
  mark(s, M, 1.02, 0.86)
  s.addText('ParallaX', { x: M + 1.1, y: 0.86, w: 5.2, h: 1.15, fontFace: HEAD, fontSize: 66, color: C.ink, margin: 0, valign: 'middle' })
  s.addText('Chromatic difference imaging for the SPHEREx sky', { x: M, y: 2.2, w: 5.9, h: 1.1, fontFace: SANS, fontSize: 28, color: C.accent, margin: 0, valign: 'top' })
  s.addText('See what really moved or changed in the infrared sky: any coordinates, in your browser.', { x: M, y: 3.42, w: 5.7, h: 0.95, fontFace: SANS, fontSize: 19, color: C.ink, margin: 0, valign: 'top' })
  s.addShape('line', { x: M, y: 4.62, w: 5.6, h: 0, line: { color: C.line, width: 1 } })
  s.addText([
    { text: 'TEAM  ', options: { fontFace: MONO, fontSize: 14, color: C.muted } },
    { text: 'ZENITH LABS', options: { fontFace: HEAD, fontSize: 18, color: C.ink, breakLine: true } },
    { text: 'Abed El Rahmane Jaafir  ·  Mohamad Alayli', options: { fontFace: SANS, fontSize: 18, color: C.ink, breakLine: true } },
    { text: 'CHALLENGE  ', options: { fontFace: MONO, fontSize: 14, color: C.muted } },
    { text: 'Planet X and SPHEREx', options: { fontFace: HEAD, fontSize: 18, color: C.ink, breakLine: true } },
    { text: 'NASA Space Apps Challenge 2026 - Beirut', options: { fontFace: SANS, fontSize: 18, color: C.muted } },
  ], { x: M, y: 4.8, w: 5.9, h: 1.9, margin: 0, valign: 'top', paraSpaceAfter: 7 })
  const r = fit(s, A('app_threeway.png'), 6.75, 1.0, W - 6.75 - M, 5.1)
  s.addText('The ParallaX web app on real SPHEREx data (Barnard’s Star field)', { x: r.x, y: r.y + r.h + 0.1, w: r.w, h: 0.32, fontFace: SANS, fontSize: 14, color: C.muted, margin: 0 })
}

// ---- 2. The challenge ---------------------------------------------------------------------------
{
  const s = base(2, 'THE CHALLENGE', 'Find what moves or changes in the infrared sky')
  const rows = [
    ['THEN', 'Pluto, the original “Planet X”, was found by blinking two photographs of the same sky.'],
    ['NOW', 'SPHEREx images the whole sky in the infrared and comes back about every six months.'],
    ['THE ASK', 'A public web tool that shows how that sky changes over time, so anyone can spot things that move or vary.'],
  ]
  rows.forEach(([k, t], i) => {
    const y = 1.95 + i * 1.32
    s.addShape('rect', { x: M, y, w: 0.07, h: 1.02, fill: { color: C.accent }, line: { color: C.accent, width: 0 } })
    s.addText(k, { x: M + 0.28, y, w: 1.4, h: 0.3, fontFace: MONO, fontSize: 14, color: C.accent, margin: 0 })
    s.addText(t, { x: M + 0.28, y: y + 0.32, w: 5.55, h: 0.75, fontFace: SANS, fontSize: 19, color: C.ink, margin: 0, valign: 'top' })
  })
  s.addText([
    { text: 'Why it matters  ', options: { fontFace: HEAD, color: C.ink } },
    { text: '1,628,230 public SPHEREx images are waiting to be compared.', options: { color: C.muted } },
  ], { x: M, y: 6.1, w: 5.9, h: 0.7, fontFace: SANS, fontSize: 17, margin: 0, valign: 'top' })
  const r = fit(s, A('app_home.png'), 6.85, 1.85, W - 6.85 - M, 4.5)
  s.addText('ParallaX home page: type coordinates, get the “little video”', { x: r.x, y: r.y + r.h + 0.1, w: r.w, h: 0.32, fontFace: SANS, fontSize: 14, color: C.muted, margin: 0 })
}

// ---- 3. The problem ---------------------------------------------------------------------------
{
  const s = base(3, 'THE PROBLEM', 'Never the same spot in the same colour twice')
  const a = fit(s, A('time_wavelength.png'), M, 1.85, 6.2, 3.75, { align: 'left', valign: 'top' })
  s.addText('Barnard’s Star field: 357 exposures in 3 survey passes, every one at another wavelength (real data, from the app).', { x: a.x, y: 5.3, w: a.w, h: 0.6, fontFace: SANS, fontSize: 14, color: C.muted, margin: 0, valign: 'top' })
  const bx = M + 6.2 + 0.45
  const bw = W - M - bx
  const b = fit(s, A('diff_naive.png'), bx, 1.85, 3.31, 3.31, { align: 'left', valign: 'top' })
  s.addText([
    { text: 'Subtract two dates naively', options: { fontFace: HEAD, fontSize: 18, color: C.naive, breakLine: true } },
    { text: 'The star lights up as a false alarm. Only the colour of the exposure changed.', options: { fontSize: 16, color: C.ink } },
  ], { x: b.x + b.w + 0.25, y: 1.85, w: bw - b.w - 0.25, h: 3.75, fontFace: SANS, margin: 0, valign: 'top', paraSpaceAfter: 6 })
  s.addText('Same field, one frame minus a frame 191 days apart, colour off by 9 bandwidths (real data).', { x: b.x, y: 5.3, w: bw, h: 0.6, fontFace: SANS, fontSize: 14, color: C.muted, margin: 0, valign: 'top' })
  s.addShape('rect', { x: M, y: 6.42, w: W - 2 * M, h: 0.68, fill: { color: C.panel }, line: { color: C.line, width: 1 } })
  s.addText([
    { text: 'And the pixels are coarse (6.15 arcsec): ', options: { color: C.muted } },
    { text: 'a star’s peak pixel jitters by 23 to 27% between frames, while the test stars move only 1 to 2 pixels.', options: { color: C.ink } },
  ], { x: M + 0.2, y: 6.42, w: W - 2 * M - 0.4, h: 0.68, fontFace: SANS, fontSize: 16, margin: 0, valign: 'middle' })
}

// ---- 4. The solution ---------------------------------------------------------------------------
{
  const s = base(4, 'THE SOLUTION', 'Predict each frame at its own colours, then subtract')
  // diagram: three boxes and two arrows
  const bw = 2.2
  const bh = 1.5
  const gap = 0.45
  const y = 1.85
  const boxes = [
    ['1  OTHER PASSES', 'The spectrum that every pixel showed before', C.blue],
    ['2  TEMPLATE', 'The static sky, predicted at this frame’s own wavelengths', C.chroma],
    ['3  SUBTRACT', 'What is left has really moved or changed', C.accent],
  ]
  boxes.forEach(([k, t, col], i) => {
    const x = M + i * (bw + gap)
    s.addShape('roundRect', { x, y, w: bw, h: bh, rectRadius: 0.06, fill: { color: C.panel }, line: { color: col, width: 1.5 } })
    s.addText(k, { x: x + 0.14, y: y + 0.1, w: bw - 0.28, h: 0.34, fontFace: MONO, fontSize: 14, color: col, margin: 0, fit: 'shrink' })
    s.addText(t, { x: x + 0.14, y: y + 0.46, w: bw - 0.28, h: bh - 0.52, fontFace: SANS, fontSize: 15, color: C.ink, margin: 0, valign: 'top' })
    if (i < 2) s.addShape('line', { x: x + bw + 0.06, y: y + bh / 2, w: gap - 0.12, h: 0, line: { color: C.muted, width: 2, endArrowType: 'triangle' } })
  })
  // "any coordinates" block under the diagram
  const dw = 3 * bw + 2 * gap
  s.addShape('rect', { x: M, y: 3.75, w: dw, h: 2.75, fill: { color: C.panel }, line: { color: C.line, width: 1 } })
  s.addText([
    { text: 'Any coordinates · in your browser · no server', options: { fontFace: HEAD, fontSize: 21, color: C.accent, breakLine: true } },
    { text: 'A 45.6 MB index of all 1,628,230 public SPHEREx images; pixels are read straight from the public archive.', options: { fontSize: 17, color: C.ink, breakLine: true } },
    { text: 'Spectra on click, per-pass blink, add and subtract, Gaia and WISE overlays, known-asteroid labels, shareable links.', options: { fontSize: 17, color: C.ink, breakLine: true } },
    { text: 'Live fields give frames, stacks, spectra and pair differences; the template is computed by the open Python pipeline.', options: { fontSize: 14, color: C.muted } },
  ], { x: M + 0.22, y: 3.92, w: dw - 0.44, h: 2.5, fontFace: SANS, margin: 0, valign: 'top', paraSpaceAfter: 7 })
  // before / after
  const px = M + dw + 0.45
  const pw = (W - M - px - 0.25) / 2
  s.addText('BEFORE', { x: px, y: 1.85, w: pw, h: 0.3, fontFace: MONO, fontSize: 14, color: C.naive, margin: 0 })
  s.addText('AFTER', { x: px + pw + 0.25, y: 1.85, w: pw, h: 0.3, fontFace: MONO, fontSize: 14, color: C.chroma, margin: 0 })
  const p1 = fit(s, A('diff_naive.png'), px, 2.2, pw, pw, { valign: 'top' })
  fit(s, A('diff_chromatic.png'), px + pw + 0.25, 2.2, pw, pw, { valign: 'top' })
  s.addText('Naive pair', { x: px, y: p1.y + p1.h + 0.08, w: pw, h: 0.32, fontFace: HEAD, fontSize: 15, color: C.ink, margin: 0 })
  s.addText('Chromatic template', { x: px + pw + 0.25, y: p1.y + p1.h + 0.08, w: pw + 0.1, h: 0.32, fontFace: HEAD, fontSize: 15, color: C.ink, margin: 0 })
  s.addText('The same real frame of Barnard’s Star (0.970 micron), on one colour scale. The halo in the naive pair is false signal from the colour mismatch; the template removes most of it.', { x: px, y: p1.y + p1.h + 0.46, w: 2 * pw + 0.25, h: 1.5, fontFace: SANS, fontSize: 14, color: C.muted, margin: 0, valign: 'top' })
}

// ---- 5. Proof ---------------------------------------------------------------------------------
{
  const s = base(5, 'PROOF', 'Measured on real frames, against two baselines')
  s.addText('Faintest moving source found (lower is better)', { x: M, y: 1.72, w: 6.5, h: 0.36, fontFace: HEAD, fontSize: 18, color: C.ink, margin: 0 })
  const r = fit(s, A('chart_f50.png'), M, 2.1, 6.5, 3.85, { align: 'left', valign: 'top', frame: false })
  s.addText('Flux at which half of the artificial moving sources added to real frames are recovered, on blank sky, with every method tuned to the same false-detection rate (0.5 per frame).', { x: M, y: r.y + r.h + 0.08, w: 6.5, h: 0.95, fontFace: SANS, fontSize: 14, color: C.muted, margin: 0, valign: 'top' })
  const x = 7.55
  const w = W - M - x
  const nums = [
    ['1.2–1.8×', 'fainter moving sources than the gated pair'],
    ['3–15%', 'deeper than the gated pair, in every field'],
    ['4 of 5', 'fields with fewer false detections than the gated pair'],
  ]
  nums.forEach(([n, t], i) => {
    const y = 1.72 + i * 0.66
    s.addText(n, { x, y, w: 1.75, h: 0.58, fontFace: HEAD, fontSize: 27, color: C.chroma, margin: 0, valign: 'middle' })
    s.addText(t, { x: x + 1.85, y, w: w - 1.85, h: 0.58, fontFace: SANS, fontSize: 15, color: C.ink, margin: 0, valign: 'middle' })
  })
  s.addShape('line', { x, y: 3.78, w, h: 0, line: { color: C.line, width: 1 } })
  s.addText('THE FIVE CHALLENGE TARGETS, AGAINST CATALOGUES', { x, y: 3.88, w, h: 0.3, fontFace: MONO, fontSize: 14, color: C.accent, margin: 0, fit: 'shrink' })
  const targets = [
    ['Barnard’s Star', '10.21 ± 0.26 arcsec/yr (Gaia: 10.36)'],
    ['Epsilon Indi B', '4.64 ± 0.09 arcsec/yr (catalogue: 4.70)'],
    ['WISE 0855−0714', 'found in stacks, S/N 6.6 (optimistic)'],
    ['RW Aurigae', '0.76 mag brighter at 4.4–5.0 µm'],
    ['R Draconis', 'period 250 d (catalogue: about 246 d)'],
  ]
  const rowsT = targets.map(([a, b]) => [
    { text: a, options: { fontFace: HEAD, fontSize: 14, color: C.ink, margin: [2, 4, 2, 0] } },
    { text: b, options: { fontFace: SANS, fontSize: 14, color: C.ink, margin: [2, 0, 2, 4] } },
  ])
  s.addTable(rowsT, { x, y: 4.22, w, colW: [1.75, w - 1.75], rowH: 0.35, border: { type: 'none' }, valign: 'middle' })
  if (MOVERS_VERIFIED_IN_PUBLISHED_PACKS) s.addText('Asteroid (52) Europa and Pluto: found where JPL Horizons predicts, to 0.05 pixel.', { x, y: 6.08, w, h: 0.5, fontFace: SANS, fontSize: 14, color: C.ink, margin: 0, valign: 'top' })
  s.addText('Limits: 1–2 pixel motion shows better in a per-pass blink; parallax is not measured; bright stars saturate.', { x, y: 6.62, w, h: 0.55, fontFace: SANS, fontSize: 14, color: C.muted, margin: 0, valign: 'top' })
}

// ---- 6. Data, tools, how it was built -----------------------------------------------------------
{
  const s = base(6, 'DATA, TOOLS AND HOW IT WAS BUILT', 'Open data in, open source out')
  const cols = [
    ['NASA AND PARTNER DATA', C.blue, [
      'SPHEREx Level-2 spectral images, DR1 and QR3, from the NASA/IPAC Infrared Science Archive (IRSA)',
      'ESA Gaia DR3 and CatWISE2020 star positions',
      'JPL Horizons and IMCCE SkyBoT for known solar-system objects',
    ]],
    ['THE STACK', C.chroma, [
      'Pipeline: Python with NumPy, SciPy and Astropy; 87 tests',
      'Web app: React, TypeScript and Vite; a static site, 55 tests',
      'Reads only the pixels it needs: about 0.5 MB per image instead of the 65 MB file',
      'Licence: Apache-2.0',
    ]],
    ['HOW IT WAS BUILT', C.accent, [
      'Research first: the official text, the archive, existing approaches',
      'Then pipeline, three-way ledger, web app and live mode',
      'Development began on 12–13 November 2026, before the on-site event; the local organizers allowed early preparation',
    ]],
  ]
  const cw = (W - 2 * M - 2 * 0.3) / 3
  cols.forEach(([k, col, items], i) => {
    const x = M + i * (cw + 0.3)
    s.addShape('rect', { x, y: 1.85, w: cw, h: 3.5, fill: { color: C.panel }, line: { color: C.line, width: 1 } })
    s.addShape('rect', { x, y: 1.85, w: cw, h: 0.06, fill: { color: col }, line: { color: col, width: 0 } })
    s.addText(k, { x: x + 0.2, y: 2.02, w: cw - 0.4, h: 0.32, fontFace: MONO, fontSize: 14, color: col, margin: 0 })
    s.addText(items.map((t) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: true } })), { x: x + 0.2, y: 2.44, w: cw - 0.4, h: 2.85, fontFace: SANS, fontSize: 15, color: C.ink, margin: 0, valign: 'top', paraSpaceAfter: 7 })
  })
  s.addText([
    { text: 'Limits  ', options: { fontFace: HEAD, color: C.naive } },
    { text: 'Planet X is the motivation, not a claim: a real Planet Nine would be far too faint for single SPHEREx frames. Parallax is not reliably measured; bright targets saturate.', options: { color: C.ink } },
  ], { x: M, y: 5.55, w: W - 2 * M, h: 0.66, fontFace: SANS, fontSize: 15, margin: 0, valign: 'top' })
  s.addText([
    { text: 'SI use  ', options: { fontFace: HEAD, color: C.accent } },
    { text: 'Software, documents and figures were produced with an SI coding assistant (Claude, by Anthropic) directed by the team, who reviewed and ran everything. All results are computed by our own code from real SPHEREx data. No SI-generated images, video, voices or faces.', options: { color: C.ink } },
  ], { x: M, y: 6.25, w: W - 2 * M, h: 0.9, fontFace: SANS, fontSize: 15, margin: 0, valign: 'top' })
}

// ---- 7. Impact, next, links, credits -----------------------------------------------------------
{
  const s = base(7, 'IMPACT AND WHAT IS NEXT', 'Anyone can blink the infrared sky')
  const half = (W - 2 * M - 0.4) / 2
  s.addText('IMPACT', { x: M, y: 1.8, w: half, h: 0.3, fontFace: MONO, fontSize: 14, color: C.chroma, margin: 0 })
  s.addText([
    'Students, amateurs and researchers can look at any position, with no install and no account',
    'A published, reproducible benchmark of three ways to difference SPHEREx frames, with its limits',
    'Every view has its own link and can be embedded in a lesson or a report',
  ].map((t) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: true } })), { x: M, y: 2.2, w: half, h: 2.3, ...body({ fontSize: 17 }) })
  const x2 = M + half + 0.4
  s.addText('NEXT', { x: x2, y: 1.8, w: half, h: 0.3, fontFace: MONO, fontSize: 14, color: C.accent, margin: 0 })
  s.addText([
    'More moving-object fields: asteroids and comets',
    'Bring the chromatic template to live fields',
    'Follow each new SPHEREx data release',
  ].map((t) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: true } })), { x: x2, y: 2.2, w: half, h: 2.3, ...body({ fontSize: 17 }) })
  s.addShape('rect', { x: M, y: 4.6, w: W - 2 * M, h: 1.02, fill: { color: C.panel }, line: { color: C.line, width: 1 } })
  s.addText([
    { text: 'Code  ', options: { fontFace: MONO, fontSize: 14, color: C.muted } },
    { text: 'github.com/abed-r-j/parallax-spherex', options: { fontFace: MONO, fontSize: 16, color: C.ink } },
    { text: '   (to be published)', options: { fontFace: SANS, fontSize: 14, color: C.accent, breakLine: true } },
    { text: 'Site  ', options: { fontFace: MONO, fontSize: 14, color: C.muted } },
    { text: 'abed-r-j.github.io/parallax-spherex', options: { fontFace: MONO, fontSize: 16, color: C.ink } },
    { text: '   (to be published)', options: { fontFace: SANS, fontSize: 14, color: C.accent } },
  ], { x: M + 0.22, y: 4.6, w: W - 2 * M - 0.44, h: 1.02, margin: 0, valign: 'middle', paraSpaceAfter: 4 })
  s.addText([
    { text: 'Not affiliated with or endorsed by NASA. ', options: { bold: true, color: C.ink } },
    { text: `${SPHEREX_ACK} ${IRSA_ACK} `, options: {} },
    { text: 'Data: SPHEREx DR1 Spectral Images, doi:10.26131/IRSA678, and QR3, doi:10.26131/IRSA662. Also used: ESA Gaia DR3; CatWISE2020 (IRSA); IMCCE SkyBoT; NASA/JPL Solar System Dynamics, Horizons (https://ssd.jpl.nasa.gov). Team ZENITH LABS, NASA Space Apps Challenge 2026 - Beirut. Code under Apache-2.0. Made with the help of an SI coding assistant (Claude, by Anthropic).', options: {} },
  ], { x: M, y: 5.85, w: W - 2 * M, h: 1.4, fontFace: SANS, fontSize: 10, color: C.muted, margin: 0, valign: 'top' })
}

await pptx.writeFile({ fileName: join(here, 'ParallaX_ZENITH_LABS.pptx') })

// ---- the speaker script, from the same text --------------------------------------------------
const TITLES = ['Title', 'The challenge', 'The problem', 'The solution', 'Proof', 'Data, tools and how it was built', 'Impact and what is next']
const total = TALK.reduce((a, t) => a + words(t.text), 0)
const per = (who) => TALK.filter((t) => t.who === who).reduce((a, t) => a + words(t.text), 0)
let md = `# ParallaX: speaker script for the 7 slides (2 minutes)

SI disclosure: drafted with the help of an SI coding assistant (Claude, by Anthropic); to be reviewed and spoken by the team.
Generated by \`build_deck.mjs\` from the same text as the speaker notes in \`ParallaX_ZENITH_LABS.pptx\`. Edit the text there and rebuild.

Speakers: **Abed** = Abed El Rahmane Jaafir, **Mohamad** = Mohamad Alayli.
Total: **${total} words** (Abed ${per(ABED)}, Mohamad ${per(MOHAMAD)}). At a calm 145 to 150 words per minute this is ${(total / 150 * 60).toFixed(0)} to ${(total / 145 * 60).toFixed(0)} seconds. Rehearse with a timer; if you run over, drop the last sentence of slide 6.

| Slide | Speaker | Words | About |
|---|---|---|---|
${TALK.map((t, i) => `| ${i + 1}. ${TITLES[i]} | ${t.who} | ${words(t.text)} | ${(words(t.text) / 148 * 60).toFixed(0)} s |`).join('\n')}
| **Total** | | **${total}** | **${(total / 148 * 60).toFixed(0)} s** |

`
TALK.forEach((t, i) => { md += `## Slide ${i + 1}: ${TITLES[i]} (${t.who}, ${words(t.text)} words)\n\n${t.text}\n\n` })
md += `## Notes for the speakers

* Every number spoken is from \`docs/RESULTS.md\`: 1.2 to 1.8 times fainter than the gated pair at a matched false-detection rate (section 2.1); Barnard's Star 10.21 +- 0.26 arcsec/yr against 10.36 from Gaia DR3 (section 3), spoken as "10.2" and "10.4".
* Do not say that ParallaX found Planet X or that it measures parallax. If asked: a real Planet Nine would be far too faint for single SPHEREx frames, and parallax is not reliably measured.
* If asked about the name: it comes from the blink-and-shift idea, not from a parallax measurement.
* If asked what "wavelength-matched pair" means: subtracting only two exposures whose colours agree within half a filter bandwidth.
* Timeline, if asked: development began on 12-13 November 2026, before the on-site event, after the local organizers allowed early preparation.

## 30-second "elevator" version (${words(ELEVATOR)} words, one speaker)

${ELEVATOR}
`
writeFileSync(join(here, 'SPEAKER_SCRIPT.md'), md)
console.log(`deck: 7 slides -> ParallaX_ZENITH_LABS.pptx; talk ${total} words (${TALK.map((t) => words(t.text)).join(', ')}); elevator ${words(ELEVATOR)} words`)
