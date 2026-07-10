# Cross-tab percentage direction — clear MANUAL control — spec

## Problem

A classified (cross-tab) chart can percentage in two directions. The engine already
supports both plus `auto`; the values are `percent_base ∈ {auto, classifier, question, total}`.
The customer ticket ("Ristiintaulukointi-prosenteilla") wants a chart where **each
primary segmenter group sums to 100 %** — e.g. gender × values-segment where *each
gender's* bars sum to 100 % ("of women, X % are in segment Y"), not *each segment's*
bars summing to 100 % across gender.

That direction is already reachable — but only via the abstract, role-relative labels
on the "Percentages of" control, and the roles are **hidden** from the analyst:

| current label | value | means |
|---|---|---|
| Automatic | `auto` | resolve from variable roles |
| Each segment (the classifying variable) | `classifier` | distribute the base var within each classifier group |
| Each category (this question) | `question` | distribute the classifier within each base category |
| Total | `total` | over the grand total |

Which option yields "each gender = 100 %" flips depending on whether gender is the
internal **base** or the **classifier** — something the analyst can't see. So the same
intent maps to opposite options on two otherwise-identical charts. Reproduced live in
`case-134 / rep-209` (slide 1 = wrong `classifier`, slide 2 = wanted `question`) and in
`tests/suite/unit/stats/test_percent_direction_ticket.py`.

## Goal

Make the **manual** direction choice unambiguous by naming the **actual variables** and
stating the outcome, so an analyst picks the grouping they want without knowing base vs
classifier and without relying on `auto`. The primary change (Task 1) is **labelling/UX**
on the Design control only — the engine directions and the stored `percent_base` values
are unchanged. A secondary, OPTIONAL change (Task 2) refines `auto`'s tie-break and is the
only part that touches engine behaviour.

## Design

### 1. Variable-named option labels (primary, frontend only)

`percent_base` gets a dedicated `PercentBaseWidget` that builds its option labels from
the chart's two variables, which the Design config already has in `WidgetProps`
(`question` = base, `variables` + `chart.classifying_var` = classifier):

- `shortLabel(v)` = the variable's `label` collapsed to one line and trimmed to ≤ 24
  chars (append `…` when cut); the variable name if the label is empty. Applied to BOTH
  labels so a verbose variable label (e.g. "Segm. malli B - 6 segmenttiä", or a gender
  variable whose label is the full question "Identifioitko itsesi") stays readable.
- `baseLabel` = `shortLabel` of the base variable = `variables[question.variables[0]]`.
- `clfLabel` = `shortLabel` of `variables[chart.classifying_var]`.

Rendered options (value → label), `auto` first because it stays the default:

- `auto` → **"Automatic"**
- `question` → **"% within each {baseLabel}"**
- `classifier` → **"% within each {clfLabel}"**
- `total` → **"% of the total"**

Below the control, a single field-level hint (the Select renders one hint, not per-option
help): **"'% within each X' means each X's bars add up to 100 %."**

So for gender × segment the analyst sees "% within each Sukupuoli" vs "% within each
segment" and directly picks the one that sums each gender to 100 %, regardless of which
variable is the internal base.

**Mapping (verified):** `question` distributes the classifier within each base category →
each base group sums to 100 %; `classifier` distributes the base within each classifier
group → each classifier group sums to 100 %. Confirmed against `case-134/rep-209`:
`question` → each gender 100 %, `classifier` → each segment 100 %.

**Fallbacks / scope of the relabel:**
- If `variables` is not yet loaded, or the base variable/question can't be resolved, render
  today's static labels so the control never blanks or shows a partial `% within each …`.
- If a SECOND classifier (`chart.classifying_var_2`) is set, the classifier side is a
  combination of two variables — naming one would be wrong — so keep the static labels in
  that case (variable-named labels are single-classifier only here; see Out of scope).
- When `chart.classifying_var` is unset the whole control is already hidden — unchanged.

This part is frontend-only: no change to the engine or to the stored `percent_base` value.

### 2. `auto` tie-break refinement (secondary, backend, optional)

`resolve_percent_base` returns `"question"` only when the base **strictly** outranks the
classifier; equal scores fall back to the legacy `"classifier"`. This only bites if the
customer's actual failing chart uses `percent_base == "auto"` AND its two variables **tie**
— e.g. a demographic that `_DEMOGRAPHIC_RE` failed to match (so it scored 2 instead of 3)
sitting opposite a segment (also 2).

Important: on a genuine tie the resolver has **no signal** that one side ought to be the
denominator — both scored the same — so a blind tie-break flip to `"question"` would
silently change the direction of every existing tie chart. So this task is **CONTINGENT on
the plan's Step 0** (read the failing chart) and takes the lowest-blast-radius form:

- If the tie is caused by a **missed demographic**, extend `_DEMOGRAPHIC_RE` /
  `segmenter_score` so that variable scores 3; the existing strict-outrank rule then already
  resolves it to `"question"` — no tie-break change, minimal collateral.
- Flipping the **global tie default** (`classifier` → `question`) is a broad behavioural
  change; only do it with Seppo's sign-off and a regression sweep of existing reports.

Either way Task 1 already unblocks the customer, so Task 2 may be deferred entirely.

## Out of scope
- New engine directions or changing what `question`/`classifier`/`total` compute.
- Migrating existing reports' stored `percent_base` values.
- Variable-named labels for TWO-classifier charts (`classifying_var_2` set) — those keep
  the static labels for now.
- Stacked-bar row-summary interactions.

## Testing / verification
- **Repro (done):** `test_percent_direction_ticket.py` — `classifier` = wrong reading,
  `question` = wanted, `auto` already resolves to `question`. Keep as the regression anchor.
- **Frontend:** a component/Playwright check that on a gender×segment chart the
  "Percentages of" options read "% within each {gender label}" / "% within each {segment
  label}", and selecting the gender one makes each gender's bars sum to 100 % in the
  preview. Verify the static-label fallback when `variables` is empty.
- **Auto detection (only if Step 0 shows an `auto` mis-resolve):** a unit test that the
  previously-missed demographic variable now scores 3 and the chart resolves to `question`;
  existing `test_engine_percent_base_auto.py` + `test_percent_direction_ticket.py` stay green
  (guards against collateral direction changes).
- **Manual sign-off:** Seppo verifies against `case-134 / rep-209` after vacation.
