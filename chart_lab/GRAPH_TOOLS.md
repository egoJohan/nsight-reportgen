# nSight graph-production toolset — for egoHive agentic workflows

A description of how the slides/graphs were produced, written as a **toolset** you can lift
into egoHive: a set of deterministic chart tools + supporting tools, plus the orchestration
pattern that drives them. Numbers are always computed/read by deterministic code — never by an
LLM. The LLM's only job is orchestration + prose.

---

## 1. The pipeline (how a graph slide is made)

```
free-text DESCRIPTION  +  DATA (json/SPSS)
        │
        ▼  (agent reads the description, picks the right chart tool, fills its params)
   chart tool  ──►  deterministic Python (matplotlib OR Vega-Lite/altair+vl_convert)
        │            renders a vector/PNG chart from the EXACT data
        ▼
   slide-compose tool  ──►  python-pptx: chart image + key-message title + caption + n  → 1 .pptx slide
        │
        ▼
   render-to-image tool  ──►  LibreOffice headless → PNG  (so the result can be SEEN)
        │
        ▼
   JUDGE (vision)  ──►  data coverage / chart-style / information density / overlaps
        │  (fixes fed back to the tool; loop, typically 1 iteration)
        ▼
   assemble-deck tool  ──►  merge approved slides into one ordered .pptx
```

Roles: the **agent** chooses the tool + fills params from the description; the **tools** are
deterministic; the **judge** (a vision step) accepts/rejects and feeds fixes back.

---

## 2. Chart tools (the core deliverable)

Each is a deterministic generator. Listed as: **tool — purpose — input data contract — key
params — engine — source script**. All share the house-style + exact-numbers contract (§4).

