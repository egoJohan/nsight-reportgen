"""TDD tests for LibreOffice PPTX->PDF conversion and PDF page rasterization (Task 1.3)."""
from __future__ import annotations
import os
import shutil
import pytest
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.render.base import Slot
from reportbuilder.render.native.column import build_column_chart
from reportbuilder.testing.fixtures import known_series

pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None,
    reason="LibreOffice not installed",
)


def _make_deck(tmp_path) -> str:
    """Build a one-chart PPTX using build_column_chart and save to tmp_path."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slot = Slot(
        slide_index=0,
        left=Inches(1),
        top=Inches(1),
        width=Inches(8),
        height=Inches(5),
        name="slot1",
    )
    series = known_series()
    build_column_chart(slide, slot, series)
    deck_path = str(tmp_path / "deck.pptx")
    prs.save(deck_path)
    return deck_path


def test_pptx_to_pdf_produces_pdf(tmp_path):
    """pptx_to_pdf converts a real chart deck to a non-empty PDF."""
    from reportbuilder.export.pdf_convert import pptx_to_pdf

    deck = _make_deck(tmp_path)
    pdf = pptx_to_pdf(deck, str(tmp_path))

    assert pdf.endswith(".pdf"), f"expected .pdf extension, got {pdf!r}"
    assert os.path.getsize(pdf) > 0, "PDF must be non-empty"


def test_pdf_page_to_png(tmp_path):
    """pdf_page_to_png rasterizes first page of the converted PDF to a non-empty PNG."""
    from reportbuilder.export.pdf_convert import pptx_to_pdf
    from reportbuilder.export.preview import pdf_page_to_png

    deck = _make_deck(tmp_path)
    pdf = pptx_to_pdf(deck, str(tmp_path))
    png = pdf_page_to_png(pdf, 0, str(tmp_path / "p0.png"))

    assert os.path.getsize(png) > 0, "PNG must be non-empty"
