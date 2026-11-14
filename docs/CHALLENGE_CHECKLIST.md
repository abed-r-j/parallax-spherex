# Challenge checklist: "Planet X and SPHEREx"

An audit of ParallaX against the official challenge text (details and resources tabs as
published on 13 November 2026). Items A1 to A12 are what the Objectives require; B1 to B11
are the optional "Potential Considerations"; C1 to C6 come from the Resources tab. Status is
one of **Met**, **Partial** or **Not used**, and anything short of fully met says why.

SI disclosure: drafted with the help of an SI coding assistant (Claude, by Anthropic), checked by the team.

State of the audit: 14 November 2026. The site and the repository are public at
<https://abed-r-j.github.io/parallax-spherex/> and
<https://github.com/abed-r-j/parallax-spherex>.

## Summary

| Group | Met | Partial | Open |
|---|---|---|---|
| A. Mandatory (12) | 12 | 0 | 0 |
| B. Optional (11) | 10 | 1 (B11) | 0 |
| C. Resources (6) | 4 | 1 (C6) | 0; C5 not used |

## A. Mandatory

| # | Requirement | Status | Where it is satisfied | Evidence |
|---|---|---|---|---|
| A1 | It is a web tool | Met | `web/`: static Vite + React + TypeScript site, built to `web/dist` | `npm run build` passes; 55 unit tests; screenshots in `docs/img/` |
| A2 | It is public-facing | Met | Live site <https://abed-r-j.github.io/parallax-spherex/>, served by GitHub Pages from the `gh-pages` branch (the contents of `web/dist`, published with `web/scripts/publish_site.ps1`); source at <https://github.com/abed-r-j/parallax-spherex>. The site needs no account and no server of ours | Published on 14 November 2026. Worth re-checking in a private browser window, signed out, before submitting |
| A3 | Displays images of the sky from SPHEREx | Met | Real Level-2 spectral images, DR1 (doi:10.26131/IRSA678) and QR3 (doi:10.26131/IRSA662), from NASA/IPAC IRSA | 1,991 frames in five packs under `web/public/data/`; live path reads the public archive bucket directly; no synthetic imagery in the app |
| A4 | Easy for anyone to quickly see how the sky changes over time | Met | Home page with one-click fields; blink player; plain-language text under every view; "How it works" page; [USER_GUIDE.md](USER_GUIDE.md) | Precomputed fields open from 10 to 18 MB of local files; a live field of 55 images arrives in 10 to 12 s on a fast connection (one to two minutes on a slow one) |
| A5 | Users enter coordinates as Right Ascension and declination | Met | Search box on every page (`web/src/lib/coords.ts`); also `?ra=&dec=` in the URL | Decimal degrees and sexagesimal both parse; headless-browser check of four typed strings |
| A6 | A series of images of that patch "like a little video" | Met | Player: play, pause, step, speed, loop; sequence by survey pass or every frame in time order (`web/src/components/Player.tsx`, `Viewer.tsx`) | `docs/img/pass-blink.png`; keyboard checks (Space, arrows) pass |
| A7 | Easy to spot moving objects | Met | Per-pass stack blink with 4x smooth display; Subtract; chromatic difference; catalogue-position marker; per-pass measured positions; known-object labels | `docs/img/subtract.png` shows the two-lobe signature of Barnard's Star; `docs/img/europa52.png` and `docs/img/pluto.png` show an asteroid and Pluto under their predicted positions (fields `europa52`, `pluto`). Limit stated in the app: the test stars move only 1 to 2 pixels |
| A8 | Tested on Barnard's Star | Met | Field `barnard`, 357 frames, 3 passes | Proper motion 10.2 +- 0.5 arcsec/yr (scatter between detectors) at 356.3 +- 1.5 deg against 10.36 at 355.6 (Gaia DR3). Core saturated in 99% of frames; measured from the wings, with a free annual term (one degree of freedom) |
| A9 | Tested on Epsilon Indi B | Met | Field `epsindi`, 454 frames, 4 passes | 4.64 +- 0.09 arcsec/yr at 122.6 +- 1.3 deg against 4.70 at 122.7 |
| A10 | Tested on WISE 0855 at RA 08h55m10.831s, Dec -7d14m42.53s; accepts that notation | Met | Field `wise0855`, 258 frames, 3 passes, 8.3 arcmin wide so that it holds both the 2010 challenge position and today's position 2 arcmin west | The exact string `08h55m10.831s -7d14m42.53s` parses to 133.7951292, -7.2451472 and opens the field. Invisible in single frames; moving source with a combined statistic of 6.6 in pass-difference stacks of detectors 5 and 6 along the catalogue track (not a Gaussian sigma; calibrated on random tracks, see RESULTS.md) |
| A11 | Tested on variable star RW Aurigae | Met | Field `rwaur`, 332 frames, 3 passes | In Sep 2025, compared with Sep 2026: 0.37 +- 0.14 mag fainter at 0.75-1.1 micron and 0.76 +- 0.03 mag brighter at 4.4-5.0 micron; control star shows no change (0.00 +- 0.02 mag). Core saturated in 39% of frames |
| A12 | Tested on variable star R Draconis | Met | Field `rdra`, 590 of 2,493 available images | Periodic change significant in 22 of 43 wavelength bins, median peak-to-peak 1.18 mag; free period 250 d (244 to 258 d, 95%, bootstrap; each bin spans 1.2 to 1.8 cycles) against a catalogued period of about 246 d. Saturated in 97% of frames: relative wing photometry only |

