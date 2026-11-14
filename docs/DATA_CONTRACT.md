# ParallaX data pack (contract between the Python pipeline and the web app)

A *field* is one patch of sky. The pipeline writes one folder per field; the web app only
reads these files, so the site is fully static and works offline.

SI disclosure: drafted with the help of an SI coding assistant (Claude, by Anthropic), checked by the team.

```
web/public/data/
  index.json                 list of fields
  <key>/meta.json            everything except pixels
  <key>/cube.bin             pixels, little-endian, sections described in meta.json
```

Every array over frames is ordered by time (`mjd` ascending). Pixel coordinates are
0-based, `x` to the right (west), `y` up (north) on a north-up, east-left tangent grid
of `n` x `n` pixels of `scale` arcsec centred on (`ra0`, `dec0`). Array layout in
`cube.bin` is C order: `[frame][y][x]`.

## index.json

```json
{ "generated": "2026-11-13T20:00:00Z", "pipeline": "1.0.0",
  "fields": [ { "key": "barnard", "name": "Barnard's Star", "kind": "motion",
                "ra": 269.446, "dec": 4.768, "n": 61, "scale": 6.15, "nFrames": 358,
                "nCampaigns": 3, "blurb": "...", "thumb": "barnard/thumb.png" } ] }
```

`kind` is one of `motion`, `variable`, `mover`, `static`, `custom`.

## meta.json

```json
{
  "key": "barnard", "name": "Barnard's Star", "kind": "motion", "blurb": "...",
  "ra0": 269.446, "dec0": 4.768, "n": 61, "scale": 6.15,
  "target": { "name": "...", "ra": 0, "dec": 0, "epoch": 2000.0, "pmRa": 0, "pmDec": 0 },
  "release": { "collections": ["spherex_dr1", "spherex_qr3"], "doi": ["10.26131/IRSA678"],
               "retrieved": "2026-11-13" },
  "encoding": { "soft": 0.05, "lo": -1.2, "hi": 9.7 },
  "sections": { "img": { "offset": 0, "dtype": "uint16", "shape": [358, 61, 61] }, "...": {} },
  "frames": { "mjd": [], "iso": [], "det": [], "campaign": [], "lam": [], "bw": [],
              "lamFit": [[a, bx, by]], "sigma": [], "sky": [], "zodi": [], "fwhm": [],
              "name": [], "collection": [],
              "naivePartner": [], "gatedPartner": [], "nRef": [] },
  "campaigns": [ { "index": 0, "start": "2025-08-15", "end": "2025-08-28", "nFrames": 120 } ],
  "gaia": [], "wise": [], "sso": [], "detections": [], "candidates": [],
  "science": {}, "ledger": {},
  "live": {}
}
```

`live` is present only on fields built in the browser (see "Fields built in the browser"
below); pipeline packs do not carry it.

### `encoding` and the `img` / `tpl` sections

Surface brightness `v` (MJy/sr, zodiacal light and residual sky removed) is stored as

```
q = 0                                             no data
q = 1 + round( (asinh(v / soft) - lo) / (hi - lo) * 65534 )     otherwise (uint16)
```

so `v = soft * sinh(lo + (q - 1) / 65534 * (hi - lo))`. `lo` and `hi` are the asinh of the
true minimum and maximum of the finite pixels, so no finite value is clipped (an earlier
version clipped the faint end at a percentile).
1 MJy/sr = 889.86 microJy per 6.15 arcsec pixel.

### Sections of cube.bin

| name | dtype | shape | meaning |
|---|---|---|---|
| `img` | uint16 | [N, n, n] | calibrated image, encoded as above |
| `flags` | uint8 | [N, n, n] | bit 1 = no data / dead pixel, 2 = suspect (transient, overflow, non-linear, persistence), 4 = catalogued source, 8 = pipeline outlier |
| `tpl` | uint16 | [N, n, n] | chromatic template: what a static sky would look like in this frame, predicted from the *other* survey passes at this frame's per-pixel wavelength. Encoded like `img`. 0 = no prediction |
| `snrCorr` | int8 | [N, n, n] | (img - tpl) / sigma, times 4, clipped to +-127; -128 = undefined |
| `snrNaive` | int8 | [N, n, n] | same for the naive pair difference (frame minus `naivePartner`). The sigma includes the fitted "star noise" term (see RESULTS.md section 2.2), not only the statistical variance |
| `snrGated` | int8 | [N, n, n] | same for the wavelength-gated pair difference (frame minus `gatedPartner`), also with the star-noise term in sigma; all -128 when the frame has no partner |
| `stack` | float32 | [C, 6, n, n] | per survey pass, per detector, inverse-variance mean image in MJy/sr (NaN = no data) |

