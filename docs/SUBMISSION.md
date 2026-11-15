# Submission text for the NASA Space Apps project form

Ready-to-paste text for the eight fields of the 2026 project form. Field names and prompts
are copied from the official Project Submission Guide (dated 13 November 2026, read on 15
November). The form closes on **Sunday 15 November 2026 at 23:59, Beirut time**. Only the
last saved submission is judged, so submit early and resubmit. The step-by-step order for
the day is in [SUBMISSION_DAY.md](SUBMISSION_DAY.md).

SI disclosure: drafted with the help of an SI coding assistant (Claude, by Anthropic), checked by the team.

Three things the guide says that shape this page:

* "This is the page that the judges will review. The more information you provide on this
  page, the better the judges can rate your submission." So the long versions below are the
  ones to paste. Each sub-question of the guide is answered under its own short heading.
* The page accepts pasted or uploaded **images** (JPG, PNG, GIF, up to 10 MB each). It does
  not accept videos or documents: those go in as public links that need no login.
* The guide states no character limits. If the live form enforces one, use the shorter
  versions at the end of this file.

Everything must be in English. Open every link in a private browser window, logged out,
before pasting it.

---

## 1. Project Name

Prompt: "What is the name of your project?"

```
ParallaX
```

If the field takes a longer name: `ParallaX: chromatic difference imaging for the SPHEREx sky`

## 2. High-Level Project Summary

Prompt: "Provide a high-level summary of your project. What did you develop? How does it
address the challenge? Why is it important?"

About 275 words.

```
WHAT WE DEVELOPED
ParallaX is a public web tool that plays NASA's SPHEREx infrared images of any patch of sky as a little video, so anyone can spot things that move or change. You type coordinates or pick a field, watch the video, click a star to get its spectrum, and switch to difference views that show what changed. It runs in the browser: the page reads the images itself from the public NASA/IPAC archive, with no server and no account.

HOW IT ADDRESSES THE CHALLENGE
"Planet X and SPHEREx" asks for exactly this tool, tested on five named targets. ParallaX meets every stated objective and ten of the eleven optional considerations, and we measured all five targets against catalogues (Barnard's Star: 10.2 +- 0.5 arcsec/yr; Gaia: 10.36). We also found the catch in the data: SPHEREx never photographs the same spot in the same colour twice, so blinking or subtracting two dates makes ordinary stars look like false alarms. For seven prepared fields ParallaX predicts what an unchanging sky would look like at each frame's own colours and subtracts it. On five real fields, at the same false-alarm rate, this finds moving sources 1.2 to 1.9 times fainter than the usual fix on blank sky.

WHY IT IS IMPORTANT
SPHEREx images the whole sky again and again, and 1,628,230 of its images are already public. With ParallaX anyone with a browser (a classroom, a citizen scientist, a researcher) can look at how any position changes, and can check what they see against a measured, reproducible false-alarm comparison. We publish the numbers, the limits and the code. Planet X is the motivation, not a claim.
```

**Images to paste under this field** (from `submission/media/`): `01_hero.png` first, then
`02_little_video_barnard.gif`.

## 3. Link to Project Demo

Prompt: "Provide a short demonstration ("demo") of your project, either in the form of a
7-slide presentation (including title and introductory slides) or a 30-second or less video
presentation. ... The link you provide should not require a password, permission, or
registration in order to access your project demo."

Our demo is the slide deck: **7 slides, including the title slide**. Paste this link (the
copy served by the project site, which opens directly in the browser):

```
https://abed-r-j.github.io/parallax-spherex/ParallaX_ZENITH_LABS.pdf
```

Backup, the same file in the public repository (use it if the first link does not open in a
private window at the moment you submit):

```
https://github.com/abed-r-j/parallax-spherex/blob/main/presentation/ParallaX_ZENITH_LABS.pdf
```

