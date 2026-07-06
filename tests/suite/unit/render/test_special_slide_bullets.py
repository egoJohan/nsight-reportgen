"""Markdown bullet parsing for special slides — leading marker + indent → nesting."""
from reportbuilder.render.image.special_slide import _bullet_level


def test_marker_stripped_at_top_level():
    assert _bullet_level("* Top") == (0, "Top")
    assert _bullet_level("- Dash") == (0, "Dash")
    assert _bullet_level("+ Plus") == (0, "Plus")


def test_indentation_sets_nesting_level():
    assert _bullet_level("  * Once") == (1, "Once")
    assert _bullet_level("    * Twice") == (2, "Twice")
    assert _bullet_level("\t* Tab") == (1, "Tab")


def test_plain_line_is_level_zero_bullet():
    assert _bullet_level("Plain text") == (0, "Plain text")


def test_nesting_depth_is_capped():
    assert _bullet_level(" " * 20 + "* Deep")[0] == 3
