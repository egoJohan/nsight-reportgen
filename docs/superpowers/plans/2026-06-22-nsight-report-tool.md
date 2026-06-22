# nSight Report Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-service survey report builder — import SPSS `.sav` → browse questions → compose PowerPoint reports (variable × chart type) → preview → export editable PPT + PDF — backed by datahive as system of record, with a fully automated end-to-end test suite where Claude judges the visual/subjective gates.

**Architecture:** Near-stateless Python backend (`reportbuilder` package) = Question Model builder + deterministic statistics engine (SeriesResult) + dual-mode rendering engine (native editable charts | guaranteed-clean images) + PPT→PDF preview/export. datahive (separate repo) is the system of record via its generic **projects app** (Project=Case, attached docs=Material/Report/Artifact) and gains three generic additions (aggregation primitive, projects REST, report-JSON round-trip). A thin Flutter UI (copy Prima Volta) sits on a REST API. The hardest unknown — de-novo native chart construction with clean layout — is proven by a **spike first**.

**Tech Stack:** Python 3.11+, `uv`, `pytest` (+`pytest-asyncio`), `pyreadstat`, `pandas`, `duckdb`, `python-pptx`, `matplotlib`, LibreOffice (headless PPT→PDF), `pdftotext`/`pdfplumber` (PDF text extraction), `anthropic` SDK (Claude-as-judge), FastAPI; datahive (FastAPI/Python) for D1–D3; Flutter web for UI.

**Companion specs (read before implementing):**
- Design: `docs/superpowers/specs/2026-06-22-nsight-report-tool-design.md`
- Requirements catalog (REQ-* IDs, every task cites the REQs it satisfies): `docs/superpowers/specs/2026-06-22-nsight-report-tool-requirements.md`

## Global Constraints

- **Python ≥ 3.11**, managed with `uv`. Run tests with `uv run pytest`. New package lives at `src/reportbuilder/`; tests at `tests/rb/`. `pythonpath=["src"]` is already set, so `import reportbuilder` works.
- **The prototype (`src/nsight/`) is reference only — do not import from it.** Image-mode rendering may lift *techniques* from `chart_lab/` but re-implemented under `reportbuilder/`.
- **Numbers never come from an LLM.** Every chart number is computed by the deterministic statistics engine. Claude is used ONLY as a test judge for visual/subjective gates, never to produce report data.
- **SeriesResult is the sole numeric source.** Renderers, exports, and previews read it; none re-derive numbers.
- **Native-mode reports contain zero picture-shapes in chart slots** (the editability gate, REQ-C-23). Image-mode reports are non-editable by explicit choice.
- **Genericity guardrail (datahive):** every datahive change must be describable without the words "nSight", "survey", or "chart". Reviewed per datahive PR.
- **Numeric variables only** this phase (REQ-D-02); string variables are out of scope.
- **TDD throughout:** write the failing test, see it fail, implement minimally, see it pass, commit. Frequent commits.
- **Commit message footer** for every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

`reportbuilder` backend package (`src/reportbuilder/`):

```
reportbuilder/
  model/
    question.py        # Variable, ValueLabel, Question, QuestionModel  (REQ-C-02/05/06, D-01..06, M-01/02)
    report.py          # ChartSpec, Report, SortSpec, NumberFormat, ElementToggles  (REQ-C-08/10/11, S-*, N-*)
    chart_types.py     # ChartType enum + the 11 type ids + native/image capability table (REQ-C-13)
  ingest/
    sav_reader.py      # .sav -> QuestionModel via pyreadstat (REQ-C-01, D-01..06, MV-02)
    multi_group.py     # multi-question auto-suggest + apply user grouping (REQ-M-02, R2)
  stats/
    series.py          # SeriesResult, Cell (the sole numeric contract)
    base_rules.py      # single/multi/segment base computation incl. missing (REQ-C-14/16, M-03, MV-01/02)
    statistics.py      # pct / count / mean over bases (REQ-C-15, N-01/02/03)
    sorting.py         # data_order/pct/topbox_sum/mean/count sorting (REQ-S-01/02/03, C-26)
    engine.py          # compute(question, spec, data) -> SeriesResult (orchestrator)
    aggregate.py       # raw counts source: datahive aggregation primitive OR in-process fallback (R1/D1 decouple)
  render/
    base.py            # ChartRenderer protocol, Slot, StyleSpec, RenderContext
    style_spec.py      # load a style spec (fonts/colors/sizes/positions) from a template PPT (REQ-C-25/27, R4)
    layout.py          # native layout solver: compute c:manualLayout coords from label metrics (R3)
    native/            # one builder per chart type -> native c:chart (REQ-C-13/23/24)
      __init__.py      # NATIVE_BUILDERS registry
      column.py bar.py line.py pie.py doughnut.py radar.py scatter.py funnel.py  # combo deferred
    image/             # matplotlib builders -> PNG -> add_picture (REQ-C-13 image mode)
      __init__.py      # IMAGE_BUILDERS registry (all 11 incl. funnel/combo)
      <one module per type>
    elements.py        # element profile: title/axes/legend/N/data-labels/filter-var (REQ-C-24a..i)
    deck.py            # assemble Report -> .pptx: slots, completeness (REQ-C-18), mode dispatch
  export/
    pptx_build.py      # write the .pptx artifact
    pdf_convert.py     # LibreOffice headless PPT->PDF (REQ-C-21, R5)
    preview.py         # PDF page rasterization for the preview views (REQ-C-19a/b)
  store/
    datahive_client.py # REST client: projects CRUD, attach/read docs, aggregation (D1/D2/D3)
    duckdb_store.py    # local respondent-row store for in-process aggregation fallback
  api/
    app.py             # FastAPI app
    routes_cases.py routes_materials.py routes_questions.py routes_reports.py routes_render.py
  testing/
    judge.py           # Claude-as-judge harness (REQ visual/subjective gates)
    rubrics.py         # per-requirement judge rubrics
    fidelity.py        # objective number extraction: PPTX-XML + pdftotext (R5 gate layers 1&2)
    fixtures.py        # synthetic .sav builders + golden Attendo bindings
```

datahive changes (`/home/johan/Projects/egoiq/egohive/egohive-datahive/`):
```
datahive/aggregation/service.py        # generic GROUP BY / cross-tab over a tabular item (D1)
datahive/api/routers/aggregation.py    # REST surface for it (D1)
datahive/api/routers/projects.py       # projects REST router (D2)
datahive/projects/service.py           # attach_doc gains reference_id/raw-source round-trip (D3) [modify]
```

Flutter UI (`/home/johan/Projects/egoiq/primavolta/` patterns, new app or module — decided in Phase 8):
```
lib/features/reports/...               # Data area (question browser) + Reports area (builder + preview)
```

---

## Core Types (the locked interfaces — every task references these verbatim)

These are defined in Phase 1 (Task 1.x) and are the `Consumes`/`Produces` contract for all later tasks. **Do not change signatures without updating this section.**

```python
# reportbuilder/model/question.py
from dataclasses import dataclass

@dataclass(frozen=True)
class ValueLabel:
    value: float
    label: str

@dataclass(frozen=True)
class Variable:
    name: str                              # SPSS variable name
    label: str                             # variable label -> question text (REQ-D-04)
    measurement: str                       # "categorical" | "scale"
    value_labels: tuple[ValueLabel, ...]   # (REQ-D-05)
    missing_values: frozenset[float]       # user-defined missing codes; Sysmis = NaN handled separately (REQ-D-06, MV-02)

@dataclass(frozen=True)
class Question:
    qid: str                               # stable id (slug of primary variable / group)
    kind: str                              # "single" | "multi"  (REQ-C-06, M-01/02)
    variables: tuple[str, ...]             # 1 for single; N for multi group
    text: str                              # question text from the variable label

@dataclass
class QuestionModel:
    variables: dict[str, Variable]         # name -> Variable
    questions: list[Question]
    def question(self, qid: str) -> Question: ...
    def variable(self, name: str) -> Variable: ...
```

```python
# reportbuilder/stats/series.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Cell:
    pct: float | None       # 0..100
    count: float | None
    mean: float | None

@dataclass(frozen=True)
class SeriesResult:
    categories: tuple[str, ...]               # row labels, already in final sort order
    segments: tuple[str, ...]                 # column labels; always includes "Total"
    cells: dict[tuple[str, str], Cell]        # (category, segment) -> Cell
    base_n: dict[str, int]                    # segment -> N  (REQ-C-24h)
    statistic: str                            # "pct" | "count" | "mean"
    def cell(self, category: str, segment: str) -> Cell: ...
```

