# Comparison Grouping — P2b Workspace UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. No unit-test
> framework on the frontend (only Playwright), so each task is verified by `npx tsc -b` +
> `npm run build` + driving the dialog with Playwright and LOOKING at the screenshot.

**Goal:** Turn the two-column Manage-grouping dialog into the workspace from the mockup — a
Comparisons stage (create/split comparisons of parallel questions) plus the awareness affordances
(Structure rail, Changes log + undo, Report-impact counter).

**Architecture:** Extend `ManageGroupingDialog` in place. Add `comparisons` to the working state,
thread it through `useRegroupedQuestions` (regroup already accepts it, P2a), and add
`useParallelSuggestions` (same query key as regroup, selects `parallel_suggestions`). A segmented
control swaps the Questions stage (existing) and the new Comparisons stage; a left Structure rail
and a right Changes rail wrap both. Chart type is NOT chosen here (P2a: Design-phase, filtered).

**Tech Stack:** React, TypeScript, @tanstack/react-query, shadcn/ui, lucide-react, Playwright.

## Global Constraints
- No `render` in comparisons — chart type is a Design-phase choice.
- One "Compare" action; comparison cards support Split; fully reversible both tiers.
- Verify with `tsc` + `build` + Playwright (backend on :8200 NSIGHT_DEMO, vite on :5173).
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

## File Structure
- `web/src/lib/queries.ts` — add `useParallelSuggestions`; ensure `useRegroupedQuestions` passes
  `comparisons` (it forwards the whole grouping object, so just include the field).
- `web/src/components/ManageGroupingDialog.tsx` — the workspace: comparisons state, segmented
  control, Comparisons stage, Structure rail, Changes rail, Report-impact. (Largest change.)
- Verification only: Playwright drives `http://localhost:5173`.

---

### Task 1: Data plumbing — comparisons through regroup + a suggestions hook

**Files:**
- Modify: `web/src/lib/queries.ts` — `useParallelSuggestions` (mirror `useBatterySuggestions`).
- Modify: `web/src/components/ManageGroupingDialog.tsx` — `comparisons` state; pass it into
  `useRegroupedQuestions({ groups, singles, comparisons })`.

**Interfaces:**
- Produces: `useParallelSuggestions(materialId, grouping) -> ParallelSuggestion[]`.
- Produces: dialog working state gains `comparisons: ComparisonSpec[]` (seeded from
  `grouping.comparisons`), passed to the reshape so comparison questions appear in `workingReshaped`.

- [ ] **Step 1: Add the hook** (after `useBatterySuggestions` in queries.ts):
```ts
export function useParallelSuggestions(
  materialId: string | null,
  grouping: GroupingOverride
) {
  return useQuery({
    queryKey: ["regrouped-questions", materialId ?? "", JSON.stringify(grouping)],
    queryFn: () => api.materials.regroup(materialId!, grouping),
    enabled: !!materialId,
    select: (d) => d.parallel_suggestions ?? [],
  });
}
```
Also widen `api.materials.regroup`'s return type (in `api.ts`) to include
`parallel_suggestions?: ParallelSuggestion[]` and import `ParallelSuggestion`.

- [ ] **Step 2: Seed + thread comparisons in the dialog.**
Add state `const [comparisons, setComparisons] = useState<ComparisonSpec[]>([]);`, seed it in the
open-effect (`setComparisons((grouping.comparisons ?? []).map((c) => ({ ...c })));`), pass
`{ groups, singles, comparisons }` to `useRegroupedQuestions`, and include `comparisons` in the
`onSave` payload. Import `ComparisonSpec`, `ParallelSuggestion`.

- [ ] **Step 3: Verify** — `cd web && npx tsc -b` (exit 0) + `npm run build`. Existing dialog
still works (comparisons empty by default). Commit.

---

### Task 2: Comparisons stage — suggestions, pool, Compare, cards, Split

**Files:**
- Modify: `web/src/components/ManageGroupingDialog.tsx`.

**Interfaces:**
- Consumes: `workingReshaped` (has `kind==="comparison"` questions now), `useParallelSuggestions`.
- Produces: a `stage` state (`"questions" | "comparisons"`) + a segmented control; the Comparisons
  stage UI.

- [ ] **Step 1: Segmented control** — add `const [stage, setStage] = useState<"questions"|"comparisons">("questions");`
and a two-button segmented control in the header row; the existing two-column grid renders when
`stage==="questions"`.

