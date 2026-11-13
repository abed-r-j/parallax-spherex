/**
 * Unit tests of the pure functions: decoding, WCS, coordinate parsing, stretch,
 * photometry, URL state, engine reply parsing - plus a check on the real Barnard pack.
 * SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
 */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseCoords } from './coords'
import {
  buildPack, decodeBrightness, decodeFrame, decodeSnr, deriveGatedPartners, deriveNaivePartners,
  encodeBrightness, sectionView, snrAllUndefined, stackImage,
} from './decode'
import { parseJob, parseJobId } from './engine'
import { fieldContaining, nearestFields, presetNear } from './fields'
import { apertureSum, centroid, lamAt, spectrumAt, spectrumCsv } from './photometry'
import { chromaProduct, filterFrames, flagsRgba, gatedProduct, meanImage, mismatchMap, naiveProduct, passEntries, selectionFrames } from './products'
import { cmapLut, normalise, percentiles, renderRgba, stretchUnit, upsampleBicubic } from './stretch'
import type { Frames, Meta } from './types'
import { ujyPerMjySr } from './types'
import { DEFAULT_STATE, parseQuery, toQuery } from './urlstate'
import { formatDec, formatRa, insideGrid, mjdToYear, pixToSky, propagate, separationArcsec, skyToPix } from './wcs'

describe('coordinate parsing', () => {
  it('parses the three required forms', () => {
    const a = parseCoords('08h55m10.831s -7d14m42.53s')!
    expect(a.ra).toBeCloseTo(133.7951292, 6)
    expect(a.dec).toBeCloseTo(-7.2451472, 6)
    const b = parseCoords('08 55 10.83 -07 14 42.5')!
    expect(b.ra).toBeCloseTo(133.795125, 6)
    expect(b.dec).toBeCloseTo(-7.2451389, 6)
    expect(parseCoords('133.795 -7.245')).toEqual({ ra: 133.795, dec: -7.245 })
  })
  it('parses other common forms', () => {
    expect(parseCoords('133.795, -7.245')).toEqual({ ra: 133.795, dec: -7.245 })
    expect(parseCoords('08:55:10.83 -07:14:42.5')!.ra).toBeCloseTo(133.795125, 6)
    expect(parseCoords('17 57 48.5 +04 41 36')!.dec).toBeCloseTo(4.693333, 5)
    expect(parseCoords('00 00 00 -00 30 00')!.dec).toBeCloseTo(-0.5, 9)
    expect(parseCoords('8.5h 10d')).toEqual({ ra: 127.5, dec: 10 })
    expect(parseCoords('10 +20°')).toEqual({ ra: 10, dec: 20 })
  })
  it('rejects nonsense', () => {
    for (const t of ['', 'hello', '400 10', '10 95', '10', '08 61 00 +10 00 00', '1 2 3', 'M31'])
      expect(parseCoords(t)).toBeNull()
  })
})

describe('TAN projection', () => {
  const g = { ra0: 269.446288, dec0: 4.767983, n: 61, scale: 6.15 }
  it('puts the centre at (n-1)/2 with east left and north up', () => {
    expect(skyToPix(g, g.ra0, g.dec0)).toEqual({ x: 30, y: 30 })
    expect(skyToPix(g, g.ra0, g.dec0 + 6.15 / 3600)!.y).toBeCloseTo(31, 5)
    expect(skyToPix(g, g.ra0 + 6.15 / 3600 / Math.cos((g.dec0 * Math.PI) / 180), g.dec0)!.x).toBeCloseTo(29, 4)
  })
  it('round-trips at every corner, also near the pole and across RA = 0', () => {
    for (const grid of [g, { ra0: 0.001, dec0: 89.2, n: 81, scale: 6.15 }, { ra0: 359.999, dec0: -56.78, n: 61, scale: 6.15 }])
      for (const [x, y] of [[0, 0], [60, 0], [0, 60], [60, 60], [12.3, 45.6]]) {
        const s = pixToSky(grid, x, y)
        const p = skyToPix(grid, s.ra, s.dec)!
        expect(p.x).toBeCloseTo(x, 7)
        expect(p.y).toBeCloseTo(y, 7)
      }
  })
  it('agrees with the great-circle distance on small scales', () => {
    const s = pixToSky(g, 40, 30)
    expect(separationArcsec(g.ra0, g.dec0, s.ra, s.dec)).toBeCloseTo(61.5, 3)
  })
  it('knows what is inside', () => {
    expect(insideGrid(g, g.ra0, g.dec0 + 0.05)).toBe(true)
    expect(insideGrid(g, g.ra0, g.dec0 + 0.06)).toBe(false)
    expect(skyToPix(g, g.ra0 + 180, -g.dec0)).toBeNull()
  })
  it("moves Barnard's Star by its proper motion", () => {
    const p = propagate(269.452075, 4.693391, -798.58, 10328.12, 2000, 2026)
    expect((p.dec - 4.693391) * 3600).toBeCloseTo(268.53, 2)
    expect(mjdToYear(51544.5)).toBe(2000)
    expect(mjdToYear(60902.865381)).toBeCloseTo(2025.622, 3)
  })
  it('formats sexagesimal', () => {
    expect(formatRa(133.7951292)).toBe('08 55 10.83')
    expect(formatDec(-7.2451472)).toBe('-07 14 42.5')
    expect(formatDec(4.9999999)).toBe('+05 00 00.0')
  })
})

