"""nSight perception archetype — 100% stacked horizontal bar (general opinion).

Diverging red->green palette so positive reads instantly (improves on the original's
green=bad/blue=good). Cream brand theme. Headless SVG+PNG via vl-convert.
Run: uv run python chart_lab/gen_stacked.py <ver>
"""
import json
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import vl_convert as vlc

LAB = Path(__file__).parent
d = json.loads((LAB / "perception_idx17.json").read_text())
CATS = d["categories"]               # ['Yksityiset...', 'Julkinen...']
SEG_ORDER = ["Erittäin huono", "Huono", "Hyvä", "Erittäin hyvä", "En osaa sanoa"]
POS = ["Hyvä", "Erittäin hyvä"]

PALETTE = {
    "Erittäin huono": "#B23A3A",  # deep red
    "Huono": "#E08A6E",            # coral
    "Hyvä": "#86B36A",             # light green
    "Erittäin hyvä": "#3F7D4E",    # deep green
    "En osaa sanoa": "#BDB6A8",    # warm grey
}
LIGHT_SEG = ["Huono", "Hyvä", "En osaa sanoa"]  # need dark text
CREAM = "#F4EFE6"; INK = "#2B2B2B"; FONT = "Liberation Sans"

# long form + short display names for the y axis
SHORT = {"Yksityiset palveluntarjoajat": "Yksityiset", "Julkinen palveluntarjoaja": "Julkinen"}
rows, pos_rows = [], []
for ci, cat in enumerate(CATS):
    for seg in SEG_ORDER:
        rows.append({"cat": SHORT.get(cat, cat), "segment": seg, "value": d["series"][seg][ci]})
    pos_rows.append({"cat": SHORT.get(cat, cat),
                     "pos": sum(d["series"][s][ci] for s in POS)})
df = pd.DataFrame(rows); pdf = pd.DataFrame(pos_rows)
catorder = [SHORT.get(c, c) for c in CATS]

df["order"] = df["segment"].map({s: i for i, s in enumerate(SEG_ORDER)})
YAXIS = alt.Axis(labelFont=FONT, labelFontSize=13, labelColor=INK, labelFontWeight="bold",
                 ticks=False, domain=False, labelPadding=8)
XSCALE = alt.Scale(domain=[0, 122])  # headroom for the right-side callout

bars = alt.Chart(df).mark_bar(height=46, stroke=CREAM, strokeWidth=1.5).encode(
    y=alt.Y("cat:N", sort=catorder, title=None, axis=YAXIS),
    x=alt.X("value:Q", stack="zero", title=None, axis=None, scale=XSCALE),
    order=alt.Order("order:Q", sort="ascending"),
    color=alt.Color("segment:N", sort=SEG_ORDER,
                    scale=alt.Scale(domain=SEG_ORDER, range=[PALETTE[s] for s in SEG_ORDER]),
                    legend=alt.Legend(orient="bottom", title=None, direction="horizontal",
                                      labelFont=FONT, labelFontSize=12, labelColor=INK,
                                      symbolType="square", symbolSize=150)),
)

labels = alt.Chart(df).mark_text(font=FONT, fontSize=12, fontWeight="bold").encode(
    y=alt.Y("cat:N", sort=catorder),
    x=alt.X("value:Q", stack="zero", bandPosition=0.5, scale=XSCALE, axis=None),
    order=alt.Order("order:Q", sort="ascending"),
    detail="segment:N",
    text=alt.Text("value:Q", format="d"),
    color=alt.condition(
        "indexof(['Huono','Hyvä','En osaa sanoa'], datum.segment) >= 0",
        alt.value(INK), alt.value("white")),
)

# Right-side "Myönteinen X %" callout, placed just past the 100-wide bar (x=102).
pdf["x"] = 102
pdf["label"] = "▸ " + pdf["pos"].astype(int).astype(str) + " % myönt."
pos_lab = alt.Chart(pdf).mark_text(align="left", font=FONT, fontSize=13, fontWeight="bold",
                                   color="#3F7D4E").encode(
    y=alt.Y("cat:N", sort=catorder),
    x=alt.X("x:Q", scale=XSCALE, axis=None),
    text=alt.Text("label:N"),
)

chart = alt.layer(bars, labels, pos_lab).properties(
    width=760, height=190,
    title=alt.TitleParams(
        text="Mikä on yleinen käsityksesi tuntemistasi hoivapalveluita tarjoavista yrityksistä?",
        subtitle="Yleinen käsitys (%) · n=1001 · vihreä = myönteinen",
        font=FONT, fontSize=15, fontWeight="bold", color=INK, anchor="start",
        subtitleFont=FONT, subtitleFontSize=11, subtitleColor="#8A857B", offset=12),
).configure(background=CREAM).configure_view(stroke=None).configure_legend(padding=8)

ver = sys.argv[1] if len(sys.argv) > 1 else "s1"
spec = chart.to_dict()
(LAB / f"stacked_{ver}.svg").write_text(vlc.vegalite_to_svg(spec))
(LAB / f"stacked_{ver}.png").write_bytes(vlc.vegalite_to_png(spec, scale=2.0))
print(f"wrote stacked_{ver}.png/.svg")
