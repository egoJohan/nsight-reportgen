# Row-summary column Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An optional, configurable summary column to the right of a `stacked_horizontal_bar` chart — one value per bar/row (top-2/top-3/sum/mean/net), e.g. the "Samaa mieltä (4+5)" = 65 %, 62 %, … column.

**Architecture:** Five flat `ChartSpec` fields carry the config. The stats engine computes one value per bar and attaches `row_summaries` to `SeriesResult`. The stacked-horizontal-bar renderer reserves a right strip and draws the header + values. Frontend adds the config widgets (a select + editable header + code pickers, the pickers shown per function).

**Tech Stack:** Python (dataclasses, pandas, matplotlib) backend; React/TS frontend. Tests: pytest (`.venv/bin/python -m pytest`), `tsc -b`, `vite build`, Playwright.

**Spec:** `docs/superpowers/specs/2026-07-07-row-summary-column-design.md`

## Global Constraints
- Applies to `stacked_horizontal_bar` only; every other chart type renders unchanged.
- Off by default (`row_summary_fn == "none"`) → byte-identical render to today.
- Engine owns stats; the renderer only draws `series.row_summaries` + the header.
- `default_label(fn)`: `top2_sum`→"Top 2", `top3_sum`→"Top 3", `sum`→"Sum", `mean`→"Keskiarvo", `net`→"Net". Defined once in Python, mirrored verbatim in TS.
- Fields: `row_summary_fn: str="none"`, `row_summary_codes: tuple[float,...]=()`, `row_summary_pos_codes: tuple[float,...]=()`, `row_summary_neg_codes: tuple[float,...]=()`, `row_summary_label: str=""`.

---

### Task 1: Model fields + serde

**Files:**
- Modify: `src/reportbuilder/model/report.py` (ChartSpec fields + `report_from_json`)
- Test: `tests/rb/test_report_serde.py`

**Interfaces:**
- Produces: the five `ChartSpec` fields above (exact names/types); `default_label(fn: str) -> str` (module-level in `report.py`).

- [ ] **Step 1: Failing serde test** — add to `test_report_serde.py`:
```python
def test_row_summary_roundtrip():
    from reportbuilder.model.report import report_from_json, default_label
    assert default_label("top2_sum") == "Top 2"
    c = {
        "question_ref": "q1", "chart_type": "stacked_horizontal_bar", "statistic": "pct",
        "classifying_var": None, "template_slot": "s1",
        "row_summary_fn": "net", "row_summary_pos_codes": [4, 5],
        "row_summary_neg_codes": [1, 2], "row_summary_label": "Netto",
    }
    r = report_from_json({"render_mode": "image", "template_ref": "", "charts": [c]})
    spec = r.charts[0]
    assert spec.row_summary_fn == "net"
    assert spec.row_summary_pos_codes == (4.0, 5.0)
    assert spec.row_summary_neg_codes == (1.0, 2.0)
    assert spec.row_summary_label == "Netto"
    # to_dict round-trips
    assert r.to_dict()["charts"][0]["row_summary_fn"] == "net"
```

- [ ] **Step 2: Run — fails** `AttributeError: row_summary_fn` (or KeyError). Run: `.venv/bin/python -m pytest tests/rb/test_report_serde.py::test_row_summary_roundtrip -q`

- [ ] **Step 3: Implement** — add the fields to `ChartSpec` (after `category_label_overrides`, before `options`):
```python
    # Right-hand per-row summary column (stacked_horizontal_bar only). Off when
    # row_summary_fn == "none". See spec 2026-07-07-row-summary-column.
    row_summary_fn: str = "none"                 # none|top2_sum|top3_sum|sum|mean|net
    row_summary_codes: tuple[float, ...] = ()        # for "sum"
    row_summary_pos_codes: tuple[float, ...] = ()    # for "net"
    row_summary_neg_codes: tuple[float, ...] = ()    # for "net"
    row_summary_label: str = ""                       # header; "" → default_label(fn)
```
Add a module-level helper:
```python
_ROW_SUMMARY_DEFAULT_LABEL = {
    "top2_sum": "Top 2", "top3_sum": "Top 3", "sum": "Sum",
    "mean": "Keskiarvo", "net": "Net",
}

def default_label(fn: str) -> str:
    return _ROW_SUMMARY_DEFAULT_LABEL.get(fn, "")
```
In `report_from_json`'s per-chart build (where `not_answered_codes` is parsed), add:
```python
            row_summary_fn=c.get("row_summary_fn", "none"),
            row_summary_codes=tuple(float(x) for x in c.get("row_summary_codes", ())),
            row_summary_pos_codes=tuple(float(x) for x in c.get("row_summary_pos_codes", ())),
            row_summary_neg_codes=tuple(float(x) for x in c.get("row_summary_neg_codes", ())),
            row_summary_label=c.get("row_summary_label", ""),
```
(`to_dict` uses `asdict`, so it round-trips automatically — confirm by reading the existing `to_dict`.)

