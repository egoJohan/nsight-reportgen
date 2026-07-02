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
Both distribution (`_single`) and summary/mean (`_summary`) results flow through
`_relabel_combo_segments` in `compute` (the ONE cross-tab-only seam) — do the work there:
- Add to `SeriesResult` an optional `segment_primary: dict[str, str] | None = None`
  (relabelled segment → primary group label, e.g. `"Mies · 18-30" → "Mies"`), built from
  the `m1` code→label map already computed there. Additive/optional → serde, exports, and
  every non-cross-tab renderer are untouched.
- **Drop `"Total"` from `segments`** for cross-tab (a total across both classifiers is
  noise). Keep `base_n["Total"]` — the footer "n = N" still reads it; only the Total BAR
  goes away.
- Segments stay primary-major (Mies·…, then Nainen·…), so a renderer groups by scanning
  consecutive same-primary runs.

### Part A — Grouped-with-gaps (Phase 1, the default when it fits)
In `bars.py`, GATED on `ctx.series.segment_primary` being present (so single-classifier and
non-classifier charts keep their exact current layout — no regression):
- **Positioning:** segments are primary-major; insert an EXTRA gap where the primary group
  changes, separating each group. Clustered: within each answer cluster the sub-bars split
  into primary groups; stacked: the stacked bars split into primary groups along the axis.
- **Colour (stays in the teal palette):** colour by POSITION-WITHIN-PRIMARY-GROUP (reset at
  each group), so the secondary reads as the same light→dark ramp in every group (age 18-30
  light … 51+ dark under both Mies and Nainen) — no second hue needed. Stacked bars keep the
  ANSWER colour (the stack's meaning); the grouping is the gap + label only.
- **Labelling (concrete):**
  - *Clustered:* the gap separates primary groups; the legend already names each combo
    (`Mies · 18-30`), so no extra axis label — just the gap.
  - *Stacked:* x-tick = the SECONDARY value only (`18-30`), and a primary group label
    centred under each group's bars (`Mies` / `Nainen`) — fixes the current combo-label vs
    legend overlap and shows both variables.
- **Fixes:** Total already dropped (engine); reuse the dynamic `_place_series_legend` so the
  legend clears the x-ticks.

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
