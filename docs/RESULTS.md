# ParallaX: measured results

Every number here comes from real SPHEREx Level-2 images (DR1, doi:10.26131/IRSA678, and QR3,
doi:10.26131/IRSA662) retrieved from NASA/IPAC IRSA on 13 November 2026, and can be
regenerated with

```
python pipeline/scripts/run_ledger.py       # three-way comparison, writes data/ledger/*.json
python pipeline/scripts/run_validation.py   # target measurements, writes data/science/*.json
```

Run time is two to four minutes per field on a laptop (i7-11800H).

SI disclosure: drafted with the help of an SI coding assistant (Claude, by Anthropic), checked by the team.

## 1. Data used

| Field | Images | Survey passes | Field of view | Note |
|---|---|---|---|---|
| Barnard's Star | 357 | 3 | 6.25 arcmin | core saturated in 99% of frames |
| Epsilon Indi B | 454 | 4 | 6.25 arcmin | unsaturated |
| WISE 0855-0714 | 258 | 3 | 8.3 arcmin | invisible in single frames |
| RW Aurigae | 332 | 3 | 6.25 arcmin | core saturated in 39% of frames |
| R Draconis | 590 of 2,493 available | continuous (deep field) | 6.25 arcmin | core saturated in 97% of frames |

In these fields a position is typically seen in 60 to 150 frames per survey pass, spread
over two to eight weeks, each at a different wavelength; passes repeat about every six months.

## 2. Three ways to difference two dates

* **Naive pair**: a frame minus the same-detector frame nearest in time from another pass.
  This is what a plain blink comparator does.
* **Wavelength-gated pair**: a frame minus the other-pass frame closest in wavelength,
  accepted only if they differ by less than half a filter bandwidth. This is the approach
  taken by most of the other tools we surveyed.
* **Chromatic template** (ours): a frame minus a prediction of the static sky at that
  frame's per-pixel wavelength, built from the spectrum each pixel showed in the other passes.

