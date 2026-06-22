"""nSight perception-profile radar — SMALL MULTIPLES (one mini-radar per brand vs the
average). Far more readable than 8 overlaid lines. matplotlib, free, SVG+PNG.
Run: uv run python chart_lab/gen_radar_sm.py <ver>
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

LAB = Path(__file__).parent
d = json.loads((LAB / "radar_0.json").read_text())
attrs = d["categories"]
series = {k.split(",")[0].strip(): v for k, v in d["series"].items()}
brands = list(series.keys())

CREAM = "#F4EFE6"; INK = "#2B2B2B"; GREY = "#B7AFA0"
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK})
PALETTE = ["#2F6F8F", "#D9508A", "#E29B2E", "#4E8A4E", "#7E5BA6",
           "#C04A3B", "#3FA9A0", "#6B7C45"]

N = len(attrs)
ang = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist(); ang += ang[:1]
avg = [float(np.mean([series[b][i] for b in brands])) for i in range(N)]
avg_c = avg + avg[:1]

fig = plt.figure(figsize=(12.5, 7.6), dpi=150)
fig.patch.set_facecolor(CREAM)

for k, brand in enumerate(brands):
    ax = fig.add_subplot(2, 4, k + 1, polar=True)
    ax.set_facecolor(CREAM)
    ax.set_theta_offset(np.pi / 2); ax.set_theta_direction(-1)
    v = series[brand] + series[brand][:1]
    ax.plot(ang, avg_c, color=GREY, lw=1.0, ls=(0, (3, 2)), zorder=2)        # avg reference
    ax.fill(ang, v, color=PALETTE[k], alpha=0.30, zorder=3)
    ax.plot(ang, v, color=PALETTE[k], lw=1.8, zorder=4)
    ax.set_xticks(ang[:-1])
    ax.set_xticklabels([str(i + 1) for i in range(N)], fontsize=7, color="#8A857B")
    ax.set_ylim(0, 60); ax.set_yticks([30]); ax.set_yticklabels([])
    ax.grid(color="#DED6C7", lw=0.7)
    ax.spines["polar"].set_color("#CFC8BA")
    ax.set_title(brand, fontsize=11, fontweight="bold", color=PALETTE[k], pad=8)

fig.suptitle("Brändimielikuvat — profiili brändeittäin (% samaa mieltä · autettu · Marraskuu 2025)",
             x=0.5, y=1.0, fontsize=14, fontweight="bold", color=INK)
# numbered attribute key (3 columns)
key = "   ".join(f"{i+1} {a}" for i, a in enumerate(attrs))
cols = [attrs[0:5], attrs[5:10], attrs[10:14]]
xs = [0.06, 0.40, 0.72]
for ci, group in enumerate(cols):
    start = sum(len(c) for c in cols[:ci])
    txt = "\n".join(f"{start+j+1}.  {a}" for j, a in enumerate(group))
    fig.text(xs[ci], 0.02, txt, fontsize=8, color="#6E685C", va="bottom", linespacing=1.5)
fig.text(0.5, 0.115, "– – –  keskiarvo (kaikki brändit)", ha="center", fontsize=8.5, color=GREY)

fig.subplots_adjust(left=0.03, right=0.99, top=0.90, bottom=0.20, wspace=0.45, hspace=0.45)
ver = sys.argv[1] if len(sys.argv) > 1 else "sm1"
fig.savefig(LAB / f"radar_{ver}.png", facecolor=CREAM)
fig.savefig(LAB / f"radar_{ver}.svg", facecolor=CREAM)
print(f"wrote radar_{ver}.png/.svg")
