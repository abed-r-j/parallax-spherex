# Likely questions from judges, with honest answers

Thirty-two questions (12b and 15b were added after the independent review) grouped by the five judging criteria (Impact, Creativity, Validity,
Relevance, Presentation). Each answer is short, says what is true, and is backed by a number
from [RESULTS.md](RESULTS.md) or the build reports. Where the honest answer is "no" or "not
yet", it says so.

## Impact

**1. Did you find Planet X?**
No, and we do not claim to. At the roughly 500 astronomical units of current orbit fits, a
Planet Nine would be two to five magnitudes fainter than SPHEREx's depth, and earlier WISE searches
already cover the brightest models. Planet X is the motivation: Pluto was found by blinking
two photographs. What we show is that the method works on real moving objects: Barnard's
Star measured at 10.2 +- 0.5 arcsec/yr against 10.36 in Gaia, and an asteroid and Pluto
found, on average, within 0.05 pixel of where JPL Horizons predicts them as seen from SPHEREx.

**2. Who would actually use this?**
Three groups. Citizen scientists and classrooms, who need only a browser, including in
Lebanon and the Arab region where a research computing setup is rare. Survey scientists who
want a quick look at any position: 55 images in 10 to 12 seconds on a fast connection. And people who build
transient searches on SPHEREx, who get a reproducible false-alarm benchmark on five fields.

**3. What is the single most useful thing you produced?**
The three-way ledger. On the same real frames: naive pair, wavelength-gated pair, chromatic
template; at the same false-alarm rate, the flux at which half of injected moving sources
are found in Barnard's field is 1427, 1003 and 563 microJy. Anyone
can regenerate it with one script in two to four minutes per field.

**4. What does it cost to keep running?**
Nothing. The site is static files and reads public data. There is no server, no database and
no account. The whole index of 1,628,230 images is 45.6 MB.

**5. What happens when new data arrives?**
A few commands. `parallax fetch` downloads only images that are not on disk yet,
`parallax publish` rebuilds the data packs, and `build_sky_index.py` fetches only the days
that are missing. The first full index download took about 73 minutes; an update
downloads only the new days. Pushing to the repository tests and redeploys the site.

**6. Could volunteers really discover something with it?**
Possibly variable stars and unusual movers, but we are careful here. Almost everything
SPHEREx can see moving in a single frame is a known asteroid, and the tool labels those. Its
value for volunteers is that a residual comes with evidence: the three-way view, the
two-minute repeat exposure, and the known-object overlay. A vetting queue for volunteers is
on the roadmap, not built. The Candidates tab is a list of things to look at, not of
discoveries: in Barnard's field its 16 groups all sit in the halo of the saturated star.

## Creativity

