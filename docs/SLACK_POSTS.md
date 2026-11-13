# Slack posts for the team channel

Eight messages to paste into the team's Slack channel, in this order. Each is under 1200
characters and can be read on its own. Text between square brackets in capitals is a
placeholder: replace it before posting. Do not post phone numbers, e-mail addresses or
identity documents in the channel; send those privately to the organizers.

Times are Beirut time. Post 2 is due Saturday 14 November at 14:30 and post 5 on Saturday at
20:30.

---

## 1. Team and roles

```
Team ZENITH LABS. Challenge: "Planet X and SPHEREx". Project: ParallaX.

Members:
- Abed El Rahmane Jaafir, team lead. AI engineer; MEng Software Engineering, currently Master in AI at Saint Joseph University of Beirut. Role: [CONFIRM, for example: problem definition, method, science checks, final decisions].
- Mohamad Alayli. BSc Computer Science, Lebanese American University; autonomous systems and back-end engineering. Role: [CONFIRM, for example: back end, testing, demo, deployment].

Tools: Python, TypeScript and React, public NASA data, and an SI coding assistant (Claude) that we direct and review.

Note on timing: we began preparing on 12-13 November, before the on-site event, after the organizers allowed early preparation.
```

## 2. Idea description (due Saturday 14:30)

```
ParallaX: idea in simple terms.

The challenge: build a public web tool that shows how the SPHEREx infrared sky changes over time, so anyone can spot things that move or vary. Pluto, the original "Planet X", was found this way, by blinking two photographs.

The problem: SPHEREx never photographs the same spot in the same colour twice. Each picture is taken through a filter whose colour changes across the detector. If you blink or subtract two dates, ordinary stars light up as false alarms. The pixels are also large, and the challenge's test stars move by only one to two pixels.

Our solution:
1. Type any coordinates and get the "little video" in the browser, with no server, straight from NASA's public archive.
2. For each picture we predict what an unchanging sky would look like in that picture's own colours and subtract it. What is left is real change.
3. We measure how well this works against the simpler methods, on real data, and publish the numbers and the limits.

Planet X is the motivation, not a claim.
```

## 3. Research findings and sources

```
ParallaX: research findings and sources.

Official resources we used:
- SPHEREx at NASA/IPAC IRSA (the data): https://irsa.ipac.caltech.edu/Missions/spherex.html
- IRSA SPHEREx tutorial notebooks: https://caltech-ipac.github.io/irsa-tutorials/spherex/
- WiseView, our model for a browser blink tool: http://byw.tools/wiseview
- Gaia Data Release 3 (ESA): https://archive.stsci.edu/missions-and-data/gaia

What we found:
- Every SPHEREx revisit is at a different wavelength; a position is seen about 75 times per pass, and passes repeat about every six months.
- Browsers cannot query IRSA directly, but can read the public data bucket. So we ship our own index of all 1,628,230 public images.
- A real Planet Nine would be too faint for single SPHEREx frames.

Papers we rely on:
- Bock et al. 2026, The SPHEREx Satellite Mission, doi:10.3847/1538-4357/ae2be2
- Kuchner et al. 2017, Backyard Worlds, doi:10.3847/2041-8213/aa7200
- Meisner et al. 2018, WISE search for Planet Nine, doi:10.3847/1538-3881/aaae70
- Alard & Lupton 1998, image subtraction, doi:10.1086/305984
- Zackay, Ofek & Gal-Yam 2016, doi:10.3847/0004-637X/830/1/27
```

## 4. Data and methods

```
ParallaX: data and methods.

Data: SPHEREx Level-2 spectral images from NASA/IPAC IRSA, Data Release 1 (doi:10.26131/IRSA678) and Quick Release 3 (doi:10.26131/IRSA662). 1,991 frames in the five challenge fields. Overlays: ESA Gaia DR3, CatWISE2020, known asteroids from IMCCE SkyBoT and JPL Horizons (as seen from the SPHEREx spacecraft).

Methods:
- Download only the pixels we need by range request (about 0.5 MB instead of a 65 MB file).
- Align all pictures of a field and keep the wavelength of every pixel.
- Chromatic template: per pixel, fit brightness against wavelength in the other survey passes, predict the current picture, subtract.
- Compare three ways of differencing on the same pictures: naive pair, wavelength-matched pair, chromatic template.
- Inject artificial moving sources into real pictures and count how many each method finds.
- Measure the five targets against catalogues.

Software: Python (NumPy, SciPy, Astropy), TypeScript and React. 120 Python and 55 TypeScript tests. Open source, Apache-2.0.
```

