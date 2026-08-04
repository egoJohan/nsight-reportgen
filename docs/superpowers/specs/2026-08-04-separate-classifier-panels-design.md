# Separate classifier panels — two background variables side by side

Date: 2026-08-04
Status: approved design, not yet implemented

## Problem

A slide can already be split by two background variables, but the second one is
always **subordinate** to the first: the engine crosses them into combos
(`gender × age`), and the chart draws nine bars grouped under a rotated "Naiseksi"
/ "Mieheksi" label. That answers "how does age behave *within* each gender".

The common request is the other one: show the same question cut by gender **and**
cut by age, in one image, without crossing them. Crossing also thins the bases —
in `Erisan_hiustenmuotoilu_DATA` the `Muuten` gender group has n=4, so every
`Muuten × age` cell is unreportable and that panel renders empty.

A second, smaller problem sits next to it: on some slides the *Second classifying
variable* control is not there at all, with no explanation for why.

## Goals

- One slide can show a question split by variable A and by variable B, uncrossed.
- The choice between crossed and separate is explicit and per slide.
- No existing slide changes appearance when this ships.
- The reason a second classifier is unavailable is always visible to the author.

## Non-goals

- More than two background variables. The spec keeps `classifying_var` +
  `classifying_var_2`. A list of N classifiers is a larger reshaping of the chart
  spec, the config UI and the cross-tab code, and every added panel shrinks the
  others; it can be built later on top of this without redoing it.
- Batteries and comparison questions. A battery's bars are already
  `statement × segment`, and a comparison overlays its member questions as the
  series; in both, a per-variable panel split is a third dimension and needs its
  own design. Both keep today's behaviour and the new option is hidden for them.
- Per-panel chart types. Both panels use the slide's chart type.

## Author-facing behaviour

The existing *Two-variable layout* select (`xtab_layout`) gains a fourth option
and is added to the two stacked chart types, which do not have it today:

| Option | Crossed? | Result |
|---|---|---|
| `auto` (Automatic) | yes | grouped bars while the combos stay legible, else small multiples — unchanged |
| `grouped` (Grouped bars) | yes | bars pulled apart into groups by the first variable — unchanged |
| `small_multiples` (Small multiples) | yes | one panel per group of the first variable — unchanged |
| `separate` (**Separate panels, one per variable**) | **no** | one panel per *variable* |

`auto` never resolves to `separate`. Separate is always an explicit choice, so
deploying this changes no existing slide.

In separate mode each panel is an ordinary one-classifier chart of the same
question — the first panel split by `classifying_var`, the second by
`classifying_var_2` — with its own legend and its own bases. The *⇄ Swap* link
keeps working and simply reorders the panels. The two variables need not have the
same number of groups; each panel sizes its own bars.

Panel arrangement is automatic: **side by side**, unless there are more than 6
answer categories or any category label is longer than 14 characters, in which
case the panels stack **one above the other** so each keeps the full width.
Those are `_should_orient_horizontal`'s thresholds, reused because they measure
the same label pressure — here against the half-width a side-by-side panel gets.
Both bar orientations use this rule.

Chart types offering the option: `horizontal_bar`, `vertical_bar`,
`stacked_horizontal_bar`, `stacked_vertical_bar` — the four whose config already
carries `classifying_var_2`. The `xtab_layout` help text gains the new option's
description.

Each panel is titled with its variable's label ("Identifioitko itsesi…?",
"Ikäryhmät"), the way small multiples already title panels with the primary
group. The legend sits under its own panel, since the series differ per panel.

The methodology footer's *filter* annotation currently prints
`spec.classifying_var` alone (`elements.py:149`); in separate mode it names both
variables, so the footer does not claim the slide is split by only the first.

### The Total series

`show_total` keeps exactly its current meaning; separate mode adds no new rule.
`resolve_show_total` is consulted as today, and when it returns true each panel
gets its **own** Total series (`"<variable label> · Total"`) so the panel reads as
a complete chart. Note what today's rule already implies here:

- stacked types → `resolve_show_total` returns true even on `auto`, so both
  panels carry a Total stack by default;
- clustered types on a percentage statistic → `auto` returns false, so neither
  panel gets one unless the author sets *Show*.

The engine applies this decision itself in separate mode. It must, because
`series_values` drops the Total series by matching the literal string `"Total"`,
which never matches a `"… · Total"` panel segment — leaving that safety net
inoperative. The engine emits panel Totals only when `resolve_show_total` is true
and never emits a bare `"Total"` segment.

`base_n["Total"]` is a hard contract — `elements.py:120` indexes it directly to
print the N footer, and a `KeyError` there is deliberately not caught. Separate
mode keeps `base_n["Total"]` as the overall base regardless of whether any Total
*segment* is drawn.

