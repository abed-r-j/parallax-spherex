/**
 * "How it works" in plain language, and the About / Credits page with the required
 * acknowledgements and disclosures.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { useEffect, useState } from 'react'
import type { PackIndex } from '../lib/types'
import { DEFAULT_ENGINE_URL } from '../lib/engine'
import { loadManifest, type SkyManifest } from '../lib/skyindex'

const DET = ['var(--d1)', 'var(--d2)', 'var(--d3)', 'var(--d4)', 'var(--d5)', 'var(--d6)']

function FilterFigure() {
  return (
    <figure>
      <svg viewBox="0 0 640 210" role="img" aria-label="A detector covered by a filter whose colour changes smoothly from one edge to the other. A star lands at a different place, and so at a different colour, on each visit.">
        <defs>
          <linearGradient id="lvf" x1="0" x2="1">
            <stop offset="0" stopColor="var(--d1)" /><stop offset="0.5" stopColor="var(--d3)" /><stop offset="1" stopColor="var(--d5)" />
          </linearGradient>
        </defs>
        <rect x="40" y="34" width="560" height="110" fill="url(#lvf)" opacity="0.55" />
        <rect x="40" y="34" width="560" height="110" fill="none" stroke="var(--line)" />
        {[[130, 70, 'visit 1'], [330, 104, 'visit 2'], [505, 60, 'visit 3']].map(([x, y, t]) => (
          <g key={t as string}>
            <circle cx={x as number} cy={y as number} r="7" fill="var(--ink)" />
            <line x1={x as number} x2={x as number} y1={(y as number) + 10} y2="158" stroke="var(--ink)" strokeDasharray="3 3" />
            <text x={x as number} y="176" textAnchor="middle">{t}</text>
          </g>
        ))}
        <text x="40" y="24">shorter wavelength</text>
        <text x="600" y="24" textAnchor="end">longer wavelength</text>
        <text x="320" y="200" textAnchor="middle">one detector: the filter colour changes smoothly from left to right</text>
      </svg>
      <figcaption>The same star, three visits. It falls on a different part of the filter each time, so it is photographed in three different colours.</figcaption>
    </figure>
  )
}

function TemplateFigure() {
  const pts = [[70, 120], [120, 104], [175, 92], [240, 96], [300, 84], [370, 70], [430, 74], [500, 58], [560, 50]]
  return (
    <figure>
      <svg viewBox="0 0 640 200" role="img" aria-label="Measurements of one pixel at many wavelengths from earlier passes trace its spectrum. The new frame is compared with the spectrum at its own wavelength, not with a single earlier frame.">
        <polyline points={pts.map((p) => p.join(',')).join(' ')} fill="none" stroke="var(--m-chroma)" strokeWidth="2" />
        {pts.map(([x, y]) => <circle key={x} cx={x} cy={y} r="4" fill="var(--pass2)" />)}
        <circle cx="335" cy="46" r="6" fill="var(--pass3)" />
        <line x1="335" y1="52" x2="335" y2="77" stroke="var(--pass3)" strokeWidth="2" />
        <text x="345" y="44">new frame: brighter than predicted here</text>
        <circle cx="240" cy="150" r="4" fill="var(--pass2)" />
        <text x="250" y="154">the same pixel in the other survey passes</text>
        <line x1="40" y1="170" x2="600" y2="170" stroke="var(--line)" />
        <text x="320" y="190" textAnchor="middle">wavelength</text>
        <text x="20" y="100" transform="rotate(-90 20 100)" textAnchor="middle">brightness</text>
      </svg>
      <figcaption>The chromatic template: each pixel&rsquo;s own spectrum, built from the other passes, predicts what the new frame should show at its exact colour.</figcaption>
    </figure>
  )
}

export function HowItWorks() {
  return (
    <article className="prose">
      <h1>How ParallaX works</h1>
      <p>
        SPHEREx is a space telescope launched in 2025. Every six months it photographs the whole sky in 102 infrared colours, from 0.75 to 5 micron:
        light redder than the eye can see. ParallaX lets you play its pictures of one patch of sky in time order, to look for things that move or change.
      </p>

      <h2>Why every visit has a different colour</h2>
      <p>
        Most cameras change colour by swapping filters. SPHEREx has no moving parts in front of its six detectors. Each detector sits behind one
        filter whose colour changes smoothly from one edge to the other, and the telescope steps the sky across it. Where a star lands decides the colour it is seen in.
      </p>
      <FilterFigure />
      <p>
        So when SPHEREx comes back to the same star, days or months later, the star lands somewhere else on the filter. In the map of dots beside every field you can see it directly:
        no two visits share a wavelength.
      </p>
      <div className="row wrap" aria-hidden="true">
        {DET.map((c, i) => <span key={c} className="small"><i className="dot" style={{ background: c }} />detector {i + 1}</span>)}
      </div>

      <h2>Why that matters for spotting change</h2>
      <p>
        The classic way to find something that changed is to blink two pictures, or subtract one from the other. With SPHEREx, the two pictures were taken in two colours.
        Every star is a little brighter in one colour than in the other, so the subtraction lights up everywhere, and real changes drown in false ones.
        The usual fix is to compare only pairs whose colours match. That loses few frames, but each difference is as noisy as a single partner frame.
      </p>

      <h2>What the chromatic template does</h2>
      <p>
        ParallaX corrects instead of rejecting. For each pixel it collects what that pixel looked like at every colour during the <em>other</em> survey passes: that is the pixel&rsquo;s spectrum.
        From it, it predicts what an unchanging sky would look like in the new frame, pixel by pixel, at exactly that frame&rsquo;s colours. Subtract the prediction, and far fewer false alarms are left.
      </p>
      <TemplateFigure />
      <p>
        The <b>Three-way</b> view shows the same frame differenced three ways: against a naive partner, against a colour-matched partner, and against the chromatic template.
        The <b>Ledger</b> tab gives the measured numbers for each field: how many false detections each method leaves, how many frames it can use, and how faint a new source it can find.
      </p>

      <h2>How to spot something that moved</h2>
      <ol>
        <li>Open a field and press play. For nearby stars, start with the sequence &ldquo;By survey pass&rdquo;: it blinks one clean stack per pass, six months apart.</li>
        <li>Watch the star against its neighbours. The amber marker shows where the catalogue says it should be on that date; the coloured dots show where it was measured in each pass.</li>
        <li>Switch to <b>Subtract</b> (or <b>Gated pair</b>). A star that moved leaves a bright lobe where it is now and a dark lobe where it used to be. For a shift of one or two pixels these show the two lobes better than the chromatic difference.</li>
        <li>Click the star. Its spectrum is built on the spot from every frame, and the light curve shows whether it also changed in brightness.</li>
      </ol>

      <h2>What to keep in mind</h2>
      <ul>
        <li>SPHEREx pixels are large: 6.15 arcseconds. Even the fastest star in the sky, Barnard&rsquo;s Star, moves less than two pixels between the first and the latest pass. Use the smooth display to see it.</li>
        <li>The star images are sharper than the pixels, so a star&rsquo;s pixel values change with its exact position even when nothing else does. The pipeline measures that effect and includes it in its noise.</li>
        <li>Very faint objects, such as the brown dwarf WISE 0855&minus;0714, cannot be seen in one frame. Only the stacks of a whole pass go deep enough.</li>
        <li>The brightest stars saturate; their cores are blank.</li>
        <li>A solar-system object is still there in the exposure two minutes later, but has moved on by the next visit hours later. Known asteroids are marked when the field carries them.</li>
        <li>Parallax (distance) is not measured reliably, and Planet X is the motivation, not a claim.</li>
      </ul>
    </article>
  )
}

/** What the sky index of this site covers, read from its manifest. */
function IndexCoverage() {
  const [m, setM] = useState<SkyManifest | null>(null)
  const [missing, setMissing] = useState(false)
  useEffect(() => {
    let on = true
    loadManifest().then((v) => on && setM(v), () => on && setMissing(true))
    return () => {
      on = false
    }
  }, [])
  if (missing) return <> This copy of the site carries no sky index, so the live route is not available here.</>
  if (!m) return null
  let lo = Infinity
  let hi = -Infinity
  for (const s of m.shards) {
    lo = Math.min(lo, s[4])
    hi = Math.max(hi, s[5])
  }
  const day = (mjd: number) => new Date((mjd - 40587) * 86400000).toISOString().slice(0, 10)
  const total = m.rows?.total
  const gaps = m.coverage?.missing_days?.length ?? 0
  return (
    <>
      {' '}The index on this site was built on {m.built_utc.slice(0, 10)} and lists {typeof total === 'number' ? total.toLocaleString('en-US') : 'all'} images
      taken from {day(lo)} to {day(hi)} ({m.collections.join(', ')}){m.coverage ? (m.coverage.complete || !gaps ? ', with no day missing' : `, with ${gaps} day${gaps === 1 ? '' : 's'} still missing`) : ''}.
      Images released after that date are not listed.
    </>
  )
}

