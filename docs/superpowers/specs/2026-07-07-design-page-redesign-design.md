# Design-page redesign — spec

## Goal

Rework the report wizard's **Design** page into a slide-editor layout: a persistent
scrollable slide list on the left, and the slide's preview + configuration stacked on
the right. Move the "all slides" grid to the (renamed) **Preview** step, which also
hosts deck generation/download.

**Select stays as-is. No backend changes.**

## Current state (what we're changing)

The wizard (`web/src/components/wizard/`) has three steps in `ReportWizard.tsx`:
`select` ("Select"), `configure` ("Design"), `download` ("Download").

- **`StepConfigure.tsx` (Design):** a compact top `SlideNavigator` bar (prev/next,
  jump-to search, details ⓘ, Overview-grid button) over a two-column grid
  `grid-cols-[360px_minmax(0,1fr)]` — **config panel on the left (360 px)**, **preview
  on the right**. The active slide is tracked by local state `active`
  (`question_ref`) inside `StepConfigureInner`. Opens the `SlideOverview` grid as a
  **modal** and `QuestionDetailsDialog` for details.
- **`SlideNavigator.tsx`:** exports `SlideNavigator` (the top bar) and `SlideOverview`
  (the full-deck thumbnail grid, a `Dialog`), plus `slideTitle()`.
- **`StepDownload.tsx` (Download):** `handleGenerate` (render → preview PDF) and
  `handleDownload("pdf"|"pptx")`. No slide grid.
- Preview components (`ChartPreview` / `SpecialPreview`) render the **full baked 16:9
  slide** (`renderTitle:true`) — unchanged. Config forms (`ChartControls` /
  `SpecialSlideControls`) — unchanged.

## New Design page layout (`StepConfigure`)

A single-row **CSS grid**: `grid grid-cols-[300px_minmax(0,1fr)] gap-4`
(one implicit `auto` row, default `align-items: stretch`). The row's height is set by
the taller cell's *in-flow* content — which will be the right column, because the left
cell's list is taken out of flow (see below).

### Left column — slide list (navigation only)
- The left grid cell is `relative`; the list inside is an **absolutely-positioned
  scroll area** (`absolute inset-0 overflow-y-auto`). Because the list is out of flow,
  the left cell has **~0 in-flow content height**, so it never grows the row — the
  **right column (preview + config) sets the row height**, `align-items: stretch`
  stretches the left cell to that height, and the absolute list fills it and scrolls
  internally when there are more slides than fit. No JS measurement.
- Page-scroll model: the row's height *is* the natural height of preview + config, so
  when that exceeds the viewport the **page** scrolls; the left list scrolls
  **independently** within the row. (This matches the requested "list height = preview
  + configuration height" — the list is bound to that height, not the viewport.)
- A small `min-height` floor on the left cell (e.g. `min-h-[24rem]`) keeps the list
  usable when a slide's config is unusually short (special "no options" slide).
- Rows are **compact text rows** reusing the Select deck-row visual: slide number +
  `slideTitle()` + a subtitle `"<Chart Type>, <Question Type>"` (e.g. "Pie Chart,
  Battery") for question slides, `"Bullets, Special"` for special slides. (Reuse the
  `KIND_LABELS` + `chartTypeLabel` logic already in `StepSelect.tsx`; extract a shared
  helper so both places agree.)
- The **active** row is highlighted (border/ring + tint). Clicking a row sets it
  active. `← / →` keys still step through slides (existing handler, now driven by the
  lifted `active`). On active change, the active row **auto-scrolls into view**
  (`scrollIntoView({ block: "nearest" })`).
- **Navigation only** — no reorder/remove/add here (that stays in Select).

### Right column — preview (top) + configuration (below)
- **Preview on top:** the existing `ChartPreview` / `SpecialPreview`, unchanged
  (WYSIWYG baked 16:9 slide, `SLIDE_ASPECT`), full width of the column.
- A small **ⓘ details** button in the preview's top-right corner. For a **chart**
  slide it opens `QuestionDetailsDialog` (read-only, as today via `editQid`); it is
  **hidden for special slides** (they're edited inline below — matches today's
  `onEditQuestion && !isSpecialSlide` gate).
- **Configuration below the preview:** the existing `ChartControls` (chart slides) /
  `SpecialSlideControls` (special slides) / demographics-grid note, moved from the old
  360 px left panel to **under** the preview. Same components, same behavior (chart
  type, title/subtitle/footer, sort, classifying var, `percent_base`, number format,
  not-answered, category labels; special heading + markdown bullets + regenerate).
- **Config layout at the wider width:** the config is now much wider than the old
  360 px panel, so a single column would look sparse. Render the config fields in a
  **2-column grid** and constrain the block to a readable `max-w-4xl` (left-aligned
  under the preview). `ConfigForm` already ships the hint for this — its widgets
  declare `col-span-2` (NumberFormat, Not-answered, Category-labels) even though the
  container is currently `flex flex-col` — so switch `ConfigForm` to
  `grid grid-cols-2 gap-4` (those widgets span both columns; simple select/switch
  fields sit two-across). `ChartControls`' header fields (chart type / slide title /
  subtitle / footer) may either join that grid or stay stacked full-width above it —
  implementer's call, but the title/subtitle textareas should be full-width.
- The empty state ("No slides yet — go to Select…") stays.

### Removed from Design
- The `SlideNavigator` top bar (prev/next/jump/overview) — deleted.
- The `SlideOverview` **modal** usage — the grid moves to Preview (below).