describe('decoding', () => {
  const enc = { soft: 0.0148, lo: -3.6, hi: 12.65 }
  it('inverts the brightness encoding', () => {
    expect(decodeBrightness(0, enc)).toBeNaN()
    for (const v of [-0.2, 0, 0.01, 1, 250]) {
      const back = decodeBrightness(encodeBrightness(v, enc), enc)
      expect(Math.abs(back - v)).toBeLessThan(Math.max(1e-5, Math.abs(v) * 2e-4))
    }
    expect(encodeBrightness(NaN, enc)).toBe(0)
  })
  it('locates sections by offset and refuses bad ones', () => {
    const buf = new ArrayBuffer(64)
    new Uint16Array(buf, 8, 4).set([1, 2, 3, 65535])
    expect(Array.from(sectionView(buf, { offset: 8, dtype: 'uint16', shape: [1, 2, 2] }, 'uint16')!)).toEqual([1, 2, 3, 65535])
    expect(sectionView(buf, { offset: 60, dtype: 'uint16', shape: [1, 2, 2] }, 'uint16')).toBeNull()
    expect(sectionView(buf, undefined, 'uint16')).toBeNull()
    expect(sectionView(buf, { offset: 0, dtype: 'int8', shape: [4] }, 'uint16')).toBeNull()
    const odd = sectionView(buf, { offset: 9, dtype: 'uint16', shape: [2] }, 'uint16')
    expect(odd).not.toBeNull()
  })
  it('decodes signal-to-noise cubes', () => {
    const c = Int8Array.from([-128, 4, -6, 127, -128, -128, -128, -128])
    const a = decodeSnr(c, 0, 2)
    expect(a[0]).toBeNaN()
    expect(Array.from(a.slice(1))).toEqual([1, -1.5, 31.75])
    expect(snrAllUndefined(c, 0, 2)).toBe(false)
    expect(snrAllUndefined(c, 1, 2)).toBe(true)
  })
  it('derives partners as the contract defines them', () => {
    const f = {
      mjd: [0, 1, 200, 201, 202], det: [1, 2, 1, 2, 1], campaign: [0, 0, 1, 1, 1],
      lam: [1.0, 1.5, 1.2, 1.501, 1.004], bw: [0.02, 0.03, 0.02, 0.03, 0.02],
    } as unknown as Frames
    expect(Array.from(deriveNaivePartners(f))).toEqual([2, 3, 0, 1, 0])
    expect(Array.from(deriveGatedPartners(f))).toEqual([4, 3, -1, 1, 0])
  })
})