export function About({ index, dois }: { index: PackIndex | null; dois: string[] }) {
  return (
    <article className="prose">
      <h1>About ParallaX</h1>
      <p>
        ParallaX is the entry of team ZENITH LABS (Abed El Rahmane Jaafir, Mohamad Alayli) to the NASA Space Apps Challenge 2026, Beirut, for the challenge
        &ldquo;Planet X and SPHEREx&rdquo;. Planet X is the motivation, not a claim: this tool shows how to look for moving and varying objects in SPHEREx data, and reports
        only what it measures.
      </p>

      <h2>Data and acknowledgements</h2>
      <blockquote>
        This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a
        joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration.
      </blockquote>
      <blockquote>
        This research has made use of the NASA/IPAC Infrared Science Archive, which is funded by the National Aeronautics and Space Administration and operated by the
        California Institute of Technology.
      </blockquote>
      <p>
        SPHEREx Level-2 spectral images, data release identifiers:{' '}
        {dois.length ? dois.map((d, i) => <span key={d}>{i ? ', ' : ''}<a href={`https://doi.org/${d}`} rel="noreferrer" target="_blank">doi:{d}</a></span>) : 'listed here once a field is loaded'}.
        {index?.generated ? ` Fields generated ${index.generated.slice(0, 10)} with pipeline version ${index.pipeline ?? '?'}.` : ''}
      </p>
      <ul>
        <li>Star positions and proper motions: Gaia Data Release 3, European Space Agency (ESA) Gaia mission, processed by the Gaia Data Processing and Analysis Consortium.</li>
        <li>Infrared sources: CatWISE2020 catalogue, from WISE and NEOWISE data.</li>
        <li>Known solar-system objects: SkyBoT, IMCCE, Observatoire de Paris (Berthier et al. 2006).</li>
        <li>Ephemerides: NASA/JPL Solar System Dynamics. Data retrieved on 13 November 2026. Horizons System. https://ssd.jpl.nasa.gov. Queried by the offline pipeline, not by this page.</li>
        <li>Mission paper: Bock et al. 2026, The SPHEREx Satellite Mission, ApJ 999, 139, doi:10.3847/1538-4357/ae2be2.</li>
        <li>Pipeline built with Astropy, NumPy and SciPy.</li>
      </ul>

      <h2>How it is made</h2>
      <p>
        A Python pipeline downloads the SPHEREx cutouts, builds the chromatic templates and the three kinds of difference, measures them, and writes one small data pack per field.
        This website only reads those packs. It is a static site: no server and no tracking. With the precomputed fields it makes no outside requests and works offline.
      </p>
      <h2>Any other position: fetched live in your browser</h2>
      <p>
        For coordinates outside the precomputed fields, the page can build a field itself. A compact index, shipped with the site, lists every public SPHEREx Level-2 image:
        where it points, when it was taken and its file name. Your browser then reads the pixels straight from the SPHEREx Level-2 spectral images in the NASA/IPAC Infrared Science Archive
        public bucket on Amazon Web Services (<code>nasa-irsa-spherex</code>): from each 65 MB file only the header, the few detector rows that cover the field and the wavelength table.
        These are the only outside requests the site makes, and only when you ask for a live field.
        <IndexCoverage />
      </p>
      <p>
        A live field shows the frames, the per-pass stacks, spectra, add and subtract and the two pair differences. To stay small it removes one robust sky level per frame
        instead of the archive&rsquo;s zodiacal-light model, estimates the noise from the frame itself, and does not read the pixel flags, so hot pixels and cosmic rays are not masked.
        The chromatic template, the three-way ledger and the searches are made only by the Python pipeline. To get those for a new position, run a ParallaX engine
        on your own computer (by default at {DEFAULT_ENGINE_URL}) and the page will use it.
      </p>
      <p>
        To embed a view in another page, use the Share button: the address carries the coordinates, field of view, detector, mode and frame, and <code>embed=1</code> hides everything but the picture and its player.
      </p>

      <h2>Use of SI</h2>
      <p>
        The team chose the challenge, the goal and the direction: a comparison of SPHEREx dates that accounts for the changing wavelength. The specific method
        (a per-pixel chromatic template checked against two baselines) was worked out with an SI assistant (Claude, by Anthropic), which also surveyed existing tools,
        wrote the code and drafted the documents under the team&rsquo;s direction. The team reviewed the work, ran it and is responsible for it.
        Every number shown is computed by the project&rsquo;s own code from the published SPHEREx data and can be reproduced with the pipeline. No SI-generated images are used.
      </p>

      <h2>Licence</h2>
      <p>Code: Apache-2.0. Fonts: IBM Plex (SIL Open Font License 1.1), bundled with the site.</p>
      <p>Not affiliated with or endorsed by NASA.</p>
    </article>
  )
}
