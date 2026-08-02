# Classifying variables — string categoricals and banner/indicator columns

**Date:** 2026-08-02
**Status:** approved (design), pending implementation plan

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

Changing how percentages are computed. A new "classifiers" UI (the grouping editor
is the manual override). Weighting. Cross-material classifiers.

## Evidence base

Both rules below were measured against **10 distinct datasets** (the local demo
store, `input/`, and three pulled from staging), not just the reporting material.
Findings are in §1.3 and §2.4. Two limits are worth stating plainly:

- Only **one study** (in two exports) contains banner columns at all. §2's
  thresholds are therefore validated as *non-false-positive* (0 spurious families
  across the other 9 datasets, 100 genuine multi-response questions correctly
  rejected) but not validated as *broadly representative*.
- Most of these files share one survey platform's paradata signature
  (`Vstatus` / `Vlanguage` / `VGeo*`). Behaviour on other platforms' exports is
  unproven for both rules.

## 1. Encoding 1 — string categoricals

### 1.1 Stop calling a coded string column free text

`_is_text_variable` gains a categorical escape hatch:

```
text  ⟺  no value labels
     AND >50 % of values non-numeric          (unchanged)
     AND NOT (distinct ≤ 12 AND maxlen ≤ 30 AND rows/distinct ≥ 10)
```

The **repetition ratio** (`answered rows / distinct values`) does the real work. A
distinct-count rule alone is not enough: `Elamantilanne_muu` in the SuomalainenTyo
material has only **5** distinct values but is a genuine open-end ("Muu, mikä?",
mean length 43, ratio 1.0). The ratio separates it correctly; a `distinct ≤ 12`
rule would have misclassified it and broken its word-cloud/themes path.

"maxlen" and "distinct" are computed over non-null, non-blank values.

### 1.2 Let a label-less string categorical be a classifier

Such a variable has no value labels, so its categories are its **distinct string
values**, in first-seen (file) order. Two helpers must stop keying off
`var.value_labels`:

- `_segmentable` — accept a string categorical whose distinct-value count is 2–10.
- `_has_real_category_labels` — apply the existing generic-flag filter
  (`true/false/empty/yes/no/kyllä/ei/…`) to the **distinct values** when there are
  no value labels.

The second is required, not cosmetic: `var131` "URL_Villas" holds `TRUE`/`FALSE`
and must stay out of the picker, which is exactly what that filter already exists
to prevent.

The engine segments by such a variable through the existing `seg_series` seam,
which already accepts string segment keys with no numeric coercion (built for
cross-tab combos). Segment labels are the values themselves.

### 1.3 Measured effect (10 datasets)

| | |
|---|---|
| Substantive variables recovered | `var214` "Pakkausilme 1 tai 2"; `var129` "New Percent Branch - Concept" (Branch A/B/C — the same concept-path pattern in a different study); `var18` "URL_profiili" (enemmistoomistajat / prosenttiomistajat / vierailijat) |
| Paradata reclassified | 31 — all still removed from the question list and picker by `_is_metadata`, which does not consult `measurement` |
| Genuine open-ends misclassified | **0 of 114** |

## 2. Encoding 2 — banner/indicator columns

### 2.1 One predicate

```
near_partition(masks, n)  ⟺  2 ≤ k ≤ 10
                         AND coverage = |⋃ masks| / n  ≥ 0.95
                         AND overlap  = |{rows in ≥2 masks}| / n  ≤ 0.02
```

where each mask is `column == 1`.

### 2.2 Normalise both encodings to one code path

The two candidate detectors are **mutually exclusive** — each fires on exactly the
export the other misses (§2.4). Rather than maintain both, ungrouped indicator
families are normalised into the existing multi-question shape at model load:

1. **At model load**, extend auto-grouping: bucket *ungrouped* 0/1 indicator
   columns by name stem (trailing digits stripped: `Polku1`, `Polku2` → `polku`).
   A bucket satisfying `near_partition` becomes a multi question, exactly as
   auto-grouping already does for value-labelled ones.
