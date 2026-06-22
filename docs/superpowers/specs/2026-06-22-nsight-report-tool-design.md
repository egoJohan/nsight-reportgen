# nSight self-service report tool — design spec

_Date: 2026-06-22 · Status: draft for review_

Source requirement: `Mitä työkalun pitäisi tehdä.docx` ("What the tool should do"),
plus decisions taken in the brainstorming session recorded inline below.

---

## 1. Goal

Build a **self-service survey report builder**: a user imports SPSS `.sav` data,
browses it question-by-question, picks variables and a chart type per variable, and
composes/saves/edits/duplicates multiple PowerPoint reports, previews them on screen, and
exports **editable PPT + PDF**. This is a generic interactive tool — there is no
natural-language brief, no LLM-written narrative, and no "fidelity to a pre-existing deck"
target (those belonged to the earlier prototype, which proved out the deterministic
tabulation/rendering core but is a different product).

## 2. Framing & decisions taken

- **Fresh design.** We are not constrained to reuse the prototype's code; we keep its
  *learnings* (deterministic numbers, native-chart rendering, the image experiments in
  `chart_lab/`, the fidelity-harness idea).
- **datahive is the system of record** (not a separate Postgres). Cases/Materials/Reports
  live in datahive's **projects app**, so they are reachable for agentic discussion
  (Claude/ChatGPT) over MCP.
- **Genericity guardrail (standing constraint):** datahive's genericity and architectural
  simplicity must not be endangered by nSight-specific needs. Every change to datahive must
  be describable *without* the words "nSight", "survey", or "chart". nSight-specific meaning
  lives only in the nSight backend and inside opaque document payloads datahive never parses.
- **Frontend is deliberately thin** and not the focus of this phase. The risky elements are
  all backend Python. Recommended frontend: **Flutter web**, copying Prima Volta's shell
  (icon rail, context panel, `pdf_view`). Frontend holds **zero charting logic**.
- **Backend is near-stateless** Python: aggregation client + statistics engine + rendering
  + preview/export + a thin REST API. Operational state only (render-job queue, caches).
- **Scope of this phase:** cover all of the most risky elements (R1–R6 + datahive
  dependencies below). Breadth polish and the docx's "EI TÄRKEÄ" items (user management,
  template-management UI, history import) are out of scope.

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
`create_workflow_template` over MCP; templates are "validated as data — no domain logic
hardcoded"; `attach_doc` remembers each doc as a classified, indexed item; the MCP schema's
own example app namespace is literally `nsight`.

**The report definition is opaque to datahive.** datahive stores, links, versions
(`reference_id`/`replace_source`), and serves it; it never parses a ChartSpec or knows what a
"base rule" is.

## 5. datahive changes required (all generic)

1. **Projects REST router** — so the projects app has REST in addition to MCP (consistency;
   the nSight backend calls it over REST). _D2_
