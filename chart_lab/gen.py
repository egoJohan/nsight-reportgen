"""nSight aided-awareness chart — Vega-Lite/Altair archetype, headless SVG+PNG export.

Iterate on THEME/encoding here; run `uv run python chart_lab/gen.py <version>`.
Plots the original chart's exact data so the comparison is purely visual quality.
"""
import json
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import vl_convert as vlc

LAB = Path(__file__).parent
data = json.loads((LAB / "original_data.json").read_text())

WAVES = ["Toukokuu 2024", "Marraskuu 2024", "Toukokuu 2025", "Marraskuu 2025"]
CURRENT = "Marraskuu 2025"

# nSight-ish palette (teal / magenta / amber / green), current wave = strong green
PALETTE = {
    "Toukokuu 2024": "#2F9C95",
    "Marraskuu 2024": "#D9508A",
    "Toukokuu 2025": "#E9A23B",
    "Marraskuu 2025": "#4E8A4E",
}
CREAM = "#F4EFE6"
INK = "#2B2B2B"

# long form
rows = []
for i, brand in enumerate(data["categories"]):
    for wave in WAVES:
        v = data["series"].get(wave, [None] * 99)[i]
        if v is not None:
            rows.append({"brand": brand, "wave": wave, "value": v})
df = pd.DataFrame(rows)

# brand order by current wave desc
order = (df[df.wave == CURRENT].sort_values("value", ascending=False)["brand"].tolist())

FONT = "Liberation Sans"

base = alt.Chart(df).encode(
    y=alt.Y("brand:N", sort=order, title=None,
            axis=alt.Axis(labelFont=FONT, labelFontSize=12, labelColor=INK, labelPadding=6,
                          ticks=False, domain=False)),
    yOffset=alt.YOffset("wave:N", sort=WAVES),
)

bars = base.mark_bar(height=alt.RelativeBandSize(0.84), cornerRadiusEnd=2).encode(
    x=alt.X("value:Q", title=None, scale=alt.Scale(domain=[0, 100]),
            axis=alt.Axis(format="d", labelFont=FONT, labelFontSize=11, labelColor="#8A857B",
                          values=[0, 20, 40, 60, 80, 100], title="%", titleColor="#8A857B",
                          grid=True, gridColor="#E2DBCD", domain=False, ticks=False)),
    color=alt.Color("wave:N", sort=WAVES,
                    scale=alt.Scale(domain=WAVES, range=[PALETTE[w] for w in WAVES]),
                    legend=alt.Legend(orient="bottom", title=None, direction="horizontal",
                                      labelFont=FONT, labelFontSize=11, labelColor=INK,
                                      symbolType="square", symbolSize=130)),
)

# data labels on EVERY wave (completeness, like the original), consistent dark ink for
# legibility; current wave bold so "this wave" reads instantly. Two layers = per-wave weight.
_lab = dict(align="left", dx=3, font=FONT, fontSize=9, baseline="middle")
labels_prior = base.transform_filter(alt.datum.wave != CURRENT).mark_text(
    **_lab, color="#7A7466").encode(x="value:Q", text=alt.Text("value:Q", format="d"))
labels_current = base.transform_filter(alt.datum.wave == CURRENT).mark_text(
    **_lab, color=INK, fontWeight="bold").encode(x="value:Q", text=alt.Text("value:Q", format="d"))
labels = labels_prior + labels_current

chart = (bars + labels).properties(
    width=820, height=430,
    title=alt.TitleParams(
        text="Mitä seuraavista hoivapalveluiden tarjoajista tunnet vähintään nimeltä?",
        subtitle="Autettu tunnettuus (%) · n=1001",
        font=FONT, fontSize=15, fontWeight="bold", color=INK, anchor="start",
        subtitleFont=FONT, subtitleFontSize=11, subtitleColor="#8A857B", offset=14,
    ),
).configure(background=CREAM).configure_view(stroke=None).configure_axis(
    labelFont=FONT
).configure_legend(padding=6, rowPadding=4)

ver = sys.argv[1] if len(sys.argv) > 1 else "v1"
spec = chart.to_dict()
(LAB / f"{ver}.svg").write_text(vlc.vegalite_to_svg(spec))
png = vlc.vegalite_to_png(spec, scale=2.0)
(LAB / f"{ver}.png").write_bytes(png)
print(f"wrote {ver}.svg / {ver}.png")
