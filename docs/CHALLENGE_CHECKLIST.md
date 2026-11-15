# Challenge checklist: "Planet X and SPHEREx"

An audit of ParallaX against the official challenge text (details and resources tabs as
published on 13 November 2026). Items A1 to A12 are what the Objectives require; B1 to B11
are the optional "Potential Considerations"; C1 to C6 come from the Resources tab. Status is
one of **Met**, **Partial** or **Not used**, and anything short of fully met says why.

SI disclosure: drafted with the help of an SI coding assistant (Claude, by Anthropic), checked by the team.

State of the audit: 14 November 2026 for sections A to C; the two official guides were checked on 15 November 2026 (last section). The site and the repository are public at
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

* **No video is recorded.** The official Project Demo is the 7-slide deck, which the guide
  accepts in place of a 30-second video.
* **B11**: Aladin is not used.
* **Depth of the "moving object" demonstration**: the three test stars move 1 to 2 pixels.
  The tool shows it best with per-pass stacks and Subtract, not with the chromatic template.
* **Parallax**, named in the challenge background, is not measured reliably.
* **WISE 0855** is recovered only in stacks along its catalogue track, with a statistic calibrated on random tracks.
* **Live fields** lack overlays, flags and the chromatic template.

## Official guides, checked 15 November

The two official guides were read first-hand on 15 November 2026 from the copies the team
printed from the Space Apps site that morning: the **Judging & Awards Guide** (11 pages,
rows J) and the **Project Submission Guide** (16 pages, rows S), both dated 13 November 2026.
Every "must", limit, required field, checkbox and condition in them is listed below and
checked against the repository and the public links. Status is **Met** (verified in the
files or on the web today), **Team action** (only the team member can do or confirm it on
the Space Apps site) or **Not applicable**.

How the links were checked: each public address was requested on 15 November at about 12:05
Beirut time with `curl.exe`, without any login or cookie, following redirects.

| Address | Answer |
|---|---|
| `https://abed-r-j.github.io/parallax-spherex/` | 200 |
| `https://abed-r-j.github.io/parallax-spherex/?field=barnard` | 200 |
| `https://abed-r-j.github.io/parallax-spherex/ParallaX_ZENITH_LABS.pdf` | **404 at that time** (the copy was still being added to the site; re-check before pasting) |
| `https://github.com/abed-r-j/parallax-spherex` | 200 |
| `https://github.com/abed-r-j/parallax-spherex/blob/main/presentation/ParallaX_ZENITH_LABS.pdf` | 200 (raw file: 200, a PDF of 788 kB, the deck as pushed on 14 November) |
| `https://github.com/abed-r-j/parallax-spherex/blob/main/docs/ParallaX_Project_Report.pdf` | 200 |
| `https://github.com/abed-r-j/parallax-spherex/blob/main/THIRD_PARTY_LICENSES.md` | 200 |
| `https://github.com/abed-r-j/parallax-spherex/blob/main/docs/SI_DISCLOSURE.md` | 200 |
| `https://irsa.ipac.caltech.edu/Missions/spherex.html`, `https://caltech-ipac.github.io/irsa-tutorials/spherex/`, `https://ssd.jpl.nasa.gov/` | 200 each |

The deck was rebuilt on 15 November (slides 4 and 6 changed, see S24 and S25). The copies on
GitHub and on the site show the new slides only after the next push and site publish.

### Eligibility for Global Judging (Judging & Awards Guide, pages 3 and 4)