2. **In the picker**, one rule: a **multi question whose members satisfy
   `near_partition` is offerable as a classifying variable.**

This makes the customer's two exports produce the *same* model, which is the
correctness property worth having — today they differ only because one has value
labels on the indicator columns.

### 2.3 Semantics

- Segments are the **member labels** (`Polku 1`, `Polku 2`), in member order.
- Each segment's base is its **own** `=1` count — independent sub-populations, per
  standard banner-table practice. Segments need not sum to the total.
- Because of that, **`percent_base = "question"`** ("distribute the segments within
  each category") **is disabled** for a multi classifier; the frontend hides it and
  the resolver ignores it. Other directions are unaffected.
- `TOTAL` is never offered: alone it is one segment, and `k ≥ 2` excludes it.
- `ChartSpec.classifying_var` carries the **qid**. Resolution order is **variable
  name first, then multi qid**, so no new spec field is needed and `percent_base`,
  `show_total` and cross-tab combos keep working unchanged. `compute()` builds the
  `seg_series` before dispatch, which every path already accepts.
- Overlapping banners the analyst genuinely wants are reached by grouping the
  columns by hand in the grouping editor; auto-detection stays conservative so
  tick-box grids never flood the picker.
- Being offerable as a classifier does **not** remove a multi question from the
  question list — `polku` stays chartable, as it is today. The two roles coexist.

### 2.3a Migration note

Step 1 of §2.2 creates multi questions that did not exist before, so the question
list changes for any material containing an ungrouped near-partition indicator
family. Measured blast radius: **1 of 10 datasets** (`polku` in `mat-erisan`).
Existing reports are unaffected — a report's charts reference qids it already
stored, and a newly created group only adds a question. The manual grouping
override remains the escape hatch if a family is grouped wrongly.

### 2.4 Measured effect (10 datasets)

```
                              mat-erisan   mat-erisan2   other 8
multi near-partition              –            polku        –
ungrouped stem family           polku           –           –
```

Genuine multi-response questions rejected: **100**. Spurious families in the other
9 datasets: **0**. `var7` (10 members, 94 % of respondents tick ≥2) is correctly
rejected.

## 3. Where the changes land

Both fixes sit in the **model-load** layer; no renderer change, and the engine gains
only the classifier→`seg_series` resolution.

| Change | File |
|---|---|
| Cardinality/ratio guard | `ingest/sav_reader.py` (`_is_text_variable`) |
| Indicator-family grouping | `ingest/multi_group.py` (auto-group step) |
| `near_partition` predicate | `ingest/multi_group.py` (shared, exported) |
| String categorical + generic-flag filter | `api/routes_questions.py` (`_segmentable`, `_has_real_category_labels`) |
| Classifier → `seg_series` | `stats/engine.py` (`compute`) |
| Hide `percent_base=question` for a multi classifier | `render/config_schema.py` + frontend self-hide |

## 4. Testing

**Predicate unit tests, against the real shapes:**
- `var214` → categorical; `Elamantilanne_muu` (5 distinct, ratio 1.0) and
  `Rooli_muu` (12 distinct, ratio 1.7) → still text. These two are the near-misses
  that a distinct-count-only rule gets wrong.
- `URL_Villas` (TRUE/FALSE) → not offered; `URL_profiili` (three named segments) →
  offered.
- `polku` → near-partition; `var7` (cov 1.00, ovl 0.94) → not.
- `TOTAL` → rejected on `k ≥ 2`.

**Regression:** the 114 text variables across the 10 datasets stay `text`, and the
31 paradata flips stay out of the question list. This is the test that catches a
future loosening of the ratio.

**Engine:** a string classifier and a multi classifier each produce the expected
segments, labels and per-segment bases; per-segment bases are independent (they do
not sum to the total when segments overlap).

**Serde:** a qid in `classifying_var` round-trips.

**Equivalence:** `mat-erisan` and `mat-erisan2` yield the same classifier offering —
the property §2.2 exists to guarantee.
