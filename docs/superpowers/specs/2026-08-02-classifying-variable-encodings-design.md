# Classifying variables — string categoricals and banner/indicator columns

**Date:** 2026-08-02
**Status:** approved (design), pending implementation plan
**Revision:** 2. Changes from revision 1, all found in review:
§0 a latent `Total` denominator bug this feature would have made common;
§1.1 thresholds re-derived from a sensitivity sweep (`maxlen ≤ 30` was arbitrary
and a false-negative risk);
§2.1 coverage rule replaced — the old one rejected screened designs;
§2.3 segmentation seam changed from `seg_series` to `seg_masks`, because revision 1
specified semantics its own mechanism could not express;
§2.4 the picker endpoint enumerates variables only, so question-backed classifiers
need explicit synthetic entries;
§2.5 a banner classifier plus a second classifier raised an unguarded `KeyError`.

## Problem

In packaging and concept studies, part of the sample sees concept 1 and part sees
concept 2. That "path" (*polku*) variable is the natural classifying variable — but
in the customer's Erisan material it does not appear in the **Classifying variable**
picker at all, in either of the two encodings the data uses.

The picker offers a variable when `_segmentable(v) or _is_binary_flag(v, df)`, and
`_segmentable` requires `measurement == "categorical"` **and** 2–10 value labels
**and** not a Likert scale. Neither encoding passes:

**Encoding 1 — a coded string column** (`var214`, "Pakkausilme 1 tai 2"):

```
measurement : text
value_labels: []
raw values  : ['Pakkausilme 1', 'Pakkausilme 2']
```

`_is_text_variable` (`ingest/sav_reader.py`) classifies it as open-ended free text.
Its only test is "are >50 % of values non-numeric?" — with no cardinality check, two
distinct values are indistinguishable from 500 essay answers. The variable is then
both non-chartable and non-segmentable.

**Encoding 2 — banner/indicator columns** (`Polku1`, `Polku2`, plus a `TOTAL`
column that is 1 for everyone). One column per group, each 1-or-missing. These fail
`_segmentable` (one value label, needs ≥2) and fail `_is_binary_flag` on three
counts: they carry a value label, their label differs from their name, and their
data is `{1.0}` rather than `{0.0, 1.0}`.

The two encodings coexist in the same study. The customer's two exports of the same
data differ only in whether the indicator columns carry 0/1 value labels — and that
detail alone changes whether auto-grouping picks them up.

## Goal

Both encodings reach the Classifying variable picker, with segments named from the
data, on any material — without the analyst recoding the SAV.

## Non-goals

A new "classifiers" UI (the grouping editor is the manual override). Weighting.
Cross-material classifiers. Pairing a banner classifier with a **second**
classifying variable (§2.5). Changing the percentage *directions* or their
resolution — §0 corrects one denominator that is currently wrong, and changes
nothing for a classifier that covers every respondent.

## Evidence base

Both rules were measured against **10 distinct datasets** (the local demo store,
`input/`, and three pulled from staging) — 147 text variables and 175
multi-response questions — not just the reporting material. Two limits are worth
stating plainly:

- Only **one study** (in two exports) contains banner columns at all. §2's
  thresholds are validated as *non-false-positive* (1 hit in 175 multis) but not as
  *broadly representative*.
- Most of these files share one survey platform's paradata signature
  (`Vstatus` / `Vlanguage` / `VGeo*`). Behaviour on other platforms' exports is
  unproven for both rules.

## 0. Prerequisite — a latent `Total` denominator bug

Found while reviewing this design. `aggregate_counts` computes the `Total` column
over **all** non-null rows, while `segment_bases` computes the `Total` base over
**segmented** rows only. The two disagree whenever respondents fall outside every
segment, and the cell percentages are then counts-over-a-smaller-base.

Reproduced end-to-end (100 respondents, a classifier covering 60):

```
segments: ('A', 'B', 'Total')   show_total: True
base_n  : {'A': 30, 'B': 30, 'Total': 60}
   A      sums to  100.0%
   B      sums to  100.0%
   Total  sums to  167.0%          <-- wrong
```

`resolve_show_total` returns `True` unconditionally for stacked bars, so a stacked
chart classified by a partially-covering variable draws that inflated Total bar.

This is **pre-existing and independent of this design** — it needs only a classifier
with missing or unlabelled values. It is latent in the customer's current report
(no chart there sets a classifying variable), but §2 makes partial coverage
*routine*: a screened design leaves 40 % of respondents in no segment by
construction. Shipping §2 on top of this would turn a latent bug into a common one.

