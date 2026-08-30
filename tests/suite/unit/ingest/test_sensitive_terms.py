"""Which strings in a study might name a company.

The terms that must never reach an LLM are not hidden in prose — they are in
the study's own structure. A brand tracker enumerates its brands as data: they
are the members of its batteries and the categories of its questions. Measured
against a real Finnish study, reading that structure found every one of the
nine brands, where the best general-purpose NER available found 15-20%.

This PROPOSES; an analyst confirms. "Ahne" (greedy) and "Validia" are both
capitalised battery members and only a human reliably tells which is an image
attribute and which is a care provider.
"""
from __future__ import annotations

from reportbuilder.ingest.sensitive_terms import propose_sensitive_terms
from reportbuilder.model.question import QuestionModel, ValueLabel, Variable


def _model(*variables: Variable) -> QuestionModel:
    return QuestionModel(variables={v.name: v for v in variables}, questions=[])


def _var(name: str, label: str = "", values: tuple[str, ...] = ()) -> Variable:
    return Variable(name=name, label=label, measurement="categorical",
                    value_labels=tuple(ValueLabel(float(i + 1), t)
                                       for i, t in enumerate(values)),
                    missing_values=frozenset())


def test_it_finds_the_members_of_a_brand_battery():
    """The shape a brand tracker actually has: "<brand>:<shared question>"."""
    model = _model(
        _var("q1a", "Attendo:Mitä seuraavista tunnet?"),
        _var("q1b", "Esperi:Mitä seuraavista tunnet?"),
        _var("q1c", "Humana:Mitä seuraavista tunnet?"),
    )
    assert set(propose_sensitive_terms(model)) >= {"Attendo", "Esperi", "Humana"}


def test_a_member_named_once_is_not_proposed():
    """One appearance is a question, not a battery member — proposing every
    colon-prefix would bury the analyst in the study's own wording."""
    model = _model(_var("q1", "Yksittäinen:Kysymys tästä aiheesta"))
    assert propose_sensitive_terms(model) == []


def test_it_finds_brands_on_the_other_side_of_the_colon():
    """Real studies put the member on either side: "Ahne:Rinnekodit" pairs an
    image attribute with the provider it was attributed to."""
    model = _model(
        _var("q2a", "Ahne:Rinnekodit"),
        _var("q2b", "Luotettava:Rinnekodit"),
        _var("q2c", "Ahne:Ykköskodit"),
        _var("q2d", "Luotettava:Ykköskodit"),
    )
    proposed = set(propose_sensitive_terms(model))
    assert {"Rinnekodit", "Ykköskodit"} <= proposed


def test_value_labels_count_too():
    """A "which of these do you use" question carries its brands as answers."""
    model = _model(
        _var("q3", "Mitä palveluntarjoajaa käytät?",
             values=("Attendo", "Esperi", "En mitään näistä")),
        _var("q4", "Mitä palveluntarjoajaa suosittelisit?",
             values=("Attendo", "Esperi", "En mitään näistä")),
    )
    proposed = set(propose_sensitive_terms(model))
    assert {"Attendo", "Esperi"} <= proposed


def test_it_leaves_out_the_obvious_non_answers():
    """"En osaa sanoa" is in every study and is nobody's brand."""
    model = _model(
        _var("q5", "Kysymys", values=("En osaa sanoa", "Ei mikään näistä")),
        _var("q6", "Toinen", values=("En osaa sanoa", "Ei mikään näistä")),
    )
    assert propose_sensitive_terms(model) == []


def test_it_leaves_out_scale_points():
    """A rating scale's levels repeat across every battery member and would
    otherwise dominate the proposal."""
    scale = ("Täysin eri mieltä", "Jokseenkin eri mieltä",
             "Jokseenkin samaa mieltä", "Täysin samaa mieltä")
    model = _model(_var("q7", "Väite A", values=scale),
                   _var("q8", "Väite B", values=scale))
    assert propose_sensitive_terms(model) == []


def test_it_proposes_rather_than_decides():
    """Image attributes and brands are both capitalised battery members. The
    proposal includes both; a human picks. Being wrong in this direction is
    safe — an extra term is masked needlessly, a missing one leaks."""
    model = _model(
        _var("a1", "Ahne:Rinnekodit"), _var("a2", "Ahne:Ykköskodit"),
        _var("a3", "Luotettava:Rinnekodit"), _var("a4", "Luotettava:Ykköskodit"),
    )
    proposed = propose_sensitive_terms(model)
    assert "Ahne" in proposed, "the attribute is proposed too — a human decides"


