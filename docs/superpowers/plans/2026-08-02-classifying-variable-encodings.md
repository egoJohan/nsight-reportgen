# Classifying Variable Encodings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a study's "path" variable (which concept a respondent saw) usable as a classifying variable in both encodings real SAV files use — a coded string column, and one-column-per-group indicator columns.

**Architecture:** Both fixes land in the model-load layer. A coded string column stops being misread as open-ended free text and is segmented through the existing string-keyed `seg_series` seam. Indicator columns are normalised into the existing multi-question shape at load, and a multi whose members near-partition the sample becomes offerable as a classifier, segmented through a new `seg_masks` seam that (unlike `seg_series`) can express overlap. A pre-existing `Total`-denominator bug is fixed first, because supporting screened designs makes it common.

**Tech Stack:** Python 3.13, pandas, duckdb, pytest, FastAPI; React + TypeScript frontend (Vite).

**Spec:** `docs/superpowers/specs/2026-08-02-classifying-variable-encodings-design.md`

## Global Constraints

- Run tests with `.venv/bin/python -m pytest tests/suite -q` from `/home/johan/Projects/nsight/proto`. The legacy suite `tests/rb` must also stay green.
- Frontend typecheck: `cd web && npx tsc --noEmit -p tsconfig.app.json`.
- Rule A thresholds, exactly: `distinct ≤ 12` AND `ratio ≥ 10` AND `maxlen ≤ 80`, where `ratio = answered rows / distinct values`; `distinct`/`maxlen` over non-null, non-blank values.
- Rule B predicate, exactly: `2 ≤ k ≤ 10` AND `covered ≥ max(30, 0.10·n)` AND `overlap / covered ≤ 0.02` AND every mask has ≥1 respondent. Overlap is counted among **covered** respondents, not the whole sample.
- Never commit `*.sav` or anything under `work/` — client IPR (already gitignored).
- Client fixtures for manual checks: case `case-erisan` / `mat-erisan` (string encoding, `var214`) and `case-erisan2` / `mat-erisan2` (indicator encoding, `Polku1`/`Polku2`) in the local demo store.
- Commit after each task. Do not bundle tasks.

---

### Task 1: Fix the `Total` denominator mismatch (spec §0)

`aggregate_counts` totals over **all** non-null rows; `segment_bases` totals over **segmented** rows. With a classifier that does not cover everyone, the Total column's percentages are counts over a smaller base and sum to >100%. This is pre-existing and must land before Task 8 makes partial coverage routine.

**Files:**
- Modify: `src/reportbuilder/stats/aggregate.py:24-30`
- Test: `tests/suite/unit/stats/test_aggregate.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `aggregate_counts(data, value_var, classifying_var=None, *, seg_series=None)` — unchanged signature; the `("<code>", "Total")` entries are now restricted to rows that fall in some segment whenever a segmentation is given.

- [ ] **Step 1: Write the failing test**

Append to `tests/suite/unit/stats/test_aggregate.py`:

```python
import numpy as np
import pandas as pd

from reportbuilder.stats.aggregate import aggregate_counts


def test_total_excludes_rows_outside_every_segment():
    """The Total column must sit on the same population as the segment bases —
    respondents the classifier does not cover belong to neither. Regression: the
    Total used to count all rows, so a 60%-covering classifier made the Total
    column's percentages sum to 167%."""
    df = pd.DataFrame({
        "q":   [1.0, 2.0] * 50,
        "clf": [1.0] * 30 + [2.0] * 30 + [np.nan] * 40,
    })
    counts = aggregate_counts(df, "q", "clf")
    # 60 covered rows: 30 in segment 1, 30 in segment 2, alternating q -> 30/30
    assert counts[(1.0, "Total")] == 30
    assert counts[(2.0, "Total")] == 30
    assert counts[(1.0, "Total")] + counts[(2.0, "Total")] == 60


def test_total_unchanged_when_classifier_covers_everyone():
    """The regression guard for every existing cross-tab."""
    df = pd.DataFrame({"q": [1.0, 2.0] * 50, "clf": [1.0] * 50 + [2.0] * 50})
    counts = aggregate_counts(df, "q", "clf")
    assert counts[(1.0, "Total")] == 50
    assert counts[(2.0, "Total")] == 50


