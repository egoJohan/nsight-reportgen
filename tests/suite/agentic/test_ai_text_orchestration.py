"""Deterministic tests for the ``reportbuilder.ai.text`` generators.

Each generator takes an injectable ``chat=`` callable; we drive them with a
``RecordingChat`` and assert (a) the prompt carries the findings/question and
(b) the reply is parsed into the expected shape. No network.
"""
from __future__ import annotations

from reportbuilder.ai.reference import ReferenceLabels
from reportbuilder.ai.text import (
    generate_conclusion_bullets,
    generate_data_chat,
    generate_demographics_bullets,
    generate_open_themes,
    generate_overview_bullets,
    generate_slide_title,
    pick_demographic_questions,
    shorten_labels,
)

from suite._helpers import RecordingChat


# --------------------------------------------------------------------------- #
# generate_slide_title
# --------------------------------------------------------------------------- #
def test_slide_title_prompt_carries_question_and_findings():
    chat = RecordingChat('"**Tyytyväisyys on korkealla**"')
    title = generate_slide_title(
        "Kuinka tyytyväinen olet palveluun?",
        [("Erittäin tyytyväinen", 62.0), ("Melko tyytyväinen", 28.5)],
        chat=chat,
    )
    # _clean strips quotes and markdown emphasis.
    assert title == "Tyytyväisyys on korkealla"
    assert chat.calls == 1
    prompt = chat.prompts[0]
    assert "Kuinka tyytyväinen olet palveluun?" in prompt
    assert "Erittäin tyytyväinen" in prompt
    assert "62" in prompt and "28.5" in prompt  # integer compacted, .5 kept


def test_slide_title_empty_reply_falls_back_to_question_text():
    chat = RecordingChat("")
    title = generate_slide_title("Alkuperäinen kysymysteksti", [("A", 1.0)], chat=chat)
    assert title == "Alkuperäinen kysymysteksti"


# --------------------------------------------------------------------------- #
# shorten_labels — reference verbatim (0 calls) vs AI path
# --------------------------------------------------------------------------- #
def test_shorten_labels_reference_verbatim_no_llm_call():
    # An exact normalized match that is strictly shorter → reused verbatim,
    # the AI is never called.
    reference = ReferenceLabels(labels=["Tyytyväiset"], titles=[])
    chat = RecordingChat("SHOULD NOT BE USED")
    out = shorten_labels(["Tyytyväiset."], reference=reference, chat=chat)
    assert out == [("Tyytyväiset.", "Tyytyväiset")]
    assert chat.calls == 0


def test_shorten_labels_ai_path_parses_numbered_reply():
    reference = ReferenceLabels(labels=[], titles=[])
    chat = RecordingChat("1. Lyhyt yksi\n2. Lyhyt kaksi")
    out = shorten_labels(
        ["Pitkä otsikko numero yksi", "Pitkä otsikko numero kaksi"],
        reference=reference,
        chat=chat,
    )
    assert out == [
        ("Pitkä otsikko numero yksi", "Lyhyt yksi"),
        ("Pitkä otsikko numero kaksi", "Lyhyt kaksi"),
    ]
    assert chat.calls == 1
    assert "Pitkä otsikko numero yksi" in chat.prompts[0]


def test_shorten_labels_omits_unchanged_labels():
    # An AI reply that echoes the original produces no override (short == full).
    reference = ReferenceLabels(labels=[], titles=[])
    chat = RecordingChat("1. Sama teksti")
    out = shorten_labels(["Sama teksti"], reference=reference, chat=chat)
    assert out == []


# --------------------------------------------------------------------------- #
# Bullet generators — parsing of numbered/dashed replies
# --------------------------------------------------------------------------- #
def test_overview_bullets_parsed_and_prompt_lists_topics():
    chat = RecordingChat("- Ensimmäinen havainto\n- Toinen havainto")
    bullets = generate_overview_bullets(
        "Asiakastutkimus 2026", ["Tyytyväisyys", "Suosittelu"], 250, chat=chat
    )
    assert bullets == ["Ensimmäinen havainto", "Toinen havainto"]
    prompt = chat.prompts[0]
    assert "Asiakastutkimus 2026" in prompt
    assert "Tyytyväisyys" in prompt and "Suosittelu" in prompt
    assert "250" in prompt


