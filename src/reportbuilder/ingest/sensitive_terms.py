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
from dataclasses import dataclass, field

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

#: A web address: `mobiilivarmenne.fi`, `Suomi.fi`, `synsam.com`. Not after
#: an `@`, which would make it the tail of an e-mail address.
_DOMAIN = re.compile(
    r"(?<![\w.@-])(?:[\w-]+\.)+(?:fi|com|net|org|se|de|dk|no|eu|io)\b", re.IGNORECASE)

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
    # A web address inside a label is the name, and the rest of the label is
    # the study's own wording. "Katsomalla apua mobiilivarmenne.fi:stä" was
    # offered whole, the model rightly saw an organisation in it, and the
    # analyst was asked to mask a sentence. (2026-09-19)
    domain = _DOMAIN.search(t)
    if domain:
        return domain.group(0)
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
    counts, _lists, _sources = _structure(model)
    proposed = list(counts)
    # Frequent first: the brand a tracker is ABOUT appears in every grid, so
    # the analyst reads the likeliest candidates before the marginal ones.
    proposed.sort(key=lambda t: (-counts[t], t.lower()))
    return proposed


def _structure(model: QuestionModel
               ) -> tuple[Counter[str], list[tuple[str, ...]], dict[str, str]]:
    """The candidates the study's structure offers, the LISTS it offers them
    in — one battery, one question's options, one variable's categories — and
    the question each candidate is an option of. The lists are what
    `with_siblings` reads; the sources are what the model reads."""
    counts: Counter[str] = Counter()
    lists: list[tuple[str, ...]] = []
    sources: dict[str, str] = {}

    # --- battery members -------------------------------------------------
    # Within a group of variables sharing one side of the colon, the members
    # are what VARIES on the other side. Counting occurrences instead gets
    # this exactly backwards for the commonest shape — each brand appears
    # once while the shared question repeats — and proposes the question.
    by_tail: dict[str, set[str]] = {}
    by_head: dict[str, set[str]] = {}
    for var in model.variables.values():
        label = (var.label or "").strip()
        if ":" not in label or _is_location(var):
            continue
        head, _, tail = label.partition(":")
        head, tail = head.strip(), tail.strip()
        if head and tail:
            by_tail.setdefault(tail, set()).add(head)
            by_head.setdefault(head, set()).add(tail)

    for grouped in (by_tail, by_head):
        for shared, members in grouped.items():
            if len(members) < 2:
                continue        # not a battery, just one labelled variable
            terms = []
            for m in members:
                term = _candidate(m)
                if term:
                    counts[term] += len(members)
                    terms.append(term)
                    sources.setdefault(term, shared)
            lists.append(tuple(sorted(set(terms))))

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
        if _LOCATION.search(getattr(question, "text", "") or ""):
            continue
        options = [(model.variables[v].label or "").strip()
                   for v in getattr(question, "variables", ()) or ()
                   if v in model.variables]
        options = [o for o in options if o]
        if len(options) < 2:
            continue            # one indicator is not a list of options
        terms = []
        for option in options:
            term = _candidate(option)
            if term:
                counts[term] += len(options)
                terms.append(term)
                sources.setdefault(term, question.text or "")
        lists.append(tuple(dict.fromkeys(terms)))

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
        if _is_location(var):
            continue            # a Country or City field: places, never names
        terms = []
        for vl in var.value_labels:
            term = _candidate(vl.label or "")
            if term:
                value_counts[term] += 1
                terms.append(term)
                sources.setdefault(term, var.label or "")
        lists.append(tuple(dict.fromkeys(terms)))
    for term, n in value_counts.items():
        counts[term] += n

    return counts, [lst for lst in dict.fromkeys(lists) if len(lst) >= 2], sources


# ---------------------------------------------------------------------------
# Reading wider: the study's prose and what its respondents wrote
# ---------------------------------------------------------------------------
#
# The structure is where a tracker ENUMERATES its brands, but not the only
# place a study names one. Measured on eight studies against the names found by
# reading each of them (2026-09-19), the structure alone offered 55 of 98 to
# the model:
#
#   * the client itself is often only in the WORDING — "DNA:n mobiilivarmenne",
#     "Holiday Clubin omistajana" — never an option;
#   * a brand inside a long option ("Kyllä, minulla on Elisa Mobiilivarmenne")
#     was refused as a sentence;
#   * the competitors respondents name unprompted are in the open answers:
#     Mehiläinen, Pihlajalinna and Terveystalo on the Attendo study, eighteen
#     medicines on Alflorex, Keops and Lensway on Synsam.
#
# Reading those as well offered 98 of 98. The model judges; an extra
# candidate costs it a line, a missing one leaves the study unmasked.

