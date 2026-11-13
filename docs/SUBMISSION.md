# Submission text for the NASA Space Apps project form

Ready-to-paste text for the eight fields of the 2026 project form, in the order of the form.
The form opens on Saturday 14 November 2026 at 09:00 and closes on Sunday 15 November 2026
at 23:59, Beirut time. Only the last saved submission is judged, so submit early and
resubmit.

The Project Submission Guide states no character limits. Check the live form for limits when
it opens; each long field below has a shorter version in case one is enforced.

Everything must be in English. Do not paste anything marked **paste after publishing** until
the link has been opened successfully in a private browser window, logged out.

---

## 1. Project Name

```
ParallaX
```

If the form allows a subtitle or a longer name: `ParallaX: chromatic difference imaging for the SPHEREx sky`

## 2. High-Level Project Summary

About 120 words.

```
ParallaX is a public web tool that plays NASA's SPHEREx infrared images of any patch of sky as a little video, so anyone can spot things that move or change. Type coordinates and the browser fetches the images itself from the public archive; no server is needed. SPHEREx never photographs the same spot in the same colour twice, so blinking or subtracting two dates makes ordinary stars look like false alarms. ParallaX predicts what an unchanging sky would look like at each frame's own colours and subtracts it. On five real fields this goes 3 to 15% deeper than the usual fix and cuts false detections in four of them. We publish the measurements, the limits, and the code to reproduce them. Planet X is the motivation, not a claim.
```

Shorter version (about 60 words):

```
ParallaX plays NASA's SPHEREx infrared images of any patch of sky as a little video, in the browser, so anyone can spot things that move or change. Because SPHEREx sees every revisit in a different colour, it predicts the unchanging sky at each frame's own colours and subtracts it, and it publishes measured, reproducible false-alarm numbers on five real fields.
```

## 3. Link to Project Demo

**Paste after publishing.** This must point to the demo itself: either a video of 30 seconds
or less, or a slide deck of at most 7 slides including the title and introduction slides.
Exceeding either limit makes the project ineligible for Global Judging.

```
[PASTE AFTER PUBLISHING: public link to the 30-second demo video or the 7-slide deck]
```

* It must open without a password, permission request or sign-in. Test it in a private
  window.
* If it is a video: 30.0 seconds or less as shown by the host (render at about 29 seconds),
  English narration or English subtitles.
* If it is a deck: team name, member names, the challenge name, a picture of the project,
  the user experience, and how NASA data makes it possible.
* A file in the public GitHub repository or a public video link both qualify.

## 4. Link to Final Project

**Paste after publishing.** This should point to the working tool. Recommended: the live
site, with the repository linked from it and from the description below.

```
[PASTE AFTER PUBLISHING: https://abed-r-j.github.io/parallax-spherex/]
```

Only one link fits in this field. If the site is not live in time, use the repository
instead:

```
[PASTE AFTER PUBLISHING: https://github.com/abed-r-j/parallax-spherex]
```

Neither address is published at the time of writing. Open the link in a private window
before pasting it.

## 5. Detailed Project Description

About 500 words.

```
WHAT IT DOES
ParallaX shows how the SPHEREx infrared sky changes over time. You enter Right Ascension and declination, or pick one of the five challenge targets, and it plays the SPHEREx images of that patch as a little video. You can blink survey passes six months apart, step through every exposure, add or subtract any images, click any pixel to get its spectrum on the fly, and overlay Gaia DR3 stars, WISE sources, contamination flags and known asteroids. Every view is a link that can be shared or embedded.

THE PROBLEM WE FOUND
SPHEREx never photographs the same spot in the same colour twice. Each exposure passes through a filter whose wavelength changes across the detector, so every pixel has its own wavelength and every revisit lands on another one. Blink or subtract two dates naively and ordinary stars light up as false alarms. The pixels are also coarse (6.15 arcsec), and the challenge's own test stars move by only one to two pixels.

HOW IT WORKS
1. Any coordinates, no server. The site ships a 45.6 MB index of all 1,628,230 public SPHEREx Level-2 images. The browser looks up which images cover your position and reads only the pixels it needs from the public archive bucket: 55 images of M51 in 10 to 12 seconds on a fast connection.
2. A chromatic template. For every frame, a Python pipeline predicts what a static sky would look like at that frame's own per-pixel wavelength, from the spectrum each pixel showed in the other survey passes, and subtracts it. What is left is change.
3. A published three-way ledger. The same real frames are differenced three ways (naive pair, wavelength-matched pair, chromatic template), with artificial moving sources injected and searched for again.

RESULTS, WITH THEIR LIMITS
In Barnard's Star field, false detections per frame are 4.64 (naive), 2.44 (matched pair) and 0.99 (ours); at an equal false-alarm rate we find moving sources down to 563 microJy against 1025. Across five fields the template is 3 to 15% deeper and has fewer false detections in four. We measured Barnard's Star at 10.21 +- 0.26 arcsec/yr (Gaia: 10.36) and Epsilon Indi B at 4.64 +- 0.09 (catalogue: 4.70), recovered the cold brown dwarf WISE 0855 only in stacks (S/N 6.6, moderately optimistic), and saw RW Aurigae and R Draconis vary. We also publish what did not work: for stars that shift one or two pixels a simple blink of per-pass stacks shows the motion better than our template; parallax is not measured reliably; bright targets saturate; R Draconis is not a clean test. Planet X is the motivation, not a claim: a real Planet Nine would be too faint for single SPHEREx frames.

BENEFITS AND GOALS
Anyone with a browser can explore SPHEREx in time, including classrooms and citizen scientists. Researchers get a quick look at any position and a reproducible false-alarm benchmark. The site is static, so it costs nothing to run, and updating to a new data release is three commands.

TOOLS
Python 3 (NumPy, SciPy, Astropy, HTTPX, FastAPI, Typer), TypeScript, React, Vite, Vitest, pytest, GitHub Actions and GitHub Pages. Hardware: one laptop. 120 Python and 55 TypeScript tests. Open source, Apache-2.0. Development began on 12-13 November 2026, before the on-site event, after the local organizers allowed early preparation. Not affiliated with or endorsed by NASA.
```

