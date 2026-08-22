# Several pie charts on one slide — split by one background variable

Date: 2026-08-22
Status: approved design, not yet implemented
Trello: [Useampi piirakkakuvio samalla sivulla](https://trello.com/c/j0LVdj6k)

## Problem

A pie slide shows one circle covering the whole sample. The common request is to
see the same question cut by one background variable — "voitko tehdä etätöitä"
for women, for men, for the rest — as two or three pies side by side on one
slide, each its own 100%.

Today that is not merely unstyled, it is impossible: pie, doughnut and funnel are
registered with `single_series_schema()` (`render/config_schema.py:281`), which
carries no classifying-variable field at all, and the configure panel actively
clears a chosen classifier when a slide is switched to one of these types
(`web/src/components/wizard/StepConfigure.tsx:844`). The image renderer reinforces
it: `_render_pie` reads `data[segs[0]]` (`render/image/pie.py`), so a multi-segment
series would silently collapse to its first group.

The card also asks for a guardrail: more than three groups do not fit one page, and
the author should be told.

## Goals

- One slide shows the same question as one pie per group of a single background
  variable, uncrossed, each pie its own 100%.
- The author is warned before rendering when the chosen variable has more than
  three groups.
- What the slide actually drew — including any group it left out — is recorded on
  the slide itself, not only in the editor.
- No existing slide changes appearance when this ships.

## Non-goals

- **Crossing two background variables on a pie.** These types keep one classifier;
  `classifying_var_2` and `xtab_layout` stay out of their schema. A pie of
  `gender × age` is nine circles and answers nothing legibly.
- **A "Total" reference pie.** `show_total` stays hidden for these types. The
  overall distribution remains available as an ordinary un-split pie slide.
- **More than three pies.** Four circles on a 4:3 slot is the case the card exists
  to prevent, not a layout to support.
- **The native (OOXML) chart path.** It keeps today's single-series behaviour.
- **Per-pie chart types**, and batteries/comparison questions, which are already
  multi-series and would make the panel split a third dimension.

## Author-facing behaviour

### The control

Pie, doughnut and funnel gain the ordinary **classifying variable** picker — the
same field, the same segmentable-variable filter, the same labels as every
clustered bar chart. Their schema becomes `single_series_schema()` plus
`classifying_var_field()`; `classifying_var_2_field()`, `xtab_layout_field()` and
`show_total_field()` remain absent.

Leaving the picker empty produces exactly today's slide. The split is never
inferred: choosing a variable IS the option the card asks for, so no separate
toggle is added.

The frontend rule that drops a stale `classifying_var` when the chart type changes
tests the backend catalog rather than a hard-coded type list — `supportsClassifying`
asks whether the type's config carries a `classifying_var` field
(`StepConfigure.tsx:843`). Adding the field to the schema therefore exempts these
three types automatically, with no frontend change: switching a gender-split bar
chart to a pie keeps the split and draws three pies, rather than silently flattening
the slide to one circle. The behaviour still needs a test, since nothing in the
frontend states the intent.

### What the slide draws

One pie per group, left to right, in the **variable's own group order** — age
brackets read 18–29, 30–44, 45–59, never reordered by size. Each panel is titled
with its group label and carries its own base beneath it. A single legend sits
centred below the row: the categories are identical in every pie, so a per-panel
legend would be the same list three times.

```
Voitko työssäsi tehdä etätöitä?

     Naiset            Miehet             Muut
      ___               ___               ___
     /   \             /   \             /   \
    | 54% |           | 41% |           | 60% |
     \___/             \___/             \___/
     n = 512           n = 486           n = 25

           ■ En voi      □ Kyllä voin

Osuus vastaajista (%) · n = 1023
```

Each pie renormalises to its own base, so a slice answers "of *this* group, what
share said X". Slice colours are keyed to the answer category and identical across
panels, so one colour means one answer everywhere; the *Not answered* slice keeps
its MUTED grey (R4.2).

### More than three groups

Three checks, deliberately distinct, because they count different things:

| Where | Counts | Does |
|---|---|---|
| Configure panel | the variable's values (`Variable.n_values`) | warns, naming the variable, that only the three largest groups will be drawn |
| Renderer | the groups that actually survive | keeps the three largest by base, draws them in the variable's own order |
| Slide footer | what was drawn | names the omitted groups |

The two counts can legitimately differ — grouping overrides and empty categories
mean a four-value variable may yield three drawable groups. So the panel warning is
**advisory** and the footer is **authoritative**: it is the record that travels with
the deck. Naming the omitted groups in the footer is therefore not optional. Silently
dropping the smallest groups is the real risk this feature carries, and the footer is
what keeps the omission visible to whoever reads the deck rather than to whoever
built it.

Ranking is by base size; ties break on the variable's own group order, so the choice
is deterministic.

## Implementation shape

### Rendering

`_render_pie` grows a panel loop rather than borrowing the bar renderer's panel
machinery from `image/bars.py`. That machinery (`_side_by_side_layout`,
`_stack_panels`, `_MIN_HGUTTER_PLOT_IN`) exists to measure tick-label gutters and to
decide between side-by-side and stacked layouts — decisions a pie does not have,
because it has no axis furniture and is capped at three panels. Extracting it would
mean regression risk to the separate-panels feature in exchange for machinery pie
would not use. If a fourth chart family later needs panels, the two can be unified
then.

The layout is a column split of the existing wide figure: N equal square axes with
`set_aspect("equal")`, panel titles above, a shared `fig.legend` centred below. The
single-group case must produce byte-comparable output to today's slide — one axes,
legend to the right — so the un-split path is preserved rather than re-expressed as
a one-panel special case of the new one.

Funnel gets the same option against its own renderer (`image/funnel.py`); doughnut
shares `_render_pie` and needs no separate work.

### Feasibility

`charts/pie.py::_is_parts_of_whole` decides whether a pie is honest at all by asking
whether the categories partition the base. It currently evaluates a single series.
With a split it must evaluate **per group** — a question that partitions overall can
fail to partition within a thin group. A pie is offered only when every drawn group
partitions its own base, under the same `_UNDERSHOOT_TOL_PCT` tolerance.

### Footer

`add_filter_annotation` (`render/elements.py:146`) already names the classifying
variable, and already has a branch for naming two variables in the separate layout.
It gains the omitted-group clause for capped pie slides.

## Testing

**Renderer** — N groups draw N pie axes; five groups draw three, and they are the
three largest; display order follows the variable's group order, not base size; the
legend is emitted once; each panel's slices sum to its own 100%; a single group
renders today's un-split slide.

**Schema** — pie, doughnut and funnel expose `classifying_var` and expose neither
`classifying_var_2`, `xtab_layout` nor `show_total`.

**Feasibility** — a question that partitions overall but not within one group does
not offer a pie once split by that variable.

**Footer** — a capped slide names its omitted groups; an uncapped one does not.

**Frontend** — the warning appears at four-plus groups and not at three; switching a
classified bar chart to a pie preserves the classifier.