* The first link answers 200 (verified 15 November 18:40, identical to the repository
  copy). **Open it in a private window before pasting it.** You can change it later by
  resubmitting. A link that answers 404 cannot be judged.
* The limit is strict: more than 7 slides, or a video over 30 seconds, makes the project
  ineligible for Global Judging. The PDF has exactly 7 pages (counted on 15 November).
* The deck shows what the guide asks of a slide demo: the team name, the members' names and
  the challenge (slide 1); pictures of the project (slides 1 to 4); the user experience
  (slide 4, "What a user does"); and how NASA and partner-agency data make it possible
  (slide 6, credits on slide 7).

Decision (15 November, evening): the team member chose to submit the **27.6-second demo
video** in field 3 instead of the deck. It is hosted on the project site:

```
https://abed-r-j.github.io/parallax-spherex/ParallaX_demo_30s.mp4
```

The 7-slide deck above stays public as supporting material. The video and a 112.9-second
judging video (required by the Beirut organizers) were recorded on 15 November 2026; one
adult team member appears and speaks, and there is no music. Both were posted in the team's
Slack channel on 15 November ([SLACK_POSTS.md](SLACK_POSTS.md), post 7). The judging video
is not hosted on the project site or in the repository.

## 4. Link to Final Project

Prompt: "Share a publicly accessible link to your final project. ... The link you provide
should not require a password, permission, or registration in order to access your final
project."

The working tool, live:

```
https://abed-r-j.github.io/parallax-spherex/
```

The source code, public (Apache-2.0):

```
https://github.com/abed-r-j/parallax-spherex
```

If the field accepts only one link, paste the first; the repository link is also the first
line of field 5 and is in the site's footer and About page. If it accepts free text, paste
both lines as `Live tool: ...` and `Source code: ...`.

## 5. Detailed Project Description

Prompt: "Provide additional details about your project. Some questions to consider are:
What exactly does it do? How does it work? What benefits does it have? What do you hope to
achieve? What tools, coding languages, hardware, or software did you use to develop your
project?"

About 1,120 words. Paste all of it; add the images where marked below the block.

