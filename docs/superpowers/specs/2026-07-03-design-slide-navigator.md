# Design-phase slide navigator

## Goal
Replace the Design phase's tall fixed 280px slide-list column with a compact **navigator** under
the phase banner, so reaching any slide (especially the tail of a 20-30 slide deck) is one keypress
or one search — not a scroll-hunt — and the reclaimed width goes to the preview.

## Current state (from code)
`StepConfigureInner` (`web/src/components/wizard/StepConfigure.tsx`) renders
`grid grid-cols-[280px_minmax(0,1fr)]`:
- LEFT (280px): "Slides (N)" — `charts.map` of every slide (number + question text + chart type),
  drag-to-reorder via `useDragReorder(onReorder)` (`{dragIndex, overIndex, containerRef, itemProps}`),
  click sets `active` (tracked by `question_ref`, not index). Also holds `addSpecialBar`.
- RIGHT (1fr): the `activeChart` header + large preview + config controls.
State/props available: `charts: ChartSpec[]`, `active`/`setActive`, `activeChart`, `activeIndex`,
`questionMap` (from `useRegroupedQuestions`), `onReorder(from,to)`, `onRemoveChart`, `onAddSpecial`,
`onUpdateChart`. Helpers: `chartTypeLabel`, `isSpecialSlide`, `rendersFullSlide`, `useChartPreview`.
UI primitives present: `dialog`, `input`, `scroll-area`, `sheet` (NO popover/command).

## Design

### File structure
The new components live in a NEW file `web/src/components/wizard/SlideNavigator.tsx` (StepConfigure
is already 1634 lines). It exports `SlideNavigator` and `SlideOverview`; `SlideThumb` and the jump
popover are internal. Everything they need is passed as PROPS (charts, activeIndex, questionMap,
materialId, grouping, onSelect, onReorder, onAddSlide) — they do NOT import StepConfigure's
`GroupingCtx`; grouping is passed explicitly so cache keys still match.

### Layout change (minimal, low-risk)
Drop the two-column grid. New vertical stack inside `StepConfigureInner`:
1. `<SlideNavigator/>` — the bar (full width).
2. The EXISTING `activeChart` work area (header + preview + controls) — unchanged internally, now
   full width so the preview is wider. (We do NOT restructure the preview/config internals — that
   keeps the diff small and the risk low; the width win comes for free from removing the column.)
3. `<SlideOverview/>` — a Dialog, mounted always, shown when `overviewOpen`.
`addSpecialBar` moves into the navigator as a compact **"+ Add slide"** button (opens the existing
special-slide dialog via `setSpecialDialogOpen`) AND appears atop the Overview grid.

### `SlideNavigator` (new component in the same file)
Props: `{ charts, activeIndex, questionMap, onSelect(i:number), onOpenOverview(), onAddSlide() }`.
Renders one row:
`[‹ Prev] [ pos · icon · "title" ▾ (jump trigger) ] [Next ›] [▦ Overview] [+ Add slide]`
- Prev disabled at index 0; Next disabled at last. Click → `onSelect(activeIndex∓1)`.
- Center shows `${activeIndex+1} / ${charts.length}`, the chart-type glyph, and the slide title
  (`isSpecialSlide(c) ? c.slide_title || chartTypeLabel(c.chart_type) : questionMap.get(c.question_ref)?.text ?? c.question_ref`), truncated. Clicking it toggles the jump popover.
- Empty deck (`charts.length === 0`): render nothing (the work area already guards on `activeChart`).

### Jump popover (inline, built by hand — no Popover primitive)
An absolutely-positioned panel under the center trigger: an `<input>` (autofocused) + a filtered,
scrollable list of ALL slides (number, chart-type glyph, title, chart-type label). Filter =
case-insensitive substring match over **title + chart-type label** (so "radar" narrows to radars).
Click a row → `onSelect(index)` + close. Closes on: outside click (document mousedown listener),
`Esc`, or select. Arrow-up/down within the popover move a highlighted row; `Enter` selects it.

### `SlideOverview` (Dialog, full-screen)
`<Dialog open={overviewOpen} onOpenChange={setOverviewOpen}>` with a wide `DialogContent`
(`w-[92vw] max-w-[92vw] h-[88vh]`). Body: a responsive thumbnail grid
(`grid-cols-2 sm:grid-cols-3 lg:grid-cols-4`) of `<SlideThumb/>`, each draggable via
`useDragReorder(onReorder)` (`itemProps(i)`, index-based — same hook the old list used). Clicking a
thumbnail → `onSelect(index)` + close. `Esc`/backdrop closes (Dialog default). Header carries the
"+ Add slide" action. The current slide's thumb is ringed (`active`).

### `SlideThumb` (new component — one per grid cell, so it may call hooks)
Props: `{ materialId, chart, index, isActive, grouping, questionMap, dragProps }`.
Renders: the slide number badge, a drag handle (`GripVerticalIcon`), the slide title, and a preview
image via `useChartPreview(materialId, chart, { renderTitle: rendersFullSlide(chart), grouping })`.
The `renderTitle` MUST equal `rendersFullSlide(chart)` — that is exactly what `DeckPrefetch` passes
(StepConfigure line 1288), so the thumb hits the SAME warmed cache instead of triggering a second
render. While the image is pending, fall back to the chart-type label. `overflow-hidden`, fixed
aspect. (priority is omitted — it doesn't affect the cache key.)

### Keyboard (← / →)
`useEffect` in `StepConfigureInner`: a `keydown` listener on `window`. On `ArrowLeft`/`ArrowRight`:
- IGNORE when the user is typing or in a menu: bail if `overviewOpen`, if the jump popover is open,
  or if `document.activeElement` matches `input, textarea, select, [contenteditable], [role="dialog"] *`.
- Else `preventDefault()` and `onSelect(clamp(activeIndex ∓ 1, 0, len-1))`.
Cleanup on unmount. (Left = previous, Right = next, per the decision.)

### Selection plumbing
`onSelect(i)` = `setActive(charts[i]?.question_ref ?? null)`. `activeIndex` derives from `active`
(existing). Reorder/remove keep working because `active` is a `question_ref`, not an index (existing
invariant). After `onAddSlide` creates a slide, select it (existing `onAddSpecial` returns its ref).

## Testing (no FE unit framework → build + Playwright)
- `npx tsc -b` + `npm run build` clean.
- Playwright on a report with ≥8 slides: (a) Next/Prev step the slide + update `pos`; (b) `→`/`←`
  keys do the same and are ignored while an input is focused; (c) click title → type a chart type
  ("radar") → list filters → pick → that slide shows; (d) ▦ Overview opens the full-screen grid,
  drag reorders, click jumps + closes; (e) "+ Add slide" still works. Screenshot each; LOOK.

## Edge cases
- **Special slides** in jump/overview: title via `slide_title || chartTypeLabel`; thumb uses glyph
  (no chart preview) since `rendersFullSlide` is true — or the full-slide PNG if cheap.
- **Single slide**: Prev+Next disabled; Overview shows one; jump still works.
- **Active becomes stale** after a remove: existing code re-points `active` to `charts[0]` when the
  active ref vanishes — keep that effect.
- **Jump filter matches nothing**: show "No slides match" row.
- **Grid drag on a 2-D grid**: `useDragReorder` is index-based so reorder still works; the drop
  affordance may be a simple target highlight rather than the list's drop-line — acceptable.

## Out of scope (this spec)
Bulk reorder in Select (already exists there); animated transitions; multi-select in Overview.
