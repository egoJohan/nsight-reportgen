"""Removing a word is saved and served beside the merges.

Same endpoint and the same Save as the merge editor, because folding variants
together and throwing a stray word away are one job: cleaning the tokens an
open question produced. (Johan, 2026-09-10)
"""
from __future__ import annotations

import pytest

from reportbuilder.api.model_loader import _dropped_from_cfg


def test_the_config_shape_normalises_blanks_away():
    cfg = {"dropped_words": {"avoin": ["hyvä", "  ", "", "kyllä"]}}
    assert _dropped_from_cfg(cfg) == {"avoin": ("hyvä", "kyllä")}


def test_a_question_with_nothing_removed_is_absent_not_empty():
    """"Nothing removed" is the default and must not be a value every reader
    has to recognise."""
    assert _dropped_from_cfg({"dropped_words": {"avoin": []}}) == {}
    assert _dropped_from_cfg({}) == {}
    assert _dropped_from_cfg({"dropped_words": "nonsense"}) == {}


def test_the_request_body_accepts_both_halves():
    from reportbuilder.api.routes_questions import WordMergesBody

    body = WordMergesBody(merges=[], dropped=["hyvä"])
    assert body.dropped == ["hyvä"]
    assert WordMergesBody().dropped == []


def test_curation_puts_them_on_the_question():
    """The engine reads `question.dropped_words`, so the loader has to set it —
    on every path that assembles a model, not just the wizard's."""
    import dataclasses

    from reportbuilder.api.model_loader import _apply_dropped
    from reportbuilder.model.question import Question, QuestionModel

    q = Question(qid="avoin", text="Avoin", kind="single", variables=("avoin",))
    model = QuestionModel(variables={}, questions=[q])

    out = _apply_dropped(model, {"avoin": ("hyvä",)})

    assert out.question("avoin").dropped_words == ("hyvä",)
    # untouched questions keep the empty default
    assert _apply_dropped(model, {}).question("avoin").dropped_words == ()
