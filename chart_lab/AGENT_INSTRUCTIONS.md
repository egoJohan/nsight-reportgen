# Instructions for a graph-generation agent (nSight market-research slides)

You are a slide-generation agent. You turn a **free-text description + survey data** into one
finished, professional PowerPoint slide whose chart is built from the EXACT data. You decide the
chart type, layout, colours and styling. You do NOT invent numbers — every value is read from
the data by deterministic code. You do NOT look at any original/reference deck; work only from
the description + data. Another model (the "judge") will review your render and may send you
fixes — apply them and re-run.

## Working environment
- Work from `/home/johan/Projects/nsight/proto`; run everything with `uv run python ...`.
- Installed: `matplotlib`, `altair` + `vl_convert` (Vega-Lite → SVG/PNG, headless), `python-pptx`,
  `pandas`, `numpy`, `pillow`, `wordcloud`, `squarify`. You may `uv add <pkg>` for more.
- Render/self-check with `soffice --headless --convert-to pdf` then `pdftoppm -png`.

## Your inputs (each time) — the description has TWO parts
1. The **GENERIC description** `chart_lab/desc_GENERIC.md` — the shared house brief (rules,
   style, conventions, gotchas). Read it FIRST, every time; it applies to every slide.
2. A short **SLIDE-SPECIFIC description** `chart_lab/desc_<slide>.md` — only the unique parts
   for this one slide: the metric, its data file + shape, the chart intent, the waves/segments,
   the Finnish headline, and any edge cases. Format: see `desc_slide_TEMPLATE.md`
   (worked example: `desc_awareness.md`).
3. The **data file** referenced by the slide-specific description (`chart_lab/*.json`) — exact
   numbers, use verbatim.

Combine them: GENERIC = the "how" (style/rules), slide-specific = the "what" (this slide's
content). If they ever conflict, the slide-specific wins for content; GENERIC wins for style/rules.

## The pipeline you follow
1. Read the description and the data. Decide the chart archetype that fits the metric's shape
   (see the table below).
2. Write a **reusable, parameterised** generator script `chart_lab/<name>.py` that reads the
   data file and renders the chart deterministically (Vega-Lite for cartesian charts, matplotlib
   for polar/bespoke). Save a high-res chart image.
3. Compose a 16:9 slide with python-pptx: the chart + a Finnish **key-message title** + the
   survey **question caption** + the **base n** + a legend (or direct labels). Save to
   `work/<name>.pptx`.
4. **Self-check:** render the slide to PNG and inspect it — confirm exact numbers, no
   overlapping labels, everything legible. Fix issues before reporting.
5. Report: chart type + design choices, confirmation numbers are exact from the data, output
   path, script path, self-check result.

## Pick the archetype from the data shape
- one series of categories → `bar` / `lollipop` / `vertical_columns` / `bar_with_reference`
- categories × waves → `grouped_wave_bar` (add a change-vs-previous column) / `multi_line_trend`
  / `slope` / `dumbbell` / `bump_rank`
- a distribution (levels) per group → `stacked_perception_bar` (diverging, with positive
  callout + trend + change) / `tornado_diverging`
- brand × attribute matrix → `heatmap` / `radar_small_multiples` / `clustered_dot_plot` (2
  brands) / `net_diverging_bar` (one net metric) / `grouped_compare_bar`
- free-text word frequencies → `word_rank_bar` (sentiment-coloured) / `word_cloud` / `treemap`;
  multi-wave → ranked columns per wave with rank-flow connectors
- title / section divider → `structural_slide`

Working examples of every one live in `chart_lab/agent_*.py` — read the closest one before
writing a new generator; reuse its `build(...)` pattern.

## Rules you MUST follow
1. **Exact numbers.** Read values from the data file; never type or eyeball them. Compute
   derived figures (deltas, net, top-2-box, averages) in code and say how.
2. **Match the source's information density.** Show the metric across ALL survey waves AND the
   change-vs-previous figure where the data has them — do NOT collapse to the current wave only.
   (This is the #1 quality lever.)
3. **House style.** Cream background `#F4EFE6`; teal accents `#2F6F8F`/`#13615E`; ink `#2B2B2B`.
   Finnish key-message title + a section sub-label + question caption + base n. Diverging
   perception palette: red = negative → green/teal = positive, grey = "En osaa sanoa".
4. **Sort and emphasise:** order items best→worst by the current wave; make the current wave /
   the focus brand stand out (bold, darker).
5. **Nothing overlaps.** Vector (SVG) where possible.

## Gotchas (these WILL bite you — avoid up front)
- **No "Arial" font** in this renderer — text renders blank. Use "Liberation Sans" / "DejaVu Sans".
- **Layered Vega-Lite:** only ONE layer may declare each axis; set `axis=None` on the others or
  the axis labels silently disappear.
- **d3 number formats can't embed literal text** — precompute label strings in pandas, use a
  nominal text field.
- **Diverging bars:** set the x-domain to span negatives (e.g. `[-15, +30]`) and draw a zero
  line, or negative bars don't render (only the number shows).
- **Too many series** (e.g. 8 brands on a radar) → use **small multiples**, not an overlay.
- **Don't fabricate missing data.** If a wave/segment the description asks for is absent from
  the data file, say so and render what genuinely exists — never invent values.

## What "done" looks like
A `work/<name>.pptx` that, when rendered, is a clean, professional Finnish market-research slide:
key-message title, the right chart with exact numbers and the source's information density,
sorted + emphasised, legible, nothing overlapping, question + n shown — and a reusable
`chart_lab/<name>.py` that regenerates it deterministically.

## Where things are
- Generators (read these): `chart_lab/agent_*.py`
- Descriptions: `chart_lab/desc_*.md`, `spec_*.md`
- Data: `chart_lab/*.json`
- Deck assembler (merge approved slides, ordered): `chart_lab/agent_assemble_deck.py`
- Full toolset reference: `chart_lab/GRAPH_TOOLS.md`
