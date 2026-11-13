# ParallaX web app

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.

Static Vite + React + TypeScript site. It reads the data packs in `public/data/`
(format: `../docs/DATA_CONTRACT.md`) and, for any other position, builds a field live in the
browser from the public SPHEREx archive (see below). No server of its own.

    npm install
    npm run dev        # development server
    npm test           # vitest unit tests (decode, WCS, coordinates, stretch, photometry, URL state)
    npm run lint
    npm run build      # -> dist/, relative paths (base './'), works from any static server or GitHub Pages
    node scripts/shots.mjs all [site-dir]   # screenshots to ../data/screens + behaviour checks (needs Chrome)
    node scripts/live-check.mjs [m51|cosmos|all]   # real live fetches from the archive: screenshots live-*.png,
                                                   # numbers to ../data/live/probe-*.json (needs Chrome and network)

URL parameters: `field, ra, dec, fov (arcmin), det (1-6), mode (image|chroma|naive|gated|compare|add|sub),
frame, seq (frames|passes), embed=1`, plus display extras `st, cm, lim, sm, lam, ov, pix, ap` and `engine`.
A live request is `ra, dec, live=1, size (arcmin: 3, 6 or 9), dets (for example 2,5 or all), max (images, default 360)`;
without `size` / `dets` the view's `fov` / `det` stand in, so `?ra=..&dec=..&fov=3&det=3&live=1` works too.

## Live fields (any coordinates, no server)

For coordinates outside the precomputed fields the page offers to fetch the field live. `src/lib/skyindex.ts`
reads the static sky index in `public/skyindex/` (`../docs/SKY_INDEX.md`) to list the SPHEREx Level-2 images
that contain the position; `src/lib/live.ts` then reads, from each 65 MB file in the public NASA/IPAC IRSA bucket
on AWS (`nasa-irsa-spherex`, CORS + Range), the header (28.8 kB), the detector rows the field needs (one
contiguous range) and, once per detector calibration, the 5.76 kB wavelength table; `fits.ts` and `sip.ts` parse
the header and the TAN-SIP coordinates. Frames are resampled bilinearly onto the pack grid and handed to the
ordinary viewer as a `Pack` while they arrive (at most 5 requests at a time, retries with back-off, Stop button,
finished fields cached in memory for the session).

Differences from a pipeline pack, on purpose, to keep the download small: FLAGS, VARIANCE and ZODI are not
fetched. One robust sky level per frame is removed (clipped median of a detector window about 31 arcmin wide),
the noise is the robust scatter of neighbouring detector pixels, only the no-data flag is set (hot pixels and
cosmic rays are not masked in single frames; the per-pass stacks reject them), and there is no chromatic
template, ledger or search: those need the Python pipeline (the engine).

Live engine (optional, for coordinates outside the precomputed fields): base URL in `src/lib/engine.ts`
(default `http://127.0.0.1:8000`, override with `?engine=` or in the page). The engine must send CORS
headers (`Access-Control-Allow-Origin`, and answer the `OPTIONS` preflight of `POST /api/field`).
