# Separate Classifier Panels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one slide show a question split by two background variables *side by side* (gender in one panel, age group in the other) instead of only crossed, and make the second-classifier control always reachable.

**Architecture:** A new `xtab_layout` value, `"separate"`, switches the engine from combo segmentation to mask segmentation — one mask per group of each variable, each an ordinary cut with its own base. Segments carry `segment_primary = <source variable label>`, the existing hook renderers group panels by, so panels come out one per *variable*. Two new panel renderers (clustered, stacked) draw them.

**Tech Stack:** Python 3.13, pandas, matplotlib (Agg), python-pptx, pytest; React 19 + TypeScript + Vite for the config UI.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-04-separate-classifier-panels-design.md`. Read it before Task 1.
- Backend tests: `.venv/bin/python -m pytest tests/suite -q` (must stay green: 1874 passed, 15 skipped as of `fa09d6f`).
- Frontend typecheck: `cd web && npx tsc -b` (must exit 0).
- `auto` must never resolve to `separate`. Deploying this changes no existing slide.
- `base_n["Total"]` must always be present — `elements.py:120` indexes it directly and the `KeyError` is deliberately uncaught.
- Never emit a bare `"Total"` **segment** in separate mode; per-panel totals are named `"<variable label> · Total"`.
- Separate mode applies to **single, multi and summary-statistic** paths. Batteries and comparison questions keep today's behaviour.
- Two variables only. A list of N classifiers is explicitly out of scope.
- Follow the house comment style: explain *why*, cite spec dates, keep comments at the density of the surrounding code.

## Traceability to the original report

| Reported | Covered by |
|---|---|
| "samassa kuvassa voi olla data splitattuna useamman taustamuuttujan suhteen … sukupuoli ja ikäryhmät molemmat classifying variablena" | Tasks 1–8: two classifying variables render together in one image, one panel each. Beyond two is deliberately out of scope per the design decision taken 2026-08-04. |
| "toinen tulee alisteiseksi toiselle. Tämä voisi olla hyvä olla myös erillään" | Tasks 1–8 (`separate` layout) and Task 9 (the option in the config UI). Nested stays available and stays the default. |
| "Horizontal barissa ei mulla anna valita enää toista classifying muuttujaa" | Task 9: the field is never silently removed again — disabled with a reason when there is no primary, and enabled (not hidden) for a banner primary. |

---

### Task 1: `_separate_masks` — the segmentation helper

**Files:**
- Modify: `src/reportbuilder/stats/engine.py:35-99` (`_banner_masks`, `_classifier_masks`)
- Create (in the same module, after `_classifier_masks`): `_classifier_label`, `_separate_layout`, `_separate_masks`
- Test: `tests/suite/unit/stats/test_separate_masks.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `_separate_layout(spec) -> bool` — True when `spec.options["xtab_layout"] == "separate"` **and** both classifiers are set.
  - `_classifier_label(cv: str, model: QuestionModel) -> str` — display label for a classifier name or banner qid.
  - `_separate_masks(spec, data, model) -> tuple[dict[str, pd.Series], dict[str, str]] | None` — `(masks, primary)`. `masks` maps segment label → boolean mask, ordered: variable 1's groups, variable 1's Total (only when `resolve_show_total` is true), then variable 2's the same way. `primary` maps every segment label → its source variable's label. Returns `None` when `_separate_layout` is False.
  - `_banner_masks(spec, data, model, var_name=None)` and `_classifier_masks(spec, data, model, var_name=None)` — `var_name` defaults to `spec.classifying_var`.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/stats/test_separate_masks.py`:

```python
"""Mask segmentation for the SEPARATE two-variable layout.

Two background variables shown side by side are NOT crossed: each variable
contributes its own groups as ordinary cuts of the sample, so a respondent counts
once in the gender panel and once in the age panel — never in a product of the
two. (spec 2026-08-04-separate-classifier-panels)
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup():
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Identifioitko itsesi…?", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Naiseksi"), ValueLabel(2.0, "Mieheksi")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "18-34-vuotiaat"),
                                 ValueLabel(2.0, "35-54-vuotiaat"),
                                 ValueLabel(3.0, "55-69-vuotiaat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0, 5.0] * 24,
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 40,
    })
    return model, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_separate_layout_needs_the_option_and_both_variables():
    assert engine._separate_layout(_spec()) is True
    assert engine._separate_layout(_spec(options={"xtab_layout": "auto"})) is False
    assert engine._separate_layout(_spec(options={})) is False
    assert engine._separate_layout(_spec(classifying_var_2=None)) is False


def test_masks_are_the_sum_of_both_variables_groups_not_the_product():
    model, df = _setup()
    masks, _primary = engine._separate_masks(_spec(), df, model)
    assert list(masks) == [
        "Identifioitko itsesi…? · Naiseksi",
        "Identifioitko itsesi…? · Mieheksi",
        "Ikäryhmät · 18-34-vuotiaat",
        "Ikäryhmät · 35-54-vuotiaat",
        "Ikäryhmät · 55-69-vuotiaat",
    ]  # 2 + 3, never 2 x 3


def test_each_mask_is_that_groups_own_rows():
    model, df = _setup()
    masks, _primary = engine._separate_masks(_spec(), df, model)
    assert int(masks["Identifioitko itsesi…? · Naiseksi"].sum()) == 60
    assert int(masks["Ikäryhmät · 18-34-vuotiaat"].sum()) == 40


def test_primary_maps_every_segment_to_its_source_variable():
    model, df = _setup()
    masks, primary = engine._separate_masks(_spec(), df, model)
    assert set(primary) == set(masks)
    assert primary["Identifioitko itsesi…? · Naiseksi"] == "Identifioitko itsesi…?"
    assert primary["Ikäryhmät · 55-69-vuotiaat"] == "Ikäryhmät"


def test_show_total_on_adds_one_total_mask_per_variable():
    model, df = _setup()
    masks, primary = engine._separate_masks(_spec(show_total="on"), df, model)
    assert "Identifioitko itsesi…? · Total" in masks
    assert "Ikäryhmät · Total" in masks
    assert "Total" not in masks, "no bare Total segment — it is not a panel"
    assert primary["Ikäryhmät · Total"] == "Ikäryhmät"
    assert int(masks["Ikäryhmät · Total"].sum()) == 120


def test_show_total_off_adds_none():
    model, df = _setup()
    masks, _primary = engine._separate_masks(_spec(show_total="off"), df, model)
    assert not [s for s in masks if s.endswith(" · Total")]


def test_two_variables_sharing_a_group_label_stay_distinct():
    model, df = _setup()
    model.variables["age"] = Variable(
        name="age", label="Ikäryhmät", measurement="categorical",
        value_labels=(ValueLabel(1.0, "Naiseksi"),) + model.variables["age"].value_labels[1:],
        missing_values=frozenset())
    masks, _primary = engine._separate_masks(_spec(), df, model)
    assert "Identifioitko itsesi…? · Naiseksi" in masks
    assert "Ikäryhmät · Naiseksi" in masks


def test_returns_none_when_not_separate():
    model, df = _setup()
    assert engine._separate_masks(_spec(options={"xtab_layout": "auto"}), df, model) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_separate_masks.py -q`
Expected: FAIL — `AttributeError: module 'reportbuilder.stats.engine' has no attribute '_separate_layout'`

- [ ] **Step 3: Give `_banner_masks` and `_classifier_masks` a variable-name parameter**

In `src/reportbuilder/stats/engine.py`, change the two signatures and their `cv` lookups. `_banner_masks` also **loses** its `classifying_var_2` guard — that check moves to `compute()` in Task 5, because once this function can be asked about the *second* variable it would otherwise raise on every separate-mode chart.

```python
def _banner_masks(spec, data: pd.DataFrame, model: QuestionModel, var_name=None):
    """Segment masks when a classifier names a near-partition MULTI question.

    Resolution is variable-name-first — a real DataFrame column or model variable
    always wins — so this only fires for a qid. Returns None otherwise, leaving
    every existing classifier untouched. `var_name` defaults to the PRIMARY
    classifier; the separate layout asks about the second one too, so this is a
    pure resolver — the "a banner cannot be crossed" guard lives in compute().
    (spec 2026-08-02 §2.4, 2026-08-04)"""
    from reportbuilder.ingest.multi_group import member_masks, near_partition

    cv = var_name or getattr(spec, "classifying_var", None)
    if not cv or cv in data.columns or cv in model.variables:
        return None
    q = next((x for x in model.questions
              if x.qid == cv and x.kind == "multi"), None)
    if q is None:
        return None
    masks = member_masks(data, q.variables)
    if not masks or not near_partition(masks, len(data)):
        return None
    return {model.variable(v).label: m for v, m in zip(q.variables, masks)}


def _classifier_masks(spec, data: pd.DataFrame, model: QuestionModel, var_name=None):
    """One boolean mask per segment for ANY classifier form, or None.

    Unifies the three shapes a classifier can take — a banner qid (indicator
    columns), a coded STRING column, and a value-labelled numeric column — so paths
    that segment by hand (the batteries, the separate layout) don't each
    reimplement the resolution. `var_name` defaults to the PRIMARY classifier.
    Ordered: banner, then the column's own values. (spec 2026-08-02 §2.4)"""
    cv = var_name or getattr(spec, "classifying_var", None)
    banner = _banner_masks(spec, data, model, cv)
    if banner:
        return banner
    if not cv or cv not in data.columns:
        return None
    col = data[cv]
    ...  # body unchanged below this point, using `cv`
