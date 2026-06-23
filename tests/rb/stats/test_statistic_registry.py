"""Tests for the pluggable statistic registry. (REQ-C-15)

Covers:
1. Back-compat: pct, count, mean compute and render as before.
2. median: summary_fn produces correct median over clean data.
3. sum: summary_fn produces correct sum over clean data.
4. End-to-end render with statistic="median" via build_pptx.
5. number_format_code routes through the registry.
6. Unregistered statistic raises KeyError with helpful message.
7. Extensibility: register a new statistic (p90) with one call, no engine edits.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
)
from reportbuilder.stats.engine import compute
from reportbuilder.stats.registry import (
    Statistic,
    _dec_fmt,
    register,
    statistic as get_statistic,
)
from reportbuilder.render.elements import number_format_code
from reportbuilder.testing.fidelity import numbers_from_pptx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scale_var(name: str = "score", label: str = "Score") -> Variable:
    return Variable(
        name=name,
        label=label,
        measurement="scale",
        value_labels=(),
        missing_values=frozenset(),
    )


def _question(var: Variable) -> Question:
    return Question(qid=var.name, kind="single", variables=(var.name,), text=var.label)


def _model(var: Variable) -> QuestionModel:
    return QuestionModel(variables={var.name: var}, questions=[_question(var)])


def _spec(qref: str, stat: str, **kw) -> ChartSpec:
    return ChartSpec(
        question_ref=qref,
        chart_type=kw.get("chart_type", "vertical_bar"),
        statistic=stat,
        classifying_var=kw.get("classifying_var", None),
        number_format=kw.get("number_format", NumberFormat()),
        sort=kw.get("sort", SortSpec(basis="data_order")),
        template_slot=kw.get("template_slot", "s1"),
        elements=kw.get("elements", ElementToggles()),
    )


# ---------------------------------------------------------------------------
# Test 1: Back-compat — pct, count, mean still work exactly as before (REQ-C-15)
# ---------------------------------------------------------------------------

def test_backcompat_pct():
    """pct statistic still produces the expected percentage. (REQ-C-15)"""
    var = Variable(
        name="q1", label="Q1", measurement="categorical",
        value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
        missing_values=frozenset(),
    )
    q = Question(qid="q1", kind="single", variables=("q1",), text="Q1")
    model = QuestionModel(variables={"q1": var}, questions=[q])
    df = pd.DataFrame({"q1": [1.0, 1.0, 1.0, 2.0, 2.0]})

    res = compute(q, _spec("q1", "pct"), df, model)

    assert res.statistic == "pct"
    assert res.cell("Yes", "Total").pct == 60.0
    assert res.cell("Yes", "Total").value("pct") == 60.0


def test_backcompat_count():
    """count statistic still produces integer counts. (REQ-C-15, REQ-N-03)"""
    var = Variable(
        name="q1", label="Q1", measurement="categorical",
        value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
        missing_values=frozenset(),
    )
    q = Question(qid="q1", kind="single", variables=("q1",), text="Q1")
    model = QuestionModel(variables={"q1": var}, questions=[q])
    df = pd.DataFrame({"q1": [1.0, 1.0, 1.0, 2.0, 2.0]})

    res = compute(q, _spec("q1", "count"), df, model)

    assert res.statistic == "count"
    assert res.cell("Yes", "Total").count == 3.0
    assert res.cell("Yes", "Total").value("count") == 3.0


def test_backcompat_mean():
    """mean statistic still produces correct mean in the .mean field. (REQ-C-15, REQ-N-02)"""
    var = _scale_var("age", "Age")
    q = _question(var)
    model = _model(var)
    df = pd.DataFrame({"age": [30.0, 40.0, 50.0, 60.0, 70.0]})

    res = compute(q, _spec("age", "mean"), df, model)

    assert res.statistic == "mean"
    assert res.cell("Age", "Total").mean == 50.0
    assert res.cell("Age", "Total").value("mean") == 50.0


# ---------------------------------------------------------------------------
# Test 2: median — data [1,2,3,4,100] → median 3.0 (REQ-C-15)
# ---------------------------------------------------------------------------

def test_median_compute():
    """Median of [1,2,3,4,100] == 3.0 via cell.value('median'). (REQ-C-15)"""
    var = _scale_var("v", "V")
    q = _question(var)
    model = _model(var)
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 100.0]})

    res = compute(q, _spec("v", "median"), df, model)

    assert res.statistic == "median"
    assert res.cell("V", "Total").value("median") == 3.0


# ---------------------------------------------------------------------------
# Test 3: sum — data [10,20,30] → sum 60.0 (REQ-C-15)
# ---------------------------------------------------------------------------

def test_sum_compute():
    """Sum of [10,20,30] == 60.0 via cell.value('sum'). (REQ-C-15)"""
    var = _scale_var("v", "V")
    q = _question(var)
    model = _model(var)
    df = pd.DataFrame({"v": [10.0, 20.0, 30.0]})

    res = compute(q, _spec("v", "sum"), df, model)

    assert res.statistic == "sum"
    assert res.cell("V", "Total").value("sum") == 60.0


# ---------------------------------------------------------------------------
# Test 4: End-to-end render with statistic="median" via build_pptx (REQ-C-15)
# ---------------------------------------------------------------------------

def test_median_renders_end_to_end(tmp_path):
    """Build a 1-ChartSpec report with statistic='median' over a scale var.
    numbers_from_pptx must contain the median value, proving the full pipeline
    (value-access + number-format) routes through the registry. (REQ-C-15)"""
    var = _scale_var("v", "V")
    q = _question(var)
    model = _model(var)
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 100.0]})
    # median == 3.0

    spec = ChartSpec(
        question_ref="v",
        chart_type="vertical_bar",
        statistic="median",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="s1",
        elements=ElementToggles(),
    )
    report = Report(
        name="MedianTest",
        render_mode="native",
        template_ref="t.pptx",
        charts=(spec,),
    )

    out = str(tmp_path / "median_test.pptx")
    result_path = build_pptx(report, model, df, out)
    assert os.path.exists(result_path)

    extracted = numbers_from_pptx(result_path)
    pool: list[float] = []
    for v in extracted.values():
        pool.extend(v if isinstance(v, (list, tuple)) else [v])

    assert any(abs(3.0 - got) <= 0.5 for got in pool), (
        f"Expected median ~3.0 not found in PPTX values: {pool}"
    )


# ---------------------------------------------------------------------------
# Test 5: Number format routes through the registry (REQ-C-15)
# ---------------------------------------------------------------------------

def test_number_format_via_registry():
    """number_format_code is registry-driven: median uses decimal fmt, pct uses % fmt. (REQ-C-15)"""
    fmt = NumberFormat()   # pct_decimals=0, mean_decimals=1

    median_fmt = number_format_code(fmt, "median")
    pct_fmt = number_format_code(fmt, "pct")

    # decimal format for summary stats
    assert "%" not in median_fmt, f"median format should not contain %: {median_fmt!r}"
    assert median_fmt.startswith("0"), f"median format should start with 0: {median_fmt!r}"
    # pct format must contain %
    assert "%" in pct_fmt, f"pct format should contain %: {pct_fmt!r}"


# ---------------------------------------------------------------------------
# Test 6: Unregistered statistic → KeyError with registered names (REQ-C-15)
# ---------------------------------------------------------------------------

def test_unregistered_statistic_raises_key_error():
    """compute with an unregistered statistic raises KeyError mentioning known names. (REQ-C-15)"""
    var = _scale_var("v", "V")
    q = _question(var)
    model = _model(var)
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0]})

    spec = _spec("v", "bogus")
    with pytest.raises(KeyError, match="bogus"):
        compute(q, spec, df, model)


# ---------------------------------------------------------------------------
# Test 7: Extensibility proof — register p90 with one call, no engine edit (REQ-C-15)
# ---------------------------------------------------------------------------

def test_extensibility_register_p90():
    """Registering a new statistic (p90) requires exactly one register() call;
    compute() + cell.value() work without any engine modification. (REQ-C-15)"""
    register(Statistic(
        "p90", "summary", _dec_fmt,
        summary_fn=lambda s: float(s.quantile(0.9)),
    ))

    var = _scale_var("v", "V")
    q = _question(var)
    model = _model(var)
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]})
    # p90 of [1..10] == 9.1

    res = compute(q, _spec("v", "p90"), df, model)

    assert res.statistic == "p90"
    v = res.cell("V", "Total").value("p90")
    assert v is not None
    assert abs(v - 9.1) <= 0.2, f"Expected p90 ~9.1, got {v}"
