// Writes the two video scripts and their English subtitle files from one list of cues, so
// that the scripts and the subtitles can never disagree:
//
//   node video/make_scripts.mjs
//
// -> SCRIPT_30s.md, subs_30s.srt, SCRIPT_2min.md, subs_2min.srt (in this folder).
// It refuses to write if a script breaks its limit (30 s: at most 70 spoken words, end at
// 28.5 s; 2 min: at most 290 words, end at 1:55) or if a line would have to be spoken faster
// than 165 words per minute. Every number spoken is from docs/RESULTS.md.
// SI disclosure: drafted with the help of an SI coding assistant (Claude, by Anthropic); to be
// reviewed and spoken by the team. No SI-generated voices or faces are used.
import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const A = 'Abed'
const M = 'Mohamad'
const CAM = 'ON CAMERA'

// 30 seconds: [start s, end s, speaker, picture, spoken text]
const S30 = {
  file: '30s', title: 'ParallaX: project demo video (30 seconds or less)', maxWords: 70, end: 28.5, hard: 30,
  cues: [
    [0.0, 3.0, A, `${CAM}: both members, side by side. Abed speaks, Mohamad waves.`, 'We are Abed and Mohamad, team ZENITH LABS.'],
    [3.0, 7.0, M, `${CAM}: both members. Mohamad speaks.`, 'Pluto was found by blinking two photos. We blink SPHEREx.'],
    [7.0, 11.5, A, 'SCREEN: shot_01_type_coordinates.mp4 (from 3.0 s: typing the coordinates, landing on the field). Text over the first second: "ParallaX: chromatic difference imaging for the SPHEREx sky".', 'This is ParallaX: it finds fainter changes in the infrared sky.'],
    [11.5, 15.5, M, 'SCREEN: shot_03_time_wavelength.mp4 (2 s), then shot_04_naive_false_alarms.mp4 (2 s).', 'SPHEREx never repeats a colour, so stars become false alarms.'],
    [15.5, 20.5, A, 'SCREEN: shot_05_three_way.mp4 (from 2.5 s, where the naive panel glows and the template panel does not). Text: "SPHEREx data: NASA/IPAC IRSA".', 'From NASA’s open data, we predict each frame’s own colours, and subtract.'],
    [20.5, 25.0, M, 'SCREEN: shot_11_live_fetch.mp4 (the progress bar and the picture arriving, sped up 2x), or shot_12_asteroid_europa.mp4.', 'Next: anyone types coordinates and explores the changing sky.'],
    [25.0, 28.5, A, `${CAM}: both members. One closing line, then hold still for one second.`, 'ParallaX: open source, open data.'],
  ],
}
// 2 minutes: [section or '', speaker, picture, spoken text]; times are computed from the word counts
const S120 = {
  file: '2min', title: 'ParallaX: two-minute video for the local judges', maxWords: 290, end: 115, hard: 120,
  auto: [
    ['Introduction', A, `${CAM}: both members.`, 'We are ZENITH LABS. I am Abed El Rahmane Jaafir.'],
    ['', M, `${CAM}: both members.`, 'And I am Mohamad Alayli. This is ParallaX, for the challenge Planet X and SPHEREx.'],
    ['Why we chose this approach', M, `${CAM}: Mohamad alone, or keep both.`, 'Pluto was found by blinking two photographs. The challenge asks for a tool to do that with the SPHEREx infrared sky.'],
    ['', M, 'SCREEN: shot_03_time_wavelength.mp4, then shot_04_naive_false_alarms.mp4.', 'But SPHEREx never photographs a spot in the same colour twice, and its pixels are coarse. Blink two dates, and stars light up as false alarms.'],
    ['', M, 'SCREEN: shot_06_chromatic.mp4.', 'So we chose to correct the colour first, and only then compare.'],
    ['Data, software, methods and tools', A, 'SCREEN: shot_01_type_coordinates.mp4. Text over the picture: "Data: SPHEREx (NASA/IPAC IRSA), Gaia DR3, CatWISE2020, JPL Horizons, IMCCE SkyBoT".', 'Our data is open: SPHEREx images from the NASA/IPAC archive, with Gaia, CatWISE, JPL Horizons and SkyBoT.'],
    ['', A, 'SCREEN: shot_11_live_fetch.mp4 (whole fetch, sped up 2x). Text: "Python pipeline + React / TypeScript app, no server".', 'A Python pipeline does the science, and a React and TypeScript app shows it. An index of more than 1.6 million public images lets the browser fetch any position, with no server.'],
    ['Demonstration', M, 'SCREEN: shot_02_blink_barnard.mp4.', 'Here is Barnard’s Star, blinked pass by pass: you can see it move.'],
    ['', M, 'SCREEN: shot_05_three_way.mp4 (whole clip).', 'Here is one frame differenced three ways: naive, wavelength-matched, and our chromatic template, which predicts the frame at its own wavelengths from the other passes.'],
    ['', M, 'SCREEN: shot_07_click_spectrum.mp4, then shot_12_asteroid_europa.mp4.', 'Click any star for its spectrum. And here an asteroid crosses, right under its predicted label.'],
    ['What makes it distinctive', A, 'SCREEN: shot_09_ledger.mp4. Text: "1.2 to 1.9 times fainter than the gated pair, at a matched false-detection rate (blank sky)".', 'What is distinctive: we publish the measurements. On blank sky, at the same false-alarm rate, the template finds moving sources 1.2 to 1.9 times fainter than a wavelength-matched pair.'],
    ['Development process, challenges and limitations', M, `${CAM}: Mohamad.`, 'We started on the twelfth and thirteenth of November, before the on-site event, as the organizers allowed. An SI coding assistant helped; we directed and checked its work, and an independent review re-ran the code.'],
    ['', A, `${CAM}: Abed. Optional cut-away: shot_08_subtract_passes.mp4.`, 'The hard part was honesty. Bright stars saturate, parallax is not measured, and this is not a Planet Nine detector.'],
    ['', A, `${CAM}: both members.`, 'ParallaX is open source. Thank you.'],
  ],
}