def test_total_counts_all_rows_when_there_is_no_classifier():
    df = pd.DataFrame({"q": [1.0, 2.0] * 50})
    counts = aggregate_counts(df, "q")
    assert counts[(1.0, "Total")] == 50
    assert counts[(2.0, "Total")] == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_aggregate.py -q -k total`
Expected: `test_total_excludes_rows_outside_every_segment` FAILS with `assert 50 == 30`.

- [ ] **Step 3: Restrict the Total aggregate to segmented rows**

In `src/reportbuilder/stats/aggregate.py`, replace the `total = con.execute(...)` block:

```python
    # The Total column sits on the SAME population as the per-segment bases (see
    # base_rules.segment_bases): a respondent the classifier does not cover belongs
    # to no segment and must not inflate the Total. Without a classifier, every row
    # counts. (spec 2026-08-02 §0)
    where = f'"{value_var}" IS NOT NULL'
    if seg_col is not None:
        where += f' AND "{seg_col}" IS NOT NULL'
    total = con.execute(
        f'SELECT "{value_var}" AS v, COUNT(*) AS n FROM d WHERE {where} GROUP BY v'
    ).fetchall()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite tests/rb -q`
Expected: all pass. If a stats test that asserts a Total count fails, it was asserting the buggy denominator — read it, confirm its classifier has uncovered rows, and update the expected number.

- [ ] **Step 5: Commit**

```bash
git add src/reportbuilder/stats/aggregate.py tests/suite/unit/stats/test_aggregate.py
git commit -m "fix(stats): Total column excludes rows outside every segment"
```

---

### Task 2: Stop misreading a coded string column as free text (spec §1.1)

**Files:**
- Modify: `src/reportbuilder/ingest/sav_reader.py:26-40` (`_is_text_variable`)
- Test: `tests/suite/unit/ingest/test_text_variable.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `_is_text_variable(series: pd.Series, value_labels: tuple) -> bool` — unchanged signature, narrower result.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/ingest/test_text_variable.py`:

```python
"""A coded string column (few short values, each repeated many times) is a
CATEGORICAL, not an open-ended answer. The repetition ratio is the discriminator:
`Elamantilanne_muu` in the SuomalainenTyo material has only 5 distinct values and
is still a genuine open-end. (spec 2026-08-02 §1.1)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.ingest.sav_reader import _is_text_variable


def _series(values):
    return pd.Series(values, dtype=object)


def test_two_coded_values_repeated_is_categorical():
    s = _series(["Pakkausilme 1", "Pakkausilme 2"] * 256)   # d=2, ratio=256
    assert _is_text_variable(s, ()) is False


def test_low_distinct_but_unrepeated_is_still_text():
    """Elamantilanne_muu: 5 distinct, 5 answers, ratio 1.0 — an open-end."""
    s = _series(["Olen eläkkeellä ja teen satunnaisia keikkoja",
                 "Opiskelen ja käyn töissä", "Yrittäjä", "Vanhempainvapaalla",
                 "Työtön, etsin töitä"])
    assert _is_text_variable(s, ()) is True


def test_twelve_distinct_low_ratio_is_still_text():
    """Rooli_muu: 12 distinct, 20 answers, ratio 1.7 — an open-end."""
    s = _series([f"vastaus {i}" for i in range(12)] + [f"vastaus {i}" for i in range(8)])
    assert _is_text_variable(s, ()) is True


def test_long_concept_label_is_still_categorical():
    """34 characters — must not be rejected. A maxlen of 30 would have."""
    s = _series(["Pakkausilme 1 – uusi punainen ilme",
                 "Pakkausilme 2 – vanha sininen ilme"] * 200)
    assert _is_text_variable(s, ()) is False


def test_boilerplate_paragraphs_stay_text():
    """The maxlen guard: two very long repeated blocks are not categories."""
    s = _series(["A" * 400, "B" * 400] * 200)
    assert _is_text_variable(s, ()) is True


def test_high_cardinality_open_end_is_text():
    s = _series([f"vapaa vastaus numero {i}" for i in range(300)])
    assert _is_text_variable(s, ()) is True


def test_blank_values_do_not_count_as_a_category():
    """Blank strings are not answers; they must not become a category or inflate
    the distinct count."""
    s = _series(["Pakkausilme 1", "Pakkausilme 2", "", "   "] * 100)
    assert _is_text_variable(s, ()) is False


def test_value_labelled_variable_is_never_text():
    s = _series([1.0, 2.0] * 50)
    assert _is_text_variable(s, (("x",),)) is False


def test_all_blank_series_is_not_text():
    assert _is_text_variable(_series(["", "  "]), ()) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_text_variable.py -q`
Expected: `test_two_coded_values_repeated_is_categorical`, `test_long_concept_label_is_still_categorical` and `test_blank_values_do_not_count_as_a_category` FAIL (currently return `True`).

- [ ] **Step 3: Add the categorical escape hatch**

In `src/reportbuilder/ingest/sav_reader.py`, add above `_is_text_variable`:

```python
# A coded string column (few short values, each repeated many times) is a
# CATEGORICAL, not an open-ended answer. `ratio` is the discriminator: a genuine
# open-end has roughly one row per distinct value even when few people answered
# ("Muu, mikä?"), while a coded category is repeated across the sample. `maxlen`
# is only a guard against pathological repeated boilerplate — a sweep over
# maxlen 20..120 x ratio 5..20 across 147 real text variables gave an identical
# outcome in every cell. (spec 2026-08-02 §1.1)
_CODED_MAX_DISTINCT = 12
_CODED_MIN_RATIO = 10.0
_CODED_MAX_LEN = 80


def _is_coded_string(series: pd.Series) -> bool:
    """True when a label-less string column looks like a coded categorical."""
    nn = series.dropna().astype(str)
    nn = nn[nn.str.strip() != ""]
    if len(nn) == 0:
        return False
    distinct = nn.nunique()
    if distinct == 0 or distinct > _CODED_MAX_DISTINCT:
        return False
    if int(nn.str.len().max()) > _CODED_MAX_LEN:
        return False
    return (len(nn) / distinct) >= _CODED_MIN_RATIO
```

Then in `_is_text_variable`, replace the final `return` with:

```python
    if float(coerced.isna().mean()) <= 0.5:
        return False
    return not _is_coded_string(nn)
```

Note `nn` here is the existing `series.dropna()`; `_is_coded_string` re-filters blanks itself.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_text_variable.py -q && .venv/bin/python -m pytest tests/suite tests/rb -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/reportbuilder/ingest/sav_reader.py tests/suite/unit/ingest/test_text_variable.py
git commit -m "fix(ingest): a coded string column is categorical, not free text"
```

---

### Task 3: Corpus regression guard for Task 2

Task 2's thresholds were derived from 10 real datasets. This pins that outcome so a future loosening is caught.

**Files:**
- Test: `tests/suite/unit/ingest/test_text_variable_corpus.py` (create)

**Interfaces:**
- Consumes: `_is_text_variable` from Task 2.
- Produces: nothing.

- [ ] **Step 1: Write the test**

Create `tests/suite/unit/ingest/test_text_variable_corpus.py`:

```python
"""Corpus guard for the coded-string rule. Runs only when the local client
materials are present (they are gitignored IPR), so CI without them skips."""
from __future__ import annotations

import pathlib

import pytest

from reportbuilder.ingest.sav_reader import read_sav

_STORE = pathlib.Path("work/demo-store/materials")

# (material, variable, expected measurement) — the cases that pin the thresholds.
_CASES = [
    ("mat-erisan.sav", "var214", "categorical"),    # the target: 2 values, ratio 255
    ("mat-erisan.sav", "var43", "text"),            # 52 distinct, ratio 1.1
    ("mat-207.sav", "Elamantilanne_muu", "text"),   # 5 distinct, ratio 1.0
    ("mat-207.sav", "Rooli_muu", "text"),           # 12 distinct, ratio 1.7
    ("mat-207.sav", "Perustelu", "text"),           # 371 distinct
]


@pytest.mark.parametrize("material,var,expected", _CASES)
def test_corpus_measurement(material, var, expected):
    path = _STORE / material
    if not path.exists():
        pytest.skip(f"{material} not available locally")
    _df, model = read_sav(str(path))
    assert model.variables[var].measurement == expected


def test_no_substantive_open_end_becomes_categorical():
    """Across every local material: a variable that is still text must not have
    flipped, and the only NON-paradata flips are the known coded columns."""
    from reportbuilder.ingest.sav_reader import _is_metadata

    if not _STORE.exists():
        pytest.skip("local materials not available")
    allowed = {"var214", "var129", "var18"}
    unexpected = []
    for path in sorted(_STORE.glob("*.sav")):
        _df, model = read_sav(str(path))
        for name, v in model.variables.items():
            if v.measurement == "categorical" and not v.value_labels:
                if _is_metadata(name, v.label or name):
                    continue
                if name not in allowed:
                    unexpected.append(f"{path.name}:{name} ({v.label})")
    assert not unexpected, f"unexpected label-less categoricals: {unexpected}"
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_text_variable_corpus.py -q -rs`
Expected: PASS (or SKIP if materials are absent). If `test_no_substantive_open_end_becomes_categorical` fails, a real open-end is being misclassified — do not widen `allowed`; retune the ratio.

- [ ] **Step 3: Commit**

```bash
git add tests/suite/unit/ingest/test_text_variable_corpus.py
git commit -m "test(ingest): corpus guard for the coded-string thresholds"
```

---

### Task 4: Offer a label-less string categorical as a classifier (spec §1.2)

**Files:**
- Modify: `src/reportbuilder/ingest/sav_reader.py` (add `string_categories`)
- Modify: `src/reportbuilder/api/routes_questions.py` (`_segmentable`, `_has_real_category_labels`, `_category_labels`)
- Test: `tests/suite/unit/api/test_string_classifier.py` (create)

**Interfaces:**
- Consumes: `_is_coded_string` (Task 2).
- Produces: `string_categories(series: pd.Series) -> tuple[str, ...]` — distinct non-blank values, natural-sorted. `_segmentable(var, df=None) -> bool` — gains an optional `df` so a label-less string categorical can be judged by its values.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/api/test_string_classifier.py`:

```python
"""A label-less string categorical is a legitimate classifying variable; a
generic TRUE/FALSE flag is not. (spec 2026-08-02 §1.2)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.api import routes_questions as R
from reportbuilder.ingest.sav_reader import string_categories
from reportbuilder.model.question import Variable


