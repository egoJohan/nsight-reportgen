"""A BATTERY on a numbered scale must also say which end is which.

`_numbered_scale_caption` was added for the single-variable path: a stacked bar
shortens a numeric rating scale's legend to bare numbers, so the endpoint
wording moves to a caption above the footer. The battery path builds its own
SeriesResult and never asked for one — so Attendo's brand-image batteries, 14
statements over "1 - Ei vastaa lainkaan" … "5 - Vastaa täysin", drew a legend
reading "1 2 3 4 5" with nothing anywhere on the slide saying whether 5 was
good or bad. A battery is where a numbered scale is MOST common, and it was the
one path that lost the words.

Same rule as the single path, deliberately: the caption appears only where the
legend actually drops the words.
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


def _caption(scale, chart_type="stacked_horizontal_bar"):
    model, df = _model(scale)
    return compute(model.questions[0], _spec(chart_type), df, model).caption


def test_a_battery_on_an_endpoint_labelled_scale_captions_its_ends():
    assert _caption(_ENDPOINT) == "1 = Ei vastaa lainkaan · 5 = Vastaa täysin"


def test_no_caption_when_every_level_carries_its_own_words():
    """The legend keeps the words there, so a caption would repeat them."""
    assert _caption(_ALL_WORDED) is None


def test_the_scale_point_is_read_from_the_LABEL_not_the_sav_code():
    """Attendo's own export, var102: the middle points are coded 2, 3, 4 but the
    two ENDPOINTS sit on codes 10346 and 10350, with "En osaa sanoa" on 10351.
    The scale point is what the label says ("1 - ..."), which is how
    `battery_scale_levels` reads it; keying the caption on the SAV code instead
    asked 10346 to begin with "10346", and the real slide got no caption at all.
    """
    scale = {2: "2", 3: "3", 4: "4",
             10346: "1 - Ei vastaa lainkaan", 10350: "5 - Vastaa erittäin hyvin",
             10351: "En osaa sanoa"}
    assert _caption(scale) == "1 = Ei vastaa lainkaan · 5 = Vastaa erittäin hyvin"


def test_no_caption_for_a_chart_type_that_does_not_shorten_its_legend():
    """A plain bar prints the scale on the category axis in full."""
    assert _caption(_ENDPOINT, chart_type="horizontal_bar") is None
