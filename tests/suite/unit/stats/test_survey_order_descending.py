"""Survey order can run backwards.

"KRIITTINEN Jos Sort = Survey order mahdollistetaan myös 'Ascending'" — a
stacked bar split by region (Muu Suomi = 0, Itäinen Suomi = 1) drew Muu Suomi
first, the headline was about Itä-Suomi, and with Survey order selected the
direction control was locked, so nothing could put Itäinen Suomi on top.
(Suomalainen Työ, 2026-09-23)

The rule, as agreed with Johan: with Survey order, ASCENDING is the default and
lists the entries as the data has them; DESCENDING reverses that. It reverses
the rows survey order lays down — the categories, a split stack's group rows,
a battery's statements — never the scale inside a stack.

Stored as its own flag, `survey_descending`, off by default. `descending` has
always been saved as True on every slide, so reading survey order off it would
have flipped every existing survey-order slide the moment this shipped.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, SortSpec, report_from_json,
)
from reportbuilder.stats.engine import compute
from reportbuilder.stats.sorting import sort_categories

pytestmark = pytest.mark.unit

_ROWS = [("A", 1.0, {"data_index": 0, "pct": 10.0}),
         ("B", 2.0, {"data_index": 1, "pct": 30.0}),
         ("C", 3.0, {"data_index": 2, "pct": 20.0})]


def test_survey_order_ascending_is_the_data_order():
    assert sort_categories(_ROWS, SortSpec(basis="data_order")) == ["A", "B", "C"]


def test_survey_order_descending_reverses_it():
    spec = SortSpec(basis="data_order", survey_descending=True)
    assert sort_categories(_ROWS, spec) == ["C", "B", "A"]


def test_the_flag_means_nothing_to_a_value_sort():
    spec = SortSpec(basis="pct", descending=True, survey_descending=True)
    assert sort_categories(_ROWS, spec) == ["B", "C", "A"]


def test_a_saved_slide_keeps_its_order():
    """Every stored slide says `descending: true` and has no survey flag."""
    doc = {"name": "r", "render_mode": "image", "template_ref": "", "charts": [{
        "question_ref": "q", "chart_type": "horizontal_bar", "statistic": "pct",
        "classifying_var": None, "number_format": {}, "template_slot": "s1",
        "elements": {}, "sort": {"basis": "data_order", "descending": True}}]}
    sort = report_from_json(doc).charts[0].sort
    assert sort.survey_descending is False
    assert sort_categories(_ROWS, sort) == ["A", "B", "C"]


# ---- the reported slide: a stacked bar split by region -------------------------

_SCALE = {1: "1 - Ei lainkaan tärkeä", 2: "2", 3: "3", 4: "4", 5: "5 - Erittäin tärkeä"}
_REGION = {0: "Muu Suomi", 1: "Itäinen Suomi"}


def _stacked_by_region(**sort):
    q = Variable(name="q", label="Kuinka tärkeää työ on sinulle?", measurement="ordinal",
                 missing_values=[],
                 value_labels=[ValueLabel(value=float(c), label=l) for c, l in _SCALE.items()])
    region = Variable(name="alue", label="Alue", measurement="nominal", missing_values=[],
                      value_labels=[ValueLabel(value=float(c), label=l) for c, l in _REGION.items()])
    rows = [{"q": float(1 + i % 5), "alue": float(i % 2)} for i in range(200)]
    model = QuestionModel(variables={"q": q, "alue": region},
                          questions=[Question(qid="q", text=q.label, kind="single", variables=("q",))])
    spec = ChartSpec(question_ref="q", chart_type="stacked_horizontal_bar", statistic="pct",
                     classifying_var="alue", number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order", **sort), template_slot="s1",
                     elements=ElementToggles(), show_total="on")
    return compute(model.question("q"), spec, pd.DataFrame(rows), model)


def test_split_stack_ascending_lists_the_groups_as_coded():
    assert _stacked_by_region().segments[:2] == ("Muu Suomi", "Itäinen Suomi")


def test_split_stack_descending_puts_the_last_group_first():
    got = _stacked_by_region(survey_descending=True)
    assert got.segments[:2] == ("Itäinen Suomi", "Muu Suomi"), got.segments


def test_total_stays_last_either_way():
    assert _stacked_by_region(survey_descending=True).segments[-1] == "Total"


def test_the_scale_inside_the_stack_is_never_reversed():
    got = _stacked_by_region(survey_descending=True)
    assert got.categories[0].startswith("1") and got.categories[-1].startswith("5")


# ---- a battery's statements ---------------------------------------------------

def _battery(chart_type, **sort):
    names = ("v0", "v1", "v2")
    variables = {n: Variable(name=n, label=f"Väite {n}", measurement="ordinal", missing_values=[],
                             value_labels=[ValueLabel(value=float(c), label=l)
                                           for c, l in _SCALE.items()]) for n in names}
    rows = [{n: float(1 + (i + j) % 5) for j, n in enumerate(names)} for i in range(100)]
    model = QuestionModel(variables=variables, questions=[Question(
        qid="b", text="Väitteet", kind="battery", variables=names)])
    spec = ChartSpec(question_ref="b", chart_type=chart_type,
                     statistic="mean" if chart_type == "horizontal_bar" else "pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order", **sort), template_slot="s1",
                     elements=ElementToggles())
    return compute(model.questions[0], spec, pd.DataFrame(rows), model)


@pytest.mark.parametrize("chart_type", ["horizontal_bar", "stacked_horizontal_bar"])
def test_battery_statements_reverse(chart_type):
    asc = _battery(chart_type)
    desc = _battery(chart_type, survey_descending=True)
    rows_of = (lambda r: r.categories) if chart_type == "horizontal_bar" else (lambda r: r.segments)
    assert list(rows_of(desc)) == list(reversed(rows_of(asc))), (rows_of(asc), rows_of(desc))
