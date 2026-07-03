# Grouping workspace — UI rework (comparison groups + awareness)

## Why this rework
Two forces meet here:
1. **New capability** — a comparison (overlay several parallel questions as radar / grouped-bar
   series; the brand-image adjectives) is, we decided, a GROUPING act. It belongs in the group
   manager, not a chart-panel checklist.
2. **Existing weakness** — the current group manager has thin *awareness*. From the code map:
   no change log, no diff, no toast, no highlight, no report-impact signal; "Apply to report"
   just closes the dialog; battery suggestions live in StepSelect, *outside* the dialog. The user
   learns what changed only from a `manual`/`auto` badge and an auto-checked row afterwards.

The brief: the group manager must be **highly intuitive**, and the user must be **constantly aware
of what is being done and where the change lands**. Adding a second grouping tier to a UI that is
already weak on awareness forces us to fix awareness first, then fit comparison into it.

## What exists today (grounding — from the code map)
- One dialog, `ManageGroupingDialog` (85vh×85vw), opened only from wizard **StepSelect**.
- Two columns: LEFT "Groupable variables" (pool, kind badges `scale`/`tick`) → select ≥2 →
  "Group as multi" / "Group as battery"; RIGHT "Groups" (cards: title, member list, `multi`/
  `battery` badge, `manual`/`auto` badge, split/ungroup).
- Data: `GroupingOverride = { groups: GroupSpec[]; singles: string[] }`,
  `GroupSpec = { kind: "multi"|"battery"; variables: string[]; label? }`. Members are **variables**.
- Reshape preview via `POST /regroup` → `{ questions, battery_suggestions }`; the dialog derives
  its cards from the reshape of the *working* override (titles are the real backend titles).
- Grouping lives on the **report draft** (`draft.grouping`), saved with the report. (Confirmed
  earlier: grouping is report-level, not case-level.)

## The core model shift: TWO TIERS
- **Tier 1 — Combine variables → questions.** Today's multi/battery. Members are VARIABLES.
  Output: one question per group (a multi's options, or a battery's statements×scale).
- **Tier 2 — Compare questions → comparisons.** NEW. Members are QUESTIONS (multis/batteries/
  singles that share a category set). Output: one multi-series chart (radar or grouped bar).

Tier 2 sits *on top of* Tier 1: a comparison's members are the qids that Tier 1 produced. This
ordering is the central design constraint (data + UI): you compare things that already exist as
questions. The UI must make the two tiers legible without making the user think in "tiers".

## Design principles (ranked — awareness first)
1. **Always show current state.** A persistent structure view: what is grouped, into what, at
   both tiers. The user never has to remember or guess.
