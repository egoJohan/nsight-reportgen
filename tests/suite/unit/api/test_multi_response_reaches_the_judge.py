"""A brand tracker's options reach the model that decides which are companies.

The proposer reading multi-response options is only half the protection: the
endpoint hands its candidates to `pick_company_terms`, and a study whose brands
never became candidates never reached that judgement either. On the Taffel study
the proposal was nineteen product ATTRIBUTES from one rating battery, the model
correctly called none of them a company, and an analyst was shown an empty list
for a study naming eighteen brands.

Measured after the fix, against the real material and the real model: 66
candidates in, 18 brands out — `Taffel`, `Estrella`, `Pringles`, `Pirkka`,
`Coop`, `Kettle`, `Snack Day`, `Pipers`, `Gårdchips`, `Weekend Snacks`,
`Cheetos`, `Lay's`, `OLW`, `Poppamies`, `Red Head`, `Xtra`, `Oikia`. That run
needs a hive; this one pins the wiring without one. (Johan, 2026-09-14)
"""
from __future__ import annotations

import json

from reportbuilder.ai.text import pick_company_terms
from reportbuilder.ingest.sensitive_terms import propose_from_models
from reportbuilder.model.question import (
    Question, QuestionModel, ValueLabel, Variable,
)

#: What a chip tracker's "which of these do you buy" question enumerates: real
#: brands beside the study's own non-answers and a flavour category.
_OPTIONS = ("Taffel", "Estrella", "Pringles", "Pirkka", "Coop",
            "Linssisipsit", "En mitään näistä")
_BRANDS = {"Taffel", "Estrella", "Pringles", "Pirkka", "Coop"}


def _model() -> QuestionModel:
    variables = {
        f"var12O{i}": Variable(
            name=f"var12O{i}", label=option, measurement="categorical",
            value_labels=(ValueLabel(0.0, "Unchecked"), ValueLabel(1.0, "Checked")),
            missing_values=frozenset())
        for i, option in enumerate(_OPTIONS)
    }
    question = Question(qid="var12", kind="multi", variables=tuple(variables),
                        text="Mitä seuraavista sipsimerkeistä ostat?")
    return QuestionModel(variables=variables, questions=[question])


def _judge(reply: list[str]):
    """A stand-in for the model, recording what it was asked to judge."""
    seen: dict = {}

    def chat(prompt: str, **_kw) -> str:
        seen["prompt"] = prompt
        return json.dumps(reply, ensure_ascii=False)

    return chat, seen


def test_the_brands_are_among_the_candidates_the_judge_is_given():
    """The failure this guards: the judge answered honestly about a list that
    never contained a brand, and the analyst read the empty result as safety."""
    model = _model()
    candidates = propose_from_models(model, model)
    missing = sorted(_BRANDS - set(candidates))
    assert not missing, f"never offered to the model: {missing}"


def test_the_judge_decides_and_its_answer_is_what_is_returned():
    model = _model()
    candidates = propose_from_models(model, model)
    chat, seen = _judge(["Taffel", "Estrella", "Pringles", "Pirkka", "Coop"])

    picked = pick_company_terms(candidates, ["Mitä seuraavista ostat?"], chat=chat)

    assert set(picked) == _BRANDS
    for brand in _BRANDS:
        assert brand in seen["prompt"], f"{brand!r} was not put to the model"


def test_a_flavour_category_is_offered_and_may_be_rejected():
    """Recall is the proposer's job; the rejecting is the model's. Offering
    `Linssisipsit` costs a sentence, missing `Estrella` costs the masking."""
    model = _model()
    candidates = propose_from_models(model, model)
    assert "Linssisipsit" in candidates

    chat, _seen = _judge(["Taffel", "Estrella", "Pringles", "Pirkka", "Coop"])
    picked = pick_company_terms(candidates, [], chat=chat)
    assert "Linssisipsit" not in picked


def test_the_studys_own_non_answer_is_never_a_candidate():
    """"En mitään näistä" opens with a non-answer and is dropped before the
    model is troubled with it."""
    model = _model()
    assert "En mitään näistä" not in propose_from_models(model, model)
