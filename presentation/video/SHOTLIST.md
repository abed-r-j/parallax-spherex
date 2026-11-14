# ParallaX: screen footage shot list

SI disclosure: the capture scripts and this list were written with the help of an SI coding assistant (Claude, by Anthropic) and checked by the team. The clips show the real ParallaX web app on real SPHEREx data. They contain no SI-generated imagery.

All clips are silent, 1920x1080, 30 frames per second, H.264 (`.mp4`), and open in Clipchamp. The only thing drawn on top of the app is the white mouse pointer (headless Chrome shows none). Clips may be trimmed, sped up or slowed down freely in the editor.

| Clip | Length | What it shows | Script line it covers |
|---|---|---|---|
| `shot_01_type_coordinates.mp4` | 9.8 s | Home page; the challenge coordinates of WISE 0855-0714 (`08 55 10.83 -07 14 42.5`) are typed; the field opens; six per-pass stacks are stepped | 30 s: "This is ParallaX: fewer false alarms in the infrared sky." 2 min: "Our data is open: SPHEREx images from the NASA/IPAC archive..." |
| `shot_02_blink_barnard.mp4` | 8.8 s | Barnard's Star, detector 3, the three survey passes blinked in the smooth 4x display (the dark square is the saturated core; watch the wings and the cross-hair shift) | 2 min: "Here is Barnard's Star, blinked pass by pass: you can see it move." |
| `shot_03_time_wavelength.mp4` | 10.0 s | 84 frames of the Barnard field stepped in time order: the picture changes colour band and the marker walks across the "When and at what colour" map | 30 s: "SPHEREx never repeats a colour..." 2 min: "But SPHEREx never photographs a spot in the same colour twice..." |
| `shot_04_naive_false_alarms.mp4` | 8.3 s | Naive pair difference, frames 93 to 109: the star lights up or goes dark from frame to frame | 30 s: "...so stars become false alarms." 2 min: "Blink two dates, and stars light up as false alarms." |
| `shot_05_three_way.mp4` | 8.7 s | The same frames differenced three ways side by side (naive, gated, chromatic); it rests for 2 s on frame 101, where the naive panel has a bright halo | 30 s: "From NASA's open data, we predict each frame's own colours, and subtract." 2 min: "Here is one frame differenced three ways..." |
| `shot_06_chromatic.mp4` | 7.1 s | The chromatic difference alone, frames 93 to 109 | 2 min: "So we chose to correct the colour first, and only then compare." |
| `shot_07_click_spectrum.mp4` | 7.1 s | RW Aurigae field: the pointer clicks a neighbouring star and its spectrum (0.75 to 5 micron, three passes) appears | 2 min: "Click any star for its spectrum." |
| `shot_08_subtract_passes.mp4` | 5.0 s | Barnard's Star, pass 3 minus pass 1 (detector 2): the bright and dark lobes of a star that moved | 2 min, optional cut-away under "The hard part was honesty..." |
| `shot_09_ledger.mp4` | 9.1 s | The pointer opens the Ledger tab; the page scrolls to the three-way table and the recovery curves for the Barnard field | 2 min: "What is distinctive: we publish the measurements..." |
| `shot_10_wise0855_blink.mp4` | 7.8 s | WISE 0855-0714, detector 6, the three passes blinked, with the catalogue position marked | spare (questions about the faintest target) |
| `shot_11_live_fetch.mp4` | 26.9 s | LIVE, real network: M51 (`13 29 52.7 +47 11 43`) is typed, one detector is chosen, 55 images (21 MB) are fetched in the browser from the public archive in about 11 s of real time, then frames are stepped | 30 s: "Next: anyone types coordinates and explores the changing sky." 2 min: "A Python pipeline does the science... with no server." |
| `shot_11b_live_fetch_fallback.mp4` | 10.0 s | Fallback for shot 11: three real screenshots of an earlier live fetch of the same position (smaller picture with a border, because they were taken at 1440x900) | same lines as shot 11, only if shot 11 cannot be used |
| `shot_12_asteroid_europa.mp4` | 8.9 s | Asteroid (52) Europa crossing a fixed field on 20-21 August 2025, 24 frames, under its known-object label (JPL Horizons as seen from SPHEREx) | 30 s: alternative picture for "Next: ..." 2 min: "And here an asteroid crosses, right under its predicted label." |
| `shot_13_pluto.mp4` | 11.4 s | Pluto drifting 12 pixels between 4 and 10 October 2025 (18 frames, forwards then backwards), under its label; the other labels are fainter asteroids that are not visible | spare (it pairs well with "Pluto was found by blinking two photographs") |

## How the clips were made and checked

* `capture.mjs` serves a built copy of the web app from a plain static server, drives it in headless Chrome through `playwright-core`, saves a screenshot sequence with a duration for every screenshot, and encodes it with ffmpeg. Playwright's `recordVideo` is not used. `lib.mjs` holds the server, the pointer and the recorder.
* The view is 1600x900 CSS pixels at a device scale of 1.2, which gives 1920x1080 images with readable text.
* `check_clips.py` runs ffprobe on every clip and writes four frames of each to `_check/<clip>.jpg`. Every sheet was looked at: text readable, nothing cut off, pointer where it should be, the asteroid and Pluto under their labels.
* Shot 11 was captured on 14 November 2026 against the live archive (55 images, 21 MB, 10 to 12 s). Its timing is real, not sped up.

## Regenerate

    cd web && npm install && npm run build          # makes web/dist
    cd ../presentation && npm install               # playwright-core, pptxgenjs (Chrome must be installed)
    node video/capture.mjs                          # every clip and the slide screenshots (assets/)
    node video/capture.mjs ../web/dist shot_05,shot_12   # only some clips
    node video/capture.mjs ../web/dist stills       # only the slide screenshots
    node video/make_fallback.mjs                    # shot_11b
    python video/check_clips.py                     # sizes, lengths and the _check sheets
    node video/make_scripts.mjs                     # SCRIPT_30s.md, SCRIPT_2min.md, subs_*.srt