**Therefore:** make the two `Total` denominators agree — restrict the `Total`
aggregate to rows that fall in some segment, matching `segment_bases` — as a
**separate change, landed and tested before** §1 and §2. It is a bug fix in its own
right and should not be bundled with this feature.

## 1. Encoding 1 — string categoricals

### 1.1 Stop calling a coded string column free text

`_is_text_variable` gains a categorical escape hatch:

```
text  ⟺  no value labels
     AND >50 % of values non-numeric                    (unchanged)
     AND NOT (distinct ≤ 12 AND ratio ≥ 10 AND maxlen ≤ 80)
```

where `ratio = answered rows / distinct values`, and `distinct` / `maxlen` are
computed over non-null, non-blank values.

**The ratio is the discriminator.** A distinct-count rule alone is not enough:
`Elamantilanne_muu` (SuomalainenTyo) has only **5** distinct values but is a genuine
open-end ("Muu, mikä?", ratio 1.0), and `Rooli_muu` has 12 distinct values at ratio
1.7. Both are correctly kept as text by the ratio and would be misclassified by a
`distinct ≤ 12` rule on its own.

**Threshold robustness.** A sweep over `maxlen ∈ {20,30,40,60,80,120}` ×
`ratio ∈ {5,10,20}` across all 147 text variables gives an **identical** outcome in
every cell: 2 substantive flips (`var214`, in both exports), 0 open-ends
misclassified. The result is therefore insensitive to both knobs across a wide band;
`ratio = 10` is a mid-band choice.

`maxlen ≤ 80` is a **guard against pathological cases** (e.g. two repeated
boilerplate paragraphs), not a discriminator — it excludes nothing in this corpus.
It is set generously on purpose: a legitimate concept label such as
`"Pakkausilme 1 – uusi punainen ilme"` (34 chars) must not be rejected. Revision 1
specified `maxlen ≤ 30`, which was both arbitrary and a live false-negative risk.

### 1.2 Let a label-less string categorical be a classifier

Such a variable has no value labels, so its categories are its **distinct string
values**, ordered by **natural (alphanumeric) sort** — so `Pakkausilme 2` precedes
`Pakkausilme 10`. Sorting is used rather than first-appearance because row order in
a SAV is arbitrary and would make category order non-reproducible across exports.

Two helpers must stop keying off `var.value_labels`:

- `_segmentable` — accept a string categorical whose distinct-value count is 2–10.
- `_has_real_category_labels` — apply the existing generic-flag filter
  (`true/false/empty/yes/no/kyllä/ei/…`) to the **distinct values** when there are
  no value labels.

The second is required, not cosmetic: `var131` "URL_Villas" holds `TRUE`/`FALSE`
and must stay out of the picker, which is exactly what that filter already exists
to prevent.

**The 12/10 asymmetry is intentional.** `distinct ≤ 12` governs *chartability*
(text vs categorical); `2 ≤ n ≤ 10` governs *classifier eligibility*. A string
variable with 11–12 distinct values becomes a chartable categorical question but is
not offered as a classifier — exactly the existing behaviour for a value-labelled
categorical with 11–12 labels.

### 1.3 Measured effect (10 datasets, 147 text variables)

| | |
|---|---|
| Substantive variables recovered | `var214` "Pakkausilme 1 tai 2"; `var129` "New Percent Branch - Concept" (Branch A/B/C — the same concept-path pattern in a different study); `var18` "URL_profiili" (enemmistoomistajat / prosenttiomistajat / vierailijat) |
| Paradata reclassified | 31 — all still removed from the question list and picker by `_is_metadata`, which does not consult `measurement` |
| Genuine open-ends misclassified | **0 of 114** |

## 2. Encoding 2 — banner/indicator columns

### 2.1 The predicate

```
near_partition(masks, n)  ⟺  2 ≤ k ≤ 10
                         AND covered = |⋃ masks|  ≥  max(30, 0.10·n)
                         AND overlap = |{rows in ≥2 masks}| / covered  ≤  0.02
                         AND every mask has ≥ 1 respondent
```

where each mask is `column == 1`.

**Overlap is measured among *covered* respondents, not the whole sample, and the
floor is an absolute count.** Revision 1 required `coverage ≥ 0.95` of the sample,
which silently rejects the common **screened** design where only qualifiers see a
concept. Verified: a simulated 60 %-qualifying `polku` (coverage 0.56) is accepted
by this predicate and was rejected by revision 1's.

The absolute floor and the non-empty-member rule exist because dropping the
coverage requirement altogether admits degenerate families — `var157` (3 members,
1 respondent) and `var17` (10 members, 1 respondent) have vacuously perfect
exclusivity.

### 2.2 Normalise both encodings to one code path