2. **Every edit is visible, named, and reversible.** A running change log ("Created battery
   *Palvelun laatu* from 5 variables"), each entry undoable, pending vs applied distinguished.
3. **Show where it lands and what it costs.** Each change names its effect on the report — count
   deltas ("18 questions → 12 slides"), highlight + auto-reveal of the affected card, and for a
   comparison, "4 questions → 1 slide".
4. **Reverse anything, both tiers.** Every grouping is undoable in place: split a comparison and
   its member questions return; split a question and its variables return. No preview lives here —
   the chart type is a Design-phase choice, so a thumbnail would presuppose a decision not yet made.
5. **Non-destructive, reversible session.** Live reshape preview before Apply; Apply commits;
   Cancel reverts the whole session; per-change undo in between.
6. **Guide, don't gate.** Suggest groupings (parallel-question + battery suggestions) inline;
   explain in a tooltip why an action is disabled; never silently drop.

## Information architecture
- Keep grouping **report-level, in the wizard**. Promote it from a cramped two-column dialog to a
  **full-height "Grouping workspace"** (still a modal/overlay over StepSelect, but laid out as a
  workspace). The richer model + awareness panels don't fit the current two columns.
- Entry point unchanged: the "Manage grouping" button in StepSelect opens it. Add a compact
  **grouping summary chip** on that button ("3 groups · 1 comparison") so state is visible without
  opening. Battery/parallel suggestions move *into* the workspace (they belong to grouping); a
  small count can still ride on the StepSelect button ("2 suggestions").

## Workspace layout (three zones)
```
┌───────────────────────────────────────────────────────────────────────┐
│ Grouping                         Report impact: 18 questions → 12 slides│  ← header + live impact
│                                              [ Cancel ]  [ Apply ]      │
├──────────────┬────────────────────────────────────────┬────────────────┤
│ STRUCTURE    │  WORKING AREA                           │  CHANGES        │
│ (live tree)  │  ◐ Questions   ○ Comparisons  ← segmented│  • Created …    │  ← 3 zones
│              │                                          │  • Split …      │
│ Variables 42 │  [pool / cards for the active stage]     │  (each undoable)│
│  ▸ Questions │                                          │  ───────────    │
│     Multi 3  │  Suggestions ▸ inline, dismissable       │  PREVIEW        │
│     Battery 2│                                          │  [thumbnail of  │
│  ▸ Compares 1│                                          │   selected grp] │
└──────────────┴────────────────────────────────────────┴────────────────┘
```

### Zone A — Structure (left rail, ALWAYS visible) — principle 1
A compact live tree of the current reshaped state:
- `Variables (n ungrouped)` → `Questions` → `Comparisons`, with per-node counts and kind chips.
- Selecting a node scrolls/reveals it in the working area and shows its preview.
- This is the single source of "what's grouped right now", visible at both tiers at all times.
- A node touched this session carries a subtle **changed** dot until Apply.

### Zone B — Working area (center) — the two tiers, one at a time
A **segmented control** switches the working stage (not tabs that hide state — the Structure rail
keeps global state visible; the segment only swaps the *editing surface*):

- **Questions (Tier 1)** — the existing flow, refined: variable pool (kind badges) → select ≥2 →
  "Combine as multi" / "Combine as battery"; question cards on the right with kind/source badges,
  member list, rename, and split. Battery **suggestions** render inline here as accept/dismiss rows.
- **Comparisons (Tier 2)** — a pool of QUESTIONS eligible to compare (multis/batteries/singles
  that share a category set), grouped by their shared category signature so the user sees "these 6
  adjectives share the same services". Select ≥2 → ONE action: "Compare". Comparison cards show
  members (the adjectives) and edit/**split** — but NO render toggle and NO preview: the chart
  type (radar vs grouped bar) is chosen later in the **Design phase**, like every chart. The
  Design chart-type picker is filtered for a comparison to just the applicable types — radar +
  grouped/clustered bars (via `_compatible_chart_types`; pie/scatter/line/etc. excluded).
  **Parallel-question suggestions** ("6 questions share the same options — compare them?") render
  inline, accept/dismiss, mirroring battery suggestions.

Copy names the act by effect: "Combine as multi", "Compare" — not "group". The chart type is a
Design-phase decision, so the group manager stays about STRUCTURE, never presentation.

### Zone C — Changes + Reverse (right rail) — principles 2 & 4
- **Changes** — a reverse-chronological list of this session's edits, each a plain sentence with an
  **Undo**. "Combined 5 variables into battery *Palvelun laatu*." / "Compared 6 questions —
  *Brändimielikuva*." / "Split *Ikäryhmä* back to a single question." Pending (unsaved) throughout
  the session; Apply commits them; Cancel discards all.
- **Reverse** — a persistent reminder that both tiers unwind here: comparison → questions →
  variables, each a **Split** on the card. No chart preview (chart type is chosen in Design).

### Where-it-lands feedback — principle 3 (woven across zones)
On any create/split: (a) the new/affected card gets a brief highlight + is auto-revealed in both
the working area and the Structure tree; (b) the header **Report impact** counter animates its
delta; (c) a Changes entry is prepended; (d) on Apply, StepSelect scrolls to and highlights the
resulting question(s), replacing today's silent auto-check.

## The comparison flow (Tier 2) in detail
1. **Eligibility.** A question is comparison-eligible when it shares an exact category label-set
   with ≥1 other question (multi option-set or battery attribute-set) — the `_parallel_questions`
   rule from Phase 1. The pool groups eligible questions under their shared signature.
2. **Suggest.** The workspace surfaces parallel sets as suggestions ("6 questions share options
   *IS, IL, HS, Yle, MTV, Ei mikään* — compare them?") with Compare / Dismiss. Accept → pre-fills a
   comparison with all members (auto-detect as a *suggestion*, then editable — this is the escape
   hatch the Phase-1-only design lacked).
3. **Create / edit.** Select members (or accept a suggestion) → choose render (radar default;
   grouped bars alternative). The comparison card lists members (adjective labels via the common-
   strip `_series_label`), shows the render toggle + preview, and supports add/remove member and
   split. Removing all-but-one collapses it back to a single-question chart (escape hatch).
4. **Result.** One reshaped comparison "question" (qid `compare-<slug>`); a chart on it renders the
   overlay. In the report it is one slide; the Report-impact counter reflects the collapse.

## Data model changes
Extend the override with a Tier-2 list; Tier-1 unchanged:
```ts
interface ComparisonSpec {
  members: string[];                 // QIDS (Tier-1 outputs), ≥2
  label?: string | null;             // optional title; else derived stem
}   // NO render — chart type (radar / grouped bar) is a Design-phase choice on the ChartSpec
interface GroupingOverride {
  groups: GroupSpec[];               // Tier 1 (unchanged) — variable members
  singles: string[];                 // unchanged
  comparisons?: ComparisonSpec[];    // Tier 2 — question members
}
```
- **Resolution order** (backend `apply_grouping_override`): Tier 1 first (produces qids), then
  resolve `comparisons` against those qids; a comparison whose members no longer exist (a member
  was regrouped/split) is dropped leniently (mirrors today's invalid-group handling) and reported.
- **Qid stability** is now load-bearing: comparison members reference Tier-1 qids, so multi/battery
  qids must stay stable across edits (battery qid already is a slug; verify multi qids are stable).
- `/regroup` returns, additionally, `parallel_suggestions` (sets of qids sharing a category set)
  alongside `battery_suggestions`, and the reshaped comparison questions.
- Serde: `comparisons` round-trips on `ReportDoc.grouping`. A comparison chart's `series_refs`
  (spec Part B) is derived from the comparison's members, so chart-level config stays thin.

## Interaction flows (happy paths)
- **Combine a battery:** accept a battery suggestion (or select ≥2 shared-scale vars) → card
  appears highlighted, Changes logs it, impact counter drops → Apply → StepSelect reveals the
  battery question.
- **Create a comparison:** switch to Comparisons → accept "6 adjectives share options" suggestion →
  radar preview appears in the right rail → optionally toggle to grouped bars, drop one adjective →
  Apply → one comparison slide.
- **Undo:** click Undo on a Changes entry → the reshape reverts, Structure + impact update, entry
  removed. **Cancel:** discard the whole session. **Apply:** commit `groups`+`singles`+`comparisons`.

## States & edge cases
- **Empty:** no ungrouped variables / no eligible comparisons → explain, don't blank ("Every
  variable is already in a question." / "No questions share a category set yet — combine variables
  first.").
- **Incompatible selection:** mixed kinds or non-shared category set → the Compare action is
  disabled with a tooltip naming the reason.
- **Many parallel questions:** a suggestion of 12 adjectives → the comparison pre-fills all but the
  preview + member list make trimming obvious; consider a soft "that's a lot of polygons" hint.
- **Cross-tier conflict:** splitting a Tier-1 question that a comparison uses → warn ("*Rohkea* is
  in comparison *Brändimielikuva* — splitting it removes it from that comparison") and update both.
- **Collisions / dup labels:** disambiguate series labels (`Rohkea (2)`), as Phase 1 already does.

## Microcopy (active voice, effect-named)
Buttons: "Combine as multi", "Combine as battery", "Compare", "Split", "Undo", "Apply", "Cancel".
Toast-style status: on Apply → "Grouping applied · 12 slides".
Suggestions: "6 questions share the same options — compare them?" Errors explain + fix.

## Phasing
- **P1 (done):** engine auto-detect radar (parallel multis).
- **P2a — data + awareness spine:** `comparisons` in the override + backend resolution +
  `parallel_suggestions`; the Changes log, Structure rail, and Report-impact counter (awareness
  works even before the comparison UI is rich).
- **P2b — comparison working stage:** the Comparisons segment (pool, suggestions, create/edit,
  render toggle, preview) + the question-multiselect interactions.
- **P2c — polish:** where-it-lands highlights/auto-reveal, StepSelect reveal-on-apply, grouping
  summary chip on the button, grouped-bar rendering of comparisons.

## Open items / risks
- **Modal vs. full page:** the workspace may outgrow a modal; if so, a dedicated route is cleaner.
  Decide when P2b lands.
- **Two-tier overwhelm:** the segmented control + always-on Structure rail is the mitigation;
  validate with the customer that "Questions vs Comparisons" reads naturally (Finnish labels TBD
  with the customer — likely "Kysymykset" / "Vertailut").
- **Preview cost:** live thumbnails reuse the (LibreOffice-free) PNG preview; ensure they're cheap
  and cached (the preview cache already keys on grouping).
