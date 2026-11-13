"""Check the screen clips: print size, frame rate, frame count and length of every
video/shot_*.mp4 (ffprobe), and save a contact sheet of a few frames of each clip to
video/_check/<shot>.jpg so that a person can LOOK at them.

    python video/check_clips.py [name-filter]

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""
import glob
import json
import os
import subprocess
import sys

from PIL import Image

here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, '_check')
os.makedirs(out, exist_ok=True)
flt = sys.argv[1] if len(sys.argv) > 1 else ''
N = 4
for mp4 in sorted(glob.glob(os.path.join(here, '*.mp4'))):
    name = os.path.splitext(os.path.basename(mp4))[0]
    if flt and flt not in name:
        continue
    p = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
                        'stream=width,height,r_frame_rate,nb_read_frames,codec_name,pix_fmt:format=duration', '-of', 'json', mp4],
                       capture_output=True, text=True, check=True)
    j = json.loads(p.stdout)
    s = j['streams'][0]
    dur = float(j['format']['duration'])
    audio = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', mp4],
                           capture_output=True, text=True).stdout.strip()
    print(f"{name}: {s['width']}x{s['height']} {s['r_frame_rate']} fps {s['nb_read_frames']} frames {dur:.2f} s {s['codec_name']} {s['pix_fmt']} audio={'yes' if audio else 'none'} {os.path.getsize(mp4) / 1e6:.1f} MB")
    tiles = []
    for k in range(N):
        t = dur * (k + 0.5) / N
        f = os.path.join(out, f'_{name}_{k}.png')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{t:.3f}', '-i', mp4, '-frames:v', '1', f], check=True)
        tiles.append(Image.open(f).convert('RGB').resize((960, 540), Image.LANCZOS))
    sheet = Image.new('RGB', (1920, 1080))
    for k, im in enumerate(tiles):
        sheet.paste(im, ((k % 2) * 960, (k // 2) * 540))
    sheet.save(os.path.join(out, f'{name}.jpg'), quality=88)
    for k in range(N):
        os.remove(os.path.join(out, f'_{name}_{k}.png'))
