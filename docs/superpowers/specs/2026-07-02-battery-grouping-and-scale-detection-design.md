# Battery grouping + robust scale detection — design

## Goal
Let users create the **stacked multi-variable comparison** chart (a battery: each
statement a 100%-stacked bar split by a shared rating scale — the DNA/"tärkeys"
example) from several similar rating variables. Customer: "En keksi miten saan
tehtyä sellaisen sliden jossa on usean samankaltaisen muuttujan pylväät pinottuna
samaan kuvaan."

## Root cause (three gaps, verified)
1. **Auto-battery needs a `:` label pattern.** `battery_group._cells` only finds
   batteries whose variable labels are `category:subject:question`. Plain statement
   labels ("voin tunnistautua verkossa…") are never grouped → shown as N singles.
2. **No manual battery grouping.** The grouping dialog only makes `multi` groups;
   `apply_grouping_override` explicitly SKIPS `kind: "battery"` (Phase 2 deferred).
3. **Scale parsed from a leading digit.** `_rating_scale` maps a code→point via the
   leading integer of each value label ("5 - Erittäin tärkeä"→5). Word-only labels
   ("Erittäin tärkeä", coded 1..5) yield `{}` → the stack can't build.

Decision (customer): do **both** auto-detection AND manual grouping, and make scale
detection robust either way (leading-digit labels OR plain 1..N codes).

## Design

### Part A — robust scale detection (`stats/engine.py`)  [foundation]
Replace/augment `_rating_scale` with `scale_levels(var) -> list[(code, label, point)]`:
- If every non-missing value label has a leading integer → use those points (today's
  behaviour, keeps out-of-order SAV codes correct).
- Else, if the non-missing value **codes** form a plausible ordinal scale — contiguous
  integers, `3 ≤ N ≤ 11` — treat the **codes as the points** (1..N), keeping the word
  labels for display. So an importance 1..5 with word labels becomes a real scale.
- Else `[]` (not a scale). The N-bound + contiguity guard avoids mistaking a nominal
  categorical (gender 1/2, few-value) for a scale; the battery context (shared scale
  across members) further protects against false positives.
- `_battery_stacked` / `_battery` / `_single(is_rating)` use `scale_levels`, so
  word-labelled batteries render with their real levels and order.

### Part B — smarter auto-battery detection (`ingest/battery_group.py`)
Add a second detector alongside the `:`-pattern one: group variables that
- share the **same scale signature** (identical non-missing code→label map, via A), AND
- share a **common label stem** (a non-trivial common prefix, e.g. "Kuinka tärkeä on…"
  or a shared bracketed subject), AND
- are **contiguous** in SAV order (a real grid, not scattered look-alikes),
into one battery: stem = the common prefix (the question), subjects = each var's
distinctive remainder. Conservative thresholds (`min_members ≥ 3`, `≥2` share the stem)
to avoid over-grouping unrelated same-scale questions. Existing `:`-pattern detection
stays; the new one only fires when it doesn't.

### Part C — manual "Group as battery" (grouping override + dialog)
- `ingest/grouping_override.py`: apply `kind: "battery"` manual groups — build a battery
  question from the selected variables (members are the statements; text = the group
  label), IF the members share a scale (via A); else skip (leniency).
- `render/config_schema` / model: a battery question suggests `stacked_horizontal_bar`.
- `api/routes_questions.py`: `/variables` (or a new flag) exposes a `scale` marker so the
  dialog can offer only scale variables for a battery; `_validate`/regroup accept battery.
- Web `ManageGroupingDialog`: a second action **"Group as battery"** (beside "Group as
  multi"), enabled when ≥2 selected variables are scale-type and share a scale. Creates
  `{kind: "battery", variables, label}`; existing battery groups shown as cards, splittable.
  (Report-scoped, like the multi grouping already shipped.)

## Testing (TDD)
- **A:** `scale_levels` — digit-labelled, word-labelled 1..5, out-of-order codes, and a
  nominal 1/2/3 categorical (→ not a scale); battery stacked renders a word-labelled scale.
- **B:** several same-scale contiguous vars with a common stem → one battery; scattered
  same-scale but unrelated vars → NOT grouped; the `:`-pattern case still works.
- **C:** manual battery override → battery question with the members; non-scale members →
  skipped; regroup/serde accept battery; report round-trips.
- Full-tree regression (scale detection touches `_single`/battery paths broadly).

## Phasing
- **Phase 1:** A (robust scale) + C (manual "Group as battery") — the reliable path the
  user drives; unblocks the customer deterministically.
- **Phase 2:** B (smarter auto-detection) — convenience, heuristic; ship after A/C so
  there's always a manual fallback if it over/under-groups.

## Risks
- Auto-detection (B) is heuristic and can't be tested against the customer's data here —
  hence conservative thresholds + manual override as the safety net.
- Code-as-scale detection could misread an ordinal-looking nominal; the N≥3 + contiguity
  guard and the battery-context requirement mitigate it. A wrong auto-group is fixable
  via manual split.