#: A word must be written by this many respondents to be offered. One or two is
#: a respondent's own spelling or a person's name; three is a name the study's
#: population shares.
MIN_RESPONDENTS = 3

#: At most this many open-answer words, most-written first. Keeps the model's
#: list near 250 lines on the widest study measured.
MAX_OPEN_TERMS = 200

#: Variables that cannot name a company, matched on the variable's name or label.
#:
#: What a survey tool writes about the SESSION, not the respondent's answer:
#: the browser's user agent alone offered "Mozilla" and "AppleWebKit".
#:
#: And WHERE the respondent is — the tool's geo-IP fields (`Country`, `City`,
#: `URL_Region`) and the study's own residence questions. A place is never a
#: company, and the model cannot be relied on to say so: the hive masks place
#: names as personal data before the model sees them, so "Tampere" and "Kemi"
#: reached it as invented words and it called them companies. Read here, they
#: are never offered. (2026-09-19)
#:
#: The session words apply to FREE TEXT only: "Which device do you use?" asked
#: with options is a question whose options may well be brands.
_SESSION = re.compile(
    r"user.?agent|referr?er|ip.?addr|session|\burl\b|link|longitude|latitude|"
    r"browser|device|tracking|utm_|e-?mail|sähköposti|puhelin|phone",
    re.IGNORECASE)
_LOCATION = re.compile(
    r"country|\bcity\b|region|postal|zip.?code|postinumero|municipality|"
    r"kaupunki|\bkunta\b|paikkakun|maakunta|lääni|\bnuts ?\d|"
    r"bundesland|\blän\b|asuinpaikka|asuinkunta|kotikunta|asuinalue|"
    r"missä (?:maakunnassa|läänissä|kunnassa|kaupungissa|maassa) asut|missä asut",
    re.IGNORECASE)


def _is_location(var) -> bool:
    return bool(_LOCATION.search(var.name or "") or _LOCATION.search(var.label or ""))


def _is_metadata(var) -> bool:
    return _is_location(var) or bool(
        _SESSION.search(var.name or "") or _SESSION.search(var.label or ""))

#: Finnish case endings, to fold an inflected mention onto its name when the
#: name itself occurs: Synsamista -> Synsam, Telian -> Telia. Longest first.
_ENDINGS = tuple(sorted({
    "n", "a", "ä", "ta", "tä", "sta", "stä", "ssa", "ssä", "lla", "llä", "lta",
    "ltä", "lle", "ksi", "in", "iin", "hin", "seen", "na", "nä", "t", "ineen",
    "tta", "ttä", "ista", "istä", "illa", "illä", "ille", "ilta", "iltä",
    "issa", "issä", "ien", "jen",
}, key=len, reverse=True))

#: Function words and the instructions a questionnaire opens with, capitalised
#: only because they open an answer or a question.
_FUNCTION_WORDS = frozenset("""
en ei et emme se sen ne niitä ja tai sekä että mutta kun jos koska vaan vain
myös mikä mitä miten missä minkä millä mihin miksi kuinka kuka ketä onko ovat
on oli olen olisi voisi voi tämä tuo nämä ne ne siinä siellä täällä nyt no joo
kyllä ehkä en tiedä eos emt minä mä mulla minulla meillä
kerro kerroit arvioi valitse vastaa listaa kuvaile tarkastele mieti entä huom
the a an and or of to in on for is it i we you yes no not
""".split())

#: Where one run of capitalised words ends and the next begins.
_SENTENCE = re.compile(r"(?<=[.?!])\s+|\n+")
_CLAUSE_BREAK = re.compile(r"[,;:()\[\]/\\\"«»“”]|\s[-–—]\s")


def _word(w: str) -> str:
    return w.strip(".!?'’`*…")


def _is_capitalised(w: str) -> bool:
    return (any(c.isupper() for c in w) and not any(c.isdigit() for c in w)
            and w.casefold() not in _FUNCTION_WORDS)


def _is_question_verb(word: str) -> bool:
    """A Finnish yes/no question opens on its verb, marked -ko/-kö: "Oletko",
    "Tiedätkö", "Käytätkö"."""
    low = word.casefold()
    return len(low) > 4 and low.endswith(("ko", "kö"))


def capital_runs(text: str, *, skip_opener: bool) -> list[str]:
    """Each maximal run of capitalised words in *text*; see `_runs`."""
    return [run for run, _opens in _runs(text, skip_opener=skip_opener)]