Shorter version (about 150 words), if a limit applies:

```
ParallaX plays SPHEREx images of any patch of sky as a little video. Enter RA and Dec; the browser finds the images in a 45.6 MB index of all 1,628,230 public Level-2 images and reads only the pixels it needs from the public archive, with no server. You can blink survey passes, add or subtract images, get spectra on the fly, overlay Gaia DR3, WISE and known asteroids, and share or embed any view by URL. Because SPHEREx sees every revisit at a different wavelength, a Python pipeline predicts the static sky at each frame's own per-pixel wavelength and subtracts it. On five real fields this is 3 to 15% deeper than wavelength-matched pairs and has fewer false detections in four (Barnard's field: 0.99 against 2.44 per frame). All five challenge targets are measured against catalogues, and the limits are published. Python, TypeScript, React. Apache-2.0. Planet X is the motivation, not a claim.
```

## 6. Use of Super Intelligence (SI)

```
Yes. We used one SI tool: Claude, a large language model by Anthropic, as a coding and writing assistant.

How we used it: under our direction it wrote most of the Python pipeline, the web app and their tests, gathered and checked background research (the challenge text, the rules, the archive interfaces, the literature), and drafted the documentation, which we reviewed. We defined the problem and the approach (correct for SPHEREx's per-visit wavelength change with a per-pixel template, and test it with a three-way comparison), directed the work, decided what to keep, and ran and reviewed everything.

What SI was not used for: no SI-generated images, video, audio, voices or faces appear anywhere in the project. Every figure is a plot made by our code from real SPHEREx data, or a screenshot of the running app. All results are computed by the project's own code from real SPHEREx data; the tool itself contains no machine-learning or language model.

How it is marked: every source file written with the assistant carries an "SI disclosure" line in its header; the README, the app's About page and docs/SI_DISCLOSURE.md in the repository state the same. Outputs of ParallaX are its own and are not NASA products.
```

## 7. NASA Data

```
1. SPHEREx Level-2 Spectral Images, from the NASA/IPAC Infrared Science Archive (IRSA): Data Release 1 (doi:10.26131/IRSA678) and Quick Release 3 (doi:10.26131/IRSA662), retrieved 13 November 2026. This is the core of the project. We use the calibrated images with their per-pixel wavelength, variance and flag information: 1,991 frames in the five challenge fields (Barnard's Star, Epsilon Indi B, WISE 0855-0714, RW Aurigae, R Draconis), read as small cutouts by HTTP range request. Every picture, spectrum and measurement in the tool comes from these images. https://irsa.ipac.caltech.edu/Missions/spherex.html

2. IRSA services: the Table Access Protocol service (the SPHEREx image catalogue, from which we built a static index of all 1,628,230 public Level-2 images), and the public SPHEREx bucket hosted on Amazon Web Services (nasa-irsa-spherex), from which the web page reads pixels directly for any coordinates. IRSA's Moving Object Search Tool was used as an independent check.

3. SPHEREx tutorial notebooks by IRSA, for the access patterns. https://caltech-ipac.github.io/irsa-tutorials/spherex/

4. CatWISE2020 catalogue (from NASA's WISE and NEOWISE missions), served by IRSA: infrared sources overlaid on the images.

5. NASA/JPL Solar System Dynamics, Horizons System (https://ssd.jpl.nasa.gov), data retrieved 13 November 2026: positions of known solar-system objects as seen from the SPHEREx spacecraft at each exposure time, used to label known asteroids and to check our detections.

6. WiseView (http://byw.tools/wiseview), listed in the challenge resources, is our stated inspiration for a browser blink tool; none of its code is used.

Acknowledgements: This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration. This research has made use of the NASA/IPAC Infrared Science Archive, which is funded by the National Aeronautics and Space Administration and operated by the California Institute of Technology.
```