def _var(name, label, measurement="categorical"):
    return Variable(name=name, label=label, measurement=measurement,
                    value_labels=(), missing_values=frozenset())


def test_string_categories_are_natural_sorted():
    s = pd.Series(["Polku 10", "Polku 2", "Polku 1", "Polku 2"])
    assert string_categories(s) == ("Polku 1", "Polku 2", "Polku 10")


def test_string_categories_ignore_blanks_and_are_stable_under_shuffling():
    a = pd.Series(["Pakkausilme 2", "", "Pakkausilme 1", "   "])
    b = pd.Series(["Pakkausilme 1", "   ", "Pakkausilme 2", ""])
    assert string_categories(a) == string_categories(b) == ("Pakkausilme 1", "Pakkausilme 2")


def test_coded_string_column_is_segmentable():
    v = _var("var214", "Pakkausilme 1 tai 2")
    df = pd.DataFrame({"var214": ["Pakkausilme 1", "Pakkausilme 2"] * 100})
    assert R._segmentable(v, df) is True


def test_generic_true_false_flag_is_not_offered():
    v = _var("var131", "URL_Villas")
    df = pd.DataFrame({"var131": ["TRUE", "FALSE"] * 100})
    assert R._has_real_category_labels(v, df) is False


def test_named_segment_recode_is_offered():
    v = _var("var18", "URL_profiili")
    df = pd.DataFrame({"var18": ["enemmistoomistajat", "prosenttiomistajat",
                                 "vierailijat"] * 100})
    assert R._segmentable(v, df) is True
    assert R._has_real_category_labels(v, df) is True


def test_eleven_distinct_values_are_chartable_but_not_classifiable():
    """The 12/10 asymmetry: chartability and classifier eligibility differ, exactly
    as they already do for a value-labelled categorical."""
    v = _var("v", "Eleven")
    df = pd.DataFrame({"v": [f"cat {i}" for i in range(11)] * 20})
    assert R._segmentable(v, df) is False


def test_value_labelled_variable_is_unaffected_by_the_df_argument():
    from reportbuilder.model.question import ValueLabel
    v = Variable(name="clf", label="C", measurement="categorical",
                 value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B")),
                 missing_values=frozenset())
    assert R._segmentable(v) is True
    assert R._segmentable(v, pd.DataFrame({"clf": [1.0, 2.0]})) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/api/test_string_classifier.py -q`
Expected: FAIL — `string_categories` does not exist and `_segmentable` takes one argument.

- [ ] **Step 3: Add `string_categories` to `sav_reader.py`**

```python
def _natural_key(s: str) -> list:
    """Sort key that orders 'Polku 2' before 'Polku 10'."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", s) if t != ""]


def string_categories(series: pd.Series) -> tuple[str, ...]:
    """The categories of a LABEL-LESS string categorical: its distinct non-blank
    values, natural-sorted.

    Sorted rather than first-seen because row order in a SAV is arbitrary, and
    category order must be reproducible across exports. (spec 2026-08-02 §1.2)"""
    nn = series.dropna().astype(str)
    nn = nn[nn.str.strip() != ""]
    return tuple(sorted(set(nn.str.strip()), key=_natural_key))
```

- [ ] **Step 4: Widen the two picker predicates**

In `src/reportbuilder/api/routes_questions.py`, change `_segmentable` and `_has_real_category_labels` to accept an optional DataFrame and fall back to the string values when there are no value labels:

```python
def _segmentable(var, df=None) -> bool:
    """...(existing docstring)...

    A LABEL-LESS string categorical (a coded path/concept column) is judged by its
    distinct VALUES instead of its value labels. (spec 2026-08-02 §1.2)"""
    if var.measurement != "categorical":
        return False
    if not var.value_labels:
        cats = _string_cats(var, df)
        return 2 <= len(cats) <= 10
    nv = len(var.value_labels)
    if not (2 <= nv <= 10):
        return False
    return not _is_likert_scale(var)


def _string_cats(var, df) -> tuple[str, ...]:
    """Distinct values of a label-less string categorical, or () when unavailable."""
    if df is None or var.name not in getattr(df, "columns", []):
        return ()
    return string_categories(df[var.name])
```

and in `_has_real_category_labels`, source the candidate labels from the values when there are none:

```python
def _has_real_category_labels(var, df=None) -> bool:
    generic = {"true", "false", "empty", "yes", "no", "kyllä", "ei", "-", "—", ""}
    if var.value_labels:
        candidates = [vl.label or "" for vl in var.value_labels]
    else:
        candidates = list(_string_cats(var, df))
    named = [lbl for c in candidates if (lbl := c.strip())
             and any(ch.isalpha() for ch in lbl)
             and lbl.lower() not in generic]
    return len(named) >= 2
```

Add `string_categories` to the `sav_reader` import at the top of the file. Update the two existing call sites (`_keep` and the `segmentable` field in the `/variables` payload) to pass `_df_or_none()`, and `_category_labels` to return `string_categories(df[...])` for a label-less string categorical.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/api/test_string_classifier.py -q && .venv/bin/python -m pytest tests/suite tests/rb -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/reportbuilder/ingest/sav_reader.py src/reportbuilder/api/routes_questions.py tests/suite/unit/api/test_string_classifier.py
git commit -m "feat(api): offer a label-less string categorical as a classifier"
```

---

### Task 5: Segment by a string classifier in the engine (spec §1.2)

`_single`/`_multi`/`_summary` pass `spec.classifying_var` to `segment_bases`, which does `pd.to_numeric(...)` — every row of a string column becomes NaN. Route a string classifier through the existing string-keyed `seg_series` seam instead.

**Files:**
- Modify: `src/reportbuilder/stats/engine.py:34-53` (`_combo_segmentation`)
- Test: `tests/suite/unit/stats/test_string_classifier_engine.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks (works on raw df values).
- Produces: `_combo_segmentation(spec, data)` — unchanged name and signature; now also returns a `(seg_series, ordered)` pair for a SINGLE classifier whose column holds strings. Returns `(None, None)` otherwise, exactly as before.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/stats/test_string_classifier_engine.py`:

```python
"""Cross-tabbing by a coded string column. (spec 2026-08-02 §1.2)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _model_and_df():
    q = Variable(name="q", label="Q", measurement="categorical",
                 value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
                 missing_values=frozenset())
    path = Variable(name="var214", label="Pakkausilme 1 tai 2",
                    measurement="categorical", value_labels=(),
                    missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "var214": path}, questions=[])
    df = pd.DataFrame({
        "q": [1.0, 2.0, 1.0, 1.0],
        "var214": ["Pakkausilme 1", "Pakkausilme 1", "Pakkausilme 2", "Pakkausilme 2"],
    })
    return model, Question(qid="q", kind="single", variables=("q",), text="Q"), df


