# Multiple classifying variables (cross-tab) — design

## Goal
Let a chart split its data by **two** classifying variables at once (e.g. gender ×
age), not just one. Requested by the customer: "samassa kuvassa voi olla data
splitattuna useamman taustamuuttujan suhteen … esim. sukupuoli ja ikäryhmät
molemmat classifying variablena."

## Scope (v1)
- **Up to 2** classifying variables (primary `classifying_var` + secondary).
- **Display:** flat cross-product series, ordered so the primary clusters
  (Male·18–24, Male·25–34, … Female·18–24, …). No configurable display modes yet
  (nested axis / small-multiples deferred to a later phase).
- **Chart types:** **clustered bars only** — `vertical_bar` and `horizontal_bar`.
  A second classifier is NOT offered for stacked bars (stacking a cross-product is
  meaningless), nor for `combo`/`line` (they assign special meaning to segment 0/1),
  nor for pie/doughnut/funnel/word cloud/themes (single-series).
- **Guard:** the UI warns when the combination count is large (> 12); no hard cap.
- **Back-compat:** a chart with no secondary classifier behaves **byte-for-byte** as
  today — the single-classifier code path is untouched (the new `seg_series` params
  default to `None`).

## Current pipeline (single classifier) — verified
- `ChartSpec.classifying_var: str | None`.
- `_single` (categorical) and `_summary` (summary stats) compute segments via:
  - `segment_bases(data, var, classifying_var, missing_override=)` — reads the
    classifier column with **`pd.to_numeric`**, returns `{ "Total": N, "<code>": N }`
    where code = `str(int(code))` (or `str(code)` if non-integer).
  - `aggregate_counts(data, var.name, classifying_var)` — duckdb `GROUP BY value,
    classifier`; segment label = `str(int(s))`; also a "Total" over all non-null
    values. **Casts `float(s)`** — so a classifier value must be numeric.
  - `_missing_counts(data, var, eff, classifying_var)` — per-segment not-answered
    counts, also via `pd.to_numeric`.
- `SeriesResult.segments` = code strings + "Total".
- `compute()` end: `if spec.classifying_var: result = _relabel_segments(result,
  model, spec.classifying_var)` maps codes → value labels for display.
- Render `image/bars.py`: `bars = [s for s in segs if s != "Total"]` — **"Total" is
  already dropped from the drawn series**; it survives only as `base_n` / reference.

**Consequence for the design:** the three stats primitives assume a single *numeric*
classifier. A synthetic string combo column ("1|10002") would crash at `float(s)`.
So we generalize the primitives to accept a **precomputed segmentation Series**.

## Design

### Data model — `src/reportbuilder/model/report.py`
- Add `classifying_var_2: str | None = None` to `ChartSpec` (secondary; optional).
- `classifying_var` stays the PRIMARY.
- `report_from_json`: `classifying_var_2=c.get("classifying_var_2")`. Default None →
  round-trips; old reports (no key) load as None. No migration needed.

### Stats primitives — accept a precomputed segmentation
Add an optional keyword `seg_series: pd.Series | None = None` to:
- `segment_bases(data, var, classifying_var=None, *, seg_series=None, missing_override=None)`
- `aggregate_counts(data, value_var, classifying_var=None, *, seg_series=None)`
- `_missing_counts(data, var, eff, classifying_var=None, *, seg_series=None)`

When `seg_series` is provided it IS the segmentation (its values are the segment keys,
`NaN`/`NA` rows excluded from every segment and from "Total"); the functions use it
**as-is with no numeric coercion** (keys are strings). When it's `None`, behaviour is
exactly today's (numeric single classifier). aggregate_counts registers the series as a
temp column and `GROUP BY value, seg` using the string key directly (no `float()`).

### Segmentation builder — `src/reportbuilder/stats/engine.py`
New helper used by both `_single` and `_summary`:

```
_segmentation(spec, data) -> tuple[pd.Series | None, tuple[str, ...] | None]
```
- If `spec.classifying_var_2` and `spec.classifying_var` are both set:
  - `c1 = pd.to_numeric(data[classifying_var]); c2 = pd.to_numeric(data[classifying_var_2])`
  - `key(code) = str(int(code)) if float(code).is_integer() else str(code)` (SAME
    formatting the primitives use, so relabel lookups line up).
  - `seg_series = where(c1.notna() & c2.notna(), key(c1) + "|" + key(c2), NA)`
  - `ordered = tuple(k for (n1,n2,k) in sorted({(c1,c2,key)…}, by (n1,n2)))` —
    numeric **primary-major** order (NOT lexical string order).
  - return `(seg_series, ordered)`.
