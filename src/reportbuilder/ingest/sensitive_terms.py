"""Which strings in a study might name a company.

The terms that must never reach an LLM are not hidden in prose. A brand tracker
ENUMERATES its brands as data: they are the members of its batteries and the
categories of its questions. Reading that structure is not a heuristic standing
in for entity recognition — it is reading the answer off the source.

That matters because entity recognition does not work here. Measured against a
real Finnish study (283 label strings, 153 mentions of nine care-provider
brands):

    spaCy fi_core_news_md, ORGANIZATION      15 %
    spaCy fi_core_news_lg, any entity type   16 %
    a local Gemma 3 4b                       finds most, misspells some,
                                             7.5 s per slide
    the study's own structure               100 %

Finnish is the hard case — names inflect (``Attendosta``, ``Mehiläisen``) and
the models label companies as GPE, PRODUCT or PERSON as often as ORG — but the
argument is not really about Finnish. Asking a general-purpose model to
rediscover entities the application already holds as data is strictly harder
than looking them up.

This module PROPOSES. An analyst confirms, because ``Ahne`` ("greedy") and
``Validia`` are both capitalised battery members and only a person reliably
tells the image attribute from the care provider. The confirmed list is what
gets registered with datahive, and being wrong in the generous direction is
safe: an extra term is masked needlessly, a missing one leaks.
"""
from __future__ import annotations

import re
from collections import Counter

from reportbuilder.model.question import QuestionModel

#: A member must appear this many times to be proposed. A battery repeats its
#: members across every statement; a one-off colon is the study's own wording
#: ("Huom:Vastaa kaikkiin"), and proposing those would bury the analyst.
MIN_OCCURRENCES = 2

#: Longer than this and it is a sentence, not a name.
MAX_TERM_CHARS = 40

#: The `1=` an SPSS export writes in front of a value label. Stripped before
#: anything else looks at the label; see `_candidate`.
_CODE_PREFIX = re.compile(r"^\d+\s*=\s*")

#: Openers that mark a non-answer, a scale point or an instruction rather than
#: a name. Matched at the start, case-insensitively, on a word boundary.
_NOT_A_NAME = re.compile(
    r"^(en |ei |kyllä\b|täysin\b|jokseenkin\b|melko\b|erittäin\b|hyvin\b"
    r"|jokin\b|joku\b|muu\b|muut\b|other\b|none\b|yes\b|no\b|don't\b)",
    re.IGNORECASE,
)


#: SPSS writes these as the value labels of every multi-response indicator, so
#: they appear in more grids than any brand does. They are file format, not data.
_ARTEFACTS = frozenset({
    "checked", "unchecked", "selected", "not selected", "valittu", "ei valittu",
    "true", "false", "yes", "no",
    # Export placeholders. On the Holiday Club file "EMPTY" is the third value
    # label of a TRUE/FALSE flag, so it repeats across every such flag and beat
    # most brands on frequency — a word from the exporter, proposed as a company.
    "empty", "null", "none", "n/a", "na", "missing", "sysmis", "#null!",
})

#: A frequency or interval, which is a point on a scale rather than an entity.
#: The quality and agreement scales were already covered by `_SCALE_POINTS`; a
#: FREQUENCY scale is the same thing and was not — "Kerran vuodessa", "Pari
#: kertaa vuodessa", "Muutaman vuoden välein" and "Harvemmin" all reached the
#: analyst as candidate company names on a real study.
#:
#: Two shapes, because a frequency takes two. A bare adverb is matched WHOLE, so
#: a company is never caught by sharing a word. A counted interval is matched on
#: its counting word — "kerran", "kertaa", "välein" — which no company name
#: uses, and which is what makes "Kerran vuodessa" a frequency rather than a
#: name whatever noun follows it.
_FREQUENCY_WORDS = frozenset({
    "harvemmin", "useammin", "usein", "harvoin", "päivittäin", "viikoittain",
    "kuukausittain", "vuosittain", "satunnaisesti", "säännöllisesti",
    "aina", "ei koskaan", "en koskaan", "jatkuvasti",
    "always", "never", "rarely", "often", "sometimes", "seldom",
    "daily", "weekly", "monthly", "yearly", "annually", "occasionally",
})
_COUNTED_INTERVAL = re.compile(
    r"\b(kerran|kertaa|välein|kertaa\s+vuodessa|times a|per year|per month|"
    r"per week|a year|a month|a week)\b",
    re.IGNORECASE,
)

#: Bare scale points. A rating grid makes these battery members like any other,
#: so they arrive capitalised, short, and more frequent than any brand — on the
#: real study "Huono" and "Hyvä" led the proposal list, ahead of Attendo.
#: Matched WHOLE, never as a prefix: "Hyvä" is a scale point, "Hyvinvointi Oy"
#: is a company.
_SCALE_POINTS = frozenset({
    "hyvä", "huono", "erinomainen", "heikko", "keskinkertainen", "neutraali",
    "samaa mieltä", "eri mieltä", "kyllä", "ei", "parempi", "huonompi",
    "good", "bad", "excellent", "poor", "average", "neutral", "agree", "disagree",
})


