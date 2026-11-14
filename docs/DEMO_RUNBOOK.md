# Demo runbook (on-stage laptop, Windows)

How to show ParallaX live without surprises. Everything in the 2-minute demo works with the
network cable out and Wi-Fi off. Only one optional step (the live fetch) needs the internet,
and it has a fallback.

Paths assume the repository is at `C:\...\parallax-spherex`. The demo address is
`http://127.0.0.1:8000`. Replace it with the public site address once the site is published.

## 1. The night before

Do all of this on the laptop that will be on stage, with the same Windows account.

**Build and check**

- [ ] `cd web` then `npm install` (if not done) and `npm run build`. `web\dist\index.html`
      must exist.
- [ ] `cd pipeline` then `uv sync` (if not done). `.venv\Scripts\parallax.exe` must exist.
- [ ] `.venv\Scripts\python.exe -m pytest -q` prints `130 passed, 2 skipped`.
- [ ] In `web`: `npx vitest run` prints `55 passed`.
- [ ] `.venv\Scripts\parallax.exe targets` lists the five challenge fields with their
      cutout counts.

**Run everything once with Wi-Fi off.** Windows Smart App Control is on in enforce mode on
this laptop, and it may check a program file it has not seen before against an online
service. A file that was never run online can therefore be blocked the first time it runs
offline. So:

- [ ] With Wi-Fi **on**, start the server once (section 2) and open every URL of section 3.
      This lets Windows see every program file while it can still look it up.
- [ ] Turn Wi-Fi **off** (airplane mode). Close the terminal and the browser. Start the
      server again from a new terminal and open every URL of the 2-minute demo again.
- [ ] If anything is blocked offline, note which file. Do **not** switch Smart App Control
      off (it is a security setting and may not be possible to switch back on). Use fallback
      C in section 5 instead: a plain static server needs no project binaries.
- [ ] Do not install or update anything after this test (no `uv sync`, no `npm install`, no
      Windows or browser update prompts accepted). An updated binary is a new, unseen file.

**Prepare the machine**

- [ ] Power plan: plugged in, sleep and screen-off set to "never"; notifications off (Focus
      assist / Do not disturb); close chat and mail apps.
- [ ] Browser: Chrome, one window, zoom 100% (Ctrl+0), bookmarks bar hidden, dark theme left
      as is. Open the URLs of section 3 in tabs, in order, and leave them open.
- [ ] Display: try the projector resolution if you can. The layout needs more than 980 pixels
      of window width to show the picture and the side panel next to each other; below that
      the panel moves under the picture. Mirror the display, do not extend it.
- [ ] Record a screen capture of the whole 2-minute path as a last-resort fallback, and keep
      the screenshots in `docs\img\` at hand.
- [ ] Charge the laptop and bring the charger and a video adapter.
- [ ] Phone hotspot ready, in case the venue network is down and you want the live fetch.

## 2. Starting it

Open PowerShell in the repository folder:

```powershell
cd pipeline
.\.venv\Scripts\parallax.exe serve
```

It prints `ParallaX is running at http://127.0.0.1:8000  (Ctrl+C to stop)`. Wait about ten
seconds, then open <http://127.0.0.1:8000>. The home page shows the seven fields. Leave the
terminal open and minimised.

If port 8000 is taken: `.\.venv\Scripts\parallax.exe serve --port 8010` and use that port in
every URL.

Stop it with Ctrl+C in that terminal when the demo is over.

## 3. Tabs to prepare, in order

