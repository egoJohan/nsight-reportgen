"""Image-render matrix: every chart_type in IMAGE_BUILDERS places exactly one
valid PNG PICTURE for a representative series.

Deterministic — matplotlib Agg is headless-safe; no soffice.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from suite._helpers import make_ctx, assert_single_picture, picture_shapes
from suite.integration.render._series import series_for

from reportbuilder.render.image import IMAGE_BUILDERS

IMAGE_TYPES = [
    "vertical_bar", "horizontal_bar", "stacked_vertical_bar", "stacked_horizontal_bar",
    "line", "pie", "doughnut", "radar", "scatter", "funnel", "combo", "wordcloud",
]


def test_registry_has_all_twelve():
    assert set(IMAGE_BUILDERS) == set(IMAGE_TYPES)
    assert len(IMAGE_BUILDERS) == 12


@pytest.mark.parametrize("chart_type", IMAGE_TYPES)
def test_image_builder_places_single_png(chart_type):
    """Each builder returns None and places exactly ONE PICTURE that is a valid PNG."""
    series, overrides = series_for(chart_type)
    prs, slide, slot, ctx = make_ctx(chart_type, series, **overrides)

    ret = IMAGE_BUILDERS[chart_type](ctx)

    assert ret is None, f"{chart_type} image builder should return None, got {ret!r}"
    pic = assert_single_picture(slide, slot)

    # assert_single_picture already checks the PNG magic + aspect; double-check the
    # blob is a decodable, non-empty raster.
    blob = pic.image.blob
    assert blob[:4] == b"\x89PNG"
    img = Image.open(io.BytesIO(blob))
    w, h = img.size
    assert w > 0 and h > 0


@pytest.mark.parametrize("chart_type", IMAGE_TYPES)
def test_image_builder_adds_no_native_chart(chart_type):
    """Image mode must not emit a native c:chart graphicFrame."""
    series, overrides = series_for(chart_type)
    prs, slide, slot, ctx = make_ctx(chart_type, series, **overrides)
    IMAGE_BUILDERS[chart_type](ctx)
    assert not any(getattr(sh, "has_chart", False) for sh in slide.shapes)
    assert len(picture_shapes(slide)) == 1