| # | Requirement in the guide | Status | Evidence, or what the team must do |
|---|---|---|---|
| J1 | "Respond to one of the official NASA Space Apps Challenges" | Met | One challenge, "Planet X and SPHEREx": named on slide 1, in the README and in the form text; objectives audited in sections A to C above |
| J2 | All members registered, on the same Local Event, not waitlisted, and shown on the team's Members tab; no new members after submission closes; 1 to 6 members for a Local Event team | Team action | One member, Abed El Rahmane Jaafir (former member: Mohamad Alayli, until 14 November 2026). He must look at the Members tab today and confirm Beirut, not waitlisted. If waitlisted, write to the Local Lead at once |
| J3 | "Complete all of the required fields on the Project Submission page" | Team action | Text for all eight fields is ready in [SUBMISSION.md](SUBMISSION.md); the form refuses to submit while a required field is empty |
| J4 | A demo: a slide presentation of at most 7 slides including title and intro slides, or a video of at most 30 seconds | Met | `presentation/ParallaX_ZENITH_LABS.pdf` has 7 pages (counted with a PDF reader library) and the `.pptx` has 7 slides (counted by PowerPoint in `export_deck.ps1`) |
| J5 | English on the project page and in linked materials | Met | Form text, deck, site, README and report are in English |
| J6 | Submit on the Project tab ("edit", then "submit") before Sunday 15 November, 23:59 local time of the Local Event | Team action | Beirut time. Plan in [SUBMISSION_DAY.md](SUBMISSION_DAY.md): first submission by 18:00 |
| J7 | Tick the box "I have read and understand the project submission requirements ... and I agree to the Participant Terms and Conditions and Privacy Policy" | Team action | The member reads the guide and the terms before ticking |
| J8 | Tick the box confirming original work, that all external resources (code, text, images, even open source) are listed in the References field, and that no copyrighted material is used without permission | Team action | Field 8 of [SUBMISSION.md](SUBMISSION.md) and `THIRD_PARTY_LICENSES.md` hold the list; all images are our own screenshots and plots; no music or footage is used. One addition made today: the deck-building library (PptxGenJS, MIT) is now named in field 8; it should also be added to `THIRD_PARTY_LICENSES.md` |
| J9 | Review for prohibited bilateral activity with China or a Chinese-owned entity, decided by NASA "based on information provided by the applicant" | Team action | Nothing to change in the project. The member answers any affiliation question on the site truthfully; the data used come from NASA/IPAC, NASA/JPL, ESA and IMCCE (France) |
| J10 | Everyone who submits a project by the deadline receives a certificate of participation | Team action | After submitting: see S35 |

### Judging criteria and awards (Judging & Awards Guide, pages 5 to 11)

Each criterion is scored 1 to 5 at every level of judging. "Met" here means the submission
addresses the wording; the score is the judges'.

| # | Guide wording (shortened) | Status | Where it is addressed |
|---|---|---|---|
| J11 | Impact: addresses a problem; reach from a few people to a broad audience | Met | Form field 2 "Why it is important" and field 5 "What benefits does it have?"; slide 7 |
| J12 | Creativity: "a novel concept" or an improvement on existing ideas "in a meaningful way" | Met | Field 5 "What is new"; slides 3 and 4. We state that template subtraction itself is standard |
| J13 | Validity: grounded in scientific principles, feasible, complete; "usability and user-friendliness" count | Met | Field 5 "How we tested it" with baselines, controls and published failures ([RESULTS.md](RESULTS.md)); the tool is live and needs no install; four user steps on slide 4 |
| J14 | Relevance: addresses the challenge directly; "meaningfully integrates NASA data, utilizing it as a core component ... rather than a superficial addition" | Met | Sections A to C above; field 5 "How NASA data is used"; field 7; slide 6 says "NASA, the core" |
| J15 | Presentation: challenge, solution and significance conveyed clearly; "Judges evaluate the demo and full project" | Met | 7-slide deck with a 2-minute script (291 words); sub-headed form text; pasted images |
| J16 | Local awards are optional and separate; only officially submitted Global Nominees go to Global Judging | Team action | Ask the Local Lead how the Beirut awards work |
| J17 | Dates: Global Nominees 3 December 2026; Global Finalists and Honorable Mentions 17 December 2026; Global Winners 26 January 2027 | Not applicable | For the calendar; listed in [SUBMISSION_DAY.md](SUBMISSION_DAY.md) |
| J18 | Ten Global Awards, among them Best Use of Data ("best makes space data accessible or leverages it to a unique application"), Best Use of Science ("best and most valid use of the scientific method"), Best Use of Technology | Not applicable | Awards are decided by the executive judges among Global Finalists. The form text describes access to the data, the tested hypothesis and the server-less design plainly, without naming any award |