```

Keep the rest of `_classifier_masks` exactly as it is — it already uses `cv`.

- [ ] **Step 4: Add the three new helpers**

Immediately after `_classifier_masks`:

```python
def _classifier_label(cv: str, model: QuestionModel) -> str:
    """Display label for a classifier — a variable's label, a banner qid's question
    text, else the raw name. Used to prefix separate-layout segments so the two
    variables' groups can never collide. (spec 2026-08-04)"""
    v = model.variables.get(cv)
    if v is not None and (v.label or "").strip():
        return v.label
    q = next((x for x in model.questions if x.qid == cv), None)
    if q is not None and (q.text or "").strip():
        return q.text
    return cv


def _separate_layout(spec) -> bool:
    """True when the author asked for the two classifiers SIDE BY SIDE rather than
    crossed. Needs both variables — one classifier has nothing to sit beside.
    (spec 2026-08-04-separate-classifier-panels)"""
    opts = getattr(spec, "options", None) or {}
    return (opts.get("xtab_layout") == "separate"
            and bool(getattr(spec, "classifying_var", None))
            and bool(getattr(spec, "classifying_var_2", None)))


def _separate_masks(spec, data: pd.DataFrame, model: QuestionModel):
    """(masks, primary) for the SEPARATE layout, or None when it isn't asked for.

    Each variable contributes its own groups as ordinary cuts — no crossing, so a
    respondent counts once per variable and the thin cells a cross-tab produces
    (a 4-person gender group times three age bands) never arise. Segment labels are
    "<variable> · <group>" so two variables sharing a group label stay distinct, and
    `primary` maps each segment to its SOURCE VARIABLE — the hook the renderer
    groups panels by, which is what makes one panel come out per variable.

    A per-variable "<variable> · Total" mask is added when the Total series is on;
    a bare "Total" segment is never emitted, because it belongs to no panel.
    (spec 2026-08-04-separate-classifier-panels)"""
    if not _separate_layout(spec):
        return None
    want_total = resolve_show_total(spec, True)
    masks: dict[str, pd.Series] = {}
    primary: dict[str, str] = {}
    for cv in (spec.classifying_var, spec.classifying_var_2):
        groups = _classifier_masks(spec, data, model, cv)
        if not groups:
            continue                       # stale/empty variable → its panel is dropped
        label = _classifier_label(cv, model)
        for group_label, m in groups.items():
            key = f"{label} · {group_label}"
            masks[key] = m
            primary[key] = label
        if want_total:
            any_group = pd.Series(False, index=data.index)
            for m in groups.values():
                any_group = any_group | m
            key = f"{label} · Total"
            masks[key] = any_group
            primary[key] = label
    return (masks, primary) if masks else None
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_separate_masks.py -q`
Expected: PASS (8 passed)

- [ ] **Step 6: Run the whole suite — the signature change touches shared helpers**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: PASS. One deliberate regression is possible: any test asserting that `_banner_masks` raises on a banner + second classifier. That guard moves to `compute()` in Task 5 — if such a test exists, mark it `@pytest.mark.xfail(reason="guard moves to compute() in Task 5")` and remove the marker in Task 5.

- [ ] **Step 7: Commit**

```bash
git add src/reportbuilder/stats/engine.py tests/suite/unit/stats/test_separate_masks.py
git commit -m "feat(stats): _separate_masks — uncrossed segmentation for two classifiers"
```

---

### Task 2: Separate mode in `_single`

**Files:**
- Modify: `src/reportbuilder/stats/engine.py:465-500` (segmentation branch), `:528-547` (percent_base), `:609-624` (bar sort), `:660-668` (result)
- Test: `tests/suite/unit/stats/test_separate_single.py`

**Interfaces:**
- Consumes: `_separate_masks`, `_separate_layout` from Task 1.
- Produces: a `SeriesResult` whose `segments` are the separate-mode labels, `segment_primary` maps each to its variable, and `base_n["Total"]` is the overall base.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/stats/test_separate_single.py`:

```python
"""A single question split by two background variables SIDE BY SIDE."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import QuestionModel, Question, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup():
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Keski"),
                                 ValueLabel(3.0, "Vanhat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0, 5.0] * 24,
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 40,
    })
    return model, question, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_segments_are_the_sum_of_both_variables_groups():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert list(r.segments) == [
        "Sukupuoli · Nainen", "Sukupuoli · Mies",
        "Ikäryhmät · Nuoret", "Ikäryhmät · Keski", "Ikäryhmät · Vanhat",
    ]


def test_segment_primary_is_the_source_variable():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert r.segment_primary["Sukupuoli · Nainen"] == "Sukupuoli"
    assert r.segment_primary["Ikäryhmät · Vanhat"] == "Ikäryhmät"
    assert len(set(r.segment_primary.values())) == 2, "one panel per VARIABLE"


def test_bases_are_per_group_and_total_survives():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert r.base_n["Sukupuoli · Nainen"] == 60
    assert r.base_n["Ikäryhmät · Nuoret"] == 40
    assert r.base_n["Total"] == 120, "the N footer indexes base_n['Total'] directly"


def test_each_group_sums_to_100_percent():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    for seg in r.segments:
        total = sum((r.cell(c, seg).pct or 0.0) for c in r.categories)
        assert abs(total - 100.0) < 1.5, f"{seg} should be a full distribution"


def test_percent_base_is_forced_to_the_classifier_direction():
    model, question, df = _setup()
    r = engine.compute(question, _spec(percent_base="question"), df, model)
    for seg in r.segments:
        total = sum((r.cell(c, seg).pct or 0.0) for c in r.categories)
        assert abs(total - 100.0) < 1.5


def test_crossed_layout_is_untouched():
    model, question, df = _setup()
    r = engine.compute(question, _spec(options={"xtab_layout": "auto"}), df, model)
    assert len([s for s in r.segments if s != "Total"]) == 6, "2 x 3 combos"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_separate_single.py -q`