```
Live tool: https://abed-r-j.github.io/parallax-spherex/
Source code: https://github.com/abed-r-j/parallax-spherex
Team ZENITH LABS (Abed El Rahmane Jaafir). Former member: Mohamad Alayli (until 14 November 2026). Challenge: Planet X and SPHEREx.

WHAT EXACTLY DOES IT DO?
ParallaX shows how the SPHEREx infrared sky changes over time. A user does four things:
1. Types a position as Right Ascension and declination, in decimal degrees or in the hours-minutes-seconds notation of the challenge text, or picks one of the prepared fields.
2. Watches the SPHEREx images of that patch as a little video: survey passes six months apart, or every exposure in time order, with play, pause, step and speed.
3. Clicks any star or pixel and gets its spectrum on the fly, with a light curve and a CSV download.
4. Switches to the difference views: add or subtract any images, or see one frame differenced three ways side by side.
Overlays show Gaia DR3 stars moved to the date of the frame, WISE sources, contamination flags and known asteroids. Every view is a link that can be shared or embedded in another page. Plain-language text sits under every view, and there is a "How it works" page and a user guide.

HOW DOES IT WORK?
The problem we found. SPHEREx never photographs the same spot in the same colour twice. Each exposure passes through a filter whose wavelength changes across the detector, so every pixel has its own wavelength and every revisit lands on another one. Blink or subtract two dates naively and ordinary stars light up as false alarms. The pixels are also coarse (6.15 arcsec), and the challenge's test stars move by only one to two pixels.

Three parts answer it.
1. Any coordinates, no server. The site carries a 45.6 MB index of all 1,628,230 public SPHEREx Level-2 images. The browser looks up which images cover the position and reads only the pixels it needs from the public archive: 55 images of the galaxy M51 in 10 to 12 seconds on a fast connection.
2. A chromatic template, for the prepared fields. For every frame, an open Python pipeline predicts what a static sky would look like at that frame's own per-pixel wavelength, from the spectrum each pixel showed in the other survey passes, and subtracts it. Fields fetched live in the browser show frames, stacks, spectra and simple pair differences instead.
3. A published three-way comparison. The same real frames are differenced three ways (naive pair, wavelength-matched pair, chromatic template), with artificial moving sources added and searched for again.

What is new. Template subtraction is standard in astronomy; careful SPHEREx blink tools avoid the colour problem by comparing only frames of matching wavelength. ParallaX corrects instead of rejecting, by building the template along the wavelength axis, and it measures all three approaches on the same frames and publishes the result, including where ours loses.

HOW WE TESTED IT, AND WHAT WE FOUND
We treated the idea as a hypothesis and tested it against two baselines on real data, with known answers as controls.
- Sensitivity. At an equal false-alarm rate (0.5 per frame) the template finds moving sources 1.2 to 1.9 times fainter than the wavelength-matched pair on blank sky in five fields (Barnard's Star field: 563 microJy against 1003), and 1.1 to 1.6 times fainter next to a star. It is 3 to 15% deeper in quoted noise.
- The five challenge targets, against catalogues. Barnard's Star: 10.2 +- 0.5 arcsec/yr (Gaia DR3: 10.36). Epsilon Indi B: 4.64 +- 0.09 (catalogue: 4.70). WISE 0855-0714: recovered only in stacks, with a statistic of 6.6 calibrated on random tracks. RW Aurigae and R Draconis: brightness changes measured.
- Moving objects with a known answer. Asteroid (52) Europa is detected in all 24 frames that contain it; with no ephemeris the classifier flags 21 of them as a mover and recovers the track at 28.3 arcsec per hour (JPL Horizons: 28.5). Pluto, the original Planet X, is found in 18 of 18 frames where Horizons predicts it.
- Review. A separate adversarial review pass by the SI assistant, independent of the session that wrote the code, re-ran the code; these are the corrected numbers. Anyone can regenerate them with two scripts.
What did not work, which we also publish: a raw count of false alarms is not a fair comparison, because our low count rests on a measured error map that the pairs do not have, and with a purely statistical noise model our method floods like the others; for a star that shifts one or two pixels a simple blink of per-pass stacks shows the motion better than our template; parallax is not measured reliably; bright targets saturate; R Draconis is not a clean test. Planet X is the motivation, not a claim: a real Planet Nine would be too faint for single SPHEREx frames.

HOW NASA DATA IS USED
NASA data is the core, not an addition. Every picture, spectrum and measurement comes from SPHEREx Level-2 spectral images served by the NASA/IPAC Infrared Science Archive (1,991 frames in the five challenge fields). We use the per-pixel wavelength, variance and flag information, not only the pictures. NASA/JPL Horizons gives the positions of known solar-system objects as seen from the SPHEREx spacecraft. From a Space Agency Partner, ESA's Gaia Data Release 3 gives the star positions and motions used in the overlays and as the reference for Barnard's Star.

WHAT BENEFITS DOES IT HAVE?
- Open to everyone: a browser is enough, with no install, no account and no cost, so classrooms and citizen scientists anywhere can explore SPHEREx in time.
- Useful to researchers: a quick look at any position, and a reproducible false-alarm benchmark for anyone building a search for moving or variable sources on SPHEREx.
- Honest by design: a residual comes with its evidence (three-way view, repeat exposure, known-object labels), and the limits are stated in the app.
- Cheap to keep alive: the site is static files, and updating to a new data release takes a few commands.

WHAT DO YOU HOPE TO ACHIEVE?
That people who are not astronomers can see the infrared sky change for themselves, and that the comparison we publish helps others avoid false alarms in SPHEREx data. Next steps: more moving-object fields (asteroids and comets), the chromatic template in live fields, and following each new SPHEREx data release.

WHAT TOOLS, CODING LANGUAGES, HARDWARE, OR SOFTWARE DID YOU USE?
Languages: Python 3 and TypeScript. Pipeline: NumPy, SciPy, Astropy, HTTPX, FastAPI, Typer, Matplotlib. Web app: React, Vite. Tests: pytest (130 tests) and Vitest (55 tests). Hosting: GitHub Pages (published from the gh-pages branch by a local script). Tests are run locally; a manual GitHub Actions workflow for them is included but has not been run. Hardware: one laptop. An SI coding assistant (Claude, by Anthropic) was used under the team's direction; see the SI field. Open source, Apache-2.0. Development began on 12-13 November 2026, before the on-site event, after the local organizers allowed early preparation. Not affiliated with or endorsed by NASA.
```