def test_spss_multi_response_markers_are_not_proposed():
    """"Checked"/"Unchecked" are the value labels of every multi-response
    indicator, so they appear in more grids than any brand does. They are file
    format, not data, and they led the proposal list on both real studies."""
    model = _model(
        _var("m1", "Attendo:Mitä tunnet?", values=("Checked", "Unchecked")),
        _var("m2", "Esperi:Mitä tunnet?", values=("Checked", "Unchecked")),
    )
    proposed = propose_sensitive_terms(model)
    assert "Checked" not in proposed and "Unchecked" not in proposed
    assert {"Attendo", "Esperi"} <= set(proposed)


def test_bare_scale_points_are_not_proposed():
    """A rating grid makes "Hyvä"/"Huono" battery members like any other, so
    they arrive capitalised, short and more frequent than any brand — on the
    real study they led the list, ahead of Attendo."""
    model = _model(
        _var("r1", "Hyvä:Millainen mielikuva?"), _var("r2", "Huono:Millainen mielikuva?"),
        _var("r3", "Attendo:Millainen mielikuva?"),
        _var("r4", "Hyvä:Entä palvelu?"), _var("r5", "Huono:Entä palvelu?"),
        _var("r6", "Attendo:Entä palvelu?"),
    )
    proposed = propose_sensitive_terms(model)
    assert "Hyvä" not in proposed and "Huono" not in proposed
    assert "Attendo" in proposed


def test_a_company_that_merely_starts_like_a_scale_point_survives():
    """"Hyvä" is a scale point; "Hyvinvointi Oy" is a company. Whole-word
    matching, never a prefix."""
    model = _model(_var("c1", "Hyvinvointi Oy:Kysymys"),
                   _var("c2", "Hyvinvointi Oy:Toinen kysymys"),
                   _var("c3", "Attendo:Kysymys"), _var("c4", "Attendo:Toinen kysymys"))
    assert "Hyvinvointi Oy" in propose_sensitive_terms(model)


# --------------------------------------------------------------------------- #
# Scale points and export artefacts are not company names
# --------------------------------------------------------------------------- #
# Found on the Holiday Club study, which proposed "EMPTY", "Harvemmin", "Kerran
# vuodessa", "Muutaman vuoden välein" and "Pari kertaa vuodessa" — four points
# of a frequency scale and one exporter placeholder. The quality and agreement
# scales were already filtered; a frequency scale is the same kind of thing.


def test_a_frequency_scale_point_is_not_a_name():
    from reportbuilder.ingest.sensitive_terms import _candidate

    for point in ("Kerran vuodessa", "Pari kertaa vuodessa",
                  "Muutaman vuoden välein", "Harvemmin", "Vuosittain",
                  "Never", "Once a year"):
        assert _candidate(point) is None, point


def test_an_export_placeholder_is_not_a_name():
    """On the real file "EMPTY" is the third value label of a TRUE/FALSE flag,
    so it repeated across every such flag and outranked most brands."""
    from reportbuilder.ingest.sensitive_terms import _candidate

    for junk in ("EMPTY", "NULL", "Missing", "N/A", "SYSMIS"):
        assert _candidate(junk) is None, junk


def test_a_company_is_not_caught_by_sharing_a_word_with_a_scale():
    """The filters are whole-word or counting-word, never a substring: a
    frequency filter that swallowed "Vuosilomat Oy" would be worse than the
    problem it solves."""
    from reportbuilder.ingest.sensitive_terms import _candidate

    for name in ("Vuosilomat Oy", "Aina Group", "Usein Oy", "Viking Line Club",
                 "Lapland Hotels Club", "Scandic Friends", "Finnair Plus"):
        assert _candidate(name) == name, name


# --------------------------------------------------------------------------- #
# Which model the proposal reads
# --------------------------------------------------------------------------- #
# Neither model is right alone. Grouping decides which side of "<a>:<b>" is the
# member — a judgement this module cannot make, so it reads both sides and a
# brand-image grid contributes its ATTRIBUTES beside its brands. But grouping
# can also dissolve the shape entirely, and then it proposes nothing, which
# means no gate and no registered terms.


def _labelled(labels: dict[str, str]):
    """A model built from variable LABELS alone — the only thing these read."""
    from reportbuilder.model.question import QuestionModel, Variable

    return QuestionModel(
        variables={n: Variable(name=n, label=l, measurement="nominal",
                               value_labels=(), missing_values=frozenset())
                   for n, l in labels.items()},
        questions=[])


