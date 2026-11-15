// Builds the picture tracks (base_*.mp4), the teleprompters (teleprompter_*.mp4) and the
// timelines (timeline_*.json) that assemble.ps1 reads. No people, no camera, no microphone.
//   node build_video.mjs            both videos
//   node build_video.mjs 30s        only one
// Times, speakers and words come from SCRIPT_*.md and subs_*.srt (made by make_scripts.mjs).
// SI disclosure: written with the help of an SI coding assistant (Claude, by Anthropic).
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const DIR = dirname(fileURLToPath(import.meta.url))
const B = join(DIR, '_build')
mkdirSync(B, { recursive: true })
const FPS = 30
const BG = '0x10161f', PANEL = '0x17202c', INK = '0xebe7dc', MUTED = '0x97a3b4', ACCENT = '0xe8b04a', BLUE = '0x6cc5e8'
const FONT = "fontfile='C\\:/Windows/Fonts/segoeui.ttf'"
const FONTB = "fontfile='C\\:/Windows/Fonts/segoeuib.ttf'"
// Geometry shared with assemble.ps1 (through the timeline file)
const SUB = { x: 340, y: 896, w: 1240, h: 128 } // subtitle band, bottom, inside the title-safe area
const LT = { x: 96, y: 692, w: 1728, h: 184 } // lower third for the opening and closing text
const COUNT = 5.5 // teleprompter: five numbers, then a half-second long beep at zero

const OPEN = ['ParallaX: chromatic difference imaging for the SPHEREx sky',
  'Team ZENITH LABS - Abed El Rahmane Jaafir, Mohamad Alayli',
  'Challenge: Planet X and SPHEREx   |   NASA Space Apps Challenge 2026 - Beirut']
const CLOSE = ['https://abed-r-j.github.io/parallax-spherex/',
  'Data: SPHEREx Level-2 spectral images, NASA/IPAC IRSA; ESA Gaia DR3; JPL Horizons',
  'Not affiliated with or endorsed by NASA. Made with the help of an SI coding assistant.']

const S = (file, ss, dur, speed = 1) => ({ file, ss, dur, speed })
const C = (dur) => ({ card: true, dur })
const PLANS = {
  '30s': {
    segs: [C(3), S('shot_13_pluto', 0.5, 4, 1.15), S('shot_01_type_coordinates', 3, 4.5), S('shot_03_time_wavelength', 2, 2),
      S('shot_04_naive_false_alarms', 1, 2), S('shot_05_three_way', 2.5, 5),
      S('shot_11_live_fetch', 1, 1.5), S('shot_11_live_fetch', 8.5, 1.5), S('shot_11_live_fetch', 22, 1.5), C(3.5)],
    notes: [[7, 9.5, 'ParallaX: chromatic difference imaging for the SPHEREx sky'], [15.5, 20.5, 'SPHEREx data: NASA/IPAC IRSA']],
    camFull: [[0, 3], [25, 28.5]], ltOpen: [0, 3], ltClose: [25, 28.5],
  },
  '2min': {
    segs: [C(11), S('shot_13_pluto', 0, 8.5, 1.15), S('shot_03_time_wavelength', 1, 6), S('shot_04_naive_false_alarms', 1, 4.5),
      S('shot_06_chromatic', 1, 5), S('shot_01_type_coordinates', 2, 7),
      S('shot_11_live_fetch', 0.5, 3), S('shot_11_live_fetch', 5, 2), S('shot_11_live_fetch', 8, 2), S('shot_11_live_fetch', 12, 3), S('shot_11_live_fetch', 21, 3),
      S('shot_02_blink_barnard', 1.5, 5.5), S('shot_05_three_way', 0, 10.5, 0.85), S('shot_07_click_spectrum', 0, 2.8),
      S('shot_12_asteroid_europa', 1, 3.7), S('shot_09_ledger', 0, 12, 0.85), C(25.5)],
    notes: [[35, 42, 'Data: SPHEREx (NASA/IPAC IRSA), Gaia DR3, CatWISE2020, JPL Horizons, IMCCE SkyBoT'],
      [42, 55, 'Python pipeline + React / TypeScript app, no server'],
      [77.5, 89.5, '1.2 to 1.9 times fainter than the gated pair, at a matched false-detection rate (blank sky)']],
    camFull: [[0, 11], [89.5, 115]], ltOpen: [0, 6], ltClose: [109, 115],
  },
}