```python
# reportbuilder/model/report.py
from dataclasses import dataclass, field

@dataclass(frozen=True)
class SortSpec:
    basis: str                       # "data_order"|"pct"|"topbox_sum"|"mean"|"count"  (REQ-S-01)
    topbox_codes: tuple[float, ...] = ()     # for "topbox_sum" (REQ-S-02)
    descending: bool = True

@dataclass(frozen=True)
class NumberFormat:
    pct_decimals: int = 0            # REQ-N-01
    mean_decimals: int = 1          # REQ-N-02
    count_round_up: bool = False    # REQ-N-03
    show_pct_sign: bool = True

@dataclass(frozen=True)
class ElementToggles:
    title: bool = True; legend: bool = True; n: bool = True
    axis_names: bool = True; filter_var: bool = True; data_labels: bool = True

@dataclass(frozen=True)
class ChartSpec:
    question_ref: str                # qid (REQ-C-11)
    chart_type: str                  # see chart_types.py (REQ-C-13)
    statistic: str                   # "pct"|"count"|"mean" (REQ-C-15)
    classifying_var: str | None      # segmentation -> segments + Total (REQ-C-14)
    number_format: NumberFormat
    sort: SortSpec
    template_slot: str
    elements: ElementToggles
    scatter_xy: tuple[str, str] | None = None   # scatter only (design §9a)

@dataclass(frozen=True)
class Report:
    name: str
    render_mode: str                 # "native" | "image" (per report, design §8)
    template_ref: str
    charts: tuple[ChartSpec, ...]
```

```python
# reportbuilder/render/base.py — rendering contract
from typing import Protocol
class Slot:                          # placement region on a slide from the template
    slide_index: int; left: int; top: int; width: int; height: int; name: str
class StyleSpec:                    # loaded from template PPT (REQ-C-25/27)
    def font_for(self, element_class: str) -> tuple[str, int]: ...   # (font_name, point_size)
    def color_for(self, series_index: int) -> str: ...
class RenderContext:
    slide: object; slot: Slot; style: StyleSpec; spec: "ChartSpec"; series: "SeriesResult"; fmt: "NumberFormat"
class ChartRenderer(Protocol):
    def render(self, ctx: RenderContext) -> None: ...     # native: add_chart; image: add_picture
```

```python
# reportbuilder/testing/judge.py — Claude-as-judge (REQ visual/subjective gates)
from dataclasses import dataclass
@dataclass(frozen=True)
class JudgeVerdict:
    passed: bool
    reasoning: str
    confidence: float                # 0..1
def judge_image(png_path: str, rubric: str, *, requirement_id: str,
                extra_context: str = "") -> JudgeVerdict: ...
def judge_pdf(pdf_path: str, rubric: str, *, requirement_id: str) -> list[JudgeVerdict]:  # one per page
    ...
```

```python
# reportbuilder/testing/fidelity.py — objective number gates (R5 layers 1&2)
def numbers_from_pptx(pptx_path: str) -> dict:        # chart series read via python-pptx
    ...
def numbers_from_pdf(pdf_path: str) -> list[float]:   # pdftotext/pdfplumber data-label numbers
    ...
def assert_series_match(extracted: dict, series: "SeriesResult", tol: float = 0.5) -> None:
    ...
```

```python
# reportbuilder/store/datahive_client.py — system-of-record client (D1/D2/D3)
class DataHiveClient:
    def create_case(self, name: str) -> str: ...                       # -> project_id (REQ-C-03/07)
    def list_cases(self) -> list[dict]: ...
    def attach_material(self, case_id: str, name: str, sav_bytes: bytes,
                        codebook_summary: str) -> str: ...             # -> material_doc_id (REQ-C-04)
    def save_report(self, case_id: str, report_id: str | None, report_json: str,
                    readable: str) -> str: ...                          # reference_id round-trip (REQ-C-08, D3)
    def load_report(self, report_doc_id: str) -> str: ...              # exact JSON back
    def aggregate(self, material_id: str, group_by: list[str],
                  filters: dict, weight: str | None = None) -> dict: ... # raw counts (D1)
```

---

## Test Strategy — automated end-to-end, Claude as judge

Every requirement is covered by at least one automated test. Tests are layered:

1. **UNIT / GOLD (objective):** statistics engine, base rules, sorting, formatting, multi-grouping. Golden tests assert computed `SeriesResult` == known truth using the Attendo `.sav` + the deck's printed numbers (bindings in `testing/fixtures.py`). These are plain `pytest`.
2. **RENDER (objective):** generated `.pptx` is valid OOXML; native mode has a real `c:chart` + embedded workbook and **zero picture shapes** in chart slots; image mode has a picture; element presence (title/axes/legend/N/data-labels/filter-var) asserted by inspecting the OOXML; chart-data series == `SeriesResult`. Plain `pytest` over python-pptx.
3. **CONV (objective):** `export/pdf_convert` produces a valid PDF with expected page count; `numbers_from_pdf` (pdftotext) data-label numbers == `SeriesResult` — the layer that actually guards LibreOffice drift (design §10 layer 2). Plain `pytest` (requires LibreOffice on the runner).
4. **JUDGE (Claude-as-judge, the subjective gates):** the deterministic pipeline renders each chart/page to PNG; `judge_image`/`judge_pdf` sends the PNG + a per-requirement rubric to Claude and returns a structured `JudgeVerdict{passed, reasoning, confidence}`. This automates the gates objective tests can't express:
   - **Layout cleanliness / no overlapping or truncated labels** (the R3 risk; design §9a render-verify gate).
   - **Presentation-quality PDF/PPT** (REQ-C-28b/29b).
   - **Sensible per-question organization** of the browser view (REQ-C-05) — judged on a rendered screenshot in Phase 8.
   - Rubrics live in `testing/rubrics.py`, one per judged requirement, each a precise checklist so the verdict is reproducible. The judge prompt forces a JSON verdict and is run at low temperature; a test asserts `verdict.passed` (and logs `reasoning` on failure). Judge tests are marked `@pytest.mark.judge` so they can run in a dedicated CI lane (needs `ANTHROPIC_API_KEY`).
5. **INTEG (datahive):** project create / attach material+report / list / exact JSON round-trip via `reference_id`/`reveal_source`, against a test hive; aggregation-primitive parity vs in-process aggregation.
6. **E2E:** one test drives the whole chain — synthetic (and Attendo) `.sav` → QuestionModel → Report definition → render (both modes) → `.pptx` + `.pdf` → run layers 2–4 (objective number gates + Claude judge on rendered pages). This is the "automated end to end, Claude as the judge" deliverable (Phase 9).

**REQ → test mapping** is maintained in the requirements catalog's Test-approach column; each task below names the REQ(s) it satisfies and the layer(s) that verify it. Phase 9 includes a coverage-audit test that fails if any IN/DEFER REQ has no referencing test.

---

## Phases (each is an independently-testable milestone)

- **Phase 0 — Foundation:** package scaffold, core types, the Claude-judge + fidelity harness. (Everything depends on it.)
- **Phase 1 — Rendering spike (R3, highest unknown):** prove de-novo `add_chart` + `c:manualLayout` + data-label placement → clean editable chart through LibreOffice, judged by Claude. Go/no-go on native rendering.
- **Phase 2 — Ingest + Question Model:** `.sav` → QuestionModel; multi-group auto-suggest + apply (REQ-C-01/02/05/06, D-*, M-01/02).
- **Phase 3 — Statistics engine:** base rules, statistics, sorting → SeriesResult; golden tests vs Attendo (REQ-C-14/15/16, M-03/04, MV-*, N-*, S-*).
- **Phase 4 — datahive changes (D1/D2/D3):** aggregation primitive, projects REST, report-JSON round-trip; generic, guardrail-reviewed.
- **Phase 5 — Rendering engine:** native (9 types + funnel approximation) + image (all 11) builders, element profile, style spec, deck assembly, completeness (REQ-C-13/17/18/23/24/25/27).
- **Phase 6 — Preview / export + REST API:** PPT→PDF, preview views, the fidelity gate wired, FastAPI routes for cases/materials/questions/reports/render (REQ-C-03/04/07/08/09/10/19/21/22/28/29).
- **Phase 7 — Report builder orchestration:** Report definition CRUD, duplicate, render-mode dispatch, end-to-end backend wiring (REQ-C-07/08/09/12).
- **Phase 8 — Flutter UI:** Data area (question browser: browse/sort/edit/delete + single/multi) + Reports area (builder + preview + duplicate) (REQ-U-*, C-26).
- **Phase 9 — E2E suite + coverage audit:** full-pipeline E2E with Claude judge; REQ-coverage audit test.

Detailed bite-sized tasks for each phase follow below.

---

## Cross-Phase Reconciliation (canonical decisions — these OVERRIDE any conflicting wording in the per-phase tasks)

The phases were drafted in parallel; where two phases named the same thing differently, the canonical form below wins. Executors must use these names/signatures.

### C1. Canonical `chart_type` ids (docx-aligned)
The single source of truth for chart-type ids — used by `model/chart_types.py` `ChartType` enum **values**, `ChartSpec.chart_type`, and BOTH builder registries:

```
line, pie, vertical_bar, stacked_vertical_bar, horizontal_bar,
stacked_horizontal_bar, radar, doughnut, scatter, funnel, combo
```

