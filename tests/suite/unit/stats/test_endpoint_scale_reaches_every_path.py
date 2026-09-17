"""A scale worded only at its ends is a scale on EVERY path, not on some of them.

`scale_levels(var, df)` learned to read an endpoint-labelled rating off the data
(see test_endpoint_labelled_scale_is_a_scale). The frame was then threaded into
`_battery` and `_battery_stacked` and nowhere else, which left four callers still
asking `scale_levels(var)` with no frame — and a frameless answer for this shape
is `[]`, "not a scale at all".

The consequences were not cosmetic:

- `_drop_empty_segments` decided every classifier group had answered nothing,
  returned None, and `_battery` fell back to the whole sample. Thirty men
  answering 5 and thirty women answering 1 drew ONE bar at 3.0 — a number no
  respondent gave, on a slide whose classifier the editor still showed as
  selected. A blank chart is a bug report; a plausible wrong number is a wrong
  decision.
- `_battery_comparison` — the parallel-battery radar, the shape this whole
  feature was reported against — mapped every answer to NaN and drew nothing,
  while the SAME data on a horizontal bar charted correctly.
- `_top_scale_categories` found no levels, so "Sort by top 2" silently did
  nothing while the control still read Top 2.

One rule, asked the same way everywhere. These tests are at the CONSUMER, not at
`scale_levels`: the unit was already right and still shipped three wrong
charts. (Johan, 2026-09-17)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, SortSpec,
)
from reportbuilder.stats.engine import compute

pytestmark = pytest.mark.unit

ENDS = (ValueLabel(1.0, "Erittäin huonosti"), ValueLabel(5.0, "Erittäin hyvin"))
FULL = tuple(ValueLabel(float(i), f"Taso {i}") for i in range(1, 6))
STATEMENTS = ("Laatu", "Hinta")


def _model(labels=ENDS) -> tuple[QuestionModel, Question]:
    vars_ = {n: Variable(n, n, "ordinal", tuple(labels), frozenset())
             for n in STATEMENTS}
    vars_["sukup"] = Variable(
        "sukup", "Sukupuoli", "nominal",
        (ValueLabel(1.0, "Mies"), ValueLabel(2.0, "Nainen")), frozenset())
    model = QuestionModel(variables=vars_, questions=[])
    q = Question(qid="bat", kind="battery", variables=STATEMENTS, text="Väittämät")
    return model, q


def _split_df() -> pd.DataFrame:
    """Thirty men who answer 5 and thirty women who answer 1.

    Chosen so the pooled mean (3.0) is a value NOBODY gave: a chart showing 3.0
    cannot be mistaken for a rounding artefact of the right answer.
    """
    rows = {n: [5.0] * 30 + [1.0] * 30 for n in STATEMENTS}
    rows["sukup"] = [1.0] * 30 + [2.0] * 30
    return pd.DataFrame(rows)


def _spec(**over) -> ChartSpec:
    base = dict(question_ref="bat", chart_type="horizontal_bar", statistic="mean",
                classifying_var="sukup", number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s1",
                elements=ElementToggles())
    base.update(over)
    return ChartSpec(**base)


def _means(res, statement: str) -> dict[str, float | None]:
    return {seg: (res.cells.get((statement, seg)) or type(res.cells[next(iter(res.cells))])()).mean
            for seg in res.segments}


# ---------------------------------------------------------------------------
# _drop_empty_segments: the classifier must survive
# ---------------------------------------------------------------------------

def test_the_split_survives_an_endpoint_labelled_scale():
    model, q = _model()
    res = compute(q, _spec(), _split_df(), model)
    assert "Mies" in res.segments and "Nainen" in res.segments, (
        f"the classifier was dropped; segments={res.segments}")


def test_each_group_keeps_its_own_mean():
    """The defect showed as one bar at the pooled 3.0 — a value nobody gave."""
    model, q = _model()
    res = compute(q, _spec(), _split_df(), model)
    assert _means(res, "Laatu")["Mies"] == pytest.approx(5.0)
    assert _means(res, "Laatu")["Nainen"] == pytest.approx(1.0)


def test_a_fully_labelled_scale_behaves_the_same():
    """The control. If this ever diverges from the test above, the fix has made
    the two kinds of scale two different features again."""
    model, q = _model(FULL)
    res = compute(q, _spec(), _split_df(), model)
    assert _means(res, "Laatu")["Mies"] == pytest.approx(5.0)
    assert _means(res, "Laatu")["Nainen"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _battery_comparison: the radar this feature was reported against
# ---------------------------------------------------------------------------

def _comparison_model(labels=ENDS):
    """Two parallel batteries with identical statement labels — the brand-image
    shape `_parallel_batteries` detects, which a radar charts."""
    attrs = ("Luotettava", "Moderni")
    vars_: dict[str, Variable] = {}
    for brand in ("A", "B"):
        for a in attrs:
            vars_[f"{brand}_{a}"] = Variable(
                f"{brand}_{a}", a, "ordinal", tuple(labels), frozenset())
    model = QuestionModel(
        variables=vars_,
        questions=[Question(qid="A", kind="battery", text="Attendo",
                            variables=tuple(f"A_{a}" for a in attrs)),
                   Question(qid="B", kind="battery", text="Mehiläinen",
                            variables=tuple(f"B_{a}" for a in attrs))])
    # A comparison names its MEMBER QUESTIONS, not variables — `variables` stays
    # empty or `_compute_series` would look for columns called "A" and "B".
    cmp_q = Question(qid="cmp", kind="comparison", text="Brändit",
                     variables=(), members=("A", "B"))
    rng = np.random.default_rng(7)
    df = pd.DataFrame({n: rng.choice([1.0, 2.0, 3.0, 4.0, 5.0], size=240)
                       for n in vars_})
    return model, cmp_q, df


def test_the_parallel_battery_radar_is_not_blank():
    model, q, df = _comparison_model()
    res = compute(q, _spec(question_ref="cmp", chart_type="radar",
                           classifying_var=None), df, model)
    drawn = [c.mean for c in res.cells.values() if c.mean is not None]
    assert drawn, f"every cell was empty; base_n={res.base_n}"


def test_no_path_in_the_engine_asks_without_the_frame():
    """The structural guard, because the behavioural ones above could not catch
    this on their own: each missed call site is a DIFFERENT chart, and the next
    one added will be a chart nobody wrote a test for.

    Every `scale_levels(` call in the engine has a frame in scope — `data` or
    `df` — so asking without one is always the omission, never a choice. Outside
    this module it can be legitimate (`ingest/battery_group.py` suggests groups
    before any frame is loaded), so the rule is scoped to where it holds.
    """
    import ast
    from pathlib import Path

    # Parsed, not grepped. The obvious regex reads `scale_levels(model.variable(vn),
    # data)` as a one-argument call, because it stops at the first `)` — and a
    # guard that cries wolf is one somebody deletes.
    src = Path(__file__).resolve().parents[4] / "src/reportbuilder/stats/engine.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    bad = [
        (node.lineno, ast.unparse(node))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "scale_levels"
        and len(node.args) + len(node.keywords) < 2
    ]
    assert not bad, (
        "these ask whether something is a scale without the data that answers "
        f"it for an endpoint-labelled rating: {bad}")


def test_the_radar_and_the_bar_agree():
    """The sharpest form of the defect: the same data, blank on one chart type
    and correct on another, because only one path was given the frame."""
    model, q, df = _comparison_model()
    radar = compute(q, _spec(question_ref="cmp", chart_type="radar",
                             classifying_var=None), df, model)
    bar = compute(q, _spec(question_ref="cmp", chart_type="horizontal_bar",
                           classifying_var=None), df, model)
    assert bool([c for c in radar.cells.values() if c.mean is not None]) == \
           bool([c for c in bar.cells.values() if c.mean is not None])
