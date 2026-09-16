"""A multi-response question's options are where a brand tracker keeps its brands.

"Having 'Taffel' study leads to 0 sensitive terms although there is many company
names in the study."

SPSS writes a multi-response question as one indicator variable per option: the
OPTION text is the variable's label and the value labels are Checked/Unchecked.
On the Taffel study that is where every brand lives —

    var12  (19 members)  Taffel, Estrella, Pirkka, Coop, Snack Day, Pipers,
                         Gårdchips, Weekend Snacks, ...
    var34O120..O124      Taffel, Estrella, Pringles, Coop, Pirkka

— and `propose_sensitive_terms` read none of it. It reads a variable label only
when it carries a colon (the battery-member split) and otherwise reads value
labels, so a bare option label was invisible. The study proposed nineteen
product ATTRIBUTES from its one rating battery ("Hinta", "Maku", "Rapeus tai
suutuntuma"), the model correctly judged none of them a company, and the analyst
was shown an empty list for a study naming eight brands. Nothing was registered,
so nothing was masked.

This proposes; `ai.text.pick_company_terms` still decides. Offering an option
list that turns out to be flavours costs the model a sentence; missing the brand
list costs the masking everything it is for. (Johan, 2026-09-14)
"""
from __future__ import annotations

from reportbuilder.ingest.sensitive_terms import propose_sensitive_terms
from reportbuilder.model.question import (
    Question, QuestionModel, ValueLabel, Variable,
)

_CHECKED = ("Unchecked", "Checked")


def _member(name: str, option: str) -> Variable:
    """One multi-response indicator: the OPTION is the variable's own label."""
    return Variable(name=name, label=option, measurement="categorical",
                    value_labels=tuple(ValueLabel(float(i), t)
                                       for i, t in enumerate(_CHECKED)),
                    missing_values=frozenset())


def _multi(qid: str, options: tuple[str, ...]) -> tuple[QuestionModel, Question]:
    variables = {f"{qid}O{i}": _member(f"{qid}O{i}", o)
                 for i, o in enumerate(options)}
    q = Question(qid=qid, kind="multi", variables=tuple(variables),
                 text="Mitä seuraavista sipsimerkeistä ostat?")
    return QuestionModel(variables=variables, questions=[q]), q


_BRANDS = ("Taffel", "Estrella", "Pringles", "Pirkka", "Coop", "Snack Day", "Pipers")


def test_the_options_of_a_multi_response_question_are_proposed():
    model, _q = _multi("var12", _BRANDS)
    proposed = set(propose_sensitive_terms(model))
    missing = [b for b in _BRANDS if b not in proposed]
    assert not missing, f"not proposed: {missing}"


def test_a_brand_ending_like_a_finnish_case_is_still_proposed():
    """`Estrella` ends in "-lla" and was read as an adessive, so the one rule
    written to drop inflected OPTIONS ("Muualla", "Verkkokaupasta") dropped a
    real brand instead. An enumerated member stands in the nominative; the
    inflection rule belongs to value labels, not to a list of options."""
    model, _q = _multi("var34", ("Taffel", "Estrella", "Pringles"))
    assert "Estrella" in propose_sensitive_terms(model)


def test_the_spss_markers_are_still_not_proposed():
    """Checked/Unchecked are the value labels of every indicator in the file."""
    model, _q = _multi("var12", _BRANDS)
    proposed = propose_sensitive_terms(model)
    assert "Checked" not in proposed and "Unchecked" not in proposed


def test_an_option_named_once_is_not_a_list():
    """One indicator is not a multi-response family — the same rule the battery
    members follow, so a lone labelled variable is not proposed."""
    model, _q = _multi("solo", ("Taffel",))
    assert propose_sensitive_terms(model) == []


def test_an_inflected_VALUE_label_is_now_offered_too():
    """REVERSED 2026-09-16. This used to assert the opposite.

    The case-ending rule was applied to value labels and not to multi-response
    options, on the reasoning that an option is a phrase the question puts the
    respondent inside (`Muualla`, `Omassa rauhassa`) while an enumerated member
    stands in the nominative. But a single-choice question's value labels are
    ALSO an enumerated list when the question is "which of these brands do you
    know" — and there the rule dropped `Estrella`, the brand it was written to
    protect, which only survived because Taffel happened to ask it as a
    multi-response.

    Measured the way the original rule was, across Attendo, Holiday Club and
    Synsam: no company is lost and 29 candidates are added, all of them
    demographics and attribute phrases. The old rule was also inconsistent
    inside a single list — it kept `Hämeen lääni` and dropped `Uudenmaan lääni`.

    `ai.text.pick_company_terms` drops these; a company it never sees reaches
    the vendor in clear.
    """
    var = Variable(name="q1", label="Missä syöt sipsejä?", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Kotona"), ValueLabel(2.0, "Muualla"),
                                 ValueLabel(3.0, "Omassa rauhassa")),
                   missing_values=frozenset())
    var2 = Variable(name="q2", label="Entä juhlissa?", measurement="categorical",
                    value_labels=var.value_labels, missing_values=frozenset())
    model = QuestionModel(variables={"q1": var, "q2": var2}, questions=[])
    proposed = propose_sensitive_terms(model)
    assert "Muualla" in proposed
    assert "Omassa rauhassa" in proposed


def test_a_battery_is_unaffected():
    """The existing source still works alongside the new one."""
    variables = {
        "b1": Variable(name="b1", label="Attendo:Mitä ajattelet?",
                       measurement="categorical", value_labels=(),
                       missing_values=frozenset()),
        "b2": Variable(name="b2", label="Mehiläinen:Mitä ajattelet?",
                       measurement="categorical", value_labels=(),
                       missing_values=frozenset()),
    }
    model = QuestionModel(variables=variables, questions=[])
    assert {"Attendo", "Mehiläinen"} <= set(propose_sensitive_terms(model))


def test_the_shared_synthetic_study_still_names_no_companies(tmp_path):
    """The fixture almost every backend test builds a case from.

    Its contract, stated by `test_sensitive_terms_gate`: it names no companies,
    so it proposes nothing, so the report gate does not fire and a test can
    create a report without first accepting terms. Twenty test files depend on
    that without saying so.

    Reading multi-response options broke it — the fixture's "Channel A" /
    "Channel B" were enumerated proper nouns, the study began proposing them,
    and 23 fixtures failed at setup with a report that was refused. The labels
    are lower-case phrases now, and this is the assertion that says why, so the
    next person to name an option after something proper-looking finds out here
    rather than in twenty unrelated failures. (Johan, 2026-09-14)
    """
    from reportbuilder.ingest.multi_group import enrich_model
    from reportbuilder.ingest.sav_reader import read_sav
    from reportbuilder.ingest.sensitive_terms import propose_from_models
    from reportbuilder.testing.fixtures import synthetic_sav

    _df, raw = read_sav(synthetic_sav(tmp_path))
    assert propose_from_models(enrich_model(raw), raw) == []