| Tool | Purpose | Input data contract | Engine | Script |
|---|---|---|---|---|
| `grouped_wave_bar` | brand metric across waves, sorted, current-wave emphasis, optional **change column** | `{categories:[item], series:{wave:[v…]}}` (nulls ok) | Vega-Lite / mpl | `agent_dense_awareness.py`, `agent_build_awareness.py` |
| `stacked_perception_bar` | 100%-stacked diverging (neg→pos) per group, positive callout, optional **positive-trend sparkline + change** | `{categories:[group], current_levels:{level:[per group]}, positive_trend?, change_vs_prev?}` | mpl | `agent_dense_opinion.py`, `agent_build_opinion.py` |
| `radar_small_multiples` | one mini-radar per brand vs the all-brand average, numbered spokes + key | `{categories:[attr×14], series:{brand:[v…]}}` | matplotlib polar | `agent_build_radar.py`, `agent_radar_sm` |
| `multi_line_trend` | metric over waves, leaders emphasised, **direct end-labels** (no legend) | `{categories:[item], series:{wave:[v…]}}` | Vega-Lite / mpl | `agent_build_trend.py` |
| `attribute_bar` | sorted horizontal bar of N attributes for one brand, negatives flagged (low=good), optional **4-wave ramp + change** | `{attribute_categories:[…], series_by_wave:{wave:[v…]}}` | matplotlib | `agent_dense_brandimage.py`, `agent_build_brandimage.py` |
| `word_rank_bar` / `word_waves` | TOP-N words by count, sentiment-coloured; multi-wave columns w/ rank connectors | `{waves:{wave:[[word,count]]}, sentiment:{word:label}}` | matplotlib | `agent_dense_words.py` |
| `heatmap` | brand × attribute matrix, sequential colormap, negatives grouped + flagged | `{categories:[attr], series:{brand:[v…]}}` | matplotlib | `agent_var_image.py` (#1) |
| `clustered_dot_plot` | two brands head-to-head per attribute (gap line) | same as heatmap, pick 2 brands | matplotlib | `agent_var_image.py` (#2) |
| `net_diverging_bar` | one net metric per brand, zero centre line, neg bars left (red) / pos right (teal) | `{brand: net_value}` (derived) | matplotlib | `agent_var_image.py` (#3) |
| `grouped_compare_bar` | top-N attributes × few brands, grouped | subset of heatmap data | Vega-Lite / mpl | `agent_var_image.py` (#4) |
| `slope_chart` | two-point change per series, end labels | `{categories:[item], series:{waveA, waveB}}` | matplotlib | `agent_var_awareness.py` (#1) |
| `dumbbell` | first vs last value per item + delta | `{categories, series:{first,last}}` | matplotlib | `agent_var_awareness.py` (#2) |
| `lollipop` | ranked dots+stems (one wave) | `{categories, values}` | matplotlib | `agent_var_awareness.py` (#3) |
| `bump_rank_chart` | rank (1..n) over waves | `{categories, series:{wave:[v…]}}` (ranked in code) | matplotlib | `agent_var_awareness.py` (#4) |
| `bar_reference_line` | bars vs a reference/avg line | `{categories, values, reference?}` | matplotlib | `agent_var_awareness.py` (#5) |
| `vertical_columns` | columns (orientation variety) | `{categories, values}` | matplotlib | `agent_var_awareness.py` (#6) |
| `word_cloud` | words sized by count, sentiment-coloured | `{words:[{word,count,sentiment}]}` | `wordcloud` | `agent_var_wordsop.py` (#1) |
| `treemap` | words as area-proportional sentiment tiles | same | `squarify`+mpl | `agent_var_wordsop.py` (#2) |
| `tornado_diverging` | butterfly: negatives left / positives right of centre | `{categories, current_levels}` | matplotlib | `agent_var_wordsop.py` (#3) |
| `structural_slide` | title / section-divider (no chart) | `{kind, heading, index?, total?}` | python-pptx | `agent_build_structural.py` |

→ **~20 distinct chart archetypes.** Each script has a parameterised `build(...)` and is
deterministic (same data in → same chart out). Vega-Lite is used for cartesian charts (clean
text-measured auto-layout); matplotlib for polar/bespoke (radar, treemap, diverging).

## 3. Supporting tools

| Tool | Purpose | How |
|---|---|---|
| `slide_compose` | place a chart image + Finnish key-message title + question caption + base-n onto a 16:9 slide | python-pptx (`build_deck.py` pattern) |
| `render_to_image` | rasterise a `.pptx`/slide so it can be judged | `soffice --headless --convert-to pdf` → `pdftoppm` PNG |
| `judge` | vision check: data coverage, chart-style fidelity, information density, overlaps; compare vs an original | a vision-capable model viewing the PNG |
| `assemble_deck` | merge approved per-slide `.pptx` into one ordered deck, preserving each slide's chart/media | deep-copy `<p:sld>` + rel graph + media into a blank 16:9 deck (`agent_assemble_deck.py`); ordered by a `(file, slide#)` list |

---

## 4. Shared contracts (every chart tool obeys these)

1. **Exact numbers.** Values are read from the data file by code; never typed by the model.
   Derived figures (deltas, net, top-2-box, averages) are computed in code and documented.
2. **House style.** Cream background `#F4EFE6`, teal accent `#2F6F8F`/`#13615E`, ink `#2B2B2B`;
   Finnish key-message title + section sub-label + question caption + base n; legend or direct
   labels. Diverging perception palette = red(neg)→green/teal(pos), grey = "En osaa sanoa".
3. **Vector where possible** (SVG via vl-convert) for print-grade output; high-res PNG fallback.
4. **Information density to match the source:** show the metric across **all survey waves** +
   the **change-vs-previous** figure (this was the single biggest quality lever vs collapsing
   to the current wave).

---

## 5. Mapping to egoHive `Tool` plugins

Each chart tool maps 1:1 onto egoHive's `Tool` contract:

- `tool_id` = e.g. `nsight_chart_grouped_wave_bar`.
- `definition.parameters` (JSON schema) = the **data** (per the contract above) + **style
  options** (title, question, base_n, emphasis_series, show_change, palette) + **output**
  (svg|png|pptx-slide).
- `execute(parameters, context)` = run the deterministic generator → return the chart asset
  (or a composed slide). No LLM inside; pure function.

Compose them with two more plugins: `nsight_render_to_image` (for the verify loop) and
`nsight_assemble_deck`. An egoHive **agent** (Gemini model + these tools enabled) then runs the
orchestration in §1: read the brief, pick tools, fill params, write the Finnish key messages,
call `assemble_deck`. The agent never produces a number — the tools do.

A natural **chart-selector** helper (a small tool or the agent's own routing) maps
`(metric shape → archetype)`: one series → `bar`/`lollipop`/`columns`; series×waves →
`grouped_wave_bar`/`trend`/`slope`/`dumbbell`/`bump`; distribution → `stacked_perception_bar`/
`tornado`; brand×attribute matrix → `heatmap`/`radar_small_multiples`/`net_diverging_bar`;
free-text frequencies → `word_rank_bar`/`word_cloud`/`treemap`.

---

## 6. Hard-won gotchas (bake these into the tools)

- **Fonts:** the headless renderer has **no "Arial"** — text renders blank. Use "Liberation
  Sans" / "DejaVu Sans".
- **Layered Vega-Lite:** only **one layer** may declare each axis (others `axis=None`) or the
  axis labels silently drop.
- **d3 number formats can't embed literal text** — precompute label strings in pandas.
- **Diverging bars need a domain that spans negatives** (e.g. `[-15, +30]`) and an explicit
  zero line, or negative bars don't draw (only the number shows).
- **Many-series charts:** small multiples beat overlay (radar with 8 brands).
- **Deck merge:** python-pptx has no native merge — deep-copy the slide part + its full
  relationship graph + media, with a self-maintained partname set to avoid layout/media
  collisions; keep the assembler's slide-order list as the single source of truth (a stale
  order silently reverts swapped-in slides — that bit us once).
- **Don't fabricate missing data:** if a requested wave/segment isn't in the source, the tool
  must surface that, not invent it (an agent correctly refused to fake 3 waves).

---

## 7. Artefacts in this repo
- Generators: `chart_lab/agent_*.py` (one per archetype, all reusable `build(...)`).
- Descriptions (the agent inputs): `chart_lab/desc_*.md`, `spec_*.md`.
- Data contracts (examples): `chart_lab/*.json`.
- Assembler: `chart_lab/agent_assemble_deck.py` (+ `agent_assemble_deck20.py` order).
- Output deck: `work/attendo_agent_deck20.pptx`.
- Judging records: `chart_lab/ITERATIONS.md`, `COMPARISON.md`.