const words = (t) => t.split(/\s+/).filter((w) => /[A-Za-z0-9]/.test(w)).length
const clock = (s) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`
const stamp = (s) => {
  const ms = Math.round(s * 1000)
  const p = (v, n = 2) => String(v).padStart(n, '0')
  return `${p(Math.floor(ms / 3600000))}:${p(Math.floor(ms / 60000) % 60)}:${p(Math.floor(ms / 1000) % 60)},${p(ms % 1000, 3)}`
}
/** Give every cue a pause of 0.4 s plus a share of the remaining time in proportion to its words. */
function retime(S) {
  const pause = 0.4
  const total = S.auto.reduce((a, c) => a + words(c[3]), 0)
  const k = (S.end - pause * S.auto.length) / total
  let t = 0
  S.sections = []
  S.cues = S.auto.map(([section, who, pic, text], i) => {
    const a = t
    t = i === S.auto.length - 1 ? S.end : Math.round((t + pause + words(text) * k) * 2) / 2
    if (section) S.sections.push([section, a])
    return [a, t, who, pic, text]
  })
}
/** Split a sentence into subtitle blocks of at most two lines of 42 characters. */
function blocks(text) {
  const lines = []
  let line = ''
  for (const w of text.split(' ')) {
    if ((line + ' ' + w).trim().length > 42) { lines.push(line); line = w } else line = (line + ' ' + w).trim()
  }
  if (line) lines.push(line)
  const out = []
  for (let i = 0; i < lines.length; i += 2) out.push(lines.slice(i, i + 2).join('\n'))
  return out
}

retime(S120)
for (const S of [S30, S120]) {
  const total = S.cues.reduce((a, c) => a + words(c[4]), 0)
  const last = S.cues.at(-1)[1]
  S.cues.forEach((c, i) => { if (i && Math.abs(c[0] - S.cues[i - 1][1]) > 1e-9) throw new Error(`${S.file}: gap or overlap at cue ${i + 1}`) })
  const rate = S.cues.map((c) => words(c[4]) / (c[1] - c[0]) * 60)
  if (total > S.maxWords) throw new Error(`${S.file}: ${total} spoken words, limit ${S.maxWords}`)
  if (last > S.end + 1e-9) throw new Error(`${S.file}: ends at ${last} s, target ${S.end} s`)
  if (Math.max(...rate) > 165) throw new Error(`${S.file}: a line needs ${Math.max(...rate).toFixed(0)} words per minute`)
  const by = (who) => S.cues.filter((c) => c[2] === who).reduce((a, c) => a + words(c[4]), 0)
  let md = `# ${S.title}\n\n`
  md += `SI disclosure: drafted with the help of an SI coding assistant (Claude, by Anthropic); to be reviewed and spoken by the team. Generated by \`make_scripts.mjs\` together with \`subs_${S.file}.srt\`: edit the cues there and run it again.\n\n`
  md += `* Target length **${clock(S.end)}** (hard limit ${clock(S.hard)}${S.file === '30s' ? ': a longer video makes the project ineligible for Global Judging' : ', as asked by the local organizers'}).\n`
  md += `* Spoken words: **${total}** (limit ${S.maxWords}); Abed ${by(A)}, Mohamad ${by(M)}. Average ${(total / last * 60).toFixed(0)} words per minute; fastest line ${Math.max(...rate).toFixed(0)}.\n`
  md += `* Screen clips are in this folder (see \`SHOTLIST.md\`); they are silent. Subtitles: \`subs_${S.file}.srt\`.\n`
  if (S.file === '30s') md += `* Structure suggested by the organizers: 0:00 names and team; 0:02 the challenge and why; 0:05 project name and tagline; 0:10 how it works, with the product on screen and how NASA open data made it possible; 0:20 to 0:30 the future. This script keeps that order; the first three steps start one to two seconds later than suggested so that nobody has to rush.\n`
  else md += `* The five required points, in order: ${S.sections.filter(([n]) => n !== 'Introduction').map(([n, t]) => `${n.toLowerCase()} (${clock(t)})`).join('; ')}.\n`
  md += `\n| Time | Who | Picture | Words | Says |\n|---|---|---|---|---|\n`
  for (const [a, b, who, pic, text] of S.cues) md += `| ${clock(a)} to ${clock(b)} | ${who} | ${pic} | ${words(text)} | "${text}" |\n`
  md += `\n## Notes\n\n`
  md += `* Say the lines as written, or shorter. Do not add numbers: every number here is from \`docs/RESULTS.md\`.\n`
  md += `* Never say that ParallaX found Planet X or measured a parallax.\n`
  md += `* Put this credit as small text over the last seconds (it does not need to be spoken): "SPHEREx data: NASA/IPAC IRSA. Not affiliated with or endorsed by NASA. Made with the help of an SI coding assistant."\n`
  md += `* Paste the two full acknowledgement sentences (SPHEREx and NASA/IPAC IRSA, as in the README) and the SI statement into the video description where the video is hosted.\n`
  if (S.file === '2min') md += `* "1.2 to 1.9 times fainter" is against the wavelength-gated pair, on blank sky, with every method tuned to the same false-detection rate (RESULTS.md section 2.1). "More than 1.6 million" is 1,628,230 images. Development began on 12-13 November 2026, before the on-site event, after the local organizers allowed early preparation. The asteroid is (52) Europa on 20-21 August 2025; its label comes from JPL Horizons as seen from SPHEREx.\n`
  writeFileSync(join(here, `SCRIPT_${S.file}.md`), md)

  let srt = ''
  let n = 1
  for (const [a, b, , , text] of S.cues) {
    const bl = blocks(text)
    const chars = bl.map((x) => x.length)
    const sum = chars.reduce((p, q) => p + q, 0)
    let t = a
    bl.forEach((x, i) => {
      const e = i === bl.length - 1 ? b : t + (b - a) * chars[i] / sum
      srt += `${n++}\n${stamp(t)} --> ${stamp(e)}\n${x}\n\n`
      t = e
    })
  }
  writeFileSync(join(here, `subs_${S.file}.srt`), srt)
  console.log(`${S.file}: ${total} words (limit ${S.maxWords}), ends ${clock(last)}, ${n - 1} subtitles, average ${(total / last * 60).toFixed(0)} wpm, fastest ${Math.max(...rate).toFixed(0)} wpm; per cue ${S.cues.map((c) => words(c[4])).join(',')}`)
}