def _spec(**kw):
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="var214", number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def test_segments_are_the_string_values():
    model, q, df = _model_and_df()
    r = engine.compute(q, _spec(), df, model)
    assert set(r.segments) == {"Pakkausilme 1", "Pakkausilme 2", "Total"}


def test_per_segment_bases_are_correct():
    model, q, df = _model_and_df()
    r = engine.compute(q, _spec(), df, model)
    assert r.base_n["Pakkausilme 1"] == 2
    assert r.base_n["Pakkausilme 2"] == 2
    assert r.base_n["Total"] == 4


def test_cells_split_by_the_string_segment():
    model, q, df = _model_and_df()
    r = engine.compute(q, _spec(), df, model)
    assert r.cell("Yes", "Pakkausilme 2").count == 2.0
    assert r.cell("No", "Pakkausilme 1").count == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_string_classifier_engine.py -q`
Expected: FAIL — segments come back as just `("Total",)` because the numeric cast wipes the column.

- [ ] **Step 3: Handle a single string classifier in `_combo_segmentation`**

In `src/reportbuilder/stats/engine.py`, insert before the existing `if not (cv1 and cv2): return None, None`:

```python
    # A coded STRING classifier (a path/concept column with no value labels) has no
    # numeric codes, so it cannot go down the pd.to_numeric path. Its values ARE the
    # segment keys — exactly what seg_series accepts. (spec 2026-08-02 §1.2)
    if cv1 and not cv2 and cv1 in data.columns:
        col = data[cv1]
        if col.dtype == object:
            vals = col.dropna().astype(str).str.strip()
            vals = vals[vals != ""]
            if len(vals) and not _numeric_like(vals):
                keys = pd.Series([None] * len(data), index=data.index, dtype=object)
                keys.loc[vals.index] = vals
                # Same ordering the picker and category list use — one source of truth.
                ordered = string_categories(col)
                return keys, ordered
```

and add near the top of the module:

```python
from reportbuilder.ingest.sav_reader import string_categories


def _numeric_like(values: pd.Series) -> bool:
    """True when the values are really numbers held as strings — those keep the
    existing numeric segmentation path."""
    return bool(pd.to_numeric(values, errors="coerce").notna().all())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_string_classifier_engine.py -q && .venv/bin/python -m pytest tests/suite tests/rb -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/reportbuilder/stats/engine.py tests/suite/unit/stats/test_string_classifier_engine.py
git commit -m "feat(stats): segment by a coded string classifier"
```

---

### Task 6: The `near_partition` predicate (spec §2.1)

**Files:**
- Modify: `src/reportbuilder/ingest/multi_group.py`
- Test: `tests/suite/unit/ingest/test_near_partition.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `near_partition(masks: list[pd.Series], n: int) -> bool`
  - `member_masks(df, members: tuple[str, ...]) -> list[pd.Series] | None` — `column == 1` per member, or `None` if any member is missing from `df`.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/ingest/test_near_partition.py`:

```python
"""Do these indicator columns split the sample into segments? (spec 2026-08-02 §2.1)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.ingest.multi_group import member_masks, near_partition


def _masks(*cols):
    return [pd.Series(c, dtype=bool) for c in cols]


def test_clean_two_way_split_is_a_partition():
    n = 200
    a = [True] * 100 + [False] * 100
    b = [False] * 100 + [True] * 100
    assert near_partition(_masks(a, b), n) is True


def test_screened_design_is_a_partition():
    """Only 60% qualify and see a concept; the rest are in no segment. A coverage
    threshold measured over the whole sample wrongly rejected this."""
    n = 200
    a = [True] * 60 + [False] * 140
    b = [False] * 60 + [True] * 60 + [False] * 80
    assert near_partition(_masks(a, b), n) is True


def test_overlapping_multi_response_is_not_a_partition():
    """var7: nearly everyone ticks two or more."""
    n = 200
    a = [True] * 200
    b = [True] * 190 + [False] * 10
    assert near_partition(_masks(a, b), n) is False


def test_degenerate_family_with_one_respondent_is_rejected():
    """var157/var17: exclusivity is vacuously perfect when almost nobody answered."""
    n = 1549
    a = [True] + [False] * 1548
    b = [False] * 1549
    assert near_partition(_masks(a, b), n) is False


def test_family_with_an_empty_member_is_rejected():
    n = 200
    a = [True] * 100 + [False] * 100
    b = [False] * 100 + [True] * 100
    c = [False] * 200
    assert near_partition(_masks(a, b, c), n) is False


def test_single_column_is_rejected():
    assert near_partition(_masks([True] * 200), 200) is False


def test_more_than_ten_columns_is_rejected():
    n = 200
    cols = [[i * 18 <= j < (i + 1) * 18 for j in range(200)] for i in range(11)]
    assert near_partition(_masks(*cols), n) is False


def test_two_percent_overlap_is_tolerated():
    n = 200
    a = [True] * 102 + [False] * 98
    b = [False] * 100 + [True] * 100          # 2 rows in both
    assert near_partition(_masks(a, b), n) is True


def test_ten_percent_overlap_is_rejected():
    n = 200
    a = [True] * 120 + [False] * 80
    b = [False] * 100 + [True] * 100          # 20 rows in both
    assert near_partition(_masks(a, b), n) is False


def test_member_masks_returns_none_for_a_missing_column():
    df = pd.DataFrame({"Polku1": [1.0, None]})
    assert member_masks(df, ("Polku1", "Polku2")) is None


def test_member_masks_treats_missing_as_not_in_segment():
    df = pd.DataFrame({"Polku1": [1.0, None, 1.0]})
    masks = member_masks(df, ("Polku1",))
    assert list(masks[0]) == [True, False, True]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_near_partition.py -q`
Expected: FAIL with `ImportError: cannot import name 'near_partition'`.

- [ ] **Step 3: Implement the predicate**

Add to `src/reportbuilder/ingest/multi_group.py`:

```python
# A "banner" family is one indicator column per group (Polku1/Polku2): the columns
# SPLIT the sample rather than collecting multiple ticks per respondent. Overlap is
# measured among COVERED respondents so a screened design — where only qualifiers
# see a concept — still counts, and the floor is an absolute count so a family only
# one person answered cannot pass on vacuous exclusivity. (spec 2026-08-02 §2.1)
_BANNER_MIN_COVERED = 30
_BANNER_MIN_COVERAGE = 0.10
_BANNER_MAX_OVERLAP = 0.02


def member_masks(df, members: tuple[str, ...]):
    """`column == 1` per member, or None when any member is absent from `df`."""
    import pandas as pd

    masks = []
    for name in members:
        if name not in getattr(df, "columns", []):
            return None
        masks.append(pd.to_numeric(df[name], errors="coerce") == 1.0)
    return masks


def near_partition(masks, n: int) -> bool:
    """True when these indicator masks split the sample into usable segments."""
    import pandas as pd

    k = len(masks)
    if not (2 <= k <= 10) or n <= 0:
        return False
    if any(int(m.sum()) < 1 for m in masks):
        return False
    M = pd.concat(masks, axis=1)
    covered = int(M.any(axis=1).sum())
    if covered < max(_BANNER_MIN_COVERED, _BANNER_MIN_COVERAGE * n):
        return False
    overlap = int((M.sum(axis=1) >= 2).sum())
    return (overlap / covered) <= _BANNER_MAX_OVERLAP
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_near_partition.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/reportbuilder/ingest/multi_group.py tests/suite/unit/ingest/test_near_partition.py
git commit -m "feat(ingest): near_partition predicate for banner column families"
```

---

### Task 7: Group ungrouped indicator families into multis (spec §2.2)

Makes the two customer exports produce the same model: one has 0/1 value labels on `Polku1`/`Polku2` (so existing auto-grouping catches them), the other does not.

**Files:**
- Modify: `src/reportbuilder/ingest/multi_group.py` (add `suggest_indicator_families`)
- Modify: `src/reportbuilder/ingest/grouping_override.py:91,131-133`
- Modify: `src/reportbuilder/api/model_loader.py:109-133`
- Test: `tests/suite/unit/ingest/test_indicator_families.py` (create)

**Interfaces:**
- Consumes: `near_partition`, `member_masks` (Task 6).
- Produces:
  - `suggest_indicator_families(model, df) -> list[tuple[str, ...]]` — returns `[]` when `df is None`.
  - `apply_grouping_override(model, override, df=None)` — new optional third parameter.
  - `_finalize(model, material_id, client, override, df=None)` in `model_loader`.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/ingest/test_indicator_families.py`:

```python
"""Ungrouped 1-or-missing indicator columns become one multi question, so an export
WITHOUT 0/1 value labels behaves like one with them. (spec 2026-08-02 §2.2)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.ingest.grouping_override import apply_grouping_override
from reportbuilder.ingest.multi_group import suggest_indicator_families
from reportbuilder.model.question import Question, QuestionModel, Variable


