"""Adds a two-line plain caption under presentation/assets/chart_f50.png -> submission/media/07_results_chart.png.

The chart itself is a matplotlib plot of measured numbers (docs/RESULTS.md, section 2, column
"f50, blank sky"); this script only adds text below it. No SI-generated imagery.
SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent.parent
src = Image.open(root / "presentation" / "assets" / "chart_f50.png").convert("RGB")
bg = src.getpixel((3, 3))
lines = [
    "Faintest moving test source found half the time, on blank sky. Lower is better.",
    "Real SPHEREx images; all three methods held to the same false-detection rate (0.5 per frame).",
]
font = ImageFont.truetype("segoeui.ttf", 40)
pad, lh = 40, 58
out = Image.new("RGB", (src.width, src.height + pad + lh * len(lines) + 20), bg)
out.paste(src, (0, 0))
d = ImageDraw.Draw(out)
for i, t in enumerate(lines):
    w = d.textlength(t, font=font)
    assert w < src.width - 40, (t, w)
    d.text(((src.width - w) / 2, src.height + pad // 2 + i * lh), t, font=font, fill=(232, 228, 216) if i == 0 else (160, 170, 185))
dst = Path(__file__).resolve().parent / "media" / "07_results_chart.png"
out.save(dst, optimize=True)
print(dst, out.size)
