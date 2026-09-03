"""egoHive-backed AI text services for the nSight report builder.

Two editable, AI-defaulted text fields are produced here — and ONLY the prose:
the numbers stay 100% deterministic from the stats engine. The caller stores the
results in ``ChartSpec.slide_title`` / ``ChartSpec.category_label_overrides``.

- :func:`generate_slide_title` — a short *descriptive* Finnish headline that says
  what the chart shows (highlighting the leading result), not the raw question.
- :func:`shorten_labels` — short Finnish category labels: reuse a verbatim
  reference short label when one matches the originating decks, otherwise
  AI-shorten in a single batched egoHive call (max ~24 chars, no ellipsis).

Every function takes an injectable ``chat`` callable so the logic is
unit-testable offline with a fake. The default is never bare
:func:`~reportbuilder.ai.masked_chat.datahive_chat` but one of its
purpose-bound wrappers (``M.synthesise``, ``M.summarise``, ``M.rewrite``,
``M.classify``, ``M.converse``), chosen to match what THIS function's prompt
asks the model to do — interpret, condense, reword, or choose. datahive reads
that purpose to pick the model, so a wrong one here is answered by the wrong
size of model, silently and with plausible output.

That default is load-bearing, not a convenience. It routes every prompt through
datahive, which pseudonymises the study's company names before a vendor model
sees them and restores them in the reply. Calling a model directly from here
would send a confidential brand tracker — client and competitors, named — to a
third party. If you add a function to this module, take `chat` the same way and
let it default the same way.
"""
from __future__ import annotations

import json
import logging
import re

from nsight.agent.egohive_client import EgoHiveError, _clean
from reportbuilder.ai import masked_chat as M

from reportbuilder.ai.reference import ReferenceLabels

log = logging.getLogger(__name__)

# Max length for an AI-shortened category label (C.2).
MAX_LABEL_LEN = 24

# Soft cap on a slide title length. A title is an analytical key message
# ("avainviesti"), so it needs room for a short conclusion — not a 3-word slogan.
MAX_TITLE_LEN = 110

#: What the model writes at the very end of a finished headline, so that a
#: headline which never got to its end can be told from one that did.
#:
#: The relay's output budget is spent on the model's own reasoning before the
#: visible answer is written, and a headline is exactly the reasoning-heavy,
#: hundred-character job that runs out: measured against the local hive, a
#: mechanical 629-character reply came back whole while every analytical
#: headline stopped between 80 and 110 characters, mid-word. Six of one
#: customer's thirty slides carried the wreckage — "…työnantajana selvästi yks"
#: — and a generated title is tagged with the data it was written about, so
#: nothing ever reconsidered it.
#:
#: A mark at the END is what makes this detectable at all. Anything cut short
#: loses its last characters first, and the mark is the last of them; if it
#: survived, nothing after it was lost. Guessing from the text instead —
#: "does this end mid-word?" — means teaching this module Finnish morphology,
#: which it would get wrong in both directions.
TITLE_END_MARK = "¶"

# Style exemplars: real analytical key-message headlines from nSight decks.
# They state the SUBJECT of the question and the KEY CONCLUSION from the data —
# not a restatement of the question, not a bare slogan.
_TITLE_EXAMPLES = (
    "Yleinen käsitys yksityisistä palveluntarjoajista on kohentunut ja on nyt yhtä myönteinen kuin julkisista",
    "Attendo tunnetaan selvästi parhaiten yksityisistä hoivapalveluiden tarjoajista",
    "Suurin osa vastaajista valitsisi mieluummin yksityisen kuin julkisen hoivapalvelun",
)