**7. How is this different from other blink tools?**
Most tools blink or subtract frames, and the careful ones only compare pairs whose
wavelengths match. We correct instead of rejecting: for each frame we predict the static sky
at that frame's own per-pixel wavelength from the other survey passes and subtract the
prediction. Then we measure all three approaches on the same frames and publish the result,
including where ours loses. We did not find a published false-alarm comparison of this kind
for SPHEREx blinking. (If asked which tools: public viewers for this challenge and for WISE;
we describe approaches and do not name or rank anyone's project.)

**8. Is the chromatic template your own idea, or the SI's?**
Both had a part, and we say so. The team chose the challenge, the goal and the direction: a
comparison of SPHEREx dates that accounts for the changing wavelength. The specific method
(a per-pixel chromatic template checked against two baselines) was worked out with the SI
assistant (Claude, by Anthropic), which also surveyed existing tools, wrote the code and
drafted the documents under our direction. We reviewed the work, ran it and are responsible
for it. Template subtraction itself is standard in
astronomy; what is new here is building the template along the wavelength axis, because
SPHEREx never repeats a wavelength.

**9. What was the most surprising thing you learned?**
That colour is not the largest problem. Pixel sampling is. SPHEREx pixels are 6.15 arcsec,
larger than the star images, so the peak pixel of a bright star scatters by 23 to 27% from
frame to frame even at the same wavelength. That is why a purely statistical noise model
gives 28 to 33 false detections per frame in Barnard's field for all three methods, ours
included, and why our template carries a measured error map.

**10. Why "ParallaX"?**
Parallax is the apparent shift of a nearby object when the observer moves; the challenge
text describes it. The name joins that word with the X of "Planet X". We are straightforward that we do not measure
parallax reliably: our fitted annual term for Barnard's Star is about three times its true
parallax.

**11. What is creative about the display?**
The time-against-wavelength map: every frame is a dot, and you see at a glance that no two
visits share a wavelength. Also spectra on the fly from any pixel, a wavelength-mismatch
tint over pair differences, and a three-way view of one frame on one scale.

## Validity

**12. How do you know the detections are real?**
Four checks. (1) Known answers: two proper motions within one sigma of the catalogue, and an
asteroid and Pluto within 0.05 pixel of the prediction on average. (2) Injection and recovery:
artificial sources are added to real frames and searched for again. (3) A physical veto: a
"mover" that is absent in the exposure of the same detector two minutes later is a cosmic
ray; this removed 14 of 17 single-frame movers in the first 202 Barnard frames. (4) Labels
from SkyBoT and JPL Horizons for known objects. And we count false detections rather than
assume there are none: 0.99 per frame in Barnard's field for our method. Finally, the work
went through an independent adversarial review that re-ran the code; the published numbers
are the corrected ones.

**12b. Did the classifier find the asteroid by itself?**
Now yes; at first, no. Asteroid (52) Europa is detected in all 24 frames that contain it
(S/N 111 to 236). Without the ephemeris, the classifier calls 21 of the 24 a mover and the
linker recovers the track blind: 28.3 arcsec per hour at position angle 89.2 degrees, against
28.5 at 89.1 from JPL Horizons. Before a fix made after the independent review it called
only 2 of 24 a mover (so bright a source covered more pixels than a fixed limit allowed), and
our earlier "24 of 24" rested on the ephemeris label. Pluto is detected in 18 of 18 frames
(S/N 14 to 57) but moves 0.7 arcsec per hour, below the linker's minimum of 1: blind, the
classifier calls 8 a mover and 8 a variable, and only the ephemeris names it. Anything
faster than about 170 arcsec per hour is rejected as a cosmic ray.

**13. Why is your chromatic method not better at showing Barnard's Star moving?**
Because a template built from two other passes averages two old positions of the star, so
the dark lobe at the old position is diluted. Both lobes exceed 5 sigma in 69% of Barnard
frames for the gated pair and in only 17% for the template. For a star that shifts one or
two pixels, a pair, or simply blinking per-pass stacks, is the better tool, and that is the
app's default for such stars. The template is better at depth and at sensitivity for a given
false-alarm rate across the field, not at this.

**14. Gating throws away most frames, so yours rescues them, right?**
No. We expected that and measured the opposite: 96 to 99% of frames find a partner within
half a bandwidth in ordinary fields, because the survey revisits at nearly repeating
wavelengths. Only the R Draconis deep field loses 21%. Our advantage is depth (3 to 15%) and
sensitivity at a matched false-alarm rate, not rescued frames.

**15. Is the comparison fair to the other methods?**
The sensitivity comparison is; the raw false-alarm count is not, and we say so. Sensitivity
is compared at the same false-detection rate (0.5 per frame, and also 0.2 and 1), not at
the same threshold: 1.2 to 1.9 times fainter on blank sky, 1.1 to 1.6 next to a star. We
also tried a stronger simple baseline, the weighted mean of all wavelength-matched frames:
it does not beat the template (733 / 821 / 894 against 563 / 593 / 707 microJy). The
shortcut used for the injection test was checked against a full re-run (peak S/N 0.98,
completeness within 0 to 4 points). The choices we made (a 14-pixel exclusion around the
target, the 0.5 rate) are stated and stored in the ledger files.

**15b. Your template only wins on false alarms because of its noise model, doesn't it?**
Largely, yes. With one purely statistical sigma for all three methods the template floods as
much as the pairs: 27.55 / 31.38 / 32.98 false detections per frame in Barnard's field. Its
low count in the main table (0.99) comes from its measured model-error map, which the pairs
do not have, so the false-alarm columns are not like for like. Under every calibration we
tried it still gives fewer false detections than the gated pair in Barnard's and RW
Aurigae's fields; in Epsilon Indi and WISE 0855 the answer depends on the noise model; in
R Draconis it has slightly more. An earlier version of our table showed the template's
map-based numbers in the "plain" column; the independent review caught it and we corrected
it. The claim we stand on is the matched-rate sensitivity. The false-alarm tail itself is
not Gaussian: artefacts of saturated stars and unflagged transients dominate it, which is
why the matched-rate thresholds are 8 to 12 sigma.

**16. Where does your method lose?**
R Draconis: the saturated star fills the cutout, and the template has slightly more false
detections than the gated pair (0.61 against 0.58 per frame). The two-lobe signature of
moving stars (question 13). And RW Aurigae's change is caught in fewer frames by the template
than by the gated pair (39% against 86%). The Ledger tab shows this openly: under "Known
target recovered" the template says "no" for Barnard's Star, because its detection sits next
to the saturated core and the classifier calls it an artifact in 85% of frames. Next to a
star at a strict 0.2 false alarms per frame the template has no advantage. And pass-to-pass
registration offsets of up to 0.1 pixel are not corrected in the differencing.

**17. You say you detect WISE 0855. How sure are you?**
It is invisible in single frames. In stacks of detectors 5 and 6 along the catalogue track a
moving source appears with a combined statistic of 6.6 (395 +- 69 microJy), 1.5 arcsec from
the predicted position. That number is not a Gaussian sigma, because the pass differences
are not independent, so we calibrated it on random tracks in the same maps: they scatter by
0.6; 1 of 2,000 fixed-position tracks reaches 6.46 and 0 of 200 searched tracks reach 6.63.
The reversed track gives -4.1 and detectors 1 to 4 give 0.2, as expected for so cold an
object. The motion, 7.81 +- 1.57 arcsec/yr against a catalogue 8.15, assumes the catalogue
parallax; an independent centroid fit gives 6.2 +- 1.1.

**18. Can you measure distance by parallax, as the challenge text suggests?**
Not reliably. SPHEREx always looks about 90 degrees from the Sun, so any systematic effect
tied to the Sun's direction imitates parallax. Our annual term for Barnard's Star is about
three times its true parallax. We report proper motion and say parallax is not measured.

**19. The bright targets saturate. Does that not invalidate the measurements?**
It limits them. Barnard's Star is saturated in 99% of frames and R Draconis in 97%; RW
Aurigae in 39%. Positions come from fitting the unsaturated wings (0.11 pixel scatter
between detectors for a saturated star, 0.04 for an unsaturated one) and fluxes are relative,
not absolute. For Barnard's Star the honest error on the motion is the scatter between the
six detectors, 0.5 arcsec/yr, not the formal 0.26.

**20. Are the injected test sources realistic?**
They are simple: achromatic point sources with a Gaussian profile, placed on blank sky and
next to stars. Real sources have colours. This favours no method in particular, but it means
the completeness numbers are for that kind of source.

**21. How do you know the live browser path gives the right pixels?**
We compared it with the Python pipeline on the same images: resampled pixels agree within
2e-4 relative, the wavelength within 5e-6 micron, and our coordinate code within 1e-6 pixel
of Astropy on a real header. The index was checked against the live archive at six
positions: zero misses.

**22. How well is it tested?**
130 Python tests and 55 TypeScript tests, all offline, on synthetic data with known answers
and on recorded real service responses. Two more Python tests call live services and run on
request.

## Relevance

**23. Does it meet the stated objectives?**
Yes, all of them: a web tool; SPHEREx images; coordinates in right ascension and
declination, including the exact notation in the challenge text; a little video; and all
five named targets tested and measured. The one item pending at the time of writing is
publication of the public site. Of the eleven optional considerations we address ten fully;
for the eleventh we use Astropy but not Aladin. See
[CHALLENGE_CHECKLIST.md](CHALLENGE_CHECKLIST.md).

**24. Which NASA data do you use, and how deeply?**
SPHEREx Level-2 spectral images, Data Release 1 and Quick Release 3, from NASA/IPAC IRSA:
1,991 frames in the five challenge fields, and the catalogue of all 1,628,230 public images
for the index. We use the per-pixel wavelength, the variance and the flag planes, not only
the pictures. Also CatWISE2020 from IRSA, JPL Horizons with the SPHEREx spacecraft as the
observer, and IRSA's moving-object search as an independent check (the same 136 images of
asteroid (52) Europa, zero differences).

