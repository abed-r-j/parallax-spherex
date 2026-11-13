/**
 * Tests of the in-browser live path: the sky index reader (test vectors of
 * docs/SKY_INDEX.md and the real shards), the FITS and TAN-SIP code against numbers made
 * with astropy on a real SPHEREx header, and the whole field builder on synthetic files.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { decodeFrame, stackImage } from './decode'
import { FITS_BLOCK, dataBytes, float32BE, int32BE, lastHduOffset, need, num, parseHeader, readWaveTable, str, waveAt } from './fits'
import {
  LIVE_ENCODING, assignCampaigns, buildLiveField, estimateLive, liveGridN, liveKey, neighbourNoise, normaliseSpec, planeFit, robustSky, robustStack, subsetEvenly,
  type LiveProgress,
} from './live'
import { lamAt } from './photometry'
import { chromaProduct, naiveProduct } from './products'
import { pixToWorld, wcsFromHeader, worldToPix } from './sip'
import {
  cellsForPoint, checkManifest, footprintMargin, querySkyIndex, readRecord, recordKey, scanShard, shardName, shardsForPoint,
  type SkyHit, type SkyManifest, type SkyQuery,
} from './skyindex'
import { parseQuery, toQuery } from './urlstate'
import { pixToSky } from './wcs'

const INDEX = resolve('public/skyindex')
const FIX = resolve('src/lib/__fixtures__')
const haveIndex = existsSync(resolve(INDEX, 'manifest.json'))
const manifest: SkyManifest | null = haveIndex ? (JSON.parse(readFileSync(resolve(INDEX, 'manifest.json'), 'utf8')) as SkyManifest) : null
const toBuffer = (b: Buffer): ArrayBuffer => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer

function queryLocal(ra: number, dec: number): SkyHit[] {
  const out: SkyHit[] = []
  for (const [b, c, p] of shardsForPoint(manifest!, ra, dec)) scanShard(toBuffer(readFileSync(resolve(INDEX, shardName(b, c, p)))), ra, dec, manifest!, out)
  return out.sort((p, q) => p.mjd - q.mjd)
}

describe('sky index: the test vectors of the specification', () => {
  const grid = { band_height_deg: 5, cells_per_band: [3, 9, 16, 22, 28, 33, 39, 44, 49, 53, 57, 61, 64, 67, 69, 70, 71, 72, 72, 71, 70, 69, 67, 64, 61, 57, 53, 49, 44, 39, 33, 28, 22, 16, 9, 3] }
  const m = { grid, search_radius_deg: 2.58 }
  it('selects the documented cells', () => {
    const cases: [number, number, [number, number][]][] = [
      [269.4463, 4.768, [[18, 53], [18, 54], [19, 52], [19, 53]]],
      [202.4696, 47.1953, [[26, 29], [26, 30], [27, 27], [27, 28]]],
      [133.7688, -7.2429, [[16, 25], [16, 26], [17, 26], [17, 27]]],
      [270.0, 66.56, [[30, 24], [30, 25], [31, 20], [31, 21]]],
      [0.05, 10.0, [[19, 70], [19, 0], [20, 69], [20, 0]]],
      [90.0, -66.56, [[4, 6], [4, 7], [5, 7], [5, 8]]],
      [0.0, 90.0, [[35, 0], [35, 1], [35, 2]]],
      [0.0, -90.0, [[0, 0], [0, 1], [0, 2]]],
    ]
    for (const [ra, dec, want] of cases) expect(cellsForPoint(ra, dec, m)).toEqual(want)
    expect(cellsForPoint(360.05, 10, m)).toEqual(cellsForPoint(0.05, 10, m))
  })
  it('decodes the documented record and builds its S3 key', () => {
    const hex = '47b60c9e03ed2f0219bcb352554f944184441dad9ce79f358a4db801'
    const bytes = Uint8Array.from(hex.match(/../g)!.map((h) => parseInt(h, 16)))
    const r = readRecord(new DataView(bytes.buffer), 0)
    expect(Math.round(r.ra * 1e7)).toBe(2651633223)
    expect(Math.round(r.dec * 1e7)).toBe(36695299)
    expect(r.x).toEqual([-17383, 20309, 17540, -20466])
    expect(r.y).toEqual([21171, 16788, -21219, -16740])
    expect(r.mjd).toBeCloseTo(60899.671964, 6)
    expect([r.det, r.suffix, r.seq, r.prefix]).toEqual([3, 1, 310, 110])
    const prefixes: SkyManifest['prefixes'] = []
    prefixes[110] = [0, 'dr1', '2025W33_1B', 'l2b-v27-2026-227']
    expect(recordKey(r, { prefixes })).toBe('dr1/level2/2025W33_1B/l2b-v27-2026-227/3/level2_2025W33_1B_0310_1D3_spx_l2b-v27-2026-227.fits')
    expect(recordKey({ det: 6, seq: 321, suffix: 1, prefix: 0 }, { prefixes: [[0, 'dr1', '2025W33_2C', 'l2b-v27-2026-228']] })).toBe(
      'dr1/level2/2025W33_2C/l2b-v27-2026-228/6/level2_2025W33_2C_0321_1D6_spx_l2b-v27-2026-228.fits',
    )
    // the centre is inside, a point three degrees away is not, the far side of the sky never is
    expect(footprintMargin(r, r.ra, r.dec)).toBeGreaterThan(0)
    expect(footprintMargin(r, r.ra, r.dec + 3)).toBeLessThan(0)
    expect(footprintMargin(r, r.ra + 180, -r.dec)).toBe(-Infinity)
  })
  it('refuses an unknown format', () => {
    expect(() => checkManifest({ format: 'other', version: 1 } as SkyManifest)).toThrow()
    expect(() => checkManifest({ format: 'parallax-skyindex', version: 2 } as SkyManifest)).toThrow()
  })
})

describe.skipIf(!haveIndex)('sky index: the shipped shards', () => {
  it('has the documented first record in b18/c053_000.bin', () => {
    const buf = readFileSync(resolve(INDEX, 'b18/c053_000.bin'))
    expect(buf.length).toBe(756 * 28)
    expect(buf.subarray(0, 28).toString('hex')).toBe('47b60c9e03ed2f0219bcb352554f944184441dad9ce79f358a4db801')
    expect(manifest!.prefixes[110]).toEqual([0, 'dr1', '2025W33_1B', 'l2b-v27-2026-227'])
  })
  it("reproduces the documented counts for Barnard's Star, M51 and WISE 0855", () => {
    const barnard = queryLocal(269.4463, 4.768)
    expect(barnard.length).toBe(358)
    expect(barnard[0].key).toBe('dr1/level2/2025W33_2C/l2b-v27-2026-228/3/level2_2025W33_2C_0321_1D3_spx_l2b-v27-2026-228.fits')
    expect(barnard[0].mjd).toBeCloseTo(60902.864715, 6)
    expect(barnard[0].marginArcsec).toBeCloseTo(1689.3, 1)
    expect(barnard[0].collection).toBe('spherex_dr1')
    expect(barnard[0].obsId).toBe('2025W33_2C_0321_1')
    expect(queryLocal(202.4696, 47.1953).length).toBe(413)
    expect(queryLocal(133.7688, -7.2429).length).toBe(258)
    expect(shardsForPoint(manifest!, 269.4463, 4.768).length).toBe(4)
  })
  it('handles RA wrap-around and both celestial poles', () => {
    expect(queryLocal(0.05, 10).length).toBe(330)
    expect(queryLocal(0, 90).length).toBe(430)
    expect(queryLocal(0, -90).length).toBe(526)
  })
  it('queries through fetch, with the build time as cache key', async () => {
    const seen: string[] = []
    vi.stubGlobal('fetch', async (url: string) => {
      seen.push(url)
      const path = resolve(INDEX, url.replace('./idx/', '').split('?')[0])
      return existsSync(path) ? new Response(readFileSync(path)) : new Response('', { status: 404 })
    })
    try {
      const q = await querySkyIndex(202.4696, 47.1953, { base: './idx' })
      expect(q.hits.length).toBe(413)
      expect(q.shardsRead).toBe(4)
      expect(q.bytes).toBeLessThan(200000)
      expect(q.hits.every((h, i) => i === 0 || h.mjd >= q.hits[i - 1].mjd)).toBe(true)
      expect(seen[0]).toBe('./idx/manifest.json')
      expect(seen[1]).toContain(`?v=${encodeURIComponent(manifest!.built_utc)}`)
      expect(q.hits[0].url.startsWith('https://nasa-irsa-spherex.s3.amazonaws.com/')).toBe(true)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})

interface Expected {
  key: string; total: number; dataOffset: number; mjdAvg: number; detector: number; obsid: string; psfFwhm: number
  naxis1: number; naxis2: number; px: number[]; py: number[]; ra: number[]; dec: number[]; backX: number[]; backY: number[]
  lam: number[]; bw: number[]; target: { ra: number; dec: number; pix: [number, number] }; waveShape: number[]
}

describe('FITS and TAN-SIP against astropy on a real Level-2 header', () => {
  const head = new Uint8Array(readFileSync(resolve(FIX, 'l2_header.bin')))
  const tail = new Uint8Array(readFileSync(resolve(FIX, 'l2_wave.bin')))
  const exp = JSON.parse(readFileSync(resolve(FIX, 'l2_expected.json'), 'utf8')) as Expected
  const prim = parseHeader(head, 0)!
  const h = parseHeader(head, prim.bytes + dataBytes(prim))!

  it('parses the primary and image headers', () => {
    expect(prim.bytes).toBe(FITS_BLOCK)
    expect(dataBytes(prim)).toBe(0)
    expect(prim.bytes + h.bytes).toBe(exp.dataOffset)
    expect(need(h, 'NAXIS1')).toBe(exp.naxis1)
    expect(need(h, 'NAXIS2')).toBe(exp.naxis2)
    expect(need(h, 'BITPIX')).toBe(-32)
    expect(num(h, 'DETECTOR')).toBe(exp.detector)
    expect(str(h, 'OBSID')).toBe(exp.obsid)
    expect(num(h, 'MJD-AVG')).toBe(exp.mjdAvg)
    expect(num(h, 'PSF_FWHM')).toBeCloseTo(exp.psfFwhm, 12)
    expect(str(h, 'CTYPE1')).toBe('RA---TAN-SIP')
    expect(str(h, 'BUNIT')).toBe('MJy / sr')
    expect(dataBytes(h)).toBe(Math.ceil((2040 * 2040 * 4) / FITS_BLOCK) * FITS_BLOCK)
  })
  it('tolerates HIERARCH cards, free-format values and booleans', () => {
    expect(num(h, 'L2 N_HOT')).toBe(1)
    expect(num(h, 'KEN_A')).toBe(20000)
    expect(str(h, 'SPS_TARGET')).toBe('SPS_096984_S12')
    expect(h.cards.get('ASTRONETSOLVED')).toBe(true)
    expect(h.cards.get('HE_AIRGLOW_CONT')).toBe(false)
    expect(num(h, 'X_SC_START')).toBeCloseTo(-1392.2851695142451, 9)
    expect(h.history.some((l) => /\[CALIB\] spectral_wcs \S+/.test(l))).toBe(true)
    expect(parseHeader(head.subarray(0, 5000), FITS_BLOCK)).toBeNull()
    const card = (s: string) => s.padEnd(80)
    const txt = card("NAME    = 'O''Neil  '           / a quote") + card('VAL     =              1.5D+02') + card('END')
    const small = parseHeader(Uint8Array.from(txt, (ch) => ch.charCodeAt(0)))!
    expect(small.cards.get('NAME')).toBe("O'Neil")
    expect(small.cards.get('VAL')).toBe(150)
    expect(small.bytes).toBe(FITS_BLOCK)
  })
  it('pixel to sky agrees with astropy', () => {
    const w = wcsFromHeader(h)
    let worst = 0
    exp.px.forEach((x, i) => {
      const s = pixToWorld(w, x, exp.py[i])
      const cosd = Math.cos((exp.dec[i] * Math.PI) / 180)
      worst = Math.max(worst, Math.abs(s.ra - exp.ra[i]) * cosd * 3600, Math.abs(s.dec - exp.dec[i]) * 3600)
    })
    expect(worst).toBeLessThan(1e-5) // arcsec
  })
  it('sky to pixel agrees with astropy all_world2pix to far better than 0.01 pixel', () => {
    const w = wcsFromHeader(h)
    let worst = 0
    exp.ra.forEach((ra, i) => {
      const p = worldToPix(w, ra, exp.dec[i])!
      worst = Math.max(worst, Math.abs(p.x - exp.backX[i]), Math.abs(p.y - exp.backY[i]))
    })
    expect(worst).toBeLessThan(1e-6)
    const t = worldToPix(w, exp.target.ra, exp.target.dec)!
    expect(t.x).toBeCloseTo(exp.target.pix[0], 6)
    expect(t.y).toBeCloseTo(exp.target.pix[1], 6)
    expect(worldToPix(w, exp.target.ra + 180, -exp.target.dec)).toBeNull()
  })
  it('converges without the inverse polynomials too', () => {
    const w = wcsFromHeader(h)
    const bare = { ...w, ap: null, bp: null }
    exp.ra.forEach((ra, i) => {
      const p = worldToPix(bare, ra, exp.dec[i])!
      expect(Math.abs(p.x - exp.backX[i])).toBeLessThan(1e-6)
      expect(Math.abs(p.y - exp.backY[i])).toBeLessThan(1e-6)
    })
  })
  it('reads the WCS-WAVE table and interpolates like the pipeline', () => {
    expect(lastHduOffset(tail)).toBe(0)
    const t = readWaveTable(tail)
    expect([t.y.length, t.x.length, 2]).toEqual(exp.waveShape)
    expect(t.values.length).toBe(exp.waveShape.reduce((a, b) => a * b, 1))
    let worstLam = 0
    let worstBw = 0
    exp.px.forEach((x, i) => {
      const [lam, bw] = waveAt(t, x + 1, exp.py[i] + 1)
      worstLam = Math.max(worstLam, Math.abs(lam - exp.lam[i]))
      worstBw = Math.max(worstBw, Math.abs(bw - exp.bw[i]))
    })
    expect(worstLam).toBeLessThan(1e-6) // micron
    expect(worstBw).toBeLessThan(1e-6)
    // a longer tail (more of the file before the table) works as well
    const longer = new Uint8Array(tail.length + FITS_BLOCK)
    longer.set(tail, FITS_BLOCK)
    expect(lastHduOffset(longer)).toBe(FITS_BLOCK)
    expect(readWaveTable(longer).x).toEqual(t.x)
    expect(() => readWaveTable(head.subarray(0, 2 * FITS_BLOCK))).toThrow()
  })
  it('reads big-endian numbers', () => {
    const b = new Uint8Array([0x3f, 0x80, 0, 0, 0xc0, 0x20, 0, 0, 0xff, 0xff, 0xff, 0xfe, 0, 0, 1, 0])
    expect(Array.from(float32BE(b, 0, 2))).toEqual([1, -2.5])
    expect(Array.from(int32BE(b, 8, 2))).toEqual([-2, 256])
  })
})

describe('live field: small pieces', () => {
  it('chooses an odd grid that covers the requested size', () => {
    expect([3, 6, 9].map(liveGridN)).toEqual([31, 59, 89])
    for (const s of [3, 6, 9]) expect((liveGridN(s) * 6.15) / 60).toBeGreaterThanOrEqual(s)
  })
  it('normalises and names a request', () => {
    const s = normaliseSpec({ ra: -10, dec: 5, detectors: [5, 2, 2, 9] })
    expect(s).toEqual({ ra: 350, dec: 5, sizeArcmin: 3, detectors: [2, 5], maxImages: 360 })
    expect(normaliseSpec({ ra: 1, dec: 2, detectors: [1, 2, 3, 4, 5, 6] }).detectors).toEqual([])
    expect(liveKey(s)).toBe('live_350.00000_p5.00000_3am_d25_x360')
    expect(liveKey(normaliseSpec({ ra: 1, dec: -2, detectors: [], sizeArcmin: 6, maxImages: 50 }))).toBe('live_1.00000_m2.00000_6am_dall_x50')
  })
  it('keeps an evenly spaced subset and says nothing is lost when all fit', () => {
    const all = Array.from({ length: 10 }, (_, i) => i)
    expect(subsetEvenly(all, 20)).toBe(all)
    expect(subsetEvenly(all, 4)).toEqual([0, 3, 6, 9])
    expect(subsetEvenly(all, 1)).toEqual([0])
    expect(subsetEvenly(Array.from({ length: 29399 }, (_, i) => i), 360).length).toBe(360)
  })
  it('starts a new survey pass after a 30-day gap', () => {
    expect(assignCampaigns([1, 2, 31, 62, 63, 200])).toEqual([0, 0, 0, 1, 1, 2])
    expect(assignCampaigns([])).toEqual([])
  })
  it('measures a robust sky and noise in the presence of stars', () => {
    const img = new Float32Array(900)
    let seed = 7
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
    for (let k = 0; k < img.length; k++) img[k] = 0.4 + 0.02 * Math.sqrt(-2 * Math.log(rnd())) * Math.cos(2 * Math.PI * rnd())
    for (let k = 0; k < 30; k++) img[k * 29] = 50 + k
    img[5] = NaN
    const { sky, sigma } = robustSky(img)
    expect(sky).toBeCloseTo(0.4, 2)
    expect(sigma).toBeGreaterThan(0.015)
    expect(sigma).toBeLessThan(0.025)
    expect(robustSky(new Float32Array(4).fill(NaN))).toEqual({ sky: 0, sigma: NaN })
  })
  it('measures the pixel noise under a bright, smooth object', () => {
    const rows = 40
    const cols = 300
    const win = new Float32Array(rows * cols)
    let seed = 11
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++) {
        const galaxy = 30 * Math.exp(-((c - 150) ** 2 + (r - 20) ** 2) / (2 * 40 ** 2))
        win[r * cols + c] = 1.5 + galaxy + 0.03 * Math.sqrt(-2 * Math.log(rnd())) * Math.cos(2 * Math.PI * rnd())
      }
    win[77] = NaN
    win[500] = 900
    const noise = neighbourNoise(win, rows, cols)
    expect(noise).toBeGreaterThan(0.026)
    expect(noise).toBeLessThan(0.036)
    expect(robustSky(win).sigma).toBeGreaterThan(1) // the plain scatter is dominated by the object
    expect(neighbourNoise(new Float32Array(6), 2, 3)).toBeNaN()
  })
  it('fits the wavelength plane', () => {
    const n = 9
    const lam = new Float32Array(n * n)
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) lam[y * n + x] = 2.5 + 0.001 * (x - 4) - 0.0004 * (y - 4)
    lam[3] = NaN
    const fit = planeFit(lam, n)
    expect(fit[0]).toBeCloseTo(2.5, 5)
    expect(fit[1]).toBeCloseTo(0.001, 6)
    expect(fit[2]).toBeCloseTo(-0.0004, 6)
    expect(planeFit(new Float32Array(81).fill(NaN), n)).toEqual([null, 0, 0])
  })
  it('stacks with outlier rejection', () => {
    const frames = [1, 1.1, 0.9, 1.05, 0.95, 400].map((v) => ({ img: Float32Array.from([v, NaN]), sigma: 0.1 }))
    const s = robustStack(frames, 2)
    expect(s[0]).toBeCloseTo(1, 5)
    expect(s[1]).toBeNaN()
    expect(robustStack([], 2)[0]).toBeNaN()
  })
  it('gives an honest size estimate', () => {
    const e = estimateLive(60, 3)
    expect(e.bytes).toBeGreaterThan(15e6)
    expect(e.bytes).toBeLessThan(30e6)
    expect(e.secondsSlow).toBeGreaterThan(e.secondsFast)
  })
  it('carries a live request through the URL', () => {
    const s = parseQuery('?ra=202.4696&dec=47.1953&live=1&size=6&dets=2,5&max=100&mode=naive&frame=7')
    expect(s.live).toEqual({ sizeArcmin: 6, detectors: [2, 5], maxImages: 100 })
    expect(s.page).toBe('view')
    expect(parseQuery(toQuery(s))).toEqual(s)
    // the short form of the brief: fov and det stand in for size and detectors
    const short = parseQuery('?ra=150&dec=2.2&fov=3&det=3&live=1')
    expect(short.live).toEqual({ sizeArcmin: 3, detectors: [3], maxImages: 360 })
    expect(parseQuery('?ra=150&dec=2.2&live=1').live).toEqual({ sizeArcmin: 3, detectors: [2, 5], maxImages: 360 })
    expect(parseQuery('?ra=150&dec=2.2&live=1&dets=all').live!.detectors).toEqual([])
    expect(parseQuery('?ra=150&dec=2.2').live).toBeNull()
    expect(parseQuery('?field=barnard&live=1').live).toBeNull()
    expect(toQuery(parseQuery('?ra=150&dec=2.2&live=1&dets=all'))).toContain('dets=all')
  })
})

// ---- synthetic Level-2 files -------------------------------------------------------------

const NX = 240
const NY = 200
const cardOf = (k: string, v: string | number | boolean) => {
  const val = typeof v === 'string' ? `'${v.padEnd(8)}'` : typeof v === 'boolean' ? (v ? 'T' : 'F').padStart(20) : String(v).padStart(20)
  return (k.startsWith('HISTORY') ? `HISTORY ${v}` : `${k.padEnd(8)}= ${val}`).padEnd(80)
}
function headerBytes(cards: [string, string | number | boolean][]): Uint8Array {
  const txt = cards.map(([k, v]) => cardOf(k, v)).join('') + 'END'.padEnd(80)
  const out = new Uint8Array(Math.ceil(txt.length / FITS_BLOCK) * FITS_BLOCK).fill(32)
  for (let i = 0; i < txt.length; i++) out[i] = txt.charCodeAt(i)
  return out
}
const ramp = (x: number, y: number) => 5 + 0.01 * x + 0.02 * y
const lamOf = (xd: number, yd: number) => 1.6 + 0.002 * xd + 0.0005 * yd

/** A small file laid out like a Level-2 image: PRIMARY, IMAGE, a filler HDU, WCS-WAVE. */
function syntheticFile(o: { crval: [number, number]; rot: number; mjd: number; det: number; calib: string; hole?: [number, number] }): Uint8Array {
  const s = 6.15 / 3600
  const c = Math.cos((o.rot * Math.PI) / 180)
  const sn = Math.sin((o.rot * Math.PI) / 180)
  const img = headerBytes([
    ['XTENSION', 'IMAGE'], ['BITPIX', -32], ['NAXIS', 2], ['NAXIS1', NX], ['NAXIS2', NY], ['PCOUNT', 0], ['GCOUNT', 1],
    ['DETECTOR', o.det], ['CRPIX1', NX / 2 + 0.5], ['CRPIX2', NY / 2 + 0.5],
    ['PC1_1', -s * c], ['PC1_2', s * sn], ['PC2_1', s * sn], ['PC2_2', s * c], ['CDELT1', 1.0], ['CDELT2', 1.0],
    ['CTYPE1', 'RA---TAN-SIP'], ['CTYPE2', 'DEC--TAN-SIP'], ['CRVAL1', o.crval[0]], ['CRVAL2', o.crval[1]],
    ['A_ORDER', 2], ['A_2_0', 2e-6], ['A_1_1', -1e-6], ['B_ORDER', 2], ['B_0_2', 3e-6], ['B_0_0', 0.3],
    ['MJD-AVG', o.mjd], ['PSF_FWHM', 7.25], ['CRPIX1W', 1], ['CRVAL1W', 1], ['CRPIX2W', 1], ['CRVAL2W', 1],
    ['HISTORY', `[CALIB] spectral_wcs ${o.calib}`],
  ])
  const data = new Uint8Array(Math.ceil((NX * NY * 4) / FITS_BLOCK) * FITS_BLOCK)
  const dv = new DataView(data.buffer)
  for (let y = 0; y < NY; y++) for (let x = 0; x < NX; x++) dv.setFloat32((y * NX + x) * 4, o.hole && o.hole[0] === x && o.hole[1] === y ? NaN : ramp(x, y), false)
  const filler = headerBytes([['XTENSION', 'IMAGE'], ['BITPIX', 8], ['NAXIS', 1], ['NAXIS1', 5000], ['PCOUNT', 0], ['GCOUNT', 1], ['EXTNAME', 'FILLER']])
  const fillData = new Uint8Array(Math.ceil(5000 / FITS_BLOCK) * FITS_BLOCK)
  const gx = [1, 80, 240]
  const gy = [1, 100, 150, 200]
  const row = (gx.length + gy.length) * 4 + gx.length * gy.length * 2 * 4
  const wave = headerBytes([
    ['XTENSION', 'BINTABLE'], ['BITPIX', 8], ['NAXIS', 2], ['NAXIS1', row], ['NAXIS2', 1], ['PCOUNT', 0], ['GCOUNT', 1], ['TFIELDS', 3],
    ['TTYPE1', 'X'], ['TFORM1', `${gx.length}J`], ['TTYPE2', 'Y'], ['TFORM2', `${gy.length}J`],
    ['TTYPE3', 'VALUES'], ['TFORM3', `${gx.length * gy.length * 2}E`], ['TDIM3', `(2,${gx.length},${gy.length})`], ['EXTNAME', 'WCS-WAVE'],
  ])
  const wdata = new Uint8Array(FITS_BLOCK)
  const wv = new DataView(wdata.buffer)
  let at = 0
  for (const v of [...gx, ...gy]) { wv.setInt32(at, v, false); at += 4 }
  for (const y of gy) for (const x of gx) { wv.setFloat32(at, lamOf(x, y), false); wv.setFloat32(at + 4, 0.04, false); at += 8 }
  const prim = headerBytes([['SIMPLE', true], ['BITPIX', 8], ['NAXIS', 0], ['EXTEND', true]])
  const parts = [prim, img, data, filler, fillData, wave, wdata]
  const out = new Uint8Array(parts.reduce((a, p) => a + p.length, 0))
  let o2 = 0
  for (const p of parts) { out.set(p, o2); o2 += p.length }
  return out
}