def _runs(text: str, *, skip_opener: bool) -> list[tuple[str, bool]]:
    """Each maximal run of capitalised words in *text*.

    MAXIMAL, never its sub-phrases: "One Tallink Silja" is offered, "One" is
    not — a model shown the parts picked "One", "Line", "Plus" and "Club",
    and an accepted term is masked for the whole tenant.

    `skip_opener` drops a word that opens a sentence ALONE, which the study's
    own wording capitalises for grammar ("Tuotteet ovat vanhanaikaisia"). An
    opener followed by another capital starts a name and is kept: dropping it
    offered "Hotels Club", "Friends" and "Line Club" for Lapland Hotels Club,
    Scandic Friends and Viking Line Club. An open answer is often a single
    name, so there the opener is always kept.
    """
    out: list[tuple[str, bool]] = []
    for sentence in _SENTENCE.split(text or ""):
        first = True
        for clause in _CLAUSE_BREAK.split(sentence):
            run: list[str] = []
            opens = False
            for raw in clause.split() + [""]:
                w = _word(raw)
                if w and _is_capitalised(w):
                    opens = opens or (first and not run)
                    run.append(w)
                    first = False
                    continue
                if w:
                    first = False
                if skip_opener and opens and len(run) > 1 and _is_question_verb(run[0]):
                    run = run[1:]           # "Oletko Holiday Club -omistaja?"
                    opens = False
                if run and len(run) <= 3 and not (skip_opener and opens and len(run) == 1):
                    out.append((" ".join(run), opens))
                run, opens = [], False
    return out


def _fold(counts: Counter[str], known: list[str] = (),
          openers: set[str] = frozenset()) -> Counter[str]:
    folded: Counter[str] = Counter()
    for term, target in _fold_map(counts, known, openers).items():
        folded[target] += counts[term]
    return folded


def _fold_map(counts: Counter[str], known: list[str] = (),
              openers: set[str] = frozenset()) -> dict[str, str]:
    """Count an inflected mention toward its name when the name also occurs —
    here, or among the *known* candidates already found elsewhere. Only the
    last word inflects: "Holiday Clubin" -> "Holiday Club"."""
    by_fold = {t.casefold(): t for t in known}
    by_fold.update((t.casefold(), t) for t in counts)

    def uninflected(low: str) -> str | None:
        for ending in _ENDINGS:
            if low.endswith(ending) and len(low) - len(ending) >= 3:
                stem = by_fold.get(low[: -len(ending)])
                if stem:
                    return stem
        return None

    folded: dict[str, str] = {}
    for term in counts:
        low = term.casefold()
        target = uninflected(low)
        if target is None and term in openers:
            # A verb opening the sentence, glued to a name the study also
            # writes on its own: "Sanoit Alflorexin", "Nouse Holiday Clubin".
            # Only a run that OPENED a sentence: "Suomen Seniorihoiva" is a
            # name even though "Seniorihoiva" is written on its own too.
            tail = low.split(" ", 1)[1]
            target = by_fold.get(tail) or uninflected(tail)
        folded[term] = target or term
    return folded


def _prose_candidates(model: QuestionModel, known: list[str] = ()) -> Counter[str]:
    """Names in the study's own wording: question texts, variable labels and
    option labels, where a capital not opening a sentence is a name."""
    counts: Counter[str] = Counter()
    openers: set[str] = set()
    texts = [q.text for q in getattr(model, "questions", ()) or ()]
    for var in model.variables.values():
        if _is_metadata(var):
            continue            # "IP Address" is the survey tool's, not a name
        texts.append(var.label)
        texts.extend(vl.label for vl in var.value_labels)
    for text in texts:
        for run, opens in _runs(_CODE_PREFIX.sub("", text or ""), skip_opener=True):
            counts[run] += 1
            if opens and " " in run:
                openers.add(run)
        counts.update(m.group(0) for m in _DOMAIN.finditer(text or ""))
    return _fold(counts, known, openers)


def _open_answer_candidates(model: QuestionModel, df, known: list[str] = ()
                            ) -> tuple[Counter[str], dict[str, str]]:
    """Names respondents wrote, counted once per answer that mentions them, and
    the question each was written most in answer to."""
    counts: Counter[str] = Counter()
    where: dict[str, Counter[str]] = {}
    if df is None:
        return counts, {}
    for var in model.variables.values():
        if var.measurement != "text" or var.name not in df.columns:
            continue
        if _is_metadata(var):
            continue
        for answer in df[var.name].dropna().astype(str):
            found = set(capital_runs(answer, skip_opener=False))
            found.update(m.group(0) for m in _DOMAIN.finditer(answer))
            # A word SHOUTED is a place typed with caps lock ("HELSINKI"), not a
            # name; an acronym (DNA, OP, OLW) is short and kept.
            for t in found:
                if not (t.isupper() and len(t) > 4):
                    counts[t] += 1
                    where.setdefault(t, Counter())[var.label or var.name] += 1
    folded: Counter[str] = Counter()
    folded_where: dict[str, Counter[str]] = {}
    for term, target in _fold_map(counts, known).items():
        folded[target] += counts[term]
        folded_where.setdefault(target, Counter()).update(where[term])
    return folded, {t: w.most_common(1)[0][0] for t, w in folded_where.items()}


