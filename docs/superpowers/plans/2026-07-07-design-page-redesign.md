# Design-page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the report wizard's **Design** page into a slide-editor layout (left slide list + right preview/config) and move the all-slides grid to a renamed **Preview** step that also generates/downloads the deck.

**Architecture:** Pure frontend refactor in `web/src/components/wizard/`. Lift the active-slide state into `ReportWizard`; rebuild `StepConfigure` as a two-column CSS-grid (left list height-bound to the right column via an absolutely-positioned scroll area); extract the thumbnail grid into a reusable `SlideGrid`; host it inline on the Preview (ex-Download) step. No backend changes.

**Tech Stack:** React + TypeScript, Vite, TanStack Query, Tailwind. Verification: `tsc -b`, `npm run build`, and live testing by the user.

**Spec:** `docs/superpowers/specs/2026-07-07-design-page-redesign-design.md`

## Global Constraints
- No backend / render changes. Select page unchanged.
- Preview components (`ChartPreview`/`SpecialPreview`) render `renderTitle:true` (unchanged).
- Each task ends **buildable** (`tsc -b` clean) so the user can test live at any commit.
- Verification per task: `cd web && npx tsc -b` (expect `TSC=0`). Full `npm run build` at the end.

---

### Task 1: Shared slide-subtitle helper

Extract the deck-row subtitle logic (`"<Chart Type>, <Question Type>"` / `"Bullets, Special"`) so Select and the new Design list agree.

**Files:**
- Modify: `web/src/lib/charts.ts` (add `slideSubtitle`)
- Modify: `web/src/components/wizard/StepSelect.tsx` (use it; drop local `KIND_LABELS`)

**Interfaces:**
- Produces: `slideSubtitle(chart: ChartSpec, questionMap: Map<string, Question>): string`

