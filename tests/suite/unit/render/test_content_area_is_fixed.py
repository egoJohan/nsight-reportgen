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


# ── the question stands IN the content's corner, and the chart below it ─────
#
# Johan, 2026-09-21: "The default layout positioning of the subtitle should be
# such that it positions to the top left corner of the content in the
# template's layout. The content's top is then adjusted to the bottom of the
# subtitle" … "the bottom y shall not change".
#
# By GEOMETRY, never by the text: "we do not need to wait for any question
# rendering, we just position the y to the subtitle bottom". The layout editor
# draws this box and cannot know what one slide's question will say.

def _slide_parts(style):
    import dataclasses

    from reportbuilder.render.deck import render_report
    from reportbuilder.testing.fixtures import known_series, one_chart_report

    report = dataclasses.replace(one_chart_report(), render_mode="image")
    report = dataclasses.replace(report, charts=tuple(
        dataclasses.replace(c, slide_title="Otsikko joka kertoo tuloksen")
        for c in report.charts))
    prs = render_report(report, {"q1": known_series()}, style,
                        titles={"q1": "Mikä seuraavista vastaa työtilannettasi?"})
    slide = prs.slides[0]
    texts = [s for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()]
    pictures = [s for s in slide.shapes
                if not s.has_text_frame and int(s.height or 0) > int(Inches(1.0))]
    assert len(texts) >= 2, "expected a title and a question on the slide"
    assert pictures, "expected the chart picture on the slide"
    return texts[1], max(pictures, key=lambda p: int(p.height))


@pytest.mark.parametrize("name", sorted(_TEMPLATES))
def test_the_question_stands_in_the_contents_top_left_corner(name):
    """One line of it, in the corner — and its BOTTOM is the edge that counts:
    the text is bottom-anchored there and a longer question grows up into the
    band under the headline, never down into the chart. (Johan, 2026-09-21)"""
    path = pathlib.Path(_TEMPLATES[name])
    if not path.exists():
        pytest.skip(f"{path} not available locally")
    style = load_style_spec(str(path))
    content = effective_content_rect(style)
    question, _chart = _slide_parts(style)
    bottom = int(question.top) + int(question.height)
    assert content[1] < bottom <= content[1] + int(Inches(0.6)), (
        f"{name}: the question ends {(bottom - content[1]) / 914400:.2f}in "
        f"below the content's top")
    assert int(question.top) <= content[1] + int(Inches(0.01)), (
        f"{name}: the question starts below the content's top")


@pytest.mark.parametrize("name", sorted(_TEMPLATES))
def test_the_chart_starts_at_the_questions_bottom_and_keeps_its_foot(name):
    path = pathlib.Path(_TEMPLATES[name])
    if not path.exists():
        pytest.skip(f"{path} not available locally")
    style = load_style_spec(str(path))
    content = effective_content_rect(style)
    question, chart = _slide_parts(style)
    q_bottom = int(question.top) + int(question.height)
    assert abs(int(chart.top) - q_bottom) < int(Inches(0.02)), (
        f"{name}: the chart starts {(int(chart.top) - q_bottom) / 914400:+.2f}in "
        f"from the question's bottom")
    # The picture is fitted inside the area, so it need not reach the foot —
    # but it may never pass it: the content gives up the strip at its top and
    # nothing at its bottom. (Johan, 2026-09-21: "the bottom y shall not change")
    foot = content[1] + content[3]
    assert int(chart.top) + int(chart.height) <= foot + int(Inches(0.02)), (
        f"{name}: the chart reaches "
        f"{(int(chart.top) + int(chart.height) - foot) / 914400:+.2f}in past the foot")


def test_the_question_box_does_not_depend_on_what_it_says(tmp_path):
    """Two slides of the same deck, one question short and one long: the chart
    starts in the same place on both."""
    import dataclasses

    from reportbuilder.render.deck import render_report
    from reportbuilder.testing.fixtures import known_series, one_chart_report

    path = pathlib.Path(_TEMPLATES["attendo"])
    if not path.exists():
        pytest.skip(f"{path} not available locally")
    style = load_style_spec(str(path))

    def chart_top(question: str) -> int:
        report = dataclasses.replace(one_chart_report(), render_mode="image")
        report = dataclasses.replace(report, charts=tuple(
            dataclasses.replace(c, slide_title="Otsikko") for c in report.charts))
        prs = render_report(report, {"q1": known_series()}, style,
                            titles={"q1": question})
        pics = [s for s in prs.slides[0].shapes
                if not s.has_text_frame and int(s.height or 0) > int(Inches(1.0))]
        return int(max(pics, key=lambda p: int(p.height)).top)

    short = chart_top("Ikä")
    long = chart_top("Mikä seuraavista vaihtoehdoista kuvaa parhaiten sitä, miten "
                     "arvioit palvelun kokonaisuutena onnistuneen viime vuoden aikana "
                     "ja miten todennäköisesti suosittelisit sitä tuttavallesi?")
    assert short == long, (
        f"the chart moved {(long - short) / 914400:+.2f}in with the question's length")