Expected: FAIL — segments are the six crossed combos.

- [ ] **Step 3: Add the segmentation branch in `_single`**

In `_single`, immediately before `banner = _banner_masks(spec, data, model)` (currently line 473), add:

```python
    separate = _separate_masks(spec, data, model)
```

Then make it the first branch of the `if banner is not None:` chain:

```python
    if separate is not None:                         # two classifiers SIDE BY SIDE
        sep_masks, sep_primary = separate
        bases = segment_bases(data, var, missing_override=eff, seg_masks=sep_masks)
        counts = aggregate_counts(data, var.name, seg_masks=sep_masks)
        segments = tuple(sep_masks)                  # no bare "Total": it is no panel
    elif banner is not None:                         # banner: indicator columns
        ...
```

`banner` and `seg_series` must not also be computed for a separate chart, so guard their assignment:

```python
    banner = None if separate is not None else _banner_masks(spec, data, model)
    seg_series, ordered = ((None, None) if (banner or separate is not None)
                           else _combo_segmentation(spec, data))
```

- [ ] **Step 4: Force the percentage direction**

In the `pb` chain (currently line 535), add a branch before the stacked one:

```python
    pb = getattr(spec, "percent_base", "auto")
    if not (spec.classifying_var and real_segs):
        pb = "classifier"
    elif separate is not None:
        # The segments come from two UNRELATED variables, so "within each answer
        # category" would distribute across cuts that share no denominator and
        # print labels that don't sum. Each panel is a plain per-group
        # distribution. (spec 2026-08-04)
        pb = "classifier"
    elif spec.chart_type in _STACKED_BAR_TYPES:
        ...
```

- [ ] **Step 5: Sort bars within each panel, not across panels**

Replace the reorder block at line 613 (`if _bars_are_segments and spec.sort.basis in (...)`) body with a panel-aware version:

```python
    if _bars_are_segments and spec.sort.basis in ("topbox_sum", "top3_sum"):
        n_top = 3 if spec.sort.basis == "top3_sum" else 2
        top_cats = _top_scale_categories(var, categories, n_top)
        if top_cats:
            def _topbox(seg: str) -> float:
                return sum((cells.get((c, seg)) or Cell(pct=None)).pct or 0.0
                           for c in top_cats)

            reals = [s for s in segments if s != "Total"]
            if separate is not None:
                # Sort WITHIN each panel. A global sort would interleave the two
                # variables' segments and destroy the panel grouping. (2026-08-04)
                _sp = separate[1]
                order: list[str] = []
                for panel in dict.fromkeys(_sp[s] for s in reals):
                    order += sorted((s for s in reals if _sp[s] == panel),
                                    key=_topbox, reverse=spec.sort.descending)
                reals = order
            else:
                reals.sort(key=_topbox, reverse=spec.sort.descending)
            segments = tuple(reals) + (("Total",) if "Total" in segments else ())
```

- [ ] **Step 6: Attach `segment_primary` to the result**

At the `return SeriesResult(...)` (line 660):

```python
    return SeriesResult(categories=tuple(categories), segments=segments, cells=cells,
                        base_n={s: denom.get(s, 0) for s in segments},
                        statistic=spec.statistic, caption=scale_caption,
                        row_summaries=row_summaries,
                        row_summary_keys=tuple(statements),
                        segment_primary=(separate[1] if separate is not None else None))
```

`base_n` is built from `denom`, which is built from `bases` — and `bases` already carries `"Total"` from `segment_bases`. Add it explicitly so the N footer keeps working even though `"Total"` is not in `segments`:

```python
    base_n = {s: denom.get(s, 0) for s in segments}
    base_n.setdefault("Total", bases.get("Total", 0))
```

and pass `base_n=base_n`.

- [ ] **Step 7: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_separate_single.py -q`
Expected: PASS (6 passed)

- [ ] **Step 8: Run the suite**

Run: `.venv/bin/python -m pytest tests/suite -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/reportbuilder/stats/engine.py tests/suite/unit/stats/test_separate_single.py
git commit -m "feat(stats): separate two-classifier layout for single questions"
```

---

### Task 3: Separate mode in `_multi`

**Files:**
- Modify: `src/reportbuilder/stats/engine.py:702-782` (`_multi`)
- Test: `tests/suite/unit/stats/test_separate_multi.py`

**Interfaces:**
- Consumes: `_separate_masks` (Task 1).
- Produces: same `SeriesResult` shape as Task 2, for a multi question.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/stats/test_separate_multi.py`:

```python
"""A MULTI question split by two background variables side by side."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _member(name, label):
    return Variable(name=name, label=label, measurement="categorical",
                    value_labels=(ValueLabel(0.0, "Unchecked"), ValueLabel(1.0, "Checked")),
                    missing_values=frozenset())


def _setup():
    m1, m2 = _member("m1", "Kanava A"), _member("m2", "Kanava B")
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Vanhat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"m1": m1, "m2": m2, "sex": sex, "age": age},
                          questions=[])
    q = Question(qid="mm", kind="multi", variables=("m1", "m2"), text="Kanavat")
    df = pd.DataFrame({
        "m1": [1.0, 0.0] * 40,
        "m2": [1.0, 1.0, 0.0, 0.0] * 20,
        "sex": ([1.0] * 40) + ([2.0] * 40),
        "age": [1.0, 2.0] * 40,
    })
    return model, q, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="mm", chart_type="horizontal_bar", statistic="pct",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_multi_segments_are_the_sum_not_the_product():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert list(r.segments) == [
        "Sukupuoli · Nainen", "Sukupuoli · Mies",
        "Ikäryhmät · Nuoret", "Ikäryhmät · Vanhat",
    ]
    assert r.base_n["Total"] == 80


def test_multi_segment_primary_is_the_variable():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert len(set(r.segment_primary.values())) == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_separate_multi.py -q`
Expected: FAIL — four crossed combos plus `"Total"`.

- [ ] **Step 3: Implement**

In `_multi`, replace the `banner`/`seg_series` setup (currently lines 723-724) and add a branch as the first case of the existing chain:

```python
    separate = _separate_masks(spec, data, model)
    banner = None if separate is not None else _banner_masks(spec, data, model)
    seg_series, ordered = ((None, None) if (banner or separate is not None)
                           else _combo_segmentation(spec, data))
    seg_codes: list[str] = []
    seg_mask: dict[str, "pd.Series"] = {}
    if separate is not None:
        for label, m in separate[0].items():
            seg_codes.append(label)
            seg_mask[label] = m
    elif banner is not None:
        ...
```

Then make the "Total" segment conditional and attach `segment_primary`:

```python
    segments = tuple(seg_codes) if separate is not None else tuple(seg_codes) + ("Total",)
```

and at the return:

```python
    return SeriesResult(categories=categories, segments=segments, cells=cells,
                        base_n=seg_base, statistic=spec.statistic,
                        segment_primary=(separate[1] if separate is not None else None))
```

`seg_base` already sets `seg_base["Total"] = base_total`, so the N footer keeps working.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_separate_multi.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the suite and commit**

```bash
.venv/bin/python -m pytest tests/suite -q
git add src/reportbuilder/stats/engine.py tests/suite/unit/stats/test_separate_multi.py
git commit -m "feat(stats): separate two-classifier layout for multi questions"
```

---

### Task 4: Separate mode in `_summary`

**Files:**
- Modify: `src/reportbuilder/stats/engine.py:270-330` (`_summary`)
- Test: `tests/suite/unit/stats/test_separate_summary.py`

