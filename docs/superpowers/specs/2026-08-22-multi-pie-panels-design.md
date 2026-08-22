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
carries no classifying-variable field at all. Three further layers enforce the same
assumption, and each has to be accounted for — though one turns out to need no code
change:

- `_is_parts_of_whole` (`charts/pie.py:50`) returns False when `n_series != 1`, so
  both `pie_suitability` and `pie_suggest` return None — the chart type would
  *disappear from the picker* the moment a classifier were set.
- `_render_pie` (`image/pie.py`) reads `data[segs[0]]`; `image/funnel.py:33` does the
  same. A multi-segment series silently collapses to its first group.
- The configure panel clears a stale classifier when a slide switches to a type
  whose schema has no such field.

The card also asks for a guardrail: more than three groups do not fit one page, and
the author should be told.

## Goals

- One slide shows the same question as one pie per group of a single background
  variable, uncrossed, each pie its own 100%.
- The author is warned before rendering when the chosen variable has more than
  three groups.
- What the slide actually drew — including any group it left out, and for whatever
  reason — is recorded on the slide itself, not only in the editor.
- No existing slide changes appearance when this ships.

## Non-goals

- **Crossing two background variables on a pie.** These types keep one classifier;
  `classifying_var_2` and `xtab_layout` stay out of their schema. A pie of
  `gender × age` is nine circles and answers nothing legibly.
- **A "Total" reference pie.** `show_total` stays out of the schema. The overall
  distribution remains available as an ordinary un-split pie slide.
- **More than three pies.** Four circles on a 4:3 slot is the case the card exists
  to prevent, not a layout to support.
- **Splitting the native (OOXML) chart path.** It draws one circle — but it does
  need a small guard, see *The native path needs a guard*.
- **Per-pie chart types**, and batteries/comparison questions, which are already
  multi-series and would make the panel split a third dimension.
- **A split-aware AI headline** — see *Known limitations*.

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

The frontend rule that drops a stale `classifying_var` on a chart-type change tests
the backend catalog rather than a hard-coded type list — `supportsClassifying` asks
whether the type's config carries a `classifying_var` field
(`StepConfigure.tsx:843`). Adding the field to the schema therefore exempts these
three types automatically, with no frontend change: switching a gender-split bar
chart to a pie keeps the split and draws three pies rather than silently flattening
the slide to one circle. It still needs a test, because nothing in the frontend
states the intent.

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

Slice colours are keyed to the answer category and identical across panels, so one
colour means one answer everywhere; the *Not answered* slice keeps its MUTED grey
(R4.2). The footer's overall N stays the whole base, with each panel's own base
under its pie.

### Each pie is its own 100%

