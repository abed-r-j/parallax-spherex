# ParallaX: record yourselves, then one command per video

SI disclosure: this guide and the scripts were drafted with the help of an SI coding assistant (Claude, by Anthropic). You film and speak everything yourselves: no SI-generated voices, faces or imagery.

The exact words are in `SCRIPT_30s.md` and `SCRIPT_2min.md`. Do the 30-second video first, then repeat the steps with `2min`.

1. **Open the teleprompter full screen** on the laptop: `presentation\video\teleprompter_30s.mp4` (double-click, then F11 or the full-screen button; pause it at the very start; sound on).
2. **Start recording yourselves** with the Windows Camera app (video mode) or a phone propped at eye level next to the laptop. Both of you in the frame, landscape if possible, a quiet room, the light in front of you (never a window behind you).
3. **Press play.** You hear five short beeps (5, 4, 3, 2, 1) and one long beep at zero. Start speaking as the long beep ends and follow the big line; the name beside it says who speaks, the bar shows how much of the line's time is used, the small line is what comes next. After the last line hold still for one second.
4. **Stop the recording** and copy the file to `presentation\video\takes\` as `take_30s.mp4` (and `take_2min.mp4` for the long one). A `.mov` from a phone also works: give its name with `-Take`.
5. **Run the two commands** in PowerShell (Start menu, type "PowerShell"):

       cd "C:\Users\abedr\Downloads\Nasa Space Apps Beirut\parallax-spherex\presentation\video"
       powershell -ExecutionPolicy Bypass -File assemble.ps1 -Video 30s  -Take takes\take_30s.mp4
       powershell -ExecutionPolicy Bypass -File assemble.ps1 -Video 2min -Take takes\take_2min.mp4

   Each one writes `final_30s.mp4` / `final_2min.mp4` and a contact sheet `final_30s_contact.jpg` / `final_2min_contact.jpg`, and prints the offset it used, the duration, the resolution and the size. A red message means the file must not be submitted.
6. **Check**: open the contact sheet (six frames: your faces at the start and the end, the small face window at the top in between, subtitles readable), then play the final file with sound. If the voice and the subtitles are out of step, run the command again with `-Offset` and the number of seconds into your recording where the first word starts, for example `-Offset 6.2` (the script prints the value it used; add to it if the voice comes late, subtract if it comes early). Other options: `-Layout split` (screen on the left, you in a column on the right), `-Corner tl` (face window top left), `-CropY 0.3` (a tall phone video: keep a higher part of the picture).
7. **Rules**: the demo must be 30.0 s or less (the script stops it at 28.5 s and refuses anything over 29.9 s); the judges' video 2:00 or less; English; no music; nobody under 18 in the picture; both of you agree to appear; no NASA, JPL or Space Apps logos anywhere in the shot (clothes, wall, laptop stickers).

A second take is cheap: record again and run the same command. When both files are right, upload them as **unlisted** YouTube videos, or hand them to the team lead to be hosted with the project site. The `takes\` folder and the `final_*.mp4` files are not committed to the public repository (see `.gitignore`); the team decides later whether to publish them.

If the scripts or the shots change: `node make_scripts.mjs`, then `node build_video.mjs` (rebuilds `base_*.mp4`, `teleprompter_*.mp4`, `timeline_*.json`), then record again. `make_placeholders.ps1` makes two labelled dummy takes for trying the command without a recording.
