"""Cross-tabbing by a banner (indicator-column) classifier. (spec 2026-08-02 §2.4)

`classifying_var` carries the QID of a near-partition multi question; resolution is
variable-name-first, so a real column always wins.
"""
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


def test_cells_split_by_the_banner_segment():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert r.cell("Yes", "Polku 1").count == 50.0
    assert r.cell("No", "Polku 2").count == 50.0


def test_a_non_partition_multi_is_not_used_as_a_classifier():
    """An overlapping tick-box multi must fall through, not become segments."""
    model, q, df = _setup()
    df["Polku2"] = 1.0                       # everyone in both -> 100% overlap
    r = engine.compute(q, _spec(), df, model)
    assert set(r.segments) == {"Total"}


def test_a_real_variable_name_wins_over_a_qid():
    """Resolution order: a DataFrame column always takes precedence."""
    model, q, df = _setup()
    clf = Variable(name="clf", label="C", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B")),
                   missing_values=frozenset())
    model.variables["clf"] = clf
    df["clf"] = [1.0, 2.0] * 100
    r = engine.compute(q, _spec(classifying_var="clf"), df, model)
    assert set(r.segments) == {"A", "B", "Total"}


def test_screened_banner_total_excludes_unqualified_respondents():
    """Only 60% saw a concept; the Total must sit on those 120, not on 200."""
    model, q, df = _setup()
    df.loc[120:, "Polku1"] = None
    df.loc[120:, "Polku2"] = None
    r = engine.compute(q, _spec(), df, model)
    assert r.base_n["Total"] == 120
    for seg in ("Polku 1", "Polku 2"):
        total = sum((r.cell(c, seg).pct or 0) for c in r.categories)
        assert abs(total - 100.0) < 0.5