OOXML mapping lives inside the native builders: `vertical_bar`→`COLUMN_CLUSTERED`, `stacked_vertical_bar`→`COLUMN_STACKED`, `horizontal_bar`→`BAR_CLUSTERED`, `stacked_horizontal_bar`→`BAR_STACKED`. **Override:** Task 0.5's enum values (`column`, `bar`, …) and Phase 1's registry key `"column"` are replaced by `vertical_bar` etc. Task 1.2's `build_column_chart` registers under `"vertical_bar"`.

### C2. Canonical rendering entry point + builder signature
- All chart builders take a single `RenderContext`: `build_<type>(ctx: RenderContext) -> None`. **Override:** Phase 1's `build_column_chart(slide, slot, series, *, point_size)` is refactored in Task 5.4 to `build_vertical_bar(ctx)`; the spike (Tasks 1.2–1.4) may use the positional form internally but Task 5.4 converges it to `(ctx)` before Phase 5 proceeds.
- Deck assembly entry point is **`render/deck.py::render_report(report: Report, series_by_ref: dict[str, SeriesResult], style: StyleSpec) -> Presentation`** plus `render_to_file(report, series_by_ref, style, out_path) -> str`. **Override:** Phase 6 Task 6.1's `build_pptx(report, model, data, out_path)` is implemented as: compute `series_by_ref` (loop `ChartSpec`→`engine.compute`), load the StyleSpec, then call `render_to_file`. There is no `build_deck`.

### C3. Canonical export/PDF/preview API (one module set)
`export/pdf_convert.py` and `export/preview.py` are created in **Phase 1 (Task 1.3)**; Phase 6 EXTENDS them, it does not recreate them. Canonical functions:
- `export/pdf_convert.py`: `pptx_to_pdf(pptx_path, out_dir) -> str` (the converter), `pdf_page_count(pdf_path) -> int`.
- `export/preview.py`: `pdf_page_to_png(pdf_path, page_index, out_path, *, resolution=150) -> str`, `rasterize_pages(pdf_path, out_dir, *, dpi=150) -> list[str]`, and `slide_view`/`page_view` (both call `rasterize_pages` — two labels over the one PDF).
**Override:** Phase 6's `convert_to_pdf`/`slide_view`/`page_view` are renamed/rebuilt on top of `pptx_to_pdf`/`rasterize_pages`.

### C4. Image-mode fidelity check uses the computed SeriesResult (no `data_arrays_for`)
**Override:** Phase 6 Task 6.5's reference to `render.image.data_arrays_for(spec, model, data)` is dropped. The orchestrator already holds `series_by_ref`; image-mode layer-3 simply asserts the `SeriesResult` that fed the builder equals the engine's `compute` output (an identity check that the right series was passed). No new function.

### C5. `read_sav` signature
Canonical: `ingest/sav_reader.py::read_sav(path: str | Path) -> tuple[pandas.DataFrame, QuestionModel]` (Phase 2). **Override:** Phase 7's material route does NOT call `read_sav(bytes)`; it writes the uploaded bytes to a temp file, calls `read_sav(tmp_path)`, uses the returned `QuestionModel` for `question_count`, and stores the raw bytes to datahive via `attach_material`.

### C6. `multi_group` function names
Canonical (Phase 2): `ingest/multi_group.py::suggest_multi_groups(model) -> list[tuple[str,...]]` and `apply_groups(model, groups) -> QuestionModel`. **Override:** Phase 7 Task 7.4's `apply_grouping(model, variables, kind)` is a thin wrapper: for `kind=="multi"` it calls `apply_groups(model, [tuple(variables)])`; for `kind=="single"` it splits the group back to singles. Add this wrapper to `multi_group.py`.

### C7. Added foundation tasks (gaps the phases assumed but no task created)
These are inserted into Phase 0 and MUST be done before the phases that consume them:

- **Task 0.9 — `model/report.py` JSON (de)serialization.** Add `report_to_json(report: Report) -> str` and `report_from_json(data: dict | str) -> Report` (round-trips every field incl. nested `ChartSpec`/`SortSpec`/`NumberFormat`/`ElementToggles`/`scatter_xy`). Consumed by Phase 7 (report CRUD) and the datahive round-trip. Test: `report_from_json(report_to_json(r)) == r` for a 3-chart report.
- **Task 0.10 — `testing/fixtures.py` consolidated builders.** One module providing every fixture the phases reference: `synthetic_sav(tmp_path) -> str`, `synthetic_sav_bytes() -> bytes`, `tiny_question_model() -> QuestionModel`, `tiny_model_and_data() -> tuple[QuestionModel, DataFrame]`, `known_series() -> SeriesResult`, `known_pcts() -> list[float]`, `one_chart_report() -> Report`, `two_chart_report() -> Report`, `report_json_n_charts(n) -> dict`. Attendo golden bindings (`ATTENDO_AIDED_VARS`, `DECK_AIDED_AWARENESS`, opinion constants) are added here in Phase 3 as data (copied, never imported from `src/nsight/`). **Override:** Phase 3 Task 3.6 and Phase 9 stop creating `fixtures.py`/`testing/__init__.py` (already exist); they only add constants/builders.
- **Task 0.11 — `reportbuilder/config.py` test paths.** `ATTENDO_SAV: Path` resolving the repo `input/` `.sav`, and `WORK_DIR`, `ATTENDO_TEMPLATE` (= `work/attendo_blanked.pptx`). **Override:** Phases 2/3/5 use `reportbuilder.config`, NOT `from nsight import config`, honoring the no-`nsight`-import constraint. (A one-line path constant, not a logic import.)

### C8. Test directory layout
All Python tests under `tests/rb/` with subdirs mirroring the package (`tests/rb/ingest/`, `tests/rb/stats/`, `tests/rb/render/`, `tests/rb/render/native/`, `tests/rb/render/image/`, `tests/rb/api/`, `tests/rb/e2e/`). Flutter tests under `ui/test/` + `ui/integration_test/`. Markers: `integration` (real Attendo files / test hive) and `judge` (Claude API). Both registered in `pyproject.toml` (Task 0.1 + 9.5).

### C9. datahive template name
Canonical template ref: **`wftemplate:dataset-report-study`** (generic; NOT `survey-study`), per Phase 4 Task 4.7 and the genericity guardrail. `DataHiveClient.create_case` passes this template_ref.

### Phase / task index
- Phase 0 (Foundation): 0.1 scaffold · 0.2 question types · 0.3 series types · 0.4 report types · 0.5 chart_types · 0.6 fidelity · 0.7 rubrics · 0.8 judge · **0.9 report JSON serde** · **0.10 fixtures** · **0.11 config paths**
- Phase 1 (Spike): 1.1 layout solver · 1.2 native vertical_bar · 1.3 pptx→pdf + preview · 1.4 spike judge · 1.5 GO/NO-GO
- Phase 2 (Ingest): 2.1–2.6
- Phase 3 (Statistics): 3.1–3.7
- Phase 4 (datahive D1/D2/D3): 4.1–4.8
- Phase 5 (Rendering engine): 5.1–5.18
- Phase 6 (Preview/export): 6.1–6.5
- Phase 7 (REST API): 7.1–7.7
- Phase 8 (Flutter UI): 8.1–8.12
- Phase 9 (E2E + coverage audit): 9.1–9.5

The full bite-sized task text for every phase follows. Where a per-phase step's identifiers differ from C1–C9 above, the canonical form wins.

---

## Phase 0 — Foundation

Goal: scaffold the `reportbuilder` package and `tests/rb/`, lock in the Core Types verbatim, and stand up the fidelity + Claude-judge test harness everything else depends on.

> Note (per C1/C7): Task 0.5 uses the canonical chart_type ids from §C1 (`vertical_bar` etc., not `column`). Tasks 0.9/0.10/0.11 (report JSON serde, consolidated fixtures, config paths) are added per §C7 and listed after 0.8.

### Task 0.1: Scaffold `reportbuilder` package, `tests/rb/`, deps, and pytest config

**Files:**
- Create: `src/reportbuilder/__init__.py` and `model/__init__.py`, `stats/__init__.py`, `render/__init__.py`, `testing/__init__.py`, `ingest/__init__.py`, `export/__init__.py`, `store/__init__.py`, `api/__init__.py`
- Create: `tests/rb/__init__.py`, `tests/rb/test_scaffold.py`
- Modify: `pyproject.toml` (add `src/reportbuilder` to wheel packages; add `anthropic>=0.40`, `pdfplumber>=0.11` deps; add `judge` pytest marker)

**Interfaces:** Produces an importable `reportbuilder` package; consumes nothing.