# --------------------------------------------------------------------------- #
# Slide title
# --------------------------------------------------------------------------- #
def _slide_title_prompt(question_text: str, findings: list[tuple[str, float]]) -> str:
    """Compose the Finnish descriptive-headline prompt."""
    lines = []
    for label, value in findings:
        # Format value compactly (drop trailing .0).
        v = f"{value:.0f}" if float(value).is_integer() else f"{value:.1f}"
        lines.append(f"- {label}: {v}")
    findings_block = "\n".join(lines) if lines else "- (ei kärkituloksia)"
    examples_block = "\n".join(f"- {e}" for e in _TITLE_EXAMPLES)
    return (
        "Olet markkinatutkimuksen analyytikko. Kirjoitat kaaviolle avainviestin "
        "(otsikon), joka kertoo lukijalle, mitä kysyttiin ja mikä on vastausten "
        "keskeinen johtopäätös.\n\n"
        f"Kysymys (mitä kysyttiin): \"{question_text}\".\n"
        "Vastausten kärkitulokset (kategoria: arvo):\n"
        f"{findings_block}\n\n"
        "Esimerkkejä hyvän avainviestin tyylistä:\n"
        f"{examples_block}\n\n"
        "Kirjoita YKSI suomenkielinen avainviesti, joka tiivistää kysymyksen aiheen "
        "ja vastausten keskeisen johtopäätöksen yhdeksi analyyttiseksi havainnoksi. "
        "Otsikon tulee TULKITA tuloksia (mitä data kertoo), ei vain todeta yksittäistä "
        "lukua tai toistaa kysymystä. Vältä iskulausetta; kirjoita kuten esimerkeissä. "
        f"Enintään noin {MAX_TITLE_LEN} merkkiä, yksi rivi, ei lainausmerkkejä, ei "
        "loppupistettä. "
        f"Kirjoita aivan loppuun merkki {TITLE_END_MARK}, jotta tiedämme "
        "vastauksen valmistuneen."
    )


def generate_slide_title(
    question_text: str,
    findings: list[tuple[str, float]],
    *,
    # `summarise`, not `synthesise`. A headline CONDENSES what the findings
    # already say; it does not reach past them. The distinction is the hive's:
    # synthesise is for output allowed to state something no input sentence
    # stated, and it is bound to `generous` deliberation because that is the one
    # place deliberation pays. A title is not that place, and the measurement
    # said so before the taxonomy did — deliberating took 6.8-7.4s and returned
    # the only headline with no number in it, a hedge where the job was to
    # report.
    #
    # Measured over all 30 questions of a real study, not a short sample: at
    # `summarise` (thinking=low) a headline costs a MEDIAN of ~10s and as much
    # as 41s, because these questions are long and the deliberation scales with
    # them. The same 30 prompts at thinking=floor cost 1.43s median, 1.65s at
    # worst, with headlines a reader cannot tell apart — and rather more of them
    # carrying an actual number. The remaining cost is the hive's to remove:
    # `summarise` is bound to `low` there, and this work wants `floor`.
    chat=M.summarise,
) -> str:
    """Generate a short descriptive Finnish slide title.

    ``findings`` is the top categories with their values (label, pct). Returns a
    single clean line. ``EgoHiveError`` propagates so the endpoint can map it to
    a 503; on an empty reply we fall back to the question text.
    """
    prompt = _slide_title_prompt(question_text, findings)
    reply = chat(prompt)
    fallback = (question_text or "").strip()
    raw = (reply or "").strip()
    if not raw:
        return fallback
    # Only a headline that reached its end is a headline. Without the mark the
    # answer was cut off somewhere we cannot see, and half a sentence printed on
    # a slide is worse than the question it was meant to improve on — which is
    # exactly what the question text is: what the deck showed before there were
    # generated headlines at all.
    if TITLE_END_MARK not in raw:
        log.warning("ai: slide title arrived without its end mark, so it was cut "
                    "short; falling back to the question text (%r)", raw[-40:])
        return fallback
    # The mark may land either side of the model's own wrapping: `"Otsikko"¶`
    # puts it outside, `"**Otsikko ¶**"` inside. Cleaning the whole reply first
    # leaves a stray opening quote in the first case; cutting at the mark first
    # leaves one in the second. So cut at the mark, then re-attach only the
    # closing WRAPPER PUNCTUATION that followed it — never words, so anything
    # the model kept writing after its headline is still discarded.
    head, _, tail = raw.partition(TITLE_END_MARK)
    closer = "".join(ch for ch in tail if ch in '*_"\'`»)]}')
    return _clean(head + closer) or fallback


