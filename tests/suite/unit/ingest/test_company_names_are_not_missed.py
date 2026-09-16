"""Recall beats tidiness: a name we fail to offer is a name that leaks.

"Sensitive Terms skippaa nyt sellaiset mahtavat yritysnimet kuin Amazon,
Salesforce, Aramco ja nSight."

Two rules were dropping real companies before the model ever saw them.

A value label had to appear in TWO questions to count. The reasoning was that a
brand recurs across the questions that ask about it while a one-off category is
the study's own wording — true of some studies, and fatal to the ordinary one
that asks "which of these companies do you know" exactly once. Every option in
it appeared a single time, so the study proposed nothing at all and the screen
said its structure named no companies.

And a term had to START with a capital. `nSight`, `eBay`, `iPhone` and `3M` are
all written the way their owners write them, and all four were refused.

`ai.text.pick_company_terms` decides; this module's job is to offer. An extra
candidate costs the model a sentence, a missing one costs the masking
everything it is for. (Johan, 2026-09-15)
"""
from __future__ import annotations

from reportbuilder.ingest.sensitive_terms import _candidate, propose_sensitive_terms
from reportbuilder.model.question import QuestionModel, ValueLabel, Variable


def _asked_once(*options: str) -> QuestionModel:
    """One question listing *options* — the shape that proposed nothing."""
    var = Variable(name="q1", label="Mitä seuraavista yrityksistä tunnet?",
                   measurement="categorical",
                   value_labels=tuple(ValueLabel(float(i + 1), o)
                                      for i, o in enumerate(options)),
                   missing_values=frozenset())
    return QuestionModel(variables={"q1": var}, questions=[])


_REPORTED = ("Amazon", "Salesforce", "Aramco", "nSight")


def test_the_four_names_from_the_report_are_offered():
    proposed = set(propose_sensitive_terms(_asked_once(*_REPORTED)))
    missing = [n for n in _REPORTED if n not in proposed]
    assert not missing, f"still dropped: {missing}"


def test_a_company_named_once_is_enough():
    """The rule that caused it: a value label needed a second question."""
    assert "Amazon" in propose_sensitive_terms(_asked_once("Amazon", "En osaa sanoa"))


def test_a_name_that_does_not_start_with_a_capital_is_still_a_name():
    """nSight, eBay, iPhone — written the way their owners write them."""
    for name in ("nSight", "eBay", "iPhone"):
        assert _candidate(name) == name, f"{name!r} was refused"


def test_a_name_that_starts_with_a_digit_is_still_a_name():
    assert _candidate("3M") == "3M"


def test_a_brand_whose_name_ends_like_a_case_ending_is_offered():
    """`Estrella` ends in `-lla`, which the inflection rule reads as an adessive.
    A multi-response option list is already exempt, because its members stand in
    the nominative; the value labels of a single-choice question are the same
    kind of list and were not. Estrella is the brand that rule was written to
    protect, and it was being dropped through the other door."""
    proposed = propose_sensitive_terms(
        _asked_once("Estrella", "Taffel", "Amazon", "En osaa sanoa"))
    assert "Estrella" in proposed


def test_the_studys_own_non_answers_are_still_dropped():
    """Widening recall must not start proposing the scale."""
    proposed = propose_sensitive_terms(
        _asked_once("Amazon", "En osaa sanoa", "Ei mikään näistä", "Muu, mikä?"))
    assert "Amazon" in proposed
    for junk in ("En osaa sanoa", "Ei mikään näistä", "Muu, mikä?"):
        assert junk not in proposed, f"{junk!r} was offered as a company"


def test_lower_case_prose_is_still_not_a_name():
    """A label with no capital anywhere is the study's own wording."""
    assert _candidate("erittäin tärkeä") is None
    assert _candidate("melko todennäköisesti") is None


def test_a_code_prefix_is_not_part_of_the_name():
    """SPSS exports write value labels as `1=Amazon`. Masking `1=Amazon`
    masks nothing — the text says `Amazon`."""
    assert _candidate("1=Amazon") == "Amazon"
    assert _candidate("12 = Salesforce") == "Salesforce"


def test_a_code_prefixed_scale_point_is_still_a_scale_point():
    """`Erittäin epätodennäköistä` is refused; `1=` must not smuggle it in."""
    assert _candidate("1=Erittäin epätodennäköistä") is None
    assert _candidate("7=Täysin samaa mieltä") is None


def test_the_spss_markers_are_still_dropped():
    proposed = propose_sensitive_terms(_asked_once("Checked", "Unchecked", "Amazon"))
    assert "Amazon" in proposed
    assert "Checked" not in proposed and "Unchecked" not in proposed


def test_a_scale_point_is_still_dropped():
    proposed = propose_sensitive_terms(_asked_once("Hyvä", "Huono", "Amazon"))
    assert "Amazon" in proposed
    assert "Hyvä" not in proposed and "Huono" not in proposed