def _var(name, label):
    return Variable(name=name, label=label, measurement="categorical",
                    value_labels=(), missing_values=frozenset())


def _model():
    vars_ = {"Polku1": _var("Polku1", "Polku 1"),
             "Polku2": _var("Polku2", "Polku 2"),
             "TOTAL": _var("TOTAL", "Kaikki vastaajat")}
    qs = [Question(qid=n.lower(), kind="single", variables=(n,), text=v.label)
          for n, v in vars_.items()]
    return QuestionModel(variables=vars_, questions=qs)


def _df(n=200):
    half = n // 2
    return pd.DataFrame({
        "Polku1": [1.0] * half + [None] * (n - half),
        "Polku2": [None] * half + [1.0] * (n - half),
        "TOTAL": [1.0] * n,
    })


def test_indicator_family_is_suggested():
    assert suggest_indicator_families(_model(), _df()) == [("Polku1", "Polku2")]


def test_total_alone_is_not_a_family():
    fams = suggest_indicator_families(_model(), _df())
    assert all("TOTAL" not in f for f in fams)


def test_no_dataframe_means_no_suggestion():
    assert suggest_indicator_families(_model(), None) == []


def test_grouping_override_creates_the_multi_question():
    m = apply_grouping_override(_model(), {}, df=_df())
    polku = [q for q in m.questions if q.kind == "multi"]
    assert len(polku) == 1
    assert polku[0].variables == ("Polku1", "Polku2")


def test_without_a_dataframe_the_model_is_unchanged():
    m = apply_grouping_override(_model(), {}, df=None)
    assert [q for q in m.questions if q.kind == "multi"] == []


