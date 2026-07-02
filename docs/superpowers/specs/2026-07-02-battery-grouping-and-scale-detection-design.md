# Battery grouping + robust scale detection — design

## Goal
Let users create the **stacked multi-variable comparison** chart (a battery: each
statement a 100%-stacked bar split by a shared rating scale — the DNA/"tärkeys"
example) from several similar rating variables. Customer: "En keksi miten saan
tehtyä sellaisen sliden jossa on usean samankaltaisen muuttujan pylväät pinottuna
samaan kuvaan."

## Root cause (three gaps, verified in code)
1. **Auto-battery needs a `:` label pattern.** `battery_group._cells` only finds
   batteries whose labels are `category:subject:question`. Plain statement labels
   ("voin tunnistautua verkossa…") are never grouped → shown as N singles.
2. **No manual battery grouping.** The grouping dialog only makes `multi` groups;
   `apply_grouping_override` explicitly SKIPS `kind: "battery"` (Phase 2 deferred).
3. **Scale parsed from a leading digit.** `_rating_scale` maps code→point via the
   leading integer of each value label ("5 - Erittäin tärkeä"→5). Word-only labels
   ("Erittäin tärkeä", coded 1..5) yield `{}` → the stack can't build.

Decision (customer): do **both** auto-detection AND manual grouping, robust either way.

## Findings that shape the design (verified)
- Battery members carry **no common label prefix** (each label is a *different*
  statement) and **no meaningful common variable-name prefix** (e.g. `var39`,`var40`).
  → An auto-detector CANNOT rely on a common stem; the only honest signals are
  **contiguous SAV position + identical scale signature**, which **over-groups** any
  run of same-scale questions. So auto-detection is inherently unreliable here and must
  be **conservative + user-confirmable**, with manual grouping as the reliable path.
- `_rating_scale` is shared by `_single` (line 390, `is_rating`), `_combo_two_var`
  (598) and the battery paths. → We must **not mutate `_rating_scale`** (it would leak
  code-as-scale into standalone categoricals and misread a nominal 1/2/3 as a scale).
  Add a **new** function used only where a scale is already asserted (battery context).

## Design

### Part A — robust scale detection (`stats/engine.py`)  [foundation, low-risk]
Add `scale_levels(var) -> list[(code, label, point)]` — do NOT change `_rating_scale`:
- If every non-missing **value label** has a leading integer → use those points (same
  as today; keeps out-of-order SAV codes correct).
- Else, if the non-missing **value-label codes** (the DEFINED points, not data) are
  contiguous integers with `3 ≤ N ≤ 11` → treat the codes as the points (1..N), keeping
  the word labels. → a word-labelled importance 1..5 becomes a real scale.
- Else `[]`.
- **Used ONLY by the battery paths** (`_battery_stacked`, `_battery`) and by manual/auto
  battery validation — never by `_single`/`_combo`, so a standalone nominal categorical
  is untouched (no false "scale"). Digit-labelled batteries render identically to today.

### Part C — manual "Group as battery" (Phase 1, reliable)  [primary deliverable]
The deterministic path the user drives; unblocks the customer regardless of auto-detect.
- **`ingest/grouping_override.py`:** apply `kind: "battery"` manual groups. Validity:
  ≥2 known members that each yield a non-empty `scale_levels` AND **share the same scale
  signature** (identical non-missing code→label map); else skip (lenient, like multi).
  Build the battery question **directly** — `Question(qid=f"battery-{slug(label|members)}",
  kind="battery", variables=tuple(members), text=label)` — NOT via `apply_batteries`
  (which expects the `:`-cell structure). Add battery members to `blocked` so auto multi/
  battery detection skips them; drop them from `singles`.
- **`model.report` / plugins:** a `battery` question already suggests
  `stacked_horizontal_bar` (existing routing) — no change; verify.
- **`api/routes_questions.py`:** `/variables` exposes a `scale: bool` marker (via
  `scale_levels`) so the dialog can offer scale variables. `regroup` is already lenient
  (it just builds the override and calls `apply_grouping_override`), so ALL battery
  handling lands in `apply_grouping_override` — no endpoint validation to change. The
  `GroupSpec` body already carries a `kind` field; the browse payload already emits
  battery questions.
- **Web `ManageGroupingDialog`:** the pool shows BOTH tick-box AND scale variables, each
  tagged with its type. Two group actions: **"Group as multi"** (enabled for a tick-box
  selection, as today) and **"Group as battery"** (enabled when ≥2 selected are scale
  vars sharing a scale). Battery groups appear as cards (kind badge "Battery"),
  splittable. Report-scoped, mirrors the shipped multi-grouping. Emits
  `{kind: "battery", variables, label}` into `report.grouping.groups`.

### Part B — auto-battery detection (Phase 2, convenience, heuristic)
Since there's no reliable stem, do NOT silently create batteries from "contiguous +
same-scale". Instead **SUGGEST**: when a run of **≥3 contiguous, currently-single,
same-scale-signature** variables exists, surface a dismissible hint in the Select step
("These N questions share a scale — group as a battery?") that pre-fills the manual
"Group as battery" action for the user to confirm. Keep the existing `:`-pattern
auto-detector (silent, since that pattern is unambiguous). This gives auto-convenience
without the over-grouping risk of silent creation, and always leaves the user in control.

## Testing (TDD)
- **A:** `scale_levels` — digit-labelled; word-labelled 1..5 (→ points 1..5);
  out-of-order codes; a nominal 1/2/3 (still a scale by the code rule — that's fine, it's
  only consumed in battery context); and confirm `_single`/`_combo` behaviour is
  BYTE-IDENTICAL (they don't call `scale_levels`).
- **C (engine/override):** manual battery override → a `battery` question with the
  members; members with mismatched scales or non-scale → skipped; members leave `singles`
  and block auto-grouping; `_battery_stacked` renders a word-labelled scale via
  `scale_levels`; serde/regroup round-trip a battery group.
- **C (api/web):** `/variables` marks scale vars; regroup accepts battery; dialog builds a
  battery from a scale selection.
- **B:** the suggestion fires for ≥3 contiguous same-scale singles; does NOT fire for a
  scattered/short/mixed-scale set; the `:`-pattern auto-battery still works.
- Full-tree regression.

## Phasing
- **Phase 1 — A + C:** robust scale + manual "Group as battery". Deterministic; unblocks
  the customer. Ship first.
- **Phase 2 — B:** the confirmable auto-suggestion. Ships behind the manual fallback.

## Risks / open items (minor)
- Code-as-scale can label a nominal 1..N as a "scale", but it's consumed ONLY in battery
  context (membership asserts intent), so it never reclassifies a standalone question.
- The battery qid must stay stable across edits so charts referencing it survive; derive
  from a slug of the label (fallback: sorted members). Collisions disambiguated with a
  numeric suffix (as `apply_batteries` already does).
- Mixed-scale selection in the dialog: disable "Group as battery" with a hint rather than
  silently skipping, so the user understands why.