**Images to paste in this field** (from `submission/media/`), each right after the paragraph
it illustrates:

| Image | Paste after |
|---|---|
| `05_spectrum_on_click.png` | "WHAT EXACTLY DOES IT DO?" (the four user steps) |
| `06_time_wavelength.png` | "The problem we found" |
| `08_live_fetch.png` | part 1, "Any coordinates, no server" |
| `04_three_way.png` | part 3, "A published three-way comparison" |
| `07_results_chart.png` | "Sensitivity" |
| `03_asteroid_europa.gif` | "Moving objects with a known answer" |

`submission/media/README.md` describes each image and gives a caption for it; its "Form
field" column agrees with the table above. All eight files are PNG or GIF and under 10 MB
(checked on 15 November; the largest, the asteroid GIF, is 3.24 MB).
Every image is a screenshot of our app or a plot made by our code from SPHEREx data: nothing
is SI-generated, so nothing needs a watermark, and no person appears in any of them.

## 6. Use of Super Intelligence (SI)

Prompt: "Did you utilize any Super Intelligence (SI) tools and software in preparing your
solution? If yes, how did you use them?"

The guide says this answer is collected for data purposes and is not shown to the judges,
but the judges do see the SI markings inside the project. The wording below is the agreed
one from [SI_DISCLOSURE.md](SI_DISCLOSURE.md); correct it only if it says more, or less,
than what happened.

```
Yes. We used one SI tool: Claude, a large language model by Anthropic, as a research, coding and writing assistant.

How we used it: the team chose the challenge, the goal and the direction: a comparison of SPHEREx dates that accounts for the changing wavelength. The specific method (a per-pixel chromatic template checked against two baselines) was worked out with the SI assistant, which also surveyed existing tools, gathered and checked background research (the challenge text, the rules, the archive interfaces, the literature), wrote the code and its tests, and drafted the documents under the team's direction. Separate sessions of the same assistant, independent of the session that wrote the code, re-ran the code as an adversarial review; this was not a human or third-party review. The team reviewed the work, ran it and is responsible for it.

What SI was not used for: no SI-generated images, video, audio, voices or faces appear anywhere in the project. Every figure is a plot made by our code from real SPHEREx data, or a screenshot of the running app. All results are computed by the project's own code from real SPHEREx data; the tool itself contains no machine-learning or language model.

How it is marked: every source file written with the assistant carries an "SI disclosure" line in its header; the README, the app's About page, the slides (text and file properties) and docs/SI_DISCLOSURE.md in the repository state the same. Outputs of ParallaX are its own and are not NASA products.
```

## 7. NASA Data

Prompt: "Provide specific details about what NASA data and resources you used. To be
eligible for a Global Award, you must use at least one NASA data or resource."

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

Prompt: "List all of the data, resources, and tools used in your project. Resources should
include any code, text, and images (even if they are open source or freely available) that
you used when creating your project. If you are using any copyrighted materials, make sure
you have permission to use them."

The second checkbox of the form refers to this field: everything external must be listed
here. Compare it once more with `THIRD_PARTY_LICENSES.md` before ticking the box.

