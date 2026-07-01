"""Unit tests for the prompt-composing / generator entry points in
``reportbuilder.ai.text`` (pure logic; chat injected via RecordingChat)."""
from __future__ import annotations

import pytest

from nsight.agent.egohive_client import EgoHiveError
from reportbuilder.ai import text as T
from reportbuilder.ai.reference import ReferenceLabels
from suite._helpers import RecordingChat


# --------------------------------------------------------------------------- #
# generate_slide_title
# --------------------------------------------------------------------------- #
def test_slide_title_prompt_contains_question_and_findings():
    findings = [("Attendo", 86.0), ("Esperi", 75.5)]
    chat = RecordingChat("Attendo tunnetaan parhaiten")
    T.generate_slide_title("Mikä brändi tunnetaan?", findings, chat=chat)
    assert chat.calls == 1
    prompt = chat.prompts[0]
    assert "Mikä brändi tunnetaan?" in prompt
    # Integer value formatted without decimals, non-integer with one decimal.
    assert "- Attendo: 86" in prompt
    assert "- Esperi: 75.5" in prompt


def test_slide_title_strips_markdown_and_wrapping_quotes():
    # Single-line reply: markdown emphasis + wrapping quotes are stripped.
    chat = RecordingChat('"**Attendo johtaa selvästi**"')
    title = T.generate_slide_title("Q", [("A", 1.0)], chat=chat)
    assert title == "Attendo johtaa selvästi"


def test_slide_title_keeps_only_first_line():
    # ACTUAL _clean behavior: the quote-unwrap check runs on the whole (still
    # multi-line) string BEFORE the newline split, so a leading quote is only
    # removed when the WHOLE string is quote-wrapped. Here the second line means
    # the wrapping quotes survive onto the first line.
    chat = RecordingChat('"Ensimmäinen rivi"\nroskarivi')
    title = T.generate_slide_title("Q", [("A", 1.0)], chat=chat)
    assert title == '"Ensimmäinen rivi"'


def test_slide_title_blank_reply_falls_back_to_question_text():
    title = T.generate_slide_title("  Alkuperäinen kysymys?  ", [("A", 1.0)],
                                   chat=RecordingChat("   \n  "))
    assert title == "Alkuperäinen kysymys?"


def test_slide_title_is_not_truncated_to_max_title_len():
    # ACTUAL behavior: generate_slide_title does NOT cap the length; MAX_TITLE_LEN
    # only appears as guidance inside the prompt text. The cleaned reply is
    # returned verbatim even if longer than MAX_TITLE_LEN.
    long_reply = "Z" * (T.MAX_TITLE_LEN + 50)
    title = T.generate_slide_title("Q", [("A", 1.0)], chat=RecordingChat(long_reply))
    assert title == long_reply
    assert len(title) > T.MAX_TITLE_LEN


def test_slide_title_propagates_egohive_error():
    def boom(_prompt):
        raise EgoHiveError("down")

    with pytest.raises(EgoHiveError):
        T.generate_slide_title("Q", [("A", 1.0)], chat=RecordingChat(boom))


def test_slide_title_prompt_handles_empty_findings():
    chat = RecordingChat("otsikko")
    T.generate_slide_title("Q", [], chat=chat)
    assert "(ei kärkituloksia)" in chat.prompts[0]


# --------------------------------------------------------------------------- #
# shorten_labels
# --------------------------------------------------------------------------- #
def _ref(labels):
    return ReferenceLabels(labels=labels, titles=[])


def test_shorten_labels_reuses_reference_verbatim_zero_chat_calls():
    # "Kyllä varmasti" normalizes equal to "Kyllä, varmasti" but is strictly
    # shorter -> reused verbatim, no chat call at all.
    ref = _ref(["Kyllä varmasti"])
    chat = RecordingChat("SHOULD NOT BE CALLED")
    out = T.shorten_labels(["Kyllä, varmasti"], reference=ref, chat=chat)
    assert out == [("Kyllä, varmasti", "Kyllä varmasti")]
    assert chat.calls == 0


def test_shorten_labels_uses_numbered_reply_when_ai_needed():
    ref = _ref([])  # no reference matches -> everything goes to AI
    chat = RecordingChat("1. Lyhyt A\n2. Lyhyt B")
    out = T.shorten_labels(["Pitkä otsikko A", "Pitkä otsikko B"],
                           reference=ref, chat=chat)
    assert chat.calls == 1
    assert out == [("Pitkä otsikko A", "Lyhyt A"), ("Pitkä otsikko B", "Lyhyt B")]
    # The prompt lists the labels to shorten as a numbered list.
    assert "1. Pitkä otsikko A" in chat.prompts[0]


def test_shorten_labels_swallows_egohive_error_returns_empty():
    def boom(_prompt):
        raise EgoHiveError("unreachable")

    ref = _ref([])
    out = T.shorten_labels(["Pitkä otsikko"], reference=ref, chat=RecordingChat(boom))
    # AI unreachable -> fall back to originals -> short == full -> nothing emitted.
    assert out == []