function synthetic(): { meta: Meta; buf: ArrayBuffer } {
  const n = 9
  const N = 4
  const enc = { soft: 0.01, lo: -3, hi: 10 }
  const buf = new ArrayBuffer(N * n * n * 2 + N * n * n + 8 + 2 * 6 * n * n * 4)
  const img = new Uint16Array(buf, 0, N * n * n)
  for (let i = 0; i < N; i++)
    for (let y = 0; y < n; y++)
      for (let x = 0; x < n; x++) {
        const star = Math.exp(-((x - 4 - (i >= 2 ? 1 : 0)) ** 2 + (y - 4) ** 2) / 2)
        img[i * n * n + y * n + x] = encodeBrightness(0.1 + star * (1 + i), enc)
      }
  img[0] = 0
  const fo = N * n * n * 2
  new Uint8Array(buf, fo, N * n * n)[0] = 1
  const so = fo + N * n * n + 3 - ((fo + N * n * n + 3) % 4) + 4
  const meta: Meta = {
    key: 't', name: 'T', kind: 'static', ra0: 10, dec0: 20, n, scale: 6.15,
    encoding: enc,
    sections: {
      img: { offset: 0, dtype: 'uint16', shape: [N, n, n] },
      flags: { offset: fo, dtype: 'uint8', shape: [N, n, n] },
      stack: { offset: so, dtype: 'float32', shape: [2, 6, n, n] },
      tpl: { offset: 0, dtype: 'uint16', shape: [N + 1, n, n] },
    },
    frames: {
      mjd: [0, 0.1, 200, 200.1], iso: ['a', 'b', 'c', 'd'], det: [1, 2, 1, 2], campaign: [0, 0, 1, 1],
      lam: [1.0, 1.5, 1.004, 1.6], bw: [0.02, 0.03, 0.02, 0.03],
      lamFit: [[1.0, 0.001, 0.002], [1.5, 0, 0], [1.004, 0.001, 0.002], [1.6, 0, 0]],
      sigma: [0.01, 0.01, 0.01, 0.01],
    },
  }
  const st = new Float32Array(buf, so, 2 * 6 * n * n).fill(NaN)
  st.fill(1, 0, n * n)
  st.fill(2, 6 * n * n, 7 * n * n)
  return { meta, buf }
}

describe('pack assembly and products', () => {
  const { meta, buf } = synthetic()
  const pack = buildPack(meta, buf, 'x')
  it('copes with missing and malformed optional sections', () => {
    expect(pack.nFrames).toBe(4)
    expect(pack.tpl).toBeNull() // wrong shape -> ignored
    expect(pack.snrCorr).toBeNull()
    expect(pack.partnersDerived).toBe(true)
    expect(pack.nCampaigns).toBe(2)
    expect(chromaProduct(pack, 0).missing).toMatch(/template/)
    expect(() => buildPack({ ...meta, sections: {} }, buf, 'x')).toThrow()
  })
  it('lists stacks and filters frames', () => {
    expect(passEntries(pack, 0)).toEqual([{ pass: 0, det: 1 }, { pass: 1, det: 1 }])
    expect(stackImage(pack, 0, 2)).toBeNull()
    expect(filterFrames(pack, 2, 0, 9)).toEqual([1, 3])
    expect(filterFrames(pack, 0, 1.4, 1.55)).toEqual([1])
    expect(selectionFrames(pack, { kind: 'group', frame: -1, pass: 1, det: 0 }, 0)).toEqual([2, 3])
    expect(selectionFrames(pack, { kind: 'frame', frame: -1, pass: 0, det: 0 }, 3)).toEqual([3])
  })
  it('makes pair differences in the browser when the pipeline has not', () => {
    const nv = naiveProduct(pack, 0)
    expect(nv.partner).toBe(2)
    expect(nv.note).toBeTruthy()
    // the star moved by one pixel and brightened: negative lobe where it now is
    expect(nv.data![4 * 9 + 5]).toBeLessThan(-50)
    expect(nv.data![0]).toBeNaN()
    expect(gatedProduct(pack, 0).partner).toBe(2)
    expect(gatedProduct(pack, 1).missing).toMatch(/No usable partner/)
  })
  it('maps the wavelength mismatch and stacks frames', () => {
    const m = mismatchMap(pack, 0, 2)!
    expect(m[40]).toBeCloseTo(-0.2, 5)
    expect(mismatchMap(pack, 0, -1)).toBeNull()
    const mean = meanImage(pack, [0, 2])!
    expect(mean[0]).toBeCloseTo(decodeFrame(pack.img, 2, 9, meta.encoding)[0], 6)
    expect(flagsRgba(pack.flags!, 0, 9)[(8 * 9 + 0) * 4 + 3]).toBeGreaterThan(0)
  })
  it('measures spectra and centroids', () => {
    expect(lamAt([1, 0.001, 0.002], 5, 6, 9)).toBeCloseTo(1.005, 9)
    expect(lamAt([null, 0, 0], 5, 6, 9)).toBeNaN()
    const flat = (k: number) => (k === 0 ? NaN : 2)
    expect(apertureSum(flat, 9, 4, 4, 1)).toEqual({ sum: 18, npix: 9 })
    expect(apertureSum(flat, 9, 1, 1, 1)).toBeNull() // touches the NaN pixel
    expect(apertureSum(flat, 9, 8, 4, 1)).toBeNull() // off the edge
    const sp = spectrumAt(pack, 4, 4, 1)
    expect(sp.points).toHaveLength(4)
    expect(sp.points[0].err).toBeCloseTo(0.01 * 3 * ujyPerMjySr(6.15), 6)
    expect(sp.points[1].flux).toBeGreaterThan(sp.points[0].flux)
    expect(spectrumAt(pack, 1, 1, 1).skipped).toBe(1)
    const csv = spectrumCsv(sp.points, ['test'], [0.9, 1.1]).split('\n')
    expect(csv[0]).toBe('# test')
    expect(csv).toHaveLength(7)
    expect(csv[2].endsWith(',1')).toBe(true)
    const big = new Float32Array(31 * 31)
    for (let y = 0; y < 31; y++) for (let x = 0; x < 31; x++) big[y * 31 + x] = 0.1 + 5 * Math.exp(-((x - 16.3) ** 2 + (y - 14.6) ** 2) / 2.4)
    const c = centroid(big, 31, 15, 15, 3)!
    expect(c.x).toBeCloseTo(16.3, 1)
    expect(c.y).toBeCloseTo(14.6, 1)
    expect(centroid(new Float32Array(31 * 31), 31, 15, 15)).toBeNull()
  })
})

