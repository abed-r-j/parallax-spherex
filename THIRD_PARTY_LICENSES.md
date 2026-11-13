# Third-party software, fonts and data

ParallaX itself is licensed under Apache-2.0 (see `LICENSE`). This file lists everything it
depends on, with the licence each item declares. Versions are those installed on the
development machine on 14 November 2026; licences were read from each package's own metadata
(`pipeline/.venv`, Python package metadata; `web/node_modules/*/package.json`). Every item is
either under a licence approved by the Open Source Initiative or is public data that is free
to use with attribution. No "non-commercial only" asset is used.

No third-party source code is copied into this repository; dependencies are installed by `uv`
and `npm`. The only third-party files that are redistributed with the built website are the
React runtime (bundled into the JavaScript) and the IBM Plex font files.

## 1. Python pipeline (`pipeline/`)

### Runtime dependencies declared in `pipeline/pyproject.toml`

| Package | Version | Licence | Used for |
|---|---|---|---|
| numpy | 2.5.4 | BSD-3-Clause (bundled parts: 0BSD, MIT, Zlib, CC0-1.0) | arrays |
| scipy | 1.18.1 | BSD-3-Clause | filters, fitting, labelling |
| astropy | 8.0.2 | BSD-3-Clause | FITS files, sky coordinates, WCS |
| sep | 1.4.1 | LGPL-3.0-or-later (parts BSD-3-Clause and MIT) | declared as a dependency; not imported by the current code |
| httpx | 0.28.1 | BSD-3-Clause | HTTP range requests and service queries |
| pillow | 13.0.0 | MIT-CMU | thumbnails |
| fastapi | 0.162.7 | MIT | local engine (`parallax serve`) |
| uvicorn | 0.54.0 | BSD-3-Clause | local engine web server |
| typer | 0.29.1 | MIT | command line |

Note on `sep`: it is the only copyleft item. It is installed as an unmodified, separately
distributed library and is not redistributed in this repository or in the website, which is
compatible with releasing ParallaX under Apache-2.0. Since no module imports it, it can be
dropped from `pyproject.toml` without changing any result.

### Installed with them (transitive runtime dependencies)

| Package | Version | Licence |
|---|---|---|
| annotated-doc | 0.0.6 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.16.0 | MIT |
| astropy-iers-data | 0.2026.11.9.0.35.9 | BSD-3-Clause |
| certifi | 2026.10.23 | MPL-2.0 |
| click | 8.5.1 | BSD-3-Clause |
| colorama | 0.4.6 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| markdown-it-py | 4.3.0 | MIT |
| mdurl | 0.1.2 | MIT |
| opentelemetry-api | 1.45.2 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pydantic | 2.14.3 | MIT |
| pydantic-core | 2.50.4 | MIT |
| pyerfa | 2.0.1.5 | BSD-3-Clause |
| pygments | 2.21.0 | BSD-2-Clause |
| pyyaml | 6.0.3 | MIT |
| rich | 15.0.0 | MIT |
| shellingham | 1.5.4 | ISC |
| starlette | 1.10.0 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.5 | MIT |

### Figures, tests and build (not needed to run the tool)

| Package | Version | Licence | Used for |
|---|---|---|---|
| matplotlib | 3.11.2 | Matplotlib licence (PSF-based, BSD-compatible) | figures |
| contourpy | 1.4.0 | BSD-3-Clause | with matplotlib |
| cycler | 0.12.1 | BSD-3-Clause | with matplotlib |
| fonttools | 4.68.0 | MIT | with matplotlib |
| kiwisolver | 1.5.1 | BSD-3-Clause | with matplotlib |
| pyparsing | 3.3.3 | MIT | with matplotlib |
| python-dateutil | 4.0.0 | BSD-3-Clause (dual with Apache-2.0) | with matplotlib |
| tzdata | 2026.6 | Apache-2.0 | with python-dateutil |
| pytest | 9.2.0 | MIT | tests |
| pytest-cov | 7.1.0 | MIT | test coverage |
| coverage | 7.17.3 | Apache-2.0 | test coverage |
| iniconfig | 2.3.1 | MIT | with pytest |
| pluggy | 1.7.0 | MIT | with pytest |
| ruff | 0.17.5 | MIT | lint |
| hatchling | 1.25 or newer (build time only, not installed in the environment) | MIT | builds the Python package |
| uv | 0.9.16 | Apache-2.0 OR MIT | installer and runner |

## 2. Web app (`web/`)

### Runtime dependencies declared in `web/package.json` (shipped in the site)

| Package | Version | Licence | Used for |
|---|---|---|---|
| react | 19.3.1 | MIT | user interface |
| react-dom | 19.3.1 | MIT | user interface |
| @fontsource/ibm-plex-sans | 5.3.0 | OFL-1.1 | packaging of the IBM Plex Sans font files |
| @fontsource/ibm-plex-mono | 5.3.0 | OFL-1.1 | packaging of the IBM Plex Mono font files |

The site loads nothing from a content-delivery network. It uses no map, chart or astronomy
library: the FITS reader, the coordinate transforms, the charts and the colour maps are the
project's own code.

### Build, test and lint dependencies (not shipped)

