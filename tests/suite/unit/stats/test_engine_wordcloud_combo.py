"""Unit tests for engine wordcloud path, text-not-chartable guard, and combo."""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.model.report import (
    ChartSpec, NumberFormat, SortSpec, ElementToggles,
)
from reportbuilder.stats import engine


def _spec(**kw):
    base = dict(question_ref="t", chart_type="vertical_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def _text_model():
    tv = Variable(name="t", label="Text", measurement="text",
                  value_labels=(), missing_values=frozenset())
    model = QuestionModel(variables={"t": tv}, questions=[])
    q = Question(qid="t", kind="single", variables=("t",), text="Text")
    return model, q


# ---- wordcloud -------------------------------------------------------------

def test_wordcloud_tokenizes_and_counts_frequencies():
    model, q = _text_model()
    df = pd.DataFrame({"t": ["hyvä palvelu palvelu", "loistava palvelu",
                             "en osaa sanoa", "123 45", "ok"]})
    r = engine.compute(q, _spec(chart_type="wordcloud"), df, model)
    assert r.statistic == "count"
    assert r.segments == ("Total",)
    # deterministic ordering: count desc then word asc
    assert r.categories == ("palvelu", "hyvä", "loistava")
    assert r.cell("palvelu", "Total").count == 3.0
    assert r.cell("hyvä", "Total").count == 1.0


def test_wordcloud_drops_stopwords_short_digits_and_nonanswers():
    model, q = _text_model()
    df = pd.DataFrame({"t": ["hyvä palvelu palvelu", "loistava palvelu",
                             "en osaa sanoa", "123 45", "ok"]})
    r = engine.compute(q, _spec(chart_type="wordcloud"), df, model)
    cats = set(r.categories)
    assert "ok" not in cats          # too short (<3)
    assert "123" not in cats and "45" not in cats  # digits
    assert "osaa" not in cats and "sanoa" not in cats  # non-answer whole phrase
    assert "ja" not in cats          # stopword (not present anyway)


def test_wordcloud_base_is_respondents_with_any_text():
    model, q = _text_model()
    df = pd.DataFrame({"t": ["hyvä palvelu palvelu", "loistava palvelu",
                             "en osaa sanoa", "123 45", "ok"]})
    r = engine.compute(q, _spec(chart_type="wordcloud"), df, model)
    # all 5 rows are non-empty strings
    assert r.base_n["Total"] == 5


def test_wordcloud_no_usable_words_raises_valueerror():
    model, q = _text_model()
    df = pd.DataFrame({"t": ["en osaa sanoa", "-", "?"]})
    with pytest.raises(ValueError):
        engine.compute(q, _spec(chart_type="wordcloud"), df, model)


# ---- text-not-chartable guard ----------------------------------------------

def test_all_text_question_non_wordcloud_raises_text_not_chartable():
    model, q = _text_model()
    df = pd.DataFrame({"t": ["hyvä palvelu", "loistava"]})
    with pytest.raises(ValueError) as ei:
        engine.compute(q, _spec(chart_type="vertical_bar"), df, model)
    assert str(ei.value) == engine.TEXT_NOT_CHARTABLE_MSG


# ---- combo two-var ---------------------------------------------------------

def test_combo_two_var_bars_pct_and_line_secondary_mean():
    primary = Variable("q", "Primary", "categorical",
                       (ValueLabel(1.0, "Low"), ValueLabel(2.0, "High")),
                       frozenset())
    sec = Variable("s", "Secondary", "scale", (), frozenset())
    model = QuestionModel(variables={"q": primary, "s": sec}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Primary")
    df = pd.DataFrame({"q": [1, 1, 2, 2], "s": [10.0, 20.0, 30.0, 50.0]})
    r = engine.compute(q, _spec(question_ref="q", chart_type="combo",
                                options={"combo_secondary": "s"}), df, model)
    assert r.categories == ("Low", "High")
    assert r.segments == ("Primary", "Secondary")
    # bars: distribution %
    assert r.cell("Low", "Primary").pct == 50.0
    assert r.cell("High", "Primary").pct == 50.0
    # line: secondary mean per category (stored in pct field for the renderer)
    assert r.cell("Low", "Secondary").pct == 15.0
    assert r.cell("High", "Secondary").pct == 40.0