describe('stretch and colour', () => {
  it('computes percentiles ignoring missing data', () => {
    expect(percentiles([NaN, 1, 2, 3, 4, 5], [0, 50, 100])).toEqual([1, 3, 5])
    expect(percentiles([NaN], [50])[0]).toBeNaN()
  })
  it('has monotonic transfer functions pinned at 0 and 1', () => {
    for (const k of ['asinh', 'linear', 'log'] as const) {
      expect(stretchUnit(k, -1)).toBe(0)
      expect(stretchUnit(k, 0)).toBe(0)
      expect(stretchUnit(k, 2)).toBeCloseTo(1, 12)
      expect(stretchUnit(k, 0.3)).toBeLessThan(stretchUnit(k, 0.6))
    }
    expect(normalise('linear', 0, -5, 5, true)).toBe(0.5)
    expect(normalise('linear', -5, -5, 5, true)).toBe(0)
    expect(normalise('asinh', 2, -5, 5, true)).toBeGreaterThan(0.5)
  })
  it('renders north up and marks missing pixels', () => {
    const px = renderRgba([0, 1, NaN, 0.5], 2, 2, { kind: 'linear', lo: 0, hi: 1, symmetric: false, cmap: 'grey' })
    expect(px.length).toBe(16)
    expect(px[8]).toBeLessThan(10) // data row 0 is the bottom picture row
    expect(px[12]).toBeGreaterThan(240)
    expect(px[0]).not.toBe(px[4]) // NaN hatch differs from data
    const lut = cmapLut('perceptual')
    const lum = (i: number) => 0.2126 * lut[i * 3] + 0.7152 * lut[i * 3 + 1] + 0.0722 * lut[i * 3 + 2]
    for (let i = 8; i < 256; i += 8) expect(lum(i)).toBeGreaterThan(lum(i - 8))
    expect(Array.from(cmapLut('diverging').slice(127 * 3, 127 * 3 + 3)).every((v) => v < 40)).toBe(true)
  })
  it('up-samples smoothly, keeps flat fields flat and missing pixels missing', () => {
    const flat = upsampleBicubic(new Float32Array(16).fill(3), 4, 4)
    expect(flat.length).toBe(256)
    expect(Math.max(...flat) - Math.min(...flat)).toBeLessThan(1e-6)
    const src = new Float32Array(25)
    src[12] = 1
    src[0] = NaN
    const up = upsampleBicubic(src, 5, 3)
    expect(up[7 * 15 + 7]).toBeCloseTo(1, 5)
    expect(up[0]).toBeNaN()
    expect(up[7 * 15 + 9]).toBeGreaterThan(0.3)
  })
})