## 5. Idea validation (due Saturday 20:30)

```
ParallaX: validation on real SPHEREx data, with caveats.

Three ways to difference, Barnard's Star field (357 pictures):
- False detections per picture: naive 4.64, matched pair 2.44, ours 0.99.
- Faintest moving source found half the time, at equal false alarms: 1457, 1025, 563 microJy.
Across five fields ours is 3 to 15% deeper and has fewer false detections in four.

Targets against catalogues:
- Barnard's Star: 10.21 +- 0.26 arcsec/yr (Gaia: 10.36).
- Epsilon Indi B: 4.64 +- 0.09 (catalogue: 4.70).
- WISE 0855: found only in stacks, signal-to-noise 6.6, which is moderately optimistic.
- RW Aurigae and R Draconis: brightness changes measured.

Caveats we publish:
- Matched pairs lose only 1 to 4% of pictures in ordinary fields. Our gain is depth and false alarms, not rescued pictures.
- For a star that moves one or two pixels, a simple blink of per-pass stacks shows the motion better than our method.
- Parallax is not measured reliably. Bright stars saturate. R Draconis is not a clean test.
- We do not claim Planet X.
```

## 6. Progress update (template)

```
ParallaX progress update, [DAY AND TIME].

Done since the last update:
- [ITEM 1]
- [ITEM 2]

In progress:
- [ITEM]

Blocked or at risk:
- [ITEM, OR "nothing"]

Next, before [TIME]:
- [ITEM]

State of the deliverables:
- Web tool: [local only / published at LINK]
- Repository: [private / public at LINK]
- 30-second demo: [not started / draft / final at LINK]
- Two-minute video: [not started / draft / final at LINK]
- Project form: [not started / saved / submitted]

Numbers have not changed since the validation post unless stated here: [NONE / WHAT CHANGED AND WHY].
```

## 7. Demo and video links

```
ParallaX: demo and videos.

- Live tool: [PASTE AFTER PUBLISHING: https://abed-r-j.github.io/parallax-spherex/]
- Source code: [PASTE AFTER PUBLISHING: https://github.com/abed-r-j/parallax-spherex]
- Project demo (30 seconds or less): [PASTE LINK]
- Two-minute judging video: [PASTE LINK]
- Project report (PDF): [PASTE LINK]

All links open without sign-in. Try these in the tool:
- Barnard's Star: add ?field=barnard to the tool address
- Three methods side by side: ?field=barnard&mode=compare&frame=40
- Any coordinates, fetched live in your browser (the galaxy M51): ?ra=202.4696&dec=47.1953&live=1&size=3&dets=3

The two-minute video covers the data, software, methods and tools, a demonstration, what is distinctive, our process with its challenges and limits, and why we chose this approach.
```

## 8. Final summary

```
ParallaX: final summary.

What it is: a public web tool that plays NASA's SPHEREx infrared images of any patch of sky as a little video, in the browser and without a server, so anyone can look for things that move or vary.

What is new: SPHEREx sees every revisit in a different colour. We predict the unchanging sky in each picture's own colours and subtract it, and we publish a measured comparison with the simpler methods (Barnard's field: 0.99 false detections per picture against 2.44 and 4.64).

Impact: classrooms and citizen scientists need only a browser, in Lebanon and anywhere else. Researchers get a quick look at any position and a reproducible false-alarm benchmark. It costs nothing to run and updates with new data in three commands.

Limits: no Planet X claim, no reliable parallax, bright stars saturate.

References: SPHEREx data from NASA/IPAC IRSA (doi:10.26131/IRSA678, doi:10.26131/IRSA662); ESA Gaia DR3; CatWISE2020; IMCCE SkyBoT; NASA/JPL Horizons; Bock et al. 2026 (doi:10.3847/1538-4357/ae2be2). Built with an SI coding assistant under our direction. Not affiliated with or endorsed by NASA.
```
