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

# Soft cap on a slide title length, mentioned in the prompt (C.2).
MAX_TITLE_LEN = 70


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
    return (
        "Olet markkinatutkimusraporttien otsikoija. "
        f"Kaavion taustakysymys: \"{question_text}\".\n"
        "Kaavion kärkitulokset (kategoria: arvo):\n"
        f"{findings_block}\n\n"
        "Kirjoita YKSI lyhyt, kuvaileva suomenkielinen otsikko, joka kertoo mitä "
        "kaavio näyttää ja nostaa esiin johtavan tuloksen. "
        f"Pidä otsikko lyhyenä (enintään noin {MAX_TITLE_LEN} merkkiä). "
        "ÄLÄ toista kysymystä sellaisenaan, äläkä kirjoita kokonaista virkettä tai "
        "listaa. Palauta vain otsikko ilman lainausmerkkejä."
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


__all__ = ["generate_slide_title", "shorten_labels", "MAX_LABEL_LEN", "MAX_TITLE_LEN"]
