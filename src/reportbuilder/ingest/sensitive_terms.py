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
})

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
    if t.lower() in _ARTEFACTS or t.lower() in _SCALE_POINTS:
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
