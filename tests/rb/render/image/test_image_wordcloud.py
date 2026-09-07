"""Task J.2: image-mode word-cloud builder (build_image_wordcloud).

Asserts the builder places exactly one PICTURE shape on the slide, the saved PNG is
non-empty, has a cream-ish background, and that the layout is deterministic
(random_state=42) so two renders of the same series produce byte-identical images.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches

from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.render.image.wordcloud import (
    build_image_wordcloud,
    _resolve_font_path,
)
from reportbuilder.render.plugins import plugin
from reportbuilder.stats.series import Cell, SeriesResult


def _slot() -> Slot:
    return Slot(slide_index=0, left=Inches(1), top=Inches(1),
                width=Inches(8), height=Inches(5), name="slot1")


def _spec() -> ChartSpec:
    return ChartSpec(
        question_ref="q", chart_type="wordcloud", statistic="count",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="slot1",
        elements=ElementToggles(),
    )


def _series() -> SeriesResult:
    cats = ("kallis", "huono", "luotettava", "hyvä", "ahne")
    counts = {"kallis": 185.0, "huono": 75.0, "luotettava": 61.0,
              "hyvä": 60.0, "ahne": 57.0}
    cells = {(c, "Total"): Cell(pct=None, count=counts[c], mean=None) for c in cats}
    return SeriesResult(categories=cats, segments=("Total",), cells=cells,
                        base_n={"Total": 817}, statistic="count")


def _ctx():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    spec = _spec()
    ctx = RenderContext(slide=slide, slot=_slot(), style=StyleSpec(),
                        spec=spec, series=_series(), fmt=spec.number_format)
    return prs, slide, ctx


def test_wordcloud_registered_in_image_builders_and_plugin():
    assert "wordcloud" in IMAGE_BUILDERS
    p = plugin("wordcloud")
    assert p.label == "Word Cloud"
    assert p.image_build is build_image_wordcloud
    # Never auto-suggested for normal questions.
    assert p.suitability(None, _series()) is None


def test_build_image_wordcloud_places_one_picture():
    _prs, slide, ctx = _ctx()
    build_image_wordcloud(ctx)
    pics = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pics) == 1
    assert pics[0].width > 0 and pics[0].height > 0


def test_resolve_font_path_returns_existing_ttf():
    import os
    fp = _resolve_font_path()
    assert fp and os.path.exists(fp)
    assert fp.lower().endswith(".ttf")


def _placed_png(slide) -> bytes:
    pics = [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pics) == 1
    return pics[0].image.blob


def test_the_cloud_lets_the_slide_show_through():
    """It used to paint cream into its own raster. `transparent=True` on the
    figure never covered that — an imshow'd array is not a figure patch — so on
    any deck that is not cream the cloud sat in a pale box. Colour and
    transparency in depth: tests/suite/unit/render/test_wordcloud_colours.py."""
    _prs, slide, ctx = _ctx()
    build_image_wordcloud(ctx)
    with Image.open(io.BytesIO(_placed_png(slide))) as im:
        im = im.convert("RGBA")
        assert im.getpixel((0, 0))[3] == 0


def test_wordcloud_layout_is_deterministic():
    """The BUILDER, twice — not a hand-rolled WordCloud with the same seed. The
    previous version of this test built its own cloud and compared it to itself,
    which held whatever the builder did."""
    _p1, slide_a, ctx_a = _ctx()
    build_image_wordcloud(ctx_a)
    _p2, slide_b, ctx_b = _ctx()
    build_image_wordcloud(ctx_b)
    assert _placed_png(slide_a) == _placed_png(slide_b)