def test_a_forced_single_is_not_regrouped():
    m = apply_grouping_override(_model(), {"singles": ["Polku1"]}, df=_df())
    assert [q for q in m.questions if q.kind == "multi"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_indicator_families.py -q`
Expected: FAIL with `ImportError: cannot import name 'suggest_indicator_families'`.

- [ ] **Step 3: Implement the suggester**

Add to `src/reportbuilder/ingest/multi_group.py`:

```python
def suggest_indicator_families(model, df) -> list[tuple[str, ...]]:
    """Ungrouped 0/1 indicator columns that, bucketed by name stem, split the sample.

    Complements suggest_multi_groups, which only buckets variables that carry binary
    VALUE LABELS — the same columns exported without labels are otherwise invisible.
    Returns [] without a DataFrame, since the split cannot be measured from metadata
    alone. (spec 2026-08-02 §2.2)"""
    from collections import OrderedDict

    import pandas as pd

    if df is None:
        return []
    grouped = {v for q in model.questions
               if q.kind in ("multi", "battery") for v in q.variables}
    buckets: "OrderedDict[str, list[str]]" = OrderedDict()
    for name, var in model.variables.items():
        if name in grouped or name not in getattr(df, "columns", []):
            continue
        s = pd.to_numeric(df[name], errors="coerce")
        vals = set(s.dropna().unique().tolist())
        if not vals or not vals <= {0.0, 1.0}:
            continue
        m = _STEM_PATTERN.match(name)
        if m and m.group(1):
            buckets.setdefault(m.group(1).lower(), []).append(name)
    out = []
    for members in buckets.values():
        masks = member_masks(df, tuple(members))
        if masks and near_partition(masks, len(df)):
            out.append(tuple(members))
    return out
```

and near the other module-level patterns:

```python
# "Polku1"/"Polku2" -> stem "polku"; also tolerates "Polku_1" and "Polku-01".
_STEM_PATTERN = re.compile(r"^(.*?)[ _\-]?0*(\d+)$")
```

- [ ] **Step 4: Thread the DataFrame through the grouping pipeline**

In `src/reportbuilder/ingest/grouping_override.py`, change the signature and the auto-multi line:

```python
def apply_grouping_override(model: QuestionModel, override: dict | None,
                            df=None) -> QuestionModel:
```

```python
    # Auto multi suggestions that don't touch a manual member or a forced single.
    auto_multi = [g for g in suggest_multi_groups(model) if not (set(g) & blocked)]
    # Indicator families (one 1-or-missing column per group) need the DATA to tell a
    # banner from a tick-box grid, so they are suggested separately. (spec §2.2)
    auto_multi += [g for g in suggest_indicator_families(model, df)
                   if not (set(g) & blocked) and g not in auto_multi]
    all_multi = manual_groups + auto_multi
```

Import `suggest_indicator_families` alongside the existing `suggest_multi_groups` import.

In `src/reportbuilder/api/model_loader.py`, pass the df through:

```python
def _finalize(model, material_id: str, client, override: dict | None, df=None):
    """..."""
    model = apply_grouping_override(model, override or {}, df=df)
    ...


def model_for_material(material_id: str, client, override: dict | None = None):
    df, model, _label = _read(material_id, client)
    return _finalize(model, material_id, client, override, df=df)


def df_model_for_material(material_id: str, client, override: dict | None = None):
    df, model, _label = _read(material_id, client)
    return df, _finalize(model, material_id, client, override, df=df)


def df_model_label_for_material(material_id: str, client, override: dict | None = None):
    df, model, label = _read(material_id, client)
    return df, _finalize(model, material_id, client, override, df=df), label
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_indicator_families.py -q && .venv/bin/python -m pytest tests/suite tests/rb -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/reportbuilder/ingest/multi_group.py src/reportbuilder/ingest/grouping_override.py src/reportbuilder/api/model_loader.py tests/suite/unit/ingest/test_indicator_families.py
git commit -m "feat(ingest): group ungrouped indicator families into multi questions"
```

---

### Task 8: `seg_masks` segmentation (spec §2.3)

`seg_series` holds one key per row and cannot express a respondent in two segments. Add a mask-based alternative that degenerates to identical results when the masks are disjoint.

**Files:**
- Modify: `src/reportbuilder/stats/base_rules.py:58-90` (`segment_bases`)
- Modify: `src/reportbuilder/stats/aggregate.py` (`aggregate_counts`)
- Test: `tests/suite/unit/stats/test_seg_masks.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `segment_bases(..., *, seg_masks: dict[str, pd.Series] | None = None)` and `aggregate_counts(..., *, seg_masks: dict[str, pd.Series] | None = None)`. When `seg_masks` is given it takes precedence over `seg_series` and `classifying_var`.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/stats/test_seg_masks.py`:

```python
"""Mask-based segmentation: one boolean mask per segment, so segments may overlap.
(spec 2026-08-02 §2.3)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import ValueLabel, Variable
from reportbuilder.stats.aggregate import aggregate_counts
from reportbuilder.stats.base_rules import segment_bases


def _var():
    return Variable(name="q", label="Q", measurement="categorical",
                    value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
                    missing_values=frozenset())


def _df(n=100):
    return pd.DataFrame({"q": [1.0, 2.0] * (n // 2)})


def test_disjoint_masks_match_the_seg_series_path():
    """The guarantee that existing classifiers are untouched."""
    df = _df()
    keys = pd.Series(["A"] * 50 + ["B"] * 50, index=df.index)
    masks = {"A": keys == "A", "B": keys == "B"}
    assert segment_bases(df, _var(), seg_masks=masks) == \
           segment_bases(df, _var(), seg_series=keys)
    assert aggregate_counts(df, "q", seg_masks=masks) == \
           aggregate_counts(df, "q", seg_series=keys)


def test_overlapping_masks_get_independent_bases():
    df = _df()
    masks = {"A": pd.Series([True] * 60 + [False] * 40, index=df.index),
             "B": pd.Series([False] * 40 + [True] * 60, index=df.index)}
    bases = segment_bases(df, _var(), seg_masks=masks)
    assert bases["A"] == 60
    assert bases["B"] == 60
    assert bases["Total"] == 100           # union, not the sum
    assert bases["A"] + bases["B"] > bases["Total"]


def test_total_excludes_rows_in_no_segment():
    """A screened design: 40 respondents saw nothing."""
    df = _df()
    masks = {"A": pd.Series([True] * 30 + [False] * 70, index=df.index),
             "B": pd.Series([False] * 30 + [True] * 30 + [False] * 40, index=df.index)}
    bases = segment_bases(df, _var(), seg_masks=masks)
    assert bases["Total"] == 60
    counts = aggregate_counts(df, "q", seg_masks=masks)
    assert counts[(1.0, "Total")] + counts[(2.0, "Total")] == 60


def test_counts_are_per_mask():
    df = _df()
    masks = {"A": pd.Series([True] * 50 + [False] * 50, index=df.index),
             "B": pd.Series([False] * 50 + [True] * 50, index=df.index)}
    counts = aggregate_counts(df, "q", seg_masks=masks)
    assert counts[(1.0, "A")] == 25
    assert counts[(2.0, "B")] == 25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_seg_masks.py -q`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'seg_masks'`.

- [ ] **Step 3: Add `seg_masks` to `segment_bases`**

In `src/reportbuilder/stats/base_rules.py`, add the parameter and handle it first:

```python
def segment_bases(data: pd.DataFrame, var: Variable, classifying_var: str | None = None,
                  missing_override: set[float] | None = None,
                  *, seg_series: pd.Series | None = None,
                  seg_masks: dict[str, pd.Series] | None = None,
                  classifier_var: Variable | None = None) -> dict[str, int]:
    """...(existing docstring)...

    When `seg_masks` is given it IS the segmentation — one boolean mask per segment,
    which unlike `seg_series` may OVERLAP. Each segment's base comes from its own
    mask; "Total" is the union, so with overlap Total < sum of segments.
    (spec 2026-08-02 §2.3)
    """
    valid = _valid_mask(data, var, missing_override)
    if seg_masks is not None:
        any_seg = pd.Series(False, index=data.index)
        for m in seg_masks.values():
            any_seg = any_seg | m
        bases = {"Total": int((valid & any_seg).sum())}
        for key, m in seg_masks.items():
            bases[str(key)] = int((valid & m).sum())
        return bases
    if seg_series is not None:
        ...
```

- [ ] **Step 4: Add `seg_masks` to `aggregate_counts`**

In `src/reportbuilder/stats/aggregate.py`, handle masks before the duckdb path (masks cannot be one SQL column):

```python
def aggregate_counts(data: pd.DataFrame, value_var: str,
                     classifying_var: str | None = None,
                     *, seg_series=None, seg_masks=None,
                     ) -> dict[tuple[float | None, str], int]:
    """...(existing docstring)...

    When `seg_masks` is given it IS the segmentation — one boolean mask per segment,
    which may OVERLAP, so counts are taken per mask rather than by a single GROUP BY.
    "Total" counts the union. (spec 2026-08-02 §2.3)"""
    if seg_masks is not None:
        counts: dict[tuple[float | None, str], int] = {}
        v = pd.to_numeric(data[value_var], errors="coerce")
        answered = v.notna()
        any_seg = pd.Series(False, index=data.index)
        for m in seg_masks.values():
            any_seg = any_seg | m
        for code, grp in v[answered & any_seg].groupby(v):
            counts[(float(code), "Total")] = int(len(grp))
        for key, m in seg_masks.items():
            sub = v[answered & m]
            for code, grp in sub.groupby(sub):
                counts[(float(code), str(key))] = int(len(grp))
        return counts
    ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_seg_masks.py -q && .venv/bin/python -m pytest tests/suite tests/rb -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/reportbuilder/stats/base_rules.py src/reportbuilder/stats/aggregate.py tests/suite/unit/stats/test_seg_masks.py
git commit -m "feat(stats): mask-based segmentation that can express overlap"
```

---

### Task 9: Resolve a banner classifier in the engine and offer it in the picker (spec §2.4)

**Files:**
- Modify: `src/reportbuilder/stats/engine.py` (`_combo_segmentation`, `_single`, `_multi`, `_summary` call sites)
- Modify: `src/reportbuilder/api/routes_questions.py` (`/variables` payload)
- Test: `tests/suite/unit/stats/test_banner_classifier.py` (create)
- Test: `tests/suite/integration/api/test_questions.py` (append)

**Interfaces:**
- Consumes: `near_partition`, `member_masks` (Task 6); `seg_masks` (Task 8).
- Produces: `_banner_masks(spec, data, model) -> dict[str, pd.Series] | None` in `engine.py` — the segment masks when `spec.classifying_var` names a near-partition multi question, else `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/stats/test_banner_classifier.py`:

```python
"""Cross-tabbing by a banner (indicator-column) classifier. (spec 2026-08-02 §2.4)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup(n=200):
    half = n // 2
    q = Variable(name="q", label="Q", measurement="categorical",
                 value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
                 missing_values=frozenset())
    p1 = Variable(name="Polku1", label="Polku 1", measurement="categorical",
                  value_labels=(), missing_values=frozenset())
    p2 = Variable(name="Polku2", label="Polku 2", measurement="categorical",
                  value_labels=(), missing_values=frozenset())
    banner = Question(qid="polku", kind="multi", variables=("Polku1", "Polku2"),
                      text="Polku")
    model = QuestionModel(variables={"q": q, "Polku1": p1, "Polku2": p2},
                          questions=[banner])
    df = pd.DataFrame({
        "q": [1.0, 2.0] * (n // 2),
        "Polku1": [1.0] * half + [None] * (n - half),
        "Polku2": [None] * half + [1.0] * (n - half),
    })
    return model, Question(qid="q", kind="single", variables=("q",), text="Q"), df


def _spec(**kw):
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="polku", number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def test_segments_are_the_member_labels():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert set(r.segments) == {"Polku 1", "Polku 2", "Total"}


def test_per_segment_bases():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert r.base_n["Polku 1"] == 100
    assert r.base_n["Polku 2"] == 100
    assert r.base_n["Total"] == 200


def test_segment_labels_are_not_mangled_by_the_relabeller():
    """_relabel_segments expects a variable name; handed a qid it must no-op."""
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert "Polku 1" in r.segments


def test_a_non_partition_multi_is_not_used_as_a_classifier():
    """An overlapping tick-box multi must fall through, not become segments."""
    model, q, df = _setup()
    df["Polku2"] = 1.0                       # everyone in both -> 100% overlap
    r = engine.compute(q, _spec(), df, model)
    assert set(r.segments) == {"Total"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_banner_classifier.py -q`
Expected: FAIL — segments come back as `("Total",)`.

- [ ] **Step 3: Resolve the qid to masks in the engine**

In `src/reportbuilder/stats/engine.py` add:

```python
def _banner_masks(spec, data: pd.DataFrame, model: QuestionModel):
    """Segment masks when `classifying_var` names a near-partition MULTI question.

    Resolution is variable-name-first: a real column always wins, so this only fires
    for a qid. Returns None otherwise. (spec 2026-08-02 §2.4)"""
    from reportbuilder.ingest.multi_group import member_masks, near_partition

    cv = getattr(spec, "classifying_var", None)
    if not cv or cv in data.columns or cv in model.variables:
        return None
    q = next((x for x in model.questions if x.qid == cv and x.kind == "multi"), None)
    if q is None:
        return None
    masks = member_masks(data, q.variables)
    if not masks or not near_partition(masks, len(data)):
        return None
    return {model.variable(v).label: m for v, m in zip(q.variables, masks)}
```

Thread it through the three consumers. In `_single`, replace the segmentation block's head:

```python
    banner = _banner_masks(spec, data, model)
    seg_series, ordered = (None, None) if banner else _combo_segmentation(spec, data)
    if banner is not None:
        bases = segment_bases(data, var, missing_override=eff, seg_masks=banner)
        counts = aggregate_counts(data, var.name, seg_masks=banner)
        segments = (*banner.keys(), "Total")
    elif seg_series is not None:
        ...
```

Apply the same three-line pattern in `_multi` and `_summary` at their `_combo_segmentation` call sites.

- [ ] **Step 4: Run the engine tests**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_banner_classifier.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Write the failing API test**

Append to `tests/suite/integration/api/test_questions.py`:

```python
def test_variables_include_a_banner_classifier(client_mock):
    """A near-partition multi is offered in the picker. /variables enumerates
    model.variables, so a question-backed classifier needs an explicit entry.
    (spec 2026-08-02 §2.4)"""
    r = client_mock.get("/materials/mat-x/variables")
    assert r.status_code == 200
    names = {v["name"] for v in r.json()["variables"]}
    # every entry must be usable as a classifying_var value
    for v in r.json()["variables"]:
        assert isinstance(v["name"], str) and v["name"]
        assert "segmentable" in v
    assert names          # sanity
```

- [ ] **Step 6: Append synthetic picker entries**

In `src/reportbuilder/api/routes_questions.py`, after `all_vars.sort(...)` in the `/variables` handler, build the extra rows:

```python
    # A banner classifier is a QUESTION, not a variable, so it would never appear in
    # a list built from model.variables. Append one synthetic entry per
    # near-partition multi; the frontend already offers anything segmentable.
    # (spec 2026-08-02 §2.4)
    from reportbuilder.ingest.multi_group import member_masks, near_partition

    banner_rows = []
    if not include_all:
        _df = _df_or_none()
        if _df is not None:
            for q in model.questions:
                if q.kind != "multi":
                    continue
                masks = member_masks(_df, q.variables)
                if masks and near_partition(masks, len(_df)):
                    banner_rows.append({
                        "name": q.qid,
                        "label": q.text or q.qid,
                        "measurement": "categorical",
                        "n_values": len(q.variables),
                        "aggregatable": False,
                        "segmentable": True,
                        "tickbox": False,
                        # Explicit marker so the frontend need not infer it by
                        # comparing against the variable list. Drives the control
                        # hiding in Task 10.
                        "banner": True,
                    })
```

and append `banner_rows` to the returned `"variables"` list.

Add the field to `web/src/lib/api.ts` on the `Variable` interface:

```ts
  // True for a banner classifier — a question-backed classifier whose segments
  // may overlap, so no second classifier and no "each category" direction.
  banner?: boolean;
```

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/python -m pytest tests/suite tests/rb -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/reportbuilder/stats/engine.py src/reportbuilder/api/routes_questions.py tests/suite/unit/stats/test_banner_classifier.py tests/suite/integration/api/test_questions.py
git commit -m "feat: offer and segment by a banner (indicator-column) classifier"
```

---

### Task 10: Guard the unsupported combinations (spec §2.4, §2.5)

A banner classifier plus a second classifier reaches `pd.to_numeric(data[qid])` and raises a bare `KeyError`; and `percent_base="question"` is meaningless when segments may overlap.

**Files:**
- Modify: `src/reportbuilder/stats/engine.py` (`_combo_segmentation`)
- Modify: `src/reportbuilder/stats/percent_base.py`
- Modify: `web/src/components/wizard/StepConfigure.tsx`
- Test: `tests/suite/unit/stats/test_banner_classifier.py` (append)

**Interfaces:**
- Consumes: `_banner_masks` (Task 9).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/suite/unit/stats/test_banner_classifier.py`:

```python
import pytest


def test_second_classifier_with_a_banner_raises_a_clear_error():
    """Deferred deliberately: crossing overlapping masks with a second variable has
    no obvious base semantics. It must not surface as a bare KeyError."""
    model, q, df = _setup()
    df["gender"] = [1.0, 2.0] * 100
    model.variables["gender"] = Variable(
        name="gender", label="Sukupuoli", measurement="categorical",
        value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
        missing_values=frozenset())
    with pytest.raises(ValueError, match="second classifying variable"):
        engine.compute(q, _spec(classifying_var_2="gender"), df, model)


def test_percent_base_question_falls_back_for_a_banner():
    model, q, df = _setup()
    r = engine.compute(q, _spec(percent_base="question"), df, model)
    # each segment sums to 100% (classifier direction), not the question direction
    for seg in ("Polku 1", "Polku 2"):
        total = sum((r.cell(c, seg).pct or 0) for c in r.categories)
        assert abs(total - 100.0) < 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_banner_classifier.py -q -k "second_classifier or percent_base"`
Expected: FAIL — `KeyError: 'polku'` rather than `ValueError`.

- [ ] **Step 3: Guard the combination**

At the top of `_combo_segmentation` in `engine.py`:

```python
    cv1 = spec.classifying_var
    cv2 = getattr(spec, "classifying_var_2", None)
    if cv1 and cv2 and cv1 not in data.columns:
        raise ValueError(
            f"'{cv1}' is a banner classifier and cannot be combined with a "
            f"second classifying variable ('{cv2}'). Remove the second classifier."
        )
```

In `percent_base.py`, make the "question" direction fall back when segments may overlap. `ChartSpec` is a frozen dataclass, so the flag is passed explicitly rather than stashed on the spec: give the direction resolver an extra keyword and add the fallback before it returns `"question"`:

```python
def resolve_percent_base(spec, ..., banner: bool = False):
    ...
    # A banner classifier's segments may overlap, so they cannot be distributed
    # within a category — that direction assumes the segments partition the
    # sample. Fall back to the classifier direction. (spec 2026-08-02 §2.4)
    if direction == "question" and banner:
        return "classifier"
```

Pass `banner=bool(_banner_masks(spec, data, model))` from each engine call site that resolves the direction. Keep the existing default so every current caller is unchanged.

- [ ] **Step 4: Hide the control in the UI**

In `web/src/components/wizard/StepConfigure.tsx`, use the `banner` flag added in Task 9 — no inference needed:

```tsx
// A banner classifier's segments may overlap, so neither a second classifier nor
// the "each category" direction applies. (spec 2026-08-02 §2.4, §2.5)
const isBannerClassifier = variables.some(
  (v) => v.name === chart.classifying_var && v.banner === true
);
```

Use `isBannerClassifier` to skip rendering the `classifying_var_2` field and to drop the `"question"` option from the `percent_base` select.

- [ ] **Step 5: Run everything**

Run: `.venv/bin/python -m pytest tests/suite tests/rb -q && cd web && npx tsc --noEmit -p tsconfig.app.json`
Expected: all pass, TSC clean.

- [ ] **Step 6: Commit**

```bash
git add src/reportbuilder/stats/engine.py src/reportbuilder/stats/percent_base.py web/src/components/wizard/StepConfigure.tsx tests/suite/unit/stats/test_banner_classifier.py
git commit -m "feat: guard banner classifier against unsupported combinations"
```

---

### Task 11: End-to-end equivalence on the customer fixtures (spec §4)

The property the whole design exists to guarantee: both customer exports offer the same classifier.

**Files:**
- Test: `tests/suite/integration/test_classifier_encodings.py` (create)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Write the test**

Create `tests/suite/integration/test_classifier_encodings.py`:

```python
"""Both Erisan exports must offer a working path classifier, by whichever encoding
they happen to use. Skipped when the client materials are absent (gitignored IPR).
(spec 2026-08-02 §4)"""
from __future__ import annotations

import pathlib

import pytest

from reportbuilder.api.model_loader import df_model_for_material
from reportbuilder.ingest.multi_group import member_masks, near_partition
from reportbuilder.store.memory_client import InMemoryDataHiveClient

_STORE = pathlib.Path("work/demo-store")


def _load(mid):
    if not (_STORE / "materials" / f"{mid}.sav").exists():
        pytest.skip(f"{mid} not available locally")
    return df_model_for_material(mid, InMemoryDataHiveClient(storage_dir=str(_STORE)))


@pytest.mark.parametrize("mid", ["mat-erisan", "mat-erisan2"])
def test_export_offers_a_path_classifier(mid):
    df, model = _load(mid)
    # string encoding
    string_ok = model.variables["var214"].measurement == "categorical"
    # indicator encoding
    banner_ok = any(
        q.kind == "multi"
        and (masks := member_masks(df, q.variables)) is not None
        and near_partition(masks, len(df))
        for q in model.questions
    )
    assert string_ok or banner_ok, f"{mid} offers no path classifier"


def test_var214_is_a_two_value_categorical_in_both_exports():
    for mid in ("mat-erisan", "mat-erisan2"):
        df, model = _load(mid)
        from reportbuilder.ingest.sav_reader import string_categories
        assert string_categories(df["var214"]) == ("Pakkausilme 1", "Pakkausilme 2")


def test_both_exports_agree():
    """The correctness property: the two exports differ only in whether the
    indicator columns carry value labels, and must not behave differently."""
    _d1, m1 = _load("mat-erisan")
    _d2, m2 = _load("mat-erisan2")
    assert m1.variables["var214"].measurement == m2.variables["var214"].measurement
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/suite/integration/test_classifier_encodings.py -q -rs`
Expected: PASS (or SKIP without the materials).

- [ ] **Step 3: Manual check in the running app**

Start the stack, open `case-erisan` and `case-erisan2`, and confirm the Classifying variable picker lists "Pakkausilme 1 tai 2" and "Polku". Pick each and confirm the chart splits into two segments with sensible bases.

```bash
NSIGHT_DEMO=1 NSIGHT_DEMO_DIR=work/demo-store NSIGHT_RELOAD=1 NSIGHT_PORT=8200 \
  .venv/bin/python -m reportbuilder.api.server &
cd web && npx vite --port 5173 --strictPort
```

- [ ] **Step 4: Commit**

```bash
git add tests/suite/integration/test_classifier_encodings.py
git commit -m "test: both Erisan exports offer a working path classifier"
```

---

## Self-review notes

- **Spec coverage:** §0 → Task 1. §1.1 → Tasks 2–3. §1.2 → Tasks 4–5. §2.1 → Task 6. §2.2 → Task 7. §2.3 → Task 8. §2.4 → Task 9. §2.5 → Task 10. §4 → Task 11 plus per-task tests.
- **Deliberately deferred:** cross-tabbing a banner classifier with a second classifier (guarded with a clear error in Task 10, per spec §2.5).
- **Risk to watch in Task 1:** an existing test may assert the old, wrong Total. Read it before changing the expected number; if its classifier covers every respondent, the number should NOT change and something else is wrong.
- **Risk to watch in Task 7:** `apply_grouping_override` is also called without a DataFrame (`report_migration.py`, `_load_singles`). Those paths keep today's behaviour by design — indicator families cannot be detected from metadata alone.
