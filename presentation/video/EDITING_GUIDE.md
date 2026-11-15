# ParallaX: one-page guide for filming and editing the two videos

SI disclosure: drafted with the help of an SI coding assistant (Claude, by Anthropic); the team films, speaks and edits everything itself. No SI-generated voices, faces, images or video.

You make two files: `ParallaX_demo_30s.mp4` (at most **30.0 s**, hard limit) and `ParallaX_judges_2min.mp4` (about **1:55**, at most 2:00).

## 0. The simpler route: no editor at all

Follow `RECORD_AND_ASSEMBLE.md`: play `teleprompter_30s.mp4` / `teleprompter_2min.mp4`, film yourself reading it, then run `assemble.ps1` once per video. It lines your recording up with the ready-made picture track (`base_*.mp4`: the screen clips cut to the script, subtitles, opening and closing text), keeps your face on screen the whole time, fixes the loudness, cuts at the script's end and checks the length. The files are then called `final_30s.mp4` and `final_2min.mp4`.

The rest of this page is the **manual alternative** in Clipchamp, for when you want to cut by hand (you can also drop `base_*.mp4` into Clipchamp as the picture track and only add your camera clip). The filming advice in section 1 applies to both routes.

## 1. Film yourself (Windows Camera app or a phone)

* **Framing**: landscape (16:9), 1080p, 30 fps. One member (Abed) in the picture from the chest up, eyes about one third from the top, camera at eye height on a stable support (a stack of books works). Look at the lens, not at the screen.
* **Light**: face a window or a lamp; never have the window behind you. Plain, tidy background, nothing with a logo on it.
* **Sound**: a quiet room with soft furniture, phone or laptop about an arm's length away, no fan or air conditioning. If you have wired earphones with a microphone, use them. Record ten seconds, listen back with headphones, then continue.
* **What to say**: exactly the lines marked ON CAMERA and the voice lines in `SCRIPT_30s.md` and `SCRIPT_2min.md`. English only.
* **Takes**: record each ON CAMERA line as its own take, three times. Leave one silent second before and after each take. Length of each take: the time shown in the script, give or take half a second (30 s video: 3.0 s, 4.0 s and 3.5 s; 2 min video: 4 s to 13 s each).
* **Voice over the screen clips**: record the voice lines as audio only (Windows Sound Recorder or the phone's voice memo), one file per line, at the same distance from the microphone as the camera takes.

## 2. Edit in Clipchamp (already on the laptop)

1. Start menu, Clipchamp, "Create a new video". Set the aspect ratio to 16:9.
2. "Import media": your camera takes, your voice recordings, and the screen clips `shot_*.mp4` from this folder (they are silent; `SHOTLIST.md` says what each one shows).
3. Drag the clips to the timeline in the order of the script table. Trim each one by dragging its ends so that it starts and stops at the times in the "Time" column. To shorten a screen clip without cutting it, select it and use "Speed" (up to 2x looks fine).
4. Put each voice recording on the audio track under its screen clip. Select every clip that has sound and set the same volume; mute nothing but the screen clips (they have no sound anyway).
5. **Subtitles**: Clipchamp cannot import `.srt` files. Either add "Text" items (style "Plain text", white, bottom centre) and paste the lines from `subs_30s.srt` or `subs_2min.srt` at their times, or turn on "Captions" (auto-captions, English) and correct every line against the script. English subtitles are a good idea even though you speak English. If you upload to YouTube you can also attach the `.srt` file there (Subtitles, Add, Upload file, "With timing").
6. Add the on-screen texts named in the script (project name and tagline, the data credit) as "Text" items in Segoe UI or a similar plain font. On the last seconds add, small: "SPHEREx data: NASA/IPAC IRSA. Not affiliated with or endorsed by NASA. Made with the help of an SI coding assistant."
7. No music, unless you composed and recorded it yourself. No transitions longer than a quarter of a second. No stock footage, no stickers, no filters.
8. "Export", 1080p. Name the files as above.

## 3. Check the length (do not skip)

* In Clipchamp the total is shown at the right end of the timeline. Aim for **28.5 s** for the demo: the limit is 30.0 s and a longer video makes the project ineligible for Global Judging.
* After exporting, check the real file: right-click, Properties, Details, "Length"; or in PowerShell: `ffprobe -v error -show_entries format=duration -of csv=p=0 ParallaX_demo_30s.mp4`. It must print a number **below 30.0** (and below 120 for the other video).
* After uploading, look at the duration the hosting site shows. If it says 0:31, cut half a second and upload again.

## 4. Upload and test the link

* **YouTube**: Create, Upload video, visibility **Unlisted**, audience "No, it's not made for kids". Or **Google Drive**: upload, Share, General access **"Anyone with the link"**, role Viewer.
* Open the link in a **private (incognito) window** where you are not signed in. It must play without asking for a login. Paste that link in the submission form and in the team's Slack channel.
* Keep the original files; do not delete the upload before judging has ended.

## 5. Rule reminders

* English speech, or English subtitles if any word is in another language.
* No music, images or footage that you do not own. The screen clips are our own app on public NASA data.
* Nobody under 18 in the picture or on the sound, not even in the background.
* The member on camera agrees to appear; nobody else is in the frame.
* No NASA, JPL, Caltech, IPAC or Space Apps logos, no mission patches, no NASA-style lettering, on screen, on clothes or behind you.
* No SI-generated voices, faces, images or video. If a tool offers "AI voiceover", "AI avatar" or "background replace", do not use it.
* Say only what the scripts say about results. Never say that ParallaX found Planet X or measured a parallax.
* Mention SI use in the video description: "Software, documents and figures were produced with the help of an SI coding assistant (Claude, by Anthropic), directed and checked by the team. No SI-generated images, video, voices or faces."
