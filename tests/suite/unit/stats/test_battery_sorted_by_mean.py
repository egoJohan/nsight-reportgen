"""Sorting a rating battery by MEAN orders its statements.

"Mean" is in the Sort list for every chart type (`SORT_BASIS_OPTIONS`), and a
rating battery's SUGGESTED chart is the stacked bar — so this is the default
chart for the commonest kind of battery slide, with a sort option on it that
did nothing. The statements came back in survey order however the author set
the control.

`_battery_stacked` reorders its statement bars for the box sums (Top 2, Top 3,
Bottom 2, Bottom 3) and for "Percentage" where a row-summary column gives that
word a meaning. Mean was never added, so it fell through to member order. The
same battery drawn as a plain bar sorts by mean correctly, which is what makes
the stacked one read as broken rather than as a limitation.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats.engine import compute

_LEVELS = [ValueLabel(value=float(i + 1), label=l)
           for i, l in enumerate(["1 Täysin eri", "2", "3", "4", "5 Täysin samaa"])]

#: Four statements whose means are deliberately NOT their survey order:
#: A 4.33, D 3.40, B 3.25, C 2.02.
_SHAPE = {
    "A hyvä":   [2, 3, 10, 30, 55],
    "B keski":  [5, 15, 40, 30, 10],
    "C heikko": [40, 30, 20, 8, 2],
    "D jakava": [30, 5, 10, 5, 50],
}
_BY_MEAN_DESC = ["A", "D", "B", "C"]


def _statements(chart_type: str, basis: str, descending: bool = True) -> list[str]:
    variables, members = {}, []
    for i, name in enumerate(_SHAPE):
        vn = f"v{i}"
        variables[vn] = Variable(name=vn, label=name, measurement="nominal",
                                 missing_values=[], value_labels=_LEVELS)
        members.append(vn)
    rows = []
    for r in range(100):
        row = {}
        for i, dist in enumerate(_SHAPE.values()):
            cum, pick = 0, len(dist)
            for lvl, n in enumerate(dist, start=1):
                cum += n
                if r < cum:
                    pick = lvl
                    break
            row[f"v{i}"] = float(pick)
        rows.append(row)
    q = Question(qid="batt", text="Väittämät", kind="battery", variables=tuple(members))
    model = QuestionModel(variables=variables, questions=[q])
    spec = ChartSpec(question_ref="batt", chart_type=chart_type, statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis=basis, descending=descending),
                     template_slot="s1", elements=ElementToggles())
    s = compute(q, spec, pd.DataFrame(rows), model)
    axis = (s.categories if chart_type == "horizontal_bar"
            else tuple(x for x in s.segments if x != "Total"))
    return [c.split()[0] for c in axis]


def test_a_plain_bar_sorts_a_battery_by_mean():
    """The control, and the reason the stacked one reads as broken: the same
    question, the same setting, on the chart type that already worked."""
    assert _statements("horizontal_bar", "mean") == _BY_MEAN_DESC


@pytest.mark.parametrize("chart_type",
                         ["stacked_horizontal_bar", "stacked_vertical_bar"])
def test_a_stacked_battery_sorts_by_mean_too(chart_type):
    assert _statements(chart_type, "mean") == _BY_MEAN_DESC


@pytest.mark.parametrize("chart_type",
                         ["stacked_horizontal_bar", "stacked_vertical_bar"])
def test_ascending_reverses_it(chart_type):
    assert _statements(chart_type, "mean", descending=False) == _BY_MEAN_DESC[::-1]


def test_survey_order_is_still_survey_order():
    assert _statements("stacked_horizontal_bar", "data_order") == ["A", "B", "C", "D"]


def test_the_box_sums_are_untouched():
    """Top 2 is 4+5: A 85, D 55, B 40, C 10 — a different order from the mean's,
    which is what makes this a real check that nothing was reinterpreted."""
    assert _statements("stacked_horizontal_bar", "topbox_sum") == ["A", "D", "B", "C"]
    assert _statements("stacked_horizontal_bar", "bottom2_sum") == ["C", "D", "B", "A"]