### Banner classifiers, and the missing control

A banner classifier (a near-partition multi question, e.g. `polku`) is rejected
with a second classifier today because crossing possibly-overlapping masks has no
defensible base. Separate mode never crosses, so `polku` + age group is
well-defined: one panel of `polku`'s groups, one of age's.

Today `ClassifyingVarWidget` returns `null` for a banner primary — the whole row
disappears with no explanation (`StepConfigure.tsx:359`) — and the config panel
filters the field out entirely when no primary classifier is chosen
(`StepConfigure.tsx:721`). This is the most likely cause of the reported
"horizontal bar no longer lets me pick a second classifying variable": that
material flags `polku` as `banner: true`, so any slide classified by it loses the
control silently.

Simply disabling the field with a "switch the layout to Separate" hint would be
**circular**: the *Two-variable layout* control is itself filtered out until a
second classifier exists, so the author could never reach the option the hint
tells them to use. The resolution:

- No primary classifier yet → the second-classifier field renders **disabled**
  with "Choose a classifying variable first." (today it is absent).
- Banner primary → the second-classifier field stays **enabled**. Picking a
  variable is allowed.
- Once two classifiers are set and the primary is a banner, the *Two-variable
  layout* select offers only `separate`; the three crossed options are disabled
  with "*Polku*'s groups come from separate columns and can overlap, so they
  cannot be crossed with another variable." The stored value is forced to
  `separate` whenever the pair becomes banner + second — both when the second
  variable is chosen against a banner primary and when the primary is switched
  to a banner variable while a second one is already set — so the chart is never
  in a state the engine rejects.

The engine keeps its explanatory `ValueError` for banner + second classifier, but
raises it only when the resolved layout is crossed — it is now a guard against a
spec built outside the UI, not a path the UI can reach. The check **moves out of**
`_banner_masks`, which becomes a pure resolver: once that function takes a
variable name (see Engine), resolving the second slot would otherwise see
`classifying_var_2` still set and raise on every separate-mode chart.

## Engine

Separate mode is a **mask-based segmentation**, reusing the path banner
classifiers already take (`_classifier_masks` → `segment_bases(seg_masks=…)`),
not the combo path (`_combo_segmentation`). It is selected by
`spec.options.get("xtab_layout") == "separate"` — the same option the renderer
reads, so the two never disagree.

One helper, `_separate_masks(spec, data, model)`, returns the label→mask mapping
and the segment→variable mapping, and is called from the **three** paths that
accept two classifiers today: `_single`, `_multi`, and `_summary` (mean/median
and the other summary statistics, which reach `_combo_segmentation` through their
own branch). Each already consumes banner-shaped masks, so the call site is a few
lines in each.