| Tab | URL | Needs internet |
|---|---|---|
| 1 | `http://127.0.0.1:8000/` | no |
| 2 | `http://127.0.0.1:8000/?field=barnard&det=2&fov=3` | no |
| 3 | `http://127.0.0.1:8000/?field=barnard&mode=sub&fov=2` | no |
| 4 | `http://127.0.0.1:8000/?field=barnard&mode=compare&frame=40&ov=target` | no |
| 5 | `http://127.0.0.1:8000/?field=barnard&seq=frames&frame=10` then click the **Ledger** tab | no |
| 6 | `http://127.0.0.1:8000/?field=rwaur&seq=frames&frame=100` | no |
| 7 | `http://127.0.0.1:8000/?field=wise0855&det=6&fov=4` | no |
| 8 | `http://127.0.0.1:8000/?ra=202.4696&dec=47.1953&live=1&size=3&dets=3` (do **not** preload; open it on stage) | yes |
| 9 | `http://127.0.0.1:8000/?field=barnard&fov=4&embed=1` | no |

Optional extra tabs after tab 7, if the fields `europa52` and `pluto` are listed on the home
page of your build (they were published on 14 November):
`http://127.0.0.1:8000/?field=europa52&seq=frames&det=3&frame=12&ov=sso` and
`http://127.0.0.1:8000/?field=pluto&seq=frames&ov=sso`. Step with the Right arrow: the
object moves from picture to picture under its green label. Say: "This is Pluto, the
original Planet X, in single SPHEREx frames, exactly where JPL Horizons predicts it as seen
from the spacecraft: within 0.03 pixel on average." Check the night before that the label sits on the
object.

## 4. What to click and what to say

### The 2-minute demo (all offline)

| Time | Do | Say |
|---|---|---|
| 0:00 | Tab 1, the home page. | "Pluto, the original Planet X, was found by blinking two photographs. The challenge asks for a web tool that lets anyone do that with SPHEREx. This is ParallaX." |
| 0:15 | Type `08h55m10.831s -7d14m42.53s` in the box, press Enter. The WISE 0855 field opens. Then go to tab 2. | "You type coordinates, in any usual notation, and get the little video. These are the challenge's own coordinates." |
| 0:30 | Tab 2. Press Space to play: three stacks of Barnard's Star, six months apart. | "Here is the fastest star in the sky. Each picture is one survey pass. It moves north, by less than two pixels. SPHEREx pixels are big." |
| 0:45 | Tab 3 (Subtract). | "Subtract the first pass from the latest. Stars that stayed vanish. Barnard's Star leaves a bright lobe where it is and a dark lobe where it was. We measure 10.2 arcseconds per year, give or take 0.5; the Gaia catalogue says 10.36." |
| 1:00 | Point at the dot map on the right. | "Now the catch. Every dot is one picture; height is its colour. No two visits share a colour, because SPHEREx sees each star through a filter that changes across the detector. Subtract two dates naively and every star lights up as a false alarm." |
| 1:15 | Tab 4 (Three-way). Point at the captions under the panels. | "Same frame, three ways. Naive: the partner is seven bandwidths off in colour. Gated: the usual fix, keep only matching pairs. Ours: predict what a static sky looks like at this frame's own colours from the other passes, and subtract that." |
| 1:35 | Tab 5 (Ledger). Point at the false-detection row, then the curves. | "And we measured it, on real frames, with test sources injected. At equal false alarms we find moving sources about 1.8 times fainter than gating in this field: 563 against 1003 microjansky. The raw false-detection counts above it are not like for like: ours is low thanks to a measured error map. The limits are published next to the wins." If someone points at the row "Known target recovered: no" under our method: "Yes. Next to the saturated core the classifier calls the star an artifact; for a star that moves one pixel a pass blink is the better tool, and we say so." |
| 1:55 | Stay on the Ledger. | "Planet X is the motivation, not a claim. What we claim is a tool anyone can open, and a number anyone can reproduce." |

### The 5-minute demo

Do the 2-minute path, slower, and add these after the Ledger.