def _group_subtitle_prompt(member_labels: list[str]) -> str:
    """Compose the prompt for a battery/multi SUBTITLE — a neutral topic description
    (not a key message), shown just above the chart."""
    items = "\n".join(f"- {m}" for m in member_labels)
    return (
        "Olet markkinatutkimuksen analyytikko. Alla on joukko osioita/väittämiä, jotka "
        "kuuluvat samaan kysymyskokonaisuuteen ja on esitetty vastaajille yhdessä.\n\n"
        f"Osiot:\n{items}\n\n"
        "Kirjoita YKSI lyhyt suomenkielinen KUVAUS siitä, mitä tämä kokonaisuus mittaa "
        "(esimerkiksi \"Väittämiä työstä ja teknologiasta\"). Kuvaus on neutraali "
        "otsikkorivi kaavion yläpuolelle — EI avainviesti, EI johtopäätös, EIKÄ toisto "
        "yhdestä osiosta. Enintään noin 90 merkkiä, yksi rivi, ei lainausmerkkejä, ei "
        "loppupistettä."
    )


def generate_group_subtitle(member_labels, *, chat=M.summarise) -> str:
    """A short neutral Finnish description of what a battery/multi covers, from its
    member labels. Empty string on an empty reply (caller falls back)."""
    labels = [str(m).strip() for m in member_labels if str(m).strip()]
    if not labels:
        return ""
    return _clean(chat(_group_subtitle_prompt(labels)))


# --------------------------------------------------------------------------- #
# Label shortening
# --------------------------------------------------------------------------- #
def _shorten_prompt(labels: list[str], examples: list[str]) -> str:
    """Compose the batched Finnish label-shortening prompt."""
    numbered = "\n".join(f"{i + 1}. {lbl}" for i, lbl in enumerate(labels))
    sample = ", ".join(examples) if examples else "(ei esimerkkejä)"
    return (
        "Lyhennä seuraavat kategoriaotsikot suomeksi kaavioita varten. "
        f"Tee jokaisesta tiivis otsikko, enintään {MAX_LABEL_LEN} merkkiä, "
        "ÄLÄ KOSKAAN käytä kolmea pistettä (…) tai ellipsiä, säilytä merkitys. "
        f"Noudata näiden esimerkkien tyyliä: {sample}.\n\n"
        "Otsikot:\n"
        f"{numbered}\n\n"
        "Palauta vastaus numeroituna listana samassa järjestyksessä, "
        "yksi lyhennetty otsikko per rivi muodossa 'numero. lyhennys'."
    )


def _postprocess_short(short: str, full: str) -> str:
    """Enforce the ≤24-char / no-ellipsis guarantees; fall back to full if empty."""
    s = _clean(short)
    # Strip any ellipsis the model added despite instructions.
    s = s.replace("…", "").replace("...", "").strip()
    # Trim dangling separators left by the ellipsis removal.
    s = s.strip(" -–—·,;:").strip()
    if len(s) > MAX_LABEL_LEN:
        s = s[:MAX_LABEL_LEN].rstrip(" -–—·,;:").strip()
    if not s:
        return full
    return s


def _parse_numbered(reply: str, labels: list[str]) -> dict[str, str]:
    """Parse a numbered-list reply back to {full_label: short_label}.

    Robust to leading bullets/whitespace. Returns an empty dict when the reply
    cannot be confidently mapped (caller then falls back to the originals).
    """
    numbered: list[tuple[int, str]] = []
    plain: list[str] = []
    for raw in reply.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^\(?(\d+)[\.\):\-]\s+(.+)$", line)
        if m:
            numbered.append((int(m.group(1)), m.group(2).strip()))
        else:
            plain.append(line)

    result: dict[str, str] = {}
    if numbered:
        for idx, text in numbered:
            if 1 <= idx <= len(labels):
                result[labels[idx - 1]] = text
        return result
    # No numbering: only accept a clean 1:1 line-per-label mapping.
    if len(plain) == len(labels):
        for lbl, text in zip(labels, plain):
            result[lbl] = text
    return result


def shorten_labels(
    full_labels: list[str],
    *,
    reference: ReferenceLabels,
    chat=M.rewrite,
) -> list[tuple[str, str]]:
    """Return ``(full, short)`` pairs for labels that need shortening.

    For each label: reuse a verbatim reference short label when one matches;
    otherwise AI-shorten (one batched egoHive call). Order is preserved and only
    pairs where ``short != full`` are included. Never crashes: a malformed or
    unreachable AI reply falls back to the original label.
    """
    matched: dict[str, str] = {}
    to_ai: list[str] = []
    for label in full_labels:
        ref = reference.match(label)
        if ref is not None:
            matched[label] = ref
        elif label not in to_ai:
            to_ai.append(label)

    ai_map: dict[str, str] = {}
    if to_ai:
        prompt = _shorten_prompt(to_ai, reference.examples())
        try:
            reply = chat(prompt)
            ai_map = _parse_numbered(reply, to_ai)
        except EgoHiveError:
            # AI unreachable -> fall back to originals (never crash). (C.2)
            ai_map = {}

    out: list[tuple[str, str]] = []
    for label in full_labels:
        if label in matched:
            short = matched[label]
        elif label in ai_map:
            short = _postprocess_short(ai_map[label], label)
        else:
            short = label  # fallback to original
        if short != label:
            out.append((label, short))
    return out