**Interfaces:**
- Consumes: `_separate_masks` (Task 1).
- Produces: a one-category `SeriesResult` with the same segment/primary contract.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/stats/test_separate_summary.py`:

```python
"""A MEAN chart split by two background variables side by side."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup():
    q = Variable(name="q", label="Arvosana", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Vanhat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Arvosana")
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0] * 20,
        "sex": ([1.0] * 40) + ([2.0] * 40),
        "age": [1.0, 2.0] * 40,
    })
    return model, question, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="mean",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_summary_segments_are_the_sum_not_the_product():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert list(r.segments) == [
        "Sukupuoli · Nainen", "Sukupuoli · Mies",
        "Ikäryhmät · Nuoret", "Ikäryhmät · Vanhat",
    ]
    assert r.base_n["Total"] == 80
    assert len(set(r.segment_primary.values())) == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_separate_summary.py -q`
Expected: FAIL — crossed combos.

- [ ] **Step 3: Implement**

`_summary` represents its segmentation as a key **series** (its statistic reads one value per segment). Separate-mode masks are disjoint within a variable but a respondent appears in *both* variables' masks, so a single key series cannot express them. Compute the per-segment value from the masks directly instead. Replace the segmentation preamble (currently lines 281-300) with:

```python
    separate = _separate_masks(spec, data, model)
    banner = None if separate is not None else _banner_masks(spec, data, model)
    seg_series, ordered = ((None, None) if (banner or separate is not None)
                           else _combo_segmentation(spec, data))
    usable_clf = spec.classifying_var and spec.classifying_var in data.columns
    if separate is not None:
        # A respondent belongs to a group of BOTH variables, so one key series
        # cannot express the segmentation — take each segment's rows from its own
        # mask. Cell shape mirrors the classifier branch below. (spec 2026-08-04)
        sep_masks, sep_primary = separate
        bases = segment_bases(data, var, seg_masks=sep_masks)
        cells: dict[tuple[str, str], Cell] = {}
        for seg, m in sep_masks.items():
            v = summary_value(data.loc[m, var.name], var, fmt, stat)
            if stat.name == "mean":
                cells[(label, seg)] = Cell(pct=None, count=None, mean=v)
            else:
                cells[(label, seg)] = Cell(pct=None, count=None, mean=None,
                                           extra=((stat.name, v),))
        return SeriesResult(categories=(label,), segments=tuple(sep_masks),
                            cells=cells, base_n=bases, statistic=stat.name,
                            segment_primary=sep_primary)
    if banner is not None or seg_series is not None or usable_clf:
        ...
```

`bases` from `segment_bases(seg_masks=…)` already includes `"Total"`, so the N
footer keeps working even though `"Total"` is not among the segments. Note the
result uses `statistic=stat.name`, matching the existing return at line 328 — not
`spec.statistic`, which for the summary family is the same string but is read from
a different place.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_separate_summary.py -q`
Expected: PASS

- [ ] **Step 5: Run the suite and commit**

```bash
.venv/bin/python -m pytest tests/suite -q
git add src/reportbuilder/stats/engine.py tests/suite/unit/stats/test_separate_summary.py
git commit -m "feat(stats): separate two-classifier layout for summary statistics"
```

---

### Task 5: `compute()` — skip relabelling, and move the banner guard

**Files:**
- Modify: `src/reportbuilder/stats/engine.py:911-979` (`compute`)
- Test: `tests/suite/unit/stats/test_separate_compute.py`

**Interfaces:**
- Consumes: `_separate_layout`, `_banner_masks` (Task 1).
- Produces: `compute()` leaves separate-mode labels untouched and raises the banner-crossing `ValueError` only for crossed layouts.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/stats/test_separate_compute.py`:

```python
"""compute() must not relabel separate-mode segments, and the banner guard must
only fire for CROSSED layouts."""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup_banner():
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    p1 = Variable(name="p1", label="Polku 1", measurement="categorical",
                  value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                  missing_values=frozenset())
    p2 = Variable(name="p2", label="Polku 2", measurement="categorical",
                  value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                  missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Vanhat")),
                   missing_values=frozenset())
    polku = Question(qid="polku", kind="multi", variables=("p1", "p2"), text="Polku")
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    model = QuestionModel(variables={"q": q, "p1": p1, "p2": p2, "age": age},
                          questions=[polku, question])
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0] * 20,
        "p1": ([1.0] * 40) + ([0.0] * 40),
        "p2": ([0.0] * 40) + ([1.0] * 40),
        "age": [1.0, 2.0] * 40,
    })
    return model, question, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="polku", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(), options={})
    base.update(kw)
    return ChartSpec(**base)


def test_banner_crossed_with_a_second_variable_still_raises():
    model, question, df = _setup_banner()
    with pytest.raises(ValueError, match="banner"):
        engine.compute(question, _spec(options={"xtab_layout": "auto"}), df, model)


def test_banner_is_allowed_in_separate_mode():
    model, question, df = _setup_banner()
    r = engine.compute(question, _spec(options={"xtab_layout": "separate"}), df, model)
    assert list(r.segments) == [
        "Polku · Polku 1", "Polku · Polku 2",
        "Ikäryhmät · Nuoret", "Ikäryhmät · Vanhat",
    ]


def test_separate_labels_survive_compute_untouched():
    model, question, df = _setup_banner()
    r = engine.compute(question, _spec(options={"xtab_layout": "separate"}), df, model)
    assert all(" · " in s for s in r.segments)
    assert not any("|" in s for s in r.segments), "no combo relabelling ran"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_separate_compute.py -q`
Expected: the separate-mode tests FAIL (labels mangled by `_relabel_combo_segments`); the crossed test FAILS too, because Task 1 removed the guard.

- [ ] **Step 3: Add the guard and skip relabelling**

In `compute()`, right after the text-not-chartable check (line 929), add:

```python
    # Crossing a BANNER classifier (segments from separate columns, possibly
    # overlapping) with a second variable has no defensible base. The SEPARATE
    # layout never crosses, so it is allowed. This guard lived inside
    # _banner_masks until that became a pure resolver. (spec 2026-08-02 §2.5,
    # 2026-08-04)
    cv2 = getattr(spec, "classifying_var_2", None)
    if cv2 and not _separate_layout(spec) and _banner_masks(spec, data, model):
        raise ValueError(
            f"'{spec.classifying_var}' is a banner classifier (its segments come "
            f"from separate columns and may overlap) and cannot be combined with a "
            f"second classifying variable ('{cv2}'). Set the two-variable layout to "
            f"Separate panels, remove the second classifier, or classify by an "
            f"ordinary variable instead."
        )
```

Then guard the relabel branches (line 970):

```python
    # Display segment codes as the classifying variable's value labels (a cross-tab
    # of two classifiers joins both labels: "Male · 25-34 vuotias"). The SEPARATE
    # layout already emits display labels, and _relabel_combo_segments would split
    # them on "|" and mangle them. (2026-08-04)
    if _separate_layout(spec):
        pass
    elif spec.classifying_var and cv2:
        result = _relabel_combo_segments(result, model, spec.classifying_var, cv2)
    elif spec.classifying_var:
        result = _relabel_segments(result, model, spec.classifying_var)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_separate_compute.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Remove any xfail marker added in Task 1, run the suite, commit**

```bash
.venv/bin/python -m pytest tests/suite -q
git add src/reportbuilder/stats/engine.py tests/suite/unit/stats/test_separate_compute.py
git commit -m "feat(stats): allow a banner classifier in the separate layout"
```

---

### Task 6: Config schema — the fourth option, on all four chart types

**Files:**
- Modify: `src/reportbuilder/render/config_schema.py:181-198` (`xtab_layout_field`, `clustered_bar_schema`), `:233-249` (`stacked_schema`)
- Test: `tests/suite/unit/render/test_config_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `xtab_layout` present in all four two-classifier schemas, with a `separate` option.

- [ ] **Step 1: Write the failing test**

Append to `tests/suite/unit/render/test_config_schema.py`:

```python
def test_xtab_layout_offers_separate_panels():
    from reportbuilder.render.config_schema import xtab_layout_field
    values = [v for v, _label in xtab_layout_field().options]
    assert values == ["auto", "grouped", "small_multiples", "separate"]


def test_all_two_classifier_schemas_carry_the_layout_control():
    from reportbuilder.render.config_schema import clustered_bar_schema, stacked_schema
    for schema in (clustered_bar_schema(), stacked_schema(),
                   stacked_schema(with_row_summary=True)):
        keys = [f.key for f in schema]
        assert "classifying_var_2" in keys
        assert "xtab_layout" in keys, "a chart with two classifiers can choose the layout"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/render/test_config_schema.py -q`
Expected: FAIL — `separate` missing, and `xtab_layout` absent from `stacked_schema`.

- [ ] **Step 3: Implement**

```python
def xtab_layout_field() -> ConfigField:
    return ConfigField(
        "xtab_layout", "select", "Two-variable layout",
        options=(("auto", "Automatic"), ("grouped", "Grouped bars"),
                 ("small_multiples", "Small multiples"),
                 ("separate", "Separate panels (one per variable)")),
        default="auto",
        help=("With a second classifying variable: 'Grouped bars' pulls the bars apart "
              "into groups by the first variable; 'Small multiples' draws one panel per "
              "value of the first variable; 'Separate panels' does NOT cross them — one "
              "panel per variable, each an ordinary split. 'Automatic' groups when it "
              "fits, else panels, and never chooses Separate on its own."),
    )
```

In `stacked_schema`, add `xtab_layout_field()` right after `classifying_var_2_field()`.

- [ ] **Step 4: Run the test to verify it passes, then the suite, then commit**

```bash
.venv/bin/python -m pytest tests/suite/unit/render/test_config_schema.py -q
.venv/bin/python -m pytest tests/suite -q
git add src/reportbuilder/render/config_schema.py tests/suite/unit/render/test_config_schema.py
git commit -m "feat(render): Separate panels option, and the layout control on stacked charts"
```

---

### Task 7: Clustered panel renderer

**Files:**
- Modify: `src/reportbuilder/render/image/_mpl.py:126-138` (`new_figure_grid`), `src/reportbuilder/render/image/bars.py:397-418` (`_resolve_xtab_layout`), `:498-512` and `:575-582` (the two clustered builders)
- Create (in `bars.py`, next to `_render_small_multiples`): `_stack_panels`, `_render_variable_panels`
- Test: `tests/suite/integration/render/test_separate_panels.py`

**Interfaces:**
- Consumes: a `SeriesResult` with `segment_primary` mapping segments to variable labels (Tasks 2–4).
- Produces: `_stack_panels(cats: list[str]) -> bool`; `_render_variable_panels(ctx, cats, *, vertical: bool) -> None`; `new_figure_grid(ctx, n, *, tall_in=None, rows=1)`.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/integration/render/test_separate_panels.py`:

```python
"""Integration: two classifiers rendered as SEPARATE panels, one per variable."""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.render.image.bars import _stack_panels
from reportbuilder.stats.engine import compute

from suite._helpers import assert_single_picture, make_ctx


def _setup():
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Keski"),
                                 ValueLabel(3.0, "Vanhat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0, 5.0] * 24,
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 40,
    })
    return model, question, df


def _spec(chart_type, **kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type=chart_type, statistic="pct",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="slot1", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_stack_panels_rule():
    assert _stack_panels(["a", "b", "c"]) is False
    assert _stack_panels([f"c{i}" for i in range(7)]) is True, "more than 6 categories"
    assert _stack_panels(["a" * 15, "b"]) is True, "a label longer than 14 chars"


@pytest.mark.parametrize("chart_type", ["horizontal_bar", "vertical_bar"])
def test_separate_panels_render_one_picture(chart_type):
    model, question, df = _setup()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type), df, model)
    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)
    IMAGE_BUILDERS[chart_type](ctx)
    assert_single_picture(slide, slot)


def test_one_panel_per_variable_not_per_group():
    model, question, df = _setup()
    series = compute(question, _spec("horizontal_bar"), df, model)
    from reportbuilder.render.image.bars import _primary_groups
    groups = _primary_groups(series)
    assert [p for p, _segs in groups] == ["Sukupuoli", "Ikäryhmät"]
    assert [len(segs) for _p, segs in groups] == [2, 3], "each panel keeps its own groups"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/integration/render/test_separate_panels.py -q`
Expected: FAIL — `ImportError: cannot import name '_stack_panels'`

- [ ] **Step 3: Give `new_figure_grid` a `rows` parameter**

In `src/reportbuilder/render/image/_mpl.py`:

```python
def new_figure_grid(ctx, n: int, *, tall_in: float | None = None, rows: int = 1):
    """Figure with n subplots (shared y-axis), house style applied — for cross-tab
    SMALL MULTIPLES (one panel per primary classifier value) and for the SEPARATE
    layout (one panel per classifying VARIABLE). `rows` > 1 stacks the panels one
    above the other, which the separate layout uses when the category labels need
    the full width. (spec 2026-08-04)"""
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(tall_in or 4.5, ctx.slot.height / _EMU_PER_IN)
    fig = _new_agg_figure(w_in, h_in)
    cols = max(1, -(-n // max(1, rows)))          # ceil(n / rows)
    axes = fig.subplots(max(1, rows), cols, sharey=True, sharex=False)
    axes = [axes] if n <= 1 else list(np.ravel(axes))
    for extra in axes[n:]:                        # an odd count leaves a blank cell
        extra.set_visible(False)
    axes = axes[:n]
    fig.patch.set_facecolor(CREAM)
    for ax in axes:
        ax.set_facecolor(CREAM)
    return fig, axes
```

Add `import numpy as np` to `_mpl.py` if it is not already imported.

- [ ] **Step 4: Teach `_resolve_xtab_layout` about `separate`**

```python
    mode = (getattr(ctx.spec, "options", None) or {}).get("xtab_layout", "auto")
    if mode in ("grouped", "small_multiples", "separate"):
        return mode
```

- [ ] **Step 5: Add `_stack_panels` and `_render_variable_panels`**

In `bars.py`, after `_render_small_multiples`:

```python
def _stack_panels(cats: list[str]) -> bool:
    """True when SEPARATE panels should sit one above the other rather than side by
    side. Side-by-side halves each panel's width, so the same label pressure
    _should_orient_horizontal measures decides it. (spec 2026-08-04)"""
    return len(cats) > 6 or any(len(c) > 14 for c in cats)


def _render_variable_panels(ctx, cats, *, vertical: bool) -> None:
    """SEPARATE layout: one panel per classifying VARIABLE, each an ordinary
    clustered bar of (answer categories x that variable's groups).

    Unlike small multiples the panels do NOT share a series axis — panel 1 shows
    gender's groups, panel 2 age's — so each carries its own legend and its own
    colours, restarting at index 0. A shared ramp would imply "Nainen" and
    "Nuoret" correspond. The VALUE axis is shared so the bars stay comparable.
    (spec 2026-08-04-separate-classifier-panels)"""
    from matplotlib.patches import Patch
    series = ctx.series
    groups = _primary_groups(series)
    _c, _s, data = series_values(series)
    n_cat = len(cats)
    rows = 2 if _stack_panels(list(cats)) else 1
    all_vals = [v for _p, segs in groups for s in segs for v in data.get(s, [])
                if v is not None]
    max_val = max(all_vals, default=0.0)
    tall = n_cat * 0.42 + 2.0
    fig, axes = new_figure_grid(ctx, len(groups),
                                tall_in=(tall * rows if not vertical else None),
                                rows=rows)

    for k, (ax, (p, segs)) in enumerate(zip(axes, groups)):
        n = len(segs)
        clrs = series_colors(n)
        if vertical:
            x = np.arange(n_cat)
            w = 0.82 / n if n > 1 else 0.6
            for i, seg in enumerate(segs):
                vals = data.get(seg, [None] * n_cat)
                off = (i - n / 2 + 0.5) * w if n > 1 else 0.0
                ax.bar(x + off, [v or 0.0 for v in vals], width=w, color=clrs[i],
                       edgecolor="none", zorder=3)
            ax.set_xticks(x)
            ax.set_xticklabels([_wrap_xtick_label(c) for c in cats], fontsize=8.5,
                               color=INK, rotation=_XTICK_ROTATION, ha="right",
                               rotation_mode="anchor")
            _apply_column_style(ax, max_val, series.statistic)
        else:
            y = np.arange(n_cat)[::-1]
            h = 0.82 / n if n > 1 else 0.6
            for i, seg in enumerate(segs):
                vals = data.get(seg, [None] * n_cat)
                off = (i - n / 2 + 0.5) * h if n > 1 else 0.0
                ax.barh(y + off, [v or 0.0 for v in vals], height=h, color=clrs[i],
                        edgecolor="none", zorder=3)
            ax.set_yticks(y)
            _apply_bar_style(ax, max_val, series.statistic)
            # The y-axis is SHARED, so set the category labels once and hide their
            # DISPLAY elsewhere (clearing them would clear the shared axis).
            first_in_row = (k == 0) if rows == 1 else True
            if k == 0:
                ax.set_yticklabels([_wrap_label(c) for c in cats], fontsize=9, color=INK)
            ax.tick_params(axis="y", labelleft=first_in_row)
        # Each panel is titled with its VARIABLE, not with a group of the first one.
        ax.set_title(p, fontsize=12.5, fontweight="bold", color=INK, pad=6)
        if ctx.spec.elements.legend:
            names = [_secondary_tick(s) for s in segs]
            handles = [Patch(facecolor=clrs[i], edgecolor="none") for i in range(len(names))]
            ax.legend(handles, names, loc="upper center", bbox_to_anchor=(0.5, -0.12),
                      ncol=min(len(names), 4), frameon=False, fontsize=9)

    fig.subplots_adjust(bottom=0.24, wspace=0.12, hspace=0.45, top=0.9,
                        left=0.12 if vertical else 0.2)
    place_picture(ctx, render_png(fig))
```

- [ ] **Step 6: Dispatch from the two clustered builders**

In `build_image_column`, next to the existing small-multiples check (line 507):

```python
    layout = _resolve_xtab_layout(ctx)
    if layout == "separate":
        _render_variable_panels(ctx, cats, vertical=True)
        return
    if layout == "small_multiples":
        _render_small_multiples(ctx, cats, vertical=True)
        return
```

Mirror it in `build_image_bar` with `vertical=False`.

- [ ] **Step 7: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/suite/integration/render/test_separate_panels.py -q`
Expected: PASS (5 passed)

- [ ] **Step 8: Run the suite and commit**

```bash
.venv/bin/python -m pytest tests/suite -q
git add src/reportbuilder/render/image/_mpl.py src/reportbuilder/render/image/bars.py \
        tests/suite/integration/render/test_separate_panels.py
git commit -m "feat(render): clustered separate panels, one per classifying variable"
```

---

### Task 8: Stacked panel renderer

**Files:**
- Modify: `src/reportbuilder/render/image/bars.py:769-833` (`build_image_bar_stacked`), `:703-768` (`build_image_column_stacked`)
- Create (in `bars.py`): `_draw_stacked_panel`, `_render_stacked_variable_panels`
- Test: `tests/suite/integration/render/test_separate_panels.py` (extend)

**Interfaces:**
- Consumes: Task 7's `_stack_panels`, `new_figure_grid(rows=…)`, `_primary_groups`.
- Produces: `_draw_stacked_panel(ax, bars, stack, data, clrs, ctx, y, flat_vals) -> None`; `_render_stacked_variable_panels(ctx, cats) -> None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/suite/integration/render/test_separate_panels.py`:

```python
@pytest.mark.parametrize("chart_type", ["stacked_horizontal_bar", "stacked_vertical_bar"])
def test_stacked_separate_panels_render_one_picture(chart_type):
    model, question, df = _setup()
    spec_kw = dict(classifying_var="sex", classifying_var_2="age",
                   options={"xtab_layout": "separate"})
    series = compute(question, _spec(chart_type), df, model)
    _prs, slide, slot, ctx = make_ctx(chart_type, series, **spec_kw)
    IMAGE_BUILDERS[chart_type](ctx)
    assert_single_picture(slide, slot)


def test_stacked_separate_panels_keep_their_row_summary_per_panel():
    model, question, df = _setup()
    spec = _spec("stacked_horizontal_bar", row_summary_fn="top2_sum")
    series = compute(question, spec, df, model)
    from reportbuilder.render.image.bars import _primary_groups, _row_summary_by_bar
    for _p, segs in _primary_groups(series):
        vals = _row_summary_by_bar(series, list(segs))
        assert len(vals) == len(segs)
        assert all(v is not None for v in vals), "every bar in the panel has its value"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/integration/render/test_separate_panels.py -q`
Expected: FAIL — the stacked builders ignore the layout and draw one flat chart.

- [ ] **Step 3: Extract the per-axes stacked drawing**

Lift the drawing loop out of `build_image_bar_stacked` (lines 776-807) into a helper both callers use — the same code, parameterised by the axes:

```python
def _draw_stacked_panel(ax, bars, stack, data, clrs, ctx, y, flat_vals) -> None:
    """Draw ONE 100%-stacked horizontal panel onto `ax`.

    Shared by the single-axes builder and the SEPARATE panel renderer. Each bar's
    segment WIDTHS are normalised to its own total so the right edges align, while
    the LABELS keep the original rounded percentages. (spec 2026-08-04)"""
    n_bars = len(bars)
    totals = np.array([sum(data[s][i] or 0.0 for s in stack) for i in range(n_bars)])
    norm = np.where(totals > 0, 100.0 / totals, 1.0)
    lefts = np.zeros(n_bars)
    for i, seg in enumerate(stack):
        orig = np.array([data[seg][j] or 0.0 for j in range(n_bars)])
        widths = orig * norm
        bar_clrs = [MUTED if c == NOT_ANSWERED_LABEL else clrs[i] for c in bars]
        ax.barh(y, widths, left=lefts, label=seg, color=bar_clrs,
                edgecolor="none", zorder=3)
        for yi, ov, l, w, bc in zip(y, orig, lefts, widths, bar_clrs):
            if w > 1:
                ax.text(l + w / 2, yi,
                        format_value(ov, ctx.series.statistic, ctx.spec.number_format,
                                     flat_vals),
                        ha="center", va="center", fontsize=9.0, fontweight="bold",
                        color=contrast_ink(bc), zorder=5)
        lefts = lefts + widths
```

Rewrite `build_image_bar_stacked`'s body to call it, keeping every surrounding line (ticks, `_apply_bar_style`, `_draw_row_summary`, legend) exactly as it is. Run `.venv/bin/python -m pytest tests/suite -q` here — this step must be behaviour-neutral.

- [ ] **Step 4: Add the stacked panel renderer**

```python
def _render_stacked_variable_panels(ctx, cats) -> None:
    """SEPARATE layout for the stacked types: one 100%-stacked panel per classifying
    VARIABLE. The stacked builders have no panel path of their own — they only draw
    the grouped/rotated-primary layout — so this is the panel equivalent.
    (spec 2026-08-04-separate-classifier-panels)"""
    series = ctx.series
    groups = _primary_groups(series)
    _bars, stack, data = _stacked_layout(series)
    clrs = scale_colors(len(stack))                 # the stack is the shared scale
    rows = 2 if _stack_panels([_secondary_tick(s) for _p, segs in groups for s in segs]) else 1
    flat_vals = [v for seg in stack for v in data[seg] if v is not None]
    max_bars = max((len(segs) for _p, segs in groups), default=1)
    fig, axes = new_figure_grid(ctx, len(groups),
                                tall_in=max_bars * 0.6 + 2.0, rows=rows)

    for ax, (p, segs) in zip(axes, groups):
        bars = list(segs)
        idx = [series.segments.index(b) for b in bars]
        panel = {s: [data[s][i] for i in idx] for s in stack}
        y = np.arange(len(bars))[::-1]
        _draw_stacked_panel(ax, bars, stack, panel, clrs, ctx, y, flat_vals)
        ax.set_yticks(y)
        ax.set_yticklabels([_wrap_label(_secondary_tick(b)) for b in bars],
                           fontsize=10.5, color=INK)
        ax.tick_params(axis="y", labelleft=True)
        ax.set_ylim(min(y) - 0.7, max(y) + 0.5)
        _apply_bar_style(ax, 100.0)
        ax.set_title(p, fontsize=12.5, fontweight="bold", color=INK, pad=6)
        _draw_row_summary(ctx, ax, y, bars)         # per panel, keyed by bar

    if ctx.spec.elements.legend and len(stack) > 1:
        _legend_below(axes[-1], len(stack))
    fig.subplots_adjust(bottom=0.24, wspace=0.18, hspace=0.45, top=0.9, left=0.2)
    place_picture(ctx, render_png(fig))
```

`_stacked_layout` returns `bars` for the whole series; here the panel's own bars come from `groups`, so the per-panel `data` is re-indexed against `series.segments`. `_draw_row_summary` already looks values up by bar label (`row_summary_keys`), so a panel gets only its own.

- [ ] **Step 5: Dispatch from the two stacked builders**

At the top of `build_image_bar_stacked`, after `cats, segs, data = _stacked_layout(ctx.series)`:

```python
    if _resolve_xtab_layout(ctx) == "separate":
        _render_stacked_variable_panels(ctx, cats)
        return
```

Do the same in `build_image_column_stacked`. The vertical stacked type reuses the horizontal panel renderer for now — a 100 % stack reads the same either way and the panel titles carry the variable; note this in a comment so it is a decision, not an oversight.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/integration/render/test_separate_panels.py -q`
Expected: PASS (8 passed)

- [ ] **Step 7: Run the suite and commit**

```bash
.venv/bin/python -m pytest tests/suite -q
git add src/reportbuilder/render/image/bars.py tests/suite/integration/render/test_separate_panels.py
git commit -m "feat(render): stacked separate panels, one per classifying variable"
```

---

### Task 9: Footer names both variables

**Files:**
- Modify: `src/reportbuilder/render/elements.py:129-154` (`add_filter_annotation`)
- Test: `tests/suite/unit/render/test_filter_annotation.py`

**Interfaces:**
- Consumes: `spec.classifying_var`, `spec.classifying_var_2`, `spec.options["xtab_layout"]`.
- Produces: no new symbols.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/render/test_filter_annotation.py`:

```python
"""The methodology footer must not claim a separate-layout slide is split by only
the first variable."""
from __future__ import annotations

from reportbuilder.render.elements import add_filter_annotation
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import make_ctx


def _series():
    return SeriesResult(categories=("A",), segments=("Total",),
                        cells={("A", "Total"): Cell(pct=100.0, count=1.0, mean=None)},
                        base_n={"Total": 1}, statistic="pct")


def _texts(slide):
    return [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]


def test_one_classifier_names_it():
    _prs, slide, _slot, ctx = make_ctx("horizontal_bar", _series(), classifying_var="sex")
    add_filter_annotation(ctx)
    assert "sex" in " ".join(_texts(slide))


def test_separate_layout_names_both():
    _prs, slide, _slot, ctx = make_ctx(
        "horizontal_bar", _series(), classifying_var="sex", classifying_var_2="age",
        options={"xtab_layout": "separate"})
    add_filter_annotation(ctx)
    text = " ".join(_texts(slide))
    assert "sex" in text and "age" in text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/render/test_filter_annotation.py -q`
Expected: FAIL on the second test — only `sex` is printed.

- [ ] **Step 3: Implement**

```python
    # In the SEPARATE layout the slide is split by BOTH variables, side by side;
    # naming only the first would misdescribe the chart. (spec 2026-08-04)
    opts = getattr(ctx.spec, "options", None) or {}
    cv2 = getattr(ctx.spec, "classifying_var_2", None)
    if cv2 and opts.get("xtab_layout") == "separate":
        tf.text = f"{ctx.spec.classifying_var} · {cv2}"
    else:
        tf.text = ctx.spec.classifying_var
```

- [ ] **Step 4: Run the test, the suite, and commit**

```bash
.venv/bin/python -m pytest tests/suite/unit/render/test_filter_annotation.py -q
.venv/bin/python -m pytest tests/suite -q
git add src/reportbuilder/render/elements.py tests/suite/unit/render/test_filter_annotation.py
git commit -m "feat(render): the filter footer names both variables in the separate layout"
```

---

### Task 10: Config UI — the control is never silently removed

**Files:**
- Modify: `web/src/components/wizard/StepConfigure.tsx:353-360` (`ClassifyingVarWidget`), `:718-727` (schema filtering), `:746-758` (`handleTypeChange`)
- Test: manual + `npx tsc -b`, then the Playwright check in Task 11

**Interfaces:**
- Consumes: `usesBannerClassifier(chart, variables)` (already in the file).
- Produces: no new exports.

- [ ] **Step 1: Stop hiding the second-classifier field**

In `ClassifyingVarWidget`, delete the early `return null` and render a disabled field with a reason instead. Replace line 359:

```tsx
  // A field that vanishes teaches the author nothing — "the horizontal bar no
  // longer lets me pick a second classifying variable" was this, silently. Always
  // render it; say why when it cannot be used. (spec 2026-08-04)
  const noPrimary = key === "classifying_var_2" && !chart.classifying_var;
```

and pass `disabled={noPrimary}` to the `Select`/`SelectTrigger`, with

```tsx
      hint={noPrimary ? "Choose a classifying variable first." : undefined}
```

A banner primary no longer disables anything — picking a second variable is allowed, because the separate layout does not cross them.

- [ ] **Step 2: Keep the field in the schema when there is no primary**

At line 718, stop filtering `classifying_var_2` out; keep filtering `show_total`:

```tsx
  // `classifying_var_2` STAYS in the schema without a primary — the widget renders
  // it disabled with a reason, instead of the row disappearing. (spec 2026-08-04)
  if (!chart.classifying_var) {
    schema = schema.filter((f) => f.key !== "show_total");
  }
```

- [ ] **Step 3: Force `separate` when the pair becomes banner + second**

Add to the same component, wrapping `onChange` for the two classifier keys:

```tsx
  // A banner classifier cannot be CROSSED with a second variable (its groups come
  // from separate columns and can overlap), but it can sit beside one. Whenever the
  // pair becomes banner + second, pin the layout to Separate panels so the chart is
  // never in a state the engine rejects — and so the author is not sent to a control
  // that only appears once two classifiers exist. (spec 2026-08-04)
  const withBannerGuard = (patch: Partial<ChartSpec>): Partial<ChartSpec> => {
    const next = { ...chart, ...patch } as ChartSpec;
    if (
      next.classifying_var &&
      next.classifying_var_2 &&
      usesBannerClassifier(next, variables) &&
      (next.options?.xtab_layout ?? "auto") !== "separate"
    ) {
      return {
        ...patch,
        options: { ...(chart.options ?? {}), xtab_layout: "separate" },
      };
    }
    return patch;
  };
```

and call `onChange(withBannerGuard({ [key]: … }))` in the `Select`'s handler and in the ⇄ Swap button.

- [ ] **Step 4: Disable the crossed options when the primary is a banner**

In `SelectWidget` (or wherever `xtab_layout` renders), disable `auto`/`grouped`/`small_multiples` when `usesBannerClassifier(chart, variables)` is true, with the title:

> "Polku's groups come from separate columns and can overlap, so they cannot be crossed with another variable."

Substitute the variable's label for "Polku".

- [ ] **Step 5: Clear a stale layout on a chart-type change**

In `handleTypeChange`, alongside the existing `classifying_var_2` clear:

```tsx
    // A stale `separate` must not survive onto a type with no second classifier.
    if (patch.chart_type && !supportsClassifying2(patch.chart_type) && chart.options?.xtab_layout) {
      extra.options = { ...(chart.options ?? {}), xtab_layout: undefined };
    }
```

- [ ] **Step 6: Typecheck and lint**

Run: `cd web && npx tsc -b && npx oxlint src/components/wizard/StepConfigure.tsx`
Expected: `tsc` exits 0; no new lint warnings beyond the two pre-existing `exhaustive-deps` ones at lines 796/848.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/wizard/StepConfigure.tsx
git commit -m "fix(web): never hide the second classifying variable without saying why"
```

---

### Task 11: End-to-end verification and deploy

**Files:**
- Create (temporary, deleted before commit): `web/verify-separate.mjs`

- [ ] **Step 1: Run the whole backend suite and the typecheck**

```bash
.venv/bin/python -m pytest tests/suite tests/rb -q
cd web && npx tsc -b
```
Expected: all green.

- [ ] **Step 2: Render the real customer case through the staging API — BEFORE state**

The material with two good classifiers and a banner variable is `mat-54`
(`Erisan_hiustenmuotoilu_DATA`): `var4` = gender, `Ikaryhmat` = age groups,
`polku` = a banner. Confirm the crossed render still looks like today:

```bash
ssh -i ~/.ssh/egohive-staging root@94.237.12.104 \
  'curl -s -m 280 -o /tmp/crossed.png -w "%{http_code}\n" -X POST \
   "http://127.0.0.1:8090/materials/mat-54/preview-chart" -H "Content-Type: application/json" \
   -d "{\"question_ref\":\"var136\",\"chart_type\":\"horizontal_bar\",\"classifying_var\":\"var4\",\"classifying_var_2\":\"Ikaryhmat\",\"render_title\":false}"'
```

- [ ] **Step 3: Deploy**

```bash
git push origin master
rsync -az --delete --exclude='.git' --exclude='.venv' --exclude='node_modules' \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='/web/dist' --exclude='/work' \
  --exclude='/input' --exclude='/ui' --exclude='/chart_lab' --exclude='*.sav' \
  --exclude='*.pptx' -e 'ssh -i ~/.ssh/egohive-staging' ./ root@94.237.12.104:/opt/nsight/
ssh -i ~/.ssh/egohive-staging root@94.237.12.104 \
  'cd /opt/nsight && docker compose -f docker-compose.staging.yml up -d --build'
```

Run the build as a background task — it does a full frontend build. Then health-check:
loopback `/` and `/cases` → 200/200, public `https://nsight.egohive.ai/` → 401.

- [ ] **Step 4: Render the AFTER state and look at it**

Repeat the Step 2 call with `"options":{"xtab_layout":"separate"}` added, for
`horizontal_bar` and `stacked_horizontal_bar`. `scp` both PNGs back and view them.
Expected: two panels — one titled "Identifioitko itsesi…?" with Naiseksi/Mieheksi/Muuten,
one titled "Ikäryhmät" with the three age bands. Not nine crossed bars, and no empty
`Muuten × age` panel.

Also render with `"classifying_var":"polku"` and `"classifying_var_2":"Ikaryhmat"` in
separate mode — it must succeed, where the crossed version returns 422 with the
banner message.

- [ ] **Step 5: Drive the config UI**

Start an isolated local pair (do not touch the user's servers on 8201):

```bash
cp -r work/demo-store "$SCRATCH/demo-store"
NSIGHT_DEMO=1 NSIGHT_DEMO_DIR="$SCRATCH/demo-store" NSIGHT_PORT=8299 \
  .venv/bin/python -m reportbuilder.api.server &
cd web && VITE_API_BASE=http://127.0.0.1:8299 npx vite --port 5199 --strictPort &
```

Write `web/verify-separate.mjs` (run it from `web/` so `playwright` resolves) that
opens `/cases/case-erisan2?report=rep-215`, goes to Design, and asserts:

1. On a slide with no classifying variable, the *Second classifying variable* field
   is present and disabled with "Choose a classifying variable first."
2. On a slide classified by a banner variable, the field is enabled; choosing a
   variable sets `options.xtab_layout` to `separate` in the saved report (read it
   back from `GET /cases/case-erisan2/reports/rep-215`).
3. Choosing *Separate panels (one per variable)* on a two-classifier slide renders a
   preview without error.

- [ ] **Step 6: Clean up and commit**

```bash
rm -f web/verify-separate.mjs
rm -rf "$SCRATCH/demo-store"
git status --short   # must show nothing untracked
```

- [ ] **Step 7: Report to the user with the before/after PNGs**

State plainly: what renders now, what is deliberately not built (more than two
variables, batteries, comparison questions), and that the horizontal-bar control is
back with a stated reason when it cannot be used.

---

## Self-review

**Spec coverage.** Author-facing option → Task 6 (schema) + Task 10 (UI). Panel
arrangement → Task 7 (`_stack_panels`, `rows`). Total series → Task 1 (per-variable
Total masks) + Tasks 2–4 (`base_n["Total"]` preserved). Banner lifting + the missing
control → Task 5 (engine guard) + Task 10 (UI). Engine segmentation, display labels,
`segment_primary`, per-panel sort, percent_base → Tasks 1–5. Rendering → Tasks 7–8.
Filter footer → Task 9. Edge-case table: stale variable → Task 1 (`continue`);
`handleTypeChange` → Task 10 Step 5; no migration → nothing to do, asserted in Task 6.

**Placeholders.** None. Task 4's `_summary` branch now carries the literal
`summary_value` / `Cell` construction copied from that function's existing
classifier branch (`engine.py:302-316`) rather than a "mirror what's there"
instruction.

**Type consistency.** `_separate_masks` returns `(masks, primary)` everywhere it is
used (Tasks 2, 3, 4, and `separate[1]` for `segment_primary`). `_stack_panels` takes
`list[str]` in both Task 7 and Task 8. `_draw_row_summary(ctx, ax, y, bars)` matches
the signature shipped on 2026-08-03. `new_figure_grid(ctx, n, *, tall_in, rows)` is
called with keywords in both renderers.
