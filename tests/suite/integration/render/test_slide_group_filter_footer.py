"""A slide drawn on part of the sample has to say so.

The base line already carries this kind of disclosure — when a pie drops a panel
whose base was too thin, the footer says which groups are missing, because image
mode has no separate "classifying variable" box the way the native builder has.
A slide computed on one group of the classifier is the same promise: N counts
those respondents and nobody else, and a reader who is not told reads the slide
as the whole study.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.export.pptx_build import build_presentation
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, Report, SortSpec,
)

pytestmark = pytest.mark.integration

QUESTION = "Suositteletko?"


def _model():
    q1 = Variable(name="q1", label=QUESTION, measurement="categorical",
                  value_labels=(ValueLabel(1.0, "Kyllä"), ValueLabel(2.0, "Ei")),
                  missing_values=frozenset())
    polku = Variable(name="polku", label="Polku", measurement="categorical",
                     value_labels=(ValueLabel(1.0, "Design 1"), ValueLabel(2.0, "Design 2"),
                                   ValueLabel(3.0, "Design 3")),
                     missing_values=frozenset())
    return QuestionModel(
        variables={"q1": q1, "polku": polku},
        questions=[Question(qid="q1", kind="single", variables=("q1",), text=QUESTION)])


def _texts(classifying_values=()):
    spec = ChartSpec(
        question_ref="q1", chart_type="horizontal_bar", statistic="pct",
        classifying_var="polku", number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles(), classifying_values=classifying_values)
    report = Report(name="r", render_mode="image", template_ref="", charts=(spec,))
    df = pd.DataFrame({"q1": ([1.0] * 6 + [2.0] * 4) * 3,
                       "polku": [1.0] * 10 + [2.0] * 10 + [3.0] * 10})
    slide = build_presentation(report, _model(), df).slides[0]
    return " || ".join(sh.text_frame.text for sh in slide.shapes
                       if sh.has_text_frame and sh.text_frame.text.strip())


def test_the_whole_sample_says_nothing_extra():
    out = _texts()
    assert "N = 30" in out
    assert "Design 1" not in out.split("N = 30")[1]


def test_one_group_is_named_on_the_base_line():
    out = _texts(("Design 1",))
    assert "N = 10" in out, out
    assert "Design 1" in out, out


def test_a_partial_selection_names_every_group_it_kept():
    out = _texts(("Design 1", "Design 3"))
    assert "N = 20" in out, out
    assert "Design 1" in out and "Design 3" in out, out


def test_naming_every_group_draws_the_whole_sample():
    """Ticking all three is the same DATA as ticking none — the rows are not
    narrowed. It still says which groups it names, which is accurate; the picker
    keeps the state from arising by storing no restriction when all are ticked."""
    out = _texts(("Design 1", "Design 2", "Design 3"))
    assert "N = 30" in out, out


def test_a_group_that_no_longer_exists_is_not_claimed_on_the_slide():
    """The engine ignores a selection it cannot resolve — the data changed under
    a saved slide, and a blank chart helps nobody — so the slide is the whole
    sample. The footer said otherwise: it printed the stale name beside a base
    covering everyone, which is a slide asserting something untrue about itself.

    Not an exotic path: nothing clears the selection when the classifying
    variable changes, so any slide reclassified after being filtered carries
    names from the old variable.
    """
    out = _texts(("Design 9",))
    assert "N = 30" in out, out
    assert "Design 9" not in out, out
