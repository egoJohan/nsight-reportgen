# Build several slides from AIDED-AWARENESS data — each a DIFFERENT chart style

Data: `chart_lab/original_data.json` = {"categories":[9 providers incl "En mitään näistä"],
"series":{"Toukokuu 2024":[..], "Marraskuu 2024":[..], "Toukokuu 2025":[..], "Marraskuu 2025":[..]}}
(% who know each provider by name; some null). Exclude "En mitään näistä" unless useful. Current
wave = Marraskuu 2025. n≈1001/wave. Numbers EXACT from the data.

Produce ONE slide for EACH of these distinct styles (maximize visual variety — they must look
clearly different from one another and from a plain bar chart):
1. **Slope chart** — Toukokuu 2024 → Marraskuu 2025 per provider (which rose/fell). Label ends.
2. **Dumbbell / connected-dot** — first measured wave vs current wave per provider (change magnitude).
3. **Lollipop chart** — current-wave awareness ranking (dot + stem), sorted.
4. **Bump / rank chart** — each provider's RANK (1=best known) across the 4 waves.
5. **Bar with market-average reference line** — current-wave awareness vs the across-provider average (above/below).
6. **Vertical column chart** — current-wave awareness as columns (different orientation).
Each slide: Finnish key-message title, the chart, metric/base caption. nSight house style
(cream #F4EFE6, teal accents), Liberation Sans/DejaVu (NO Arial). Professional, nothing
overlapping. Output ALL of them into one pptx `work/agent_var_awareness.pptx`, reusable script
`chart_lab/agent_var_awareness.py`. Self-check by rendering. You may install free libs if needed.
