"""The chart preview must look like the slide it is previewing.

A preview is drawn by compositing the chart onto the customer's empty slide,
which LibreOffice renders once per template instead of once per chart — 4.4s a
chart became ~0.2s. That is only worth having if the result is the same picture,
so this renders one chart BOTH ways and compares the pixels.

Exact equality is the wrong bar: LibreOffice and PIL resample and antialias
differently, so glyph edges and bar outlines land a shade apart. Layout is what
must match — a shifted chart, a different colour or a substituted typeface moves
far more than a few percent of pixels.
"""
from __future__ import annotations

import shutil

import numpy as np
import pytest
from PIL import Image

from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.pptx_build import build_pptx, build_presentation
from reportbuilder.export.preview import rasterize_pages
from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, Report, SortSpec,
)
from reportbuilder.render.base import StyleSpec
from reportbuilder.render.image import fast_preview

from suite.unit.render import _builders as B

pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None or shutil.which("pdftoppm") is None,
    reason="LibreOffice + poppler required",
)

_DPI = 110


def _one_chart_report():
    spec = ChartSpec(
        question_ref="q", chart_type="horizontal_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        # title=False: the frontend owns the title band, which is when the
        # compositor is used.
        elements=ElementToggles(title=False),
    )
    return Report(name="p", render_mode="image", template_ref="", charts=(spec,))


class _Model:
    """The smallest thing build_pptx needs: one question it can chart."""

    def __init__(self):
        self._q = B.q(kind="single", qid="q")

    def question(self, ref):
        return self._q


def _rendered_by_libreoffice(tmp_path, style):
    pptx = build_pptx(_one_chart_report(), _Model(), None, str(tmp_path / "deck.pptx"),
                      style=style)
    pdf = pptx_to_pdf(pptx, str(tmp_path / "pdf"))
    png = rasterize_pages(pdf, str(tmp_path / "png"), dpi=_DPI)[0]
    return Image.open(png).convert("RGB")


def _composited(style):
    prs = build_presentation(_one_chart_report(), _Model(), None, style=style)
    return fast_preview.compose_from_slide(style, prs.slides[0], dpi=_DPI)


@pytest.fixture(autouse=True)
def _fresh_ground(tmp_path, monkeypatch):
    """A cache directory of its own, so the test never reads another run's ground."""
    monkeypatch.setattr(fast_preview, "_CACHE", tmp_path / "ground")


def test_the_composited_preview_matches_the_rendered_slide(tmp_path):
    style = StyleSpec()
    theirs = _rendered_by_libreoffice(tmp_path, style)
    ours = _composited(style)
    assert ours is not None, "no ground was rendered — the fast path would never run"
    assert ours.size == theirs.size

    diff = np.abs(np.asarray(theirs, dtype=int)
                  - np.asarray(ours.convert("RGB"), dtype=int)).sum(axis=2)
    # Antialiasing differs; anything structural does not fit in 5% of the slide.
    assert (diff > 30).mean() < 0.05, "the preview does not match the slide"
    assert (diff == 0).mean() > 0.80


def test_the_ground_is_rendered_once_and_reused(tmp_path, monkeypatch):
    """The whole point: LibreOffice runs per TEMPLATE, not per chart."""
    style = StyleSpec()
    calls = []
    real = fast_preview.pptx_to_pdf
    monkeypatch.setattr(fast_preview, "pptx_to_pdf",
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    for _ in range(3):
        assert _composited(style) is not None
    assert len(calls) == 1


def test_a_missing_ground_falls_back_rather_than_guessing(monkeypatch):
    """A preview that cannot be composited must say so, not invent a slide."""
    monkeypatch.setattr(fast_preview, "ground_image", lambda *a, **k: None)
    prs = build_presentation(_one_chart_report(), _Model(), None, style=StyleSpec())
    assert fast_preview.compose_from_slide(StyleSpec(), prs.slides[0]) is None
