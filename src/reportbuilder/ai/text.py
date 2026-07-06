"""egoHive-backed AI text services for the nSight report builder.

Two editable, AI-defaulted text fields are produced here — and ONLY the prose:
the numbers stay 100% deterministic from the stats engine. The caller stores the
results in ``ChartSpec.slide_title`` / ``ChartSpec.category_label_overrides``.

- :func:`generate_slide_title` — a short *descriptive* Finnish headline that says
  what the chart shows (highlighting the leading result), not the raw question.
- :func:`shorten_labels` — short Finnish category labels: reuse a verbatim
  reference short label when one matches the originating decks, otherwise
  AI-shorten in a single batched egoHive call (max ~24 chars, no ellipsis).

Every function takes an injectable ``chat`` callable (default
:func:`egohive_chat`) so the logic is unit-testable offline with a fake.
"""
from __future__ import annotations

import re

from nsight.agent.egohive_client import EgoHiveError, _clean, egohive_chat

from reportbuilder.ai.reference import ReferenceLabels

# Max length for an AI-shortened category label (C.2).
MAX_LABEL_LEN = 24

# Soft cap on a slide title length. A title is an analytical key message
# ("avainviesti"), so it needs room for a short conclusion — not a 3-word slogan.
MAX_TITLE_LEN = 110

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
        "loppupistettä."
    )


def generate_slide_title(
    question_text: str,
    findings: list[tuple[str, float]],
    *,
    chat=egohive_chat,
) -> str:
    """Generate a short descriptive Finnish slide title.

    ``findings`` is the top categories with their values (label, pct). Returns a
    single clean line. ``EgoHiveError`` propagates so the endpoint can map it to
    a 503; on an empty reply we fall back to the question text.
    """
    prompt = _slide_title_prompt(question_text, findings)
    reply = chat(prompt)
    title = _clean(reply)
    if not title:
        return (question_text or "").strip()
    return title


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


def generate_group_subtitle(member_labels, *, chat=egohive_chat) -> str:
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
    chat=egohive_chat,
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
# Soft cap on how many bullets a special slide shows.
MAX_BULLETS = 6

# Appended to EVERY bullet-list prompt. The output goes straight onto a slide, so the
# model must return only the analytical bullets — no preamble, no closing remark, and
# above all no conversational meta aimed at the reader (e.g. "Oliko tämä yhteenveto
# hyödyllinen jatkotyöstöäsi varten?", offers of further help). Those are chat
# pleasantries, never slide content.
_BULLET_OUTPUT_RULES = (
    "\n\nTÄRKEÄÄ: Tuloste tulee suoraan diaesitykseen. Palauta VAIN ranskalaiset "
    "viivat — jokainen rivi itsenäinen analyyttinen havainto. ÄLÄ kirjoita johdantoa, "
    "otsikkoa, yhteenvetoa etkä loppukommenttia. ÄLÄ puhuttele lukijaa, ÄLÄ esitä "
    "kysymyksiä lukijalle (esim. oliko yhteenveto hyödyllinen), ÄLÄ tarjoa lisäapua "
    "etkä kommentoi omaa vastaustasi."
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
    chat=egohive_chat,
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
    chat=egohive_chat,
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
    chat=egohive_chat,
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
    chat=egohive_chat,
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
    chat=egohive_chat,
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
    chat=egohive_chat,
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