**25. Do you use partner agency data?**
ESA's Gaia Data Release 3, as the challenge resources recommend: star positions and motions
for the overlays, moved to the date of each frame, and the reference proper motion for
Barnard's Star. The Canadian resources listed for this challenge (NEOSSat, CADC) are not
used.

**26. Why does your WISE 0855 field not sit on the challenge coordinates?**
The challenge coordinates are the object's 2010 WISE position. At 8.1 arcsec per year it is
now about 2 arcmin further west, and that is where we find it. Typing the challenge
coordinates still opens the field, which is 8.3 arcmin wide and contains both positions.

**27. Did you really make spectra "on the fly"?**
Yes. Clicking a pixel builds its spectrum in the browser from every frame at that frame's
own wavelength, with a light curve in a chosen wavelength window and a CSV download. It also
works on live fields.

## Presentation

**28. What did the SI do and what did you do?**
We chose the challenge, the goal and the direction, directed the work, decided what to keep,
ran everything and reviewed it. The specific method was worked out with an SI assistant
(Claude, by Anthropic), which also surveyed existing tools, wrote the code and the tests and
drafted the documents under that direction. Every number
comes from our own code running on real SPHEREx data. No SI-generated images, video, voices
or faces are used, and the tool contains no machine-learning model.

**29. You started before the hackathon. Is that allowed?**
Development began on 12-13 November 2026, before the on-site event, after the local
organizers allowed early preparation. We state this in the README and the report, and the
commit history is not back-dated.

