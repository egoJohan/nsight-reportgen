# Cross-tab (2 classifiers) layout — use space sensibly

## Goal
When a chart is split by TWO classifying variables, lay the bars/stacks out so both
variables read clearly and the available space is used — instead of jamming the flat
cross-product into one cluster (clustered) or a flat undifferentiated row (stacked).
Customer: "Joissakin tilanteissa se niputtaa palkit tarpeettomasti yhteen … repimällä
palkit erilleen [saisi selkeämmän]. Päällekkäisissä stacked bareissa mukaan tulee vain
yksi muuttuja vaikka tilaa olisi hyvin toiselle muuttujalle."

## Current behaviour (verified by rendering)
- Engine `_combo_segmentation` builds flat combo segments `"<c1>|<c2>"`, primary-major,
  relabelled to `"Mies · 18-30"` (separator `" · "`). `_single` renders them as ordinary
  segments PLUS a `Total` segment.
- **Clustered:** each answer category is one cluster of N combo bars (+ Total). All bars
  are teal shades → primary (gender) vs secondary (age) indistinguishable; cramped.
- **Stacked:** each combo is one 100%-stacked bar in a FLAT row; the primary classifier
  isn't grouped → reads as one variable; x-tick labels collide with the legend.

## Decisions (customer)
- **Auto layout that adapts:** grouped-with-gaps when it fits; small multiples (panels)
  when there are too many combos. PLUS a manual control to steer it.

## Design

### Shared: segment grouping metadata (engine)
`_combo_segmentation`/`_single` already know each segment's primary code. Add to
`SeriesResult` an optional `segment_primary: dict[str, str]` (segment label → primary
group label, e.g. `"Mies · 18-30" → "Mies"`). Renderers use it to group segments without
parsing the display string. Cross-tab `_single` also DROPS the `Total` segment (a mixed
total across both classifiers is noise, not signal — the customer wants the split).

### Part A — Grouped-with-gaps (Phase 1, the default when it fits)
In `bars.py`, when `segment_primary` is present:
- **Positioning:** order segments primary-major (already are); insert an EXTRA gap
  between segments whose primary group differs, so each primary group is visually
  separated. (Clustered: within each answer cluster; stacked: along the bar axis.)
- **Colour (stays in the teal palette):** the PRIMARY grouping is conveyed by the gap +
  a group label/bracket, NOT a new hue. Colour encodes the SECONDARY value as a shade
  ramp (age light→dark), used consistently in every primary group, so age reads the same
  across Mies and Nainen. Stacked bars keep the ANSWER colour (the stack's meaning).
- **Group labels:** a primary-group label/bracket per group (Mies / Nainen); the
  secondary value on the per-bar tick or the legend. Both variables stay legible without
  a second hue. (Exact labelling — bracket vs two-level axis vs legend — decided in impl.)
- **Fixes:** drop Total; move the stacked legend clear of the x-tick labels (reuse the
  dynamic legend placement already in `_place_series_legend`).

### Part B — Small multiples (Phase 2, auto-fallback + manual)
When combos exceed what one panel fits (rule: `n_secondary * n_answer_bars` too wide, or
`n_combos > ~10`), render one matplotlib subplot per PRIMARY value — each a normal
clustered/stacked chart of (answer × secondary). Shared y-axis + one legend. Auto picks
this over grouped when grouped would be cramped.

### Part C — Manual control (Phase 1)
A per-chart config option (plugin `config_schema`, stored in `spec.options`):
`xtab_layout`: `auto` (default) | `grouped` | `small_multiples`. Auto uses the fit rule
(A vs B). Exposed only when `classifying_var_2` is set (schema is conditional, like
`classifying_var_2`). "Which classifier is the outer/primary group" is steered by SWAPPING
the two classifier pickers (primary = `classifying_var`); a small "Swap" affordance in the
2nd-classifier widget exchanges the two values — no new engine field.

## Testing (TDD)
- **Engine:** `segment_primary` maps every combo segment to its primary label; cross-tab
  `_single` has no `Total` segment; single-classifier and non-classifier charts are
  unchanged (no `segment_primary`).
- **Render (image-diff/asserts):** grouped layout inserts gaps between primary groups and
  emits one group label per primary; small_multiples emits N subplots; `xtab_layout`
  routes correctly; auto picks grouped for few combos, panels for many.
- **API/serde:** `xtab_layout` round-trips in `options`; schema exposes it only with a 2nd
  classifier.
- Full-tree regression (touches the hot `_single`/bars path).

## Phasing
- **Phase 1 — A + C:** grouped-with-gaps + drop Total + colour-by-primary + group labels +
  overlap fix + the `xtab_layout` control (auto==grouped for now) + swap. Immediate win.
- **Phase 2 — B:** small multiples + the auto fit-rule fallback.

## Risks
- 3 nested dimensions (answer × primary × secondary) on a 2-D axis is inherently busy;
  grouping + colour hue + labels mitigate but very high cardinality still needs panels
  (Phase 2) — the fit-rule must be conservative so we don't ship a cramped "grouped".
- 3 nested dimensions are busy even when grouped; the primary-by-gap + secondary-by-shade
  scheme stays in-palette but leans on the group label/bracket for the primary — if that
  proves unclear in testing, revisit (a second accent hue is the fallback).
- `segment_primary` is additive to SeriesResult (optional, default None) so existing
  renderers/exports are untouched.
