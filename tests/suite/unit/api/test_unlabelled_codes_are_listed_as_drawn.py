"""The label editor lists the categories the CHART draws, for unlabelled codes too.

"NPS muuttuja jää puuttumaan" brought this along: a 0–10 score with no value
labels is charted as "1".."10" (`engine.code_labels`), while the editor listed
"1.0".."10.0" — the raw floats. A rename typed against "1.0" is stored under a
name no category has, so nothing changes on the slide: the same failure that
made short labels silently do nothing on renamed categories. (2026-09-17)
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.api.routes_questions import _category_labels
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.stats import engine
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec

pytestmark = pytest.mark.unit


def _model_and_df():
    nps = Variable("NPS", "NPS", "categorical", (), frozenset())
    model = QuestionModel(variables={"NPS": nps}, questions=[
        Question(qid="nps", kind="single", variables=("NPS",), text="NPS")])
    df = pd.DataFrame({"NPS": [1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 8.0, 9.0, 10.0, 10.0]})
    return model, df


def test_the_editor_lists_what_the_chart_draws():
    model, df = _model_and_df()
    spec = ChartSpec(question_ref="nps", chart_type="vertical_bar", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())
    drawn = list(engine.compute(model.question("nps"), spec, df, model).categories)
    assert _category_labels(model, model.question("nps"), df) == drawn
    assert "1.0" not in drawn


def test_a_labelled_question_is_unchanged():
    var = Variable("q", "q", "categorical",
                   (ValueLabel(1.0, "Kyllä"), ValueLabel(2.0, "Ei")), frozenset())
    model = QuestionModel(variables={"q": var}, questions=[
        Question(qid="q", kind="single", variables=("q",), text="q")])
    df = pd.DataFrame({"q": [1.0, 2.0]})
    assert _category_labels(model, model.question("q"), df) == ["Kyllä", "Ei"]
