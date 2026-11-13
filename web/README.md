# ParallaX web app

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.

Static Vite + React + TypeScript site. It only reads the data packs in `public/data/`
(format: `../docs/DATA_CONTRACT.md`); it makes no outside requests.

    npm install
    npm run dev        # development server
    npm test           # vitest unit tests (decode, WCS, coordinates, stretch, photometry, URL state)
    npm run lint
    npm run build      # -> dist/, relative paths (base './'), works from any static server or GitHub Pages
    node scripts/shots.mjs all [site-dir]   # screenshots to ../data/screens + behaviour checks (needs Chrome)

URL parameters: `field, ra, dec, fov (arcmin), det (1-6), mode (image|chroma|naive|gated|compare|add|sub),
frame, seq (frames|passes), embed=1`, plus display extras `st, cm, lim, sm, lam, ov, pix, ap` and `engine`.

Live engine (optional, for coordinates outside the precomputed fields): base URL in `src/lib/engine.ts`
(default `http://127.0.0.1:8000`, override with `?engine=` or in the page). The engine must send CORS
headers (`Access-Control-Allow-Origin`, and answer the `OPTIONS` preflight of `POST /api/field`).