# REMOVED 2026-09-16: the Finnish case-ending rule.
#
# It refused a term whose first word carried a locative or plural-oblique
# ending — `Muualla`, `Omassa rauhassa`, `Verkkokaupasta` — on the reasoning
# that a company stands in the nominative while an option is a phrase the
# question puts the respondent inside. It was measured on Attendo, Holiday Club
# and Synsam and lost no company there.
#
# It cost one anyway, on a shape those three do not contain: a brand list asked
# as a single-choice question. `Estrella` ends in `-lla` and was refused.
# Exempting the enumerated sources one at a time left every caller passing
# `inflected_ok=True`, which is the rule saying it has no case left to judge.
#
# Dropping it adds 29 candidates across those three studies, all demographics
# and attribute phrases, and loses nothing. `ai.text.pick_company_terms` reads
# them against the study's questions and drops them in a sentence; a company it
# never sees reaches the vendor in clear. The DESCRIPTION-opener rule below is
# untouched and is what removes most of the noise.

#: Words a DESCRIPTION opens with and a company name does not.
#:
#: The same kind of list as `_SCALE_POINTS` above and chosen the same way: an
#: evaluation, a quantifier, a possessive or a first-person verb begins a
#: statement being rated, never a name. "Hyvä asiakaspalvelu", "Liian kalliit
#: hinnat", "Käytän silmälaseja päivittäin".
#:
#: Kept GENERIC on purpose. An earlier draft included words lifted from two
#: files — `vaikuttajien`, `lemmikki`, `optikkoliikkeiden` — which tunes the
#: proposal to the studies it was measured on and to nothing else.
_DESCRIPTION_OPENERS = frozenset({
    "hyvä", "hyvät", "hyviä", "heikko", "heikot", "heikkoa", "huono", "huonot",
    "paras", "parempi", "edullinen", "edulliset", "kallis", "kalliit",
    "liian", "erittäin", "melko", "tietty", "tietyt",
    "oma", "omat", "kaikki", "kaikkien", "muu", "muut", "jokin", "jotkin",
    "joustava", "joustavat", "laaja", "laajat", "nopea", "nopeat",
    "helppo", "helpot", "mahdollisuus", "mahdollisuudet", "saatavilla",
    "saan", "käytän", "asioin", "suosittelen", "haluan", "koen", "pidän",
    "ostan",
})


def _candidate(text: str) -> str | None:
    """The term this string contributes, or None if it cannot be a name."""
    t = (text or "").strip().strip(":").strip()
    # An SPSS export often writes the code into the label: `1=Amazon`,
    # `7=Täysin samaa mieltä`. The code is not part of the name — proposing
    # `1=Amazon` would mask a string the report's text never contains — and it
    # hides the rest of the label from every rule below, which is how
    # `1=Erittäin epätodennäköistä` got past the opener that already refuses
    # `Erittäin`. Judge the label it carries. (Johan, 2026-09-15)
    t = _CODE_PREFIX.sub("", t).strip()
    if not t or len(t) > MAX_TERM_CHARS:
        return None
    # A capital SOMEWHERE, not necessarily first. Requiring the first character
    # refused `nSight`, `eBay`, `iPhone` and `3M` — every one of them written
    # the way its owner writes it. A scale point or a stretch of the study's own
    # prose still carries no capital at all, which is the signal that was
    # actually wanted. (Johan, 2026-09-15)
    if not any(c.isupper() for c in t):
        return None
    if _NOT_A_NAME.match(t):
        return None
    if t.isdigit():
        return None
    low = t.lower()
    if low in _ARTEFACTS or low in _SCALE_POINTS or low in _FREQUENCY_WORDS:
        return None
    if _COUNTED_INTERVAL.search(t):
        return None
    first = t.split()[0].strip("-,")
    if first.lower() in _DESCRIPTION_OPENERS:
        return None
    # Two words is a company ("Julkiset hoivapalvelut", "Esperi Care"); five is
    # a statement being rated.
    if len(t.split()) > 3:
        return None
    return t


def propose_from_models(grouped: QuestionModel, raw: QuestionModel) -> list[str]:
    """Candidates, preferring what the GROUPED model says.

    The two models answer differently and neither is right on its own.

    Grouping decides which side of `"<a>:<b>"` is the member — a judgement this
    module cannot make, which is why it considers both sides and so drags a
    brand-image grid's ATTRIBUTES in beside its brands. Where the grouper has
    applied, it is simply better informed: on the Attendo study the grouped
    model proposes the eight brands and the two provider categories, and the
    raw one adds twelve attributes ("Luotettava", "Rehellinen", "Ammattitaitoinen").

    But grouping can also dissolve the shape entirely. On the Holiday Club study
    it took the file's 192 colon labels to 77 and the proposal to ZERO — and
    nothing proposed means nothing accepted, no gate, and no registered terms.
    An over-long list costs an analyst some unticking; an empty one costs the
    masking everything it was for.

    So: the grouped answer when there is one, the raw answer when there is not.
    Never the union — that is the long list again, for every study.
    """
    return propose_sensitive_terms(grouped) or propose_sensitive_terms(raw)