- [ ] **Step 2: Comparison-eligible pool** — derive from `workingReshaped`: questions whose
`(kind, sorted member-category labels)` signature is shared by ≥2 questions. Group the pool under
each signature. (The backend `parallel_suggestions` gives the same sets — use it directly for the
suggestion banners; derive the pool from `workingReshaped` so manual picks beyond suggestions work.)
Reuse a `catSig(q)` helper: questions of kind multi/battery keyed by `q.variables`→labels set.

- [ ] **Step 3: Comparison cards + create/split.**
```ts
function compare(qids: string[]) {
  if (qids.length < 2) return;
  setComparisons((cs) => [...cs, { members: qids, label: null }]);
}
function splitComparison(members: string[]) {
  setComparisons((cs) => cs.filter((c) => setKey(c.members) !== setKey(members)));
}
```
Comparison cards = `workingReshaped.filter(q => q.kind==="comparison")` — show title, member count,
a member list, and a Split (Undo2Icon) button → `splitComparison(q.members)`. (`Question` type must
expose `members`; add `members?: string[]` to the TS `Question` type in api.ts if absent.)

- [ ] **Step 4: Suggestion banners** — for each `useParallelSuggestions` entry not already a
comparison, a row: "N questions share the same options — compare them?" + labels + a **Compare**
button (`compare(suggestion.qids)`) + Dismiss.

- [ ] **Step 5: Verify with Playwright** — start backend+vite, open a report with parallel multis
(or seed one), open Manage grouping, switch to Comparisons, accept a suggestion, screenshot, LOOK:
a comparison card appears; Split removes it. Commit.

---

### Task 3: Awareness — Report impact, Changes log, Structure rail

**Files:**
- Modify: `web/src/components/ManageGroupingDialog.tsx`.

- [ ] **Step 1: Report-impact counter** (header) — questions-in vs questions-after. Baseline =
reshape of the SEEDED grouping (an extra `useRegroupedQuestions` on the seeded override) count;
current = `workingReshaped.length`. Render "N questions → M items" with the delta.

- [ ] **Step 2: Changes log (right rail)** — an explicit session log: push an entry on each
mutating action (`groupSelected`, `ungroup`, `compare`, `splitComparison`) with a plain sentence
and an `undo` closure that reverts that specific state change. Pending until Apply. Render newest
first with an Undo button.
```ts
type Change = { id: number; text: string; undo: () => void };
const [changes, setChanges] = useState<Change[]>([]);
const logChange = (text: string, undo: () => void) =>
  setChanges((c) => [{ id: c.length, text, undo }, ...c]);
```
Wire each action to `logChange` (e.g. compare → "Compared N questions.").

- [ ] **Step 3: Structure rail (left)** — a compact tree derived from `workingReshaped`: counts of
Questions (multi/battery) and Comparisons, with kind chips. A node touched this session gets a dot.

- [ ] **Step 4: Layout** — restructure the dialog body to the three zones (Structure | stage |
Changes) with the segmented control in the header, as in the mockup. Keep `h-[85vh] w-[85vw]`.

- [ ] **Step 5: Verify with Playwright** — screenshot the workspace: create a comparison → Changes
logs it, impact counter updates, Structure shows the comparison; Undo reverts. LOOK. Commit.

---

### Task 4: Copy, empty states, polish
- [ ] Microcopy per spec ("Combine as multi/battery", "Compare", "Split", "Apply"), empty states
("No questions share a category set yet — combine variables first."), disabled-Compare tooltip
(reason). Verify + commit.

## Self-Review
- Spec coverage: segmented tiers, Comparisons stage, suggestions, Structure rail, Changes+undo,
  Report-impact, reversible Split, no render/preview → Tasks 1-4. Where-it-lands highlight +
  StepConfigure chart-type-filter wiring are P2c (separate).
- Placeholder scan: Task 2 Step 2 references `catSig`/signature derivation — the exact `Question`
  shape (does it expose `members`, `variables`) is confirmed at implementation time; add
  `members?: string[]` to the TS `Question` type if missing (noted in Task 2 Step 3).
- Risk: this is a large single-file component; if it grows unwieldy, extract the Comparisons stage
  and the Changes rail into sibling components under `components/grouping/`.
