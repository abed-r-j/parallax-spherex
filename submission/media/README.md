# ParallaX: pictures for the project page

SI disclosure: this list and the scripts that make the pictures were written with the help of an SI coding assistant (Claude, by Anthropic) and checked by the team.

The Space Apps project page accepts pasted or uploaded pictures (JPG, PNG, GIF, up to 10 MB each) but no videos and no documents, and it is the page the judges read. These eight pictures are made for it.

**None of these pictures is SI-generated.** Files 01 to 06 are screen captures of the running ParallaX web app showing real SPHEREx images. File 07 is a plot (matplotlib) of numbers measured by the project's own code, with two lines of text added below it. File 08 is a real screenshot of a live fetch from the public archive. Nothing was drawn, retouched or edited by hand or by a generative model, so no SI watermark applies.

All numbers in the captions are from `docs/RESULTS.md`. The "Form field" column names the heading of the paste text in `docs/SUBMISSION.md` after which each picture goes; the two files agree.

| File | Size | What it shows | Suggested caption | Form field |
|---|---|---|---|---|
| `01_hero.png` | 1600 x 900, 0.27 MB | The app on the Barnard's Star field: one frame differenced three ways, the time and wavelength map, the spectrum panel | ParallaX on real SPHEREx data: the same frame of Barnard's Star differenced three ways. | High-Level Project Summary, first picture |
| `02_little_video_barnard.gif` | 900 x 762, 3 frames, loops, 0.57 MB | The "little video" the challenge asks for: the three survey passes of Barnard's Star (detector 3 stacks, August 2025 to September 2026) blinked in turn. The dark square is the saturated core of the star | Our little video: Barnard's Star moves north between three SPHEREx passes, 13 months apart. We measure 10.2 +- 0.5 arcsec per year; Gaia gives 10.36. The dark square is the star's saturated core. | High-Level Project Summary, second picture |
| `03_asteroid_europa.gif` | 900 x 762, 24 frames, loops, 3.24 MB | Asteroid (52) Europa crossing a fixed field on 20-21 August 2025 (frames 11 to 34 of 111, detectors 3 and 6, so the picture alternates between about 2 and 4.5 micron), under its known-object label | Asteroid (52) Europa crosses the field at about 28 arcsec per hour. ParallaX labels it from the JPL Horizons prediction as seen from SPHEREx: 24 of 24 detections matched within half a pixel. | Detailed Project Description, after "Moving objects with a known answer" |
| `04_three_way.png` | 1432 x 687, 0.26 MB | Naive pair, wavelength-gated pair and chromatic template for the same frame (Barnard's field, frame 101 of 357, 0.970 micron), on one scale | One frame, three ways to compare it with another date. The naive pair is 9 filter bandwidths off in colour, so the star floods the picture. Gating on wavelength helps. Our chromatic template predicts the frame's own colours from the other passes. | Detailed Project Description, after part 3, "A published three-way comparison" |
| `05_spectrum_on_click.png` | 1600 x 1000, 0.23 MB | The spectrum panel after clicking a star next to RW Aurigae: its brightness from 0.75 to 5 micron in three passes, from 314 frames | Click any star and get its spectrum: every SPHEREx frame is taken at a different infrared wavelength, so 314 frames give 314 points. | Detailed Project Description, after "What exactly does it do?" (the four user steps) |
| `06_time_wavelength.png` | 1384 x 740, 0.09 MB | The time x wavelength map of the Barnard's Star field: one dot per frame, 357 frames in 3 passes | Why blinking SPHEREx is hard: each dot is one image, and no two visits to this patch of sky share a wavelength. | Detailed Project Description, after "The problem we found" (before picture 04) |
| `07_results_chart.png` | 1950 x 1331, 0.12 MB | The faintest injected moving source found half the time, on blank sky, for the three methods in the five challenge fields, at the same false-detection rate (0.5 per frame). Lower is better | Measured on real frames: at the same false-detection rate, the chromatic template finds moving sources 1.2 to 1.9 times fainter than the wavelength-gated pair (Barnard's field: 563 against 1003 microjansky). | Detailed Project Description, after "Sensitivity" under "How we tested it" |
| `08_live_fetch.png` | 1440 x 900, 0.12 MB | A position outside the prepared fields (M51), built in the browser from the public archive, with the app's own banner: "Fetched live ... 55 images, 21 MB in 10 s" | Any position, no server: 55 SPHEREx images of M51 fetched and shown in the browser in about 10 seconds. The chromatic template is not part of a live field. | Detailed Project Description, after part 1, "Any coordinates, no server" |

Honest limits to keep next to these pictures if there is room: in picture 04 the template still leaves a residual on the wings of this saturated star; for a star that moves by one or two pixels a pair shows the two-lobe signature better than the template (`docs/RESULTS.md`, section 2.2); the 10 seconds of picture 08 were on a fast connection.

## Checks made

* Every file was opened and looked at after it was made; for each GIF the individual frames were extracted and looked at (labels readable, nothing cut off, the asteroid under its label).
* Limits: every file is under 10 MB (the largest, the asteroid GIF, is 3.24 MB); both GIFs loop forever and are 900 pixels wide.
* No logo of NASA, JPL or Space Apps appears in any picture. The pictures show no people.

## How to make them again

From the repository root, with `web/dist` built (`npm run build` in `web/`):

```
node submission/make_media.mjs                                 # 01 to 06 and 08 (headless Chrome, ffmpeg)
pipeline/.venv/Scripts/python submission/caption_chart.py      # 07, from presentation/assets/chart_f50.png
```

`make_media.mjs` serves the built site locally and drives it like `presentation/video/capture.mjs` does; the GIFs are encoded with ffmpeg (`palettegen` and `paletteuse`). Picture 08 is a copy of `docs/img/live-m51.png`, taken on 13 November 2026 with the network on.