function archive(files: Map<string, Uint8Array>, log: { url: string; range: string }[], flaky = new Set<string>()): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const range = new Headers(init?.headers).get('Range') ?? ''
    log.push({ url, range })
    if (init?.signal?.aborted) throw new DOMException('aborted', 'AbortError')
    const f = files.get(url)
    if (!f) return new Response('', { status: 404 })
    if (flaky.has(`${url} ${range}`)) {
      flaky.delete(`${url} ${range}`)
      return new Response('slow down', { status: 503 })
    }
    const m = /^bytes=(\d*)-(\d*)$/.exec(range)
    if (!m) return new Response(f.slice(), { status: 200 })
    const a = m[1] === '' ? f.length - Number(m[2]) : Number(m[1])
    const b = m[1] === '' ? f.length : Math.min(f.length, Number(m[2]) + 1)
    return new Response(f.slice(a, b), { status: 206 })
  }) as typeof fetch
}

const ROOT = 'https://archive.test/'
const fakeManifest = { format: 'parallax-skyindex', version: 1, built_utc: '2026-11-13T20:55:25Z', doi: { dr1: '10.26131/IRSA678' } } as unknown as SkyManifest
const hitOf = (name: string, mjd: number, det: number): SkyHit => ({ key: `dr1/${name}`, url: `${ROOT}dr1/${name}`, mjd, det, collection: 'spherex_dr1', release: 'dr1', obsId: name, marginArcsec: 100 })