let nText = 0
function textfile(s) {
  const name = `t${String(++nText).padStart(3, '0')}.txt`
  writeFileSync(join(B, name), s, 'utf8')
  return name
}
const en = (a, b) => `enable='gte(t,${a})*lt(t,${b})'`
function dt(s, { x, y, size, color = 'white', bold = false, a, b, box = '' }) {
  return `drawtext=${bold ? FONTB : FONT}:textfile='${textfile(s)}':fontsize=${size}:fontcolor=${color}:x=${x}:y=${y}${box}${a === undefined ? '' : ':' + en(a, b)}`
}
const CX = '(w-text_w)/2'
function wrap(text, n) {
  const out = []
  let line = ''
  for (const w of text.split(' ')) {
    if (line && (line + ' ' + w).length > n) { out.push(line); line = w } else line = line ? line + ' ' + w : w
  }
  if (line) out.push(line)
  return out
}
function run(args) {
  const r = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...args], { cwd: B, stdio: 'inherit' })
  if (r.status !== 0) { console.error('ffmpeg failed'); process.exit(1) }
}
function probe(f) {
  const r = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration,size', '-of', 'csv=p=0', f], { encoding: 'utf8' })
  return r.stdout.trim()
}
function readScript(key) {
  const sec = (m, s) => Number(m) * 60 + Number(s)
  const lines = []
  for (const row of readFileSync(join(DIR, `SCRIPT_${key}.md`), 'utf8').split(/\r?\n/)) {
    const m = row.match(/^\| (\d+):([\d.]+) to (\d+):([\d.]+) \| (\w+) \| (.*) \| \d+ \| "(.*)" \|$/)
    if (m) lines.push({ a: sec(m[1], m[2]), b: sec(m[3], m[4]), who: m[5], pic: m[6], text: m[7] })
  }
  const ts = (t) => { const [h, m, s] = t.replace(',', '.').split(':').map(Number); return h * 3600 + m * 60 + s }
  const cues = []
  for (const blk of readFileSync(join(DIR, `subs_${key}.srt`), 'utf8').replace(/\r/g, '').split(/\n\n+/)) {
    const l = blk.trim().split('\n')
    const m = l[1] && l[1].match(/(\S+) --> (\S+)/)
    if (m) cues.push({ a: ts(m[1]), b: ts(m[2]), lines: l.slice(2) })
  }
  return { lines, cues }
}

