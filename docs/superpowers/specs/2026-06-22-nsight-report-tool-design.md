# nSight self-service report tool — design spec

_Date: 2026-06-22 · Status: draft for review_

Source requirement: `Mitä työkalun pitäisi tehdä.docx` ("What the tool should do"),
plus decisions taken in the brainstorming session recorded inline below.

Every source-document statement is enumerated and traced in the companion
**[requirements catalog](./2026-06-22-nsight-report-tool-requirements.md)** (REQ-* IDs); design
sections below reference those IDs.

---

## 1. Goal

Build a **self-service survey report builder**: a user imports SPSS `.sav` data,
browses it question-by-question, picks variables and a chart type per variable, and
composes/saves/edits/duplicates multiple PowerPoint reports, previews them on screen, and
exports **editable PPT + PDF**. This is a generic interactive tool — there is no
natural-language brief, no LLM-written narrative, and no target of *reproducing a specific
deck's data/narrative* (that deck-reproduction goal belonged to the earlier prototype, a
different product). Charts must still follow a **styling/layout spec** (REQ-C-27a/b); that is a
generic "match the house style" requirement, distinct from reproducing a particular deck. We
use the Attendo deck only as a *proxy* for that style spec until the formal one exists (R4).

## 2. Framing & decisions taken

- **Fresh design.** We are not constrained to reuse the prototype's code; we keep its
  *learnings* (deterministic numbers, the image experiments in `chart_lab/`, the
  fidelity-harness idea). **Caveat (verified):** the prototype's "native chart" path only does
  `shape.chart.replace_data(...)` into charts that already exist in a fixed template
  (`render/fill_chart.py`); it never creates a chart from scratch. The new tool must build
  charts de-novo with `add_chart` + raw-OOXML layout — **unprototyped work** (see R3/§9a).
- **datahive is the system of record** (not a separate Postgres). Cases/Materials/Reports
  live in datahive's **projects app**, so they are reachable for agentic discussion
  (Claude/ChatGPT) over MCP.
- **Genericity guardrail (standing constraint):** datahive's genericity and architectural
  simplicity must not be endangered by nSight-specific needs. Every change to datahive must
  be describable *without* the words "nSight", "survey", or "chart". nSight-specific meaning
  lives only in the nSight backend and inside opaque document payloads datahive never parses.
  (Note: datahive *already* ships an SPSS/SAV connector and a `survey_codebook` MCP tool that
  predate this guardrail; the guardrail governs **new** changes, and those existing surfaces
  are reused, not extended with nSight specifics.)
- **Frontend is deliberately thin** and not the focus of this phase. The risky elements are
  all backend Python. Recommended frontend: **Flutter web**, copying Prima Volta's shell
  (icon rail, context panel, `pdf_view`). Frontend holds **zero charting logic**.
- **Backend is near-stateless** Python: aggregation client + statistics engine + rendering
  + preview/export + a thin REST API. Operational state only (render-job queue, caches).
- **Scope of this phase:** cover all of the most risky elements (R1–R6 + datahive
  dependencies below). Breadth polish and the docx's "EI TÄRKEÄ" items (user management,
  template-management UI, history import) are out of scope.
- **Numeric values only.** Per the docx, this scope targets numeric variables; string-valued
  variables are out of scope, and differing numeric SPSS types are handled uniformly
  (REQ-D-02). Deferred UI-window details (REQ-U-07/08/09/11) land in the UI phase.

## 3. Architecture overview

