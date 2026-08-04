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
`Muuten × age` cell is unreportable, and the panel renders empty.

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
- Batteries. A battery's bars are already `statement × segment`; a per-variable
  panel split is a third dimension and needs its own design. Batteries keep
  today's nested behaviour and the new option is hidden for them.
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
keeps working and simply reorders the panels.

Panel arrangement is automatic: **side by side** unless the category labels need
the full width, in which case the panels stack **one above the other**. Each
panel gets half the slot width, so the rule is the same pressure
`_should_orient_horizontal` measures for bar orientation, applied to that half:
stack vertically when there are more than 6 answer categories or any category
label is longer than 14 characters. Both bar orientations use this rule.

The *Total column* control keeps its meaning: `auto` hides the Total series (a
within-group distribution cannot sum with it), `on` draws a Total series in
**both** panels with the same value as a reference, `off` omits it.

Chart types offering the option: `horizontal_bar`, `vertical_bar`,
`stacked_horizontal_bar`, `stacked_vertical_bar` — the four whose config already
carries `classifying_var_2`.

### The banner restriction lifts in separate mode

A banner classifier (a near-partition multi question, e.g. `polku`) is rejected
with a second classifier today because crossing possibly-overlapping masks has no
defensible base. Separate mode never crosses, so `polku` + age group is
well-defined: one panel of `polku`'s groups, one of age's. The engine guard in
`_banner_masks` therefore fires only for the crossed layouts.

### Silent hides become visible reasons

`ClassifyingVarWidget` returns `null` — the whole row disappears — when the
primary classifier is a banner variable (`StepConfigure.tsx:359`), and the config
panel filters the field out entirely when no primary classifier is chosen
(`StepConfigure.tsx:721`). Both cases now render the field **disabled with a
hint**:

- no primary yet → "Choose a classifying variable first."
- banner primary in a crossed layout → "*Polku*'s groups come from separate
  columns and can overlap, so they cannot be crossed with another variable.
  Switch the two-variable layout to Separate panels to use both."

This is the most likely cause of the reported "horizontal bar no longer lets me
pick a second classifying variable": that material flags `polku` as
`banner: true`, and any slide classified by it loses the control with no
explanation.

## Engine

Separate mode is a **mask-based segmentation**, reusing the path banner
classifiers already take (`_classifier_masks` → `segment_bases(seg_masks=…)`),
not the combo path (`_combo_segmentation`).

```
masks = {}
for cv in (classifying_var, classifying_var_2):
    for group_label, mask in groups_of(cv):
        masks[f"{cv}|{group_label}"] = mask
```

Each segment is an ordinary cut of the sample with its own base — a respondent
counts once in the gender panel and once in the age panel, never in a product of
the two. Segment keys are namespaced by variable so two variables sharing a group
label (e.g. both having "Muu") stay distinct; they are relabelled for display to
`"<variable label> · <group label>"`, the same shape combo segments already use,
so `_secondary_tick` yields the group label for the per-bar tick.

`SeriesResult.segment_primary[seg]` is set to the **source variable's label**.
This is the existing hook the renderer groups panels by; pointing it at the
variable rather than at the first classifier's groups is what makes one panel come
out per variable.

`percent_base` is forced to the classifier direction in separate mode. The
"within each answer category" direction distributes a classifier across the
question's categories, which is incoherent when the segments come from two
unrelated variables and would print labels that do not sum.

When `show_total` resolves to on, a `"<variable label> · Total"` segment is added
per variable so each panel carries its own reference series.

## Rendering

`_render_small_multiples` assumes every panel shares one secondary axis: it takes
`n_sec` from the widest group, colours by index, and builds a single shared legend
from `groups[0][1]`. Separate panels have *different* series per panel, so it gets
a sibling rather than a flag:

- `_render_variable_panels(ctx, cats, *, vertical)` — clustered bars, one legend
  per panel, shared value axis across panels (`max_val` over all panels so the
  bars stay comparable), shared category axis.
- `_render_stacked_variable_panels(ctx, cats)` — the stacked equivalent. The
  stacked builders have **no panel path at all** today (they only do the
  grouped/rotated-primary-label layout), so this is new drawing code, not a
  branch. Each panel is a 100 % stack; the row-summary column, where configured,
  is drawn per panel against that panel's bars.

`new_figure_grid` currently lays out `1 × n` with `sharey=True`. It gains a
`rows` parameter (or a `new_figure_stack` sibling) for the one-above-the-other
arrangement; with two rows the category axis is shared per column and the value
axis is shared across both.

`_resolve_xtab_layout` returns `"separate"` when the option is set, and the two
clustered builders and the two stacked builders dispatch on it.

## Error handling and edge cases

| Case | Behaviour |
|---|---|
| Only one classifier set | Option is inert; the chart renders as today. The control is hidden (it already is, via the `classifying_var_2` filter). |
| A group with a tiny base | Unchanged from single-classifier charts: the renderer drops segments under `MIN_SEGMENT_BASE` (10). Crossing is what made these common; separate mode largely removes the problem. |
| Both variables the same | Already prevented — the candidate filter excludes the variable used in the other picker. |
| A variable with many groups | No cap. The panel gets as many series as the variable has groups, exactly like a one-classifier chart with that variable. |
| Banner primary + crossed layout | Engine raises the existing explanatory `ValueError`; the UI disables the control with the hint above. |
| Battery question | Option hidden; nested behaviour unchanged. |
| Switching chart type away from a two-classifier type | Existing `handleTypeChange` already clears `classifying_var_2`; it also clears `xtab_layout`. |

## Testing

Unit (`tests/suite/unit/stats/`):

- separate segmentation produces `len(groups(cv1)) + len(groups(cv2))` segments,
  never the product;
- each segment's `base_n` equals that group's own base, and the two variables'
  bases each sum to the sample (minus their own missing);
- `segment_primary` maps every segment to its source variable label;
- namespacing keeps two identically-labelled groups from different variables apart;
- `percent_base` is forced to the classifier direction;
- `show_total=on` yields one Total segment per variable, `auto`/`off` none;
- a banner classifier is accepted in separate mode and still rejected when crossed.

Integration (`tests/suite/integration/render/`):

- each of the four chart types renders exactly one picture in separate mode;
- the number of panels equals the number of variables (2), not the number of
  groups of the first;
- each panel carries its own legend entries, drawn from its own variable;
- the vertical arrangement is chosen for long category labels and the
  side-by-side one for short;
- a stacked separate panel keeps its row-summary column aligned to that panel's
  bars (guards the defect fixed on 2026-08-03).

Frontend: `tsc -b` plus a Playwright check that the disabled second-classifier
field appears with its hint on a banner-classified slide, and becomes enabled
after switching the layout to Separate panels.

## Rollout

Additive and opt-in. `xtab_layout` already lives in the free-form `options` dict,
so no report migration is needed: charts saved without it keep `auto`, which
keeps today's crossed behaviour.
