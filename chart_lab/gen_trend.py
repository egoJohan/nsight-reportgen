"""nSight trend archetype — multi-line wave-over-wave, direct end labels (no legend clutter).
Altair/Vega-Lite -> SVG. Run: uv run python chart_lab/gen_trend.py <ver>
Data: aided awareness across the 4 waves (original_data.json).
"""
import json
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import vl_convert as vlc

LAB = Path(__file__).parent
d = json.loads((LAB / "original_data.json").read_text())
WAVES = ["Toukokuu 2024", "Marraskuu 2024", "Toukokuu 2025", "Marraskuu 2025"]
SHORT = {"Toukokuu 2024": "Tou 24", "Marraskuu 2024": "Mar 24",
         "Toukokuu 2025": "Tou 25", "Marraskuu 2025": "Mar 25"}
CREAM = "#F4EFE6"; INK = "#2B2B2B"; FONT = "Liberation Sans"
# show the brands that matter; drop the "none" row
brands = [b for b in d["categories"] if b != "En mitään näistä"]
# emphasise the two leaders, mute the rest for a clean read
LEAD = {"Attendo": "#4E8A4E", "Esperi": "#D9508A"}
MUTE = "#B7AFA0"

rows = []
for i, b in enumerate(d["categories"]):
    if b == "En mitään näistä":
        continue
    for w in WAVES:
        v = d["series"][w][i]
        if v is not None:
            rows.append({"brand": b, "wave": SHORT[w], "wi": WAVES.index(w), "value": v,
                         "lead": b in LEAD})
df = pd.DataFrame(rows)
order = [SHORT[w] for w in WAVES]

color = alt.Color("brand:N",
                  scale=alt.Scale(domain=list(LEAD) + [b for b in brands if b not in LEAD],
                                  range=list(LEAD.values()) + [MUTE] * (len(brands) - len(LEAD))),
                  legend=None)
base = alt.Chart(df).encode(
    x=alt.X("wave:N", sort=order, title=None,
            axis=alt.Axis(labelFont=FONT, labelFontSize=12, labelColor=INK, labelPadding=8,
                          ticks=False, domain=False)),
    y=alt.Y("value:Q", title=None, scale=alt.Scale(domain=[0, 95]),
            axis=alt.Axis(format="d", labelFont=FONT, labelColor="#8A857B", grid=True,
                          gridColor="#E2DBCD", values=[0, 20, 40, 60, 80], domain=False, ticks=False)),
    detail="brand:N",
)
lines_mute = base.transform_filter("datum.lead == false").mark_line(
    strokeWidth=1.5, color=MUTE, opacity=0.7)
lines_lead = base.transform_filter("datum.lead == true").mark_line(strokeWidth=3).encode(color=color)
pts_lead = base.transform_filter("datum.lead == true").mark_point(
    filled=True, size=45).encode(color=color)
# end labels at the last wave
endlab = base.transform_filter(f"datum.wave == '{order[-1]}'").mark_text(
    align="left", dx=8, font=FONT, fontSize=10, baseline="middle").encode(
    text="brand:N",
    color=alt.condition("datum.lead", color, alt.value("#8A857B")),
)
chart = (lines_mute + lines_lead + pts_lead + endlab).properties(
    width=560, height=380,
    title=alt.TitleParams(
        text="Autettu tunnettuus — kehitys aalloittain",
        subtitle="% · n≈1001 / aalto · korostettu: Attendo & Esperi",
        font=FONT, fontSize=15, fontWeight="bold", color=INK, anchor="start",
        subtitleFont=FONT, subtitleFontSize=11, subtitleColor="#8A857B", offset=10),
).configure(background=CREAM).configure_view(stroke=None)

ver = sys.argv[1] if len(sys.argv) > 1 else "t1"
spec = chart.to_dict()
(LAB / f"trend_{ver}.svg").write_text(vlc.vegalite_to_svg(spec))
(LAB / f"trend_{ver}.png").write_bytes(vlc.vegalite_to_png(spec, scale=2.0))
print(f"wrote trend_{ver}.png/.svg")
