# GENERIC slide description (applies to EVERY slide)

This is the shared brief the builder agent reads for **every** slide. It is combined with a
short **slide-specific** description (the metric, data, headline, chart intent for that one
slide). Generic = the "how"; slide-specific = the "what".

## Product & audience
nSight market-research deck (Finnish). Audience = the client's leadership. Output: clean,
professional, print-grade slides that a research firm could deliver to an end customer.

## Non-negotiable rules
1. **Numbers are exact and come from the data** — read them in code; never type or estimate
   them. Compute any derived figures (change vs previous wave, net, top-2-box, averages) in
   code and state how.
2. **Never fabricate.** If the slide-specific description asks for a wave/segment that is not in
   the data, say so and render what genuinely exists.
3. **Match the source's information density:** when the data has multiple waves, show the metric
   across **all waves** AND the **change-vs-previous** figure — do not collapse to one wave.
4. **Numbers never come from an LLM.**

## House style
- Background cream `#F4EFE6`; teal accents `#2F6F8F` / `#13615E`; ink text `#2B2B2B`; muted
  `#8A857B`. Font **Liberation Sans** or **DejaVu Sans** (NEVER "Arial" — it renders blank in
  the headless renderer).
- Each slide: a **Finnish key-message title** (the takeaway, not the question) + a short
  sub-line; a teal section sub-label (e.g. "AUTETTU TUNNETTUUS · osuus vastaajista (%)"); the
  survey **question** as a footer caption; and the **base n** bottom-right.
- Diverging perception palette: red = negative → green/teal = positive; grey = "En osaa sanoa".
- Sort items best→worst by the current wave; emphasise the current wave / focus brand (bold,
  darker); de-emphasise the rest. Hold opt-out rows ("En mitään näistä") below a separator.

## Quality bar
Vector (SVG) where possible; high-res PNG otherwise. **Nothing overlaps**; every value legible.
A change column / sparkline / trend where waves exist. 16:9, 13.333×7.5 in.

## Output & reuse
Write a reusable, parameterised generator `chart_lab/<name>.py` (Vega-Lite/altair+vl_convert for
cartesian charts; matplotlib for polar/bespoke), save a high-res chart, compose the slide with
python-pptx → `work/<name>.pptx`, then self-check by rendering (soffice→pdftoppm) and fix any
overlap before reporting.

## Engineering gotchas (avoid up front)
- Layered Vega-Lite: only ONE layer declares each axis (others `axis=None`) or labels drop.
- d3 number formats can't embed literal text — precompute label strings.
- Diverging bars need an x-domain spanning negatives + an explicit zero line, or negative bars
  don't draw.
- Many series (e.g. 8-brand radar) → small multiples, not overlay.

---
*The builder agent receives: THIS generic description + ONE slide-specific description below.*