```
SPACE AGENCY PARTNER DATA
- European Space Agency (ESA), Gaia Data Release 3 (Gaia mission, processed by the Gaia Data Processing and Analysis Consortium): positions, proper motions and parallaxes of stars. Used for the star overlay (each star moved to the date of the frame) and as the reference position and proper motion of Barnard's Star. Queried at the ESA Gaia archive, with IRSA's copy as fallback.

OTHER DATA AND SERVICES
- SkyBoT, IMCCE, Observatoire de Paris (Berthier et al. 2006, ASP Conf. Ser. 351, 367): known solar-system objects in each field.

SOFTWARE (all open source; none copied into our code, all installed as dependencies)
- Python: NumPy (BSD-3-Clause), SciPy (BSD-3-Clause), Astropy (BSD-3-Clause), HTTPX (BSD-3-Clause), Pillow (MIT-CMU), FastAPI (MIT), Uvicorn (BSD-3-Clause), Typer (MIT), Matplotlib (Matplotlib licence, for figures), pytest (MIT), Ruff (MIT), Hatchling (MIT), uv (Apache-2.0 OR MIT).
- Web: React and React DOM (MIT), Vite (MIT), TypeScript (Apache-2.0), Vitest (MIT), ESLint and typescript-eslint (MIT), Playwright core (Apache-2.0, drives Chrome for screenshots).
- Slides and page images: PptxGenJS (MIT) to build the deck; Microsoft PowerPoint to export it to PDF; pypdf (BSD-3-Clause) and python-pptx (MIT) to write the document properties; FFmpeg (LGPL/GPL, used as a command-line tool, not redistributed) to encode the two animated GIFs from our own screen captures.
- Fonts: IBM Plex Sans and IBM Plex Mono (SIL Open Font License 1.1), bundled with the web app through the @fontsource packages. The PDF and PowerPoint deliverables (slides, report, paper) use system fonts that ship with Windows and Office (Segoe UI, Consolas, Times New Roman, Cambria Math); these are not redistributed in the repository beyond being embedded in those files.
- Hosting: GitHub Pages, published from the gh-pages branch by a local script. Tests are run locally; a manual GitHub Actions test workflow is included in the repository but has not been run.
- SI tool: Claude, by Anthropic (see the Use of SI field).
- Full list with versions and licences: THIRD_PARTY_LICENSES.md in the repository, https://github.com/abed-r-j/parallax-spherex/blob/main/THIRD_PARTY_LICENSES.md

IMAGES
- All images in the project, on this page and in the slides are screenshots of our app or plots made by our code from SPHEREx data. No third-party images, logos, music or video are used.

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

To affirm this, the team member should actually have read the Project Submission Guide and
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
* the slides, the pasted images and any video contain no music, footage, images or logos
  that the team does not have the right to use;
* the work that was done on 12-13 November, before the on-site event, was allowed by the
  local organizers. Keep the organizers' permission in writing (a screenshot of the message).

## How the text serves the five judging criteria

For the team's own check, not for pasting. Wording of the criteria is from the Judging &
Awards Guide.

| Criterion (guide wording, shortened) | Where the form text answers it |
|---|---|
| **Impact**: the problem addressed; how many it helps or inspires | Field 2 "Why it is important"; field 5 "What benefits does it have?" |
| **Creativity**: a novel concept or a meaningful improvement on existing ideas | Field 5 "What is new" (correct along the wavelength axis instead of rejecting frames; a published three-way comparison) |
| **Validity**: scientifically sound, feasible, complete, usable and user-friendly | Field 5 "How we tested it" (baselines, known answers, injected sources, a separate SI review pass, published failures); the four user steps; the live link in field 4 works now |
| **Relevance**: addresses the challenge directly; NASA data is a core component, not a superficial addition | Field 2 "How it addresses the challenge"; field 5 "How NASA data is used"; field 7 |
| **Presentation**: the challenge, the solution and its significance told clearly; "judges evaluate the demo and full project" | The 7-slide deck (field 3), the sub-headed text, the pasted images |

## Shorter versions, only if the live form enforces a limit

High-Level Project Summary, about 65 words:

```
ParallaX plays NASA's SPHEREx infrared images of any patch of sky as a little video, in the browser, so anyone can spot things that move or change. Because SPHEREx sees every revisit in a different colour, for its prepared fields it predicts the unchanging sky at each frame's own colours and subtracts it, and it publishes a measured, reproducible comparison with simpler methods on five real fields.
```

Detailed Project Description, about 150 words:

```
ParallaX plays SPHEREx images of any patch of sky as a little video. Enter RA and Dec; the browser finds the images in a 45.6 MB index of all 1,628,230 public Level-2 images and reads only the pixels it needs from the public archive, with no server. You can blink survey passes, add or subtract images, get spectra on the fly, overlay Gaia DR3, WISE and known asteroids, and share or embed any view by URL. Because SPHEREx sees every revisit at a different wavelength, a Python pipeline predicts the static sky at each frame's own per-pixel wavelength and subtracts it. On five real fields, at the same false-alarm rate, this finds moving sources 1.2 to 1.9 times fainter than wavelength-matched pairs on blank sky (Barnard's field: 563 against 1003 microJy). All five challenge targets are measured against catalogues, and the limits are published. Python, TypeScript, React. Apache-2.0. Planet X is the motivation, not a claim.
```

## Pre-submission checklist

**Eligibility and timing**

- [ ] The team's one member (Abed El Rahmane Jaafir) is registered for the 2026 challenge and
      for the Beirut local event, is not on the waiting list, and appears on the team's
      Members tab. No member can be added
      after submission closes.
- [ ] The team works on one challenge only: "Planet X and SPHEREx".
- [ ] "Submit for Judging" is clicked before Sunday 15 November, 23:59 Beirut time. Submit
      early and resubmit; only the last saved version is judged.
- [ ] Local judging times are confirmed with the Local Lead (semi-finals 15:00,
      presentations 19:00).

**Form**

- [ ] All eight fields are filled, in English, with the long versions above.
- [ ] The images are pasted where the tables above say.
- [ ] Both checkboxes are ticked, and the team can affirm them (see above).
- [ ] The confirmation banner appeared after "Submit for Judging".

**Demo link**

- [ ] The deck has 7 slides, title included. Over the limit means not eligible for Global
      Judging.
- [ ] The link opens in a private window with no password, permission or sign-in.
- [ ] Nobody under 18 appears or is heard in anything linked or pasted.
- [ ] No copyrighted music, footage or images.

**Final project link**

- [ ] The site and the repository open in a private window without sign-in.
- [ ] The repository has `LICENSE` (Apache-2.0), `THIRD_PARTY_LICENSES.md`, `NOTICE`.
- [ ] No personal data anywhere in the repository, site or slides (no e-mail addresses,
      phone numbers, addresses, birth dates, identity documents, CVs).
- [ ] Optional: a FortiGuard web-filter classification was requested for the site address
      (company name "N/A"); see [SUBMISSION_DAY.md](SUBMISSION_DAY.md).

**SI disclosure and branding**

- [ ] Field 6 is filled as above and matches what happened.
- [ ] No SI-generated image, video or audio. If one is ever added, it carries a visible
      "SI-generated" mark.
- [ ] No NASA insignia, logotype or seal, no JPL, Caltech or IPAC logo, no mission patch, no
      NASA-style lettering, anywhere.
- [ ] "Not affiliated with or endorsed by NASA" appears in the app footer and the README.
- [ ] Nothing the tool outputs is described as "according to NASA".

**Beirut local requirements**

- [ ] The final links and the summary are posted in the team's Slack channel
      (posts 7 and 8 in [SLACK_POSTS.md](SLACK_POSTS.md)).
- [ ] Identification and emergency-contact details are sent privately to the organizers,
      never posted in the channel.
