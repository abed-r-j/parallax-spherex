# ParallaX: measured results

Every number here comes from real SPHEREx Level-2 images (DR1, doi:10.26131/IRSA678, and QR3,
doi:10.26131/IRSA662) retrieved from NASA/IPAC IRSA on 13 November 2026, and can be
regenerated with

```
python pipeline/scripts/run_ledger.py       # three-way comparison, writes data/ledger/*.json
python pipeline/scripts/run_validation.py   # target measurements, writes data/science/*.json
```

Run time is two to four minutes per field on a laptop (i7-11800H).

## 1. Data used

| Field | Images | Survey passes | Field of view | Note |
|---|---|---|---|---|
| Barnard's Star | 357 | 3 | 6.25 arcmin | core saturated in 99% of frames |
| Epsilon Indi B | 454 | 4 | 6.25 arcmin | unsaturated |
| WISE 0855-0714 | 258 | 3 | 8.3 arcmin | invisible in single frames |
| RW Aurigae | 332 | 3 | 6.25 arcmin | core saturated in 39% of frames |
| R Draconis | 590 of 2,493 available | continuous (deep field) | 6.25 arcmin | core saturated in 97% of frames |

A typical position is seen in about 75 pointings per survey pass, within roughly two weeks,
each at a different wavelength; passes repeat about every six months.

## 2. Three ways to difference two dates

* **Naive pair**: a frame minus the same-detector frame nearest in time from another pass.
  This is what a plain blink comparator does.
* **Wavelength-gated pair**: a frame minus the other-pass frame closest in wavelength,
  accepted only if they differ by less than half a filter bandwidth. This is the approach
  taken by the other tools we surveyed.
* **Chromatic template** (ours): a frame minus a prediction of the static sky at that
  frame's per-pixel wavelength, built from the spectrum each pixel showed in the other passes.