describe('URL state', () => {
  it('round-trips a full view', () => {
    const q = 'field=barnard&ra=269.44700&dec=4.76900&fov=4&det=3&mode=compare&frame=42&seq=frames&st=log&cm=perceptual&lim=5,99&sm=1&lam=1,2.5&ov=gaia,flags&pix=30,31&ap=2&embed=1'
    const s = parseQuery(q)
    expect(s).toMatchObject({ page: 'view', field: 'barnard', ra: 269.447, dec: 4.769, fov: 4, det: 3, mode: 'compare', frame: 42, embed: true, overlays: ['gaia', 'flags'], pix: [30, 31], ap: 2, smooth: true })
    expect(parseQuery(toQuery(s))).toEqual(s)
  })
  it('falls back on bad input and keeps defaults out of the URL', () => {
    const s = parseQuery('?ra=abc&dec=4&mode=nope&det=9&frame=-3&field=../x')
    expect(s).toEqual({ ...DEFAULT_STATE })
    expect(toQuery(DEFAULT_STATE)).toBe('')
    expect(parseQuery('ra=133.795&dec=-7.245').page).toBe('view')
    expect(parseQuery('page=about').page).toBe('about')
    expect(parseQuery('ov=').overlays).toEqual([])
  })
})

describe('engine replies and field matching', () => {
  it('normalises job replies', () => {
    expect(parseJobId('abc')).toBe('abc')
    expect(parseJobId({ job_id: 7 })).toBe('7')
    expect(parseJobId({})).toBeNull()
    expect(parseJob({ state: 'RUNNING', progress: 40, message: 'x', key: 'k' })).toEqual({ state: 'running', progress: 0.4, message: 'x', key: 'k' })
    expect(parseJob(null)).toEqual({ state: 'unknown', progress: null, message: '', key: null })
  })
  it('finds the field for coordinates and the nearest ones otherwise', () => {
    const fields = [
      { key: 'barnard', name: 'B', kind: 'motion', ra: 269.446288, dec: 4.767983, n: 61, scale: 6.15, nFrames: 1, nCampaigns: 1 },
      { key: 'rwaur', name: 'R', kind: 'variable', ra: 76.956417, dec: 30.401417, n: 61, scale: 6.15, nFrames: 1, nCampaigns: 1 },
    ]
    expect(fieldContaining(fields, 269.45, 4.77)?.key).toBe('barnard')
    expect(fieldContaining(fields, 269.452075, 4.693391)).toBeNull() // J2000 position: the star has left
    expect(presetNear(269.452075, 4.693391)?.key).toBe('barnard')
    expect(presetNear(133.795, -7.245)?.key).toBe('wise0855')
    expect(nearestFields(fields, 80, 30)[0].field.key).toBe('rwaur')
  })
})

describe('the real Barnard pack', () => {
  const dir = resolve(__dirname, '../../public/data/barnard')
  it.skipIf(!existsSync(resolve(dir, 'meta.json')))('decodes into a plausible sky', () => {
    const meta = JSON.parse(readFileSync(resolve(dir, 'meta.json'), 'utf8')) as Meta
    const b = readFileSync(resolve(dir, 'cube.bin'))
    const pack = buildPack(meta, b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer, 'data')
    expect(pack.nFrames).toBe(meta.frames.mjd.length)
    expect(pack.n).toBe(meta.n)
    const mid = decodeFrame(pack.img, Math.floor(pack.nFrames / 2), pack.n, meta.encoding)
    const [p5, p50, p99] = percentiles(mid, [5, 50, 99.9])
    expect(Math.abs(p50)).toBeLessThan(0.5) // sky-subtracted background near zero, MJy/sr
    expect(p99).toBeGreaterThan(p50 + 5 * (p50 - p5))
    expect(pack.stack).not.toBeNull()
    expect(passEntries(pack, 0).length).toBeGreaterThanOrEqual(2)
    const sp = spectrumAt(pack, Math.floor(pack.n / 2), Math.floor(pack.n / 2), 1)
    expect(sp.points.length + sp.skipped).toBe(pack.nFrames)
    for (let i = 1; i < pack.nFrames; i++) expect(meta.frames.mjd[i]).toBeGreaterThanOrEqual(meta.frames.mjd[i - 1])
  })
})
