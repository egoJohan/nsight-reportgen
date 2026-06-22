"""TDD tests for deck assembly (Task 5.14).

Covers:
- render_report native dispatch: target slides contain c:chart, zero pictures.
- render_report image dispatch: target slides contain one PICTURE, no c:chart.
- render_to_file: saved Presentation reopens without exception (REQ-C-29a).
- image builder title plumbing: ctx.title flows through without error.
"""
from __future__ import annotations

import dataclasses
import tempfile
import os

import pytest
from pptx import Presentation as _open_prs
from pptx.presentation import Presentation as PrsClass
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

from reportbuilder.render.base import StyleSpec
from reportbuilder.render.deck import render_report, render_to_file
from reportbuilder.testing.fixtures import one_chart_report, two_chart_report, known_series


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _series_by_ref(report):
    """Build series_by_ref mapping all ChartSpec.question_ref -> known_series()."""
    return {spec.question_ref: known_series() for spec in report.charts}


def _slide_has_chart(slide) -> bool:
    """Return True if the slide contains any c:chart element."""
    for shape in slide.shapes:
        if shape.has_chart:
            return True
    return False


def _slide_chart_title(slide) -> str | None:
    """Return the text of the first chart title found on the slide, or None."""
    for shape in slide.shapes:
        if shape.has_chart:
            chart = shape.chart
            if chart.has_title:
                return chart.chart_title.text_frame.text
    return None


def _slide_picture_count(slide) -> int:
    """Count MSO_SHAPE_TYPE.PICTURE shapes on a slide."""
    return sum(1 for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE)


def _slide_has_picture(slide) -> bool:
    return _slide_picture_count(slide) > 0


# ---------------------------------------------------------------------------
# Test 1: native dispatch
# ---------------------------------------------------------------------------

def test_render_report_native_dispatch():
    """Native render_mode: slides get a c:chart, zero PICTURE shapes.

    Also asserts chart title == supplied title string (apply_elements applied it).
    """
    report = one_chart_report()           # render_mode="native", one chart q1/vertical_bar
    assert report.render_mode == "native"

    series_by_ref = _series_by_ref(report)
    style = StyleSpec()

    prs = render_report(report, series_by_ref, style, titles={"q1": "Satisfaction"})

    assert isinstance(prs, PrsClass)
    assert len(prs.slides) >= 1

    # Find the slide(s) that were rendered into
    rendered_slides = list(prs.slides)

    # At least one slide must have a chart
    assert any(_slide_has_chart(s) for s in rendered_slides), (
        "Expected at least one slide with a c:chart element in native mode"
    )

    # No slide should have any PICTURE shape
    for slide in rendered_slides:
        n_pics = _slide_picture_count(slide)
        assert n_pics == 0, (
            f"Slide {slide} has {n_pics} PICTURE shape(s); expected 0 in native mode"
        )

    # Check the chart title was applied correctly
    for slide in rendered_slides:
        if _slide_has_chart(slide):
            title_text = _slide_chart_title(slide)
            assert title_text == "Satisfaction", (
                f"Chart title should be 'Satisfaction', got {title_text!r}"
            )


# ---------------------------------------------------------------------------
# Test 2: image dispatch
# ---------------------------------------------------------------------------

def test_render_report_image_dispatch():
    """Image render_mode: slides get exactly one PICTURE shape, no c:chart."""
    report = one_chart_report()           # render_mode="native" — swap to image
    report = dataclasses.replace(report, render_mode="image")
    assert report.render_mode == "image"

    series_by_ref = _series_by_ref(report)
    style = StyleSpec()

    prs = render_report(report, series_by_ref, style)

    assert isinstance(prs, PrsClass)
    assert len(prs.slides) >= 1

    rendered_slides = list(prs.slides)

    # At least one slide must have a picture
    assert any(_slide_has_picture(s) for s in rendered_slides), (
        "Expected at least one slide with a PICTURE shape in image mode"
    )

    # No slide should have a chart element
    for slide in rendered_slides:
        assert not _slide_has_chart(slide), (
            "Image mode should not produce c:chart elements"
        )

    # Each slide that was rendered into should have exactly one picture
    picture_slides = [s for s in rendered_slides if _slide_has_picture(s)]
    for slide in picture_slides:
        n = _slide_picture_count(slide)
        assert n == 1, f"Expected exactly 1 PICTURE per rendered slide, found {n}"


# ---------------------------------------------------------------------------
# Test 3: render_to_file reopens
# ---------------------------------------------------------------------------

def test_render_to_file_reopens():
    """render_to_file saves a file that can be re-opened as a Presentation (REQ-C-29a)."""
    report = one_chart_report()
    series_by_ref = _series_by_ref(report)
    style = StyleSpec()

    with tempfile.TemporaryDirectory() as tmp:
        out_path = os.path.join(tmp, "output.pptx")
        returned = render_to_file(report, series_by_ref, style, out_path)

        assert returned == out_path, "render_to_file should return the out_path"
        assert os.path.isfile(out_path), "Output file must exist"

        # Reopen without exception
        prs2 = _open_prs(out_path)
        assert len(prs2.slides) >= 1


# ---------------------------------------------------------------------------
# Test 4: image builder uses ctx.title (title plumbing check)
# ---------------------------------------------------------------------------

def test_image_builder_uses_ctx_title():
    """Image builder renders without error when ctx.title is a non-empty string.

    This validates the Part A change: ax.set_title(ctx.title) is called instead
    of ax.set_title(""), so rendering with a title must not raise.
    """
    report = one_chart_report()
    report = dataclasses.replace(report, render_mode="image")
    series_by_ref = _series_by_ref(report)
    style = StyleSpec()

    # Should not raise even with a non-trivial title string
    prs = render_report(
        report, series_by_ref, style,
        titles={"q1": "Customer Satisfaction Score 2025"},
    )
    assert isinstance(prs, PrsClass)
    # Confirm a picture was produced (image mode worked)
    assert any(_slide_has_picture(s) for s in prs.slides)


# ---------------------------------------------------------------------------
# Test 5: two-chart report fills two slides
# ---------------------------------------------------------------------------

def test_render_report_two_charts_native():
    """Two-chart native report produces two slides each with a chart."""
    report = two_chart_report()
    series_by_ref = _series_by_ref(report)
    style = StyleSpec()

    prs = render_report(report, series_by_ref, style)

    assert isinstance(prs, PrsClass)
    # Two charts → two slides (fallback path creates a new slide per chart)
    assert len(prs.slides) == 2
    for slide in prs.slides:
        assert _slide_has_chart(slide), "Each slide should have a native chart"
        assert _slide_picture_count(slide) == 0, "No pictures in native mode"
