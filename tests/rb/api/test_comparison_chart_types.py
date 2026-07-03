"""A comparison question offers only the chart types that render a multi-series overlay
(radar + grouped/clustered bars); pie/scatter/etc. are filtered from the Design picker."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.model.report import ChartSpec, NumberFormat, SortSpec, ElementToggles
from reportbuilder.stats import engine
from reportbuilder.api.routes_questions import _compatible_chart_types


def _tick(n, l):
    return Variable(name=n, label=l, measurement="categorical",
                    value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                    missing_values=frozenset())


def _comp_model():
    vars_ = {"r_is": _tick("r_is", "IS"), "r_il": _tick("r_il", "IL"),
             "l_is": _tick("l_is", "IS"), "l_il": _tick("l_il", "IL")}
    qs = [Question(qid="rohkea", kind="multi", variables=("r_is", "r_il"), text="-Rohkea"),
          Question(qid="luot", kind="multi", variables=("l_is", "l_il"), text="-Luotettava")]
    comp = Question(qid="compare-x", kind="comparison", variables=("r_is", "r_il", "l_is", "l_il"),
                    text="Vertailu", members=("rohkea", "luot"))
    model = QuestionModel(variables=vars_, questions=qs + [comp])
    df = pd.DataFrame({"r_is": [1, 1], "r_il": [1, 0], "l_is": [1, 0], "l_il": [0, 1]})
    return model, comp, df


def test_comparison_offers_only_overlay_chart_types():
    model, comp, df = _comp_model()
    spec = ChartSpec(question_ref="compare-x", chart_type="radar", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s",
                     elements=ElementToggles())
    series = engine.compute(comp, spec, df, model)
    types = _compatible_chart_types(comp, series)
    assert "radar" in types
    assert set(types) <= {"radar", "vertical_bar", "horizontal_bar"}
    assert "pie" not in types and "scatter" not in types