The two candidate detectors are **mutually exclusive** — each fires on exactly the
export the other misses (§2.6). Rather than maintain both, ungrouped indicator
families are normalised into the existing multi-question shape at model load:

1. **At model load**, extend auto-grouping: bucket *ungrouped* 0/1 indicator
   columns by name stem (trailing digits stripped: `Polku1`, `Polku2` → `polku`).
   A bucket satisfying `near_partition` becomes a multi question via the existing
   `apply_groups`, so it is indistinguishable from an auto-detected one.
2. **In the picker**, one rule: a **multi question whose members satisfy
   `near_partition` is offerable as a classifying variable.**

This makes the customer's two exports produce the *same* model, which is the
correctness property worth having — today they differ only because one has value
labels on the indicator columns.

**Qid uniqueness.** `_group_qid` derives a qid from the first member's name prefix
and does not guarantee uniqueness. Synthesised families must go through the same
uniqueness check as any other group; on collision, suffix (`polku-2`) rather than
overwrite an existing question.

### 2.3 Segmentation mechanism — `seg_masks`, not `seg_series`

`seg_series` assigns **one key per row**, so it structurally cannot represent a
respondent belonging to two segments. Revision 1 specified independent
sub-population bases *and* `seg_series` as the mechanism; those are contradictory.

The segmentation seam therefore gains an optional **`seg_masks: dict[str, Series]`**
— one boolean mask per segment — accepted by `segment_bases` and `aggregate_counts`
alongside the existing `seg_series`:

- **Disjoint masks** (the auto-detected case) produce results identical to
  `seg_series`, so nothing changes for existing classifiers.
- **Overlapping masks** (only reachable via manual grouping) give each segment its
  own base, computed from its own mask — standard banner-table practice.

`seg_series` is unchanged and still used for cross-tab combos.

### 2.4 Semantics

- Segments are the **member labels** (`Polku 1`, `Polku 2`), in member order.
- Each segment's base is the count of respondents valid on the question **and** in
  that segment's mask. Segments need not sum to `Total`.
- **`Total`** is the count of respondents valid on the question and in **at least
  one** segment — the same rule `segment_bases` already applies under `seg_series`,
  and the rule §0 makes `aggregate_counts` agree with. With overlapping segments
  `Total < Σ segments`; with a screened design `Total < n`. §0 must land first or
  the `Total` bar on a screened design is inflated.
- **`percent_base = "question"`** ("distribute the segments within each category")
  **is disabled** for a banner classifier, because overlapping segments do not sum
  to 100 %. The frontend hides it; the resolver falls back to `"classifier"`.
- Segment **relabelling is skipped**: `_relabel_segments` maps numeric codes to a
  variable's value labels, and returns unchanged when handed a qid (its
  `model.variable()` lookup is already guarded). The labels are correct as
  constructed, so this needs no new code — but it is load-bearing and must be
  covered by a test.
- `TOTAL` is never offered: alone it is one segment, and `k ≥ 2` excludes it.
- `ChartSpec.classifying_var` carries the **qid**. Resolution order is **variable
  name first, then multi qid**, so no new spec field is needed. `compute()` builds
  `seg_masks` before dispatch.
- **The picker must be fed these explicitly.** `GET /materials/{id}/variables`
  builds its list from `model.variables.values()`, so a question-backed classifier
  would never appear there. The endpoint appends one synthetic entry per
  near-partition multi:

  ```
  name        = qid            (what lands in ChartSpec.classifying_var)
  label       = question text
  measurement = "categorical"
  n_values    = k              (member count)
  segmentable = true
  aggregatable= false
  tickbox     = false
  ```

  The frontend needs no change: it already offers any entry whose `segmentable` is
  true. Because `name` is a qid, the frontend can also detect a banner classifier
  (its `name` matches a question, not a variable) to hide `classifying_var_2` per
  §2.5.
- Being offerable as a classifier does **not** remove a multi question from the
  question list — `polku` stays chartable. The two roles coexist.
- Overlapping banners the analyst genuinely wants are reached by grouping the
  columns by hand in the grouping editor; auto-detection stays conservative so
  tick-box grids never flood the picker.

### 2.5 A banner classifier cannot be combined with a second classifier

`_combo_segmentation` does `pd.to_numeric(data[classifying_var])`. A qid is not a
DataFrame column, so pairing a banner classifier with `classifying_var_2` raises an
unguarded `KeyError`. This phase does **not** support that combination:

- the frontend hides `classifying_var_2` when the primary classifier is a qid;
- the engine guards it and raises a clear, actionable error rather than a `KeyError`.

Supporting it would mean crossing overlapping masks with a second variable, whose
base semantics are not obvious. Deferred deliberately.