Building it requires one refactor: `_banner_masks` and `_classifier_masks` both
read `spec.classifying_var` directly, so neither can resolve the *second*
variable. They gain a variable-name parameter (defaulting to today's behaviour)
so `_separate_masks` can resolve each slot independently — which also means a
banner variable works in **either** slot, not just the primary.

```
for cv in (classifying_var, classifying_var_2):
    for group_label, mask in groups_of(cv):
        segment[f"{var_label(cv)} · {group_label}"] = mask
```

Each segment is an ordinary cut of the sample with its own base — a respondent
counts once in the gender panel and once in the age panel, never in a product of
the two.

Three consequences that the crossed path handles differently and that separate
mode must get right:

1. **Segments carry display labels, not codes.** The crossed path emits code keys
   and `compute()` relabels them afterwards via `_relabel_combo_segments`. That
   function splits on `"|"` and looks each half up in a value-label map; run over
   separate-mode segments it would mangle them. Separate mode emits final display
   labels directly and `compute()` skips **both** relabel branches. Two variables
   sharing a group label (both having "Muu") stay distinct because the variable
   label prefixes every segment.
2. **`segment_primary` is set by the segmentation, not by the relabeller.** It maps
   each segment to its **source variable's label**. This is the existing hook the
   renderer groups panels by; pointing it at the variable rather than at the first
   classifier's groups is what makes one panel come out per variable.
   `_secondary_tick` then yields the group label for the per-bar tick, since the
   segments use the same `"A · B"` shape combo segments do.
3. **Bar sorting is per panel.** `_single` reorders the bars globally when the sort
   basis is `topbox_sum`/`top3_sum` (`engine.py:613`, `reals.sort(...)` over every
   real segment). In separate mode that would interleave the two variables'
   segments and destroy the panel grouping. The sort must run **within each
   `segment_primary` group**, leaving the groups themselves in variable order.

`percent_base` is forced to the classifier direction in separate mode. The
"within each answer category" direction distributes a classifier across the
question's categories, which is incoherent when the segments come from two
unrelated variables and would print labels that do not sum.

## Rendering

`_render_small_multiples` assumes every panel shares one secondary axis: it takes
`n_sec` from the widest group, colours by index, and builds a single shared legend
from `groups[0][1]`. Separate panels have *different* series per panel, so it gets
a sibling rather than a flag:

- `_render_variable_panels(ctx, cats, *, vertical)` — clustered bars, one legend
  per panel, value axis shared across panels (`max_val` over all of them so the
  bars stay comparable), category axis shared. Series colours restart at index 0
  in each panel: the panels show different variables, so a shared colour ramp
  would imply a correspondence between, say, "Naiseksi" and "18-34-vuotiaat".
- `_render_stacked_variable_panels(ctx, cats)` — the stacked equivalent. The
  stacked builders have **no panel path at all** today (they only do the
  grouped/rotated-primary-label layout), so this is new drawing code, not a
  branch. Each panel is a 100 % stack; the row-summary column, where configured,
  is drawn per panel against that panel's own bars, looked up through
  `row_summary_keys`.

`new_figure_grid` currently lays out `1 × n` with `sharey=True`. It gains a
`rows` parameter (or a `new_figure_stack` sibling) for the one-above-the-other
arrangement; with two rows the category axis is shared per column and the value
axis across both.

`_resolve_xtab_layout` returns `"separate"` when the option is set, and all four
builders dispatch on it.

## Error handling and edge cases

| Case | Behaviour |
|---|---|
| Only one classifier set | The layout control is hidden (it already is, via the `classifying_var_2` filter) and the chart renders as today. |
| A group with a tiny base | Unchanged from single-classifier charts: the renderer drops segments under `MIN_SEGMENT_BASE` (10). Crossing is what made these common; separate mode largely removes the problem. A whole panel can still vanish if every one of its groups is tiny. |
| Both variables the same | Already prevented — the candidate filter excludes the variable used in the other picker. |
| A variable with many groups | No cap. The panel gets as many series as the variable has groups, exactly like a one-classifier chart with that variable. |
| Banner classifier in either slot | Allowed, and the layout is forced to `separate` (see above). |
| A variable resolves to no groups (all-missing column, stale name) | That panel is omitted and the chart draws the surviving one — the same lenient degradation `_single` already applies to a stale classifier. |
| Battery or comparison question | Option hidden; today's behaviour unchanged. |
| Chart type switched away from a two-classifier type | `handleTypeChange` already clears `classifying_var_2`; **it must also clear `options.xtab_layout`**, which it does not today, so a stale `separate` cannot survive on a type that has no second classifier. |
| Report saved before this ships | No migration. `xtab_layout` lives in the free-form `options` bag (`patchField` routes it there, and the engine reads `spec.options`), so an absent value keeps `auto` and today's crossed behaviour. |

## Testing

Unit (`tests/suite/unit/stats/`):

- separate segmentation produces `len(groups(cv1)) + len(groups(cv2))` segments,
  never the product — for `_single`, `_multi` and `_summary`;
- `auto` never resolves to `separate`, for every combination of group counts;
- each segment's `base_n` equals that group's own base, and `base_n["Total"]`
  remains the overall base;
- `segment_primary` maps every segment to its source variable label;
- two identically-labelled groups from different variables stay distinct;
- `compute()` leaves separate-mode segment labels untouched (no combo relabelling);
- `percent_base` is forced to the classifier direction;
- `resolve_show_total` true → exactly one Total segment per variable and no bare
  `"Total"` segment; false → none;
- a `topbox_sum` sort reorders bars **within** each panel and never interleaves
  the two variables;
- a banner classifier is accepted in separate mode and still rejected when
  crossed — in the primary slot and in the second slot.

Integration (`tests/suite/integration/render/`):

- each of the four chart types renders exactly one picture in separate mode;
- the number of panels equals the number of variables (2), not the number of
  groups of the first;
- each panel's legend lists its own variable's groups;
- the vertical arrangement is chosen for long category labels and the
  side-by-side one for short;
- each panel is titled with its variable's label;
- the filter annotation names both variables;
- a stacked separate panel keeps its row-summary column aligned to that panel's
  bars (guards the defect fixed on 2026-08-03);
- the N footer still renders (guards the `base_n["Total"]` contract).

Frontend: `tsc -b`, plus a Playwright check that on a banner-classified slide the
second-classifier field is selectable, that choosing a variable forces the layout
to *Separate panels*, and that the crossed options are disabled with their reason.

## Rollout

Additive and opt-in. No report migration; charts saved without `xtab_layout` keep
`auto`, which keeps today's crossed behaviour.
