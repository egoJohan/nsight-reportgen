# Row-summary column for stacked-bar Likert charts — spec

## Goal

Add an optional, configurable **row-summary column** to the right of a stacked
horizontal bar chart. For each bar/row it prints one summary value — e.g. the classic
**top-2-box** "Samaa mieltä (4+5)" column at 65 %, 62 %, … from the customer's
reference deck.

Off by default; enabled per chart in the Design step. Applies only to
**`stacked_horizontal_bar`** charts. The "rows" are whatever the bars represent:
- a **battery** → one row per statement (the reference deck case),
- a single question **with a classifier** → one row per classifier group,
- a single question **total-only** → exactly one row.

Not shown on other chart types.

## Summary functions

The column runs ONE function per chart, chosen in the config:

| `row_summary_fn` | value per row | notes |
|------------------|---------------|-------|
| `none` (default) | — (feature off) | render unchanged from today |
| `top2_sum`       | sum of the 2 highest codes' % | auto-picks codes; reuses the code-selection behind `SortSpec` `topbox_sum` |
| `top3_sum`       | sum of the 3 highest codes' % | auto; reuses `top3_sum` |
| `sum`            | sum of the chosen codes' %    | `row_summary_codes` chosen by the user |
| `mean`           | mean rating (numeric codes)   | reuses the existing `mean` summary stat; excludes "Not answered" |
| `net`            | `pos% − neg%` (percentage points, signed) | `row_summary_pos_codes` − `row_summary_neg_codes` |

The summed `%`s are the **same percentages the bar segments already show** (same base,
same rounding), so the column is internally consistent with the bar.

## Config model — flat `ChartSpec` fields

Matches the existing flat-field style of `ChartSpec` (`not_answered_codes`,
`show_not_answered`, …) in `src/reportbuilder/model/report.py`. No nested object.

```python
# on ChartSpec:
row_summary_fn: str = "none"          # none|top2_sum|top3_sum|sum|mean|net
row_summary_codes: tuple[float, ...] = ()      # for fn == "sum"
row_summary_pos_codes: tuple[float, ...] = ()  # for fn == "net"
row_summary_neg_codes: tuple[float, ...] = ()  # for fn == "net"
row_summary_label: str = ""            # header; "" → default_label(fn) at render
```

- `report_from_json` parses each field (coerce code tuples to `float`, default
  missing), and `to_dict` round-trips them — same handling as the existing
  `not_answered_codes`. Verified by extending `tests/rb/test_report_serde.py`.
- `default_label(row_summary_fn) -> str` lives in ONE shared place (a small pure
  function; the frontend mirrors the exact strings): `top2_sum`→`"Top 2"`,
  `top3_sum`→`"Top 3"`, `sum`→`"Sum"`, `mean`→`"Keskiarvo"`, `net`→`"Net"`. The header
  the user sees is `row_summary_label or default_label(fn)` and is fully editable
  (they set it to e.g. `"Samaa mieltä (4+5)"`). Defaults are plain names — no code
  numbers baked in, so no ambiguity when codes change.

## Config UI — `src/reportbuilder/render/config_schema.py` + frontend

Add to the **`stacked_horizontal_bar`** schema only:

- `row_summary_fn` — a `select` field "Row summary": `none` (default) / `top2_sum` /
  `top3_sum` / `sum` / `mean` / `net`.
- `row_summary_label` — a `text` field "Summary header"; when empty the placeholder
  shows `default_label(fn)`.
- `row_summary_codes` — a value-code picker "Summed codes".
- `row_summary_pos_codes` / `row_summary_neg_codes` — pickers "Positive codes" /
  "Negative codes".

The code pickers **reuse the existing "Not answered" value-picker widget**
(`not_answered` field type / `NotAnsweredPicker`) — the scale's value labels with
checkboxes.

