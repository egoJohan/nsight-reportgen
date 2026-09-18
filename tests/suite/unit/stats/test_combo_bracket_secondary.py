"""A combo does not invent a mean for a variable that has none.

`_aggregatable` (the questions API) settled this on 2026-09-17: a BRACKET is
not a scale. "18-24", "500-999 €" — the numbers their labels start with are
quantities, and averaging them produced "Ikäluokka 55.1" on a slide nobody
could read. Such a variable is offered as a combo secondary only as the SHARE
of one of its groups ("% 55-64"), which is a number about people.

The picker stopped offering the mean that day. The RENDERER was never told, so
a slide saved before it kept drawing one — and the same complaint came back the
next morning, in the same words: "en ymmärrä ikäluokan kuvaustapaa"
(2026-09-18).

With no group chosen there is nothing honest to draw for such a variable, and
guessing a group would be inventing the author's intent. The secondary is left
out, which is what the editor's own group picker — sitting there unanswered —
is already asking them to fix.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats.engine import compute

_SENTIMENT = ["Negatiivisia", "Neutraaleja", "Positiivisia"]
_BANDS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75+"]
_RATING = ["1 - Täysin eri mieltä", "2", "3", "4", "5 - Täysin samaa mieltä"]


def _series(sec_labels: list[str], *, group: str | None = None,
            sec_measurement: str = "categorical"):
    q = Variable(name="q", label="Ajatuksia", measurement="nominal",
                 missing_values=[],
                 value_labels=[ValueLabel(value=float(i + 1), label=c)
                               for i, c in enumerate(_SENTIMENT)])
    sec = Variable(name="sec", label="Ikäluokka", measurement=sec_measurement,
                   missing_values=[],
                   value_labels=[ValueLabel(value=float(i + 1), label=l)
                                 for i, l in enumerate(sec_labels)])
    rows = [{"q": float(i % 3 + 1), "sec": float(i % len(sec_labels) + 1)}
            for i in range(600)]
    model = QuestionModel(
        variables={"q": q, "sec": sec},
        questions=[Question(qid="q", text=q.label, kind="single", variables=("q",)),
                   Question(qid="sec", text=sec.label, kind="single", variables=("sec",))])
    opts = {"combo_secondary": "sec"}
    if group:
        opts["combo_secondary_value"] = group
    spec = ChartSpec(question_ref="q", chart_type="combo", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles(), options=opts)
    return compute(model.question("q"), spec, pd.DataFrame(rows), model)


def _secondary_segments(s) -> list[str]:
    """The segments that are NOT the question's own distribution."""
    return [seg for seg in s.segments
            if s.statistic_of(seg) != s.statistic or "%" in seg or "Ikäluokka" in seg]


def test_a_bracket_with_no_group_draws_no_secondary():
    """The reported slide. Nothing about the age bands can be averaged, so
    nothing is drawn for them."""
    s = _series(_BANDS)
    assert not [seg for seg in s.segments if "Ikäluokka" in seg], s.segments


def test_the_question_itself_is_still_drawn():
    """Losing the secondary must not lose the slide."""
    s = _series(_BANDS)
    assert list(s.categories) == _SENTIMENT
    assert any(s.cell(c, seg).value("pct") is not None
               for c in s.categories for seg in s.segments)


def test_a_bracket_WITH_a_group_draws_that_share():
    """The configuration the picker asks for, and what the author wants: the
    share of one age band per sentiment."""
    s = _series(_BANDS, group="65-74")
    named = [seg for seg in s.segments if "Ikäluokka" in seg]
    assert named, s.segments
    assert "%" in named[0] and "65-74" in named[0], named


def test_a_real_rating_scale_still_gets_its_mean():
    """The control: 1..5 rating points ARE a scale, and its mean is the whole
    point of a combo's second axis."""
    s = _series(_RATING)
    assert [seg for seg in s.segments if "Ikäluokka" in seg], s.segments


def test_a_plain_numeric_variable_still_gets_its_mean():
    """Age in YEARS, not in bands: a real number, and its mean is real too."""
    q = Variable(name="q", label="Ajatuksia", measurement="nominal",
                 missing_values=[],
                 value_labels=[ValueLabel(value=float(i + 1), label=c)
                               for i, c in enumerate(_SENTIMENT)])
    sec = Variable(name="sec", label="Ikä", measurement="scale",
                   missing_values=[], value_labels=[])
    rows = [{"q": float(i % 3 + 1), "sec": float(20 + i % 50)} for i in range(600)]
    model = QuestionModel(
        variables={"q": q, "sec": sec},
        questions=[Question(qid="q", text=q.label, kind="single", variables=("q",)),
                   Question(qid="sec", text=sec.label, kind="single", variables=("sec",))])
    spec = ChartSpec(question_ref="q", chart_type="combo", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles(), options={"combo_secondary": "sec"})
    s = compute(model.question("q"), spec, pd.DataFrame(rows), model)
    assert "Ikä" in s.segments, s.segments
    assert s.statistic_of("Ikä") == "mean"
