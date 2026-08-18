"""The house-style template.

Making the default a real .pptx means one rendering path: "no template chosen"
selects this file rather than taking a branch only the default exercises.
"""
import pathlib

from reportbuilder.render import house_style as hs
from reportbuilder.render.default_template import build_default_template
from reportbuilder.render.template_check import inspect_template


def _built(tmp_path) -> str:
    return build_default_template(str(tmp_path / "default.pptx"))


def test_the_default_satisfies_our_own_template_requirements(tmp_path):
    # If the house default could not pass the check we apply to customers, the
    # requirement would be one we do not meet ourselves.
    assert inspect_template(_built(tmp_path)).ok


def test_it_offers_a_title_and_content_layout(tmp_path):
    best = inspect_template(_built(tmp_path)).best
    assert best is not None and best.has_title and best.content_count >= 1


def test_the_chart_palette_is_the_house_palette(tmp_path):
    theme = inspect_template(_built(tmp_path)).theme
    # Teal leads: a single-series chart is the common case and teal is the
    # house colour.
    assert theme.palette[0] == hs.TEAL.lstrip("#").upper()
    assert theme.palette[2] == hs.BLUE.lstrip("#").upper()
    assert len(theme.palette) == 6


def test_the_font_is_one_the_render_host_actually_has(tmp_path):
    # Naming a font is not having it: a missing font is substituted silently by
    # both matplotlib and LibreOffice, shifting label metrics.
    theme = inspect_template(_built(tmp_path)).theme
    assert theme.heading_font == "Liberation Sans"


def test_it_is_widescreen(tmp_path):
    report = inspect_template(_built(tmp_path))
    assert (report.slide_width_in, report.slide_height_in) == (13.33, 7.5)