def propose_sensitive_terms(model: QuestionModel) -> list[str]:
    """Candidate company/brand names in *model*, most frequent first.

    Two structures carry them:

    * **Battery members.** A grouped question labels its variables
      ``"<member>:<shared question>"`` — and real studies put the member on
      EITHER side, because a brand-image grid is written both as
      ``"Attendo:Mitä ajattelet?"`` and as ``"Ahne:Rinnekodit"``. Both sides
      are considered.
    * **Answer categories.** "Which of these do you use" carries its brands as
      value labels, repeated across the questions that ask about them.
    * **Multi-response options.** SPSS writes one indicator variable per
      option, with the OPTION as that variable's own label — bare, with no
      colon. That is where a brand tracker actually enumerates its brands.

    Repetition is the signal in each case: a brand recurs because the study
    asks about it several times, while the study's own wording does not.
    """
    counts: Counter[str] = Counter()

    # --- battery members -------------------------------------------------
    # Within a group of variables sharing one side of the colon, the members
    # are what VARIES on the other side. Counting occurrences instead gets
    # this exactly backwards for the commonest shape — each brand appears
    # once while the shared question repeats — and proposes the question.
    by_tail: dict[str, set[str]] = {}
    by_head: dict[str, set[str]] = {}
    for var in model.variables.values():
        label = (var.label or "").strip()
        if ":" not in label:
            continue
        head, _, tail = label.partition(":")
        head, tail = head.strip(), tail.strip()
        if head and tail:
            by_tail.setdefault(tail, set()).add(head)
            by_head.setdefault(head, set()).add(tail)

    for grouped in (by_tail, by_head):
        for _shared, members in grouped.items():
            if len(members) < 2:
                continue        # not a battery, just one labelled variable
            for m in members:
                term = _candidate(m)
                if term:
                    counts[term] += len(members)

    # --- multi-response options -------------------------------------------
    # SPSS writes a multi-response question as one indicator variable per
    # option: the OPTION is that variable's label, and Checked/Unchecked its
    # values. A brand tracker keeps its brands there — Taffel's `var12`
    # enumerates nineteen — and a bare label carries no colon, so nothing above
    # sees it. That study proposed nineteen product ATTRIBUTES from its single
    # rating battery ("Hinta", "Maku", "Rapeus tai suutuntuma"), the model
    # rightly judged none of them a company, and a study naming eight brands
    # registered nothing and masked nothing. (Johan, 2026-09-14)
    for question in getattr(model, "questions", ()) or ():
        if getattr(question, "kind", "") != "multi":
            continue
        options = [(model.variables[v].label or "").strip()
                   for v in getattr(question, "variables", ()) or ()
                   if v in model.variables]
        options = [o for o in options if o]
        if len(options) < 2:
            continue            # one indicator is not a list of options
        for option in options:
            term = _candidate(option)
            if term:
                counts[term] += len(options)

    # --- answer categories ------------------------------------------------
    # "Which of these do you use" carries its brands as value labels, and ONE
    # appearance is enough.
    #
    # This used to need two, on the reasoning that a brand recurs across the
    # questions asking about it while a one-off category is that question's own
    # wording. True of a tracker, and fatal to the ordinary study that asks
    # "which of these companies do you know" exactly once: every option appeared
    # a single time, so Amazon, Salesforce and Aramco were never offered and the
    # screen said the study's structure named no companies at all.
    #
    # The judgement belongs to `ai.text.pick_company_terms`, which reads the
    # candidates against the study's questions. An extra candidate costs it a
    # sentence; a missing one costs the masking everything it is for.
    # (Johan, 2026-09-15)
    value_counts: Counter[str] = Counter()
    for var in model.variables.values():
        for vl in var.value_labels:
            term = _candidate(vl.label or "")
            if term:
                value_counts[term] += 1
    for term, n in value_counts.items():
        counts[term] += n

    proposed = list(counts)
    # Frequent first: the brand a tracker is ABOUT appears in every grid, so
    # the analyst reads the likeliest candidates before the marginal ones.
    proposed.sort(key=lambda t: (-counts[t], t.lower()))
    return proposed


# ---------------------------------------------------------------------------
# Handing the terms over
# ---------------------------------------------------------------------------


def expand_terms(terms: list[str]) -> list[str]:
    """The accepted terms, de-duplicated, longest first.

    Longest first because a substitution walks the list in order: "Esperi Care
    Oy" has to be replaced before "Esperi", or the shorter match fires and
    leaves " Care Oy" stranded beside a surrogate.

    Inflection is deliberately NOT handled here. datahive owns deny-term
    matching, so it owns making that work in Finnish — `Mehiläinen` matching
    `Mehiläisestä` is its `_match_forms`. Doing it here would fix it for nSight
    and leave every other client of the same deny list with the same silent
    leak, each expected to get Finnish morphology right on its own.
    """
    seen: dict[str, None] = {}
    for term in terms:
        t = (term or "").strip()
        if t:
            seen.setdefault(t, None)
    return sorted(seen, key=lambda t: (-len(t), t.lower()))