False detections are residual sources with |S/N| > 5 and at least two pixels, counted
outside 14 pixels of the known changing target, per usable frame. Depth is the median
one-sigma noise of the difference per pixel over all pixels (the app's ledger panel also
shows the depth on faint sky only, which is a little lower: 35.9 / 31.8 / 28.0 microJy for
Barnard's field). "f50" is the flux at which half of the injected
moving point sources are recovered, at a detection threshold tuned so that every method
yields the same false-detection rate (0.5 per frame).

| Field | Method | Usable frames | Depth (microJy) | False detections per frame | Same, with one purely statistical sigma for all three | f50, blank sky (microJy) | f50, next to a star (microJy) |
|---|---|---|---|---|---|---|---|
| Barnard's Star | naive | 93.6% | 38.9 | 4.44 | 27.55 | 1427 | 2297 |
| | gated | 96.4% | 33.8 | 2.40 | 31.38 | 1003 | 1641 |
| | **chromatic** | **100%** | **30.5** | **0.99** | 32.98 | **563** | **1047** |
| Epsilon Indi B | naive | 100% | 28.4 | 2.51 | 7.56 | 955 | 1524 |
| | gated | 99.3% | 25.3 | 2.34 | 7.88 | 808 | 1176 |
| | **chromatic** | **100%** | **24.5** | **2.09** | 8.39 | **571** | **1094** |
| RW Aurigae | naive | 100% | 30.4 | 3.28 | 24.84 | 1014 | 1349 |
| | gated | 99.4% | 30.2 | 2.54 | 23.66 | 1150 | 1568 |
| | **chromatic** | **100%** | **25.8** | **1.28** | 24.23 | **593** | **982** |
| WISE 0855-0714 | naive | 100% | 27.5 | 3.54 | 18.98 | 2193 | not reached |
| | gated | 98.8% | 19.1 | 2.21 | 19.74 | 859 | 1326 |
| | **chromatic** | **99.6%** | **18.0** | **1.64** | 21.12 | **707** | **1157** |
| R Draconis | naive | 100% | 147.4 | 0.49 | 3.27 | 1793 | not reached |
| | gated | 79.0% | 106.8 | 0.58 | 3.30 | 1743 | not reached |
| | chromatic | 97.1% | 103.1 | 0.61 | 3.24 | 1136 | not reached |

The plain column gives all three methods one purely statistical sigma: no "star noise" term
for anyone and no model-error map for the template. Under it the template floods as much as
the pairs (33 false detections per frame in Barnard's field): its subtraction of an
under-sampled star is no cleaner than a pair's. In the main column the pairs get a fitted
"star noise" term (see 2.2) and the template gets the larger of that term and its own
measured per-pixel model-error map, which the pairs do not have. With the statistical
sigma plus that map alone the template gives 1.91 / 2.23 / 1.81 / 2.07 / 1.26 false
detections per frame in the five fields; an earlier version of this table showed those
numbers in the plain column, which was not the same noise model. The two false-detection
columns are therefore not like for like between methods. The f50 columns, taken at a
matched false-detection rate, are; see the robustness tables in 2.1.

Frames without a result are now left out of both the count and the denominator of the
false-detection rate. This changed the pair rows of Barnard's field (naive 4.64 to 4.44,
gated 2.44 to 2.40, their f50 by 2%) and the gated row of WISE 0855 (2.22 to 2.21); no
chromatic number in the main columns changed.

### 2.1 What the comparison shows

* The chromatic template is 3 to 15% deeper than the gated pair in every field in quoted
  sigma, and 17 to 25% deeper in the measured scatter of blank-sky residuals (robust
  scatter 19.5 against 26.0 microJy in Barnard's field). Bilinear resampling correlates
  the noise of neighbouring pixels in every method (the scatter of 2x2 pixel sums is 1.1 to
  1.4 times the independent-pixel value), so a per-pixel depth understates the noise per
  beam for all three.
* At a matched false-detection rate of 0.5 per frame it recovers moving sources 1.2 to 1.9
  times fainter than the gated pair on blank sky (Barnard's field: 563 against 1003
  microJy), and 1.1 to 1.6 times fainter next to a star. The factor depends on the chosen
  rate: on blank sky it is 1.1 to 2.0 for rates of 0.2 to 1 per frame and the ranking never
  flips; next to a star the advantage is gone at 0.2 per frame (in Eps Indi the gated pair
  is then better, elsewhere no method reaches 50%).
* A raw count of false detections at |S/N| > 5 is not a like-for-like comparison, because
  the methods' sigmas are not equally well calibrated: the robust width of the S/N outside
  the target mask is 0.65 to 0.88 on faint sky and 0.79 to 0.94 on stars for the template
  (sigma too large), against 0.71 to 0.97 and 1.22 to 1.85 for the gated pair (sigma too
  small on stars). The template gives fewer false detections than the gated pair in
  Barnard's and RW Aurigae's fields under every calibration we tried (Barnard: 0.99 against
  2.40 per frame as tabulated, i.e. 109 against 265 per square degree per frame; 1.89
  against 2.40 with the pairs' calibration; 1.57 against 1.87 after rescaling every S/N to
  unit width). In Eps Indi and WISE 0855 the sign depends on the noise model, and in
  R Draconis the template has slightly more. The like-for-like comparison is the
  matched-rate f50.
* A stronger trivial baseline does not beat the template: the inverse-variance mean of all
  other-pass frames inside the half-bandwidth gate, calibrated like the pairs, reaches f50
  of 733 / 821 / 894 microJy (Barnard, RW Aurigae, WISE 0855; blank sky, 0.5 per frame)
  against 563 / 593 / 707 for the template. Only 1 to 3 frames fall inside the gate per
  pixel, while the template reaches about 6 effective references by fitting across
  neighbouring wavelengths.
* The injection shortcut (adding the source to the S/N cube instead of to the image) was
  checked against a full re-run in Barnard's field: 320 sources injected into the images of
  80 frames, template, calibration and differences rebuilt. The peak S/N is 0.98 of the
  shortcut's in all three methods and the completeness agrees within 0 to 4 percentage
  points; the shortcut is slightly optimistic for all three equally.
* It needs no partner frame, so it uses 97 to 100% of frames; the gated pair loses 1 to 4% of frames
  in ordinary fields and 21% in the R Draconis deep field.

Robustness of the false-detection count (per frame at |S/N| > 5, gated pair against
chromatic template):

| Field | As in the main table | Template with exactly the pairs' calibration (no model-error map) | Every method's S/N rescaled to unit robust width | Positive detections only (main table) |
|---|---|---|---|---|
| Barnard's Star | 2.40 / 0.99 | 2.40 / 1.89 | 1.87 / 1.57 | 1.63 / 0.69 |
| Epsilon Indi B | 2.34 / 2.09 | 2.34 / 2.95 | 2.08 / 2.80 | 1.63 / 1.86 |
| RW Aurigae | 2.54 / 1.28 | 2.54 / 2.27 | 1.96 / 1.77 | 1.84 / 1.02 |
| WISE 0855-0714 | 2.21 / 1.64 | 2.21 / 3.11 | 1.76 / 2.17 | 1.58 / 1.27 |
| R Draconis | 0.58 / 0.61 | 0.58 / 0.71 | 0.74 / 1.05 | 0.45 / 0.46 |

The rescaling divides each method's S/N by its robust width (1.4826 MAD) measured outside
the target mask, separately on faint sky (static sky below 3 sigma), intermediate (3 to 10)
and bright (above 10 sigma) pixels; the classes are defined on the chromatic template for
all methods.

Robustness of the matched-rate sensitivity (f50 of the gated pair divided by f50 of the
chromatic template; above 1 the template reaches fainter):

| Field | Blank sky, 0.2 per frame | 0.5 per frame | 1.0 per frame | Next to a star, 0.2 per frame | 0.5 per frame | 1.0 per frame |
|---|---|---|---|---|---|---|
| Barnard's Star | 1.41 | 1.78 | 1.97 | not reached by either | 1.57 | 1.71 |
| Epsilon Indi B | 1.09 | 1.41 | 1.35 | 0.82 | 1.08 | 1.06 |
| RW Aurigae | 1.21 | 1.94 | 1.84 | not reached by either | 1.60 | 1.55 |
| WISE 0855-0714 | 1.07 | 1.21 | 1.49 | not reached by either | 1.15 | 1.36 |
| R Draconis | not reached by either | 1.53 | 1.62 | not reached by either | not reached by either | template only (2325 microJy) |

### 2.2 What it does not show (limits we measured)

* **Gating costs few frames.** 96 to 99% of frames find a partner within half a bandwidth,
  because the survey revisits at nearly repeating wavelengths. The advantage of the template
  is depth and sensitivity at a matched false-alarm rate, not rescued frames.
* **Pixel sampling, not colour, is the largest noise term.** SPHEREx pixels (6.15 arcsec)
  under-sample the image: the peak pixel of a bright star scatters by 23 to 27% from frame
  to frame at fixed wavelength. This is why pair differences flood with false detections
  under a purely statistical noise model, and why the template carries an empirical
  model-error map. Frame registration is not the main problem (0.16 arcsec rms on 25 stars
  within a pass), but it is not perfect either: between passes we measure offsets of up to
  0.1 pixel (0.6 arcsec, Barnard's field), which the motion fit removes and the differencing
  does not.
* **For a star that moves by one or two pixels, a pair shows the two-lobe signature better
  than the template.** Both lobes exceed 5 sigma in 69% of Barnard frames for the gated pair
  against 17% for the template, because a template built from two other passes averages
  two old positions. For such stars the tool defaults to blinking and subtracting per-pass
  stacks.
* **R Draconis is not a clean test.** The saturated Mira fills the cutout; depth is three to
  four times worse in every method and the template has slightly more false detections
  (0.61 against 0.58 per frame).
* **The template does not pass its own known-target test.** In the ledger's "known target
  recovered" row it scores "no" for Barnard's Star: its detection sits next to the saturated
  core and is classed an artifact in 85% of frames. RW Aurigae's change exceeds 5 sigma in
  39% of template frames against 86% for the gated pair, and no method classes it "variable".
* **The false-detection tail is not Gaussian noise.** It is dominated by artefacts of
  saturated stars that reach beyond the 14-pixel mask and by transients the archive did not
  flag (single residuals reach S/N of several hundred to more than a thousand; 5 to 16% of
  the strongest carry the TRANSIENT flag). This is why the thresholds that give 0.5 false
  detections per frame are about 8 to 12 sigma in the four ordinary fields (14 to 54 sigma
  at 0.2 per frame), and why f50 is several times the 5-sigma point-source depth.
* Injected sources are achromatic Gaussian point sources; the 14-pixel exclusion radius and
  the 0.5-per-frame matched rate are our choices and are recorded in the ledger files,
  which now also hold the rates 0.2 and 1.0. With exclusion radii of 8 and 20 pixels the
  ranking at |S/N| > 5 is unchanged in the four ordinary fields and flips in R Draconis.

## 3. The five challenge targets

| Target | What we measured | Reference |
|---|---|---|
| Barnard's Star | proper motion 10.2 +- 0.5 arcsec/yr (scatter between the six detectors; the formal error of the weighted fit is 0.26) at position angle 356.3 +- 1.5 deg (shift of 1.65 pixels over 3 passes, from the wings of a saturated star; fit with a free annual term, so three passes leave one degree of freedom) | 10.36 arcsec/yr at 355.6 deg (Gaia DR3) |
| Epsilon Indi B | 4.64 +- 0.09 arcsec/yr at 122.6 +- 1.3 deg (shift of 1.02 pixels over 4 passes) | 4.70 arcsec/yr at 122.7 deg |
| WISE 0855-0714 | a moving source with a combined statistic of 6.6 in pass-difference stacks of detectors 5 and 6 only, stacked along the catalogue track (not a Gaussian sigma: random tracks in the same maps scatter by 0.6; 1 of 2,000 reaches the value found at the predicted position and 0 of 200 reach the maximum of the 8-pixel search; joint-fit flux 395 +- 69 microJy), 1.5 arcsec from the predicted position; 7.81 +- 1.57 arcsec/yr at 278.2 +- 4.3 deg with the catalogue parallax assumed (an independent centroid fit gives 6.2 +- 1.1); absent in detectors 1-4 | 8.15 arcsec/yr at 274.8 deg |
| RW Aurigae | in September 2025, compared with September 2026, the star was 0.37 +- 0.14 mag fainter at 0.75-1.1 micron and 0.76 +- 0.03 mag brighter at 4.4-5.0 micron; a control star shows no change (0.00 +- 0.02 mag) | irregular T Tauri variable |
| R Draconis | periodic change significant in 22 of 43 wavelength bins (amplitudes fitted at the catalogue period), median peak-to-peak 1.18 mag (2-3 mag near 0.8 micron, about 1 mag at 4.5 micron); free period 250 d (244 to 258 d, 95%, bootstrap over 40 wavelength bins; each bin covers 1.2 to 1.8 cycles, the whole data set 2.1) | Mira, catalogued period about 246 d (AAVSO VSX: 246.1 d) |

Caveats that belong with these numbers:

* Sub-pixel centroids on under-sampled data scatter by 0.04 pixel (0.24 arcsec) between
  detectors for an unsaturated star and 0.11 pixel on the wings of a saturated one.
* Parallax is **not** measured reliably: the fitted annual term for Barnard's Star is about
  three times its true parallax. SPHEREx always looks about 90 degrees from the Sun, so any
  Sun-synchronous systematic imitates parallax.
* The WISE 0855 statistic (6.6; 6.5 at the catalogue position without any search) is not a
  Gaussian sigma, because the three pass differences are not independent. We calibrated it
  on random tracks in the same maps (the real pass-to-pass displacements, rotated by a
  random angle and placed at a random zero point): at a fixed position they scatter by 0.6
  (robust width 0.45) and 1 of 2,000 reaches 6.5; with the full 8-pixel zero-point search
  0 of 200 reach 6.6 (largest 3.4). Following the track in reverse order gives -4.1, a
  source standing still at the mean position gives -0.2, and detectors 1-4 give 0.2 on the
  track (2.7 at best in their own search). A static neighbour of 277 microJy lies inside
  the same beam at shorter wavelengths.
* The challenge coordinates of WISE 0855 are its 2010 WISE position; the source is now 2
  arcmin further west, where we find it.
* The R Draconis amplitudes were fitted with the period fixed at 245.6 d, close to the
  catalogue value. The formal range of the free period (248 to 252 d) is too narrow; a
  bootstrap over the 40 wavelength bins gives 246 to 254 d (68%) and 244 to 258 d (95%).
  No single wavelength bin covers the 2.1 cycles of the whole data set: each spans 1.2 to
  1.8 cycles with 6 to 12 points, single-bin periods scatter from about 160 to 340 d, and
  the sinusoid is a poor formal fit (a parabola in time fits better in 15 of 40 bins).
  The 43 bins come from detectors 1, 3, 4 and 6 (10 of 15, 3 of 10, 2 of 11 and 7 of 7
  significant); no detector is excluded.
* Barnard's Star sits a constant 1.35 arcsec north of its catalogue track; we have not
  explained this offset (wing bias or coordinate zero point).
* The epoch of the WISE 0855 catalogue position (2010.4) was set after the data showed the
  source 32 arcsec from the first prediction; it agrees with the date of the WISE survey.
* R Draconis and Barnard's Star saturate SPHEREx; their fluxes come from the wings and are
  relative, not absolute.

## 4. Known solar-system objects as ground truth

Two extra fields contain a catalogued body whose position at every exposure is predicted by
JPL Horizons as seen from the SPHEREx spacecraft. The fields were found by an object-first
search of the archive footprints, which returned the same 136 images as IRSA's own moving
object tool for (52) Europa.

| Field | Frames | Object present in | Chromatic-difference detections labelled with the object | Median S/N in the chromatic difference | Measured minus predicted position |
|---|---|---|---|---|---|
| (52) Europa crossing, 20-21 Aug 2025 (V 12.2, detectors 3 and 6) | 111 | 24 | 24 of 24 (S/N 111 to 236), matched to the ephemeris within 0.5 pixel; without the ephemeris the classifier calls 21 of the 24 "mover" | 186 | -0.05 +- 0.04, 0.00 +- 0.07 pixel |
| Pluto, 4-10 Oct 2025 (V 14.5, detector 2) | 46 | 18 | 18 of 18 (S/N 14 to 57), matched to the ephemeris; without the ephemeris the classifier calls 8 "mover", 8 "variable", 1 "star-residual" and 1 "artifact" | 50 | +0.03 +- 0.10, +0.01 +- 0.04 pixel |

* What the pipeline does blind, with no ephemeris (re-run on the cached fields): for
  (52) Europa the classifier calls 21 of the 24 detections "mover" and the linker joins
  them into one track of 21 detections at 28.3 arcsec per hour, position angle 89.2 deg
  (ephemeris: 28.5 at 89.1). The other 3 are called "artifact": 2 lie next to missing
  pixels and 1 has a TRANSIENT flag within one pixel. Before a fix made during our own
  review the classifier called only 2 of the 24 "mover" (a source this bright covers more
  than its former fixed limit of 30 pixels, and 8 detections lay on a faint star), so the
  earlier "24 of 24" rested on the ephemeris label.
* In the direct image Pluto is at 83 to 176 sigma in every one of its 18 frames. Blind, the
  classifier calls 8 of its 18 detections "mover" and 8 "variable" (it moves 0.7 arcsec per
  hour, so over consecutive frames it stays on the same pixels and looks like a source
  that brightened), and the linker, which
  needs at least 1 arcsec per hour, reports no track: Pluto is named only by the ephemeris.
* The classifier and the linker share a speed limit of about 170 arcsec per hour (one pixel
  between consecutive exposures 2.15 minutes apart): anything faster is rejected as a
  cosmic ray by the same-visit check.
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
  an estimated one to two minutes on a slow one).
* 130 Python tests and 55 TypeScript tests, all offline (2 more Python tests call live services and are skipped unless `PARALLAX_NETWORK=1` is set).
