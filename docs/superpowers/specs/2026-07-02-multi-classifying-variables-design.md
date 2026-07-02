# Multiple classifying variables (cross-tab) — design

## Goal
Let a chart split its data by **two** classifying variables at once (e.g. gender ×
age), not just one. Requested by the customer: "samassa kuvassa voi olla data
splitattuna useamman taustamuuttujan suhteen … esim. sukupuoli ja ikäryhmät
molemmat classifying variablena."

## Scope (v1)
- **Up to 2** classifying variables (primary + secondary).
- **Display:** flat cross-product series, ordered so the primary clusters
  (Male·18–24, Male·25–34, … Female·18–24, …). No configurable display modes yet
  (nested axis / small-multiples deferred).
- **Chart types:** bar family only (vertical/horizontal/grouped bar). The second
  classifier is NOT offered for pie/doughnut/funnel/word cloud/themes.
- **Guard:** warn in the UI when the combination count is large (> 12), since tiny
  cross-cells get statistically noisy.
- **Back-compat:** a chart with no secondary classifier behaves EXACTLY as today.

## Current pipeline (single classifier)
- `ChartSpec.classifying_var: str | None`.
- Engine `_categorical`/`_summary`: `segment_bases(data, var, classifying_var)` →
  `{ "Total": N, "<code>": N, … }`; `aggregate_counts(data, var.name, classifying_var)`
  → `{(cat_code, seg_code): count}`. `SeriesResult.segments` = code strings + "Total".
- `_relabel_segments(result, model, classifying_var)` maps segment **codes → value
  labels** ("10002" → "25-34 vuotias") for display.
- Render (`image/bars.py`) draws one series per segment via `series_values`.

## Design

### Data model — `src/reportbuilder/model/report.py`
- Add `classifying_var_2: str | None = None` to `ChartSpec` (secondary; optional).
- Keep `classifying_var` as the PRIMARY (all existing code/tests untouched).
- `report_from_json`: read `classifying_var_2` (default None). Round-trips.

### Engine — `src/reportbuilder/stats/engine.py` + `stats/base_rules.py` + `stats/aggregate.py`
Reuse the single-classifier machinery via a **synthetic combined segmentation**:
- When `classifying_var_2` is set AND `classifying_var` is set:
  - Build a combined key column: `combo = f"{code1}|{code2}"` per row (both numeric,
    NaN rows drop out of every segment, matching current behaviour).
  - Run `segment_bases`/`aggregate_counts` against this combined column (a small
    generalization: accept a precomputed segmentation Series, or assign a temp
    column on a copy of `data`). Segments = combo keys.
  - **Order** segments primary-major then secondary: sort combo keys by `(code1, code2)`.
- `base_n` is naturally per-combo (from `segment_bases` on the combined column).
- Only the primary classifier set → unchanged path.

### Labeling — `_relabel_segments` (engine)
Generalize to accept the secondary var too. For a combo key "1|10002":
- split → look up "1" in `classifying_var`'s value labels ("Male") and "10002" in
  `classifying_var_2`'s labels ("25-34 vuotias") → join with " · " → "Male · 25-34
  vuotias". "Total" passes through. Unknown codes pass through as the raw code.

### Render — reuse
No render rewrite. Grouped/vertical/horizontal bar already draw N segments; combo
segments are just more series, pre-ordered so the primary clusters. Legend shows the
combo labels. (A later phase may add nested-axis / small-multiple display styles.)

### Config schema + widget — `render/config_schema.py`, web `ClassifyingVarWidget`
- Add a `classifying_var_2` field to the **multi-series bar** schema only
  (`multi_series_schema`, stacked schema). Combo/pie/funnel/single-series schemas do
  NOT expose it.
- The 2nd picker is disabled/hidden until the 1st classifier is chosen, and cannot
  equal the 1st. Frontend shows a hint when combos > 12.

### API — `routes_questions.py` (preview), `routes_ai.py`
- `ChartSpecBody` gains `classifying_var_2`; `_chart_spec_from_body` maps it.
- AI title/label prompts can mention both splits (nice-to-have, not required).

## Testing (TDD)
- **Engine:** cross-product segments + base_n + counts for 2 classifiers; ordering
  (primary-major); combo labels via `_relabel_segments`; single-classifier path
  unchanged (regression). Use synthetic data with 2 small classifiers.
- **Serde:** `classifying_var_2` round-trips; absent → None.
- **API:** preview body maps `classifying_var_2`; schema exposes it only for bar types.
- **Guard:** combo-count threshold (frontend).

## Phasing
- **Phase 1 (this spec):** 2 classifiers, cross-product series, bar types, guard.
- **Phase 2 (later, if needed):** configurable display styles (nested axis,
  small multiples); >2 classifiers.