`resolve_percent_base` returns `"classifier"` unconditionally
(`stats/percent_base.py:103`, Johan's call 2026-07-10): every classifying-variable
group already sums to 100% before the renderer sees it. This matters more than it
looks. `_render_pie` renormalises whatever values it gets (`total = sum(vals)`), so
had the engine produced "% of total sample", the renderer would have silently
rewritten those numbers into within-group percentages and the slice labels would no
longer be the numbers the engine computed. Because the direction is already
within-group, that renormalisation is a no-op and the printed percentages are
truthful. No `percent_base` control is added, and this invariant is worth a test of
its own — it is what keeps the numbers honest, and it is invisible in the renderer.

### Which groups become panels

Three filters apply in order, and only the last is new:

1. **Groups below 10 respondents are already dropped.** `series_values`
   (`image/_mpl.py:249`) keeps a segment only when `base_n >= MIN_SEGMENT_BASE`
   (10), precisely so a tiny classifier group never renders a misleading 100%.
   Nothing about that changes; the pie panels inherit it.
2. **The bare "Total" segment is excluded from the panels.** The engine appends
   `"Total"` to `segments` for a plain classifier unconditionally
   (`stats/engine.py:596`), and `resolve_show_total` only removes it for a
   within-category percentage. A pie whose statistic is **count** resolves
   `show_total` to True, so without an explicit exclusion a count pie would grow a
   fourth, whole-sample circle — contradicting the no-total decision through a path
   no one would think to test. The panel list therefore excludes `"Total"` — but
   only when something else remains, mirroring the rule `series_values` already
   applies to it ("unless it is the ONLY series"). Excluding it unconditionally
   would leave a slide with **zero** panels in the case below, where `"Total"` is
   all that is left. With no classifier, the lone `"Total"` segment is the one pie,
   exactly as today.
3. **At most three panels.** Of what survives, the three largest by base are kept,
   ranked by `base_n` and displayed in the variable's own group order. Ties break on
   that same group order, so the choice is deterministic.

**One drawable group** still draws a titled single panel, not the un-split slide: a
reader looking at one circle must be told which group it describes, and the footer
names the groups that fell away. The un-split layout — untitled, legend to the right
— belongs only to a slide with no classifier at all.

**No drawable group** — every group below the base floor — falls back to the
`"Total"` segment via the rule `series_values` already applies, and the slide
degrades to one whole-sample pie. That is the right degradation, but it is also an
omission, and the most severe one, so the footer says the split could not be drawn
rather than leaving a whole-sample circle looking like the author's intent.

### One rule, one place

Four things now depend on the same question — *which groups become panels?* The
feasibility check asks it to decide whether to offer a pie at all, the renderer asks
it to draw, the footer asks it to name what was left out, and the tests ask it to
assert. If any two answer differently, the tool offers a pie it then draws wrong, or
draws a group the footer does not account for.

So the answer lives in **one** function — segments in, panel labels plus the reasons
for every exclusion out — and all four callers read it. Nothing re-derives the base
floor, the `"Total"` rule or the cap for itself. This is the discipline
`_side_by_side_layout` already applies next door, where one function is documented as
"the single source of truth for BOTH the side-by-side FIT DECISION and the actual
layout".

### More than three groups

Three checks, deliberately distinct, because they count different things:

| Where | Counts | Does |
|---|---|---|
| Configure panel | the variable's values (`Variable.n_values`) | warns, naming the variable, that only the three largest groups will be drawn |
| Renderer | the groups that survive the filters above | keeps the three largest, draws them in the variable's own order |
| Slide footer | what was drawn | names the groups left out, and why |

The panel's warning uses the inline notice already in this file — the bordered
`AlertCircleIcon` block — and **not** `toast.warning`, which the file also offers. A
toast is the lazier fit and the wrong one: it disappears, and a notice about what the
deck will leave out has to stay visible for as long as the variable is chosen.

The counts legitimately differ: a four-value variable one of whose groups has n=8
draws three pies and drops nothing to the cap, while the panel still warned. So the
panel warning is **advisory** and the footer is **authoritative** — it is the record
that travels with the deck. Naming the omitted groups there is not optional. Silently
dropping the smallest groups is the real risk this feature carries, and the footer is
what keeps the omission visible to whoever reads the deck rather than only to whoever
built it. It distinguishes the two reasons, because they mean different things to a
reader: a group omitted for a thin base is a group that could not be reported at all,
while a group omitted by the cap is one that fits the data but not the page.

### Category order is already shared

No work is needed to keep the pies comparable. `sort_categories` is applied once per
question, over rows whose sort keys are read from the **Total** cell — the engine
states the intent itself: *"Sorting keys come from the Total column so the category
order is stable however the segments differ."* Every segment inherits that one order,
so the shared legend and the colour-to-answer mapping are safe by construction. The
same holds for `show_empty_categories`, which drops rows on the Total value before
the split.

## Implementation shape

### Rendering

`_render_pie` grows a panel loop rather than borrowing the bar renderer's panel
machinery from `image/bars.py`. That machinery (`_side_by_side_layout`,
`_stack_panels`, `_MIN_HGUTTER_PLOT_IN`) exists to measure tick-label gutters and to
choose between side-by-side and stacked layouts — decisions a pie does not have,
because it has no axis furniture and is capped at three panels. Extracting it would
mean regression risk to the separate-panels feature in exchange for machinery pie
would not use. If a fourth chart family later needs panels, the two can be unified
then.

The layout is a column split of the existing wide figure: N equal square axes with
`set_aspect("equal")`, panel titles above, a shared `fig.legend` centred below.
Placement stays `place_picture_square`, which scales the PNG to fit the slot on its
limiting dimension and so preserves the panel row's aspect — that is what keeps each
circle a circle rather than an oval, and it needs no change for a wider figure. The
un-split path is **preserved as it stands** rather than re-expressed as a one-panel
case of the new one — its legend sits to the right, and existing slides must not
shift.

### Feasibility

`_is_parts_of_whole` must stop rejecting multi-series outright. The replacement:
with a classifier, a pie is offered only when **every panel it would draw partitions
its own base**, under the same `_UNDERSHOOT_TOL_PCT` tolerance. A question that
partitions overall can fail to within a thin group, and that group's pie would be
the one that quietly does not add up. The check runs over the shared panel list —
after the base floor and the `"Total"` rule — so a group that will not be drawn
cannot veto the chart type, and the type is never offered on a rule the renderer
does not follow.

`pie_suitability` and `pie_suggest` both route through it, so both are fixed by the
one change; their `n_categories` scoring is unchanged. Doughnut imports
`pie_suitability` directly (`charts/doughnut.py:17`), so it inherits the fix — the
one place doughnut genuinely is free.

### The native path needs a guard

The native builder is not merely un-split today; once these types accept a
classifier it becomes actively wrong. `series_chart_data`
(`native/column.py:28`) adds **every** segment as a chart series, and `build_pie`
colours `plots[0].series[0].points`. PowerPoint draws only the first series of a pie,
so a native export of a gender-split pie would render **the first group's
distribution as though it were the whole sample** — unlabelled, indistinguishable
from a correct slide, with the other groups sitting invisible in the file.

The web app only ever sends `render_mode: "image"` (`web/src/lib/api.ts:272`), so no
author can reach this today. That makes it cheap to prevent and easy to forget: the
native pie and doughnut builders take the `"Total"` segment explicitly rather than
whatever segment happens to be first, so a native export of a split pie shows the
honest overall distribution instead of an anonymous group.

This is not a new invention — `native/funnel.py:48` already reads
`series.cell(c, "Total")` by name and is safe as it stands. Pie and doughnut are the
two that guess.

### Panel titles

Group labels are survey labels and can be long ("Naiseksi itsensä identifioivat")
against a panel a third of the slot wide. They wrap at word boundaries the way
legend categories already do (`_wrap_legend_label`), never truncate — a clipped
group label on a slide that has already dropped groups is the wrong failure.

### Funnel is not free

Doughnut shares `_render_pie` and needs no separate work. Funnel does: its renderer
reads `data[segs[0]]` (`image/funnel.py:33`) and its `suitability` scores
`n_series != 1` down to 0.30, so it needs its own panel loop and its own
suitability fix. It is in scope, but it is a third of the rendering work, not a
free rider — and it is the least-used of the three, so it is the safest piece to
defer if the plan needs to be cut.

### Footer

**Corrected during implementation, 2026-08-22.** This section originally named
`add_filter_annotation` (`render/elements.py`) as the place the clause belongs. That
was wrong in the way that matters most: `deck.py:259-263` calls that function ONLY
under `render_mode == "native"`, and the web app sends image mode exclusively
(`web/src/lib/api.ts:272`). The disclosure would have rendered for nobody. Every unit
test against it would have passed while no real slide ever carried the line — the
feature's one safety net, shipped dead.

The footer an author actually sees is built by `add_image_slide_chrome`
(`render/image/slide_chrome.py`), which composes the `N = …` / statistic line. The
omitted-group clause is appended there, after the classifying variable's name. It is
ALSO added to `add_filter_annotation`, so the native path is not left lying about what
it drew — but the image path is the one that had to be right.

The lesson generalises past this feature: a disclosure has to be verified where the
reader will meet it. This one was caught by rendering a real slide through PowerPoint
and reading its footer, on a deck that had silently dropped four age groups. No
assertion about a function name would have found it.

`add_filter_annotation`'s own textbox is a fixed `Inches(3.0)` wide with no wrap
setting, sized for a single variable name. An omitted-group clause naming two labels
will not fit, so the box grows and wraps. Left alone, the one line whose job is to
disclose an omission would itself run off the slide — the failure mode this whole
section exists to prevent.

## Known limitations

The AI slide headline is computed from the **Total** column only
(`_findings_from_series`, `routes_ai.py:134` reads `cells[(cat, "Total")]`), and the
request body already carries `classifying_var` without using it for anything else.
A split pie therefore gets a headline describing the overall distribution — true,
but blind to the split the slide exists to show. Making the headline split-aware is
a separate change to the AI prompt and findings shape, and is not in this card.

## Testing

**Renderer** — N groups draw N pie axes; five groups draw the three largest;
display order follows the variable's group order, not base size; the legend is
emitted once; a slide with **no** classifier renders today's un-split layout byte
for byte, while a classifier yielding **one** drawable group renders a titled single
panel instead.

**Panel selection** — a group with base < 10 is dropped before the cap; a
**count**-statistic pie with a classifier draws no Total pie; all-groups-tiny
degrades to one whole-sample pie rather than to zero panels.

**Percent direction** — each panel's slice values are the engine's own
within-group percentages, unchanged by the renderer's renormalisation.

**Schema** — pie, doughnut and funnel expose `classifying_var` and expose neither
`classifying_var_2`, `xtab_layout` nor `show_total`.

**Feasibility** — a question that partitions overall but not within one drawn group
does not offer a pie once split by that variable; a failing group that is *not*
drawn (thin base, or capped out) does not veto it.

**Footer** — asserted against **`add_image_slide_chrome`**, the image-mode footer an
author actually sees, not only against the native-only `add_filter_annotation`: a
capped slide names its omitted groups; a slide that dropped a thin group says so, and
distinguishes the two reasons; an unaffected slide says neither. A chart type that does
NOT panel (any bar chart) never prints an omission clause — it draws every group, so
the clause there would be a false statement on a client slide.

**Native** — a native pie or doughnut with a classifier draws the overall
distribution, not the first group.

**Frontend** — the warning appears at four-plus groups and not at three, and
persists rather than dismissing itself; switching a classified bar chart to a pie
preserves the classifier.