```
┌────────────────────────────────────────────┐
│  Flutter web app  (copy Prima Volta shell)  │   thin: forms, lists, PDF preview
│  no charting logic                          │
└──────────────────┬─────────────────────────┘
                   │ nSight REST API
┌──────────────────▼─────────────────────────┐
│  nSight backend (Python, near-stateless)    │
│  • Question Model builder                   │
│  • Statistics engine  (Layer 2: survey      │
│    semantics → SeriesResult)                │
│  • Rendering engine (native | image)        │
│  • Preview/export (PPT→PDF)                  │
└───────┬───────────────────────────┬─────────┘
        │ datahive REST API         │ datahive REST API
┌───────▼───────────────────────────▼─────────┐
│  datahive  (system of record + data plane)   │
│  • projects app: Project=Case, attached docs │
│  • SPSS connector (SAV + codebook)           │
│  • aggregation primitive (Layer 1, generic)  │
│  • MCP: list_projects/recall/inventory/…     │ ← agentic discussion of cases & reports
└──────────────────────────────────────────────┘
```

- **nSight backend → datahive** uses the **REST API** (typed, deterministic, cross-process),
  not MCP. MCP is reserved for *agent* access to the same data.
- datahive's own surfaces follow a **shared-service-layer** rule: each app has one service
  module owning logic + auth/ABAC/audit; REST and MCP are thin adapters over it.

## 4. Domain model on datahive (projects app)

| nSight concept | datahive generic construct |
|---|---|
| Workspace | the dedicated `projects_workspace` (per-tenant isolated) |
| **Case** | a **Project**, created from a generic `wftemplate:survey-study` template (phases optional, e.g. *ingested → reported → delivered*; may be single-phase) |
| **Material (SAV)** | an **attached project doc** (`label="material"`): text = codebook summary + pointer to the SPSS-connector-ingested item; chunked + indexed → recall-able |
| **Report** | an **attached project doc** (`label="report"`): source = exact report-definition JSON, with a human-readable preamble so `recall`/an agent can discuss it |
| **Generated PPT/PDF** | artifact docs (`label="artifact"`) under the project |
| List / navigate cases | existing generic MCP+REST: `list_projects`, `project_status`, `recall`, `inventory` |

Grounded in datahive source: projects already expose `create_project`, `list_projects`,
`project_status`, `attach_project_doc`, `mark_project_milestone`, `advance_project_phase`,
`create_workflow_template` over MCP (these are the MCP adapter names; they delegate to the
service functions `create_from_template`, `attach_doc`, etc.). Templates are "validated as
data — no domain logic hardcoded"; the projects app is a first-class **generic** app (example
app namespaces in datahive's own schema are `notes/companies/projects/people/research/calendar`
— so "projects" is a native fit, no nSight-specific concept added).

