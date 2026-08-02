# "Compare groups" — reporting study arms side by side

**Date:** 2026-08-02
**Status:** approved (design), pending implementation plan

## Problem

In a concept or packaging test the sample is split into arms: part of the Erisan
respondents assessed *Pakkausilme 1*, part *Pakkausilme 2*. The arms together form
the study's respondent base, but the interesting reading is usually **per arm**, not
the total.

The customer's own report shows this: a gender chart drawn as two series, *Design 1*
and *Design 2* (Nainen 47 % / 46 %, Mies 53 % / 54 %). nSight currently produces the
total-level pie for the same question (N = 511, 53 % / 47 %) — correct, but not the
comparison the study exists to make.

The **chart** is already achievable: since the classifying-variable work
([[2026-08-02-classifying-variable-encodings-design]]), setting `classifying_var`
to the path variable produces exactly that two-series clustered bar, verified by
rendering. What is missing is the **workflow** — doing it across the research
questions without configuring every slide by hand.

## Goal

From the Add-slide button, generate a section of slides that compare the study's
groups across chosen questions, leaving the existing total-level slides in place.

## Non-goals

Changing how a classified chart is computed or rendered. Filtering a slide to a
single group (the arms appear as series, not as a filter). Applying a classifier to
every existing slide in one action — that is a different, destructive operation.
Weighting.

## 1. The new slide type

"Compare groups" joins Overview / Conclusion / Demographics in `AddSpecialDialog`.
Choosing it opens a small form:

```
Group by:  [ Polku                    ▾ ]
Questions: [x] Identifioitko itsesi…?
           [x] Minkä ikäinen olet?
           [x] Missä päin Suomea asut?
           [ ] …
```

- **Group by** lists the same variables as the Design panel's Classifying variable
  picker (`GET /materials/{id}/variables`, `segmentable === true`). That includes
  banner classifiers such as `Polku`, coded path columns such as
  `Pakkausilme 1 tai 2`, demographics, and analyst segment recodes — so the feature
  is "compare any groups across the report", of which the packaging arm is one case.
- **Questions** defaults to the questions already in the report, all ticked.
- Confirming inserts one chart slide per ticked question, each with
  `classifying_var` set to the chosen variable, as a contiguous block after the
  active slide (the placement rule `addSpecialSlide` already uses).

Unlike the other special slides these are ordinary chart slides — no AI content, no
`special_*` chart type — so every existing Design control works on them unchanged.

## 2. Chart type of a generated slide

A pie cannot show two series; the customer's total-level slide is a pie and their
comparison is a bar. So each generated slide keeps the question's current chart type
**unless that type cannot render multiple series**, in which case it falls back to a
clustered bar:

| Source type | Generated |
|---|---|
| `pie`, `doughnut`, `funnel`, `wordcloud`, `themes` | `horizontal_bar` |
| `stacked_horizontal_bar` / `stacked_vertical_bar` | unchanged |
| anything else | unchanged |

The question's own chart type is read from its existing slide when it has one, else
from `suggested_chart_type`.

## 3. Slide identity

This is the part that requires a model change, and the reason is concrete. Charts
are identified by `question_ref`, and Step 1 treats that as set membership:

```js
addedRefs = new Set(charts.map(c => c.question_ref))
// unticking a question:
charts.filter(c => c.question_ref !== q.qid)     // removes EVERY chart for it
```

With the total slide kept alongside the comparison slide, one question owns two
charts. Today that shows as a single tick, and unticking would silently delete both.

**`ChartSpec.slide_id`** — a stable unique id per chart — is added:

- Removal from the slide grid keys on `slide_id`.
- Step 1's tick still answers "is this question in the report?" (`question_ref`
  membership, unchanged).
- Unticking a question removes only its **primary** slides. A generated comparison
  slide is marked with `options.compare_group = "<variable name>"` — the existing
  free-form options bag, so no second first-class field — and a slide carrying that
  marker is never removed by the Step 1 toggle. "Primary" is therefore *unmarked*,
  not *unclassified*: a chart the author classified by hand stays primary, which is
  what they'd expect. Comparison slides are removed from the slide grid like any
  other slide.
- New slides get a random `slide_id` (the scheme `specialRef` already uses).
  Reports saved before this change have none; each chart is assigned
  `f"{question_ref}#{index}"` on load, which is deterministic, so loading and
  re-saving an untouched report produces no diff.

`question_ref` keeps its meaning — which question the chart shows — so the backend
is unaffected: it renders per chart and never assumed refs were unique.

## 4. What is NOT needed

Worth recording, because it shapes the size of this work:

- No engine change. `classifying_var` already produces the required series, for a
  banner classifier, a coded string column, or an ordinary value-labelled variable.
- No renderer change. The clustered bar already draws one series per group.
- No new backend endpoint. The variable list and the question list both already
  exist.

The work is a dialog, a slide-generation function, and the `slide_id` model change.

## 5. Testing

**Chart-type fallback:** pie → `horizontal_bar`; `horizontal_bar` → unchanged;
`stacked_horizontal_bar` → unchanged; word cloud → `horizontal_bar`.

**Slide identity:**
- A comparison slide and a total slide for the same question coexist.
- Removing one leaves the other.
- Unticking the question in Step 1 removes the primary slide and leaves the
  comparison slide.
- A slide the author classified BY HAND (no `compare_group` marker) is still
  treated as primary and is removed by the toggle.
- A report loaded without `slide_id` gains stable ids; saving and reloading does not
  change them.

**Generation:** picking a variable and three questions inserts exactly three charts,
each with the right `classifying_var`, in the chosen order, after the active slide.

**End to end, on the client fixture:** a generated slide for a demographic question
classified by `Polku` renders with two series and per-group bases 255 / 256 — the
numbers already verified for that split.

**Serde:** `slide_id` round-trips; an old report without it still loads.