Sections other than `img`, `flags` and `stack` may be absent; the app must cope.

### `frames`

* `lam`, `bw`: wavelength and bandwidth (micron) at the field centre.
* `lamFit`: `[a, bx, by]` with `lambda(x, y) = a + bx*(x - c) + by*(y - c)`, `c = (n-1)/2`.
  The wavelength changes across the field because SPHEREx uses a linear variable filter.
* `sigma`: median 1-sigma pixel noise of the frame (MJy/sr).
* `naivePartner`: index of the frame a naive blink would compare against (same detector,
  nearest in time in another survey pass), or -1.
* `gatedPartner`: index of the frame in another pass whose wavelength at the field centre
  is closest, accepted only if it differs by less than half a bandwidth; otherwise -1.
* `nRef`: median effective number of reference frames behind the chromatic template.

### Overlays

* `gaia[]`: `{ id, ra, dec, pmRa, pmDec, plx, g }` at epoch 2016.0 (Gaia DR3); the app
  moves each star to the frame date. `id` is a **string**: Gaia source identifiers exceed
  2^53 and would lose digits as JSON numbers. `ra`, `dec` in degrees, `pmRa` (includes
  cos(dec)) and `pmDec` in mas/yr, `plx` in mas, `g` in magnitudes.
* `wise[]`: `{ id, ra, dec, w1, w2, pmRa, pmDec }` (CatWISE2020). Positions are the
  catalogue's motion-fit positions at epoch MJD 57170 (**2015.4**), in degrees; `pmRa` and
  `pmDec` are in **mas/yr** (converted from the table's arcsec/yr); `w1`, `w2` in Vega
  magnitudes. Rows that come from the AllWISE fallback (used where CatWISE2020 has a hole)
  are at epoch 2010.56. CatWISE motions are unreliable for very fast stars (Barnard's Star
  appears as two entries with wrong motions), so the app should not use them to move fast
  stars.
* `sso[]`: known solar-system objects predicted inside a frame:
  `{ frame, name, number, ra, dec, x, y, vmag, rateRa, rateDec, source }`. `ra`, `dec`,
  `x`, `y` are the position as seen from SPHEREx at the frame time (JPL Horizons) when
  `source` says it was refined, otherwise the geocentric SkyBoT position. `rateRa` and
  `rateDec` (arcsec/h) are always the **geocentric** rates from SkyBoT, because the rate seen
  from the spacecraft wobbles with its 98-minute orbit. `vmag` may be **null**.

### Detections and candidates

* `detections[]`: `{ frame, x, y, ra, dec, snr, fluxUJy, cls, known, npix, evidence }` from
  `snrCorr`. `cls` is `mover`, `variable`, `motion-dipole`, `chromatic`, `star-residual` or
  `artifact`; `known` is the name of a matching catalogued solar-system object or null;
  `npix` is the number of connected pixels above the detection threshold; `evidence` is a
  short sentence saying why the class was given. A positive detection within 2.5 pixels of
  a predicted object brighter than V 17.5 gets `known` set and `cls: "mover"`; if the
  classifier alone had said something else, `evidence` ends with
  `"; named from the ephemeris (classifier alone: <class>)"`, so what the pipeline found
  blind is never lost.
* `candidates[]`: linked or grouped detections: `{ id, cls, frames: [], ra: [], dec: [],
  mjd: [], rate: arcsec/h or null, pa: deg or null, known, note, chance }`.
  * Linked movers have `cls: "mover"`, a fitted `rate` and `pa`, and `chance`, the expected
    number of chance alignments of unrelated detections that would look the same.
  * Grouped candidates collect repeated detections at one place: ids starting with `D` are
    `motion-dipole` groups (a bright and a dark lobe side by side) and ids starting with `V`
    are `variable` groups. For these `rate` and `pa` are null.
  * The app also shows `verdict` and `snr` columns when a candidate carries them.

### `science` and `ledger`

Free-form but stable blocks filled by the pipeline:
`science.motion` (measured proper motion of the target vs catalogue),
`science.lightcurve` (variable-star light curve at matched wavelength),
`ledger` (the three-way comparison naive / gated / chromatic: false detections per square
degree, usable-frame yield, depth, injection-recovery curves).

The ledger's per-method results sit under `ledger.modes.<mode>` with the mode keys `naive`,
`gated` and **`corrected`**. `corrected` is the chromatic template; readers should accept
`chromatic` as a synonym and label both "Chromatic template". Each mode holds
`usableFraction`, `usableFrames`, `depthUJy`, `depthPlainUJy`, `false`, `falsePlain`,
`snrWidth`, `falseUnitMad`, `thresholdAtFixedRate`, `knownSignal`, `starNoiseGain` and
`detectionsByClassPerFrame`; the injection-recovery curves are under
`ledger.injection.atThreshold5` and `ledger.injection.atFixedRate`.

* Every rate block (`false`, `falsePlain`, `falseUnitMad`, `falsePlainModelError`,
  `falsePairCalibration`) is `{ perFrame, positivePerFrame, perDeg2, pixelFraction }`:
  detections at |S/N| > `ledger.threshold` per usable frame outside the excluded radius;
  `positivePerFrame` counts positive detections only. Frames without a result are left out
  of both the count and the denominator.
* `false`: each method's own noise model. The pairs get the fitted star-noise term; the
  template gets the larger of that term and its model-error map. Not like for like.
* `falsePlain`: **one purely statistical sigma for all three methods** (no star-noise term,
  and no model-error map for the template). Under it the template floods like the pairs.
* `falsePlainModelError` (`corrected` only): statistical sigma plus the template's
  model-error map. An earlier version published this number as `falsePlain`.
* `falsePairCalibration` and `depthPairCalibrationUJy` (`corrected` only): the template
  with exactly the pairs' calibration (star-noise term, no model-error map); the depth is
  `{ all, faint }` like `depthUJy`.
* `snrWidth`: `{ faint, mid, bright }`, the robust width (1.4826 MAD) of the S/N outside the
  target mask on pixels whose static sky is below 3, 3 to 10 and above 10 sigma (classes
  defined on the chromatic template); 1.0 means a calibrated sigma.
* `falseUnitMad`: the rate after dividing each class of each method's S/N by that width.
* `ledger.rateScan`: `{ rates: [0.2, 0.5, 1.0], byMode: { <mode>: { "<rate>": { threshold,
  f50Blank, f50Star } } } }`: the S/N threshold that gives that many false detections per
  frame and the flux (microJy) at which half of the injected movers are recovered on blank
  sky and next to a star; `null` where 50% is not reached. Present only when the injection
  test was run (the two mover fields do not have it). It sits beside `injection`, not inside
  it, because the app lists every entry of `injection` as a set of curves.
* `ledger.notes` repeats these definitions in words; the app prints them.

## Fields built in the browser (`meta.live`)

For coordinates outside the published packs the web app can build a field itself from the
public archive (`web/src/lib/live.ts`). Such a field is handed to the viewer as an ordinary
pack held in memory, with one extra block, `meta.live`, whose shape is the `LiveInfo`
interface in `web/src/lib/types.ts`:

```json
"live": {
  "source": "...",          "complete": true,
  "available": 413,         "matching": 55,   "requested": 55,  "dropped": 0,
  "loaded": 55,             "skipped": 0,     "failed": 0,
  "bytes": 21400000,        "requests": 111,  "seconds": 11.2,
  "detectors": [3],         "sizeArcmin": 3,  "indexBuilt": "2026-11-13T..."
}
```

| key | meaning |
|---|---|
| `source` | where the pixels came from (the public SPHEREx bucket) |
| `complete` | false while frames are still arriving |
| `available` | images that cover the position, all detectors |
| `matching` | of those, in the chosen detectors |
| `requested` | images requested after the maximum-count cut (evenly spaced in time) |
| `dropped` | `matching - requested` |
| `loaded` | images read and resampled |
| `skipped` | images where the field falls mostly off the detector |
| `failed` | network errors after all retries |
| `bytes`, `requests`, `seconds` | cost of the fetch |
| `detectors` | detectors used (1 to 6; empty means all six) |
| `sizeArcmin` | requested field size |
| `indexBuilt` | build time of the sky index that listed the images |

A live field has the `img`, `flags` (only the no-data bit) and `stack` sections. It has no
`tpl`, `snrCorr`, `snrNaive` or `snrGated` sections and empty `gaia`, `wise`, `sso`,
`detections`, `candidates`, `science` and `ledger` blocks; the app computes the naive and
gated pair differences itself and labels them as browser-computed. The numbers in the example
are illustrative of a real M51 run (55 images, 21.4 MB, 111 requests).
