"""What a bullet's markdown means, and what it leaves alone.

Bullets are written by a model and edited by a person, and both write ordinary
Finnish prose that happens to contain underscores — a variable name, a file, an
index. `_emphasis_` treated every underscore as a marker, so
"asiakas_tyytyvaisyys_indeksi" lost both of them and came out with a word in
italics: the text on the slide was not the text the author wrote.
"""
from __future__ import annotations

from reportbuilder.render.image.special_slide import _md_runs


def _plain(text: str) -> str:
    return "".join(seg for seg, _b, _i in _md_runs(text))


def test_an_underscore_inside_a_word_is_just_an_underscore():
    text = "kentässä asiakas_tyytyvaisyys_indeksi nousi"
    assert _plain(text) == text
    assert not any(italic for _seg, _bold, italic in _md_runs(text))


def test_bold_still_works():
    runs = _md_runs("**Vahva** kosketuspinta")
    assert runs[0] == ("Vahva", True, False)


def test_italics_around_whole_words_still_work():
    assert ("sanoo", False, True) in _md_runs("hän _sanoo_ näin")


def test_asterisk_italics_still_work():
    assert ("sanoo", False, True) in _md_runs("hän *sanoo* näin")


def test_a_lone_underscore_is_left_alone():
    assert _plain("a _ b") == "a _ b"
