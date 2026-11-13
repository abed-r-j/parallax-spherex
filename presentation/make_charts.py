"""Slide charts for the ParallaX deck, drawn from the project's own ledger files.

    python presentation/make_charts.py

Reads data/ledger/<field>.json (written by pipeline/scripts/run_ledger.py) and writes
presentation/assets/chart_f50.png: the flux at which half of the injected moving point
sources are recovered on blank sky, at a matched false-detection rate of 0.5 per frame, for
the three ways of differencing (docs/RESULTS.md, section 2). Dark theme, colours of the web app.
The figure is drawn at the size it has on the slide (6.5 in wide), so its 14 pt text is 14 pt there.
SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""
import json
import os

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
out = os.path.join(here, 'assets')
os.makedirs(out, exist_ok=True)

BG, PANEL, LINE, INK, MUTED = '#10161f', '#17202c', '#2c3a4d', '#ebe7dc', '#97a3b4'
MODES = [('naive', 'Naive pair', '#e9793f'), ('gated', 'Wavelength-gated pair', '#4aa3e0'), ('corrected', 'Chromatic template', '#2fc59a')]
FIELDS = [('barnard', "Barnard's\nStar"), ('epsindi', 'Epsilon\nIndi B'), ('rwaur', 'RW\nAurigae'), ('wise0855', 'WISE\n0855-0714'), ('rdra', 'R Draconis\n(saturated)')]

plt.rcParams.update({'font.family': 'Segoe UI', 'font.size': 14, 'text.color': INK, 'axes.labelcolor': INK,
                     'xtick.color': INK, 'ytick.color': MUTED, 'axes.edgecolor': LINE, 'figure.facecolor': BG, 'axes.facecolor': BG})

vals = {}
for key, _ in FIELDS:
    L = json.load(open(os.path.join(root, 'data', 'ledger', f'{key}.json'), encoding='utf-8'))['ledger']
    assert abs(L['fixedRatePerFrame'] - 0.5) < 1e-9
    vals[key] = [L['injection']['atFixedRate']['modes'][m]['mover']['blank']['f50'] for m, _, _ in MODES]
    print(key, [round(v) for v in vals[key]], 'depth', [round(L['modes'][m]['depthUJy']['all'], 1) for m, _, _ in MODES],
          'false/frame', [round(L['modes'][m]['false']['perFrame'], 2) for m, _, _ in MODES])

fig, ax = plt.subplots(figsize=(6.5, 3.85), dpi=300)
w = 0.28
for j, (m, lab, col) in enumerate(MODES):
    xs = [i + (j - 1) * w for i in range(len(FIELDS))]
    ys = [vals[k][j] for k, _ in FIELDS]
    ax.bar(xs, ys, width=w * 0.92, color=col, label=lab, zorder=3)
ax.set_xticks(range(len(FIELDS)))
ax.set_xticklabels([n for _, n in FIELDS], fontsize=14)
ax.set_ylabel('microjansky', fontsize=14, color=MUTED)
ax.set_ylim(0, 2400)
ax.set_yticks([0, 500, 1000, 1500, 2000])
ax.grid(axis='y', color=LINE, linewidth=0.8, zorder=0)
ax.tick_params(length=0)
for s in ('top', 'right', 'left'):
    ax.spines[s].set_visible(False)
ax.legend(loc='upper left', frameon=False, fontsize=14, ncol=1, handlelength=1.2, borderaxespad=0.2)
fig.tight_layout(pad=0.6)
fig.savefig(os.path.join(out, 'chart_f50.png'), facecolor=BG)
print('wrote', os.path.join(out, 'chart_f50.png'))
