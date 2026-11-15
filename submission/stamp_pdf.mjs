// Document properties for the PDFs built with headless Chrome. Chrome's page.pdf() can set only
// the title (from <title>), so the build scripts call this after writing their PDF: it runs
// submission/set_metadata.py (pypdf, in the pipeline's Python environment), which writes Title,
// Author, Subject, Keywords and a Comments property carrying the SI statement.
// If Python or pypdf is missing the PDF is left as built and a warning is printed.
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))

export function stampMetadata(pdf) {
  const venv = join(here, '..', 'pipeline', '.venv')
  const python = [join(venv, 'Scripts', 'python.exe'), join(venv, 'bin', 'python')].find(existsSync) ?? 'python'
  const r = spawnSync(python, [join(here, 'set_metadata.py'), pdf], { encoding: 'utf8' })
  const ok = r.status === 0
  console.log(ok ? `document properties written: ${(r.stdout.match(/\/Author: .*/) ?? [''])[0].trim()}`
    : `WARNING: document properties NOT written (${(r.error?.message ?? r.stderr ?? r.stdout ?? '').trim().split('\n').pop()}). Run: python submission/set_metadata.py`)
  return ok
}