- [ ] **Step 1: Failing test.** `tests/rb/test_scaffold.py` imports `reportbuilder` + each subpackage + `anthropic` + `pdfplumber`.
- [ ] **Step 2: Run — fails** `uv run pytest tests/rb/test_scaffold.py -q` → ModuleNotFoundError.
- [ ] **Step 3: Impl.** `mkdir` the package tree; set wheel `packages = ["src/nsight", "src/reportbuilder"]`; add the two deps; add marker `judge: live Claude-as-judge test, needs ANTHROPIC_API_KEY`.
- [ ] **Step 4: Run — passes** `uv sync && uv run pytest tests/rb/test_scaffold.py -q`.
- [ ] **Step 5: Commit** `rb: scaffold reportbuilder package + tests/rb + deps`.

### Task 0.2: Core Types — `model/question.py`

Implement `ValueLabel`, `Variable`, `Question`, `QuestionModel` exactly as the locked Core Types. Satisfies REQ-C-02/05/06, D-01/03/04/05/06, M-01/02, MV-02. TDD: write `tests/rb/test_question_model.py` asserting frozen dataclasses, field values, `question()`/`variable()` lookup, and `KeyError` on missing → implement the module verbatim from the Core Types block → commit.

### Task 0.3: Core Types — `stats/series.py`

Implement `Cell`, `SeriesResult` (with `cell()` lookup) verbatim. `tests/rb/test_series_result.py`: cell lookup, "Total" always a segment, `base_n` per segment, `KeyError` on missing cell. Satisfies the "SeriesResult is the sole numeric source" constraint, REQ-C-24h.

### Task 0.4: Core Types — `model/report.py`

Implement `SortSpec`, `NumberFormat`, `ElementToggles`, `ChartSpec`, `Report` verbatim. `tests/rb/test_report_model.py`: defaults, topbox codes, ChartSpec build, Report holds charts + render_mode. Satisfies REQ-C-08/10/11/13/14/15, S-*, N-*.

### Task 0.5: `model/chart_types.py` — 11 ids + native/image capability table

**Canonical (§C1):** `class ChartType(str, Enum)` with values `line, pie, vertical_bar, stacked_vertical_bar, horizontal_bar, stacked_horizontal_bar, radar, doughnut, scatter, funnel, combo`. `Capability(native, native_kind, image)` with `native_kind in {"own","stacked_bar_approx","none"}`. `CAPABILITIES` table: the 9 own types (line/pie/vertical_bar/stacked_vertical_bar/horizontal_bar/stacked_horizontal_bar/radar/doughnut/scatter) = own; funnel = stacked_bar_approx (native True); combo = none (native False), image True for all 11. `supports(chart_type, mode)`. Tests: exactly 11 types; image supports all 11; the 9 own; funnel native approx; combo native-excluded. Satisfies REQ-C-13.

### Task 0.6: `testing/fidelity.py` — `numbers_from_pptx`, `numbers_from_pdf`, `assert_series_match`

Implement objective number gates (R5 layers 1&2). `numbers_from_pptx` reads `chart.plots[0].series` values into `{series_name: [float]}`; `numbers_from_pdf` extracts numeric tokens via `pdfplumber`; `assert_series_match(extracted, series, tol=0.5)` asserts every SeriesResult value (per `series.statistic`) appears within tol. `tests/rb/conftest.py` adds a `tmp_native_pptx` fixture (a real one-chart column deck). Tests cover read, match-ok, drift-detected, pdf-token-parse. Satisfies REQ-C-20/21/24f.

### Task 0.7: `testing/rubrics.py` — rubric registry

`RUBRICS: dict[str,str]` + `rubric_for(id)` (KeyError if absent). Seed `"R3-LAYOUT"` (no overlap/truncation, legible, clean). Tests: R3 rubric present, registry str→str, unknown raises. Scaffolds the JUDGE layer.

### Task 0.8: `testing/judge.py` — Claude-as-judge

