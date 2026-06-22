# How the graphs are created — technologies & techniques

Pure technical reference for the chart tools: which technologies are used and how each graph
type is built. No agents, no orchestration — these are the building blocks for producing the
graphs.

## Technology stack
- **Python 3.11+**, env via **uv**.
- **Altair → Vega-Lite**, rendered headless by **vl-convert** (`vl_convert`, a self-contained
  Rust binary) → **SVG** (vector) or PNG. Used for cartesian charts (bars, stacked, lines).
- **matplotlib** → SVG/PNG. Used for polar/bespoke charts (radar, treemap base, diverging,
  donut, dumbbell, slope, bump, heatmap).
- **wordcloud** (word clouds), **squarify** (treemaps).
- **pandas / numpy** — data handling + all derived math (deltas, net, top-box, averages).
- **python-pptx** — place a chart image onto a 16:9 slide and assemble/merge decks.
- **LibreOffice** (`soffice --headless`) + **poppler** (`pdftoppm`) — rasterise a slide/deck to
  PNG for visual checking. **ImageMagick** (`montage`) — side-by-side comparison images.
- **Pillow** — image sizing for embedding.
- Fonts: **Liberation Sans / DejaVu Sans** (system fonts). NOT "Arial" — absent in the headless
  renderer, so text renders blank.

## Conventions (apply to all tools)
- **Numbers are read from the data and computed in code** — never typed/estimated.
- **Styling is parameterised** (a theme dict: `background, accent, ink, muted, palette[],
  diverging{neg[],pos[],neutral}, ramp[], font, locale`) — not hardcoded, so the same tool
  serves any look. Output **SVG** where possible (vector, print-grade); else high-res PNG.
- Size 16:9 (13.333×7.5 in). Sort by the focus dimension; emphasise the focus series/period.

---

## How each graph type is created

### Cartesian (Altair / Vega-Lite → vl_convert)
- **Grouped bar (multi-series)** — `mark_bar` with `y=category`, `x=value`, `yOffset=series`
  for grouping; `color` scale = palette. Sort the y domain by the focus series. Data labels =
  a `mark_text` layer sharing the encoding. Optional change column = a separate text layer at
  fixed x past the axis.
- **100% stacked bar** — `mark_bar` with `x` `stack="normalize"` (or `stack="zero"` if values
  already sum to 100), `color=level` with an ordered scale; in-segment labels via a `mark_text`
  with `x` `bandPosition=0.5`; label colour conditional on segment (light on dark fills).
- **Line trend** — `mark_line` + `mark_point`; emphasise leaders (thicker/coloured), mute the
  rest (thin grey); **direct end-labels** via a `mark_text` filtered to the last period instead
  of a legend.
- **Columns** — same as bar with axes swapped (`x=category, y=value`).

### matplotlib (polar / bespoke)
- **Radar (small multiples)** — a grid of `subplot(polar=True)`; angles = `linspace(0,2π,N)`;
  per entity `ax.plot/fill` the closed loop; a dashed average loop as reference; numbered
  spokes (`set_xticklabels(1..N)`) + a separate numbered key (long labels don't fit on spokes).
- **Heatmap** — `imshow`/`pcolormesh` of an entity×attribute matrix with a sequential colormap
  built from the theme `ramp`; annotate each cell (`ax.text`), white text on dark cells;
  negative attributes grouped behind a divider.
- **Dot plot** — per row a grey connector (`hlines`) + two `scatter` dots (two entities);
  value labels offset to avoid collision.
- **Net diverging bar** — `barh` where the **x-domain spans negatives** (e.g. `[-15,30]`) with
  an explicit `axvline(0)`; positive bars right (teal), negative left (red); labels at bar ends.
- **Tornado / butterfly** — stack negatives leftward from 0 and positives rightward (negate the
  negative widths); group totals as callouts; "don't know" parked separately.
- **Slope** — two x positions; one `plot` per item connecting (A,B); end labels; colour by
  rose/fell.
- **Dumbbell** — per row an open dot (first) + filled dot (last) joined by a line; delta label.
- **Lollipop** — `hlines` (stem) + `scatter` (dot) per item, sorted.
- **Bump/rank** — compute rank per period; `plot` each item across periods with an **inverted
  y-axis** (1 at top); labels at right.
- **Bar with reference line** — `barh` + an `axvline`/`axhline` at the average; bars above the
  line accented, below muted.
- **Donut** — `pie` with `wedgeprops=dict(width=0.4)`; % in the ring, labels outside.
- **Ranked bar coloured by category** — `barh` sorted by value, bar colour by a category map
  (e.g. sentiment → diverging palette); count labels at bar ends; category legend.

### Frequency-of-text
- **Word cloud** — `wordcloud` lib with `relative_scaling` (size ∝ count) + a `color_func`
  mapping each word to its category colour; fixed `random_state` for reproducibility.
- **Treemap** — `squarify.plot` with sizes ∝ value, colours by category, word+count per tile.

### Non-chart
- **Structural slide (title / divider)** — drawn directly with python-pptx shapes/text on the
  themed background (accent bar, heading, optional faint section numeral). No chart.

---

## Rendering & embedding (turning a chart into a slide)
- Vega-Lite: `vl_convert.vegalite_to_svg(spec)` / `vegalite_to_png(spec, scale=2)`.
- matplotlib: `fig.savefig(path, ...)` to `.svg` / high-dpi `.png`.
- Slide: python-pptx — blank 16:9, themed background, `add_picture(chart)`, plus text boxes for
  the key-message title, section label, source caption, and base n.
- Deck: python-pptx has no native merge — deep-copy each `<p:sld>` part + its relationship graph
  + media into one deck, ordered by an explicit slide list (the order is the source of truth).

## Verify (rasterise to look at the result)
`soffice --headless --convert-to pdf <file>` then `pdftoppm -png -r <dpi> <pdf>` → inspect the
PNG (geometry-based or vision check) for exact values + no overlapping labels.

## Technical gotchas (must-handle)
- Use an **installed font** (Liberation/DejaVu), never "Arial" (blank text).
- **Layered Vega-Lite:** only ONE layer may declare each axis (others `axis=None`) or labels
  silently drop.
- **d3 number formats can't embed literal text** — precompute label strings, plot as a nominal
  field.
- **Diverging bars** need the x-domain to include negatives + an explicit zero line, or negative
  bars don't render.
- **Many series** (e.g. 8-entity radar) → **small multiples**, not an overlay.
- **Deck merge:** maintain a partname set to avoid layout/media collisions; a stale slide-order
  list silently reverts swapped slides.

## Working implementations (one file per chart type, deterministic)
`/home/johan/Projects/nsight/proto/chart_lab/agent_*.py` — each reads a data file (examples:
`/home/johan/Projects/nsight/proto/chart_lab/*.json`) and produces the chart + slide. Reusable
`build(...)` per script. Generic data shapes + a `theme` are documented in `TOOLS_GENERIC.md`.
```