def test_the_grouped_answer_wins_when_there_is_one():
    """The Attendo shape: grouped proposes the brands, raw adds the attributes
    they were rated on."""
    from reportbuilder.ingest.sensitive_terms import propose_from_models

    grouped = _labelled({"a": "Attendo:Mielikuva", "b": "Esperi:Mielikuva"})
    raw = _labelled({"a": "Luotettava:Attendo", "b": "Rehellinen:Attendo",
                  "c": "Luotettava:Esperi", "d": "Rehellinen:Esperi"})
    got = propose_from_models(grouped, raw)
    assert "Attendo" in got and "Esperi" in got
    assert "Luotettava" not in got and "Rehellinen" not in got


def test_the_raw_answer_is_used_when_grouping_found_nothing():
    """The Holiday Club shape: grouping dissolved every label the proposal
    reads, and an empty list means the gate never fires."""
    from reportbuilder.ingest.sensitive_terms import propose_from_models

    grouped = _labelled({"a": "Kysymys ilman kaksoispistettä"})
    raw = _labelled({"a": "Scandic Friends:Ohjelmat", "b": "Hilton Honors:Ohjelmat"})
    got = propose_from_models(grouped, raw)
    assert "Scandic Friends" in got and "Hilton Honors" in got


def test_it_is_never_the_union():
    """The union is the long list again, for every study."""
    from reportbuilder.ingest.sensitive_terms import propose_from_models

    grouped = _labelled({"a": "Attendo:Mielikuva", "b": "Esperi:Mielikuva"})
    raw = _labelled({"a": "Luotettava:Attendo", "b": "Rehellinen:Attendo",
                  "c": "Luotettava:Esperi", "d": "Rehellinen:Esperi"})
    assert len(propose_from_models(grouped, raw)) == 2


# ── An answer option is not a company (2026-08-30) ──────────────────────────
# Reported from staging: the proposal offered "Muualla" (elsewhere) and "Omassa
# rauhassa" (in one's own peace) as company names.
#
# Repetition is this module's whole signal, and answer OPTIONS repeat too — the
# same option list is offered by every question in a family. They are
# capitalised in the SPSS labels and short, so nothing already here stopped
# them.
#
# Two shapes separate a description from a name, and both are facts about
# Finnish rather than about any study:
#
#   A name stands in the NOMINATIVE. An option is inflected — `Muualla` carries
#   the adessive, `Omassa rauhassa` and `Verkkokaupasta` the inessive and
#   elative. A company in an answer list does not decline.
#
#   A description OPENS with an evaluation, a quantifier or a first-person
#   verb: "Hyvä asiakaspalvelu", "Liian kalliit hinnat", "Käytän silmälaseja".
#   A company name opens with itself.
#
# Both were chosen against the requirement, which is not symmetric: EVERY
# company must survive, and some noise is tolerable. A term dropped here is
# never proposed, never accepted, never registered as a deny term, and reaches
# the vendor in clear. Measured across three real studies -- Attendo, Holiday
# Club, Synsam -- these remove 26% of the proposal and lose NONE of the 24
# companies in them. The rules that cut more all cost a company: sentence-case
# alone would drop "Sokos hotels (S-kortti)".

def test_an_inflected_option_is_not_proposed():
    m = _model(
        _var("q1", values=("Kotona", "Muualla", "Omassa rauhassa")),
        _var("q2", values=("Kotona", "Muualla", "Omassa rauhassa")),
    )
    proposed = propose_sensitive_terms(m)
    assert "Muualla" not in proposed
    assert "Omassa rauhassa" not in proposed


def test_a_description_opening_with_an_evaluation_is_not_proposed():
    m = _model(
        _var("q1", values=("Hyvä asiakaspalvelu", "Liian kalliit hinnat")),
        _var("q2", values=("Hyvä asiakaspalvelu", "Liian kalliit hinnat")),
    )
    proposed = propose_sensitive_terms(m)
    assert proposed == []


def test_the_company_names_beside_them_still_are():
    """The rules must not touch what the module exists to find."""
    brands = ("Synsam", "Instrumentarium", "Specsavers", "Sokos hotels (S-kortti)",
              "Lapland Hotels Club", "Mainio-kodit", "Attendo")
    m = _model(_var("q1", values=brands), _var("q2", values=brands))
    proposed = propose_sensitive_terms(m)
    for b in brands:
        assert b in proposed, f"{b!r} was dropped"