Implement `JudgeVerdict(passed, reasoning, confidence)`, `judge_image(png_path, rubric, *, requirement_id, extra_context="")`, `judge_pdf(pdf_path, rubric, *, requirement_id) -> list[JudgeVerdict]`, and an internal `_client()` returning `anthropic.Anthropic`. Sends the PNG (base64 image block) + rubric to `claude-opus-4-8` at `temperature=0`, forces a JSON verdict `{passed, reasoning, confidence}`, parses (tolerating ```json fences via a `{.*}` regex). `tests/rb/test_judge.py`: three mocked unit tests (patch `_client`) asserting pass/fail/fenced-json parsing and that `model=="claude-opus-4-8"` + `temperature==0`; plus a `@pytest.mark.judge` live smoke test that renders an obviously-clean matplotlib bar chart and asserts `verdict.passed` (skips without `ANTHROPIC_API_KEY`). Satisfies REQ-C-28b/29b judging.

### Task 0.9: `model/report.py` JSON (de)serialization (§C7)

Add `report_to_json(report) -> str` and `report_from_json(data: dict | str) -> Report` round-tripping every field incl. nested `ChartSpec`/`SortSpec`/`NumberFormat`/`ElementToggles`/`scatter_xy` (tuple<->list). Test: `report_from_json(report_to_json(r)) == r` for a 3-chart native report; tuples restored (not lists). Consumed by Phase 7 + datahive round-trip.

### Task 0.10: `testing/fixtures.py` consolidated builders (§C7)

Provide every fixture the phases reference: `synthetic_sav(tmp_path)->str`, `synthetic_sav_bytes()->bytes`, `tiny_question_model()->QuestionModel`, `tiny_model_and_data()->tuple[QuestionModel,DataFrame]`, `known_series()->SeriesResult`, `known_pcts()->list[float]`, `one_chart_report()->Report`, `two_chart_report()->Report`, `report_json_n_charts(n)->dict`. Tests assert each returns the right type and `one_chart_report().render_mode=="native"`. (Attendo golden constants are appended here in Phase 3 as data.)

### Task 0.11: `reportbuilder/config.py` test paths (§C7)

`ATTENDO_SAV: Path` (repo `input/*.sav`), `WORK_DIR`, `ATTENDO_TEMPLATE = work/attendo_blanked.pptx`. Test: paths resolve under the repo root. Phases 2/3/5 import `reportbuilder.config`, never `nsight.config`.

---

## Phase 1 — Rendering spike (R3, highest unknown)

Goal: prove de-novo native chart construction — `add_chart` + injected raw `c:manualLayout` + data-label positions — survives LibreOffice into a clean, editable, Claude-judged chart, then take an explicit GO/NO-GO on the native path. (Builder converges to the `(ctx)` signature in Phase 5 per §C2; registry key is `vertical_bar` per §C1.)

### Task 1.1: `render/layout.py` — manual-layout solver from measured label lengths

`PlotLayout(x,y,w,h)` (0..1 fractions), `LayoutResult(plot, legend)`, `measure_label_width(text, point_size)` (deterministic char-count estimate, monotonic in length and size), `solve_column_layout(categories, legend_labels, *, point_size=10)` allocating plot vs legend margins so the longest legend label + category labels fit. Tests: width monotonic; coords in unit square; legend right of plot; longer legend label shrinks plot width. Satisfies R3 layout discipline / REQ-C-27a.

### Task 1.2: native vertical_bar builder + raw `c:manualLayout`/`c:dLblPos` injection

Create `render/native/column.py` (filename retained; registry key `vertical_bar` per §C1). Build via `add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, slot.left, slot.top, slot.width, slot.height, chart_data)` from a `SeriesResult`, then inject — via `chart._chartSpace` + `pptx.oxml.parse_xml` + `qn` — a `c:layout/c:manualLayout` plot-area box (from `solve_column_layout`) and an explicit `c:dLbls` with `c:dLblPos val="outEnd"`. Register in `render/native/__init__.py` `NATIVE_BUILDERS["vertical_bar"]`. Tests: registered; native chart with correct series values; zero `MSO_SHAPE_TYPE.PICTURE` shapes; `c:manualLayout` present; `c:dLblPos val="outEnd"` present; re-opens without error (guards REQ-C-29a). Satisfies REQ-C-13/23a/24f. (Step 4 note: if `c:dLbls`/`c:manualLayout` child ordering trips the OOXML schema, fix ordering until the reopen test passes.)

### Task 1.3: `export/pdf_convert.py` + `export/preview.py` (§C3 canonical)

`pptx_to_pdf(pptx_path, out_dir) -> str` runs `soffice --headless --convert-to pdf --outdir <dir> <pptx>` (isolated `HOME` profile dir for determinism; raises on non-zero exit / missing output; module docstring documents the font-bundling drift risk + TODO `OO_FONTDIR`). `pdf_page_to_png(pdf_path, page_index, out_path, *, resolution=150) -> str` via `pdfplumber` `page.to_image().save(..., format="PNG")`. Tests (skip if `soffice`/poppler absent): conversion produces a non-empty PDF; page→PNG non-empty. Satisfies REQ-C-21/28a.

### Task 1.4: Spike end-to-end — native vertical_bar → PDF → PNG → Claude judges layout (JUDGE)

`tests/rb/test_spike_native_column.py`: build a 5-category column chart from a `SeriesResult` fixture; objective half (no key) asserts zero picture shapes + `assert_series_match(numbers_from_pptx(pptx), series)`; `@pytest.mark.judge` half renders → `pptx_to_pdf` → `pdf_page_to_png` → `judge_image(png, rubric_for("R3-LAYOUT"), requirement_id="R3-LAYOUT")` and asserts `verdict.passed`. On FAIL, the verdict reasoning names the layout defect; iterate `solve_column_layout` margins (§9a step-3 render-verify loop) until it passes. Satisfies REQ-C-13/23a/24f/28b + fidelity layer 1.

### Task 1.5: GO/NO-GO checkpoint — native vs image-primary

Create `docs/superpowers/notes/2026-06-22-r3-spike-decision.md` recording three signals (valid OOXML reopen? numbers survive conversion? layout judged clean?). **GO (native primary):** all green → native default; Phase 5 builds the remaining native builders on this pattern; image mode is the per-report fallback. **NO-GO (image primary):** if raw-OOXML layout is impractical → image mode becomes primary, Phase 5 reorders to build image builders first and `render_mode` defaults to `"image"`. Phase 5 task ordering reads from this record.

---

## Phase 2 — Ingest + Question Model

Goal: read a `.sav` into the locked QuestionModel types (names, labels, value labels, user-missing codes, measurement) and resolve multi-question groups via prefix heuristics + user override. (REQ-C-01/02/05/06, D-01..06, M-01/02, MV-02, R2). Grounding (do NOT import the prototype): `pyreadstat.read_sav(path, apply_value_formats=False, user_missing=True)` → `meta.column_names_to_labels`, `meta.variable_value_labels`, `meta.variable_measure`, `meta.missing_ranges`.

### Task 2.1: SAV reader — variables, labels, value labels, measurement
`ingest/sav_reader.py::read_sav(path) -> tuple[pandas.DataFrame, QuestionModel]` (§C5). Map measurement `"scale"→"scale"`, else `"categorical"`. Synthetic `.sav` built in-test via `pyreadstat.write_sav`. Tests: variable names+labels read; value labels as sorted `ValueLabel` tuples; ordinal→categorical, scale stays scale, scale has empty value_labels. Returns raw rows DataFrame (user-missing preserved, not NaN'd). REQ-C-01/02, D-01/03/04/05.

### Task 2.2: SAV reader — user-missing codes + Sysmis
Populate `Variable.missing_values` from `meta.missing_ranges` (discrete `lo==hi` codes; expand `[lo,hi]` ranges across integers). Sysmis (empty→NaN) stays NaN in the frame, NOT in `missing_values`. Tests: user code 99 captured; Sysmis row is NaN; the 99-coded row value survives (`user_missing=True`). REQ-D-06, MV-02.

### Task 2.3: Single questions from the variable set
Build `QuestionModel.questions` = one `Question(qid=_slug(name), kind="single", variables=(name,), text=var.label)` per variable. `_slug` = lowercase, non-alnum→`-`. Tests: one single question per variable, fields correct, `model.question(qid)`/`variable()` resolve. REQ-C-05, M-01.

### Task 2.4: Multi-group auto-suggest via shared-prefix heuristic
`ingest/multi_group.py::suggest_multi_groups(model) -> list[tuple[str,...]]`. Strip trailing `O?\d+` suffix → prefix key; group vars sharing a prefix where the group has ≥2 members AND every member's value-label set ⊆ `{0,1}` (tickbox signature); preserve file order. Tests: `var18O45/46/47` grid suggested; non-binary or singleton not grouped. REQ-M-02, R2.

### Task 2.5: Apply a user grouping override → multi Questions
`apply_groups(model, groups: list[tuple[str,...]]) -> QuestionModel`: replace each grouped variable's single Question with one `Question(kind="multi", variables=members, text=<common label stem>, qid=<group slug>)`; ungrouped keep their single; `variables` dict unchanged. Tests: one multi created, ungrouped stays single, no duplicate singles for grouped members, variables dict intact. (§C6: Phase 7's `apply_grouping(model, variables, kind)` wraps this.) REQ-C-06, M-02.

### Task 2.6: Integration — ingest the Attendo `.sav`
`@pytest.mark.integration`, skip if absent. Uses `reportbuilder.config.ATTENDO_SAV` (§C7/C11). Assert 1001 cases; `var18O45` binary-coded; `var20` value labels incl. `10056="Hyvä"`, `10058="En osaa sanoa"`; the 9-var `var18O45..O53` aided grid auto-suggests as one multi and `apply_groups` makes it a multi question. Fix the `_prefix` regex if the real grid doesn't group (keep generic, no Attendo special-casing). REQ-C-01/02, D-04/05, M-02.

---

## Phase 3 — Statistics engine (the correctness spine, R1)

Goal: turn `Question` + `ChartSpec` + data into the locked `SeriesResult` — correct base rules (single/multi/segment+Total, missing excluded), configurable pct/count/mean, sorting baked into category order — golden-tested vs the Attendo deck. (REQ-C-14/15/16, M-03, MV-01/02, N-01/02/03, S-01/02/03, C-26, R1).

### Task 3.1: Aggregate — raw-count source (in-process duckdb), stable interface
`stats/aggregate.py::aggregate_counts(data, value_var, classifying_var=None) -> dict[tuple[float|None,str],int]` — raw unweighted cell counts keyed by `(value_code, segment_label)`; segment `"Total"` always present; NaN excluded. This is the single seam datahive's D1 primitive later replaces with the identical signature (§7 R1/D1 decouple). Tests: total-only counts exclude NaN; classifier yields per-segment + Total. R1/D1.

### Task 3.2: Base rules — single, multi, segment + Total, missing excluded
`stats/base_rules.py`: `single_base(data, var, segment_filter=None)` (valid excl. `var.missing_values` + NaN); `multi_base(data, vars_)` (respondents with ≥1 valid selection `==1` across the group — respondents-answering, NOT selection count); `segment_bases(data, var, classifying_var)` (per-segment + `"Total"`, excluding missing in both var and classifier). Tests: single excludes NaN+user-missing (base=3); multi base = 2 (not 3 selections); segment bases have Total. REQ-C-14/16, M-03, MV-01/02.

### Task 3.3: Statistics — pct/count/mean, configurable formats
`stats/statistics.py`: `pct(count, base, fmt)` (0..100, round to `fmt.pct_decimals`); `count_value(count, fmt)` (`math.ceil` if `fmt.count_round_up` else round-to-int); `mean(values, var, fmt)` (mean over valid, round to `fmt.mean_decimals`). Tests: whole-pct default + configurable decimals; round-up vs nearest; mean excludes missing + decimals. REQ-C-15, N-01/02/03.

### Task 3.4: Sorting — data_order/pct/topbox_sum/mean/count, default=pct
`stats/sorting.py::sort_categories(rows: list[tuple[str,float,dict]], spec: SortSpec) -> list[str]`. Each row dict carries `{pct,count,mean,data_index,topbox}`; the engine supplies the summed top-box pct from `spec.topbox_codes`. `data_order` preserves `data_index`; default sorts pct desc; stable (pre-order by data_index). Tests: default pct desc; data_order; count/mean bases; topbox_sum ties broken by data order; ascending when `descending=False`. REQ-S-01/02/03, C-26.

### Task 3.5: Engine — `compute(question, spec, data, model) -> SeriesResult`
`stats/engine.py`. Single: categories = non-missing value labels; per-segment cells (pct/count) over `segment_bases`/`single_base`; sort via the Total cell. Multi: categories = member labels; base = `multi_base`; per-member count = respondents with value `==1`. Missing handled entirely via base rules. Tests: single pct excludes missing + sorts by pct (base=4, Good 75/Poor 25); multi base = respondents answering (base=2, BrandA 50/BrandB 100). REQ-C-14/15/16, M-03, R1.

### Task 3.6: GOLDEN — aided awareness exact vs Attendo deck
`@pytest.mark.integration`. Add `ATTENDO_AIDED_VARS`, `DECK_AIDED_AWARENESS` (brand→%) to `testing/fixtures.py` as data (copied from `src/nsight/attendo_bindings.py`, not imported). Build the aided multi question (brand-labeled members), `compute`, assert base ≈ 1001 and each brand pct within ±1 of the deck. REQ-M-03, R1.

### Task 3.7: GOLDEN — general opinion distribution exact vs Attendo deck
`@pytest.mark.integration`. Add `OPINION_PRIVATE_VAR="var20"`, `OPINION_PUBLIC_VAR="var21"`, `OPINION_SERIES_CODES`, `DECK_OPINION_DIST`, `DECK_OPINION_POSITIVE` to fixtures. Compute single-var distribution with DK (10058) kept as a category (override `missing_values=frozenset()` for these vars — the deck's proportions sum to 1.0 over n=1001 incl. DK); assert each category proportion within ±0.01 and positive (Hyvä+Erittäin hyvä) within ±1 of the deck. (This is the one deliberate place "missing always excluded" is relaxed, per the deck's own math — confirm with nSight.) REQ-C-15/16, MV-01.

---

## Phase 4 — datahive changes (D1/D2/D3)

Goal: three generic datahive capabilities so the nSight `DataHiveClient` uses datahive as system of record over REST. Each lands as a **datahive PR**, reviewed against the genericity guardrail (G1): the diff must read as generic containers/datasets/documents/aggregation — no "nSight/survey/chart" in any code, path, payload key, or template name. datahive tests: `@pytest.mark.unit` mock-Request (like `tests/api/test_references_rest.py`), `@pytest.mark.integration` MCP/REST (like `tests/integration/test_projects.py`); run `make test-unit` / `make test-integration`. Grounding verified: `attach_doc` (service.py:247) calls `remember(text=…, classify=True)` with no `reference_id`; `TabularStore.query` (storage/tabular.py:253) is `SELECT *…WHERE…LIMIT` — no GROUP BY; projects have MCP tools but no REST router.

### Task 4.1: Report-JSON raw-source round-trip on attached docs (D3, service layer)
Add `attach_raw_doc(*, hive, store, tenant_id, actor, project_id, label, name, reference_id, text) -> dict` and `read_raw_doc(*, hive, store, tenant_id, reference_id) -> str` to `datahive/projects/service.py`. `attach_raw_doc` calls `remember(..., classify=False, reference_id=...)` (opaque raw record, versioned-replace on same id); `read_raw_doc` resolves via `store.find_resource_record_by_reference_id(..., workspace_uuid=projects_workspace(tenant_id))` then `hive.reveal_source`. Extend `FakeHive`/`FakeStore` in `tests/unit/test_projects_service.py` to honour `reference_id` overwrite + the `workspace_uuid=` kwarg. Tests: byte-exact round-trip; re-attach same id versioned-replaces. Guardrail: only generic "raw doc"/"reference_id"/"opaque source". D3, unblocks REQ-C-08.

### Task 4.2: MCP adapter for raw-doc attach/read (D3 parity)
Add `_call_attach_project_raw_doc`/`_call_read_project_raw_doc` to `datahive/api/routers/mcp_server.py` mirroring `_call_attach_project_doc` (write guard + consent + `_viewer_identity`); register in the dispatch dict + add generic tool schemas (`attach_project_raw_doc`, `read_project_raw_doc`). Integration test in `tests/integration/test_projects.py`: attach exact JSON under `reference_id`, read back identical, re-attach replaces. Shared-service-layer parity (design §5.2). D3.

### Task 4.3: Projects REST router — read endpoints (D2)
Create `datahive/api/routers/projects.py` (`/api/v1/projects`): `GET ""` → `{count, projects:[{id,name}]}` and `GET /{project_id}` → status, delegating to `_ps.list_projects`/`_ps.project_status`, ABAC mirroring the MCP path (`filter_admitted_records`, 404 unless admitted). Register in `app.py`. Lift `_effective_read_scope`/`_viewer_identity` to a shared `api/_authscope.py` if module-private to `mcp_server`. Unit tests (mock Request): list returns admitted `{id,name}`; status 404 when not admitted. D2, backs `DataHiveClient.list_cases`.

### Task 4.4: Projects REST router — write endpoints (D2)
Add `POST /api/v1/projects` (create from template), `POST /{id}/docs` (→ `_ps.attach_raw_doc`, lossless report save), `POST /{id}/advance`. Reuse the MCP write guard (`_entity_write_guard`→403), consent gate; map `ProjectError`→400. Pydantic bodies use generic keys (`name`/`template_ref`/`label`/`reference_id`/`to_phase`). Unit tests: create denied (403) for read-only auth; docs POST returns `{reference_id}`; advance gate failure → 400. D2, backs create_case/attach_material/save_report.

### Task 4.5: Generic aggregation primitive — service layer (D1)
Add `TabularStore.group_by_counts(*, item_id, group_columns, filters=None, scope_groups=None, scope_ceiling=None) -> {"dimensions","cells":[{"key","count"}],"total"}` to `storage/tabular.py`, reusing `_user_columns`/`_build_user_filter`/ABAC clauses from `query`, validating group columns (`unknown_column:` else), parameterised SQL with `_safe_ident` group cols. Create `datahive/aggregation/service.py::aggregate(...)` thin wrapper (dict filters → `FilterClause`, `asyncio.to_thread`). Unit tests: single-dimension counts; cross-tab with filter; unknown column raises. Guardrail: `group_by_counts`/`cells`/`dimensions` only — no statistic/percentage/survey concept. D1.

### Task 4.6: Aggregation REST router (D1)
Create `datahive/api/routers/aggregation.py` (`POST /api/v1/aggregation/{item_id}` body `{group_columns, filters}` → `{dimensions,cells,total}`), ABAC scope from the bearer (`auth.scope.groups`, `regulatory_ceiling`), `TabularFilterError`→400. Register in `app.py`. Unit test: counts reshaped correct; malformed column → 400. D1, backs `DataHiveClient.aggregate`.

### Task 4.7: Generic multi-phase study workflow template (D2 supporting)
Define `template_ref="wftemplate:dataset-report-study"` (§C9, generic — NOT "survey") as pure data via existing `create_workflow_template`: phases `ingested → reported(required_docs:[{label:"report"}]) → delivered(is_terminal)`. Integration test (style of `test_projects.py`): create template → ref matches; project starts at `ingested`; advance to `reported` gate-blocked until a `report` raw-doc attached (4.2), then advances; `delivered` → closed. No new datahive code (`_validate_template_spec` accepts it). D2.

### Task 4.8: INTEG — nSight `DataHiveClient` vs a running test hive
`tests/rb/test_datahive_integration.py` (nSight repo, `@pytest.mark.integration`, skip unless `DATAHIVE_TEST_URL`/token set). Implement `DataHiveClient` methods as thin REST calls: `create_case`→`POST /projects` with the dataset-report-study template; `attach_material`/`save_report`→`POST /{id}/docs` (raw-doc, stable reference_id); `load_report`→`read_project_raw_doc`; `aggregate`→`POST /aggregation/{material_id}`. Test: create_case + list; report JSON byte-exact on load; versioned replace; aggregate counts match in-process recompute (D1 parity). Covers REQ-C-03/04/07/08, D1/D2/D3.

---

## Phase 5 — Rendering engine

Goal: `Report` + per-chart `SeriesResult` → completeness-checked `.pptx` — native editable charts (9 own types + funnel stacked-bar approximation), guaranteed-clean matplotlib images (all 11), uniform element profile, template `StyleSpec` — dispatched by `render_mode`, native mode provably free of picture shapes. Assumes Phase 1's `render/base.py` (locked `ChartRenderer`/`Slot`/`StyleSpec`/`RenderContext`), `render/layout.py`, the spike's native vertical_bar, and the judge/fidelity harness. Registry keys = canonical chart_type ids (§C1); builders take `(ctx: RenderContext)` (§C2).

### Task 5.1: StyleSpec loader from a template `.pptx`
`render/style_spec.py::load_style_spec(template_path) -> TemplateStyleSpec` implementing `font_for(element_class)->(name,size)`, `color_for(series_index)->hex`, `slot(name)->Slot`, `slots()->dict`. Element classes: title/axis_values/axis_names/category_names/data_labels/legend/n_annotation/filter_var. Reads slide dims, placeholder rects→Slots, fonts via `style:<class>` shape-name convention, a fixed palette. Tests: documented font defaults; slots from placeholders; font class read from template. REQ-C-25/27a.

### Task 5.2: Interim StyleSpec from the Attendo deck
`attendo_interim_spec() -> TemplateStyleSpec` loading `work/attendo_blanked.pptx` (12192000×6858000 EMU). Add `spec_source`/`matches_client_spec=False` markers (REQ-C-27b blocked). Tests: dimensions; blocked marker. REQ-C-27a (proxy), C-27b (blocked marker).

### Task 5.3: Element profile — `render/elements.py`
`apply_elements(chart, ctx)` applies the nine elements per `ctx.spec.elements` with StyleSpec fonts; `add_n_annotation(ctx)` / `add_filter_annotation(ctx)` add slide text boxes (N from `series.base_n["Total"]`; filter var name); `number_format_code(fmt, statistic)` (`'0"%"'`/`'0.0'`/`'0'`). Tests: format codes; title present+font; data-labels/legend/axes toggle on and off; N + filter annotations gated. REQ-C-24a..i, C-25.

### Task 5.4: Native vertical_bar refinement → registry-ready (§C2 convergence)
Refactor the spike's `column.py` to `build_vertical_bar(ctx: RenderContext) -> None`; add shared `series_chart_data(series, statistic) -> CategoryChartData`; apply series colors (`series.format.fill.solid()` + `color_for(i)`), `apply_elements`, layout. Register `NATIVE_BUILDERS["vertical_bar"]`. Tests: `series_chart_data` maps SeriesResult; native real chart with `c:externalData` (embedded workbook) + correct values + zero pictures; registry has the builder. REQ-C-13/23a/b.

### Task 5.5: Native horizontal_bar + stacked column/bar
`render/native/bar.py`: `build_horizontal_bar` (BAR_CLUSTERED), `build_stacked_vertical_bar` (COLUMN_STACKED, overlap=100), `build_stacked_horizontal_bar` (BAR_STACKED, overlap=100). Tests: barDir="bar"; stacked grouping + overlap + legend; zero pictures. REQ-C-13, C-24b/g.

### Task 5.6: Native line, pie, doughnut
`build_line` (LINE_MARKERS), `build_pie` (PIE, per-point colors), `build_doughnut` (DOUGHNUT). Tests: lineChart + value-axis ticks; pieChart points==categories + per-point fill + data labels; doughnutChart; all zero pictures. REQ-C-13, C-24b/c/f.

### Task 5.7: Native radar
`build_radar` (RADAR_MARKERS, one series per segment, color_for). Test: radarChart, series==fixture, legend present, zero pictures. REQ-C-13, C-24g.

### Task 5.8: Native scatter (x/y from `ChartSpec.scatter_xy`)
`xy_chart_data(series, scatter_xy) -> XyChartData`; `build_scatter` (XY_SCATTER). Tests: xy pairs mapped; native scatterChart + both axes + zero pictures; raises `ValueError("scatter requires scatter_xy")` when `scatter_xy is None`. REQ-C-13, C-24c/d.

### Task 5.9: Native funnel as stacked-bar approximation (transparent spacer, not a picture)
`funnel_spacer_values(values)` = `(max-value)/2` per category; `build_funnel` (BAR_STACKED with leading transparent spacer series via `series.format.fill.background()` + value series, overlap=100, data labels on value series only). Tests: spacer centers bars; native barChart/stacked, two series, spacer noFill, value series correct, **zero `MSO_SHAPE_TYPE.PICTURE`**. REQ-C-13, C-23a.

### Task 5.10: Combo excluded from native mode
`render/native/__init__.py` defines `NativeUnsupportedError`; `build_combo_native(ctx)` always raises it (message names "combo" + "image mode"); register `NATIVE_BUILDERS["combo"]`. Test: raises with the right message. REQ-C-13.

### Task 5.11–5.13: Image builders (matplotlib → PNG → `add_picture`), all 11 types
`render/image/_mpl.py` (`render_png(fig, ctx)`, `place_picture(ctx, png)` → `add_picture`), `IMAGE_BUILDERS` registry. 5.11: vertical_bar/horizontal_bar/stacked variants/line. 5.12: pie/doughnut/radar(polar)/scatter. 5.13: real funnel (centered barh) + combo (bars + twinx line). Tests per builder: exactly one picture shape, slot-sized, valid PNG (PIL opens); 5.13 final test asserts `set(IMAGE_BUILDERS)` == all 11 canonical ids. REQ-C-13 image mode.

### Task 5.14: Deck assembly — `render/deck.py` (§C2 canonical entry point)
`render_report(report, series_by_ref: dict[str, SeriesResult], style: StyleSpec) -> Presentation`: open template, per `ChartSpec` resolve `style.slot(spec.template_slot)`, build `RenderContext`, dispatch `NATIVE_BUILDERS`/`IMAGE_BUILDERS` by `report.render_mode` keyed on `spec.chart_type`. `render_to_file(report, series_by_ref, style, out_path) -> str`. Tests: native dispatch → each target slide has a `c:chart`, zero pictures; image dispatch → one picture, no chart; `render_to_file` reopens (REQ-C-29a). REQ-C-13/17/29a.

### Task 5.15: Completeness + native "no picture shapes" gate
`assert_complete(prs, report)` (chart count across deck == `len(report.charts)`, no extra/missing → `CompletenessError`); `assert_no_pictures_in_chart_slots(prs, report, style)` (native only → zero pictures in chart slots, else `NativePurityError`). `render_report` calls both. Tests: completeness pass + extra-chart fails; native no-picture pass + funnel doesn't trip it + injected picture fails; image mode allows pictures (gate is a no-op, completeness counts pictures). REQ-C-18/23a.

### Task 5.16: RENDER fidelity — chart-data series == SeriesResult, per type
Parametrized over the 9 native-own types + funnel: render each → `assert_series_match(numbers_from_pptx(path), fixture_series)` (funnel: value series only, spacer skipped in extraction). Parametrized element-presence test: with all toggles, each type has title/data-labels/legend(≥2 series)/axis ticks/category names/N+filter annotations in the OOXML. REQ-C-24a..i, C-18.

### Task 5.17: JUDGE — representative types render→PDF→PNG→Claude
Add `CHART_CLEANLINESS_RUBRIC` to `rubrics.py`. `@pytest.mark.judge` tests for vertical_bar, stacked_horizontal_bar, radar, native funnel, and one image-mode combo: render → `pptx_to_pdf` → `pdf_page_to_png` → `judge_image(png, CHART_CLEANLINESS_RUBRIC, requirement_id="REQ-C-24")`, assert `verdict.passed` (tune builders/layout until clean). REQ-C-24, C-28b.

### Task 5.18: Capability table ↔ registry coverage gate
Test that `NATIVE_BUILDERS` keys == all 11 canonical ids with `combo` raising `NativeUnsupportedError` and the other 10 building real charts (cross-check `chart_types.CAPABILITIES`); `IMAGE_BUILDERS` == all 11 and superset of native-capable. Reconcile `chart_types.py` to match. REQ-C-13.

---

## Phase 6 — Preview / export + fidelity gate

Goal: `Report` → `.pptx` → `.pdf` (LibreOffice) → dual preview views → three-layer fidelity gate. EXTENDS the Phase 1 export modules (§C3), does not recreate them.

### Task 6.1: PPTX artifact builder — `export/pptx_build.py`
`build_pptx(report, model, data, out_path) -> str`: compute `series_by_ref` (loop `ChartSpec` → `engine.compute(model.question(spec.question_ref), spec, data, model)`), load the StyleSpec (`attendo_interim_spec()`), call `render_to_file(report, series_by_ref, style, out_path)` (§C2). Test: writes a `.pptx` that reopens with the ChartSpec count of chart slides (completeness). REQ-C-22/18.

### Task 6.2: `pdf_page_count` + conversion assertions (extends Phase 1 `pptx_to_pdf`)
Add `pdf_page_count(pdf_path) -> int` (via `pdfinfo`) to `export/pdf_convert.py`. CONV test (skip without LibreOffice): `pptx_to_pdf` → valid `%PDF-` + `pdf_page_count == slide count`. REQ-C-21/28a.

### Task 6.3: Dual-view preview (extends Phase 1 `export/preview.py`)
Add `rasterize_pages(pdf, out_dir, *, dpi=150) -> list[str]` (via `pdftoppm -png`), `slide_view`/`page_view` (both call it — two labels over one PDF). Test (skip without poppler): both views yield the same N PNGs (≥2), real PNG magic. REQ-C-19a/b, C-20.

### Task 6.4: PDF number extraction (already in `testing/fidelity.py` from 0.6)
Confirm `numbers_from_pdf` extracts the SeriesResult data-label numbers from a rendered PDF (CONV test against a known one-chart report, ±0.5). The LibreOffice-drift guard (§10 layer 2). REQ-C-20.

### Task 6.5: Three-layer fidelity gate — `export/fidelity_gate.py`
`run_fidelity_gate(report, model, data, pptx_path, pdf_path, series, *, tol=0.5) -> None`: native → layer1 `assert_series_match(numbers_from_pptx, series)` + layer2 assert `numbers_from_pdf` contains every series value; image → layer3 assert the `series` that fed the builder == `engine.compute` output (identity check, §C4 — no `data_arrays_for`). Tests: native passes; tampered series raises. REQ-C-20, R5.

---

## Phase 7 — REST API + report orchestration

Goal: FastAPI over the backend — cases/materials/questions/reports/render — each router thin over `DataHiveClient` + the engine; `TestClient` tests with a mock client + one live-hive INTEG.

### Task 7.1: App skeleton + DI — `api/app.py`, `api/deps.py`
`create_app(client=None) -> FastAPI` (injects a mock client for tests), `get_client()` dependency. Test: `/health` + injected mock reachable. REQ-C-30.

### Task 7.2: Cases router — `routes_cases.py`
`POST /cases {name} -> {case_id}` (`create_case`), `GET /cases` (`list_cases`). Test (mock client): create returns id + `create_case` called; list returns rows. REQ-C-03/07.

### Task 7.3: Materials router — `routes_materials.py`
`POST /cases/{case_id}/materials` (multipart `.sav`): write bytes to temp, `read_sav(tmp)` → `(df, model)` (§C5), `attach_material(case_id, name, raw, summary)`; return `{material_id, question_count}`. Test (mock client, patch `read_sav`): ingest + attach called with case id. REQ-C-01/04.

### Task 7.4: Questions router — `routes_questions.py`
`GET /materials/{material_id}/questions` (browse), `PUT .../grouping {variables, kind}` (`apply_grouping` wrapper §C6). `load_model_for_material` reads the material's `.sav` source from datahive → QuestionModel. Tests (patch loader): list ≥1 question; set multi grouping returns `kind=="multi"`. REQ-C-05/06, M-02.

### Task 7.5: Reports router — `routes_reports.py`
`POST /cases/{id}/reports` (create), `PUT .../{rid}` (versioned save), `GET .../{rid}` (exact JSON via `load_report`), `DELETE .../{rid}`, `POST .../{rid}/duplicate {name}` (load → new name → `save_report(case_id, None, ...)`). Uses `report_to_json`/`report_from_json` (0.9). Tests: create→load round-trips exact charts (arbitrary count); duplicate yields new id with `save_report` id arg `None` + new name baked in. REQ-C-08/09/10/11/12.

### Task 7.6: Render router — `routes_render.py`
`POST /cases/{id}/reports/{rid}/render {view?}` → `orchestrate_render`: `report_from_json(load_report)` → load material model+data → `build_pptx` → `pptx_to_pdf` → `slide_view`/`page_view` → `{pptx, pdf, preview:[png]}`. Test (patch `orchestrate_render`): returns artifact + preview paths. REQ-C-19/21/22.

### Task 7.7: Live-hive integration (INTEG)
`tests/rb/api/test_integration_hive.py` (skip unless `NSIGHT_TEST_HIVE_URL`): create case → upload material → create report → GET asserts exact JSON round-trip; list shows the case. Normalize JSON in the client if needed until byte-exact. REQ-C-03/04/07/08, D3.

---

## Phase 8 — Flutter UI (thin)

Goal: a Prima-Volta-shell Flutter web app (`ui/`) over the REST API — Case list/create, Case detail split into a **Data** area (question browser) and **Reports** area (builder + PDF/PPT preview + duplicate) — zero charting logic, verified by widget tests, a fake-backend smoke test, and a Claude judge screenshot test. The Flutter app does NOT exist yet under `proto/`, so 8.1 scaffolds it new (copying Prima Volta, not editing the primavolta repo). Run `cd ui && flutter test`.

- **8.1 Shell scaffold** — `ui/pubspec.yaml` (flutter_riverpod, dio, go_router, file_picker), `config/theme.dart`, `shell/app_shell.dart` (3-panel desktop / bottom-nav mobile), `icon_rail.dart`, `bottom_nav.dart` (`NavSection {cases, settings}`), `main.dart`. Widget test: desktop shows list+detail at 1200px. (REQ-U-04 frame)
- **8.2 API client + providers** — `core/services/nsight_api.dart` (Dio; methods mirror the REST routes), `core/providers/api_provider.dart`, models `CaseRecord`/`QuestionItem`/`ReportDef`. Test: `listCases` parses `GET /cases` via a mock adapter.
- **8.3 Case list + create + delete** — `features/cases/cases_list.dart`, `new_case_dialog.dart`, `providers/cases_provider.dart`. Widget test (ProviderScope override): shows cases + add button. REQ-U-04, C-03/07.
- **8.4 Case detail — Data/Reports tabs** — `features/cases/case_detail.dart` with fixed `Data`/`Reports` tabs + dynamic open-report tabs (close icon). Test: both tabs present. REQ-U-04.
- **8.5 Data area — question browser** — `features/data/question_browser.dart` (list, sort dropdown [data order/percentage/top-box/mean/count → REQ-C-26], per-row single/multi `SegmentedButton`, inline edit, delete), `edit_question_dialog.dart`, `providers/questions_provider.dart`. Test: lists questions, toggles single/multi, delete calls api. REQ-U-05, C-05/06/26.
- **8.6 Reports area — list/create/duplicate** — `features/reports/reports_list.dart`, `new_report_dialog.dart` (name + native/image toggle), `providers/reports_provider.dart`. Test: duplicate calls api with new name. REQ-U-06, C-07/09.
- **8.7 Report builder** — `features/reports/report_builder.dart` + `chart_spec_editor.dart` (dropdowns: question, chart type [11 ids §C1], statistic [pct/count/mean], classifying var, sort basis; decimals fields; element checkboxes; combo disabled when native). Save → `saveReport`. **No charting logic.** Test: add-chart row exposes exactly one chart-type dropdown (11 entries) + statistic + classifying var; save sends one ChartSpec map. REQ-C-10/11/13/14/15/26.
- **8.8 Preview — PPT/PDF toggle** — port `shell/pdf_view.dart`/`pdf_view_web.dart` verbatim; `features/reports/report_preview.dart` (Render → `POST /render` → fetch `preview.pdf`; `SegmentedButton(['Slides (PPT)','Pages (PDF)'])` over the one PDF). Test: toggle + Render button present, Render calls api. REQ-C-19a/b.
- **8.9 Terminology lint + keyboard** — `core/glossary.dart` (Case/Question/Report/Variable/Chart/Single/Multi); `test/ui_terminology_test.dart` (objective lint: forbidden synonyms don't co-occur with canonical terms in user-facing strings); a focus-traversal widget test. REQ-U-02/10.
- **8.10 Integration smoke vs fake backend** — `test/support/fake_nsight_api.dart` (in-memory), `integration_test/app_smoke_test.dart` (Case→create→Data set multi→Reports→create→add chart→render). REQ-U-01 umbrella (exercises C-03..09/19/26).
- **8.11 JUDGE screenshot test** — `test/golden/ui_screenshot_test.dart` writes PNGs of QuestionBrowser + ReportBuilder; `tests/rb/test_ui_judge.py` (`@pytest.mark.judge`) runs it then `judge_image` with rubrics `UI_QUESTION_ORG` (REQ-C-05) + `UI_BUILDER_USABILITY` (REQ-U-11). REQ-C-05, U-11.
- **8.12 Window controls scaffold (DEFER)** — `features/reports/report_window.dart` (close icon → `onClose`; drag-handle size). Built cheaply, marked `// DEFER REQ-U-07/08/09`. Test: close icon fires `onClose`.

---

## Phase 9 — End-to-end suite + coverage audit

Goal: the "automated end to end, Claude as judge" deliverable + a coverage-audit gate.

- **9.1 Full-pipeline E2E (synthetic, both modes)** — `tests/rb/e2e/test_pipeline_synthetic.py`: synthetic `.sav` (1 single + 1 multi-group + 1 scale) → QuestionModel → 3-ChartSpec Report; for `mode in (native, image)`: `build_pptx` → `pptx_to_pdf`; assert `assert_series_match(numbers_from_pptx, series)` (native) + `numbers_from_pdf` contains values + page count == 3. `@pytest.mark.judge` sibling: `judge_pdf(pdf, CLEAN_LAYOUT, requirement_id="REQ-C-28b")` every page passes. The E2E deliverable.
- **9.2 Attendo .sav E2E (golden through the chain)** — `tests/rb/e2e/test_pipeline_attendo.py` (`@pytest.mark.integration`): reproduce a known Attendo slide (in-file segment cross-tab, §7), render both modes, assert `numbers_from_pdf` data labels match the golden `SeriesResult` within tol; `@pytest.mark.judge` variant judges presentation quality (REQ-C-28b/29b). R1 + E2E.
- **9.3 REST API E2E vs test hive** — `tests/rb/e2e/test_api_e2e.py` (`@pytest.mark.integration`): `TestClient` runs POST cases → upload material → GET questions → PATCH question → POST reports → duplicate → render → GET `preview.pdf`; assert exact JSON round-trip (C-08), new id+name on duplicate (C-09), `application/pdf` non-zero (C-19/21). Add a `test_hive` conftest fixture.
- **9.4 Coverage-audit test (enforce a test per IN/DEFER REQ)** — `testing/req_catalog.py` parses the requirements markdown (ID + Scope, expanding lettered sub-IDs C-19a/b, C-23a/b, C-24a..i, C-27a/b, C-28a/b, C-29a/b; excluding OUT REQ-X-*, SCOPE-NOTE REQ-D-07, BLOCKED REQ-C-27b). `tests/rb/test_req_coverage.py` greps `tests/**/*.py` + `ui/test/**` + `ui/integration_test/**` for `REQ-<id>` tokens and FAILS listing any uncovered IN/DEFER id. Backfill `REQ-` markers in test docstrings across phases until empty. **This is the gate that proves every requirement is tested.**
- **9.5 CI lanes** — `.github/workflows/ci.yml`: objective lane (`uv run pytest -m "not judge and not integration"` + `flutter test`, always); judge lane (`-m judge`, gated on `secrets.ANTHROPIC_API_KEY`); integration lane (`-m integration`, gated on a test hive + LibreOffice). Register both markers in `pyproject.toml`.