**Conditional visibility (new frontend pattern):** the config currently hides a field
by a chart-level condition (e.g. `percent_base` without a classifier). This feature
needs a field hidden by **another field's value** (`row_summary_fn`): show `label`
when `fn != none`; show `codes` only when `fn == sum`; show `pos/neg` only when
`fn == net`. Implement this as a small, explicit rule in the frontend `FieldWidget`
dispatch (it already receives the whole `chart`, so it can read `chart.row_summary_fn`).
Document the rule next to the existing `percent_base` gate. The whole group is only
present in the `stacked_horizontal_bar` schema, so it never appears elsewhere.

Backend wiring: `ChartSpecBody` (routes_questions.py) gains the five fields and
`_chart_spec_from_body` copies them onto the spec. Frontend `ChartSpec` type
(`web/src/lib/api.ts`) gains them; `makeChart` (`web/src/lib/charts.ts`) leaves
`row_summary_fn` at `"none"` (off) by default.

## Computation — engine attaches summaries to `SeriesResult`

The engine owns all stats; the renderer only draws. In `src/reportbuilder/stats/
engine.py`, when `row_summary_fn != "none"`, compute one value per bar/row and attach
it to the produced `SeriesResult` as `row_summaries: list[float] | None`
(`None`/absent when off). One row for the single-question total case, N rows for a
battery / classified chart — aligned 1:1 with the bars the renderer draws.

Per row:
- `sum` / `top2_sum` / `top3_sum`: sum the relevant codes' **segment %** for that row.
  `top2_sum`/`top3_sum` pick the 2/3 highest codes present (reuse the existing
  `topbox_sum`/`top3_sum` code-selection already used for sorting).
- `mean`: the row's mean rating (existing `mean` summary stat over the numeric codes,
  excluding missing / "Not answered").
- `net`: `sum(pos_codes %) − sum(neg_codes %)` in percentage points (may be negative).

Rounded with the chart's `NumberFormat` (percent decimals for the `%`/`net`
functions; `mean_decimals` for `mean`). Plain floats; the renderer formats for display.

## Rendering — `src/reportbuilder/render/charts/stacked_horizontal_bar.py`

When `series.row_summaries` is present:
1. Reserve a right-hand strip by shrinking the plotting area (axes width / x-extent)
   by a fixed fraction (~12 %) — proportional to the slot, no hard-coded px, like the
   rest of the chart chrome.
2. Draw the **header** (`row_summary_label or default_label(fn)`) at the top of the
   strip, right-aligned above the values, in the muted house-style caption font.
3. For each row, draw its formatted value right-aligned in the strip at that row's y:
   the `%`/`net` functions → e.g. `65 %` (whole percent per `NumberFormat`; `net`
   keeps its sign, e.g. `+51`); `mean` → decimal, e.g. `3.8`.
4. When `series.row_summaries` is absent, render exactly as today (no layout change).

The renderer reads `series.row_summaries` and the label — it never recomputes stats.

## Out of scope
- Other chart types (regular bars, pie, line, combo, native mode) — stacked
  horizontal bar only for now.
- Multiple summary columns at once (one function per chart).
- A "top-box" bucket drawn *inside* the bar (this is a separate right-hand column).

## Testing / verification
- **Model/serde:** the five fields round-trip through `report_from_json`/`to_dict`
  (extend `tests/rb/test_report_serde.py`): each `fn`, with codes/pos/neg/label.
- **Computation:** unit tests on a known battery series — assert `top2_sum`,
  `top3_sum`, `sum([4,5])`, `mean`, `net([4,5],[1,2])` match hand-computed values, and
  that `row_summaries` is `None` when `fn == "none"` (new `tests/rb/stats/
  test_row_summaries.py`). Include the single-row (total-only) case.
- **Config schema:** the `stacked_horizontal_bar` schema exposes the five fields;
  extend `tests/suite/unit/render/test_config_schema.py`.
- **Render:** a golden/smoke render of a stacked_horizontal_bar with a summary set
  produces a PNG with the header + per-row values; with `fn == "none"` the output is
  byte-identical to today (extend the render tests).
- **Manual (Playwright):** on a battery slide in Design, pick each function → the
  preview shows the right-hand column with the correct header and values; the `sum`
  and `net` code pickers appear only for those functions; editing the header updates
  it live; the column is absent on non-stacked charts.
