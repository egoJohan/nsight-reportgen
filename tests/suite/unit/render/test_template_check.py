"""Validating a customer's own PowerPoint template.

nSight's analysts work in their CLIENTS' brand templates, which nobody will
re-author to suit us. So these tests use the three real client decks in input/
rather than a synthetic fixture — a heuristic that only works on a template we
made ourselves is worthless.
"""
import pathlib

import pytest

from reportbuilder.render.template_check import inspect_template

_TEMPLATES = {
    "attendo": "input/Attendo Bränditutkimus Marraskuu 2025.pptx",
    "synsam": "input/Synsam_Segmentointitutkimus_30.4.2025_nSight.pptx",
    "holidayclub": "input/Holiday Club_Loyalty tutkimus_raportti_19.2.2026.pptx",
}


def _template(name):
    p = pathlib.Path(_TEMPLATES[name])
    if not p.exists():
        pytest.skip(f"{p} not available locally")
    return str(p)


@pytest.mark.parametrize("name", sorted(_TEMPLATES))
def test_a_real_client_template_passes_unmodified(name):
    """The requirement has to be satisfiable by a deck nobody edited for us."""
    assert inspect_template(_template(name)).ok


@pytest.mark.parametrize("name,expected", [
    ("attendo", "1 layout area"),
    ("holidayclub", "Title and Content"),
])
def test_the_chart_layout_is_identified_across_languages(name, expected):
    """Layout NAMES cannot be the interface — the same layout is "1 layout area",
    "Innehåll" and "Title and Content" in three real templates. Ranking is by
    the size of the content placeholder instead."""
    assert inspect_template(_template(name)).best.name == expected


def test_a_divider_does_not_outrank_a_content_layout():
    """Counting placeholders picked Holiday Club's "Section Header" — a divider
    whose caption box counts the same as a full-slide content area. Area is the
    signal, so the divider must now lose."""
    report = inspect_template(_template("holidayclub"))
    best = report.best
    section = next(c for c in report.candidates if c.name == "Section Header")
    assert best.score > section.score
    assert best.content_area_pct > section.content_area_pct


class TestTheme:
    def test_the_clients_brand_palette_is_read(self):
        theme = inspect_template(_template("attendo")).theme
        # accent1-6 is what PowerPoint's own charts use for series colours.
        assert theme.palette[:3] == ["122D49", "7EA96C", "3D7098"]

    def test_the_clients_fonts_are_read(self):
        theme = inspect_template(_template("attendo")).theme
        assert (theme.heading_font, theme.body_font) == ("Century Gothic", "Calibri")

    @pytest.mark.parametrize("name", sorted(_TEMPLATES))
    def test_every_real_template_yields_a_full_palette(self, name):
        assert len(inspect_template(_template(name)).theme.palette) == 6


class TestBadInput:
    def test_a_file_that_is_not_a_pptx_is_reported_not_raised(self, tmp_path):
        bad = tmp_path / "notes.txt"
        bad.write_bytes(b"this is not a presentation")
        report = inspect_template(str(bad))
        assert not report.ok
        assert "readable PowerPoint" in report.problems[0]

    def test_a_missing_file_is_reported_not_raised(self):
        assert not inspect_template("/nonexistent/x.pptx").ok