- [ ] **Step 1:** In `lib/charts.ts`, add:
```ts
import type { Question } from "@/lib/api"; // if not already imported
const KIND_LABELS: Record<string, string> = {
  single: "Single", multi: "Multi", battery: "Battery", comparison: "Comparison",
};
/** Deck/list row subtitle: "<Chart Type>, <Question Type>", or "Bullets, Special". */
export function slideSubtitle(chart: ChartSpec, questionMap: Map<string, Question>): string {
  if (isSpecialSlide(chart)) return "Bullets, Special";
  const q = questionMap.get(chart.question_ref);
  const kind = q ? KIND_LABELS[q.kind] ?? q.kind : null;
  return kind ? `${chartTypeLabel(chart.chart_type)}, ${kind}` : chartTypeLabel(chart.chart_type);
}
```
(Reuse the existing `chartTypeLabel`/`isSpecialSlide` in that file; confirm they're defined there — if `chartTypeLabel` lives elsewhere, import it.)

- [ ] **Step 2:** In `StepSelect.tsx` `DeckList`, delete the local `KIND_LABELS` const and the inline `kindLabel`/`subtitle` computation; replace with `const subtitle = slideSubtitle(c, questionMap);` and import `slideSubtitle` from `@/lib/charts`.

- [ ] **Step 3:** `cd web && npx tsc -b` → `TSC=0`. Verify the Select deck subtitles still render (screenshot or live).

- [ ] **Step 4:** Commit: `feat(web): extract slideSubtitle helper shared by Select + Design`

---

### Task 2: Extract `SlideGrid` (grid inline), keep the modal working

Add a reusable `SlideGrid` that renders the thumbnail grid with no `Dialog`. Keep `SlideOverview` as a thin `Dialog` wrapper around it so `StepConfigure` keeps building until Task 4.

**Files:**
- Modify: `web/src/components/wizard/SlideNavigator.tsx`

**Interfaces:**
- Produces: `SlideGrid({ charts, materialId, grouping, questionMap, activeRef, onSelect }: { charts: ChartSpec[]; materialId: string; grouping?: Grouping; questionMap: Map<string,Question>; activeRef: string | null; onSelect: (index: number) => void })`

- [ ] **Step 1:** In `SlideNavigator.tsx`, extract the grid body currently inside `SlideOverview` into a new exported `SlideGrid` component (the `grid` of `SlideThumb`s + its scroll container), taking the props above. `SlideThumb` stays as-is.

- [ ] **Step 2:** Reduce `SlideOverview` to a `Dialog` that renders `<SlideGrid ... />` inside, preserving its current props/behavior (so `StepConfigure` is unchanged).

- [ ] **Step 3:** `cd web && npx tsc -b` → `TSC=0`.

- [ ] **Step 4:** Commit: `refactor(web): extract SlideGrid from SlideOverview (modal unchanged)`

---

### Task 3: Lift `active` state + `onGoToStep`; relabel Download→Preview

Move the active-slide source of truth to `ReportWizard`; thread it through props; rename the step label. `StepConfigure` starts consuming the lifted state but keeps its current layout (rewritten in Task 4).

**Files:**
- Modify: `web/src/components/wizard/ReportWizard.tsx`
- Modify: `web/src/components/wizard/StepConfigure.tsx` (accept `active`/`setActive` props; remove local `active` + its two effects)
- Modify: `web/src/components/wizard/StepDownload.tsx` (accept new props, unused until Task 5)

**Interfaces:**
- Produces (from `ReportWizard` to steps): `active: string | null`, `setActive: (ref: string | null) => void`, `onGoToStep: (index: number) => void`

- [ ] **Step 1:** In `ReportWizard`, add `const [active, setActive] = useState<string | null>(null);`. Add the two effects (using `draft.charts`): (a) if `active` && no chart matches → `setActive(draft.charts[0]?.question_ref ?? null)`; (b) if `!active` && `draft.charts.length` → `setActive(draft.charts[0].question_ref)`. Add `const goToStep = (i: number) => setStep(i)` (or reuse the existing setter name).

- [ ] **Step 2:** In `StepConfigure`, delete the local `const [active, setActive] = useState(...)` (line ~1269) and the two active-validity effects; take `active`, `setActive` from props. Keep `activeChart = charts.find(c => c.question_ref === active) ?? charts[0]` etc. Pass `active`/`setActive` down from the outer `StepConfigure` to `StepConfigureInner`.

- [ ] **Step 3:** In `ReportWizard`, pass `active`, `setActive` to `<StepConfigure>`; pass `active`, `setActive`, `onGoToStep` to `<StepDownload>` (add them to `StepDownload`'s props type; leave unused for now). Change the `download` step's `label` to `"Preview"` (keep `id: "download"`).

- [ ] **Step 4:** `cd web && npx tsc -b` → `TSC=0`. Live: Design still works (old layout), the step tab now reads "Preview".

- [ ] **Step 5:** Commit: `refactor(web): lift active-slide state to ReportWizard; rename Download→Preview`

---

### Task 4: Rebuild the Design layout (left list + right preview/config)

**Files:**
- Modify: `web/src/components/wizard/StepConfigure.tsx`

- [ ] **Step 1:** Replace the `StepConfigureInner` return layout. Remove `SlideNavigator`, `SlideOverview`, and the `overviewOpen` state/usage. New root:
```tsx
// Empty state unchanged when charts.length === 0.
<div className="grid grid-cols-[300px_minmax(0,1fr)] gap-4 items-stretch">
  {/* LEFT: height-bound scrollable slide list */}
  <div className="relative min-h-[24rem]">
    <div ref={listRef} className="absolute inset-0 overflow-y-auto pr-1 space-y-1.5">
      {charts.map((c, i) => {
        const isActive = c.question_ref === active;
        return (
          <button key={`${c.question_ref}-${i}`} ref={isActive ? activeRowRef : undefined}
            onClick={() => setActive(c.question_ref)}
            className={cn("w-full text-left flex items-center gap-2 rounded-lg border bg-card py-2 pr-2 pl-2 transition-colors",
              isActive ? "border-primary ring-1 ring-primary bg-primary/5" : "hover:border-primary/40")}>
            <span className="w-5 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{i + 1}</span>
            <span className="min-w-0 flex-1">
              <span className="line-clamp-1 text-sm">{slideTitle(c, questionMap)}</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">{slideSubtitle(c, questionMap)}</span>
            </span>
          </button>
        );
      })}
    </div>
  </div>
  {/* RIGHT: preview on top, config below */}
  <div className="space-y-4">
    <div className="relative">
      {/* existing ChartPreview / SpecialPreview / demographics preview for activeChart */}
      {/* details button: chart slides only */}
      {!activeSpecial && (
        <button onClick={() => setEditQid(activeChart.question_ref)}
          className="absolute right-2 top-2 z-20 flex size-8 items-center justify-center rounded-md bg-background/85 text-muted-foreground shadow-sm ring-1 ring-border hover:text-foreground">
          <InfoIcon className="size-4" />
        </button>
      )}
    </div>
    <div className="max-w-4xl">
      {/* existing ChartControls / SpecialSlideControls / demographics note for activeChart */}
    </div>
  </div>
</div>
```
Wire `listRef`/`activeRowRef` refs; keep the existing preview + controls components (move them into the right column). Reuse `slideTitle` + `slideSubtitle` + `cn`.

- [ ] **Step 2:** Add auto-scroll: `useEffect(() => { activeRowRef.current?.scrollIntoView({ block: "nearest" }); }, [active]);`

- [ ] **Step 3:** Simplify the `← / →` keyboard handler: drop the `overviewOpen` guard; keep the "typing in a field" guard; operate on lifted `active`.

- [ ] **Step 4:** `cd web && npx tsc -b` → `TSC=0`.

- [ ] **Step 5:** Commit: `feat(web): Design page — left slide list + right preview/config`

---

### Task 5: Preview step — inline grid + jump-to-Design

**Files:**
- Modify: `web/src/components/wizard/StepDownload.tsx`

- [ ] **Step 1:** In `StepDownload`, fetch `questionMap` via `useRegroupedQuestions(materialId, draft.grouping)` (mirror `StepConfigure`'s usage — build the `Map<string,Question>`). Import `SlideGrid`, `GroupingCtx` if needed.

- [ ] **Step 2:** Render above the generate/download controls:
```tsx
<SlideGrid charts={draft.charts} materialId={materialId} grouping={draft.grouping}
  questionMap={questionMap} activeRef={active}
  onSelect={(i) => { setActive(draft.charts[i].question_ref); onGoToStep(CONFIGURE_STEP_INDEX); }} />
```
`CONFIGURE_STEP_INDEX` = the index of the `configure` step (1). Use the same constant/lookup `ReportWizard` uses, or pass a ready `onGoToDesign` callback from `ReportWizard` instead of an index (preferred — pass `onGoToDesign: () => goToStep(configureIndex)`).

- [ ] **Step 3:** `cd web && npx tsc -b` → `TSC=0`.

- [ ] **Step 4:** Commit: `feat(web): Preview step shows all-slides grid; click jumps to Design`

---

### Task 6: Config 2-column layout at the wider width

**Files:**
- Modify: `web/src/components/wizard/StepConfigure.tsx` (`ConfigForm`)

- [ ] **Step 1:** Change `ConfigForm`'s container from `flex flex-col gap-4` to `grid grid-cols-2 gap-4` (its widgets already declare `col-span-2` for the full-width ones). Verify the header fields (chart type / slide title / subtitle / footer) still read well — keep title/subtitle textareas full-width (wrap them in `col-span-2` if they join the grid, or leave them stacked above `ConfigForm`).

- [ ] **Step 2:** `cd web && npx tsc -b` → `TSC=0`. Live: config fields sit two-across under the preview, complex widgets span full width.

- [ ] **Step 3:** Commit: `feat(web): 2-column config layout under the preview`

---

### Task 7: Cleanup — rename file, delete dead components

**Files:**
- Rename: `web/src/components/wizard/SlideNavigator.tsx` → `SlideGrid.tsx`
- Modify: imports in `StepConfigure.tsx`, `StepSelect.tsx`, `StepDownload.tsx`

- [ ] **Step 1:** Delete the now-unused `SlideNavigator` (bar) and `SlideOverview` (modal) components. Keep `SlideGrid`, `SlideThumb`, `slideTitle`.

- [ ] **Step 2:** `git mv SlideNavigator.tsx SlideGrid.tsx`; update all imports (`slideTitle`, `SlideGrid`) across `StepConfigure`, `StepSelect`, `StepDownload`.

- [ ] **Step 3:** `cd web && npx tsc -b` → `TSC=0`; then full `npm run build` → exit 0.

- [ ] **Step 4:** Commit: `refactor(web): rename SlideNavigator.tsx→SlideGrid.tsx; drop dead bar+modal`

---

## Self-Review
- **Spec coverage:** left list (T4), height-binding (T4 grid+absolute), subtitle (T1), preview+config right (T4), 2-col config (T6), ⓘ details chart-only (T4), Preview grid + jump (T5), rename step (T3), lift active (T3), SlideGrid extract + file rename (T2,T7), shared helper (T1). All covered.
- **Buildable checkpoints:** every task ends with `tsc -b` clean; T2 keeps the modal so T3–T4 stay green; dead code deleted only in T7 after all consumers migrated.
- **Type consistency:** `slideSubtitle`, `SlideGrid` prop shape, and `active/setActive/onGoToStep` signatures are defined once (T1/T2/T3) and reused verbatim in T4/T5.
