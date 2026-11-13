// Fallback for shot_11_live_fetch.mp4, for the case where the network or the archive is
// not available when the clips are regenerated: a slideshow of three real screenshots of an
// earlier live fetch of the same position (M51), taken by web/scripts/live-check.mjs and kept
// in assets/live_fallback_*.png. Silent, 1920x1080, 30 frames per second.
//
//   node video/make_fallback.mjs
//
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { copyFileSync, existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const assets = resolve(here, '..', 'assets')
const screens = resolve(here, '..', '..', 'data', 'screens')
const parts = [['progress', 3], ['partial', 3], ['done', 4]]
const args = ['-y', '-loglevel', 'error']
for (const [name, seconds] of parts) {
  const kept = join(assets, `live_fallback_${name}.png`)
  const src = join(screens, `live-m51-${name}.png`)
  if (existsSync(src)) copyFileSync(src, kept) // data/ is git-ignored, so keep our own copy
  args.push('-loop', '1', '-t', String(seconds), '-i', kept)
}
const fit = (i) => `[${i}:v]scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x10161f,setsar=1,fps=30[v${i}]`
args.push('-filter_complex', `${parts.map((_, i) => fit(i)).join(';')};${parts.map((_, i) => `[v${i}]`).join('')}concat=n=${parts.length}:v=1:a=0,format=yuv420p[v]`,
  '-map', '[v]', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-movflags', '+faststart', '-an',
  '-metadata', 'title=ParallaX screen capture: live fetch (fallback stills)', join(here, 'shot_11b_live_fetch_fallback.mp4'))
const r = spawnSync('ffmpeg', args, { encoding: 'utf8' })
if (r.status !== 0) throw new Error(r.stderr)
console.log('shot_11b_live_fetch_fallback.mp4  10.00 s')