describe('live field: the whole path on synthetic files', () => {
  afterEach(() => vi.restoreAllMocks())
  const ra0 = 150
  const dec0 = 2.2
  const specs = [
    { name: 'a.fits', crval: [150.01, 2.21] as [number, number], rot: 20, mjd: 60800.1, det: 3 },
    { name: 'b.fits', crval: [149.99, 2.19] as [number, number], rot: -65, mjd: 60800.4, det: 3 },
    { name: 'c.fits', crval: [150.0, 2.2] as [number, number], rot: 0, mjd: 60801.0, det: 3, hole: [120, 100] as [number, number] },
    { name: 'far.fits', crval: [150.33, 2.2] as [number, number], rot: 0, mjd: 60801.5, det: 3 }, // the field is only half on this one
    { name: 'd.fits', crval: [150.02, 2.2] as [number, number], rot: 100, mjd: 60990.2, det: 3 },
    { name: 'e.fits', crval: [150.0, 2.23] as [number, number], rot: 180, mjd: 60990.9, det: 3 },
    { name: 'f.fits', crval: [150.0, 2.2] as [number, number], rot: 45, mjd: 60991.3, det: 3 },
    { name: 'other-detector.fits', crval: [150.0, 2.2] as [number, number], rot: 0, mjd: 60991.4, det: 5 },
  ]
  const files = new Map(specs.map((s) => [`${ROOT}dr1/${s.name}`, syntheticFile({ ...s, calib: `cal-${s.det}` })]))
  const hits = [...specs.map((s) => hitOf(s.name, s.mjd - 0.0007, s.det)), hitOf('missing.fits', 60991.5, 3)]
  const query = async (): Promise<SkyQuery> => ({ hits, shardsRead: 4, bytes: 1000, manifest: fakeManifest })

  it('builds a pack with the right pixels, wavelengths, passes and stacks', async () => {
    const log: { url: string; range: string }[] = []
    const seen: LiveProgress[] = []
    const flaky = new Set([`${ROOT}dr1/b.fits bytes=0-28799`])
    const res = await buildLiveField({
      ra: ra0, dec: dec0, sizeArcmin: 3, detectors: [3], query, fetchImpl: archive(files, log, flaky), retryBaseMs: 1, snapshotMs: 0,
      onProgress: (p) => seen.push(p),
    })
    const { pack, info } = res
    const n = 31
    expect(pack.n).toBe(n)
    expect(pack.nFrames).toBe(6)
    expect(pack.base).toBe('live')
    expect(pack.meta.frames.name).toEqual(['a.fits', 'b.fits', 'c.fits', 'd.fits', 'e.fits', 'f.fits'])
    expect(pack.meta.frames.campaign).toEqual([0, 0, 0, 1, 1, 1])
    expect(pack.nCampaigns).toBe(2)
    expect(pack.meta.campaigns!.map((c) => c.nFrames)).toEqual([3, 3])
    expect(pack.meta.frames.mjd[0]).toBe(60800.1)
    expect(pack.meta.frames.iso[0].slice(0, 10)).toBe('2025-05-05')
    expect(pack.meta.frames.fwhm![0]).toBe(7.25)
    expect(info).toMatchObject({ complete: true, available: 9, matching: 8, requested: 8, dropped: 0, loaded: 6, skipped: 1, failed: 1, detectors: [3] })
    expect(res.problems.map((p) => [p.key, p.failed])).toEqual(expect.arrayContaining([['dr1/far.fits', false], ['dr1/missing.fits', true]]))
    expect(pack.meta.release).toMatchObject({ collections: ['spherex_dr1'], doi: ['10.26131/IRSA678'] })
    expect(pack.tpl).toBeNull()
    expect(pack.snrCorr).toBeNull()
    expect(pack.partnersDerived).toBe(true)
    expect(pack.meta.gaia).toEqual([])

    // pixels: the detector image is a plane, so bilinear resampling must reproduce it exactly
    for (let i = 0; i < pack.nFrames; i++) {
      const spec = specs.find((s) => s.name === pack.meta.frames.name![i])!
      const file = files.get(`${ROOT}dr1/${spec.name}`)!
      const h = parseHeader(file, FITS_BLOCK)!
      const w = wcsFromHeader(h)
      const img = decodeFrame(pack.img, i, n, LIVE_ENCODING)
      const sky = pack.meta.frames.sky![i]!
      let checked = 0
      for (const [x, y] of [[0, 0], [30, 0], [0, 30], [30, 30], [15, 15], [7, 22]]) {
        const s = pixToSky(pack.meta, x, y)
        const p = worldToPix(w, s.ra, s.dec)!
        const v = img[y * n + x]
        if (!Number.isFinite(v)) continue
        checked++
        expect(Math.abs(v + sky - ramp(p.x, p.y))).toBeLessThan(0.006)
        expect(Math.abs(lamAt(pack.meta.frames.lamFit[i], x, y, n) - lamOf(p.x + 1, p.y + 1))).toBeLessThan(2e-4)
      }
      expect(checked).toBeGreaterThanOrEqual(5)
      const c = worldToPix(w, ra0, dec0)!
      expect(pack.meta.frames.lam[i]).toBeCloseTo(lamOf(c.x + 1, c.y + 1), 4)
      expect(pack.meta.frames.bw[i]).toBeCloseTo(0.04, 5)
      expect(pack.meta.frames.sigma[i]).toBeGreaterThan(0)
    }
    // the NaN pixel of c.fits blanks the grid pixel that leans on it, and only raises the no-data flag
    const ci = 2
    const blank = Array.from(pack.img.subarray(ci * n * n, (ci + 1) * n * n)).filter((q) => q === 0).length
    expect(blank).toBeGreaterThanOrEqual(1)
    expect(blank).toBeLessThanOrEqual(4)
    expect(Array.from(pack.flags!.subarray(ci * n * n, (ci + 1) * n * n)).filter((v) => v === 1).length).toBe(blank)
    expect(new Set(pack.flags!)).toEqual(new Set([0, 1]))

    // stacks: one per pass for detector 3, none for the others
    expect(stackImage(pack, 0, 3)).not.toBeNull()
    expect(stackImage(pack, 1, 3)).not.toBeNull()
    expect(stackImage(pack, 0, 5)).toBeNull()
    // the browser-side differences work; the chromatic template is honestly absent
    expect(pack.naivePartner[0]).toBeGreaterThanOrEqual(3)
    expect(naiveProduct(pack, 0).data).not.toBeNull()
    expect(chromaProduct(pack, 0).data).toBeNull()
    expect(chromaProduct(pack, 0).missing).toMatch(/engine/)

    // network behaviour: detector 5 untouched, one wavelength table for the whole detector, a retry after the 503
    expect(log.some((l) => l.url.includes('other-detector'))).toBe(false)
    expect(log.filter((l) => l.range === 'bytes=-5760').length).toBe(1)
    expect(log.filter((l) => l.url.endsWith('b.fits') && l.range === 'bytes=0-28799').length).toBe(2)
    expect(log.filter((l) => l.url.endsWith('far.fits')).length).toBe(1) // header only: no pixels fetched for a skipped image
    const strip = log.find((l) => l.url.endsWith('c.fits') && l.range !== 'bytes=0-28799')!
    const [a, b] = strip.range.replace('bytes=', '').split('-').map(Number)
    expect((b - a + 1) % (4 * NX)).toBe(0)
    expect((b - a + 1) / (4 * NX)).toBeLessThanOrEqual(n + 2)
    expect(info.bytes).toBe(log.length ? res.info.bytes : 0)
    expect(info.bytes).toBeLessThan([...files.values()].reduce((s, f) => s + f.length, 0) / 2)

    // progress: index first, then counts that only grow, snapshots on the way, the final pack last
    expect(seen[0].phase).toBe('index')
    expect(seen[seen.length - 1].phase).toBe('done')
    expect(seen[seen.length - 1].pack).toBe(pack)
    expect(seen.some((p) => p.phase === 'frames' && p.pack && !p.pack.meta.live!.complete && p.pack.nFrames < 6)).toBe(true)
    expect(seen.every((p, i) => i === 0 || p.done >= seen[i - 1].done)).toBe(true)
    expect(seen.find((p) => p.last)!.last!.n).toBe(n)
  })

  it('keeps an evenly spaced subset when there are too many images, and says so', async () => {
    const msgs: string[] = []
    const res = await buildLiveField({
      ra: ra0, dec: dec0, sizeArcmin: 3, detectors: [], maxImages: 3, query, fetchImpl: archive(files, []), retryBaseMs: 1,
      onProgress: (p) => msgs.push(p.message),
    })
    expect(res.info).toMatchObject({ available: 9, matching: 9, requested: 3, dropped: 6 })
    expect(msgs.some((m) => /9 images match; fetching 3 evenly spaced in time \(6 left out\)/.test(m))).toBe(true)
    expect(res.pack.nFrames).toBeLessThanOrEqual(3)
  })

  it('explains itself when nothing can be used', async () => {
    await expect(buildLiveField({ ra: ra0, dec: dec0, detectors: [3], query: async () => ({ hits: [], shardsRead: 0, bytes: 0, manifest: fakeManifest }), fetchImpl: archive(files, []) }))
      .rejects.toThrow(/no image of this position/)
    await expect(buildLiveField({ ra: ra0, dec: dec0, detectors: [1], query, fetchImpl: archive(files, []) })).rejects.toThrow(/detector 1/)
    await expect(buildLiveField({ ra: ra0, dec: dec0, detectors: [3], query: async () => ({ hits: [hitOf('missing.fits', 60800, 3)], shardsRead: 1, bytes: 1, manifest: fakeManifest }), fetchImpl: archive(files, []), retryBaseMs: 1 }))
      .rejects.toThrow(/could be used/)
  })

  it('stops when aborted', async () => {
    const ctl = new AbortController()
    const log: { url: string; range: string }[] = []
    const p = buildLiveField({
      ra: ra0, dec: dec0, sizeArcmin: 3, detectors: [3], query, fetchImpl: archive(files, log), concurrency: 1, signal: ctl.signal,
      onProgress: (q) => { if (q.done >= 2) ctl.abort() },
    })
    await expect(p).rejects.toMatchObject({ name: 'AbortError' })
    expect(log.some((l) => l.url.endsWith('f.fits'))).toBe(false)
  })
})
