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

A single two-column **grid row**, `grid-cols-[300px_minmax(0,1fr)]`:

### Left column — slide list (navigation only)
- A relative wrapper holding an **absolutely-positioned scroll area**
  (`relative` cell → child `absolute inset-0 overflow-y-auto`). This is the crux of
  the equal-height requirement: the left cell contributes **no** intrinsic height, so
  the **right column sets the row height**, and the list fills that height and scrolls
  internally when there are more slides than fit. No JS measurement.
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
  360 px left panel to full width **under** the preview. Same components, same
  behavior (chart type, title/subtitle/footer, sort, classifying var, `percent_base`,
  number format, not-answered, category labels; special heading + markdown bullets +
  regenerate).
- The empty state ("No slides yet — go to Select…") stays.

### Removed from Design
- The `SlideNavigator` top bar (prev/next/jump/overview) — deleted.
- The `SlideOverview` **modal** usage — the grid moves to Preview (below).

## Preview page (renamed from Download)

- Rename the step **label** `"Download" → "Preview"` in `ReportWizard`'s `STEPS`
  (keep the step `id: "download"` to avoid churn, or rename to `"preview"` — implementer's
  choice; the label is what the user sees).
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

- **`SlideNavigator.tsx`:** delete `SlideNavigator` (the bar). **Extract the grid** —
  the thumbnail grid currently inside `SlideOverview` — into a reusable
  `SlideGrid` component (props: `charts`, `materialId`, `grouping`, `questionMap`,
  `activeRef`, `onSelect`) with **no `Dialog` wrapper**. Keep `slideTitle()` and
  `SlideThumb` (used by `SlideGrid`). `SlideOverview` (the modal) is removed.
- **`StepConfigure.tsx`:** new grid layout (left list + right preview/config); consume
  lifted `active`/`setActive`; drop the `SlideNavigator` + `SlideOverview` usage; add
  the ⓘ details button by the preview.
- **`StepDownload.tsx`:** add `<SlideGrid onSelect={(i) => { setActive(charts[i].ref); onGoToStep(configure) }} />` above the generate/download controls; receive
  `charts`, `active`/`setActive`, `onGoToStep`, `grouping`, `questionMap`.
- **`ReportWizard.tsx`:** lift `active`; relabel Download→Preview; wire the new props
  to `StepConfigure` and the Preview step.
- **Shared helper:** extract the deck-row subtitle logic (`KIND_LABELS`,
  `"<Chart Type>, <Question Type>"` / `"Bullets, Special"`) so the Select deck and the
  Design left list produce identical strings.

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
