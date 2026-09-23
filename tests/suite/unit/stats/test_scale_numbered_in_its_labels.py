"""A scale numbered in its own labels keeps its words on the chart itself.

"1- Ei lainkaan ylpeä", "2", … "7- Erittäin ylpeä" is labelled on every point.
A stacked bar used to shorten that legend to 1 2 3 4 5 6 7 and move the
endpoint wording to a caption at the foot. The legend now draws the labels as
they are (2026-09-23, "Category labelsin määritys ei siirry oikein
legendiin"), so every chart type prints the words itself and no caption
repeats them.

A scale whose middle points carry NO label at all is a different case and is
unchanged: it is charted as its points "1".."7" — which is also what Category
labels lists — and the endpoint wording is captioned.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats.engine import compute

_LOW = "1- Ei lainkaan ylpeä"
_HIGH = "7- Erittäin ylpeä"


def _series(labels: dict[int, str], chart_type: str = "stacked_horizontal_bar",
            overrides: tuple = ()):
    var = Variable(name="q", label="Kuinka ylpeä olet omasta työstäsi?",
                   measurement="nominal", missing_values=[],
                   value_labels=[ValueLabel(value=float(c), label=l)
                                 for c, l in sorted(labels.items())])
    # People answer across the WHOLE scale; what varies between these cases is
    # only which of its points carry a label. Generating responses on the
    # labelled codes alone turned a 1..7 labelled at its ends into a two-point
    # variable, which is a different thing entirely.
    weights = [31, 31, 71, 112, 234, 316, 224]
    codes = range(min(labels), max(labels) + 1)
    rows = [{"q": float(c)}
            for i, c in enumerate(codes)
            for _ in range(weights[i % len(weights)])]
    model = QuestionModel(
        variables={"q": var},
        questions=[Question(qid="q", text=var.label, kind="single", variables=("q",))])
    spec = ChartSpec(question_ref="q", chart_type=chart_type, statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles(),
                     category_label_overrides=overrides)
    return compute(model.question("q"), spec, pd.DataFrame(rows), model)


#: 1 and 7 carry words; 2..6 are labelled with their own number.
NUMBERED_MIDDLE = {1: _LOW, 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: _HIGH}
#: 1 and 7 carry words; 2..6 have no value label at all — already handled.
UNLABELLED_MIDDLE = {1: _LOW, 7: _HIGH}


CHART_TYPES = ("stacked_horizontal_bar", "stacked_vertical_bar", "horizontal_bar", "pie")


def test_a_numbered_middle_keeps_its_words_as_the_categories():
    for ct in CHART_TYPES:
        got = _series(NUMBERED_MIDDLE, ct)
        assert got.categories == (_LOW, "2", "3", "4", "5", "6", _HIGH), ct


def test_a_numbered_middle_is_not_captioned():
    """The words are already on the chart; a caption would be a second copy."""
    for ct in CHART_TYPES:
        assert not _series(NUMBERED_MIDDLE, ct).caption, ct


def test_the_unlabelled_middle_case_is_captioned_everywhere_still():
    for ct in CHART_TYPES:
        caption = _series(UNLABELLED_MIDDLE, ct).caption
        assert caption and "Ei lainkaan ylpeä" in caption and "Erittäin ylpeä" in caption, ct


def test_the_unlabelled_middle_case_is_charted_as_its_points():
    got = _series(UNLABELLED_MIDDLE)
    assert sorted(got.categories) == [str(n) for n in range(1, 8)], got.categories