# --------------------------------------------------------------------------- #
# Special slides — Overview / Conclusion / Demographics (bullet lists)
# --------------------------------------------------------------------------- #
# Soft cap on how many bullets a special slide shows (paginated across slides when
# they don't all fit). The wider 16:9 slide holds more, so allow a richer list.
MAX_BULLETS = 8

# Appended to EVERY bullet-list prompt. The output goes straight onto a slide, so the
# model must return only the analytical bullets — no preamble, no closing remark, and
# above all no conversational meta aimed at the reader (e.g. "Oliko tämä yhteenveto
# hyödyllinen jatkotyöstöäsi varten?", offers of further help). Those are chat
# pleasantries, never slide content.
_BULLET_OUTPUT_RULES = (
    "\n\nTULOSTEEN MUOTO — EHDOTON:\n"
    "Vastaus menee sellaisenaan koneellisesti PowerPoint-dialle. Palauta VAIN "
    "ranskalaiset viivat, yksi itsenäinen analyyttinen havainto per rivi. Vastauksen "
    "VIIMEINEN rivi on viimeinen havainto — ÄLÄ kirjoita yhtäkään riviä sen jälkeen.\n"
    "EHDOTTOMASTI KIELLETTY (ei koskaan, ei edes viimeisellä rivillä): johdanto, "
    "otsikko, yhteenveto tai loppukommentti; lukijan puhuttelu; MIKÄ TAHANSA kysymys "
    "lukijalle; tarjous jatkaa, syventyä, tehdä seuraava raportti tai auttaa lisää "
    "(esim. 'Haluatko, että syvennyn…', 'Haluatko siirtyä seuraavaan…', 'Oliko tämä "
    "hyödyllinen…', 'Voin auttaa…'); oman vastauksesi kommentointi. Nämä ovat "
    "chat-kohteliaisuuksia, EIVÄT diasisältöä."
)


def _parse_bullets(reply: str) -> list[str]:
    """Parse an LLM reply into clean bullet strings.

    Accepts numbered ("1. …"), dashed ("- …"/"• …"/"* …") or plain lines; strips
    the marker and surrounding quotes/whitespace; drops empties. Capped to
    ``MAX_BULLETS``.
    """
    out: list[str] = []
    for raw in reply.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Drop markdown code-fence lines — some models wrap the whole reply in a
        # ``` block, so the opening/closing fence ("```", "```json",
        # "```question:yes_no") would otherwise leak through as a final bullet.
        if line.startswith("```") or line.startswith("~~~"):
            continue
        # Strip a leading "1." / "1)" / "-" / "•" / "*" marker. Require a space
        # after a "*" marker so a bullet that STARTS with markdown bold
        # (**avainsana**) is not mangled into "*avainsana**".
        line = re.sub(r"^\(?\d+[\.\):\-]\s*", "", line)
        line = re.sub(r"^([\-•]\s*|\*\s+)", "", line)
        line = line.strip().strip('"').strip()
        # Drop degenerate "odd" bullets: empties, or a line that is only markers
        # / punctuation / stray markdown left after stripping (no real letters).
        if not line or not re.search(r"[^\s\-•*_:.,–—]", line):
            continue
        out.append(line)
    return out[:MAX_BULLETS]


def _study_line(study_label: str, prefix: str = "Tutkimus") -> str:
    """A '<prefix>: "<label>".' line, or empty when no real study label is known."""
    label = (study_label or "").strip()
    return f'{prefix}: "{label}".\n' if label else ""


def _findings_block(findings_by_question: list[tuple[str, list[tuple[str, float]]]]) -> str:
    """Render per-question top findings as a compact text block for a prompt."""
    blocks = []
    for q_text, findings in findings_by_question:
        if not findings:
            continue
        lines = []
        for label, value in findings:
            v = f"{value:.0f}" if float(value).is_integer() else f"{value:.1f}"
            lines.append(f"    - {label}: {v}")
        blocks.append(f"- {q_text}\n" + "\n".join(lines))
    return "\n".join(blocks) if blocks else "- (ei tuloksia)"


