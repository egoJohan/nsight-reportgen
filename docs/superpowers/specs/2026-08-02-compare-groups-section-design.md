# "Compare groups" — reporting study arms side by side

**Date:** 2026-08-02
**Status:** approved (design), pending implementation plan
**Revision:** 2. Changes from revision 1, all found in review:
§1.1 a third of the customer's questions do not split at all, so the dialog needs a
backend call to know which — revision 1 wrongly claimed no new endpoint;
§2 a generated slide must clear `classifying_var_2` or a banner classifier raises;
§3 the marker moved out of the `options` bag, which is part of the preview cache key;
§1.2 the dialog is once-only per type and calls every special slide AI-written,
neither of which fits this one;
§1.3 generating a dozen slides must not fire a dozen AI title calls.

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
           [ ] Kuinka houkuttelevana pidät oheista pakkausta?
               — only one group answered this question
```

- **Group by** lists the same variables as the Design panel's Classifying variable
  picker (`GET /materials/{id}/variables`, `segmentable === true`). That includes
  banner classifiers such as `Polku`, coded path columns such as
  `Pakkausilme 1 tai 2`, demographics, and analyst segment recodes — so the feature
  is "compare any groups across the report", of which the packaging arm is one case.
- **Questions** lists the questions already in the report. A question the chosen
  variable does not actually split is shown disabled with the reason, and cannot be
  ticked (§1.1). The rest default to ticked.
- Confirming inserts one chart slide per ticked question, each with
  `classifying_var` set to the chosen variable, as one contiguous block **appended
  after the last chart slide** — not at the front of the deck, which is where
  `addSpecialSlide(type, null)` puts a special slide. A comparison section is a
  closing section, and inserting it at the front would bury the report's opening.

### 1.1 Not every question splits — this must be visible

Measured on the customer's own report: **6 of its 18 questions produce a
one-group split** under `Polku`. Every one is a battery whose member variables
belong to a single arm (`Houkuttelevuus_1` is asked only of path 1), so
classifying it by the path yields that arm and nothing else. Two other batteries —
asked of everyone — split correctly.

Generating slides blindly would hand the author six charts that look unsplit and
have to be deleted by hand. So the dialog must know, per question, how many groups
survive. That is data-dependent, so it needs a backend call:

```
GET /materials/{id}/split-groups?classifying_var=<name-or-qid>&grouping=<json>
  → { "var3": 2, "battery-kuinka-houkuttelevana-…": 1, … }
```

It reuses the existing model load and `_classifier_masks`, counting the segments
that have any answered data for each question — the same `_drop_empty_segments`
rule the engine already applies, so the dialog can never disagree with the chart.

The dialog calls it when the **Group by** value changes and disables every question
whose count is below 2, labelled "only one group answered this question".

### 1.2 Two dialog assumptions this breaks

`AddSpecialDialog` currently renders each choice `disabled={added}` — a special
slide is once-only — and its subtitle reads *"Special slides are written by AI from
the report's data."* Neither holds here:

- **Compare groups is repeatable.** Comparing by `Polku` and then by gender are two
  legitimate sections, so this entry is exempt from the once-only rule.
- **Nothing about it is AI-written.** The dialog subtitle moves onto the individual
  choices, so the three AI slides keep that promise and this one does not make it.

### 1.3 No burst of AI title calls

Adding an ordinary slide triggers the wizard's AI title generation. A comparison
section is a dozen slides at once, which would fire a dozen egoHive calls in
parallel — slow, and enough to exhaust a quota (which this project has already hit
once). Generated slides are therefore created with **no `slide_title`**, so each
falls back to the question text, and the author regenerates titles individually
from Design if they want them. Nothing is silently spent on their behalf.

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

**A generated slide also clears `classifying_var_2`.** Carrying a second classifier
over from the source slide is not merely odd — with a banner classifier the engine
*raises* (`ValueError`, spec §2.5 of the classifying-variable work), so a report
whose source slide happens to be a cross-tab would fail to render. The generated
slide is a clean two-group comparison: one classifier, `percent_base` left at
`auto`.

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
  slide is marked with **`ChartSpec.compare_group = "<variable>"`**, and a slide
  carrying that marker is never removed by the Step 1 toggle. "Primary" is therefore
  *unmarked*, not *unclassified*: a chart the author classified by hand stays
  primary, which is what they'd expect. Comparison slides are removed from the slide
  grid like any other slide.

  The marker is a first-class field rather than a key in the free-form `options`
  bag for two reasons: `options` is plugin-config space, and it is part of the
  **preview cache key** (`queries.ts`), so a marker there would make an otherwise
  identical chart render twice. `compare_group` and `slide_id` are both excluded
  from that key — neither changes a single pixel of the PNG.
- New slides get a random `slide_id` (the scheme `specialRef` already uses).
  Reports saved before this change have none; each chart is assigned
  `f"{question_ref}#{index}"` on load, which is deterministic, so loading and
  re-saving an untouched report produces no diff.

`question_ref` keeps its meaning — which question the chart shows — so the backend
is unaffected: it renders per chart and never assumed refs were unique.

**Known limitation, deliberately not fixed here.** `AiPendingMap` is also keyed by
`question_ref` (`aiPending?.[activeChart.question_ref]?.titlePending`), so
regenerating a title on the total slide shows the spinner on its comparison twin as
well. It is cosmetic — the wrong slide shows "Updating…" briefly — and re-keying the
AI orchestrator on `slide_id` is a larger change than this feature warrants. Worth
doing if per-slide AI state ever matters for anything beyond a spinner.

## 4. What is NOT needed

Worth recording, because it shapes the size of this work:

- No engine change. `classifying_var` already produces the required series, for a
  banner classifier, a coded string column, or an ordinary value-labelled variable.
- No renderer change. The clustered bar already draws one series per group.
- No new statistics. §1.1's endpoint counts segments using the engine's existing
  `_classifier_masks` + `_drop_empty_segments`; it computes nothing new, it just
  exposes what the chart would do.

The work is a dialog, one read-only endpoint, a slide-generation function, and two
`ChartSpec` fields.

*(Revision 1 claimed "no new backend endpoint". That was wrong: whether a question
splits is a property of the DATA, and the dialog cannot know it without asking.)*

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
each with the right `classifying_var`, in the chosen order, appended after the last
chart slide. A source slide carrying `classifying_var_2` yields a generated slide
with it cleared — the regression guard for the banner `ValueError`.

**Split availability (§1.1):** on the client fixture, `Polku` reports 2 groups for
the 12 questions that split and 1 for the 6 single-arm batteries; those 6 are
disabled in the dialog. A classifier that splits nothing disables every row and the
confirm button.

**Preview cache:** two charts differing only in `slide_id` / `compare_group` produce
the same cache key, so the second is served from cache rather than re-rendered.

**Dialog:** Compare groups stays enabled after a section has been added (unlike the
three AI slides); generated slides carry no `slide_title` and trigger no AI title
request.

**End to end, on the client fixture:** a generated slide for a demographic question
classified by `Polku` renders with two series and per-group bases 255 / 256 — the
numbers already verified for that split.

**Serde:** `slide_id` round-trips; an old report without it still loads.