| Package | Version | Licence | Used for |
|---|---|---|---|
| vite | 8.3.8 | MIT | build |
| @vitejs/plugin-react | 6.3.0 | MIT | build |
| typescript | 6.0.3 | Apache-2.0 | type checking |
| vitest | 5.1.0 | MIT | tests |
| eslint | 10.14.0 | MIT | lint |
| @eslint/js | 10.0.1 | MIT | lint |
| typescript-eslint | 8.72.2 | MIT | lint |
| eslint-plugin-react-hooks | 7.1.1 | MIT | lint |
| globals | 17.14.0 | MIT | lint |
| playwright-core | 1.65.0 | Apache-2.0 | drives an installed Chrome for screenshots and checks |
| @types/node | 26.6.6 | MIT | types |
| @types/react | 19.3.0 | MIT | types |
| @types/react-dom | 19.3.0 | MIT | types |

`web/node_modules` holds 174 packages in all once the transitive build dependencies are
counted. Their declared licences are: MIT (135), Apache-2.0 (16), ISC (9), BSD-2-Clause (6),
BSD-3-Clause (2), MPL-2.0 (2: lightningcss and its Windows binary), OFL-1.1 (2: the fonts
above), BlueOak-1.0.0 (1: minimatch) and CC-BY-4.0 (1: caniuse-lite, browser-support data by
caniuse.com). None of these transitive packages is shipped in the site. The exact list is
reproducible from `web/package-lock.json`.

### Continuous integration (`.github/workflows/ci.yml`)

GitHub Actions `actions/checkout`, `actions/setup-node`, `actions/upload-pages-artifact`,
`actions/deploy-pages` (MIT) and `astral-sh/setup-uv` (MIT).

## 3. Fonts

| Font | Licence | Source |
|---|---|---|
| IBM Plex Sans (weights 400, 500, 600; Latin subset) | SIL Open Font License 1.1 | Copyright IBM Corp.; files from `@fontsource/ibm-plex-sans` |
| IBM Plex Mono (weight 400; Latin subset) | SIL Open Font License 1.1 | Copyright IBM Corp.; files from `@fontsource/ibm-plex-mono` |

"IBM Plex" is a reserved font name under the OFL; the files are redistributed unmodified.

## 4. Data and services

None of these is copied into the repository as a bulk data set. The published data packs
contain small cutouts and catalogue excerpts derived from them, and the test fixtures contain
a few recorded service responses.

| Source | What ParallaX uses | Terms and required credit |
|---|---|---|
| **SPHEREx Level-2 spectral images**, Data Release 1 (doi:10.26131/IRSA678) and Quick Release 3 (doi:10.26131/IRSA662), NASA/IPAC Infrared Science Archive (IRSA) | the images themselves: cutouts by HTTP range request, the image catalogue through IRSA's TAP service, and the public bucket `nasa-irsa-spherex` on Amazon Web Services for in-browser reads | NASA data, public. Required acknowledgements (verbatim): "This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration." and "This research has made use of the NASA/IPAC Infrared Science Archive, which is funded by the National Aeronautics and Space Administration and operated by the California Institute of Technology." Cite the data DOIs and Bock et al. 2026 (ApJ 999, 139). |
| **Gaia Data Release 3**, European Space Agency (ESA), Gaia Data Processing and Analysis Consortium | positions, proper motions, parallaxes and G magnitudes of stars in each field (ESA Gaia archive TAP; IRSA's copy as fallback) | Free to use with acknowledgement of ESA Gaia and DPAC. |
| **CatWISE2020** (from WISE and NEOWISE data), served by NASA/IPAC IRSA; AllWISE as fallback | infrared source positions, W1 and W2 magnitudes, motions | NASA data, public; IRSA acknowledgement as above. |
| **SkyBoT**, IMCCE, Observatoire de Paris | known solar-system objects in a cone at a given time | No stated restriction; requested credit, as given on the service page: "This research has made use of LTE SkyBoT VO tool", or a citation of Berthier et al. 2006 (bibcode 2006ASPC..351..367B). |
| **JPL Horizons**, NASA/JPL Solar System Dynamics | positions of known objects as seen from the SPHEREx spacecraft at each exposure time | Public domain; no endorsement implied. Credit: "NASA/JPL Solar System Dynamics. Data retrieved on 13 November 2026. Horizons System. https://ssd.jpl.nasa.gov". Queried by the offline pipeline only, one request at a time; the web page never calls JPL. Positions are unmodified apart from conversion to pixel coordinates. |
| **IRSA Moving Object Search Tool (MOST)** | an independent cross-check of which images contain asteroid (52) Europa | NASA/IPAC IRSA service; acknowledgement as above. |

Inspiration, not code or data: WiseView (Caselden et al. 2018) and the Backyard Worlds:
Planet 9 project (Kuchner et al. 2017), named in the challenge resources.

## 5. Tools used to make the project

Git, Node.js and npm, Python, Google Chrome (headless, for screenshots and PDF export), and
an SI coding assistant (Claude, by Anthropic); see `docs/SI_DISCLOSURE.md`.

Not affiliated with or endorsed by NASA.
