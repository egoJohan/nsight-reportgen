"""A BATTERY on a numbered scale says which end is which in its own legend.

Attendo's brand-image batteries, 14 statements over "1 - Ei vastaa lainkaan"
… "5 - Vastaa täysin", once drew a legend reading "1 2 3 4 5" with nothing on
the slide saying whether 5 was good or bad; a footer caption was added to put
the words back. The legend no longer shortens a scale (2026-09-23, see
render/test_an_authored_label_is_not_shortened_away.py), so the words are the
legend's own levels and a caption would only repeat them.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats.engine import compute

_STATEMENTS = ("Rehellinen", "Luotettava", "Ammattitaitoinen")
#: Endpoints worded, middle points labelled with their own number — the shape a
#: real SPSS export uses, and the one the legend shortens.
_ENDPOINT = {1: "1 - Ei vastaa lainkaan", 2: "2", 3: "3", 4: "4",
             5: "5 - Vastaa täysin"}
_ALL_WORDED = {1: "1 - Ei lainkaan", 2: "2 - Huonosti", 3: "3 - Kohtalaisesti",
               4: "4 - Hyvin", 5: "5 - Erinomaisesti"}


def _model(scale: dict[int, str]):
    variables, rows = {}, []
    for j, stmt in enumerate(_STATEMENTS):
        variables[f"v{j}"] = Variable(
            name=f"v{j}", label=f"Mielikuva: {stmt}", measurement="ordinal",
            missing_values=[],
            value_labels=[ValueLabel(value=float(c), label=l)
                          for c, l in scale.items()])
    for i in range(200):
        rows.append({f"v{j}": float((i + j) % 5 + 1) for j in range(len(_STATEMENTS))})
    model = QuestionModel(
        variables=variables,
        questions=[Question(qid="battery-mielikuva", text="Kuinka hyvin vastaavat?",
                            kind="battery",
                            variables=tuple(f"v{j}" for j in range(len(_STATEMENTS))))])
    return model, pd.DataFrame(rows)


def _spec(chart_type="stacked_horizontal_bar") -> ChartSpec:
    return ChartSpec(question_ref="battery-mielikuva", chart_type=chart_type,
                     statistic="pct", classifying_var=None,
                     number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                     template_slot="s1", elements=ElementToggles())


def _series(scale, chart_type="stacked_horizontal_bar"):
    model, df = _model(scale)
    return compute(model.questions[0], _spec(chart_type), df, model)


def test_a_battery_on_an_endpoint_labelled_scale_keeps_its_words():
    got = _series(_ENDPOINT)
    assert got.categories == ("1 - Ei vastaa lainkaan", "2", "3", "4", "5 - Vastaa täysin")
    assert got.caption is None, "the legend already names the ends"


def test_the_scale_point_is_read_from_the_LABEL_not_the_sav_code():
    """Attendo's own export, var102: the middle points are coded 2, 3, 4 but the
    two ENDPOINTS sit on codes 10346 and 10350, with "En osaa sanoa" on 10351.
    The levels are ordered by the point the label states, not the SAV code."""
    scale = {2: "2", 3: "3", 4: "4",
             10346: "1 - Ei vastaa lainkaan", 10350: "5 - Vastaa erittäin hyvin",
             10351: "En osaa sanoa"}
    got = _series(scale)
    assert got.categories == ("1 - Ei vastaa lainkaan", "2", "3", "4",
                              "5 - Vastaa erittäin hyvin")
    assert got.caption is None
