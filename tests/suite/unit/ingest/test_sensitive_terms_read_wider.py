"""The names a study's STRUCTURE does not enumerate still reach the model.

Measured on eight studies against the names found by reading each of them
(2026-09-19), the structure alone offered 55 of 98 to the model. The client
itself was only in the wording ("DNA:n mobiilivarmenne", "Holiday Clubin
omistajana"); competitors were only in the open answers (Mehiläinen,
Pihlajalinna, Terveystalo on the Attendo study; eighteen medicines on Alflorex).
Reading the wording and the answers as well offered all 98. The model judges;
an extra candidate costs it a line, a missing one leaves the study unmasked.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.ingest.sensitive_terms import (
    Candidates, capital_runs, propose_candidates, with_siblings,
)
from reportbuilder.model.question import (
    Question, QuestionModel, ValueLabel, Variable,
)

pytestmark = pytest.mark.unit


def _var(name, label="", values=(), measurement="categorical"):
    return Variable(name=name, label=label, measurement=measurement,
                    value_labels=tuple(ValueLabel(float(i + 1), t)
                                       for i, t in enumerate(values)),
                    missing_values=frozenset())


def _model(*variables, questions=()):
    return QuestionModel(variables={v.name: v for v in variables},
                         questions=list(questions))


def _terms(model, df=None):
    return propose_candidates(model, model, df).terms


# --- the study's own wording ---------------------------------------------------

def test_a_client_named_only_in_the_question_wording_is_offered():
    q = Question(qid="q1", kind="single", variables=("q1",),
                 text="Kuinka tyytyväinen olet DNA:n mobiilivarmenteeseen?")
    model = _model(_var("q1", q.text, ("Tyytyväinen", "Tyytymätön")), questions=[q])
    assert "DNA" in _terms(model)


def test_the_word_opening_a_question_is_not_offered():
    q = Question(qid="q1", kind="single", variables=("q1",),
                 text="Kerro, mitä ajattelet palvelusta. Entä hinnasta?")
    model = _model(_var("q1", q.text), questions=[q])
    terms = _terms(model)
    assert "Kerro" not in terms and "Entä" not in terms


def test_an_inflected_mention_is_counted_toward_the_name():
    q = Question(qid="q1", kind="single", variables=("q1",),
                 text="Oletko Holiday Club -omistaja? Mitä pidät Holiday Clubin eduista?")
    model = _model(_var("q1", q.text), questions=[q])
    terms = _terms(model)
    assert "Holiday Club" in terms
    assert "Holiday Clubin" not in terms


def test_a_verb_opening_the_sentence_is_not_glued_to_the_name():
    q = Question(qid="q2", kind="single", variables=("q2",),
                 text="Sanoit Alflorexin olevan tuttu. Miksi?")
    model = _model(_var("q1", "Mitä merkkejä tunnet?", ("Alflorex", "Gefilus")),
                   _var("q2", q.text), questions=[q])
    terms = _terms(model)
    assert "Alflorex" in terms
    assert not any(t.startswith("Sanoit") for t in terms)


def test_a_two_word_name_is_not_cut_to_its_second_word():
    """"Suomen Seniorihoiva" is a name even where "Seniorihoiva" is written alone."""
    model, df = _open(["Suomen Seniorihoiva"] * 3 + ["Seniorihoiva"] * 4)
    assert "Suomen Seniorihoiva" in _terms(model, df)


def test_the_survey_tools_own_variables_offer_nothing():
    model = _model(_var("ip", "IP Address"), _var("ref", "Referer URL"))
    assert _terms(model) == []


def test_a_brand_inside_a_long_option_is_offered():
    """Refused whole as a sentence, the brand in it was never offered."""
    model = _model(_var("q1", "Onko sinulla mobiilivarmenne?",
                        ("Kyllä, minulla on Elisa Mobiilivarmenne", "Ei ole")))
    assert "Elisa Mobiilivarmenne" in _terms(model)


def test_a_web_address_is_offered_without_the_sentence_around_it():
    """The reported case: the whole label was proposed and accepted as a name."""
    model = _model(_var("q1", "Miten sait apua?",
                        ("Katsomalla apua mobiilivarmenne.fi:stä", "Soittamalla")))
    terms = _terms(model)
    assert "mobiilivarmenne.fi" in terms
    assert not any("Katsomalla" in t for t in terms)


def test_only_the_whole_run_of_capitals_is_offered_never_its_parts():
    """Shown the parts, the model picked "One", "Line" and "Club" — and an
    accepted term is masked for the whole tenant."""
    runs = capital_runs("Mitä mieltä olet One Tallink Silja -risteilystä?",
                        skip_opener=True)
    assert runs == ["One Tallink Silja"]


def test_a_name_opening_an_option_keeps_its_first_word():
    """Dropping the opener offered "Hotels Club" and "Line Club"."""
    assert capital_runs("Lapland Hotels Club", skip_opener=True) == ["Lapland Hotels Club"]
    assert capital_runs("Viking Line Club -kanta-asiakkuus", skip_opener=True) == [
        "Viking Line Club"]


def test_a_word_opening_an_option_alone_is_not_a_name():
    assert capital_runs("Tuotteet ovat vanhanaikaisia", skip_opener=True) == []


def test_a_comma_ends_a_name():
    runs = capital_runs("Prisma, K-Citymarket tai Ruohonjuuri", skip_opener=False)
    assert runs == ["Prisma", "K-Citymarket", "Ruohonjuuri"]


# --- what respondents wrote ------------------------------------------------------

def _open(answers, label="Mitä hoivapalveluyrityksiä tunnet?", name="q9"):
    model = _model(_var(name, label, measurement="text"))
    return model, pd.DataFrame({name: answers})


def test_a_name_several_respondents_wrote_is_offered():
    model, df = _open(["Mehiläinen", "mehiläinen ja Esperi", "Mehiläinen, Attendo",
                       "Mehiläinen", "Attendo"])
    assert "Mehiläinen" in _terms(model, df)


def test_a_word_only_one_or_two_respondents_wrote_is_not():
    """One or two is a respondent's own spelling, or a person's name."""
    model, df = _open(["Mehiläinen", "Mehiläinen", "Pertti Virtanen", "en tiedä"])
    terms = _terms(model, df)
    assert "Mehiläinen" not in terms
    assert "Pertti Virtanen" not in terms


def test_the_browsers_user_agent_is_not_an_answer():
    model, df = _open(["Mozilla/5.0 AppleWebKit"] * 5, label="User Agent", name="ua")
    terms = _terms(model, df)
    assert "Mozilla" not in terms and "AppleWebKit" not in terms


def test_a_place_typed_in_capitals_is_not_offered_but_an_acronym_is():
    model, df = _open(["HELSINKI"] * 4 + ["DNA"] * 4)
    terms = _terms(model, df)
    assert "HELSINKI" not in terms
    assert "DNA" in terms


def test_an_answer_cut_short_is_not_offered_beside_the_name():
    model, df = _open(["Synsam"] * 6 + ["Syns"] * 3)
    terms = _terms(model, df)
    assert "Synsam" in terms and "Syns" not in terms


def test_a_function_word_opening_an_answer_is_not_offered():
    model, df = _open(["En tiedä"] * 5 + ["Kyllä"] * 5)
    terms = _terms(model, df)
    assert "En" not in terms and "Kyllä" not in terms


# --- the model's picks -------------------------------------------------------------

def test_a_list_the_model_mostly_picked_is_offered_whole():
    """The model drops members of long brand lists inconsistently: Estrella and
    Red Head beside fourteen kept, Instagram beside Facebook."""
    brands = ("Taffel", "Estrella", "Pringles", "Pirkka", "Red Head")
    got = with_siblings(["Taffel", "Pringles", "Pirkka"],
                        Candidates(terms=list(brands), lists=(brands,)))
    assert set(got) == set(brands)


def test_a_list_the_model_picked_one_of_is_left_alone():
    """One name among attribute options is not a brand list."""
    options = ("Facebook", "Radiomainonta", "TV-mainonta", "Ulkomainonta", "Lehdet")
    got = with_siblings(["Facebook"], Candidates(terms=list(options), lists=(options,)))
    assert got == ["Facebook"]


def test_the_lists_are_the_studys_own_enumerations():
    q = Question(qid="var12", kind="multi", variables=("a", "b", "c"),
                 text="Mitä sipsimerkkejä ostat?")
    model = _model(*(_var(n, label, ("Unchecked", "Checked"))
                     for n, label in (("a", "Taffel"), ("b", "Estrella"), ("c", "Pringles"))),
                   questions=[q])
    lists = propose_candidates(model, model).lists
    assert ("Taffel", "Estrella", "Pringles") in lists


# --- places --------------------------------------------------------------------------
#
# A place is never a company, and the model cannot be relied on to say so: the
# hive masks place names as personal data before the model sees them, so
# "Tampere" reached it as an invented word and it called it a company.

def test_the_survey_tools_country_field_offers_no_countries():
    model = _model(_var("Country", "Country", ("Finland", "Sweden", "United States")))
    assert _terms(model) == []


def test_the_city_respondents_typed_is_not_offered():
    model, df = _open(["Tampere"] * 5 + ["Turku"] * 4, label="City", name="City")
    assert _terms(model, df) == []


@pytest.mark.parametrize("label", ["Kaupunki/Kunta", "Nuts2alueet", "Maakunta", "Postinumero"])
def test_a_location_field_offers_nothing(label):
    model = _model(_var("loc", label, ("Uusimaa", "Stockholms", "Kanta-Häme")))
    assert _terms(model) == []


def test_a_residence_question_offers_no_regions():
    model = _model(_var("q20", "Missä maakunnassa asut tällä hetkellä?",
                        ("Uusimaa", "Kanta-Häme", "Pirkanmaa")))
    assert _terms(model) == []


def test_a_question_about_devices_still_offers_its_brands():
    """The survey tool's session words (device, browser) rule out FREE TEXT
    only; asked with options, a device question lists brands."""
    model = _model(_var("q5", "Minkä merkkinen device sinulla on?",
                        ("Apple", "Samsung", "Nokia")))
    assert {"Apple", "Samsung", "Nokia"} <= set(_terms(model))


def test_each_candidate_says_where_it_came_from():
    q = Question(qid="q1", kind="single", variables=("q1",),
                 text="Mitä optikkoketjuja tunnet? Entä Synsamin palveluita?")
    model = _model(_var("q1", q.text, ("Synsam", "Specsavers")), questions=[q])
    got = propose_candidates(model, model).sources
    assert got["Specsavers"] == ("options", q.text)