def test_shorten_labels_only_emits_when_short_differs():
    ref = _ref([])
    # Reply echoes the label unchanged for the first, shortens the second.
    chat = RecordingChat("1. Sama\n2. Lyhennetty")
    out = T.shorten_labels(["Sama", "Alkuperäinen pitkä"], reference=ref, chat=chat)
    assert out == [("Alkuperäinen pitkä", "Lyhennetty")]


def test_shorten_labels_preserves_order():
    ref = _ref([])
    chat = RecordingChat("1. AA\n2. BB\n3. CC")
    out = T.shorten_labels(["Yksi label", "Kaksi label", "Kolme label"],
                           reference=ref, chat=chat)
    assert [full for full, _ in out] == ["Yksi label", "Kaksi label", "Kolme label"]


def test_shorten_labels_postprocesses_ai_reply():
    ref = _ref([])
    # Model ignored the no-ellipsis / length rules; _postprocess_short fixes it.
    chat = RecordingChat("1. Tosi pitkä lyhennys joka ylittää rajan…")
    out = T.shorten_labels(["Alkuperäinen X"], reference=ref, chat=chat)
    (_full, short) = out[0]
    assert "…" not in short
    assert len(short) <= T.MAX_LABEL_LEN


# --------------------------------------------------------------------------- #
# pick_demographic_questions
# --------------------------------------------------------------------------- #
def test_pick_demographics_keeps_valid_drops_hallucinated_and_dedups():
    candidates = [("q1", "Ikä"), ("q2", "Sukupuoli"), ("q3", "Tyytyväisyys")]
    chat = RecordingChat("q1, q2, q99, q1")
    picked = T.pick_demographic_questions(candidates, chat=chat)
    assert picked == ["q1", "q2"]
    # The prompt lists candidates as 'qid: label'.
    assert "q1: Ikä" in chat.prompts[0]


def test_pick_demographics_empty_reply():
    candidates = [("q1", "Ikä")]
    assert T.pick_demographic_questions(candidates, chat=RecordingChat("")) == []


# --------------------------------------------------------------------------- #
# generate_data_chat
# --------------------------------------------------------------------------- #
def test_data_chat_strips_fenced_blocks():
    reply = "Vastaus käyttäjälle.\n```question:single_select\nfoo\n```"
    out = T.generate_data_chat(
        "Tutkimus", [("Q", [("A", 1.0)])],
        [{"role": "user", "content": "Kysymys?"}],
        chat=RecordingChat(reply),
    )
    assert out == "Vastaus käyttäjälle."
    assert "```" not in out


def test_data_chat_empty_reply_returns_empty_string():
    # ACTUAL behavior: generate_data_chat has NO canned fallback; an empty reply
    # is returned as an empty string (not a Finnish fallback sentence).
    out = T.generate_data_chat(
        "Tutkimus", [("Q", [("A", 1.0)])],
        [{"role": "user", "content": "Kysymys?"}],
        chat=RecordingChat("   "),
    )
    assert out == ""


def test_data_chat_prompt_includes_study_total_n_and_convo():
    chat = RecordingChat("ok")
    T.generate_data_chat(
        "Asiakastyytyväisyys", [("Kysymys 1", [("Hyvä", 60.0)])],
        [{"role": "user", "content": "Mikä oli paras tulos?"}],
        total_n=250, chat=chat,
    )
    prompt = chat.prompts[0]
    assert 'Asiakastyytyväisyys' in prompt
    assert "Vastaajia yhteensä: 250." in prompt
    assert "Käyttäjä: Mikä oli paras tulos?" in prompt
    assert "Kysymys 1" in prompt


# --------------------------------------------------------------------------- #
# bullet generators (overview / conclusion / demographics / open themes)
# --------------------------------------------------------------------------- #
def test_generate_overview_bullets_parses_and_caps():
    reply = "\n".join(f"- Havainto {i}" for i in range(1, 10))
    out = T.generate_overview_bullets("Tutkimus", ["Q1", "Q2"], 100,
                                      chat=RecordingChat(reply))
    assert out == [f"Havainto {i}" for i in range(1, T.MAX_BULLETS + 1)]


def test_generate_conclusion_bullets_keeps_bold_markdown():
    out = T.generate_conclusion_bullets(
        "Tutkimus", [("Q", [("A", 50.0)])],
        chat=RecordingChat("- **Tärkein** johtopäätös"),
    )
    assert out == ["**Tärkein** johtopäätös"]


def test_generate_demographics_bullets():
    out = T.generate_demographics_bullets(
        "Tutkimus", [("Ikä", [("18-29", 40.0)])],
        chat=RecordingChat("- Nuoria vastaajia oli 40 %"),
    )
    assert out == ["Nuoria vastaajia oli 40 %"]


def test_generate_open_themes_caps_at_max_themes():
    reply = "\n".join(f"- **Teema {i}** – {i} %" for i in range(1, 12))
    out = T.generate_open_themes("Avoin?", [("hinta", 40)], ["hyvä hinta"],
                                 chat=RecordingChat(reply))
    assert len(out) <= T.MAX_THEMES
    assert out[0] == "**Teema 1** – 1 %"
