"""The content area is what the template settings say. Nothing moves for anything.

Johan, 2026-09-18: "Content stays as it is specified in the template settings.
Subtitle and footer position themself to this, nothing moves. Subtitle anchors
its bottom to content top. Chart renders to content area."

Two earlier attempts got this wrong in opposite directions and both are gone:

  * `lowered_for_header` pushed the CHART down when the header was tall.
  * `content_box` put the question at the content's top-left and started the
    chart below it, so a longer question shrank the chart.

Neither is what the layout is. The rectangle the settings screen draws — one
definition, `style_spec.effective_content_rect`, which a drag amends — IS the
chart. The question hangs above its top edge and the footer below its bottom
edge; the rectangle itself is never consulted about their length.

The defect this all started from ("Kysymysteksti näkyy nyt graafien päällä")
cannot recur here for a structural reason: the question's bottom is pinned to
the content's TOP and it grows AWAY from the chart, so no question length can
put a word of it inside the chart.
"""
from __future__ import annotations

import pathlib

import pytest
from pptx.util import Inches

from reportbuilder.render.deck import _resolve_slot
from reportbuilder.render.style_spec import effective_content_rect, load_style_spec

_TEMPLATES = {
    "attendo": "input/Attendo Bränditutkimus Marraskuu 2025.pptx",
    "synsam": "input/Synsam_Segmentointitutkimus_30.4.2025_nSight.pptx",
    "holidayclub": "input/Holiday Club_Loyalty tutkimus_raportti_19.2.2026.pptx",
}


@pytest.mark.parametrize("name", sorted(_TEMPLATES))
def test_the_chart_is_drawn_in_the_rectangle_the_settings_publish(name):
    """The renderer and the template-settings screen must name the same box.

    They did not: on the Alflorex template the settings said 1.78in and
    `_resolve_slot` drew at a hard-coded 1.90in, inside a title band ending at
    2.13in. Two answers to one question is the whole defect.
    """
    from pptx import Presentation

    path = pathlib.Path(_TEMPLATES[name])
    if not path.exists():
        pytest.skip(f"{path} not available locally")
    style = load_style_spec(str(path))
    want = effective_content_rect(style)
    prs = Presentation(str(path))
    slot = _resolve_slot(prs, style, "s1", "image", title="Otsikko")
    assert (slot.left, slot.top, slot.width, slot.height) == want


@pytest.mark.parametrize("name", sorted(_TEMPLATES))
def test_the_rectangle_does_not_depend_on_the_headline(name):
    """A longer headline must not move the content: the header is not consulted."""
    from pptx import Presentation

    path = pathlib.Path(_TEMPLATES[name])
    if not path.exists():
        pytest.skip(f"{path} not available locally")
    style = load_style_spec(str(path))
    short = _resolve_slot(Presentation(str(path)), style, "s1", "image", title="Lyhyt")
    long_ = _resolve_slot(
        Presentation(str(path)), style, "s1", "image",
        title="Huomattavasti pidempi otsikko joka kietoutuu usealle riville "
              "ja vie selvästi enemmän tilaa kuin lyhyt otsikko koskaan veisi")
    assert (short.top, short.height) == (long_.top, long_.height)


# ── the question lines up with the headline, horizontally ───────────────────
#
# Johan, 2026-09-18: "Let's align the subtitle x always with title x."
#
# Vertically the question belongs to the CONTENT (its bottom pinned to the
# content's top edge); horizontally it belongs to the TITLE. The content
# rectangle is a separate thing an author can drag anywhere, and a question
# indented differently from the headline directly above it reads as a mistake.
#
# Compared where the TEXT starts, not where the boxes are: a title placeholder
# keeps its own insets while `_textbox` zeroes every margin, so equal box edges
# would put the question ~0.1in left of the headline.

def _text_x(shape) -> int:
    return int(shape.left or 0) + int(shape.text_frame.margin_left or 0)


@pytest.mark.parametrize("name", sorted(_TEMPLATES))
def test_the_question_starts_where_the_title_starts(name):
    import dataclasses

    from reportbuilder.model.report import ChartSpec
    from reportbuilder.export.pptx_build import build_presentation
    from reportbuilder.testing.fixtures import one_chart_report, known_series
    from reportbuilder.model.question import Question, QuestionModel
    import pandas as pd

    path = pathlib.Path(_TEMPLATES[name])
    if not path.exists():
        pytest.skip(f"{path} not available locally")
    style = load_style_spec(str(path))
    report = dataclasses.replace(one_chart_report(), render_mode="image")
    charts = tuple(dataclasses.replace(c, slide_title="Otsikko joka kertoo tuloksen")
                   for c in report.charts)
    report = dataclasses.replace(report, charts=charts)
    from reportbuilder.render.deck import render_report

    prs = render_report(report, {"q1": known_series()}, style,
                        titles={"q1": "Mikä seuraavista vastaa työtilannettasi juuri nyt?"})
    texts = [s for s in prs.slides[0].shapes
             if s.has_text_frame and s.text_frame.text.strip()]
    assert len(texts) >= 2, "expected a title and a question on the slide"
    title_x, question_x = _text_x(texts[0]), _text_x(texts[1])
    assert abs(title_x - question_x) < int(Inches(0.01)), (
        f"question text starts {abs(title_x - question_x) / 914400:.3f}in "
        f"from the title's")