### 2.6 Measured effect (10 datasets, 175 multi-response questions)

```
                              mat-erisan   mat-erisan2   other 8
multi near-partition              –            polku        –
ungrouped stem family           polku           –           –
```

Hits under the §2.1 predicate: **1 of 175**. `var7` (10 members, 94 % of
respondents tick ≥2) is correctly rejected; so are the three degenerate families.

## 3. Where the changes land

Both fixes sit in the **model-load** layer; no renderer change.

| Change | File |
|---|---|
| Cardinality/ratio guard | `ingest/sav_reader.py` (`_is_text_variable`) |
| `near_partition` predicate (shared, exported) | `ingest/multi_group.py` |
| Indicator-family grouping | `ingest/multi_group.py` (`enrich_model`) |
| String categorical + generic-flag filter | `api/routes_questions.py` (`_segmentable`, `_has_real_category_labels`) |
| Synthetic picker entries for banner classifiers | `api/routes_questions.py` (`/variables`) |
| `seg_masks` segmentation | `stats/base_rules.py` (`segment_bases`), `stats/aggregate.py` (`aggregate_counts`) |
| Classifier → `seg_masks`; combo guard | `stats/engine.py` (`compute`, `_combo_segmentation`) |
| Hide `percent_base=question` and `classifying_var_2` for a banner classifier | `render/config_schema.py` + frontend self-hide |

## 4. Testing

**Rule A predicate, against the real shapes:**
- `var214` → categorical; `Elamantilanne_muu` (5 distinct, ratio 1.0) and
  `Rooli_muu` (12 distinct, ratio 1.7) → still text. These are the near-misses a
  distinct-count-only rule gets wrong.
- A 34-character concept label → still categorical (guards the `maxlen` regression
  that revision 1 would have caused).
- `URL_Villas` (TRUE/FALSE) → not offered; `URL_profiili` (three named segments) →
  offered.
- Category order is natural-sorted and stable under row shuffling.

**Rule B predicate:**
- `polku` → accepted; `var7` (overlap 0.94) → rejected.
- A **screened** family (60 % coverage, disjoint) → accepted. This is the
  revision-1 regression test.
- Degenerate families (`var157`, `var17`: 1 covered respondent) → rejected.
- `TOTAL` alone → rejected on `k ≥ 2`.

**API:**
- `/variables` includes a synthetic entry for `polku` with `segmentable = true` and
  `name` equal to its qid — the test that the picker can actually see it.

**Prerequisite (§0), landed separately:**
- A classifier covering 60 of 100 respondents: the `Total` column's percentages sum
  to 100 %, not 167 %.
- A fully-covering classifier is unchanged — the regression guard for every existing
  cross-tab.

**Engine:**
- Disjoint `seg_masks` produce byte-identical results to the `seg_series` path —
  the guarantee that existing classifiers are untouched.
- Overlapping masks give per-segment bases that do **not** sum to `Total`.
- `Total` excludes respondents in no segment (screened design).
- A qid in `classifying_var` leaves segment labels unchanged (`_relabel_segments`
  no-op).
- Banner classifier + `classifying_var_2` raises the guarded error, not `KeyError`.

**Regression:** the 114 text variables across the 10 datasets stay `text`, and the
31 paradata flips stay out of the question list. This is the test that catches a
future loosening of the ratio.

**Serde:** a qid in `classifying_var` round-trips.

**Equivalence:** `mat-erisan` and `mat-erisan2` yield the same classifier offering —
the property §2.2 exists to guarantee.

## 5. Migration and risk

**New questions.** §2.2 step 1 creates multi questions that did not exist before, so
the question list changes for any material containing an ungrouped near-partition
indicator family. Measured blast radius: **1 of 10 datasets** (`polku` in
`mat-erisan`). Existing reports are unaffected — a report's charts reference qids it
already stored, and a new group only adds a question. The manual grouping override
remains the escape hatch.

**Reclassified paradata.** 31 variables change `measurement` from `text` to
`categorical`. All are filtered by `_is_metadata`, which ignores `measurement`, so
none reach the question list or picker. The regression test above pins this.

**Residual risks.**
- §2's thresholds rest on **one study**. If a second banner-bearing dataset later
  contradicts them, the predicate — not the surrounding machinery — is what changes.
- Both rules are unproven on survey platforms other than the one dominating this
  corpus.
- `near_partition` is evaluated per model load. Cost is O(rows × members) over
  candidate families only; negligible at these sizes, but it is new per-load work.
- Materials with fewer than 30 respondents never auto-detect a banner classifier
  (the absolute floor exceeds `n`). Manual grouping still reaches it. This is
  deliberate — exclusivity is not evidence of anything at that sample size.