2. **Shared-service-layer refactor** — REST and MCP both become thin adapters over each app's
   service; auth/ABAC/validation/audit move into services (removes today's per-adapter
   duplication, e.g. references router's inline `_ref_visible`). _D2_
3. **Aggregation primitive** — a generic "filtered GROUP BY / cross-tab cell counts over a
   tabular item", built on `accessors/sql.py` + `retrieval/tabular.py`. Returns raw counts,
   not survey statistics. Reusable by any consumer. _D1_
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
functions: `compute(question, statistic, base_rule, classifying_var, data) → SeriesResult`,
consuming raw counts from datahive's aggregation primitive (Layer 1).

- **SeriesResult** = normalized table `categories × segments → {pct, count, mean, N}` + overall
  base N. **Every chart, export, and preview reads only this shape** — nothing downstream
  re-derives numbers.
- **Base rules** (where correctness lives):
  - *Single*: base = valid responses excluding that variable's missing set.
  - *Multi*: base = respondents who answered the set (≥1 valid in the group), **not** the
    selection count. Percentages and counts both available.
  - *Classifying variable*: compute per segment **plus a Total column**; each segment carries
    its own N.
- **Statistics**: percentage (0–N decimals), count (integer, round-half-up), mean
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
the **element profile** (title, axis values + names, category names, category numeric values,
legend, N, filter-variable annotation; consistent font + size), the template **slots**, and
the **style spec**.

### 9a. Native mode (editable)
- `add_chart(XL_CHART_TYPE.X, …, chart_data)` → real `c:chart` part + embedded data workbook,
  editable with PowerPoint's own tools.
- **9 of 11** chart types map directly (line, pie, column/stacked-column, bar/stacked-bar,
  radar, doughnut, scatter). **Funnel** = native stacked-bar workaround (still an editable bar
  chart). **Combo** = raw OOXML chart groups (still a native `c:chart`), phased last.
- **Acceptance gate (native mode):** charts are always native OOXML chart objects, **never
  rasterized**. A native-mode report contains **zero picture-shapes in chart slots** —
  asserted in render-validation tests.
- **Layout discipline** to keep native charts clean (the real R3 risk — see §13):
  1. **Pin layout in OOXML** (`c:manualLayout` for plot area/legend/title; explicit data-label
     positions/font sizes) instead of trusting auto-layout. We know label lengths up front.
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
  **`.pdf`**. Preview = display that PDF, paginated (reuse Prima Volta `pdf_view`). "PPT vs PDF
  pagination" is a cosmetic toggle over the same artifact — **preview *is* the output**.
- Both `.pptx` and `.pdf` stored as datahive artifact docs and downloadable.
- **Fidelity gate**: extract numbers back out of the rendered artifact and assert they equal
  the SeriesResult (numbers are known, so checkable). Guards LibreOffice drift. Native mode
  additionally carries the **PowerPoint-vs-LibreOffice layout divergence** risk (preview
  renders in LibreOffice; the client edits in PowerPoint) — image mode does not.

## 11. API surface + frontend (thin)

- **nSight REST**: cases (→ datahive projects), materials (ingest SAV → SPSS connector + build
  Question Model), question browser (+ multi-grouping edits), report CRUD (→ datahive docs),
  render (job → artifacts), preview (serve PDF).
- **Flutter** (Prima Volta shell): Case list → Case detail (materials + reports) → Question
  browser → Report builder (variable, chart type, classifying var, statistic, sort, format,
  render_mode) → PDF preview. No charting logic.

## 12. Testing strategy

- **Statistics golden tests (R1 gate):** computed SeriesResult == known truth, using the
  Attendo `.sav` + the deck's printed numbers as ground truth.
- **Base-rule / multi-grouping unit tests:** single/multi/missing/segment bases on fixtures.
- **Native render-validation:** each type emits valid editable OOXML (chart part + embedded
  workbook present; **no picture shapes** in chart slots); golden XML snapshots.
- **Image render-validation:** picture present; rendered numbers correct.
- **Conversion fidelity:** numbers survive PPT→PDF (extract-and-compare) — guards drift.
- **datahive integration:** project create / attach material+report / list / recall round-trip
  + exact structured-JSON round-trip, against a test hive.
- **Aggregation primitive (datahive side):** generic GROUP BY / cross-tab counts correct.

## 13. Risk & dependency register

| ID | Risk | Sev | Owner | Mitigation / coverage |
|---|---|---|---|---|
| **R1** | Base/denominator correctness (single/multi/missing/segments) | CRIT | nSight | Golden tests vs Attendo truth; explicit base rules; SeriesResult as sole numeric source |
| **R2** | Multi-question grouping not in SAV | HIGH | nSight | Heuristic auto-suggest + user confirm; persisted in Question Model |
| **R3** | Native charts clean *and* editable; preview(LibreOffice)≠edit(PowerPoint) divergence | HIGH | nSight | Per-report render mode; native = pinned OOXML layout + data-shaping + render-verify gate; image mode as guaranteed-clean alternative |
| **R3′** | Funnel + combo not natively supported | MED | nSight | Funnel = native stacked-bar; combo = raw OOXML, phased last; image mode renders both trivially |
| **R4** | Template/style-spec ingestion + layout | HIGH | nSight | Derive style spec from Attendo deck; **needs the reference PPT** to finalize |
| **R5** | PPT→PDF conversion fidelity | MED-HI | nSight | Bundle fonts; numbers-survive fidelity gate |
| **R6** | Means/format/sort traps (top-box sum) | MED | nSight | Unit tests per statistic + sort rule |
| **D1** | datahive aggregation primitive (generic) | MED | datahive | New generic accessor over tabular items; via REST |
| **D2** | datahive projects REST router + shared-service-layer refactor | MED | datahive | Generic; deliverable of the layering principle |
| **D3** | Exact structured-JSON round-trip in attached docs | LOW-MED | datahive | Confirm raw source retrieval; else raw-blob sibling |
| **G1** | Genericity guardrail | standing | both | Review criterion: every datahive change describable without "nSight/survey/chart" |

## 14. Open dependencies (need input)

- **R4 blocker:** the "separate PPT document" defining chart element placement/styling. Agreed
  to use the Attendo deck in `work/` as proxy until the formal one exists.
- **D1/D2/D3:** cross-team coordination with the datahive team on the three generic additions.

## 15. Suggested phasing (for the implementation plan)

1. **Question Model + statistics engine + aggregation primitive** (R1/R2/D1) — the spine,
   golden-tested, before any rendering.
2. **datahive domain wiring** (projects REST + survey-study template + doc round-trip, D2/D3)
   — Case/Material/Report persisted and MCP-discoverable.
3. **Rendering engine** — native mode first (9 types + layout discipline), then image mode
   (reuse `chart_lab/`), then funnel/combo (R3/R3′/R4).
4. **Preview/export pipeline** (R5) + thin REST API.
5. **Flutter UI** over the settled API.
