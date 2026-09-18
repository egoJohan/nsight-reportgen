"""The content box: the question anchors its TOP-LEFT, the footer its BOTTOM-RIGHT.

Johan, 2026-09-18: "subtitle anchors to the content's top left corner, footer
(N=xxx) anchors to the bottom right corner. Naturally with correct margin
(subtitle's bottom is used for anchoring, footer's top is used for anchoring)."

This is a RESTORATION. Until 649c6bd (2026-08-23) the templated question was
TOP-anchored below the header and grew downward. That commit pinned it to the
chart's top edge instead, bottom-anchored, growing UPWARD — to keep the
question-to-chart gap identical on every slide. Growing upward needs room, and
on a template whose header is tall there is none: the arithmetic fell to
`sub_h = max(Inches(0.20), <negative>)` and planted the question inside the
bars. ("Kysymysteksti näkyy nyt graafien päällä")

Anchored at the top and growing DOWN, that failure has nowhere to occur: the
question cannot climb into the title, and the chart simply starts beneath it.

The chart is then bounded by both: subtitle bottom + margin above, footer top -
margin below.
"""
from __future__ import annotations

from pptx.util import Inches

from reportbuilder.render.image.slide_chrome import content_box


class _Box:
    """A resolved content area, as `_resolve_slot` hands one over."""
    def __init__(self, top=1.9, height=3.4, left=0.62, width=8.8):
        self.top, self.height = int(Inches(top)), int(Inches(height))
        self.left, self.width = int(Inches(left)), int(Inches(width))


def test_the_question_sits_at_the_top_of_the_content():
    box = _Box()
    r = content_box(box, question_height=int(Inches(0.40)),
                    footer_top=int(Inches(6.9)))
    assert r.question_top == box.top
    assert r.question_left == box.left


def test_the_chart_starts_below_the_questions_bottom():
    box = _Box()
    qh = int(Inches(0.40))
    r = content_box(box, question_height=qh, footer_top=int(Inches(6.9)))
    assert r.chart_top >= r.question_top + qh, "the chart starts inside the question"
    assert r.chart_top - (r.question_top + qh) >= int(Inches(0.10)), "no margin"


def test_a_longer_question_pushes_the_chart_further_down():
    """The failure mode this replaces grew UPWARD into the title instead."""
    box = _Box()
    short = content_box(box, question_height=int(Inches(0.30)),
                        footer_top=int(Inches(6.9)))
    long_ = content_box(box, question_height=int(Inches(1.20)),
                        footer_top=int(Inches(6.9)))
    assert long_.chart_top > short.chart_top
    assert long_.question_top == short.question_top, "the question's top never moves"


def test_the_chart_ends_above_the_footer():
    box = _Box()
    ft = int(Inches(6.9))
    r = content_box(box, question_height=int(Inches(0.40)), footer_top=ft)
    assert r.chart_top + r.chart_height <= ft - int(Inches(0.10))


def test_the_chart_keeps_a_usable_height_when_squeezed_from_both_ends():
    box = _Box()
    r = content_box(box, question_height=int(Inches(3.0)),
                    footer_top=int(Inches(2.6)))
    assert r.chart_height >= int(Inches(1.0))


def test_no_question_gives_the_chart_the_whole_box():
    box = _Box()
    r = content_box(box, question_height=0, footer_top=int(Inches(6.9)))
    assert r.chart_top == box.top
