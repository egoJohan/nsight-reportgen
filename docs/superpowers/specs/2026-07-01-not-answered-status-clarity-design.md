# "Not answered" status clarity — design

**Date:** 2026-07-01
**Status:** approved (design), pending implementation plan

## Problem

In the case-level **Data** view, each question row has a **Status** column (right
edge) that renders an amber **"Not answered"** text badge whenever the question has
user-missing codes (`q.missing_values.length > 0`, `web/src/components/DataTab.tsx:206-212`).

Under a column headed "Status", the words "Not answered" read as *"this question
was not answered."* The badge actually means *"this question's data contains values
coded as a non-response (EOS/"don't know", skipped, not asked)."* A customer — a
market-research professional — reported the tag's meaning was unclear (verbatim:
*"Case-tasolla oikeaan reunaan tulee 'not answered' tägi. Sen merkitys jää itselleni
hieman epäselväksi."*).

The flag is genuinely useful (it tells the analyst there is a non-response category
to be aware of), so the fix is about **communication**, not removing the signal.

## Goal

Make the case-list signal unambiguous and move the explanation to where there's room
for it (the question details dialog). No change to what triggers the flag, and no
backend change — the API already returns `missing_values` per question.

## Scope

Frontend only, two files:
- `web/src/components/DataTab.tsx` — the case-list Status column.
- `web/src/components/QuestionDetailsDialog.tsx` — the details dialog.

Out of scope: backend/stats, the chart-level "Not answered" bucket
(`show_not_answered`), the other two Status badges ("Text / not chartable",
"Word cloud"), and any change to how missing values are computed.

## Change 1 — Case-list Status column (`DataTab.tsx`)

Replace the amber **"Not answered" text badge** (the `q.missing_values.length > 0`
branch, currently lines ~206-212) with an amber **warning-triangle icon** that
signals "something to look at," with a hover tooltip:

- Icon: `TriangleAlertIcon` from `lucide-react` (already the project's alert icon,
  see `web/src/components/ui/sonner.tsx`). Add it to the existing lucide import in
  `DataTab.tsx`.
- Amber styling consistent with the current badge (e.g. `text-amber-500` /
  `text-amber-600`), small size (`size-4`), non-interactive beyond the tooltip.
- Tooltip via the native `title` attribute (the pattern already used elsewhere in
  this file), text:
  > `Has "Not answered" / missing-value codes — open for details.`
- The row already opens `QuestionDetailsDialog` on click (`onClick={() =>
  setDetailQid(q.qid)}`), so the icon needs no separate handler.

The `if/else-if` chain is unchanged in order and mutual exclusivity: a question shows
exactly one of — "Text / not chartable" badge, "Word cloud" badge, the warning icon
(this change), or the "—" placeholder. Only the missing-values branch becomes an icon;
the two capability badges stay as text (they are not "attention" flags).

## Change 2 — Details dialog (`QuestionDetailsDialog.tsx`)

The dialog already lists the missing-value codes as amber `code · label` badges
(currently lines ~160-178) under the heading `"Not answered" / missing values`.
Keep the list; retitle and add one explanatory line so the meaning is self-evident:

- Heading: **`Non-response values`** with a muted qualifier *`(excluded from the base by default)`*.
- One-line explanation below the heading, muted small text:
  > `Answer codes the data marks as a non-response — e.g. "Don't know"/EOS, skipped, or not asked. Percentages are calculated over valid answers; these can be shown as a "Not answered" category per chart.`
- Then the existing amber `code · label` badge list, unchanged.

## Verification

The `web/` app has no automated test harness (excluded from the backend suite), so
verification is visual:
1. Run the app locally against the demo store; open a case whose SAV has questions
   with user-missing codes (e.g. one of the client SAVs).
2. Confirm the Data view shows the amber warning icon (not the text badge) on those
   rows, and the tooltip on hover.
3. Open such a question; confirm the dialog shows the retitled "Non-response values"
   section with the explanation and the code·label list.
4. Confirm a question with no missing values still shows "—" (no icon), and that
   not-chartable / word-cloud rows are unaffected.

## Risks / notes

- Icon-only status loses the scannable word "Not answered"; the tooltip + dialog
  compensate, and that is the intent (the word was the source of confusion).
- No i18n layer exists (UI is English); copy stays English.