def generate_data_chat(
    study_label: str,
    findings_by_question: list[tuple[str, list[tuple[str, float]]]],
    messages: list[dict],
    total_n: int | None = None,
    *,
    chat=M.converse,
) -> str:
    """Answer the user's question about the survey DATA, grounded in the per-question
    findings. ``messages`` is the conversation so far ([{role, content}, …]); only
    the recent turns are kept to bound prompt size. The model is told to use ONLY
    the data below and to reply in the user's language."""
    study = _study_line(study_label)
    n_line = f"Vastaajia yhteensä: {total_n}.\n" if total_n else ""
    data = _findings_block(findings_by_question)
    recent = [m for m in messages if m.get("content", "").strip()][-10:]
    convo = "\n".join(
        f"{'Käyttäjä' if m.get('role') == 'user' else 'Avustaja'}: {m['content'].strip()}"
        for m in recent
    )
    prompt = (
        "Olet kyselytutkimuksen data-analyytikko ja avustaja nSight Studiossa. "
        "Vastaat käyttäjän kysymyksiin TÄSMÄLLEEN alla olevan tutkimusdatan "
        "perusteella. ÄLÄ keksi lukuja äläkä tietoja; jos vastaus ei löydy "
        "datasta, kerro se rehellisesti. Vastaa lyhyesti, selkeästi ja samalla "
        "kielellä jota käyttäjä käyttää. Vastaa PELKKÄNÄ tekstinä — älä käytä "
        "koodilohkoja (```), 'question:'-lohkoja tai muita rakenteisia "
        "valikoita.\n\n"
        f"{study}{n_line}\n"
        "Tutkimusdata (kysymys ja yleisimmät vastaukset / keskiarvot):\n"
        f"{data}\n\n"
        "Keskustelu tähän asti:\n"
        f"{convo}\n"
        "Avustaja:"
    )
    reply = (chat(prompt) or "").strip()
    # Strip any ```…``` / ~~~…~~~ fenced blocks the model appends (it sometimes
    # adds a 'question:single_select' follow-up menu we don't want shown raw).
    reply = re.sub(r"\n*(```|~~~).*?(\1|\Z)", "", reply, flags=re.DOTALL).strip()
    return reply


def generate_overview_bullets(
    study_label: str,
    question_texts: list[str],
    total_n: int | None,
    *,
    chat=M.summarise,
) -> list[str]:
    """Generate Finnish background/overview bullets describing the research."""
    topics = "\n".join(f"- {t}" for t in question_texts[:30]) or "- (ei kysymyksiä)"
    n_line = f"Vastaajia yhteensä: {total_n}.\n" if total_n else ""
    prompt = (
        "Olet markkinatutkimuksen analyytikko. Kirjoitat raportin aloitusdialle "
        "lyhyet taustatiedot tutkimuksesta.\n\n"
        f"{_study_line(study_label, 'Tutkimuksen nimi')}"
        f"{n_line}"
        "Tutkimuksessa käsitellyt aiheet (kysymykset):\n"
        f"{topics}\n\n"
        f"Kirjoita {MAX_BULLETS - 1}–{MAX_BULLETS} ranskalaista viivaa suomeksi, jotka "
        "kuvaavat tutkimuksen taustan ja tavoitteet: mitä tutkittiin, keneltä ja mitä "
        "teemoja kartoitettiin. Yksi tiivis havainto per rivi, ei numerointia, ei "
        "lainausmerkkejä. Palauta vain ranskalaiset viivat."
    )
    return _parse_bullets(chat(prompt + _BULLET_OUTPUT_RULES))


