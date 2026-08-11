# Follow-ups left open after the separate-classifier-panels work

Date: 2026-08-06
Context: `docs/superpowers/specs/2026-08-04-separate-classifier-panels-design.md`,
merged to master at `55982a1`.

These were found during implementation and review, judged non-blocking, and
deliberately not fixed. Recorded here so they are not lost with the scratch
ledger.

## Rendering

1. **Thin stacked segments crowd their own data labels.** `_draw_stacked_panel`
   in `render/image/bars.py` places a percentage label inside every segment
   regardless of its width, so a 2 % band's label collides with its neighbour's
   and with the row label — "Naiseksi**2 %6 %**". Affects the ordinary
   single-panel stacked bar identically; visible in the customer's screenshots
   from 2026-08-03, so it predates this work. Proved independent of margin
   sizing. Likely fix: drop or outdent a label below a width threshold, the way
   the clustered renderer already does with `_MIN_LABEL_BAR_PT`.

2. **A battery split by a classifier collides its bar labels.** The bars are
   `"<statement> · <segment>"`; with a dozen bars of long statement text the
   y-axis labels overlap into an unreadable stack. Pre-existing in the
   battery-crosstab feature (2026-08-02), surfaced because the config UI now
   offers a classifying variable on batteries.

3. **`_render_small_multiples` draws a phantom panel** for a fully
   base-filtered group — a titled, legended panel of 0 % bars — the same flaw
   fixed for the separate renderers (finding I4). Left alone because it is a
   crossed layout under a byte-identity constraint and its colours/legend are
   positional; needs a colour-index-preserving filter.

4. **`_render_variable_panels` and `_render_small_multiples` share ~40
   character-identical lines** (offset arithmetic, tick block, shared-axis
   label dance). The concrete cost is already paid: the same figure-height bug
   was found and fixed twice, once per renderer. Extract a
   `_draw_clustered_panel` sibling to the existing `_draw_stacked_panel`.

## Engine

5. **A saved battery chart with a banner primary and a stale
   `classifying_var_2` fails `compute()`** — 422 in preview, blank slide in an
   export — even though the battery paths ignore that value. Unchanged from
   before this work (master raised the same error from `_banner_masks`), and
   unreachable through any UI version, since a battery could never acquire a
   second classifier. Fix would be to ignore `classifying_var_2` for battery
   specs rather than raise.

## Partition correctness (found 2026-08-07/11, audit of the local store)

An audit computed `is_partition()` for all 697 saved partition-assuming charts.
55 came back non-partition, from **three unrelated causes** — the distinction
matters, because a strict gate would over-correct:

- 2 slides — genuine multi-response overlap (shares summing to 462 % and 800 %).
  This is the one that prints materially wrong numbers.
- 1 slide — two answer codes given the SAME display label via
  `category_label_overrides`, so the pie draws two identically-labelled slices
  and sums to 104 %. `case-erisan` / `rep-erisan` slide 19, `var39`. A label
  problem, not a data problem: overrides should refuse to collapse two codes
  into one label, or the engine should merge them.
- 52 slides — ordinary single-choice questions where 0.2–2 % of respondents sit
  outside the categories but inside the base, summing to 98–99.8 %. Distortion
  is 0.0–0.6pp, invisible at 0 decimals. These are fine. Any partition gate must
  keep offering pie for them.

9. **17 saved charts compute to ZERO categories** — a continuous variable with
   no value labels (age `ika`, segmentation score `qcl-2`) saved as a pie or a
   stacked bar. Nothing renders. Separate pre-existing defect; these questions
   should not be offered those chart types at all.

10. **Native export disagrees with image mode for stacked bars.**
    `render/native/bar.py:71` uses `BAR_STACKED`, not `BAR_STACKED_100`, so the
    same spec exports as a 465-long bar where the image renders a normalised
    one. Whichever way the normalisation question is settled, these two must
    agree.

12. **A true-width stacked bar is no longer a "100 % stacked bar", but the chart
    type's name and any slide title still say so.** Since 2026-08-11 the renderer
    draws true widths when the segments materially overshoot 100. The label in
    the picker should reflect that, or the type should be renamed to something
    that covers both cases.

13. **4 orphan reports** (`rep-125`, `rep-126`, `rep-130`, `rep-133`, 31 stacked
    charts between them) exist in `reports.json` with no `report_meta.json`
    entry, so they belong to no case and are unreachable in the product. Store
    debris; worth a cleanup pass.

14. **Native export transposes stacked bars relative to image mode.** Native
    stacks classifier segments within each category; the image builder stacks
    categories within segment bars. Orientation, not scaling — separate from the
    normalisation question, which is now settled.

11. **Nothing revalidates a saved `chart_type`.** `render/deck.py:176`
    dispatches straight off the stored id, the preview endpoint only guards
    scatter, and the config panel deliberately keeps the current type selectable
    ("don't trap the user"). So any offering-side gate leaves already-saved
    slides rendering exactly as before — renderer-side honesty is the only thing
    that reaches them.

## Config UI

6. **A stored `xtab_layout` value outside the current option list renders raw.**
   Restricting the stacked schemas to `auto`/`separate` means a chart saved with
   `"grouped"` shows the literal string `grouped` in the select until the author
   re-picks. Chart output is unaffected (both behave as `auto` there). One-line
   `items[value] ?? default` fallback in `SelectWidget`.

7. **`PercentBaseWidget` still offers "% within each …" on separate-mode
   charts**, which the engine overrides to the classifier direction — an inert
   control, the defect class this work set out to remove.

8. **The banner guard is asymmetric.** `usesBannerClassifier` inspects only
   `chart.classifying_var`, so a banner picked into the SECOND slot with an
   ordinary primary stays on a crossed layout and fails in
   `_combo_segmentation`. Pre-existing; the branch's story is "a banner works in
   either slot", so `withBannerGuard` should cover it.