False detections are residual sources with |S/N| > 5 and at least two pixels, counted
outside 14 pixels of the known changing target, per usable frame. Depth is the median
one-sigma noise of the difference per pixel over all pixels (the app's ledger panel also
shows the depth on faint sky only, which is a little lower: 35.9 / 31.8 / 28.0 microJy for
Barnard's field). "f50" is the flux at which half of the injected
moving point sources are recovered, at a detection threshold tuned so that every method
yields the same false-detection rate (0.5 per frame).

| Field | Method | Usable frames | Depth (microJy) | False detections per frame | Same, plain noise model | f50, blank sky (microJy) | f50, next to a star (microJy) |
|---|---|---|---|---|---|---|---|
| Barnard's Star | naive | 93.6% | 38.9 | 4.64 | 28.70 | 1457 | 2334 |
| | gated | 96.4% | 33.8 | 2.44 | 31.99 | 1025 | 1668 |
| | **chromatic** | **100%** | **30.5** | **0.99** | **1.91** | **563** | **1047** |
| Epsilon Indi B | naive | 100% | 28.4 | 2.51 | 7.56 | 955 | 1524 |
| | gated | 99.3% | 25.3 | 2.34 | 7.88 | 808 | 1176 |
| | **chromatic** | **100%** | **24.5** | **2.09** | **2.23** | **571** | **1094** |
| RW Aurigae | naive | 100% | 30.4 | 3.28 | 24.84 | 1014 | 1349 |
| | gated | 99.4% | 30.2 | 2.54 | 23.67 | 1150 | 1568 |
| | **chromatic** | **100%** | **25.8** | **1.28** | **1.81** | **593** | **982** |
| WISE 0855-0714 | naive | 100% | 27.5 | 3.54 | 18.98 | 2193 | not reached |
| | gated | 98.8% | 19.1 | 2.22 | 19.77 | 859 | 1326 |
| | **chromatic** | **99.6%** | **18.0** | **1.64** | **2.07** | **707** | **1157** |
| R Draconis | naive | 100% | 147.4 | 0.49 | 3.27 | 1793 | not reached |
| | gated | 79.0% | 106.8 | 0.58 | 3.30 | 1743 | not reached |
| | chromatic | 97.1% | 103.1 | 0.61 | 1.26 | 1136 | not reached |

The "plain noise model" column uses only the pipeline's statistical variance for the pair
methods; the main column gives every method the same fitted "star noise" term (see 2.2).

### 2.1 What the comparison shows

* The chromatic template is 3 to 15% deeper than the gated pair in every field.
* At a matched false-detection rate it recovers moving sources 1.2 to 1.8 times fainter than
  the gated pair on blank sky (Barnard's field: 563 against 1025 microJy).
* It gives fewer false detections than the gated pair in four of five fields (Barnard's
  field: 0.99 against 2.44 per frame, i.e. 109 against 269 per square degree per frame).
* It needs no partner frame, so it uses every frame; the gated pair loses 1 to 4% of frames
  in ordinary fields and 21% in the R Draconis deep field.

### 2.2 What it does not show (limits we measured)

* **Gating costs few frames.** 96 to 99% of frames find a partner within half a bandwidth,
  because the survey revisits at nearly repeating wavelengths. The advantage of the template
  is depth and false-alarm rate, not rescued frames.
* **Pixel sampling, not colour, is the largest noise term.** SPHEREx pixels (6.15 arcsec)
  under-sample the image: the peak pixel of a bright star scatters by 23 to 27% from frame
  to frame at fixed wavelength. This is why pair differences flood with false detections
  under a purely statistical noise model, and why the template carries an empirical
  model-error map. Frame registration is not the problem (0.16 arcsec rms on 25 stars).
* **For a star that moves by one or two pixels, a pair shows the two-lobe signature better
  than the template.** Both lobes exceed 5 sigma in 69% of Barnard frames for the gated pair
  against 17% for the template, because a template built from two other passes averages
  two old positions. For such stars the tool defaults to blinking and subtracting per-pass
  stacks.
* **R Draconis is not a clean test.** The saturated Mira fills the cutout; depth is three to
  four times worse in every method and the template has slightly more false detections
  (0.61 against 0.58 per frame).
* Injected sources are achromatic Gaussian point sources; the 14-pixel exclusion radius and
  the 0.5-per-frame matched rate are our choices and are recorded in the ledger files.

## 3. The five challenge targets

| Target | What we measured | Reference |
|---|---|---|
| Barnard's Star | proper motion 10.21 +- 0.26 arcsec/yr at position angle 356.3 +- 1.5 deg (shift of 1.65 pixels over 3 passes, from the wings of a saturated star) | 10.36 arcsec/yr at 355.6 deg (Gaia DR3) |
| Epsilon Indi B | 4.64 +- 0.09 arcsec/yr at 122.6 +- 1.3 deg (shift of 1.02 pixels over 4 passes) | 4.70 arcsec/yr at 122.7 deg |
| WISE 0855-0714 | a moving source at S/N 6.6 in stacks of detectors 5 and 6 only (395 +- 69 microJy), 1.5 arcsec from the predicted position; 7.81 +- 1.57 arcsec/yr at 278.2 +- 4.3 deg; absent in detectors 1-4 | 8.15 arcsec/yr at 274.8 deg |
| RW Aurigae | in September 2025, compared with September 2026, the star was 0.37 +- 0.14 mag fainter at 0.75-1.1 micron and 0.76 +- 0.03 mag brighter at 4.4-5.0 micron; a control star is constant to 0.005 mag | irregular T Tauri variable |
| R Draconis | periodic change significant in 22 of 43 wavelength bins, median peak-to-peak 1.18 mag (2-3 mag near 0.8 micron, about 1 mag at 4.5 micron); free period 250 d over 2.1 cycles | Mira, catalogued period about 246 d |

Caveats that belong with these numbers:

* Sub-pixel centroids on under-sampled data scatter by 0.04 pixel (0.24 arcsec) between
  detectors for an unsaturated star and 0.11 pixel on the wings of a saturated one.
* Parallax is **not** measured reliably: the fitted annual term for Barnard's Star is about
  three times its true parallax. SPHEREx always looks about 90 degrees from the Sun, so any
  Sun-synchronous systematic imitates parallax.
* The WISE 0855 significance comes from non-independent pass differences and a search over
  about 59 trial positions; treat 6.6 as moderately optimistic. A static neighbour of 277
  microJy lies inside the same beam at shorter wavelengths.
* The challenge coordinates of WISE 0855 are its 2010 WISE position; the source is now 2
  arcmin further west, where we find it.
* R Draconis and Barnard's Star saturate SPHEREx; their fluxes come from the wings and are
  relative, not absolute. Detector 3 photometry of R Draconis is unreliable and is excluded.

## 4. Known solar-system objects as ground truth

Two extra fields contain a catalogued body whose position at every exposure is predicted by
JPL Horizons as seen from the SPHEREx spacecraft. The fields were found by an object-first
search of the archive footprints, which returned the same 136 images as IRSA's own moving
object tool for (52) Europa.

| Field | Frames | Object present in | Chromatic-difference detections labelled with the object | Median S/N | Measured minus predicted position |
|---|---|---|---|---|---|
| (52) Europa crossing, 20-21 Aug 2025 (V 12.2, detectors 3 and 6) | 111 | 24 | 24 of 24 | 188 | -0.05 +- 0.04, 0.00 +- 0.07 pixel |
| Pluto, 4-10 Oct 2025 (V 14.5, detector 2) | 46 | 18 | 18 of 18 | 50 | +0.03 +- 0.10, +0.01 +- 0.04 pixel |

* The asteroid moves about 28 arcsec per hour and crosses the 6 arcmin field in three visits
  ten hours apart; Pluto drifts 12 pixels in 6.4 days.
* A single-exposure spectrum of (52) Europa from 45 clean frames between 0.79 and 4.97 micron
  shows reflected sunlight (about 80-87 mJy up to 1.9 micron), a minimum of about 33 mJy
  near 3.0-3.5 micron and thermal emission rising to 361 mJy at 4.97 micron. These are box
  sums without aperture or phase correction.
* In the archive's own flags, about half of the pixels on the asteroid carry the OUTLIER
  bit: a pipeline that masks outliers would erase the mover.
* These two fields use a subset of detectors; they are demonstrations of recovery, not part
  of the three-way ledger above.
* Labels are attached only for objects brighter than V = 17.5; fainter catalogued asteroids
  in a field are drawn as predictions but never used to name a detection.

## 5. Engineering numbers

* Cutouts by HTTP range request: about 0.5 MB per image instead of the 65 MB file, with
  pixels identical to the IRSA cutout service; 358 images of one field in 13 minutes.
* Sky index: all 1,628,230 public Level-2 images in 45.6 MB; zero misses against the live
  archive at six test positions.
* In-browser live mode: 55 images of M51 in 10 to 12 seconds, no server (fast connection;
  one to two minutes on a slow one).
* 120 Python tests and 55 TypeScript tests, all offline (2 more Python tests call live services and are skipped unless `PARALLAX_NETWORK=1` is set).
