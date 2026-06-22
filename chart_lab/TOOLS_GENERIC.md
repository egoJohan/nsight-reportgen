# Generic chart toolset (product-agnostic) — for egoHive

Reusable chart tools. Nothing client-specific is baked in: **palette, fonts, language, and data
are passed in** (a `theme` + the data). nSight is just one theme + one set of data files.

## Common contract (every chart tool)
- **Inputs:** `data` (per the tool's shape), `theme` (schema below), and labels: `title`,
  `subtitle`, `caption` (the source question/metric), `base_n`, `value_format` (e.g. `"%d %"`).
- **Layout / output params (NOT theme — passed per call, with defaults):**
  `width`, `height` (chart/slide size in inches; default 13.333 × 7.5 = 16:9),
  `dpi` / `scale` (raster export resolution; default scale 2),
  `font_scale` (or `base_font_pt`; default 1.0 — multiplies all font sizes so a smaller/larger
  graph stays legible). The **font family** comes from `theme.font`; the **sizes** scale here.
- **Common options:** `sort` (by which dimension), `emphasis` (focus series/period),
  `change_column` (show period-over-period delta), `output` (`svg`|`png`|`pptx_slide`).
- **Behaviour:** numbers read from `data` only (never generated); styling from `theme` only;
  deterministic; nothing overlapping; vector where possible.

## theme schema (the only place client identity lives)
```json
{
  "background": "#F4EFE6", "accent": "#2F6F8F", "accent_dark": "#13615E",
  "ink": "#2B2B2B", "muted": "#8A857B",
  "palette": ["#2F6F8F","#D9508A","#E29B2E","#4E8A4E","#7E5BA6","#C04A3B","#3FA9A0","#6B7C45"],
  "diverging": {"neg": ["#B23A3A","#E08A6E"], "pos": ["#86B36A","#3F7D4E"], "neutral": "#BDB6A8"},
  "ramp": ["#CFE6E2","#8FBFBC","#3F8C86","#13615E"],
  "font": "Liberation Sans", "locale": "fi", "currency": null
}
```
The font must exist in the render environment.

## Chart tools (generic)
| tool_id | purpose | data shape |
|---|---|---|
| `chart_bar` | ranked single-series bar | `{categories:[…], values:[…]}` |
| `chart_columns` | vertical columns | `{categories, values}` |
| `chart_lollipop` | ranked dot+stem | `{categories, values}` |
| `chart_bar_with_reference` | bars vs a reference/avg line | `{categories, values, reference?}` |
| `chart_grouped_period_bar` | categories × periods, sorted, emphasis, optional change col | `{categories, series:{period:[…]}}` |
| `chart_line_trend` | metric over periods, leader-emphasis, direct end-labels | `{categories, series:{period:[…]}}` |
| `chart_slope` | two-period change per item | `{categories, series:{A,B}}` |
| `chart_dumbbell` | first vs last per item + delta | `{categories, series:{first,last}}` |
| `chart_bump_rank` | rank over periods | `{categories, series:{period:[…]}}` |
| `chart_stacked_100_diverging` | distribution per group, neg→pos, positive callout | `{categories:[group], levels:{level:[per group]}, level_order:[…]}` |
| `chart_tornado` | butterfly: neg left / pos right of centre | same as above |
| `chart_heatmap` | entity × attribute matrix | `{rows:[entity], cols:[attr], values:[[…]]}` |
| `chart_dot_plot` | two entities head-to-head per attribute | `{categories:[attr], a:[…], b:[…], a_name, b_name}` |
| `chart_net_diverging_bar` | one net metric per entity, zero centre line | `{categories:[entity], values:[…]}` (may be negative) |
| `chart_grouped_compare_bar` | few entities × top-N attributes | `{categories:[attr], series:{entity:[…]}}` |
| `chart_radar_small_multiples` | one mini-radar per entity vs the average | `{axes:[attr], series:{entity:[…]}}` |
| `chart_ranked_bar_categorised` | ranked bar coloured by a category (e.g. sentiment) | `{items:[{label,value,category}]}` + `category_colors` |
| `chart_word_cloud` | items sized by value, coloured by category | `{items:[{label,value,category}]}` |
| `chart_treemap` | items as area-proportional tiles, coloured by category | `{items:[{label,value,category}]}` |
| `chart_donut` | 2–n slice share | `{slices:{label:value}}` |
| `structural_slide` | title / section divider (no chart) | `{kind, heading, index?, total?}` |

Engines: Vega-Lite (+vl_convert) for cartesian; matplotlib for polar/bespoke (radar, treemap,
diverging, donut); `wordcloud`/`squarify` for those two. All free, headless, deterministic.

## Supporting tools (generic)
- `slide_compose(chart_asset, title, caption, base_n, theme) -> pptx_slide`
- `render_to_image(pptx) -> png[]` (LibreOffice headless → pdftoppm) — for the verify loop
- `judge(png, [reference_png]) -> {issues, verdict}` (vision review)
- `assemble_deck(slides[], order) -> pptx` (deep-copy merge, order = source of truth)

## egoHive `Tool` mapping
Each chart tool → one `Tool` plugin: `tool_id` as above; `definition.parameters` = `data` +
`theme` + the label/option fields + `output`; `execute(parameters, context)` runs the
deterministic generator and returns the asset. No LLM inside. The agent (system prompt =
`AGENT_GENERIC.md`) selects the tool from the data shape, fills params (incl. the active theme),
writes the key-message prose, and calls `assemble_deck`.

## How client identity stays out of the tools
- **Style** → `theme` (e.g. `theme_nsight.json`). Swap the theme for another client.
- **Language** → `theme.locale` + the label/caption strings in the slide spec.
- **Data** → passed in (or a datahive query). The tools never reference a specific dataset.