- [ ] **Step 4: Run — passes.** Also run the full serde file: `.venv/bin/python -m pytest tests/rb/test_report_serde.py -q`

- [ ] **Step 5: Commit** `feat(model): row_summary_* fields on ChartSpec + default_label`

---

### Task 2: SeriesResult carries `row_summaries`

**Files:**
- Modify: `src/reportbuilder/stats/series.py`

**Interfaces:**
- Produces: `SeriesResult.row_summaries: tuple[float, ...] | None = None` — one value per bar, in `segments` order (or the bar order the renderer uses; confirm against the renderer in Task 4/5). `None` = feature off.

- [ ] **Step 1: Add the field** to `SeriesResult` (after `segment_primary`):
```python
    # Optional right-hand summary value per bar (row_summary feature), aligned to the
    # bars the renderer draws. None when the chart has no row summary. (spec 2026-07-07)
    row_summaries: tuple[float, ...] | None = None
```
- [ ] **Step 2: Run existing stats tests to confirm nothing broke** (frozen dataclass, new optional field): `.venv/bin/python -m pytest tests/rb/stats -q`
- [ ] **Step 3: Commit** `feat(stats): SeriesResult.row_summaries field`

---

### Task 3: Compute `row_summaries` in the engine

**Files:**
- Modify: `src/reportbuilder/stats/engine.py` (the stacked/battery `SeriesResult` build path)
- Create: `tests/rb/stats/test_row_summaries.py`

**Interfaces:**
- Consumes: `ChartSpec.row_summary_*`, the just-built `SeriesResult` (categories = scale codes, segments = the bars), the model's numeric code values.
- Produces: `compute_row_summaries(series: SeriesResult, spec: ChartSpec, model) -> tuple[float,...] | None` and the engine attaching it to the returned `SeriesResult` for `stacked_horizontal_bar` when `spec.row_summary_fn != "none"`.

- [ ] **Step 1: Read the engine's stacked build** — before writing, read where `compute(...)` builds the `SeriesResult` for `stacked_horizontal_bar` (grep `stacked` in engine.py; note whether the bars are `segments` or `categories`, and how numeric code values are obtained). Pin the row/code mapping here.

