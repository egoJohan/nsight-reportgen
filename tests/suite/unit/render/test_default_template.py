"""The house-style template.

Making the default a real .pptx means one rendering path: "no template chosen"
selects this file rather than taking a branch only the default exercises.
"""
import pathlib

import pytest

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


def test_the_font_matches_the_customer_templates(tmp_path):
    """Calibri — the face Attendo's own deck declares.

    A slide with no template chosen sits beside slides that do have one, and
    the default looking like them is one less thing to notice. Calibri is also
    on every Windows and Mac the deck is opened on.
    """
    theme = inspect_template(_built(tmp_path)).theme
    assert theme.heading_font == "Calibri"
    assert theme.body_font == "Calibri"


def test_the_render_host_can_draw_that_font_at_the_right_width(tmp_path):
    """Naming a font is not having it, and the substitute's METRICS are what
    decide whether a title fits the box nSight measured it against.

    Calibri and Carlito are drawn from the same metrics; anything else (Noto,
    DejaVu) is a different width, so every label reflows between what this
    host measures and what PowerPoint finally draws. This is a host
    provisioning fact, not a code defect — hence a skip that says how to fix
    it rather than a failure.
    """
    import shutil
    import subprocess

    if shutil.which("fc-match") is None:
        pytest.skip("fontconfig not available")
    resolved = subprocess.run(["fc-match", "-f", "%{family}", "Calibri"],
                              capture_output=True, text=True, check=True).stdout
    if not any(name in resolved for name in ("Calibri", "Carlito")):
        pytest.skip(
            f"Calibri resolves to {resolved!r} on this host, whose metrics differ. "
            "Install Calibri (Settings > Fonts) or metric-compatible Carlito "
            "(apt install fonts-crosextra-carlito) so measured and drawn text agree.")
    assert any(name in resolved for name in ("Calibri", "Carlito"))


def test_the_default_is_plain(tmp_path):
    """No template chosen means no branding — not nSight's, and not a client's.

    A deck in this state is a draft or is headed for a customer whose template
    is not set up yet, so the slide carries a white ground and nothing else. It
    used to arrive in nSight's cream with a teal bar beside every title.
    """
    from pptx import Presentation

    from reportbuilder.render import house_style as hs

    theme = inspect_template(_built(tmp_path)).theme
    assert theme.background == "FFFFFF"

    prs = Presentation(_built(tmp_path))
    teal = hs.TEAL.lstrip("#").upper()
    for layout in prs.slide_layouts:
        for shape in layout.shapes:
            if shape.is_placeholder:
                continue
            try:
                fill = shape.fill
                colour = str(fill.fore_color.rgb) if fill.type == 1 else ""
            except (AttributeError, TypeError, ValueError):
                continue
            assert colour != teal, f"{layout.name} still carries the house bar"


def test_the_chart_series_keep_their_colours(tmp_path):
    """Plain is about DECORATION. Series colours have a job — telling one series
    from another — and a set of greys would make a chart harder to read."""
    theme = inspect_template(_built(tmp_path)).theme
    assert theme.palette[0] == hs.TEAL.lstrip("#").upper()


def test_it_is_widescreen(tmp_path):
    report = inspect_template(_built(tmp_path))
    assert (report.slide_width_in, report.slide_height_in) == (13.33, 7.5)
