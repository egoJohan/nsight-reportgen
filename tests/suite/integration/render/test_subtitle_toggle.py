"""Turning the subtitle off.

Reported: "jos subtitlen poistaa (korvaa välilyönnillä), niin edellinen subtitle
jää näkyviin". Clearing the box did not clear the line — blank means "use the
QUESTION", which is the right default and left no way to say "no subtitle at
all". Rendering with slide_description of null, "" and " " produced three
byte-identical images.

So it is a toggle, beside the ones for the title, the legend and the n-line,
rather than a magic value in the text box: an author who wants no subtitle says
so, and an author who empties the box still gets the sensible default back.
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

QUESTION = "Kuinka tyytyväinen olet palveluun kokonaisuutena?"


def _model():
    var = Variable(name="q1", label=QUESTION, measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Kyllä"), ValueLabel(2.0, "Ei")),
                   missing_values=frozenset())
    return QuestionModel(
        variables={"q1": var},
        questions=[Question(qid="q1", kind="single", variables=("q1",), text=QUESTION)])


def _texts(elements: ElementToggles, description=None):
    model = _model()
    spec = ChartSpec(
        question_ref="q1", chart_type="horizontal_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=elements,
        slide_title="Enemmistö on tyytyväinen",   # distinct, so a subtitle applies
        slide_description=description,
    )
    report = Report(name="r", render_mode="image", template_ref="", charts=(spec,))
    df = pd.DataFrame({"q1": [1.0] * 7 + [2.0] * 3})
    slide = build_presentation(report, model, df).slides[0]
    return " || ".join(sh.text_frame.text for sh in slide.shapes
                       if sh.has_text_frame and sh.text_frame.text.strip())


def test_the_question_is_the_subtitle_by_default():
    assert QUESTION in _texts(ElementToggles())


def test_an_authored_subtitle_replaces_it():
    out = _texts(ElementToggles(), description="Oma alaotsikko")
    assert "Oma alaotsikko" in out and QUESTION not in out


def test_turning_it_off_leaves_no_subtitle_at_all():
    out = _texts(ElementToggles(subtitle=False))
    assert QUESTION not in out


def test_turning_it_off_drops_an_authored_one_too():
    """Off means off — not "off unless you typed something"."""
    out = _texts(ElementToggles(subtitle=False), description="Oma alaotsikko")
    assert "Oma alaotsikko" not in out


def test_the_headline_is_untouched_by_it():
    assert "Enemmistö on tyytyväinen" in _texts(ElementToggles(subtitle=False))