## B. Optional considerations

| # | Consideration | Status | Where it is satisfied | Evidence |
|---|---|---|---|---|
| B1 | Easy to update with the latest data releases | Met | `parallax fetch` (incremental), `parallax publish`, `pipeline/scripts/build_sky_index.py` (fetches only missing days), `web/scripts/publish_site.ps1 -Push` to redeploy | Index covers both DR1 and QR3 collections, 1,628,230 images; the update path is documented in the README. Not yet exercised on a release newer than 13 Nov 2026 |
| B2 | Creative display of the 102 bands | Met | Time-against-wavelength map of every frame; per-pixel wavelength read-out; wavelength window; chromatic template; wavelength-mismatch tint | `docs/img/three-way.png`, `docs/img/naive-mismatch.png` |
| B3 | Add the data of each of the six detector arrays separately | Met | `stack` section of every pack: per survey pass, per detector, inverse-variance mean; detector picker; Add mode | Default view of motion fields is the per-pass, per-detector stack blink |
| B4 | Generate spectra on the fly ("extra kudos") | Met | Spectrum panel: click a pixel, aperture 1, 3 x 3 or 5 x 5 pixels, light curve in a wavelength window, CSV download (`web/src/lib/photometry.ts`) | `docs/img/spectrum.png`; CSV check `parallax_barnard_x15_y45_spectrum.csv`, 341 lines. Works on live fields too. No aperture correction; saturated cores have no data |
| B5 | Option to add images taken at different times | Met | Add mode: any frame, or all frames of a pass and/or detector | In the app (key A) |
| B6 | Option to subtract images taken at different times | Met | Subtract mode (A minus B, each a frame or a group); plus three differencing methods per frame | `docs/img/subtract.png` |
| B7 | User-chosen field of view | Met | Field-of-view picker in the viewer and `fov=` in the URL; live fields in 3, 6 or 9 arcmin with the download size and time shown before fetching; engine fields up to 12 arcmin | `docs/img/live-offer.png`. Limit: precomputed packs are 6.25 or 8.3 arcmin across; the picker zooms inside them |
| B8 | Overlay data from other telescopes (Gaia, WISE) | Met | Gaia DR3 stars moved to the frame date; CatWISE2020 sources; known solar-system objects (SkyBoT, JPL Horizons) | `docs/img/overlays.png`. Limits: overlays exist only in pipeline packs, not in live fields. The WISE overlay is present in all seven packs; around R Draconis, where CatWISE2020 has a hole, it comes from AllWISE |
| B9 | Coordinates in the URL; embeddable | Met | `web/src/lib/urlstate.ts`: `?ra=&dec=&fov=&det=&mode=&frame=`, `embed=1`; Share button with link and iframe code | URL round-trip tests; a reopened URL restores the same view |
| B10 | Display metadata such as contamination flags | Met | Pixel-flags overlay (no data, suspect, catalogued source, pipeline outlier); Frame panel (date, detector, wavelength, bandwidth, noise, sky removed, archive file) | `docs/img/overlays.png`. Live fields carry only the no-data flag |
| B11 | Consider Astropy and Aladin | **Partial** | Astropy is used throughout the pipeline (FITS, WCS, coordinates). Aladin Lite is not used | We chose our own viewer so that the site makes no outside request for precomputed fields and runs offline; CDS services were also unreachable from our network during development |

## C. Resources tab

| # | Expectation | Status | Evidence |
|---|---|---|---|
| C1 | SPHEREx data from IRSA; access patterns from the IRSA tutorials | Met | All images from NASA/IPAC IRSA and its public bucket; catalogue queries through IRSA TAP |
| C2 | WiseView as model or inspiration | Met | Same idea (blink a position in the browser, share by URL); credited as inspiration. No WiseView code is used |
| C3 | If Gaia is used, use Data Release 3 | Met | `gaiadr3.gaia_source` at the ESA archive, IRSA's copy as fallback |
| C4 | Comply with data-use terms of non-U.S.-Government sites | Met | ESA Gaia and IMCCE SkyBoT credited as they request; licences and terms listed in `THIRD_PARTY_LICENSES.md` |
| C5 | Optional partner data: CSA NEOSSat, CADC | Not used | Not needed for this solution |
| C6 | "More resources may be added before the hackathon begins": re-check on 14 Nov | **Partial** | Checked on 13 Nov 2026 (4 NASA and 4 CSA resources). The re-check on 14 Nov is for the team to do |

## What is honestly not met or only partly met

* **The two videos** (30-second demo, 2-minute judging video) are not recorded yet; the
  demo link currently points to the slides.
* **B11**: Aladin is not used.
* **Depth of the "moving object" demonstration**: the three test stars move 1 to 2 pixels.
  The tool shows it best with per-pass stacks and Subtract, not with the chromatic template.
* **Parallax**, named in the challenge background, is not measured reliably.
* **WISE 0855** is recovered only in stacks along its catalogue track, with a statistic calibrated on random tracks.
* **Live fields** lack overlays, flags and the chromatic template.

Not affiliated with or endorsed by NASA.