- Else return `(None, None)` → callers use the existing numeric path unchanged.

`_single`/`_summary`: when `_segmentation` returns a series, pass `seg_series=` to
`segment_bases`/`aggregate_counts`/`_missing_counts`, and build the `segments` tuple as
`(*ordered, "Total")` (ordered combos, Total last) instead of from bases-dict order.
`base_n["Total"]` = valid rows with BOTH classifiers present (segment_bases Total on
the combo series) — same "Total = has classifier" convention as today.

**`_summary` has its own per-segment masking** (not just the primitives): today it does
`seg_codes = to_numeric(data[classifying_var])` then `data.loc[seg_codes == float(seg)]`
per segment. For a combo this MUST use the combo `seg_series` and **string** equality —
`data.loc[seg_series == key]` — and must NOT call `float(seg)` (a combo key like
"1|10002" is not floatable). Generalize this loop to take the segmentation series + the
ordered keys, with the `float()` cast confined to the single-classifier path.

**`aggregate_counts` temp column:** register `seg_series` on a copy of `data` under a
unique name (excluded rows = SQL `NULL`, i.e. Python `None`, so `WHERE seg IS NOT NULL`
still filters them), `GROUP BY value, seg`, and use the string key directly — never
`float(seg)` on the combo path.

### Labeling — `_relabel_segments` combo-aware
Extract `_code_label_map(var, seg_codes) -> dict[str,str]` from the current body
(includes the derived-binary-flag 0/1 → name/"Muut" logic). Then:
- Single classifier (today): `rl(seg) = map.get(seg, seg)`.
- Combo (both set): split `seg` on "|" → `[k1, k2]`; label = `map1.get(k1,k1) + " · "
  + map2.get(k2,k2)`; "Total" passes through. `compute()` calls the combo relabel when
  `spec.classifying_var_2` is set (passing both vars), else the single relabel.

### Render — reuse, no rewrite
Clustered `vertical_bar`/`horizontal_bar` already draw one series per non-Total
segment via `series_values`. Combo segments are simply more series, pre-ordered so the
primary clusters; the legend shows the combo labels. Colour: keep the existing palette
cycling over segments (a later phase can colour-group by the primary classifier).

Two minor render touch-points to check (not rewrites):
- **Native/pptx renderer** (`render/native`, `export/pptx_build.py`) draws from the
  same `SeriesResult`; verify it charts N combo segments (smoke test). It should, since
  segments are just more columns.
- **Classifier subtitle** (`render/elements.py`, currently `tf.text =
  ctx.spec.classifying_var`) should read "by <primary> × <secondary>" when both are set
  (today it would show only the primary's name).

### Config schema + widget
- `render/config_schema.py`: add a `classifying_var_2_field()` and include it **only**
  in the schema for clustered bars (`multi_series_schema` used by vertical/horizontal
  bar) — NOT in stacked/combo/single-series schemas.
- Web `ClassifyingVarWidget` (or a sibling): render a second picker when the schema has
  `classifying_var_2`; it is disabled until the primary is chosen, filters to the same
  segmentable/background variables, and **excludes the primary selection**. Show a hint
  when `values(primary) × values(secondary) > 12`.

### API — `routes_questions.py` (preview) + `routes_ai.py`
- `ChartSpecBody` gains `classifying_var_2: str | None = None`; `_chart_spec_from_body`
  maps it. Preview reuses `compute()` → cross-tab automatically.
- AI prompts mentioning "split by <primary> and <secondary>" — nice-to-have, optional.

## Testing (TDD)
- **Primitives:** `segment_bases`/`aggregate_counts`/`_missing_counts` with a
  `seg_series` return correct per-key bases/counts (string keys, no coercion); with
  `seg_series=None` outputs are identical to before (regression).
- **Engine:** 2-classifier `_single` produces cross-product segments, numeric
  primary-major order, correct per-combo counts + `base_n`; `_summary` likewise for a
  mean question. Combo `_relabel_segments` → "Male · 25–34"; unknown code passes
  through; binary-flag classifier still labels correctly inside a combo.
- **Regression:** a representative single-classifier chart's `SeriesResult` is
  unchanged (golden compare).
- **Serde:** `classifying_var_2` round-trips; absent → None.
- **API/schema:** preview maps `classifying_var_2`; the field appears only for
  clustered bar schemas.
- **Render smoke:** a 2-classifier clustered bar renders without error (PNG + native).

## Phasing
- **Phase 1 (this spec):** 2 classifiers, cross-product clustered bars, combo labels,
  UI guard.
- **Phase 2 (later, if needed):** configurable display styles (nested axis, small
  multiples), primary-classifier colour grouping, >2 classifiers, stacked/line support.