## 8. Space Agency Partner Data and Other References

```
SPACE AGENCY PARTNER DATA
- European Space Agency (ESA), Gaia Data Release 3 (Gaia mission, processed by the Gaia Data Processing and Analysis Consortium): positions, proper motions and parallaxes of stars. Used for the star overlay (each star moved to the date of the frame) and as the reference position and proper motion of Barnard's Star. Queried at the ESA Gaia archive, with IRSA's copy as fallback.

OTHER DATA AND SERVICES
- SkyBoT, IMCCE, Observatoire de Paris (Berthier et al. 2006, ASP Conf. Ser. 351, 367): known solar-system objects in each field.

SOFTWARE (all open source; none copied into our code, all installed as dependencies)
- Python: NumPy (BSD-3-Clause), SciPy (BSD-3-Clause), Astropy (BSD-3-Clause), HTTPX (BSD-3-Clause), Pillow (MIT-CMU), FastAPI (MIT), Uvicorn (BSD-3-Clause), Typer (MIT), sep (LGPL-3.0-or-later; declared, not imported), Matplotlib (Matplotlib licence, for figures), pytest (MIT), Ruff (MIT), Hatchling (MIT), uv (Apache-2.0 OR MIT).
- Web: React and React DOM (MIT), Vite (MIT), TypeScript (Apache-2.0), Vitest (MIT), ESLint and typescript-eslint (MIT), Playwright core (Apache-2.0, drives Chrome for screenshots).
- Fonts: IBM Plex Sans and IBM Plex Mono (SIL Open Font License 1.1), bundled through the @fontsource packages.
- Hosting and automation: GitHub Pages and GitHub Actions.
- SI tool: Claude, by Anthropic (see the Use of SI field).
- Full list with versions and licences: THIRD_PARTY_LICENSES.md in the repository.

IMAGES
- All images in the project are screenshots of our app or plots made by our code from SPHEREx data. No third-party images, logos, music or video are used.

PAPERS
- Bock, J. J., et al. 2026, "The SPHEREx Satellite Mission", ApJ 999, 139, doi:10.3847/1538-4357/ae2be2.
- Crill, B. P., et al. 2025, "The SPHEREx Sky Simulator", ApJS 281, 10, doi:10.3847/1538-4365/ae04cc.
- Kuchner, M. J., et al. 2017, "The First Brown Dwarf Discovered by the Backyard Worlds: Planet 9 Citizen Science Project", ApJL, doi:10.3847/2041-8213/aa7200.
- Meisner, A. M., et al. 2018, "A 3pi Search for Planet Nine at 3.4 micron with WISE and NEOWISE", AJ, doi:10.3847/1538-3881/aaae70.
- Brown, M. E. & Batygin, K. 2021, "The Orbit of Planet Nine", AJ, doi:10.3847/1538-3881/ac2056.
- Fortney, J. J., et al. 2016, "The Hunt for Planet Nine: Atmosphere, Spectra, Evolution, and Detectability", ApJL, doi:10.3847/2041-8205/824/2/L25.
- Alard, C. & Lupton, R. H. 1998, "A Method for Optimal Image Subtraction", ApJ 503, 325, doi:10.1086/305984.
- Zackay, B., Ofek, E. O. & Gal-Yam, A. 2016, "Proper Image Subtraction", ApJ 830, 27, doi:10.3847/0004-637X/830/1/27.
- Ivezic, Z., et al. 2022, "Simulated SPHEREx spectra of asteroids", Icarus 371, 114696, doi:10.1016/j.icarus.2021.114696.
- Lisse, C. M., et al. 2025, "SPHEREx Pre-Perihelion Mapping of H2O, CO2, and CO in Interstellar Object 3I/ATLAS", arXiv:2512.07318.

Not affiliated with or endorsed by NASA.
```

---

## The two checkboxes at submission

The form asks you to tick both. Read them; you are affirming them personally.

