"""Task J.1: word-cloud frequency engine path (stats.engine._wordcloud).

A free-text question is routed to the word-frequency path when chart_type=="wordcloud".
The resulting SeriesResult carries the answer words as categories and their frequencies
as count cells. Numbers stay deterministic.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder import config
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.question import Question, QuestionModel, Variable
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    SortSpec,
)
from reportbuilder.stats.engine import compute, _wordcloud


def _spec(chart_type: str = "wordcloud", **kw) -> ChartSpec:
    return ChartSpec(
        question_ref="q",
        chart_type=chart_type,
        statistic=kw.get("statistic", "count"),
        classifying_var=kw.get("classifying_var", None),
        number_format=kw.get("number_format", NumberFormat()),
        sort=kw.get("sort", SortSpec(basis="data_order")),
        template_slot="s",
        elements=ElementToggles(),
        category_label_overrides=kw.get("category_label_overrides", ()),
    )


def _text_var(name: str) -> Variable:
    return Variable(name=name, label=name, measurement="text",
                    value_labels=(), missing_values=frozenset())


# ---------------------------------------------------------------------------
# Synthetic-data unit tests (no fixture dependency)
# ---------------------------------------------------------------------------


def _synthetic_model() -> tuple[QuestionModel, pd.DataFrame, Question]:
    """A 2-column multi text question with a controlled vocabulary."""
    variables = {"c1": _text_var("c1"), "c2": _text_var("c2")}
    q = Question(qid="q", kind="multi", variables=("c1", "c2"), text="Describe")
    model = QuestionModel(variables=variables, questions=[q])
    df = pd.DataFrame({
        "c1": ["kallis ja huono", "kallis ei", "hyvä", "", None, "kallis 123"],
        "c2": ["luotettava", "kallis", "ok ei en", "huono", "hyvä", None],
    })
    return model, df, q


def test_wordcloud_counts_descend_and_top_word():
    model, df, q = _synthetic_model()
    sr = compute(q, _spec(), df, model)
    assert sr.statistic == "count"
    assert sr.segments == ("Total",)
    # "kallis" appears 4×, the most frequent → first category.
    assert sr.categories[0] == "kallis"
    assert sr.cell("kallis", "Total").count == 4.0
    counts = [sr.cell(c, "Total").count for c in sr.categories]
    assert all(counts[i] >= counts[i + 1] for i in range(len(counts) - 1))


def test_wordcloud_drops_stopwords_short_and_numbers():
    model, df, q = _synthetic_model()
    sr = compute(q, _spec(), df, model)
    cats = set(sr.categories)
    # Finnish stopwords dropped.
    assert "ja" not in cats and "ei" not in cats and "en" not in cats
    # Short tokens (<3 chars) dropped: "ok" and the bare number "123".
    assert "ok" not in cats
    assert "123" not in cats
    assert all(len(c) >= 3 for c in sr.categories)


def test_wordcloud_base_n_counts_responding_respondents():
    model, df, q = _synthetic_model()
    sr = compute(q, _spec(), df, model)
    # 6 rows; the row with c1="" and c2="hyvä" still answered (c2). Only a fully
    # blank/None row would NOT count — there is none here → all 6 respondents.
    assert sr.base_n["Total"] == 6


def test_wordcloud_deterministic_across_runs():
    model, df, q = _synthetic_model()
    a = _wordcloud(q, _spec(), df, model)
    b = _wordcloud(q, _spec(), df, model)
    assert a.categories == b.categories
    assert [a.cell(c, "Total").count for c in a.categories] == \
           [b.cell(c, "Total").count for c in b.categories]


def test_wordcloud_no_words_raises_value_error():
    model, df, q = _synthetic_model()
    # All answers are stopwords / too short / numbers → no usable words.
    empty = pd.DataFrame({"c1": ["ja ei en", "1 2 3", ""], "c2": ["ok", "on", None]})
    with pytest.raises(ValueError, match="No text answers to build a word cloud"):
        compute(q, _spec(), empty, model)


def test_wordcloud_on_non_text_numeric_question_yields_clean_error():
    """A wordcloud requested on a numeric question has no string answers → clean error."""
    var = Variable(name="age", label="Age", measurement="scale",
                   value_labels=(), missing_values=frozenset())
    q = Question(qid="age", kind="single", variables=("age",), text="Age")
    model = QuestionModel(variables={"age": var}, questions=[q])
    df = pd.DataFrame({"age": [21.0, 35.0, 48.0]})
    with pytest.raises(ValueError, match="No text answers to build a word cloud"):
        compute(q, _spec(), df, model)


def test_wordcloud_applies_category_label_overrides():
    model, df, q = _synthetic_model()
    sr = compute(q, _spec(category_label_overrides=(("kallis", "EXPENSIVE"),)), df, model)
    assert "EXPENSIVE" in sr.categories
    assert "kallis" not in sr.categories
    assert sr.cell("EXPENSIVE", "Total").count == 4.0


# ---------------------------------------------------------------------------
# Real Attendo fixture: var37 ("Millä kolmella sanalla kuvailisit…")
# ---------------------------------------------------------------------------


def test_var37_wordcloud_top_word_and_descending():
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")
    df, model = read_sav(str(config.ATTENDO_SAV))
    # var37 spans three free-text columns — combine them into one multi question.
    members = ("var37O67", "var37O68", "var37O69")
    assert all(model.variables[m].measurement == "text" for m in members)
    q = Question(qid="var37", kind="multi", variables=members, text="Three words")

    sr = compute(q, _spec(), df, model)
    assert sr.statistic == "count"
    # "kallis" is by far the most frequent word (185×) → top category.
    assert sr.categories[0] == "kallis"
    assert sr.cell("kallis", "Total").count == 185.0
    counts = [sr.cell(c, "Total").count for c in sr.categories]
    assert all(counts[i] >= counts[i + 1] for i in range(len(counts) - 1))
    # Stopwords removed even though they are frequent in the raw data.
    assert "en" not in sr.categories and "ei" not in sr.categories
    assert all(len(c) >= 3 for c in sr.categories)
    # Top-N cap.
    assert len(sr.categories) <= 60
    # Deterministic.
    sr2 = compute(q, _spec(), df, model)
    assert sr2.categories == sr.categories


# ---------------------------------------------------------------------------
# Value merges (data cleaning): fold variant tokens into one word, summing counts
# ---------------------------------------------------------------------------


def test_wordcloud_merges_variant_tokens_and_sums_counts():
    variables = {"c1": _text_var("c1")}
    # esperi ×3, esper ×2 → merged display "Esperi" with count 5.
    q = Question(
        qid="q", kind="single", variables=("c1",), text="Brand",
        value_merges=(("Esperi", ("esperi", "esper")),),
    )
    model = QuestionModel(variables=variables, questions=[q])
    df = pd.DataFrame(
        {"c1": ["esperi", "esperi", "esperi", "esper", "esper", "attendo"]}
    )
    sr = compute(q, _spec(), df, model)
    assert sr.categories[0] == "Esperi"
    assert sr.cell("Esperi", "Total").count == 5.0
    # the raw variants are gone as separate words; unmerged word stays
    assert "esperi" not in sr.categories and "esper" not in sr.categories
    assert "attendo" in sr.categories


def test_wordcloud_no_merges_is_unchanged():
    variables = {"c1": _text_var("c1")}
    q = Question(qid="q", kind="single", variables=("c1",), text="Brand")
    model = QuestionModel(variables=variables, questions=[q])
    df = pd.DataFrame({"c1": ["esperi", "esper", "attendo"]})
    sr = compute(q, _spec(), df, model)
    assert set(sr.categories) == {"esperi", "esper", "attendo"}
