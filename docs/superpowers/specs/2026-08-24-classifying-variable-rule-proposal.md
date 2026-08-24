# Which variables become classifying variables — a rule to agree with nSight

**Date:** 2026-08-24
**Status:** proposal, for the nSight discussion P-C-12 asks for
**Ticket:** 7tGYRb8n · Requirement P-C-12 (Speksi 2), affects P-C-11 and P-C-13

P-C-12 is the customer's own open point: *"On vielä tarkennettava se tapa miten ja
missä luokittelevan muuttujan ilmestyminen classifying variable -valikkoon
tapahtuu."* No general rule has been agreed — only individual cases have been
fixed as they were reported.

This document exists so that discussion does not start from a blank page. It
states what nSight Studio does today, what has actually gone wrong, and a
proposed rule, reduced to four decisions.

## What the rule is today

A variable appears in the picker when it passes ALL of:

1. It is not paradata — its name or label is not in the metadata lists
   (`ingest/sav_reader.py`: `vrid`, `vdatesub`, `vstatus`, "response id",
   "ip address", "url", …).
2. `measurement == "categorical"`.
3. It has **2–10 value labels**. A label-less string column is judged instead by
   its **2–10 distinct values** (spec 2026-08-02).
4. It is **not a Likert item** — labels that are mostly sequential digits
   starting at 1 ("1=Täysin eri mieltä" … "7=Täysin samaa mieltä") are what a
   survey MEASURES, not how respondents are segmented. Bracket categoricals
   ("18–24", "500–999 €") are not Likert and do qualify.
5. Its categories are **substantively named** — at least two labels that contain
   letters and are not TRUE/FALSE/EMPTY/yes/no/kyllä/ei.

Two further routes in, both added for specific customer files:

6. A **derived binary flag**: an unlabelled categorical whose data is 0/1
   membership (Attendo's "Suosittelijat", "Kokemusta", "Ammattilainen").
7. A **banner classifier**: a near-partition multi-response question
   (Polku1 + Polku2), offered as a synthetic entry because it is a QUESTION and
   the picker otherwise lists only variables.

Implementation: `_segmentable`, `_is_likert_scale`, `_has_real_category_labels`,
`_is_binary_flag`, `_banner_classifier_rows` in `api/routes_questions.py`.

## What has actually gone wrong

Every reported problem has been the same kind: a variable that SHOULD be a
classifier was not offered, and the analyst had no way to tell why.

| Ticket | Case | Outcome |
|---|---|---|
| **oZ5ipM2e** (Verified) | Packaging study "polku" variable — half the sample sees concept 1, half concept 2. Did not appear in the picker in either encoding the data used. | Fixed by spec 2026-08-02: rules 3 and 6 above |
| Done-list card | Attendo's derived segment flags, unlabelled 0/1 columns | Fixed by rule 6 |
| Analyst recodes | Names look like paradata, categories are real | Fixed by rule 5 |
| **poXKu8Td** (Verified) | Splitting one chart by several background variables | Separate feature |
| **vSsnJkhU** (Verified) | Stacked bars *required* a classifier; they should work from Total alone | Fixed |

The pattern is the point. Rules 3–7 were each added because a specific customer
file broke the rule before it. Each fix was correct and each left the next file's
surprise in place — because "is this a background variable or a measured item?"
is a question about the researcher's INTENT, and SPSS metadata does not record
intent. A 1–7 scale and a 7-region variable are structurally identical.

Worse, the failure is silent: the variable is simply absent, with nothing said.
An analyst cannot tell a variable that was judged unsuitable from one the file
never contained.

## Proposal

Stop trying to infer intent perfectly. Keep the heuristic as a **default**, and
make sure it can never be the last word.

**1. The heuristic stays, as a suggestion.** Rules 1–7 decide what is offered
first. They are good defaults: they keep the picker to the handful of variables
an analyst usually wants, which is why it is usable at all on a 300-variable
file.

**2. Nothing is unreachable.** The picker gets a "Show all variables" option
listing every categorical, heuristic or not, marked as unusual. The endpoint
already supports this (`include_all`, used by the grouping editor), so the cost
is UI only. This alone would have resolved oZ5ipM2e without a spec: the analyst
picks the polku variable and moves on.

**3. A choice is remembered.** When an analyst picks a variable the heuristic did
not offer, that variable is marked as a classifier FOR THAT MATERIAL, so it
appears normally for every colleague and every later report on the same data.
The team teaches the tool about their file once.

**4. Exclusions can be seen.** A quiet line — "12 variables hidden: rating
items, IDs, free text" — with a way to look. A rule nobody can inspect is a rule
nobody can trust, and this is the difference between "the tool is wrong" and
"the tool made a choice I can change".

This answers P-C-12 definitely: **by default the heuristic; always reachable via
show-all; and remembered once chosen.** It also makes the heuristic's mistakes
cheap, which means it can be tuned later without risk.

## What nSight needs to decide

1. **Is a remembered choice per material, per case, or per customer?** Per
   material is the safest (the data is what a variable means), per customer the
   most convenient for repeated waves of the same study.
2. **Who may mark a variable?** Anyone who can edit the report, or only an
   admin? Marking changes what every colleague sees.
3. **Should the heuristic ever hide a marked variable again** — e.g. after a new
   data upload where that variable now has 400 distinct values?
4. **Do rating items stay excluded by default?** Cross-tabbing by a single
   Likert item ("split by how satisfied they are") is legitimate analysis, and
   today it is impossible. Rule 4 assumes nobody wants it; that assumption has
   not been checked with them.

Question 4 is the one to ask first. If they do want it, rule 4 changes from a
filter to a sort order, and the picker becomes considerably simpler.

## Not in scope here

The implementation. P-C-12 says two phases — *ensin määrittely nSightin kanssa,
sitten toteutus* — and this is the first. Once the four questions are answered,
the work is small: a UI toggle, a per-material list of marked variables, and a
line of explanatory text.