### Project Submission Guide

| # | Requirement in the guide | Status | Evidence, or what the team must do |
|---|---|---|---|
| S1 | Submission is open from Saturday 14 November 09:00 to Sunday 15 November 23:59, time zone of the Local Event; local judging times may differ | Team action | Beirut: semi-finals 15:00, presentations 19:00, form closes 23:59 |
| S2 | Reach the page through the profile icon, "My Team", then the "Project" tab | Team action | Steps in [SUBMISSION_DAY.md](SUBMISSION_DAY.md) |
| S3 | Click "Edit"; click "Save Progress" often; changes are visible only to the team until the project is submitted | Team action | Same |
| S4 | Toggle the edit "Lock" to ON while editing; another member can still remove it and overwrite unsaved changes | Team action | The team has one member, who edits in a single window |
| S5 | The page accepts images (JPG, PNG, GIF up to 10 MB) by upload or paste; it does not accept videos or documents | Met | Eight images are prepared in `submission/media/` (6 PNG and 2 GIF; the largest is 3.24 MB; each was opened and looked at). [SUBMISSION.md](SUBMISSION.md) says which goes under which field |
| S6 | Videos and documents go on a cloud service or repository with "a publicly accessible link with no logins, permissions, or registrations required" | Met, with one open point | See the table of answers above. The deck copy on the site answered 404 at check time; the GitHub copy answered 200 |
| S7 | Before submitting: set files to public and test each link in a private browser | Team action | Do it for the three links of fields 3 and 4 |
| S8 | Recommended, not required, for a new website: request a FortiGuard Web Filter Classification (pick a category; company name "N/A") | Team action (optional) | Suggested category "Education" or "Reference"; the guide's link points to `https://www.fortiguard.com/faq/wfratingsubmit`; see [SUBMISSION_DAY.md](SUBMISSION_DAY.md) |
| S9 | Field "Project Name": "What is the name of your project?" | Met | Field 1 |
| S10 | Field "High-Level Project Summary": "What did you develop? How does it address the challenge? Why is it important?" | Met | Field 2, one heading per question |
| S11 | Field "Link to Project Demo": a 7-slide presentation or a video of 30 seconds or less, on an external host, public, no password, permission or registration | Met, with the open point of S6 | Field 3 |
| S12 | The demo counts, "but the majority of judges' evaluation will be based on your project submission" | Met | The long, sub-headed versions of fields 2 and 5 are the ones to paste |
| S13 | Field "Link to Final Project": a public link to the final project | Met | Field 4: the live site (200), with the repository (200) |
| S14 | Field "Detailed Project Description": what it does, how it works, benefits, what you hope to achieve, tools, languages, hardware, software | Met | Field 5, one heading per question |
| S15 | Field "Use of Super Intelligence (SI)": say whether and how SI tools were used. SI "should not be used to come up with your idea". Generated content may not use NASA branding. Generated images and videos need a visible watermark; audio, code and data need an acknowledgement in descriptive text and metadata. The answer is not seen by judges, but the markings inside the project are | Met | Field 6 keeps the agreed wording of [SI_DISCLOSURE.md](SI_DISCLOSURE.md). All 70 tracked source files of the pipeline and the web app carry an "SI disclosure" header line (counted today). The deck states it on slides 6 and 7 and in the file properties (Comments or Description, and the keyword "SI-assisted") of the PPTX and the PDF; the data files of the site carry a `provenance` block with the same sentence. No SI-generated image, video or audio exists, so there is nothing to watermark. No NASA, JPL or Space Apps logo is used |
| S16 | Field "NASA Data": specific details; "To be eligible for a Global Award, you must use at least one NASA data or resource" | Met | Field 7: SPHEREx Level-2 images from NASA/IPAC IRSA (the core), IRSA services, CatWISE2020, JPL Horizons |
| S17 | Field "Space Agency Partner Data and Other References": all data, resources and tools, including code, text and images; partner data is "highly encouraged" | Met | Field 8. ESA, a 2026 Space Agency Partner, through Gaia DR3 |
| S18 | Every team must create a Project Demo | Met | The 7-slide deck |
| S19 | The demo is hosted on an external site with a public link | Met, with the open point of S6 | GitHub (200) and the project site |
| S20 | English on the page and in linked materials; "Slide decks must be in English" | Met | Looked at all seven slide images today |
| S21 | "The slide deck should be no more than seven slides (including the title and intro slides)" | Met | 7 |
| S22 | "Readable font size" and few words per slide "when possible" | Met, with a note | Body text is 14 to 19 point on a 13.3-inch-wide slide and headings are 34; side notes are 13, and only the credits on slide 7 are smaller (10 point). Slides 5 and 6 are dense: say them slowly |
| S23 | Visuals must "display an image of the project" | Met | Real screenshots of the app on slides 1, 2, 3 and 4 |
| S24 | Visuals must "describe the user experience" | Met (fixed today) | Slide 4 now has a block "What a user does": type coordinates or pick a field, watch the little video, click a star for its spectrum, switch to the difference views |
| S25 | Visuals must "include how NASA and space agency open and space based data and technology make your solution possible" | Met (sharpened today) | Slide 6, column "The data that make it possible": NASA SPHEREx Level-2 images from NASA/IPAC IRSA as the core, NASA/JPL Horizons, and the partner agency ESA with Gaia DR3; acknowledgements and DOIs on slide 7 |
| S26 | Slide content must address the team name, the names of the team members and the challenge selected | Met | Slide 1: ZENITH LABS; Abed El Rahmane Jaafir; former member: Mohamad Alayli (until 14 November 2026); "Planet X and SPHEREx" |
| S27 | "Projects that exceed these limits will not be eligible for Global Judging" | Met | 7 slides; no video in the demo field |
| S28 | All members are confirmed participants at the same Local Event; a waitlisted member must ask the Local Lead for acceptance | Team action | Same as J2 |
| S29 | All required fields completed; all content in English | Team action | Same as J3, J5 |
| S30 | "Submit for Judging" must be clicked before the deadline; anything saved or submitted after it is not eligible | Team action | Do not save anything after 23:59 |
| S31 | Demos and final projects "may not include any images, video, audio, or other likeness to persons under 18 years old" | Met | No person appears in the deck (all seven slides viewed), in the eight prepared images (viewed) or on the site; there is no audio or video |
| S32 | Tick "Terms and Conditions", tick "Confirm All Work is Original", then "Submit for Judging"; a banner and a confirmation message appear | Team action | Take a screenshot of the banner |
| S33 | The project may be edited and resubmitted until the end; "Only your last saved submission will be reviewed" | Team action | Submit early, resubmit after any correction, and check the page once more at the end |
| S34 | A participant certificate becomes available on the user Profile once the project is submitted | Team action | The member: see S35 |
| S35 | To get it: profile icon, "Profile", "Participant Information", "2026 NASA Space Apps Challenge", yellow "Download Participant Certificate" button; paper size Letter; PDF only; use a laptop; the name printed is the "Full Name" of the profile, which can be changed at any time | Team action | Check the spelling of the Full Name before downloading. For download problems the guide gives a support address on its page 15 |

Count: 53 rows. Met: 30 (three of them with the open point of the site copy of the deck).
Team action: 21 (one optional). Not applicable: 2.

Not affiliated with or endorsed by NASA.