**30. If you had another month, what would you do?**
Model the sub-pixel position of each exposure in the template, which is the largest
remaining noise term. Add co-moving fields so that a fast object can be followed across the
sky. Build a volunteer vetting queue on top of the candidates. And run the ledger on many
more fields, so the benchmark is a survey property and not five examples.

## Short answers to keep ready

* Barnard's Star: 10.2 +- 0.5 arcsec/yr measured, 10.36 in Gaia DR3; shift of 1.65 pixels.
* Epsilon Indi B: 4.64 +- 0.09 measured, 4.70 catalogued; shift of 1.02 pixels.
* Fainter at matched false alarms (0.5 per frame): 1.2 to 1.9 times on blank sky, 1.1 to 1.6
  next to a star; Barnard 563 against 1003 microJy.
* Depth advantage over gating: 3 to 15% in quoted noise, 17 to 25% in measured blank-sky scatter.
* False detections per frame, Barnard: 4.44 naive, 2.40 gated, 0.99 chromatic; not like for
  like (ours uses a measured error map). With plain noise: 27.55 / 31.38 / 32.98.
* Europa: 21 of 24 called a mover with no ephemeris; blind track 28.3 arcsec/h (ephemeris 28.5).
* WISE 0855: statistic 6.6, calibrated on random tracks; never call it a sigma.
* Index: 1,628,230 images, 45.6 MB. Live: 55 images in 10 to 12 s on a fast connection.
* Asteroid (52) Europa and Pluto: within 0.05 and 0.03 pixel of the Horizons prediction.
* Tests: 130 Python, 55 TypeScript.
* Not a claim: Planet X, parallax, absolute fluxes of saturated stars.
