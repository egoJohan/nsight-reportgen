"""A label SPSS cut in half does not end in a character nobody can draw.

An SPSS variable label is capped at 256 BYTES. A long Finnish battery statement
runs past it and the file stores the label truncated at that byte — in the
middle of a multi-byte character. Decoding the orphaned byte yields U+FFFD, the
replacement character, and the renderer draws it: the Synsam study's slide
headline ends "…ja 7= erittäin t◆", a black diamond on a client's slide.
matplotlib says so too, once per render ("Glyph 65533 missing from font").

The half character carries no information — it is the tail of a letter the file
does not contain — so it is dropped on the way in. Only at the END, where a
truncation boundary is: a replacement character in the MIDDLE means something
else went wrong with the encoding, and hiding that would be worse than drawing
it.
"""
from __future__ import annotations

import pytest

from reportbuilder.ingest.sav_reader import _clean_label

TAIL = "Vastaa asteikolla 1-7, jossa 1=ei lainkaan tärkeää ja 7= erittäin t"


def test_a_trailing_replacement_character_is_dropped():
    assert _clean_label(TAIL + "�") == TAIL


def test_trailing_whitespace_around_it_goes_too():
    assert _clean_label(TAIL + "�  ") == TAIL


def test_several_trailing_replacements_all_go():
    assert _clean_label(TAIL + "��") == TAIL


def test_a_clean_label_is_untouched():
    assert _clean_label(TAIL) == TAIL


def test_an_interior_replacement_is_left_alone():
    """Mid-label mojibake is a different fault and must stay visible."""
    broken = "Kehysvalikoiman�yksilöllisyys"
    assert _clean_label(broken) == broken


@pytest.mark.parametrize("value", ["", None])
def test_nothing_is_still_nothing(value):
    assert _clean_label(value) == ""
