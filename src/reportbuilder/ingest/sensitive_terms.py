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


def _candidate(text: str) -> str | None:
    """The term this string contributes, or None if it cannot be a name."""
    t = (text or "").strip().strip(":").strip()
    if not t or len(t) > MAX_TERM_CHARS:
        return None
    if not t[:1].isupper():
        return None            # a name is capitalised; a scale point rarely is
    if _NOT_A_NAME.match(t):
        return None
    if t.isdigit():
        return None
    low = t.lower()
    if low in _ARTEFACTS or low in _SCALE_POINTS or low in _FREQUENCY_WORDS:
        return None
    if _COUNTED_INTERVAL.search(t):
        return None
    # Two words is a company ("Julkiset hoivapalvelut", "Esperi Care"); five is
    # a statement being rated.
    if len(t.split()) > 3:
        return None
    return t


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

    Repetition is the signal in both cases: a brand recurs because the study
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

    # --- answer categories ------------------------------------------------
    # "Which of these do you use" carries its brands as value labels. Here
    # repetition IS the signal: a brand recurs across the questions that ask
    # about it, while a one-off category is that question's own wording.
    value_counts: Counter[str] = Counter()
    for var in model.variables.values():
        for vl in var.value_labels:
            term = _candidate(vl.label or "")
            if term:
                value_counts[term] += 1
    for term, n in value_counts.items():
        if n >= MIN_OCCURRENCES:
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
