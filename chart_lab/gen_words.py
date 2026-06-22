"""nSight brand-image word list — ranked horizontal bar, sentiment-coloured (improves on a
plain text list / wordcloud: precise counts + instant sentiment read).
Altair/Vega-Lite -> SVG. Run: uv run python chart_lab/gen_words.py <ver>
Data: slide-25 spontaneous brand-image TOP-10 for Attendo (current wave).
"""
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import vl_convert as vlc

LAB = Path(__file__).parent
CREAM = "#F4EFE6"; INK = "#2B2B2B"; FONT = "Liberation Sans"
SENT = {"neg": "#C04A3B", "pos": "#3F7D4E", "neu": "#9C9485"}

# TOP-10 Attendo brand-image words (Marraskuu 2025), word -> (count, sentiment)
WORDS = [
    ("Kallis", 185, "neg"), ("Huono", 75, "neg"), ("Kiireinen", 66, "neg"),
    ("Luotettava", 61, "pos"), ("Hyvä", 60, "pos"), ("Ahne", 57, "neg"),
    ("Iso", 36, "neu"), ("Tunnettu", 32, "pos"), ("Välittävä", 32, "pos"),
    ("Huolehtiva", 27, "pos"),
]
df = pd.DataFrame([{"word": w, "count": c, "sent": s} for w, c, s in WORDS])
order = df.sort_values("count", ascending=False)["word"].tolist()
SENT_LABEL = {"neg": "Kielteinen", "pos": "Myönteinen", "neu": "Neutraali"}
df["Sävy"] = df["sent"].map(SENT_LABEL)

YAXIS = alt.Axis(labelFont=FONT, labelFontSize=13, labelColor=INK, labelFontWeight="bold",
                 ticks=False, domain=False, labelPadding=8)
base = alt.Chart(df).encode(
    y=alt.Y("word:N", sort=order, title=None, axis=YAXIS),
    x=alt.X("count:Q", title=None, scale=alt.Scale(domain=[0, 205]), axis=None),
)
bars = base.mark_bar(height=22, cornerRadiusEnd=3).encode(
    color=alt.Color("Sävy:N",
                    scale=alt.Scale(domain=["Kielteinen", "Myönteinen", "Neutraali"],
                                    range=[SENT["neg"], SENT["pos"], SENT["neu"]]),
                    legend=alt.Legend(orient="bottom", title=None, direction="horizontal",
                                      labelFont=FONT, labelFontSize=12, labelColor=INK,
                                      symbolType="square", symbolSize=150)),
)
labels = base.mark_text(align="left", dx=5, font=FONT, fontSize=11, fontWeight="bold",
                        color=INK).encode(y=alt.Y("word:N", sort=order),
                                          text="count:Q")
chart = alt.layer(bars, labels).properties(
    width=560, height=360,
    title=alt.TitleParams(
        text="Millä kolmella sanalla kuvailisit mielikuvaasi Attendosta?",
        subtitle="Spontaanit maininnat · TOP 10 · kaikki vastaajat, n=863 · Marraskuu 2025",
        font=FONT, fontSize=15, fontWeight="bold", color=INK, anchor="start",
        subtitleFont=FONT, subtitleFontSize=11, subtitleColor="#8A857B", offset=12),
).configure(background=CREAM).configure_view(stroke=None).configure_legend(padding=8)

ver = sys.argv[1] if len(sys.argv) > 1 else "w1"
spec = chart.to_dict()
(LAB / f"words_{ver}.svg").write_text(vlc.vegalite_to_svg(spec))
(LAB / f"words_{ver}.png").write_bytes(vlc.vegalite_to_png(spec, scale=2.0))
print(f"wrote words_{ver}.png/.svg")