## Preview page (renamed from Download)

- Rename the step **label** `"Download" → "Preview"` in `ReportWizard`'s `STEPS`.
  **Keep the step `id: "download"`** (and the `configure` id) unchanged — only the
  user-visible label changes — so existing id/index references (step gating,
  `onGoToStep`) keep working with no churn.
- The page shows, top to bottom:
  1. The **all-slides grid** — the current `SlideOverview` thumbnail grid, rendered
     **inline** (a normal section, not a `Dialog`). Clicking a slide **sets it active
     and navigates to the Design step** to edit it.
  2. The existing **Generate deck / Download (PDF · PPTX)** controls from
     `StepDownload` (unchanged behavior).

## Shared plumbing (`ReportWizard`)

- **Lift** the `active` slide state (`question_ref` string | null) + `setActive` out
  of `StepConfigureInner` up into `ReportWizard` (the single source of truth). Pass
  both to `StepConfigure` and to the Preview step. **Move** the two effects that
  currently keep `active` sane into `ReportWizard` (which already owns `draft.charts`):
  (a) if `active` no longer matches any chart, default to the first slide's
  `question_ref`; (b) initialise `active` to the first slide when it's null and charts
  exist. The `← / →` keyboard handler stays in `StepConfigure` (it's Design-only) and
  reads/sets the lifted `active`.
- Pass a **step-navigation callback** (e.g. `onGoToStep(index)` reusing the existing
  `setStep`) so the Preview grid's click can switch to the Design step.

## Component changes summary

- **`SlideNavigator.tsx` → rename to `SlideGrid.tsx`:** with the bar gone the filename
  is misleading. Delete the `SlideNavigator` (bar) component and the `SlideOverview`
  (modal) wrapper. **Extract the thumbnail grid** (currently inside `SlideOverview`)
  into a reusable `SlideGrid` component — props `charts`, `materialId`, `grouping`,
  `questionMap`, `activeRef`, `onSelect(index)`; **no `Dialog`**. Keep `slideTitle()`
  and `SlideThumb` here (both used by `SlideGrid`, and `slideTitle` by the Design left
  list). Update all imports (`slideTitle` is imported by `StepConfigure` and
  `StepSelect`).
- **`StepConfigure.tsx`:** new grid layout (left list + right preview/config); consume
  lifted `active`/`setActive` (delete the local `active` state and the two
  active-validity effects — they move to `ReportWizard`); drop `SlideNavigator` +
  `SlideOverview` + `overviewOpen` state; simplify the `← / →` handler to drop its now
  dead `overviewOpen` guard (keep the "ignore while typing in a field" guard); add the
  ⓘ details button by the preview.
- **`StepDownload.tsx` (the Preview step):** fetch its own
  `questionMap` via `useRegroupedQuestions(materialId, draft.grouping)` (same as
  `StepConfigure` — do **not** lift `questionMap`). Render `<SlideGrid charts={draft.charts} activeRef={active} onSelect={(i) => { setActive(draft.charts[i].question_ref); onGoToStep(CONFIGURE) }} … />` above the existing generate/download controls. New
  props it receives from `ReportWizard`: `active`, `setActive`, `onGoToStep`.
- **`ReportWizard.tsx`:** lift `active` + `setActive`; add the two active-validity
  effects here (they need `draft.charts`); relabel the `download` step's `label`
  `"Download" → "Preview"`; pass `onGoToStep` (a thin wrapper over the existing step
  setter) and `active`/`setActive` to both `StepConfigure` and the Preview step.
- **Shared helper:** extract the deck-row subtitle logic (`KIND_LABELS`,
  `"<Chart Type>, <Question Type>"` / `"Bullets, Special"`) out of `StepSelect`'s
  `DeckList` into a shared function (e.g. in `lib/charts.ts`) so the Select deck and
  the Design left list produce identical strings.

## Edge cases & notes
- **Empty deck:** when `draft.charts.length === 0`, Design shows the existing empty
  state ("No slides yet — go to Select…"), not the two-column grid. The Preview grid
  shows its own empty state.
- **`activeChart` derivation:** `StepConfigure` still derives the shown slide as
  `charts.find(c => c.question_ref === active) ?? charts[0]` (unchanged), so a
  transiently-null or stale `active` never renders a blank right column.
- **Preview-grid warmth:** `SlideGrid` thumbnails use the same content-keyed
  `useChartPreview` cache as Design. They're warm if the user has visited Design first
  (its `DeckPrefetch` warms `renderTitle:true`); otherwise they render on-demand and
  cache. Optionally move `DeckPrefetch` up to `ReportWizard` so both steps stay warm —
  not required for this change.
- **Step navigation for the Preview→Design jump** uses the existing step setter (all
  steps are already reachable; only the final step gates on "at least one chart").

## Out of scope
- Select page and its deck (unchanged).
- Any backend / render changes.
- Reorder / remove / add on the Design page (structure stays in Select).
- Merging steps into a single page (explicitly dropped earlier).

## Testing / verification
- `tsc -b` clean; `oxlint` clean on changed files; `vite build` succeeds.
- Manual (Playwright, local dev): open a report on the Design step → left list shows
  all slides with correct subtitles, active highlighted; clicking a row updates the
  right preview + config; `← / →` step and auto-scroll the list; the left list's
  height matches the right column and scrolls internally for a long deck; ⓘ opens
  details for a chart slide and is absent for a special slide. On **Preview**: the grid
  shows all slides; clicking one lands on Design with that slide active; Generate /
  Download still work.
