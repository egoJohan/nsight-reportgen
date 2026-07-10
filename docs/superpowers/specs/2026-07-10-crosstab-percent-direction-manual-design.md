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
classifier and without relying on `auto`. Engine behaviour and the stored `percent_base`
values are unchanged — this is a **labelling/UX** change on the Design control, plus an
optional `auto` tie-break refinement.

## Design

### 1. Variable-named option labels (primary, frontend only)

`percent_base` gets a dedicated widget (or a special case in the schema-driven select)
that builds its option labels from the chart's two variables, which the Design config
already has in `WidgetProps` (`question` = base, `variables` + `chart.classifying_var`
= classifier):

- let `baseLabel` = the base variable's short label (from `variables`, keyed by
  `question.variables[0]`; fall back to the question text, truncated).
- let `clfLabel` = the classifying variable's label (from `variables`, keyed by
  `chart.classifying_var`).

Rendered options (value → label):

- `question` → **"% within each {baseLabel}"** — help: "each {baseLabel}'s bars sum to 100 %".
- `classifier` → **"% within each {clfLabel}"** — help: "each {clfLabel}'s bars sum to 100 %".
- `total` → **"% of the total"**.
- `auto` → **"Automatic (recommended)"** — help: "picks the natural direction from the
  variables".

So for gender × segment the analyst sees "% within each Sukupuoli" vs "% within each
segment" and directly picks the one that sums each gender to 100 %, regardless of which
variable is the internal base. The mapping `question ↔ baseLabel`, `classifier ↔ clfLabel`
holds because `question` distributes within each base category and `classifier` within
each classifier group.

Fallbacks: if either label is missing (labels not loaded, no classifier), fall back to
the current static labels so the control never renders blank. When `chart.classifying_var`
is unset the whole control is already hidden (existing behaviour) — unchanged.

### 2. `auto` tie-break refinement (secondary, backend, optional)

`resolve_percent_base` currently returns `"question"` only when the base **strictly**
outranks the classifier; ties fall back to the legacy `"classifier"`. When exactly one
side is a demographic/segmenter (score 3) it already resolves correctly; the residual
risk is a **tie** (both sides equal, e.g. a demographic not matched by the regex) landing
on `"classifier"` — the misleading direction. Refinement: on a tie, prefer the direction
whose **denominator is the stronger segmenter role**, i.e. keep the denominator on the
demographic/segment side; only fall back to `"classifier"` when the two are genuinely
symmetric. This is a small change to the final comparison in `resolve_percent_base`;
guard it with the existing `test_engine_percent_base_auto.py` + a new tie case. Mark
OPTIONAL — the manual relabel (part 1) already unblocks the customer.

## Out of scope
- New engine directions or changing what `question`/`classifier`/`total` compute.
- Migrating existing reports' stored `percent_base` values.
- Stacked-bar row-summary interactions.

## Testing / verification
- **Repro (done):** `test_percent_direction_ticket.py` — `classifier` = wrong reading,
  `question` = wanted, `auto` already resolves to `question`. Keep as the regression anchor.
- **Frontend:** a component/Playwright check that on a gender×segment chart the
  "Percentages of" options read "% within each {gender label}" / "% within each {segment
  label}", and selecting the gender one makes each gender's bars sum to 100 % in the
  preview. Verify the static-label fallback when `variables` is empty.
- **Auto tie-break (if built):** a unit test where base and classifier both score 2 and
  one is a demographic → resolves to `question` (not `classifier`); existing auto tests
  stay green.
- **Manual sign-off:** Seppo verifies against `case-134 / rep-209` after vacation.