> "I have read and understand the project submission requirements as contained in the NASA
> Space Apps Project Submission Guide, and I agree to the Participant Terms and Conditions and
> Privacy Policy."

To affirm this, both team members should actually have read the Project Submission Guide and
the Participant Terms and Conditions.

> "I confirm that the submitted project represents my team's original work and that all
> external resources including code, text and images (even if they are open source or freely
> available) used in the project are listed in the References field of the project submission
> form. In creating our solution, my team has not used any copyrighted materials (i.e., music,
> images, text, etc.) that we don't have permission to use."

To affirm this, the team must be able to say:

* the project is the team's own work, made for this challenge, with the SI assistance
  disclosed in field 6;
* field 8 lists every dataset, library, font, service, paper and tool (compare it once more
  with `THIRD_PARTY_LICENSES.md`);
* the demo video, the two-minute video and the slides contain no music, footage, images or
  logos that the team does not have the right to use;
* the work that was done on 12-13 November, before the on-site event, was allowed by the
  local organizers. The Participant FAQ says teams may not begin before the hackathon; keep
  the organizers' permission in writing (a screenshot of the message).

## Pre-submission checklist

**Eligibility and timing**

- [ ] Both members are registered for the 2026 challenge and for the Beirut local event, are
      not on the waiting list, and appear on the team's Members tab.
- [ ] The team works on one challenge only: "Planet X and SPHEREx".
- [ ] "Submit for Judging" is clicked before Sunday 15 November, 23:59 Beirut time. Submit
      early and resubmit; only the last saved version is judged.
- [ ] Local judging deadlines are confirmed with the Local Lead; they may be earlier.
- [ ] The live form has been checked for character limits.

**Form**

- [ ] All eight fields are filled, in English.
- [ ] Both checkboxes are ticked, and the team can affirm them (see above).

**Demo link**

- [ ] The video is 30.0 seconds or less as shown by the host, or the deck has 7 slides or
      fewer including title and introduction. Over the limit means not eligible for Global
      Judging.
- [ ] English narration or English subtitles; slides in English.
- [ ] A deck shows the team name, the members' names, the challenge name, a picture of the
      project, the user experience, and how NASA data makes it possible.
- [ ] The link opens in a private window with no password, permission or sign-in.
- [ ] Nobody under 18 appears or is heard. Both members agree to appear.
- [ ] No copyrighted music or footage.

**Final project link**

- [ ] The site and the repository are public and open without sign-in.
- [ ] The repository has `LICENSE` (Apache-2.0), `THIRD_PARTY_LICENSES.md`, `NOTICE`.
- [ ] No personal data anywhere in the repository, site, slides or videos (no e-mail
      addresses, phone numbers, addresses, birth dates, identity documents, CVs).
- [ ] Nothing promotes a commercial product or service.
- [ ] Optional: request a FortiGuard web-filter classification for the new site address
      (company name "N/A"), to reduce the chance that a judge's network blocks it.

**SI disclosure**

- [ ] Field 6 is filled as above.
- [ ] The idea is presented as the team's own.
- [ ] There is no SI-generated image, video or audio. If one is ever added, it carries a
      visible "SI-generated" mark.
- [ ] No NASA logos, flags or mission identifiers in any generated content.
- [ ] Nothing the tool outputs is described as "according to NASA".

**NASA branding and credits**

- [ ] No NASA insignia, logotype or seal, no JPL, Caltech or IPAC logo, no mission patch, no
      NASA-style lettering, anywhere (app, slides, videos, documents, repository).
- [ ] The Space Apps logo is used only if the Local Lead confirms it is allowed.
- [ ] "Not affiliated with or endorsed by NASA" appears in the app footer and the README.
- [ ] The SPHEREx and IRSA acknowledgement sentences appear verbatim in the app's About page,
      the README, the report and the slide or video credits, with the DOIs 10.26131/IRSA678
      and 10.26131/IRSA662.
- [ ] JPL Horizons is credited as "NASA/JPL Solar System Dynamics. Data retrieved on 13
      November 2026. Horizons System. https://ssd.jpl.nasa.gov".

**Timeline honesty**

- [ ] Written confirmation from the Local Lead that early preparation was allowed is saved.
- [ ] The README states when development began. No commit is back-dated.

**Beirut local requirements**

- [ ] The two-minute judging video covers: data, software, methods and tools; a
      demonstration; what is distinctive; the process with challenges and limitations; why
      this approach.
- [ ] The demo, the two-minute video, the research and sources, team details, problem,
      solution, impact and references are posted in the team's Slack channel
      (see `SLACK_POSTS.md`).
- [ ] Identification and emergency-contact details are sent privately to the organizers,
      never posted in the channel.