function build(key) {
  const P = PLANS[key]
  const { lines, cues } = readScript(key)
  const END = lines[lines.length - 1].b
  const total = P.segs.reduce((a, s) => a + s.dur, 0)
  if (Math.abs(total - END) > 1e-6) throw new Error(`${key}: the shot plan lasts ${total} s but the script ends at ${END} s`)
  if (cues[cues.length - 1].b !== END) throw new Error(`${key}: subtitles and script end at different times`)

  // ---- base: the picture track without people ----
  const inputs = []
  const g = []
  let t = 0
  const cards = []
  P.segs.forEach((s, i) => {
    const n = Math.round(s.dur * FPS)
    if (s.card) {
      g.push(`color=c=${BG}:s=1920x1080:r=${FPS}:d=${s.dur},format=yuv420p,setsar=1[v${i}]`)
      cards.push([t, t + s.dur])
    } else {
      if (s.speed < 0.85 - 1e-9 || s.speed > 1.15 + 1e-9) throw new Error('speed change above 15%')
      inputs.push('-i', join(DIR, s.file + '.mp4'))
      const k = inputs.length / 2 - 1
      g.push(`[${k}:v]trim=start=${s.ss}:duration=${(s.dur * s.speed + 0.2).toFixed(3)},setpts=(PTS-STARTPTS)/${s.speed},fps=${FPS},tpad=stop_mode=clone:stop_duration=${s.dur},trim=end_frame=${n},setpts=PTS-STARTPTS,scale=1920:1080,format=yuv420p,setsar=1[v${i}]`)
    }
    t += s.dur
  })
  g.push(P.segs.map((_, i) => `[v${i}]`).join('') + `concat=n=${P.segs.length}:v=1:a=0[cat]`)
  const f = []
  // card text (only seen in the base alone: in the final video the camera covers it)
  for (const [a, b] of cards) {
    const closing = b === END
    f.push(dt('ParallaX', { x: CX, y: 190, size: 160, color: ACCENT, bold: true, a, b }))
    f.push(dt(closing ? CLOSE[0] : 'Chromatic difference imaging for the SPHEREx sky', { x: CX, y: 420, size: 50, color: INK, a, b }))
    f.push(dt('Team ZENITH LABS', { x: CX, y: 520, size: 36, color: MUTED, a, b }))
  }
  // lower thirds: opening and closing text
  for (const [[a, b], L] of [[P.ltOpen, OPEN], [P.ltClose, CLOSE]]) {
    f.push(`drawbox=x=${LT.x}:y=${LT.y}:w=${LT.w}:h=${LT.h}:color=${PANEL}:t=fill:${en(a, b)}`)
    f.push(`drawbox=x=${LT.x}:y=${LT.y}:w=10:h=${LT.h}:color=${ACCENT}:t=fill:${en(a, b)}`)
    f.push(dt(L[0], { x: LT.x + 36, y: LT.y + 16, size: 44, color: INK, bold: true, a, b }))
    f.push(dt(L[1], { x: LT.x + 36, y: LT.y + 82, size: 32, color: INK, a, b }))
    f.push(dt(L[2], { x: LT.x + 36, y: LT.y + 132, size: 30, color: MUTED, a, b }))
  }
  for (const [a, b, s] of P.notes) {
    f.push(dt(s, { x: CX, y: 836, size: 30, color: INK, a, b, box: `:box=1:boxcolor=${BG}@0.85:boxborderw=12` }))
  }
  // subtitles: white on a semi-opaque dark band
  f.push(`drawbox=x=${SUB.x}:y=${SUB.y}:w=${SUB.w}:h=${SUB.h}:color=black@0.62:t=fill`)
  for (const c of cues) {
    c.lines.forEach((l, i) => {
      const y = c.lines.length === 1 ? SUB.y + 36 : SUB.y + 10 + i * 56
      f.push(dt(l, { x: CX, y, size: 44, color: 'white', bold: true, a: c.a, b: c.b }))
    })
  }
  g.push(`[cat]${f.join(',')}[out]`)
  writeFileSync(join(B, `base_${key}.graph`), g.join(';\n'), 'utf8')
  const base = join(DIR, `base_${key}.mp4`)
  run([...inputs, '-f', 'lavfi', '-t', String(END), '-i', 'anullsrc=r=48000:cl=stereo', '-/filter_complex', `base_${key}.graph`,
    '-map', '[out]', '-map', `${inputs.length / 2}:a`, '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p', '-r', String(FPS),
    '-c:a', 'aac', '-b:a', '96k', '-t', String(END), '-movflags', '+faststart', base])

  writeFileSync(join(DIR, `timeline_${key}.json`), JSON.stringify({
    video: key, end: END, firstCue: cues[0].a, hardLimit: key === '30s' ? 29.9 : 120.0,
    camFull: P.camFull, lowerThirds: [P.ltOpen, P.ltClose], sub: SUB, lt: LT, countdown: COUNT,
    lines: lines.map((l) => ({ a: l.a, b: l.b, who: l.who })),
  }, null, 1) + '\n')

  // ---- teleprompter ----
  const col = (who) => (who === 'Abed' ? ACCENT : BLUE)
  const h = []
  h.push(`color=c=${BG}:s=1920x1080:r=${FPS}:d=${END},format=yuv420p[bg]`)
  h.push(`[0:v]scale=768:432[pv]`)
  h.push(`color=c=${ACCENT}:s=1920x12:r=${FPS}:d=${END}[bar]`)
  const prog = lines.map((l) => `gte(t,${l.a})*lt(t,${l.b})*(t-${l.a})/${(l.b - l.a).toFixed(3)}`).join('+')
  const m = []
  m.push(`drawtext=${FONTB}:text='%{pts\\:hms}':fontsize=96:fontcolor=white:x=48:y=40`)
  m.push(dt(`of ${Math.floor(END / 60)}:${(END % 60).toFixed(1).padStart(4, '0')}   (hours:minutes:seconds)`, { x: 52, y: 160, size: 34, color: MUTED }))
  m.push(dt('Read the big line. The bar shows how much of its time is used.', { x: 52, y: 220, size: 30, color: MUTED }))
  lines.forEach((l, i) => {
    const cam = /^ON CAMERA/.test(l.pic) ? 'look at the camera' : 'the screen clip is showing'
    m.push(dt(`${l.who.toUpperCase()}   (${cam})`, { x: 48, y: 380, size: 54, color: col(l.who), bold: true, a: l.a, b: l.b }))
    wrap(l.text, 54).forEach((w, j) => m.push(dt(w, { x: 48, y: 500 + j * 80, size: 62, color: 'white', bold: true, a: l.a, b: l.b })))
    const nx = lines[i + 1]
    if (nx) {
      m.push(dt(`NEXT: ${nx.who.toUpperCase()}`, { x: 48, y: 926, size: 30, color: col(nx.who), bold: true, a: l.a, b: l.b }))
      let nl = wrap(nx.text, 100)
      if (nl.length > 2) nl = [nl[0], nl[1].slice(0, 96) + ' ...']
      nl.forEach((w, j) => m.push(dt(w, { x: 48, y: 968 + j * 46, size: 34, color: MUTED, a: l.a, b: l.b })))
    } else m.push(dt('LAST LINE: then hold still for one second', { x: 48, y: 926, size: 30, color: MUTED, bold: true, a: l.a, b: l.b }))
  })
  h.push(`[bg][pv]overlay=x=1104:y=24[m1]`)
  h.push(`[m1][bar]overlay=x='-1920+1920*(${prog})':y=462:eval=frame[m2]`)
  h.push(`[m2]${m.join(',')}[main]`)
  // countdown: 5 4 3 2 1 with a short 1 kHz beep each, then a long beep at zero
  const c = []
  for (let k = 0; k < 5; k++) c.push(dt(String(5 - k), { x: CX, y: 250, size: 420, color: ACCENT, bold: true, a: k, b: k + 1 }))
  c.push(dt('0', { x: CX, y: 250, size: 420, color: 'white', bold: true, a: 5, b: COUNT }))
  c.push(dt('Start speaking when the long beep ends', { x: CX, y: 110, size: 56, color: INK, bold: true }))
  c.push(dt(`FIRST LINE: ${lines[0].who.toUpperCase()}`, { x: CX, y: 800, size: 36, color: col(lines[0].who), bold: true }))
  c.push(dt(lines[0].text, { x: CX, y: 860, size: 50, color: 'white' }))
  h.push(`color=c=${BG}:s=1920x1080:r=${FPS}:d=${COUNT},format=yuv420p,${c.join(',')}[cd]`)
  h.push(`sine=frequency=1000:sample_rate=48000:duration=${COUNT},volume='0.5*(lt(t,5)*lt(mod(t,1),0.12)+gte(t,5))':eval=frame,aformat=channel_layouts=stereo[cda]`)
  h.push(`anullsrc=r=48000:cl=stereo,atrim=duration=${END}[sil]`)
  h.push(`[cd][cda][main][sil]concat=n=2:v=1:a=1[out][aout]`)
  writeFileSync(join(B, `tele_${key}.graph`), h.join(';\n'), 'utf8')
  const tele = join(DIR, `teleprompter_${key}.mp4`)
  run(['-i', base, '-/filter_complex', `tele_${key}.graph`, '-map', '[out]', '-map', '[aout]', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
    '-pix_fmt', 'yuv420p', '-r', String(FPS), '-c:a', 'aac', '-b:a', '128k', '-t', String(COUNT + END), '-movflags', '+faststart', tele])
  console.log(`base_${key}.mp4         duration,size = ${probe(base)}   (script ends at ${END})`)
  console.log(`teleprompter_${key}.mp4 duration,size = ${probe(tele)}   (countdown ${COUNT} + ${END})`)
}

for (const key of process.argv[2] ? [process.argv[2]] : ['30s', '2min']) build(key)