def _is_fragment(term: str, n: int, common: list[tuple[str, int]]) -> bool:
    """A one-word term that is the start of a longer, more-written one: an
    answer cut short ("Syns", "Instru") rather than a name of its own.
    *common* is the (casefolded term, count) of every term written often
    enough to be offered — only those can make another one a fragment."""
    if " " in term:
        return False
    low = term.casefold()
    return any(m > n and len(o) > len(low) and o.startswith(low) for o, m in common)


@dataclass(frozen=True)
class Candidates:
    """What to put to the model, the lists the structure offered it in, and
    where each candidate came from (see `pick_company_terms`)."""

    terms: list[str]
    lists: tuple[tuple[str, ...], ...]
    #: term -> (kind, text): ("options", the question it is an option of),
    #: ("answers", the open question respondents wrote it in answer to) or
    #: ("wording", "") for a name in the study's own text.
    sources: dict[str, tuple[str, str]] = field(default_factory=dict)


def propose_candidates(grouped: QuestionModel, raw: QuestionModel,
                       df=None) -> Candidates:
    """Everything that could name a company, for `ai.text.pick_company_terms`.

    The structural proposal first (`propose_from_models`), then names in the
    study's wording, then names respondents wrote in open answers. Recall is
    the point: the model drops what is not a name.
    """
    structural = propose_from_models(grouped, raw)
    _gc, g_lists, g_sources = _structure(grouped)
    _rc, r_lists, r_sources = _structure(raw)
    lists = g_lists + r_lists

    prose = _prose_candidates(raw, structural)
    written, answered_in = _open_answer_candidates(raw, df, structural + list(prose))
    common = [(t.casefold(), n) for t, n in written.items() if n >= MIN_RESPONDENTS]
    open_terms: list[str] = []
    for t, n in written.most_common():
        if n < MIN_RESPONDENTS or len(open_terms) >= MAX_OPEN_TERMS:
            break
        if _open_term_ok(t) and not _is_fragment(t, n, common):
            open_terms.append(t)

    terms: dict[str, str] = {}
    sources: dict[str, tuple[str, str]] = {}
    for t in structural:
        terms.setdefault(t.casefold(), t)
        sources.setdefault(t, ("options", g_sources.get(t) or r_sources.get(t, "")))
    for t in (t for t, _n in prose.most_common() if _open_term_ok(t)):
        if t.casefold() not in terms:
            terms[t.casefold()] = t
            sources[t] = ("wording", "")
    for t in open_terms:
        if t.casefold() not in terms:
            terms[t.casefold()] = t
            sources[t] = ("answers", answered_in.get(t, ""))
    return Candidates(terms=list(terms.values()),
                      lists=tuple(dict.fromkeys(lists)), sources=sources)


def _open_term_ok(term: str) -> bool:
    if len(term) < 2:
        return False
    if _DOMAIN.fullmatch(term):
        return True
    return _candidate(term) == term


#: The share of a list the model must have picked before the rest is offered
#: with it; see `with_siblings`.
SIBLING_SHARE = 0.5


def with_siblings(picked: list[str], candidates: Candidates) -> list[str]:
    """The model's picks, plus the rest of any list it mostly picked.

    The model is not consistent about long lists: on Synsam it kept 11 of 15
    names in one run and 7 in the next, dropping Instagram and YouTube beside
    Facebook, and on Taffel it dropped Estrella and Red Head from a brand
    list whose other fourteen members it kept. A list whose members are mostly
    names is a brand list, and its remaining members are offered with it. The
    analyst still ticks each one; nothing is accepted here.
    """
    out = list(picked)
    have = {t.casefold() for t in picked}
    for lst in candidates.lists:
        hits = sum(1 for t in lst if t.casefold() in have)
        if hits >= 2 and hits >= SIBLING_SHARE * len(lst):
            for t in lst:
                if t.casefold() not in have:
                    have.add(t.casefold())
                    out.append(t)
    return out


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
