"""A word can be taken out of a cloud.

The merge editor already folds variant tokens together ("esperi" + "esper" →
"Esperi"). The other half of the same cleaning job is throwing a word away: a
survey's open answers are full of tokens that are not findings — the client's
own name repeated in every answer, a stray "kyllä", a word the stop list does
not know. Until now the only way to lose one was to merge it into something
else, which is a lie about the data.

Dropping is applied AFTER merging, so it works on what the editor SHOWS: a raw
token in the pool, or a group's label. Dropping a merged label removes the
whole group, which is what "remove this word from the cloud" means when the
word on the cloud is that label. (Johan, 2026-09-10)
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.ingest.sav_reader import Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats.engine import _wordcloud


def _model(*, merges=(), dropped=()):
    var = Variable(name="avoin", label="Kerro omin sanoin", measurement="text",
                   value_labels=[], missing_values=[])
    answers = (["esperi on hyvä"] * 5 + ["esper hoitaa hyvin"] * 3
               + ["hoiva toimii"] * 4 + ["kallis mutta hyvä"] * 6)
    df = pd.DataFrame({"avoin": answers})
    q = Question(qid="avoin", text="Kerro omin sanoin", kind="single",
                 variables=("avoin",), value_merges=tuple(merges),
                 dropped_words=tuple(dropped))
    model = QuestionModel(variables={"avoin": var}, questions=[q])
    return q, df, model


def _spec():
    return ChartSpec(question_ref="avoin", chart_type="wordcloud", statistic="count",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())


def _words(**kw) -> list[str]:
    q, df, model = _model(**kw)
    return list(_wordcloud(q, _spec(), df, model).categories)


def test_the_cloud_has_the_words_to_begin_with():
    words = _words()
    assert "hyvä" in words and "esperi" in words


def test_a_dropped_word_is_gone():
    words = _words(dropped=("hyvä",))
    assert "hyvä" not in words
    assert "esperi" in words, "only the named word should go"


def test_dropping_is_case_insensitive_like_the_tokens():
    """Tokens are lowercased when counted; an author types what they see."""
    assert "hyvä" not in _words(dropped=("Hyvä",))


def test_a_merged_group_can_be_dropped_by_its_label():
    """The cloud shows the label, so that is what "remove this word" names."""
    merged = _words(merges=(("Esperi", ("esperi", "esper")),))
    assert "Esperi" in merged
    after = _words(merges=(("Esperi", ("esperi", "esper")),), dropped=("Esperi",))
    assert "Esperi" not in after
    assert "esperi" not in after and "esper" not in after, "the members go too"


def test_dropping_everything_is_refused_rather_than_drawn_empty():
    """An empty cloud is not a chart. The builder already raises when a question
    has no words; dropping them all must land in the same place."""
    q, df, model = _model(dropped=("hyvä", "esperi", "esper", "hoiva", "toimii",
                                   "hoitaa", "hyvin", "kallis", "mutta"))
    with pytest.raises(ValueError):
        _wordcloud(q, _spec(), df, model)


def test_dropping_does_not_change_the_respondent_base():
    """The base is people who answered, not words drawn. Someone whose only
    word was removed still answered the question."""
    q, df, model = _model()
    before = _wordcloud(q, _spec(), df, model).base_n["Total"]
    q2, df2, model2 = _model(dropped=("hyvä",))
    assert _wordcloud(q2, _spec(), df2, model2).base_n["Total"] == before