- [ ] **Step 2: Failing test** — build a known battery/stacked SeriesResult (3-code scale, 1 bar with pct {code1:20, code2:30, code3:50}) and a spec, assert:
```python
# top2_sum of 3 codes → codes 2+3 = 80.0 ; sum([code3]) → 50.0 ;
# mean → (1*20 + 2*30 + 3*50)/100 = 2.30 ; net(pos=[3], neg=[1]) → 50-20 = 30.0
```
Write the assertions against `compute_row_summaries(series, spec, model)` for each `fn`, and assert `None` when `fn == "none"`. (Use a minimal fake/real model as the other stats tests do — mirror an existing engine test's fixture.)

- [ ] **Step 3: Run — fails** (function undefined).

- [ ] **Step 4: Implement `compute_row_summaries`** — per bar:
  - `sum`/`top2_sum`/`top3_sum`: sum `series.cell(code, bar).pct` over the selected codes. For `top2/top3`, select the 2/3 highest codes present (reuse the existing top-box code selection used for sorting — grep `topbox`/`top3` in engine.py for the exact helper).
  - `mean`: Σ(code_value × pct) / Σ(pct) over the codes, using the model's numeric code values for each category.
  - `net`: Σ(pos pct) − Σ(neg pct).
  - Round with `spec.number_format` (pct decimals for %/net; mean_decimals for mean).
  Attach to the `SeriesResult` (rebuild via `dataclasses.replace(series, row_summaries=...)`) for `stacked_horizontal_bar` when `fn != "none"`.

- [ ] **Step 5: Run — passes.** Then `.venv/bin/python -m pytest tests/rb/stats -q`

- [ ] **Step 6: Commit** `feat(stats): compute_row_summaries for stacked charts`

---

### Task 4: Config schema exposes the fields

**Files:**
- Modify: `src/reportbuilder/render/config_schema.py` (`stacked_schema` + new field builders)
- Test: `tests/suite/unit/render/test_config_schema.py`

**Interfaces:**
- Produces: `row_summary_field()`, `row_summary_label_field()`, `row_summary_codes_field()`, `row_summary_pos_codes_field()`, `row_summary_neg_codes_field()` returning `ConfigField`s; added to `stacked_schema()`.

- [ ] **Step 1: Failing test** — assert the `stacked_schema()` field keys include `row_summary_fn`, `row_summary_label`, `row_summary_codes`, `row_summary_pos_codes`, `row_summary_neg_codes`, and that `row_summary_fn` is a `select` whose option values are `("none","top2_sum","top3_sum","sum","mean","net")`.

- [ ] **Step 2: Run — fails.**

- [ ] **Step 3: Implement** builders (mirror `not_answered_field` for the pickers, `statistic_field` for the select):
```python
def row_summary_field() -> ConfigField:
    return ConfigField(
        "row_summary_fn", "select", "Row summary",
        options=(("none", "None"), ("top2_sum", "Top 2 sum"), ("top3_sum", "Top 3 sum"),
                 ("sum", "Sum of selected"), ("mean", "Mean"), ("net", "Net (pos − neg)")),
        default="none",
    )

def row_summary_label_field() -> ConfigField:
    return ConfigField("row_summary_label", "text", "Summary header", default="")

def row_summary_codes_field() -> ConfigField:
    return ConfigField("row_summary_codes", "not_answered", "Summed codes")

def row_summary_pos_codes_field() -> ConfigField:
    return ConfigField("row_summary_pos_codes", "not_answered", "Positive codes")

def row_summary_neg_codes_field() -> ConfigField:
    return ConfigField("row_summary_neg_codes", "not_answered", "Negative codes")
```
Append these to `stacked_schema()`'s returned tuple. (If `ConfigField` lacks a `"text"` widget type, add it — check the `type` field's allowed values in the file's docstring/validation.)

- [ ] **Step 4: Run — passes.** Then `.venv/bin/python -m pytest tests/suite/unit/render/test_config_schema.py -q`

- [ ] **Step 5: Commit** `feat(config): row-summary fields in the stacked schema`

---

### Task 5: Renderer draws the column

**Files:**
- Modify: `src/reportbuilder/render/charts/stacked_horizontal_bar.py` (+ maybe `render/image/bars.py`)
- Test: extend the render/golden tests (`tests/rb/render/…`)

**Interfaces:**
- Consumes: `series.row_summaries` (tuple aligned to bars), `spec.row_summary_fn`, `spec.row_summary_label`, `default_label(fn)`.

- [ ] **Step 1: Read the renderer** — how it lays out bars (x 0–100, bar y positions), where the axes/figure margins are set. Confirm bar order matches `row_summaries` order (fix the Task-3 alignment if not).

- [ ] **Step 2: Smoke test** — render a `stacked_horizontal_bar` spec with `row_summary_fn="top2_sum"` through the existing preview/render path; assert the returned figure/PNG is produced without error AND (когда `fn="none"`) the output is unchanged. (Follow an existing render test's harness.)

- [ ] **Step 3: Implement** — when `series.row_summaries is not None`:
  - Reserve a right strip: reduce the axes' right extent by ~12 % (adjust `ax` position or `subplots_adjust`), proportional to the slot.
  - Header text `spec.row_summary_label or default_label(spec.row_summary_fn)` at the top of the strip, right-aligned, muted caption style (reuse house-style font/colour constants).
  - Each bar's value right-aligned at the bar's y: `%`/`net` → whole percent (respect `NumberFormat`; `net` keeps sign, e.g. `+51`); `mean` → decimal (`3.8`).
  - When `None`: no layout change.

- [ ] **Step 4: Run** the render/golden suite: `.venv/bin/python -m pytest tests/rb/render tests/test_golden_attendo.py -q` — golden decks (no row summary) must stay green.

- [ ] **Step 5: Commit** `feat(render): row-summary column on stacked horizontal bar`

---

### Task 6: Backend API passthrough

**Files:**
- Modify: `src/reportbuilder/api/routes_questions.py` (`ChartSpecBody` + `_chart_spec_from_body`)

- [ ] **Step 1:** Add the five fields to `ChartSpecBody` (mirror `not_answered_codes`: `row_summary_fn: str = "none"`, `row_summary_codes: list[float] = []`, `row_summary_pos_codes: list[float] = []`, `row_summary_neg_codes: list[float] = []`, `row_summary_label: str = ""`).
- [ ] **Step 2:** In `_chart_spec_from_body`, pass them onto the `ChartSpec` (coerce lists → tuples of float).
- [ ] **Step 3:** Verify a preview request with `row_summary_fn` set round-trips: `.venv/bin/python -m pytest tests/rb/api tests/suite/unit/api -q`
- [ ] **Step 4: Commit** `feat(api): accept row_summary_* on preview-chart/report`

---

### Task 7: Frontend — type, makeChart, config widget

**Files:**
- Modify: `web/src/lib/api.ts` (ChartSpec type), `web/src/lib/charts.ts` (makeChart + `defaultRowSummaryLabel`), `web/src/components/wizard/StepConfigure.tsx` (FieldWidget: `text` widget + conditional visibility)

- [ ] **Step 1:** `ChartSpec` type gains `row_summary_fn?: string; row_summary_codes?: number[]; row_summary_pos_codes?: number[]; row_summary_neg_codes?: number[]; row_summary_label?: string;`
- [ ] **Step 2:** `charts.ts`: `makeChart` sets `row_summary_fn: "none"`. Add `defaultRowSummaryLabel(fn)` mirroring the Python map ("Top 2"/"Top 3"/"Sum"/"Keskiarvo"/"Net").
- [ ] **Step 3:** `StepConfigure` FieldWidget:
  - Support the `"text"` widget type (a plain `<input>` bound to the field) if not already.
  - `not_answered`-type fields already render the value picker → reuse for `row_summary_codes`/`pos`/`neg`.
  - **Conditional visibility** (read `chart.row_summary_fn`): render `row_summary_label` only when `fn !== "none"`; `row_summary_codes` only when `fn === "sum"`; `row_summary_pos_codes`/`row_summary_neg_codes` only when `fn === "net"`. Put this rule next to the existing `percent_base` gate. For the label field, show `defaultRowSummaryLabel(fn)` as the placeholder.
- [ ] **Step 4:** `npx tsc -b` (TSC=0), `npm run build`.
- [ ] **Step 5: Manual (Playwright)** on a battery slide in Design: pick each function → preview shows the right column; `sum`/`net` pickers appear only for those; header edit is live; absent on non-stacked charts.
- [ ] **Step 6: Commit** `feat(web): row-summary config UI on stacked charts`

---

## Self-Review
- **Spec coverage:** model+serde (T1), SeriesResult (T2), computation incl. all 5 fns + none (T3), config schema (T4), renderer incl. none-unchanged (T5), API (T6), frontend type/makeChart/widget+conditional-visibility (T7). All covered.
- **Placeholder scan:** T3/T5 defer the exact engine/renderer internals to a read-first step because those files are unread — each still has concrete tests + interfaces; not silent placeholders.
- **Type consistency:** `row_summary_fn/codes/pos_codes/neg_codes/label` and `default_label`/`defaultRowSummaryLabel` used identically across tasks. `row_summaries` tuple on SeriesResult consumed by T5 exactly as produced by T3.
