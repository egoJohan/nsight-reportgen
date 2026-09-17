"""A scale whose middle points are labelled with their own numbers is a scale.

A stacked bar shortens a numeric rating scale's legend to bare numbers on the
promise that the endpoint WORDING moves to the caption above the footer. The
two rules that decide this never agreed on what a rating scale is:

  * the legend shortens when every level starts with its point number
    ("1- Ei lainkaan ylpeä", "2", … "7- Erittäin ylpeä" — all do);
  * `_partial_scale` builds the caption only when some point carries NO value
    label at all.

This SAV labels its middle points with their own number, so `_partial_scale`
saw a fully-labelled variable, produced no caption — and the legend threw the
endpoint words away with nothing to catch them. The slide showed a seven-point
scale as "1 2 3 4 5 6 7" and said nowhere which end was which. The same
question drawn as a PIE kept the words, because a pie does not shorten.

A label that is merely its own number carries no words, which is the same
situation as no label at all.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats.engine import compute

_LOW = "1- Ei lainkaan ylpeä"
_HIGH = "7- Erittäin ylpeä"


def _series(labels: dict[int, str], chart_type: str = "stacked_horizontal_bar"):
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
                     elements=ElementToggles())
    return compute(model.question("q"), spec, pd.DataFrame(rows), model)


#: 1 and 7 carry words; 2..6 are labelled with their own number.
NUMBERED_MIDDLE = {1: _LOW, 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: _HIGH}
#: 1 and 7 carry words; 2..6 have no value label at all — already handled.
UNLABELLED_MIDDLE = {1: _LOW, 7: _HIGH}


def test_the_unlabelled_middle_case_still_names_its_endpoints():
    """The case that always worked, so a regression here is visible."""
    caption = _series(UNLABELLED_MIDDLE).caption
    assert caption and "Ei lainkaan ylpeä" in caption and "Erittäin ylpeä" in caption


def test_a_numbered_middle_names_its_endpoints_too():
    caption = _series(NUMBERED_MIDDLE).caption
    assert caption, "no caption: the endpoint wording is nowhere on the slide"
    assert "Ei lainkaan ylpeä" in caption and "Erittäin ylpeä" in caption


def test_the_caption_does_not_repeat_the_number():
    """The label already begins with its own point number, so "1 = 1- Ei …"
    would print it twice."""
    caption = _series(NUMBERED_MIDDLE).caption
    assert "1 = 1-" not in caption, caption
    assert "7 = 7-" not in caption, caption


def test_a_word_only_scale_is_left_alone():
    """Every level named in words is NOT this case: the legend keeps the words,
    so nothing has to be moved to a caption."""
    words = {1: "Täysin eri mieltä", 2: "Jokseenkin eri mieltä",
             3: "Ei samaa eikä eri mieltä", 4: "Jokseenkin samaa mieltä",
             5: "Täysin samaa mieltä"}
    assert not _series(words).caption


def test_the_categories_are_still_the_scales_points():
    """Reclassifying must not change what the chart draws."""
    got = _series(NUMBERED_MIDDLE)
    assert len(got.categories) == 7, got.categories
