# Remediation plan — output quality + UX (2026-06-26)

After a live UI try, the generated decks were far below the proof-of-concept (plain unstyled
charts, squeezed/overlapping labels, no template, no titles/descriptions), and several requirements
were implemented too literally. This plan fixes both, with a **visual-verification gate** so no
build is handed over for testing until its charts are reviewed against the original Attendo deck.

## Benchmark
The original Attendo deck (`input/Attendo Bränditutkimus Marraskuu 2025.pptx`) is the quality bar:
headline insight + question text + branded, correctly-typed charts (often small-multiples) + logo/
footer. Generated slides must approach this.

## Track A — Rendering quality (the core value)

A1. **Render INTO the template.** `orchestrate_render` currently calls `build_pptx(...)` with no
    style → generic synthesized blank slides. Wire the report's `template_ref` → `load_style_spec`
    (or the Attendo proxy) and pass it to `build_pptx`, binding charts to the template's slots so
    output carries the template's palette/fonts/layout. (REQ-C-17/27a/20/25)
A2. **Slide title + question text + description.** Each slide shows the chart title, the **question
    text** (variable label, REQ-D-04), and an optional description/headline. Add these text boxes to
    the rendered slide. (REQ-C-24a, REQ-D-04)
A3. **Automatic number format — a per-question option (default = Automatic).** Number format is a
    **per-question / per-chart selectable option**, surfaced in the builder's chart config. The
    default is **"Automatic"**: choose pct/mean decimals + rounding from the value range (e.g. whole %
    when all ≥ ~10, one decimal when values are small/close; means by spread). The user can change it
    per question to a manual format (explicit decimals, round-up). So `NumberFormat` gains a `mode`
    (`"auto"` | `"manual"`); Automatic is computed at compute-time from the SeriesResult's value
    range; manual uses the explicit decimals. Both the engine (data-label values) and the chart
    number-format string honor it. (REQ-N-01/02/03)
A4. **Default sort = percentage magnitude.** Change the builder/engine default `SortSpec.basis` from
    `data_order` to `pct` (descending). (REQ-S-03)
A5. **Per-type quality + smart defaults.** Fix label handling (horizontal bar auto-preferred for
    many long categories; rotate/wrap or switch to avoid x-axis overlap); apply the template palette
    to series (not default blue/rainbow); restrict pie/doughnut to true parts-of-whole (single,
    sums-to-100) data and warn/disallow on multi-response; size charts to fill the slot without
    squeezing; implement `combo`. (REQ-C-13)
A6. **Missing values → "Not answered".** Read the SAV user-missing definitions; map special/missing
    codes (e.g. 99 = "En tiedä") to a "Not answered" concept — excluded from the base (REQ-MV) AND
    optionally shown as an explicit "Not answered" category, per a per-question toggle. Surface the
    detected missing set in the question browser. (REQ-D-06, MV-01/02)
A7. **Visual-verification gate.** A gallery render of EVERY chart type + a full sample Attendo report,
    reviewed (human + Claude-judge against the Attendo deck) before any demo handoff. Institutionalize
    "look at the charts" — the step that was skipped.

A8. **Per-question statistic option (percentage / count / mean).** Each question/chart has a
    statistic selector (already in `ChartSpec.statistic` + the builder dropdown). Ensure it is clear
    per question, **defaults to percentage**, and that switching a percentage question to **count**
    renders correct whole-number counts (count number-format) and to **mean** the mean value. Pair it
    with the A3 per-question number-format control. (REQ-C-15, REQ-M-04, REQ-N)

## Track B0 — Wizard workflow (the UX redesign blueprint, user-approved direction)

Replace the feature-by-feature tabs with a guided **wizard**. Question-level config lives on the
**material**; chart/slide config lives on the **report**.

**Material area (pre-wizard):** view the curated questions (A0); per question set **single/multi**
grouping and the **missing-value → "Not answered"** mapping (data properties, shared by all reports).

**Report wizard (launched by "New report"):**
1. **Select questions** — from the material's curated list (search, multi-select).
2. **Configure** — per selected question: statistic (% default), number format (Automatic default),
   sort (pct default), classifying variable, and **graph type pre-filled with the smartest
   suggestion** by question shape (multi tickbox→horizontal bar; Likert single→stacked bar;
   scale→mean bar; parts-of-whole single→pie/doughnut). Show a **live thumbnail** per question.
3. **Review charts** — full per-chart preview; fine-tune type/options. (No end-of-line surprises.)
4. **Assemble slides** — per slide: headline/insight + question text + description; reorder; choose
   template/branding; optionally **multiple charts per slide** (small-multiples like the Attendo deck).
5. **Generate & download** — full-deck preview, then **PPTX or PDF**.

**Cross-cutting:** progress is saved (report persists; resumable); free back/forward; real chart
visuals visible from step 2 onward. Stepper UI with clear step names; good defaults so a user can
click through quickly and tweak only what they want.

## Track B — Workflow / cleaner UX (components feeding B0)

B1. **Make single/multi actually work** (settable + persisted + applied) and **explain it**: single =
    one-answer question (one variable); multi = a tickbox set (several 0/1 variables) reported as one
    unit with base = respondents-answering. Auto-detect, show clearly, allow override. (REQ-C-06, M-*)
    — needs a backend persistence path for grouping (currently stateless/deferred).
B2. **Question edit + delete** in the question browser. (REQ-U-05) — needs backend routes.
B3. **Guided, cleaner flow:** Case → upload material → questions (with good auto-grouping + auto
    number format + default pct sort) → build report with **inline per-chart preview** → render.
    Reduce raw config knobs up front; sensible defaults; clearer steps; consistent terminology.
B4. **Per-chart live preview** in the builder so the user sees each chart as configured (not only at
    final render).

## Backend gaps this surfaces (nSight API, not datahive)
- Grouping persistence (single/multi) — currently stateless. Needs a persisted per-material grouping
  store (or fold into the material/report).
- Question edit/delete routes.
- Number-format "auto" + per-question missing-value config carried through compute + render.

## Sequencing (parallel, per user)
Track A and Track B proceed concurrently; both converge on a re-verified demo that passes the A7
visual gate against the Attendo benchmark. Track A (deck quality) is the core "real value".

## Track A0 — Question-list curation (FOUNDATIONAL; fixes the messy list + enables single/multi)

Confirmed on Attendo: ingest yields 229 variables = 229 "questions", including:
- **Survey-platform metadata** that aren't questions: Response ID (`vrid`), Date Submitted, Status,
  Contact ID, SessionID, **IP Address** (`vip`), `pid`/`psid`. → FILTER these out (by name/label
  pattern + measurement) so they never appear as questions.
- **Exploded multi sub-options** listed individually: `var18O45..53` are the 9 per-brand aided-
  awareness options that must be **auto-grouped into ONE multi question**; `var11O19..22` likewise.
  The current `suggest_multi_groups` heuristic isn't catching these `var<N>O<M>` option families. →
  Strengthen auto-grouping to detect the `var18O45..53`-style option families (shared `var<N>` stem)
  and present one curated question, with the option labels as its categories.

Result: a short, meaningful question list (one row per real question), which also makes single/multi
coherent (the grouped set IS the multi question). Drives REQ-C-05 ("sensible organization") + M-02.
This is a prerequisite for a clean UX and correct charts — do it early.