def generate_conclusion_bullets(
    study_label: str,
    findings_by_question: list[tuple[str, list[tuple[str, float]]]],
    *,
    chat=M.synthesise,
) -> list[str]:
    """Generate Finnish conclusion bullets summarising the major findings."""
    prompt = (
        "Olet markkinatutkimuksen analyytikko. Kirjoitat raportin "
        "johtopäätösdialle keskeiset johtopäätökset.\n\n"
        f"{_study_line(study_label)}"
        "Kysymysten kärkitulokset (kysymys ja sen vastausten kärki):\n"
        f"{_findings_block(findings_by_question)}\n\n"
        f"Kirjoita {MAX_BULLETS - 1}–{MAX_BULLETS} ranskalaista viivaa suomeksi, jotka "
        "tiivistävät tutkimuksen TÄRKEIMMÄT johtopäätökset. Tulkitse tuloksia (mitä "
        "data kokonaisuutena kertoo), älä luettele yksittäisiä lukuja. Korosta kunkin "
        "rivin avainsanat lihavoinnilla markdown-muodossa (**avainsana**). Yksi "
        "johtopäätös per rivi, ei numerointia, ei lainausmerkkejä. Palauta vain "
        "ranskalaiset viivat."
    )
    return _parse_bullets(chat(prompt + _BULLET_OUTPUT_RULES))


# Themes shown for an open-ended question.
MAX_THEMES = 6


def generate_open_themes(
    question_text: str,
    word_freqs: list[tuple[str, float]],
    sample_answers: list[str],
    *,
    chat=M.summarise,
) -> list[str]:
    """Summarise an open-ended question's answers into a few key themes.

    Given the question, the most frequent words (with counts) and a sample of
    verbatim answers, return markdown bullets — each a bold theme name plus an
    approximate share, e.g. '**Edulliset hinnat** – mainittu noin 40 %:ssa'.
    """
    freqs = "\n".join(f"- {w}: {int(c)}" for w, c in word_freqs[:25]) or "- (ei sanoja)"
    sample = "\n".join(f"- {a.strip()}" for a in sample_answers[:40] if a.strip())
    prompt = (
        "Olet markkinatutkimuksen analyytikko. Tiivistät avoimen kysymyksen "
        "vastaukset muutamaan keskeiseen teemaan.\n\n"
        f"Avoin kysymys: \"{question_text}\".\n"
        "Yleisimmät sanat vastauksissa (sana: lukumäärä):\n"
        f"{freqs}\n\n"
        "Otos vastauksista:\n"
        f"{sample or '- (ei otosta)'}\n\n"
        f"Ryhmittele vastaukset {MAX_THEMES - 2}–{MAX_THEMES} merkitykselliseen teemaan. "
        "Anna jokaiselle teemalle lyhyt nimi LIHAVOITUNA (markdown **nimi**) ja arvioi "
        "kuinka yleinen teema on (esim. osuus vastauksista). Järjestä yleisimmästä "
        "harvinaisimpaan. Yksi teema per ranskalainen viiva, ei numerointia, esim. "
        "'- **Edulliset hinnat ja tarjoukset** – mainittu noin 40 %:ssa vastauksista'. "
        "Palauta vain ranskalaiset viivat."
    )
    return _parse_bullets(chat(prompt + _BULLET_OUTPUT_RULES))[:MAX_THEMES]


def pick_demographic_questions(
    candidates: list[tuple[str, str]],
    *,
    chat=M.classify,
) -> list[str]:
    """Return the qids the LLM judges to be demographic/background variables.

    ``candidates`` is ``[(qid, label), …]``. The reply is intersected with the
    candidate qids, so hallucinated ids are dropped by the caller too.
    """
    listing = "\n".join(f"{qid}: {label}" for qid, label in candidates)
    prompt = (
        "Olet markkinatutkimuksen analyytikko. Alla on tutkimuksen kysymykset "
        "muodossa 'tunnus: kysymys'.\n\n"
        f"{listing}\n\n"
        "Valitse NIIDEN kysymysten tunnukset, jotka kuvaavat vastaajien "
        "taustatietoja eli demografiaa (esim. ikä, sukupuoli, asuinalue/maantiede, "
        "kotitalous, koulutus, tulot). Palauta VAIN tunnukset pilkulla erotettuna, "
        "ei muuta tekstiä. Jos demografisia kysymyksiä ei ole, palauta tyhjä rivi."
    )
    reply = chat(prompt)
    valid = {qid for qid, _ in candidates}
    picked: list[str] = []
    for token in re.split(r"[,\s]+", reply.strip()):
        t = token.strip().strip(".:)")
        if t in valid and t not in picked:
            picked.append(t)
    return picked