@pytest.mark.parametrize("name", sorted(_TEMPLATES))
def test_moving_the_chart_does_not_move_the_question(name):
    """SUB is a box of its own. The layout editor leaves it where it is while
    an author drags the content, so the slide must too — the question used to
    follow the chart to its new place, which is not where the editor drew it.
    (Johan, 2026-09-21)"""
    import dataclasses

    from reportbuilder.render.deck import render_report
    from reportbuilder.render.style_spec import apply_template_overrides
    from reportbuilder.testing.fixtures import known_series, one_chart_report

    path = pathlib.Path(_TEMPLATES[name])
    if not path.exists():
        pytest.skip(f"{path} not available locally")

    def question_box(overrides):
        style = load_style_spec(str(path))
        if overrides:
            apply_template_overrides(style, overrides)
        report = dataclasses.replace(one_chart_report(), render_mode="image")
        report = dataclasses.replace(report, charts=tuple(
            dataclasses.replace(c, slide_title="Otsikko joka kertoo tuloksen")
            for c in report.charts))
        prs = render_report(report, {"q1": known_series()}, style,
                            titles={"q1": "Mikä seuraavista vastaa työtilannettasi?"})
        texts = [s for s in prs.slides[0].shapes
                 if s.has_text_frame and s.text_frame.text.strip()]
        assert len(texts) >= 2, "expected a title and a question on the slide"
        return int(texts[1].top) + int(texts[1].height)

    before = question_box({})
    # the chart dragged an inch down the slide, SUB untouched
    left, top, width, height = effective_content_rect(load_style_spec(str(path)))
    moved = question_box({"content": {"x": left / 914400, "y": top / 914400 + 1.0,
                                      "w": width / 914400, "h": height / 914400 - 1.0}})
    assert moved == before, (
        f"{name}: the question moved {(moved - before) / 914400:+.2f}in with the chart")


def test_a_long_question_grows_upward_and_the_chart_stays():
    """Three lines climb into the empty band under the headline. The box's
    bottom — and so the chart's top — does not move. (Johan, 2026-09-21: "It
    needs to grow towards top, not bottom, when having more lines.")"""
    import dataclasses

    from reportbuilder.render.deck import render_report
    from reportbuilder.testing.fixtures import known_series, one_chart_report

    path = pathlib.Path(_TEMPLATES["attendo"])
    if not path.exists():
        pytest.skip(f"{path} not available locally")
    style = load_style_spec(str(path))

    def parts(question: str):
        report = dataclasses.replace(one_chart_report(), render_mode="image")
        report = dataclasses.replace(report, charts=tuple(
            dataclasses.replace(c, slide_title="Otsikko joka kertoo tuloksen")
            for c in report.charts))
        prs = render_report(report, {"q1": known_series()}, style, titles={"q1": question})
        shapes = prs.slides[0].shapes
        texts = [s for s in shapes if s.has_text_frame and s.text_frame.text.strip()]
        pics = [s for s in shapes if not s.has_text_frame and int(s.height or 0) > int(Inches(1.0))]
        return texts[1], max(pics, key=lambda p: int(p.height))

    short_q, short_chart = parts("Ikä")
    long_q, long_chart = parts(
        "Mikä seuraavista vaihtoehdoista kuvaa parhaiten sitä, miten arvioit palvelun "
        "kokonaisuutena onnistuneen viime vuoden aikana, miten todennäköisesti "
        "suosittelisit sitä tuttavallesi, ja kuinka tyytyväinen olet ollut "
        "asiakaspalveluun sekä hintatasoon kokonaisuutena arvioiden?")

    assert int(long_q.top) < int(short_q.top), "the long question did not grow upward"
    assert (int(long_q.top) + int(long_q.height)
            == int(short_q.top) + int(short_q.height)), "its bottom moved"
    assert int(long_chart.top) == int(short_chart.top), "the chart moved"
