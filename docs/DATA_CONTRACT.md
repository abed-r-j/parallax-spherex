# ParallaX data pack (contract between the Python pipeline and the web app)

A *field* is one patch of sky. The pipeline writes one folder per field; the web app only
reads these files, so the site is fully static and works offline.

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
  "science": {}, "ledger": {}
}
```

### `encoding` and the `img` / `tpl` sections

Surface brightness `v` (MJy/sr, zodiacal light and residual sky removed) is stored as

```
q = 0                                             no data
q = 1 + round( (asinh(v / soft) - lo) / (hi - lo) * 65534 )     otherwise (uint16)
```

so `v = soft * sinh(lo + (q - 1) / 65534 * (hi - lo))`.
1 MJy/sr = 889.86 microJy per 6.15 arcsec pixel.

### Sections of cube.bin

| name | dtype | shape | meaning |
|---|---|---|---|
| `img` | uint16 | [N, n, n] | calibrated image, encoded as above |
| `flags` | uint8 | [N, n, n] | bit 1 = no data / dead pixel, 2 = suspect (transient, overflow, non-linear, persistence), 4 = catalogued source, 8 = pipeline outlier |
| `tpl` | uint16 | [N, n, n] | chromatic template: what a static sky would look like in this frame, predicted from the *other* survey passes at this frame's per-pixel wavelength. Encoded like `img`. 0 = no prediction |
| `snrCorr` | int8 | [N, n, n] | (img - tpl) / sigma, times 4, clipped to +-127; -128 = undefined |
| `snrNaive` | int8 | [N, n, n] | same for the naive pair difference (frame minus `naivePartner`) |
| `snrGated` | int8 | [N, n, n] | same for the wavelength-gated pair difference (frame minus `gatedPartner`); all -128 when the frame has no partner |
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
  moves each star to the frame date.
* `wise[]`: `{ id, ra, dec, w1, w2, pmRa, pmDec }` (CatWISE2020).
* `sso[]`: known solar-system objects predicted inside a frame:
  `{ frame, name, number, ra, dec, x, y, vmag, rateRa, rateDec, source }` (rates arcsec/h).

### Detections and candidates

* `detections[]`: `{ frame, x, y, ra, dec, snr, fluxUJy, cls, known }` from `snrCorr`.
  `cls` is `mover`, `variable`, `motion-dipole`, `chromatic`, `star-residual` or `artifact`;
  `known` is the name of a matching catalogued solar-system object or null.
* `candidates[]`: linked detections: `{ id, cls, frames: [], ra: [], dec: [], mjd: [],
  rate: arcsec/h or null, pa: deg or null, known, note }`.

### `science` and `ledger`

Free-form but stable blocks filled by the pipeline:
`science.motion` (measured proper motion of the target vs catalogue),
`science.lightcurve` (variable-star light curve at matched wavelength),
`ledger` (the three-way comparison naive / gated / chromatic: false detections per square
degree, usable-frame yield, depth, injection-recovery curves).
