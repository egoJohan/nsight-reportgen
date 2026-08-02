"""Cross-tabbing by a coded string column. (spec 2026-08-02 §1.2)

The picker can offer such a variable, but the engine's numeric segmentation path
turns every string into NaN — so the chart came back as a single Total series.
"""
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


def test_rows_with_no_path_value_are_in_no_segment():
    """A blank path is not a segment, and must not inflate the Total either."""
    model, q, df = _model_and_df()
    df.loc[len(df)] = {"q": 1.0, "var214": ""}
    r = engine.compute(q, _spec(), df, model)
    assert set(r.segments) == {"Pakkausilme 1", "Pakkausilme 2", "Total"}
    assert r.base_n["Total"] == 4


def test_a_numeric_column_held_as_strings_keeps_the_numeric_path():
    """Codes stored as text ("1"/"2") must still resolve via value labels, not
    become their own string segments."""
    model, q, df = _model_and_df()
    clf = Variable(name="clf", label="C", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B")),
                   missing_values=frozenset())
    model.variables["clf"] = clf
    df["clf"] = ["1", "1", "2", "2"]
    r = engine.compute(q, _spec(classifying_var="clf"), df, model)
    assert set(r.segments) == {"A", "B", "Total"}
