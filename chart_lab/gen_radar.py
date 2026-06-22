"""nSight perception-profile radar — matplotlib (native polar; Vega-Lite has no radar).
Free, deterministic, exports SVG+PNG. Run: uv run python chart_lab/gen_radar.py <ver>
"""
import json
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

LAB = Path(__file__).parent
d = json.loads((LAB / "radar_0.json").read_text())
attrs = d["categories"]
series = {k.split(",")[0].strip(): v for k, v in d["series"].items()}  # brand -> values

CREAM = "#F4EFE6"; INK = "#2B2B2B"
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK,
                     "axes.edgecolor": "#CFC8BA"})

# 8-colour categorical palette (distinct, on cream)
PALETTE = ["#2F6F8F", "#D9508A", "#E29B2E", "#4E8A4E", "#7E5BA6",
           "#C04A3B", "#3FA9A0", "#8A8170"]

N = len(attrs)
ang = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
ang += ang[:1]  # close

fig = plt.figure(figsize=(11, 8.2), dpi=150)
fig.patch.set_facecolor(CREAM)
ax = plt.subplot(111, polar=True)
ax.set_facecolor(CREAM)
ax.set_theta_offset(np.pi / 2)
ax.set_theta_direction(-1)

for i, (brand, vals) in enumerate(series.items()):
    v = vals + vals[:1]
    ax.plot(ang, v, linewidth=1.6, color=PALETTE[i % len(PALETTE)], label=brand, zorder=3)

# attribute labels (wrapped) around the perimeter
ax.set_xticks(ang[:-1])
ax.set_xticklabels([textwrap.fill(a, 14) for a in attrs], fontsize=8.5, color=INK)
ax.tick_params(axis="x", pad=14)

# radial grid
ax.set_ylim(0, 60)
ax.set_yticks([20, 40, 60])
ax.set_yticklabels(["20", "40", "60"], fontsize=7.5, color="#8A857B")
ax.grid(color="#DDD5C6", linewidth=0.8)
ax.spines["polar"].set_color("#CFC8BA")

ax.legend(loc="center left", bbox_to_anchor=(1.18, 0.5), frameon=False,
          fontsize=9, labelcolor=INK)
fig.suptitle("Brändimielikuvat — profiili (% samaa mieltä, autettu)", x=0.05, y=0.97,
             ha="left", fontsize=14, fontweight="bold", color=INK)
fig.text(0.05, 0.93, "Arvioi mielikuvaasi · n vaihtelee brändeittäin · Marraskuu 2025",
         ha="left", fontsize=9.5, color="#8A857B")

ver = sys.argv[1] if len(sys.argv) > 1 else "r1"
fig.savefig(LAB / f"radar_{ver}.png", facecolor=CREAM, bbox_inches="tight")
fig.savefig(LAB / f"radar_{ver}.svg", facecolor=CREAM, bbox_inches="tight")
print(f"wrote radar_{ver}.png/.svg")