def test_conclusion_bullets_strip_numbering_keep_bold():
    chat = RecordingChat("1. **Tyytyväisyys** on korkealla\n2. Suosittelu on yleistä")
    bullets = generate_conclusion_bullets(
        "Tutkimus", [("Tyytyväisyys", [("Hyvä", 70.0)])], chat=chat
    )
    # _parse_bullets strips numbering but KEEPS markdown **bold** (unlike _clean).
    assert bullets == ["**Tyytyväisyys** on korkealla", "Suosittelu on yleistä"]
    assert "Hyvä" in chat.prompts[0] and "70" in chat.prompts[0]


def test_open_themes_parsed():
    chat = RecordingChat(
        "- **Hinta** – noin 40 %\n- **Laatu** – noin 25 %"
    )
    bullets = generate_open_themes(
        "Miksi valitsit palvelun?",
        [("hinta", 12.0), ("laatu", 8.0)],
        ["Halpa hinta", "Hyvä laatu"],
        chat=chat,
    )
    assert bullets == ["**Hinta** – noin 40 %", "**Laatu** – noin 25 %"]
    prompt = chat.prompts[0]
    assert "Miksi valitsit palvelun?" in prompt
    assert "hinta" in prompt  # word frequencies fed in


def test_demographics_bullets_parsed():
    chat = RecordingChat("- Enemmistö oli naisia\n- Keski-ikä 45 vuotta")
    bullets = generate_demographics_bullets(
        "Tutkimus", [("Sukupuoli", [("Nainen", 55.0)])], chat=chat
    )
    assert bullets == ["Enemmistö oli naisia", "Keski-ikä 45 vuotta"]


# --------------------------------------------------------------------------- #
# pick_demographic_questions — intersect with candidates, drop hallucinations
# --------------------------------------------------------------------------- #
def test_pick_demographic_questions_filters_to_candidates():
    candidates = [("q1", "Tyytyväisyys"), ("age", "Ikä"), ("gender", "Sukupuoli")]
    chat = RecordingChat("age, gender, hallusinaatio")
    picked = pick_demographic_questions(candidates, chat=chat)
    assert picked == ["age", "gender"]  # unknown 'hallusinaatio' dropped
    assert "tunnukset" in chat.prompts[0]  # pick prompt marker


def test_pick_demographic_questions_empty_reply():
    candidates = [("q1", "Tyytyväisyys")]
    chat = RecordingChat("")
    assert pick_demographic_questions(candidates, chat=chat) == []


# --------------------------------------------------------------------------- #
# generate_data_chat — grounded conversation reply
# --------------------------------------------------------------------------- #
def test_data_chat_prompt_has_findings_and_conversation():
    chat = RecordingChat("Tyytyväisyys on korkea.")
    reply = generate_data_chat(
        "Asiakastutkimus",
        [("Tyytyväisyys", [("Hyvä", 70.0)])],
        [{"role": "user", "content": "Miten tyytyväisyys jakautuu?"}],
        total_n=200,
        chat=chat,
    )
    assert reply == "Tyytyväisyys on korkea."
    prompt = chat.prompts[0]
    assert "Miten tyytyväisyys jakautuu?" in prompt
    assert "Hyvä" in prompt and "70" in prompt
    assert "200" in prompt


def test_data_chat_strips_fenced_blocks():
    chat = RecordingChat("Vastaus tähän.\n```question:single_select\nfoo\n```")
    reply = generate_data_chat(
        "Tutkimus", [("Q", [("A", 1.0)])], [{"role": "user", "content": "kysymys"}], chat=chat
    )
    assert reply == "Vastaus tähän."
    assert "```" not in reply
