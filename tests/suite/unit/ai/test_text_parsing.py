"""Unit tests for the pure parsing/formatting helpers in
``reportbuilder.ai.text``: ``_parse_numbered``, ``_parse_bullets``,
``_postprocess_short``, ``_findings_block``, ``_study_line``."""
from __future__ import annotations

from reportbuilder.ai import text as T


# --------------------------------------------------------------------------- #
# _parse_numbered
# --------------------------------------------------------------------------- #
def test_parse_numbered_basic_mapping():
    assert T._parse_numbered("1. Foo\n2. Bar", ["alpha", "beta"]) == {
        "alpha": "Foo", "beta": "Bar",
    }


def test_parse_numbered_robust_to_leading_bullets_and_parens():
    reply = "  (1) Eka\n  2) Toka\n3: Kolmas"
    assert T._parse_numbered(reply, ["a", "b", "c"]) == {
        "a": "Eka", "b": "Toka", "c": "Kolmas",
    }


def test_parse_numbered_out_of_range_index_ignored():
    # Index 5 has no label -> dropped; only in-range mappings survive.
    assert T._parse_numbered("1. Yksi\n5. Viisi", ["a", "b"]) == {"a": "Yksi"}


def test_parse_numbered_plain_lines_require_exact_count():
    # No numbering + matching count -> 1:1 mapping.
    assert T._parse_numbered("Yksi\nKaksi", ["a", "b"]) == {"a": "Yksi", "b": "Kaksi"}


def test_parse_numbered_plain_mismatch_returns_empty():
    # No numbering and count mismatch -> unmappable -> {}.
    assert T._parse_numbered("Yksi\nKaksi\nKolme", ["a", "b"]) == {}


def test_parse_numbered_empty_reply_returns_empty():
    assert T._parse_numbered("", ["a"]) == {}


# --------------------------------------------------------------------------- #
# _parse_bullets
# --------------------------------------------------------------------------- #
def test_parse_bullets_strips_various_markers():
    reply = "1. Numeroitu\n- Viiva\n• Pallo\n* Tähti"
    assert T._parse_bullets(reply) == ["Numeroitu", "Viiva", "Pallo", "Tähti"]


def test_parse_bullets_drops_code_fences_and_marker_only_lines():
    reply = "```json\n- Oikea havainto\n---\n```"
    assert T._parse_bullets(reply) == ["Oikea havainto"]


def test_parse_bullets_preserves_leading_bold_markdown():
    # "*bold*" style: a "**word**" bullet must NOT be mangled; the "* " marker
    # rule requires a space after "*".
    assert T._parse_bullets("- **Avainsana** loppuosa") == ["**Avainsana** loppuosa"]


def test_parse_bullets_strips_wrapping_quotes():
    assert T._parse_bullets('- "Lainattu havainto"') == ["Lainattu havainto"]


def test_parse_bullets_caps_at_max_bullets():
    reply = "\n".join(f"- rivi {i}" for i in range(20))
    assert len(T._parse_bullets(reply)) == T.MAX_BULLETS


def test_parse_bullets_empty_reply():
    assert T._parse_bullets("") == []


# --------------------------------------------------------------------------- #
# _postprocess_short
# --------------------------------------------------------------------------- #
def test_postprocess_short_removes_ellipsis_and_trailing_seps():
    assert T._postprocess_short("Lyhyt otsikko…", "full") == "Lyhyt otsikko"
    assert T._postprocess_short("Lyhyt otsikko ...", "full") == "Lyhyt otsikko"


def test_postprocess_short_enforces_max_label_len():
    s = T._postprocess_short("A" * 100, "full")
    assert len(s) <= T.MAX_LABEL_LEN


def test_postprocess_short_falls_back_to_full_when_empty():
    assert T._postprocess_short("…", "Alkuperäinen") == "Alkuperäinen"
    assert T._postprocess_short("   ", "Alkuperäinen") == "Alkuperäinen"


def test_postprocess_short_strips_markdown_and_quotes():
    assert T._postprocess_short('"**Lyhyt**"', "full") == "Lyhyt"


# --------------------------------------------------------------------------- #
# _findings_block / _study_line
# --------------------------------------------------------------------------- #
def test_findings_block_formats_int_and_float_values():
    block = T._findings_block([("Kysymys A", [("Kyllä", 60.0), ("Ehkä", 12.5)])])
    assert "- Kysymys A" in block
    assert "    - Kyllä: 60" in block
    assert "    - Ehkä: 12.5" in block


def test_findings_block_skips_questions_without_findings():
    block = T._findings_block([("Tyhjä", [])])
    assert block == "- (ei tuloksia)"


def test_study_line_present_and_absent():
    assert T._study_line("Asiakastutkimus") == 'Tutkimus: "Asiakastutkimus".\n'
    assert T._study_line("Nimi", prefix="Tutkimuksen nimi") == \
        'Tutkimuksen nimi: "Nimi".\n'
    assert T._study_line("") == ""
    assert T._study_line("   ") == ""
