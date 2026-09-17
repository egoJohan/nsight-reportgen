"""Which variables may be a combo's MEAN secondary.

"En ymmärrä ikäluokan kuvaustapaa": a combo drew "Ikäluokka" as bars reading
55.1 / 59.1 / 59.6. Those are the mean of the LEADING NUMBERS of the age
brackets ("18-24", "25-34" … "75+") — not an average age, not a scale point,
and nothing a reader can act on. The rule offered any variable whose labels
start with a digit; a bracket is not a scale. `_is_likert_scale` already drew
that line for the classifier picker ("bracket categoricals … are NOT a 1..N
sequence"), and this is the same line. (2026-09-17)
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.api.routes_questions import _aggregatable
from reportbuilder.model.question import ValueLabel, Variable

pytestmark = pytest.mark.unit


def _var(labels, measurement="categorical"):
    return Variable("v", "v", measurement,
                    tuple(ValueLabel(float(i + 1), l) for i, l in enumerate(labels)),
                    frozenset())


def test_an_age_bracket_is_not_a_mean():
    assert _aggregatable(_var(["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75+"])) is False


def test_a_spend_bracket_is_not_a_mean():
    assert _aggregatable(_var(["alle 500 €", "500-999 €", "1000-4999 €", "5000+ €"])) is False


def test_a_numbered_rating_is_a_mean():
    assert _aggregatable(_var(["1 Täysin eri mieltä", "2", "3", "4", "5 Täysin samaa mieltä"])) is True


def test_a_scale_labelled_only_at_its_ends_is_a_mean():
    assert _aggregatable(_var(["1 = Erittäin huonosti", "5 = Erittäin hyvin"])) is True


def test_a_numeric_index_is_a_mean():
    assert _aggregatable(Variable("idx", "idx", "scale", (), frozenset())) is True


def test_a_word_labelled_question_is_not_a_mean():
    assert _aggregatable(_var(["Kyllä", "Ei"])) is False


def test_an_unlabelled_score_is_a_mean_when_the_data_shows_a_scale():
    """NPS: 1–10, no labels of any kind. Its mean is the finding."""
    nps = Variable("NPS", "NPS", "categorical", (), frozenset())
    df = pd.DataFrame({"NPS": [1.0, 2.0, 3.0, 5.0, 7.0, 8.0, 9.0, 10.0, 10.0]})
    assert _aggregatable(nps, df) is True


def test_an_unlabelled_flag_is_not_a_mean():
    flag = Variable("Perus", "Perus", "categorical", (), frozenset())
    assert _aggregatable(flag, pd.DataFrame({"Perus": [0.0, 1.0, 1.0]})) is False