| Time | Do | Say |
|---|---|---|
| 2:10 | Tab 6 (RW Aurigae). Click the star if no spectrum shows. Point at the three colours of dots in the spectrum. | "Spectra on the fly. Click any pixel and you get its spectrum from every picture, coloured by pass. This young star changed: one way at short wavelengths, the other way at long ones, while a control star showed no change." |
| 2:40 | Tab 7 (WISE 0855). | "Honesty slide. This brown dwarf is the coldest known, and in a single frame it is not there. We recover it only by stacking detectors 5 and 6, with a statistic of 6.6 that we calibrated on random tracks: none of 200 reaches it. And the challenge coordinates are its 2010 position: it has moved two arcminutes west." |
| 3:05 | Tab 2 again, open the **Overlays** panel, tick Gaia and pixel flags. | "Overlays: Gaia stars moved to the date of the picture, WISE sources, contamination flags, and known asteroids predicted as seen from the spacecraft itself." |
| 3:25 | Tab 8 (live M51), if the network is up. Watch the progress bar; frames appear. | "Any other coordinates. There is no server behind this. The site carries a 46-megabyte index of all 1.6 million public SPHEREx images, and the browser reads just the pixels it needs from the public archive. Fifty-five images in about ten seconds on a good connection." |
| 4:00 | Click the **Share** button, show the link and the embed code. Switch to tab 9. | "Every view is a link, and one parameter turns it into something you can embed in a class page or another project." |
| 4:20 | Tab 1, or the About page. | "Updating to a new data release takes a few commands, and the site costs nothing to run because it is static. Built with an SI coding assistant under our direction; every number comes from our own code on real SPHEREx data." |
| 4:40 | End on the Ledger or the three-way view. | "What it does not do: it does not find Planet Nine, it does not measure parallax reliably, and for a star that moves one pixel a simple pass blink still shows the motion best. We say so in the app." |

Numbers you may quote, all from `docs/RESULTS.md`: 357 frames and 3 passes for Barnard's
field; 1427 / 1003 / 563 microJy at 0.5 false alarms per frame (4.44 / 2.40 / 0.99 false
detections per frame at 5 sigma, which are not like for like); 10.2 +- 0.5 against 10.36
arcsec/yr; 1,628,230 images in 45.6 MB; 55 images in 10 to 12 seconds on a fast connection;
130 + 55 tests. Do not round any of them into something stronger.

## 5. Fallbacks

**A. The network is down or slow (live fetch).** Skip tab 8. Say: "The live fetch needs the
archive; here is what it looks like", and show `docs\img\live-m51.png` and
`docs\img\live-offer.png`. Everything else is offline. On a slow link the same fetch takes
one to two minutes: do not wait for it on stage; start it, move on, and come back.

**B. The archive answers but slowly.** The pictures appear as they arrive. Show the first
frames, press **Stop**, and continue. Nothing breaks.

**C. `parallax serve` will not start (blocked binary, broken environment, port in use).**
Serve the built site with a plain static server. Either of these works and needs no project
binary:

```powershell
# with any Python 3 on the machine
python -m http.server 8000 --bind 127.0.0.1 --directory web\dist

# or with Node
cd web
npx vite preview --port 8000 --host 127.0.0.1
```

Every URL of the 2-minute demo works the same. Only "Build this field with the engine" is
unavailable, and the demo does not use it.

**D. The laptop or the browser fails.** Play the screen recording made the night before, or
open the published site from any other computer or a phone (once published).

**E. A field does not open.** Reload once (Ctrl+R). If `?field=...` still fails, go back to
the home page and click the field card; if a pack is missing, the page says "This field
could not be opened" and you move to the next tab.

**F. The projector is narrow.** The side panel drops under the picture. Scroll down for the
dot map and the Ledger, or use `&embed=1` on the picture tabs for a picture-only view.

## 6. Questions likely to come right after

See [JUDGES_QA.md](JUDGES_QA.md). The three to have ready: "Did you find Planet X?" (no,
and we explain why it could not be seen); "How do you know detections are real?" (the
ledger, the two-minute repeat exposure, the known-object labels); "What did the SI do?" (it
wrote most of the code under our direction; the idea, the decisions and the checks are ours;
all numbers come from our code on real data).

## 7. After the demo

- [ ] Ctrl+C in the terminal to stop the server.
- [ ] Turn Wi-Fi back on if you switched it off.
