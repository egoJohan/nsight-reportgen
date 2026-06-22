# Build several slides from BRAND-IMAGE / ATTRIBUTE data — each a DIFFERENT style

Data: `chart_lab/radar_0.json` = {"categories":[14 attributes], "series":{"Attendo, n=863":[14
ints], ... 8 brands}}. Values = % prompted agreement per attribute. Negative attributes: "Ahne",
"Välinpitämätön" (low = good). Numbers EXACT.

Produce ONE slide for EACH distinct style (clearly different layouts):
1. **Heatmap** — brands (rows) × 14 attributes (columns), colour = % agreement; readable, sorted sensibly.
2. **Clustered dot plot** — Attendo vs Esperi head-to-head across the 14 attributes (two dots per row).
3. **Net-image diverging bar** — per brand: average of positive attributes minus the negative ones, bars diverging left/right from a centre line (who has the most positive net image).
4. **Grouped horizontal bar** — top ~6 attributes compared across 3 leading brands (Attendo, Esperi, Onnikodit).
Each slide: Finnish key-message title, chart, metric/base caption (n varies by brand), nSight
house style, Liberation Sans/DejaVu (NO Arial), nothing overlapping. Output to one pptx
`work/agent_var_image.pptx`, reusable script `chart_lab/agent_var_image.py`. Self-check by rendering.