**The report definition is opaque to datahive.** datahive stores, links, and serves it; it
never parses a ChartSpec or knows what a "base rule" is. **New wiring required (not existing
behavior, see D3):** today `attach_doc` calls `remember(text=…, classify=True)` *without* a
`reference_id` and treats the doc as chunked/indexed prose. Storing the report JSON as an
exact, `replace_source`-versioned raw record (which REQ-C-08's versioned-replace depends on)
means attaching docs with a stable `reference_id` and reading back via `reveal_source` — a
small but real addition to the projects service, not a confirmation of current behavior.

## 5. datahive changes required (all generic)

1. **Projects REST router** — so the projects app has REST in addition to MCP (consistency;
   the nSight backend calls it over REST). _D2_
2. **Shared-service-layer refactor** — REST and MCP both become thin adapters over each app's
   service; auth/ABAC/validation/audit move into services. Newer apps (projects, entities,
   tasks) already follow this; the work is consolidating the **stragglers** that still embed
   auth + direct DB access inline (e.g. `references.py`'s `_ref_visible`, and a handful of
   peers) — several routers, not just one. _D2_
3. **Aggregation primitive** — a generic "filtered GROUP BY / cross-tab cell counts over a
   tabular item". Verified **genuinely new**: today's `accessors/sql.py` + `retrieval/tabular.py`
   are row-level only (`SELECT … WHERE … LIMIT`), with **no GROUP BY / cross-tab**. Returns raw
   counts, not survey statistics. Reusable by any consumer. _D1_ — but **not on the hard
   critical path**: see §7 (the nSight engine can aggregate client-side from rows until D1 lands).
4. **`survey-study` workflow template** — pure data stored as a `wftemplate`, not code.
5. **Confirm exact structured-JSON round-trip** of an attached doc's raw source. _D3_

Each item passes the genericity guardrail (none mention nSight/survey/chart).

## 6. Question Model (R2)

On material ingest, parse the SAV (via datahive's SPSS connector) into a normalized
**Question Model** independent of SPSS quirks:

- **Variable**: name, label (→ slide question text), measurement level
  (categorical/scale), value→label map, **per-variable missing set** — both Sysmis-empty
  *and* user-defined missing codes (e.g. 99 = "En tiedä").
- **Question** (the reporting unit):
  - **Single** = one variable, one chosen option.
  - **Multi** = a **group of 0/1 variables** forming one question. This grouping is **not in
    the file**; the model stores it explicitly. On ingest we **auto-suggest** groups via
    naming heuristics (shared prefix, e.g. `var18O1..O9`); the user confirms/edits in the
    question browser. Each multi question records its base rule.

Persisted alongside the material so re-opening is instant and grouping edits are durable.
This is the contract every downstream component reads.

## 7. Statistics engine (R1 — the correctness spine)

Layer 2, **in the nSight backend** (survey semantics; golden-tested; nSight-owned). Pure
functions: `compute(question, statistic, base_rule, classifying_var, data) → SeriesResult`.

**Data source (decouples R1 from D1):** the engine consumes raw counts from datahive's
aggregation primitive (Layer 1, D1) *when available*, but can equally fetch respondent rows
over datahive's existing row-level API and aggregate **in-process** — exactly what the
prototype does today against the DuckDB store. So the correctness spine is **not hard-blocked**
on the cross-team D1 deliverable; D1 is the clean, scalable integration, the in-process path is
the fallback available now.

- **SeriesResult** = normalized table `categories × segments → {pct, count, mean, N}` + overall
  base N. **Every chart, export, and preview reads only this shape** — nothing downstream
  re-derives numbers.
- **Base rules** (where correctness lives):
  - *Single*: base = valid responses excluding that variable's missing set.
  - *Multi*: base = respondents who answered the set (≥1 valid in the group), **not** the
    selection count. Percentages and counts both available.
  - *Classifying variable*: the classifier is **any in-file categorical variable** the user
    picks; compute per segment **plus a Total column**, each segment carrying its own N.
    (Note: this is distinct from the prototype's *deck-derived* populations that came from
    survey routing. `COVERAGE.md` confirmed in-file segment bases reproduce — e.g. deck slide
    16 — so golden tests for this feature use in-file segments, not routing-derived ones.)
- **Statistics** (REQ-N-01/02/03): percentage (whole by default, configurable decimals),
  count (whole numbers; rounding **upward** may be applied — configurable, per docx), mean
  (configurable decimals, scale vars).
- **Sorting** (computed here, baked into SeriesResult order so renderers are dumb): by data
  order, percentage magnitude, **top-box sum** (e.g. codes 4+5 on a 5-point scale, 5+6+7 on a
  7-point — configurable codes), mean, or count.
- **Missing handling** flows entirely through base rules — never a renderer concern.

## 8. Report definition model

A report = ordered list of **ChartSpec** + a report-level **render_mode**:

```
Report = {
  name, render_mode,          # render_mode: "native" | "image"  (per report)
  template_ref,               # which PPT template / style spec
  charts: [ ChartSpec, … ],
}
ChartSpec = {
  question_ref,               # single var or multi group
  chart_type,                 # one of the 11
  statistic,                  # pct | count | mean
  classifying_var?,           # optional → segments + Total
  number_format,              # decimals, % sign
  sort,                       # rule + (for top-box) which codes
  template_slot,              # placement on the template
  elements,                   # title/legend/N/axis-names/filter-var toggles
}
```

Generation is pure: `(Report + Question Model + data) → .pptx`. Edit/duplicate/delete operate
on this JSON. Stored as the datahive report doc's source.

## 9. Rendering engine (R3 — dual mode)

A **strategy** interface `ChartRenderer.render(SeriesResult, ChartSpec) → slide content`, with
two implementations selected by the report's `render_mode`. Both share the SeriesResult,
the **element profile** (REQ-C-24/25 — title; chart-type elements e.g. bars; axis values;
axis names; category names; category numeric values; legend; sample size N; used filter
(classifying) variable; with the **same font + point size used across charts for the same
kinds of things**), the template **slots**, and the **style spec**.

**Report completeness (REQ-C-18):** a generated report contains exactly what the definition
specifies and nothing extra — chart count and slide content equal the ChartSpec list, with no
stray slides/shapes. Asserted in render-validation.

### 9a. Native mode (editable)
- `add_chart(XL_CHART_TYPE.X, …, chart_data)` → real `c:chart` part + embedded data workbook,
  editable with PowerPoint's own tools.
- **Chart-type coverage in native mode** (vertical bar = `COLUMN`, horizontal bar = `BAR` in
  OOXML terms):
  - **9 types render as their own native chart**: line, pie, vertical bar (column), stacked
    vertical bar, horizontal bar, stacked horizontal bar, radar, doughnut, scatter.
  - **Funnel** renders as a **native stacked-bar approximation** (centered, transparent spacer
    series) — still a native, editable chart and **not a picture**, so the gate below holds. It
    is a *visual approximation*, not a pixel-true funnel; a user wanting a true funnel uses
    image mode. This trade is stated in the UI when funnel is chosen in native mode.
  - **Combo ("yhdistelmä")** is **not available in native mode initially** (requires raw-OOXML
    multi-plot work; docx marks it least important). Until that lands, a report needing a true
    combo uses **image mode**, which renders it directly. The builder disables/flags combo for
    native-mode reports so a report can never silently fail the all-types expectation.
- **Acceptance gate (native mode):** every chart is a native OOXML chart object, **never
  rasterized** — a native-mode report contains **zero picture-shapes in chart slots** (asserted
  in render-validation). Funnel-as-stacked-bar satisfies this; combo is excluded from native
  mode rather than rasterized into it.
- **Scatter data shape:** scatter consumes (x, y) numeric pairs, so it applies to a pair of
  scale variables (or a value-vs-mean mapping the ChartSpec names) — **not** to a categorical
  single-variable distribution. The builder only offers scatter where two numeric axes are
  defined; this binding is part of the ChartSpec for scatter.
- **Layout discipline** to keep native charts clean (the real R3 risk — see §13). Note
  python-pptx has **no public API** for any of this — it is **raw `c:chart` XML
  construction**, unprototyped, and is the single hardest, first-to-spike task:
  1. **Pin layout in OOXML** (`c:manualLayout` for plot-area/legend/title; explicit data-label
     positions/sizes) instead of trusting auto-layout. We know label lengths up front, so the
     coordinate computation (a small layout solver: measure label text, allocate plot vs
     legend/axis margins, place labels) is *our* code emitting raw XML, not a library call.
  2. **Shape data to the chart**: cap category count, pre-sort, wrap/truncate long labels,
     steer long-label questions to horizontal bars.
  3. **Render-and-verify quality gate**: render via LibreOffice, detect overlap/truncation,
     auto-correct (shrink font, reposition), re-check.

### 9b. Image mode (guaranteed-clean, not editable)
- matplotlib (building on `chart_lab/`) → PNG → `add_picture`. Pixel-level layout control;
  identical in preview and output; all 11 types incl. real funnel/combo trivially.
- Explicitly **non-editable** — the user opts into this trade per report.

## 10. Preview / export pipeline (R5)

- Single source: report → **`.pptx`** → **LibreOffice headless** `--convert-to pdf` →
  **`.pdf`**. Preview = display that PDF (reuse Prima Volta `pdf_view`). The user-selectable
  **PPT vs PDF view** (REQ-C-19b) is two *views of the same artifact* — a slide-deck view
  (one slide per page, PPT-style) vs a continuous PDF-page view; both derive from the one PDF,
  so **preview *is* the output**.
- Both `.pptx` and `.pdf` stored as datahive artifact docs and downloadable.
- **Fidelity gate — three concrete layers** (the previous one-line claim was inaccurate: a
  PPTX-XML read does *not* observe LibreOffice output):
  1. **Chart-data check (native):** read the written `.pptx` chart series via python-pptx and
     assert == SeriesResult. Catches *our* render bugs. Does **not** observe PDF conversion.
  2. **Conversion-drift check:** extract the **rendered data-label text from the `.pdf`**
     (`pdftotext` — data labels are real text in the PDF) and assert the numbers == SeriesResult.
     This is the layer that actually guards LibreOffice drift.
  3. **Image mode:** numbers are pixels in a PNG and are **not artifact-extractable**, so the
     check moves **upstream** — assert the matplotlib chart's data arrays == SeriesResult
     *before* rasterizing. Stated honestly: image mode verifies the inputs to the renderer, not
     the rendered pixels (the renderer is deterministic given those inputs).
- Native mode additionally carries the **PowerPoint-vs-LibreOffice layout divergence** risk
  (preview renders in LibreOffice; the client edits in PowerPoint) — image mode does not.

## 11. API surface + frontend (thin)

- **nSight REST**: cases (→ datahive projects), materials (ingest SAV → SPSS connector + build
  Question Model), question browser (+ multi-grouping edits), report CRUD (→ datahive docs),
  render (job → artifacts), preview (serve PDF).
- **Flutter** (Prima Volta shell): Case list → Case detail with **two main areas — Data and
  Reports** (REQ-U-04). The **Data** area is the question browser where question line items can
  be browsed, sorted, edited, and deleted (REQ-U-05) and single/multi defined. The **Reports**
  area builds reports (variable, chart type, classifying var, statistic, sort, format,
  render_mode), and reports can be **previewed and duplicated** (REQ-U-06). Mouse + keyboard,
  consistent terms (REQ-U-02/10). No charting logic.
- **Deferred to the UI phase (REQ-U-07/08/09/11):** report-window management, window
  size-control, close icon, and overall "easy/intuitive" usability — listed and traced, built
  when the UI is the focus.

## 12. Testing strategy

- **Statistics golden tests (R1 gate):** computed SeriesResult == known truth, using the
  Attendo `.sav` + the deck's printed numbers as ground truth.
- **Base-rule / multi-grouping unit tests:** single/multi/missing/segment bases on fixtures.
- **Native render-validation:** each type emits valid editable OOXML (chart part + embedded
  workbook present; **no picture shapes** in chart slots); chart-data series == SeriesResult;
  golden XML snapshots. Funnel asserts a native (non-picture) chart; combo asserts it is
  excluded from native mode.
- **Image render-validation:** picture present; the matplotlib data arrays == SeriesResult
  (verified pre-rasterization, per §10).
- **Conversion fidelity:** `pdftotext` data-label numbers from the rendered `.pdf` ==
  SeriesResult — the layer that actually guards LibreOffice drift.
- **PPT opens cleanly (REQ-C-29a):** OOXML schema validation + python-pptx re-open without
  exception (no PowerPoint-in-CI dependency).
- **datahive integration:** project create / attach material+report / list / recall round-trip
  + **exact JSON round-trip via `reference_id`/`reveal_source`** (the new D3 wiring), test hive.
- **Aggregation primitive (datahive side, D1):** generic GROUP BY / cross-tab counts correct;
  plus an nSight-side in-process-aggregation parity test (fallback path, §7).

## 13. Risk & dependency register

| ID | Risk | Sev | Owner | Mitigation / coverage |
|---|---|---|---|---|
| **R1** | Base/denominator correctness (single/multi/missing/segments) | CRIT | nSight | Golden tests vs Attendo truth; explicit base rules; SeriesResult as sole numeric source |
| **R2** | Multi-question grouping not in SAV | HIGH | nSight | Heuristic auto-suggest + user confirm; persisted in Question Model |
| **R3** | **De-novo native chart construction + clean layout via raw OOXML** (no python-pptx API; unprototyped — the prototype only does `replace_data`). Plus preview(LibreOffice)≠edit(PowerPoint) divergence | **CRIT** | nSight | **Spike first** (§15.0): prove `add_chart` + `c:manualLayout` + data-label placement on 2–3 types before committing. Then per-report render mode; data-shaping; render-verify gate; image mode as the guaranteed-clean fallback |
| **R3′** | Funnel + combo not natively supported | MED | nSight | Funnel = native stacked-bar approximation (still editable, not a picture); combo = image-mode only until raw-OOXML work lands; builder flags both trade-offs |
| **R4** | Template/style-spec ingestion + layout | HIGH | nSight | Derive style spec from Attendo deck **as proxy**; REQ-C-27 split into "renders against *a* spec" (testable now) vs "matches *client* spec" (blocked); **needs the reference PPT** |
| **R5** | PPT→PDF conversion fidelity | MED-HI | nSight | Bundle fonts; `pdftotext` numbers-survive gate (§10 layer 2) |
| **R6** | Means/format/sort traps (top-box sum) | MED | nSight | Unit tests per statistic + sort rule |
| **D1** | datahive aggregation primitive (generic; **genuinely new** — no GROUP BY today) | MED | datahive | New generic accessor; **not on hard critical path** — nSight aggregates in-process from rows until it lands (§7) |
| **D2** | datahive projects REST router + shared-service-layer refactor (**several stragglers**, not just `references.py`) | MED | datahive | Generic; deliverable of the layering principle |
| **D3** | Report-JSON lossless store + versioned replace on an attached doc (**new wiring**: `attach_doc` lacks `reference_id`/raw-source today) | MED | datahive | Attach with stable `reference_id`; read via `reveal_source`; REQ-C-08 depends on it |
| **G1** | Genericity guardrail | standing | both | Review criterion: every datahive change describable without "nSight/survey/chart" |

## 14. Open dependencies (need input)

- **R4 blocker:** the "separate PPT document" defining chart element placement/styling. Agreed
  to use the Attendo deck in `work/` as proxy until the formal one exists.
- **D1/D2/D3:** cross-team coordination with the datahive team on the three generic additions.

## 15. Suggested phasing (for the implementation plan)

0. **Rendering spike (R3, do first — highest unknown):** prove de-novo `add_chart` +
   `c:manualLayout` + data-label placement produces a clean, editable chart on 2–3 types,
   rendered correctly through LibreOffice. This validates the project's hardest assumption
   before anything is built on it. If raw-OOXML layout proves impractical, image mode becomes
   the primary path — better to learn that here.
1. **Question Model + statistics engine** (R1/R2) — the spine, golden-tested, before rendering.
   Uses in-process aggregation from rows (D1 not required to start).
2. **datahive domain wiring** (projects REST + survey-study template + report-JSON round-trip,
   D2/D3) — Case/Material/Report persisted and MCP-discoverable. Aggregation primitive (D1) in
   parallel as the clean replacement for in-process aggregation.
3. **Rendering engine** — native mode (9 types + layout discipline from the spike), then image
   mode (reuse `chart_lab/`), then funnel approximation; combo via image mode (R3/R3′/R4).
4. **Preview/export pipeline** (R5, three-layer fidelity gate) + thin REST API.
5. **Flutter UI** over the settled API.
