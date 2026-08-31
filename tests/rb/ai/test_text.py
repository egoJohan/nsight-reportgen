"""Unit tests for the AI text services with a FAKE chat (no network) (C.2)."""
from __future__ import annotations

from reportbuilder.ai.reference import ReferenceLabels
from reportbuilder.ai.text import (
    TITLE_END_MARK,
    MAX_LABEL_LEN,
    generate_slide_title,
    shorten_labels,
)
from nsight.agent.egohive_client import EgoHiveError


class _RecordingChat:
    """Fake chat that records the prompt and returns a canned reply."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompt: str | None = None
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        self.prompt = prompt
        self.calls += 1
        return self.reply


# --------------------------------------------------------------------------- #
# generate_slide_title
# --------------------------------------------------------------------------- #
def test_slide_title_prompt_is_finnish_with_findings_and_constraints() -> None:
    # The reply carries the end mark: the prompt asks for it, and a reply
    # without one is treated as cut short and discarded in favour of the
    # question text. A fake that omits it is not standing in for the model.
    chat = _RecordingChat(f"Attendo johtaa tunnettuudessa{TITLE_END_MARK}")
    title = generate_slide_title(
        "Mitä brändejä tunnet?",
        [("Attendo", 86.0), ("Esperi", 75.0)],
        chat=chat,
    )
    assert title == "Attendo johtaa tunnettuudessa"
    # Finnish analytical key-message ("avainviesti") prompt mentioning the
    # question, the findings, and the don't-just-restate constraint.
    assert "avainviesti" in chat.prompt
    assert "Mitä brändejä tunnet?" in chat.prompt
    assert "Attendo" in chat.prompt and "86" in chat.prompt
    assert "toistaa kysymystä" in chat.prompt


def test_slide_title_strips_quotes_and_markdown() -> None:
    chat = _RecordingChat(f'"**Attendo on tunnetuin**"{TITLE_END_MARK}')
    title = generate_slide_title("Q", [("Attendo", 50.0)], chat=chat)
    assert title == "Attendo on tunnetuin"


def test_slide_title_empty_reply_falls_back_to_question() -> None:
    chat = _RecordingChat("   ")
    title = generate_slide_title("Alkuperäinen kysymys", [], chat=chat)
    assert title == "Alkuperäinen kysymys"


def test_slide_title_propagates_egohive_error() -> None:
    def boom(_prompt: str) -> str:
        raise EgoHiveError("unreachable")

    try:
        generate_slide_title("Q", [("A", 1.0)], chat=boom)
    except EgoHiveError:
        pass
    else:
        raise AssertionError("EgoHiveError should propagate from generate_slide_title")


# --------------------------------------------------------------------------- #
# shorten_labels
# --------------------------------------------------------------------------- #
def _empty_ref() -> ReferenceLabels:
    return ReferenceLabels(labels=[], titles=[])


def test_shorten_labels_uses_reference_verbatim_without_ai() -> None:
    ref = ReferenceLabels(labels=["Erittäin tyytyväinen"], titles=[])
    chat = _RecordingChat("1. should-not-be-used")
    out = shorten_labels(["Erittäin tyytyväinen!!"], reference=ref, chat=chat)
    assert out == [("Erittäin tyytyväinen!!", "Erittäin tyytyväinen")]
    assert chat.calls == 0  # reference hit -> no AI call


def test_shorten_labels_ai_batches_and_parses_numbered_reply() -> None:
    chat = _RecordingChat("1. Tyytyväiset\n2. Tyytymättömät")
    out = shorten_labels(
        [
            "Erittäin tai melko tyytyväiset vastaajat",
            "Erittäin tai melko tyytymättömät vastaajat",
        ],
        reference=_empty_ref(),
        chat=chat,
    )
    assert out == [
        ("Erittäin tai melko tyytyväiset vastaajat", "Tyytyväiset"),
        ("Erittäin tai melko tyytymättömät vastaajat", "Tyytymättömät"),
    ]
    assert chat.calls == 1  # single batched call
    # Prompt carries the constraints.
    assert str(MAX_LABEL_LEN) in chat.prompt
    assert "ellipsiä" in chat.prompt or "kolmea pistettä" in chat.prompt


def test_shorten_labels_enforces_max_len_and_no_ellipsis() -> None:
    long_reply = "1. Tämä on aivan liian pitkä lyhennys joka ylittää rajan…"
    chat = _RecordingChat(long_reply)
    out = shorten_labels(["Jokin pitkä alkuperäinen otsikko vastaajille"], reference=_empty_ref(), chat=chat)
    assert len(out) == 1
    _full, short = out[0]
    assert len(short) <= MAX_LABEL_LEN
    assert "…" not in short and "..." not in short


def test_shorten_labels_malformed_reply_falls_back_to_original() -> None:
    # Two labels but the reply is not a parseable numbered list -> fall back.
    chat = _RecordingChat("Pahoittelut, en pysty auttamaan tässä.")
    out = shorten_labels(
        ["Ensimmäinen otsikko", "Toinen otsikko"],
        reference=_empty_ref(),
        chat=chat,
    )
    # No override produced (short == full omitted).
    assert out == []


def test_shorten_labels_ai_unreachable_falls_back_never_crashes() -> None:
    def boom(_prompt: str) -> str:
        raise EgoHiveError("down")

    out = shorten_labels(["Jokin otsikko"], reference=_empty_ref(), chat=boom)
    assert out == []  # fell back to original, no crash


def test_shorten_labels_omits_noop_and_preserves_order() -> None:
    # AI returns a label identical to the original for #2 -> omitted; order kept.
    chat = _RecordingChat("1. Lyhyt A\n2. Pitkä alkuperäinen B")
    out = shorten_labels(
        ["Pitkä alkuperäinen A", "Pitkä alkuperäinen B"],
        reference=_empty_ref(),
        chat=chat,
    )
    assert out == [("Pitkä alkuperäinen A", "Lyhyt A")]


def test_slide_title_strips_quotes_that_sit_before_the_end_mark() -> None:
    """A reply the model wrapped in quotes must not keep half the pair.

    The end mark terminates the answer, so the closing quote is not the last
    character — `"Otsikko"¶`. Cleaning before cutting at the mark could only
    find the opening quote, and the slide showed `"Otsikko`.
    """
    chat = _RecordingChat(f'"**Attendo on tunnetuin**"{TITLE_END_MARK}')
    assert generate_slide_title("Q", [("Attendo", 50.0)], chat=chat) == \
        "Attendo on tunnetuin"


def test_slide_title_discards_words_written_after_the_end_mark() -> None:
    """Only closing punctuation is carried back over the mark, never prose."""
    chat = _RecordingChat(f"Attendo johtaa{TITLE_END_MARK} ja tässä lisää selitystä")
    assert generate_slide_title("Q", [("A", 1.0)], chat=chat) == "Attendo johtaa"


def test_slide_title_handles_the_mark_inside_the_wrapper() -> None:
    """`"**Otsikko ¶**"` — the closing `**"` sits after the mark, so cutting
    there would strand the opening half."""
    chat = _RecordingChat(f'"**Attendo johtaa selvästi {TITLE_END_MARK}**"')
    assert generate_slide_title("Q", [("A", 1.0)], chat=chat) == "Attendo johtaa selvästi"