def generate_demographics_bullets(
    study_label: str,
    findings_by_question: list[tuple[str, list[tuple[str, float]]]],
    *,
    chat=M.summarise,
) -> list[str]:
    """Generate Finnish 'facts about the respondents' bullets from demographics."""
    prompt = (
        "Olet markkinatutkimuksen analyytikko. Kirjoitat raportin dialle, joka "
        "kuvaa vastaajajoukon (keitä tutkimukseen vastasivat).\n\n"
        f"{_study_line(study_label)}"
        "Demografisten kysymysten jakaumat:\n"
        f"{_findings_block(findings_by_question)}\n\n"
        f"Kirjoita {MAX_BULLETS - 1}–{MAX_BULLETS} ranskalaista viivaa suomeksi, jotka "
        "esittävät keskeiset faktat vastaajista (esim. ikäjakauma, sukupuolijakauma, "
        "maantieteellinen jakauma). Käytä lukuja jakaumista. Yksi fakta per rivi, ei "
        "numerointia, ei lainausmerkkejä. Palauta vain ranskalaiset viivat."
    )
    return _parse_bullets(chat(prompt + _BULLET_OUTPUT_RULES))


__all__ = [
    "generate_slide_title",
    "shorten_labels",
    "generate_overview_bullets",
    "generate_conclusion_bullets",
    "generate_open_themes",
    "pick_demographic_questions",
    "generate_demographics_bullets",
    "MAX_LABEL_LEN",
    "MAX_TITLE_LEN",
    "MAX_BULLETS",
]

def pick_company_terms(candidates: list[str], questions: list[str], *,
                       chat=M.identify) -> list[str]:
    """Which of *candidates* actually name a company, organisation or brand.

    The structural proposer reads the study's shape and offers everything that
    could be a name; this decides. It replaced a growing pile of Finnish word
    rules that lost ground with every new study — on `Mobiilivarmennedata` the
    rules offered six terms and every one was a rating-scale point ("Tärkeä",
    "Heikosti", "Ensisijaisesti"), which teaches an analyst that the list is
    not worth reading, and an analyst who stops reading it either confirms
    everything or skips the step. Both lose the protection.

    Only the candidate strings and the question wording are sent: no findings,
    no percentages, no respondent answers. A bare list of names, with nothing
    said about them, discloses nothing — which is what makes this the one call
    that runs unmasked (see `M.identify`). Masking it would hand the model
    surrogates of the very strings it is being asked to recognise.

    The reply must be a JSON list drawn from the candidates. Anything else
    raises, because "no answer" must reach the analyst as an error they can
    retry: an empty list would read as "nothing to mask" and leave the study
    unprotected without saying so.
    """
    wanted = [c for c in (candidates or []) if c and c.strip()]
    if not wanted:
        return []
    context = "\n".join(q for q in (questions or []) if q)[:4000]
    prompt = (
        "Tämä on suomalaisen kyselytutkimuksen rakenteesta poimittu lista "
        "ehdokasmerkkijonoja. Osa on yritysten, organisaatioiden tai "
        "tuotemerkkien nimiä; osa on asteikon vastausvaihtoehtoja, kyselyn "
        "omaa sanastoa tai muuta yleiskieltä.\n\n"
        + (f"Kyselyn kysymyksiä kontekstiksi:\n{context}\n\n" if context else "")
        + "Ehdokkaat:\n" + "\n".join(f"- {c}" for c in wanted) + "\n\n"
        "Vastaa JSON-listana, joka sisältää VAIN ne ehdokkaat, jotka ovat "
        "yrityksen, organisaation tai tuotemerkin nimiä, täsmälleen samassa "
        "kirjoitusasussa kuin yllä. Jos yksikään ei ole, vastaa []. "
        "Älä selitä mitään; vastaa pelkkä JSON-lista."
    )
    reply = (chat(prompt) or "").strip()
    match = re.search(r"\[.*\]", reply, re.S)
    if not match:
        raise EgoHiveError(
            f"the model did not answer with a list of terms: {reply[:120]!r}")
    try:
        named = json.loads(match.group(0))
    except ValueError as exc:
        raise EgoHiveError(f"unreadable list of terms: {exc}") from exc
    if not isinstance(named, list):
        raise EgoHiveError("the model's answer was not a list")
    # Only ever a subset of what was asked about. A name we never proposed is
    # invented, and registering it would mask a word the study never used.
    allowed = {c.strip().casefold(): c for c in wanted}
    out: list[str] = []
    for item in named:
        hit = allowed.get(str(item).strip().casefold())
        if hit and hit not in out:
            out.append(hit)
    return out
