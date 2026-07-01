"""Integration tests for the LibreOffice/poppler export layer (GATED).

Every test is marked `@pytest.mark.export` and uses the `require_soffice`
fixture, so the whole module SKIPS cleanly when LibreOffice is absent. Tests
that additionally need a poppler binary (`pdfinfo`, `pdftoppm`) guard that
specific tool separately with `shutil.which` and skip if it is missing.

Covered: pptx -> pdf conversion, PDF page count, the native and image fidelity
gates (layers 2 and 3), and page rasterization/preview.
"""
from __future__ import annotations

import dataclasses
import os
import shutil

import pytest

from reportbuilder.export.fidelity_gate import run_fidelity_gate
from reportbuilder.export.pdf_convert import pdf_page_count, pptx_to_pdf
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.export.preview import rasterize_pages
from reportbuilder.testing.fixtures import (
    known_series,
    one_chart_report,
    tiny_model_and_data,
    two_chart_report,
)

pytestmark = pytest.mark.export


def _need(tool: str) -> None:
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} (poppler) not installed")


# ---------------------------------------------------------------------------
# pptx -> pdf conversion (needs soffice)
# ---------------------------------------------------------------------------

def test_pptx_to_pdf_produces_pdf(require_soffice, tmp_path):
    """pptx_to_pdf converts a real chart deck to a non-empty .pdf."""
    model, data = tiny_model_and_data()
    pptx = build_pptx(one_chart_report(), model, data, str(tmp_path / "r.pptx"))

    pdf = pptx_to_pdf(pptx, str(tmp_path))

    assert pdf.endswith(".pdf")
    assert os.path.getsize(pdf) > 0, "PDF must be non-empty"


# ---------------------------------------------------------------------------
# pdf page count (needs soffice AND poppler pdfinfo)
# ---------------------------------------------------------------------------

def test_pdf_page_count_matches_slides(require_soffice, tmp_path):
    """pdf_page_count == number of chart specs (one page per slide)."""
    _need("pdfinfo")
    model, data = tiny_model_and_data()
    report = two_chart_report()
    pptx = build_pptx(report, model, data, str(tmp_path / "two.pptx"))
    pdf = pptx_to_pdf(pptx, str(tmp_path))

    assert pdf_page_count(pdf) == len(report.charts) == 2


# ---------------------------------------------------------------------------
# Fidelity gate — native path (layer 2: soffice-produced PDF)
# ---------------------------------------------------------------------------

def test_fidelity_gate_native_passes(require_soffice, tmp_path):
    """run_fidelity_gate does NOT raise for a faithfully-rendered native deck."""
    model, data = tiny_model_and_data()
    report = one_chart_report()  # native, q1 -> Yes60/No40 == known_series()
    pptx = build_pptx(report, model, data, str(tmp_path / "r.pptx"))
    pdf = pptx_to_pdf(pptx, str(tmp_path))

    run_fidelity_gate(report, model, data, pptx, pdf, known_series())


# ---------------------------------------------------------------------------
# Fidelity gate — image path (layer 3: recompute identity, soffice-free logic
# but kept here since the deck build is exercised alongside the native path)
# ---------------------------------------------------------------------------

def test_fidelity_gate_image_passes(require_soffice, tmp_path):
    """Image-mode gate (layer 3) does NOT raise; pdf_path is None."""
    model, data = tiny_model_and_data()
    report = dataclasses.replace(one_chart_report(), render_mode="image")
    pptx = build_pptx(report, model, data, str(tmp_path / "i.pptx"))

    run_fidelity_gate(report, model, data, pptx, None, known_series())


# ---------------------------------------------------------------------------
# Preview rasterization (needs soffice AND poppler pdftoppm)
# ---------------------------------------------------------------------------

def test_rasterize_pages_produces_pngs(require_soffice, tmp_path):
    """rasterize_pages emits one non-empty PNG per page of the converted PDF."""
    _need("pdftoppm")
    model, data = tiny_model_and_data()
    report = two_chart_report()
    pptx = build_pptx(report, model, data, str(tmp_path / "two.pptx"))
    pdf = pptx_to_pdf(pptx, str(tmp_path))

    pngs = rasterize_pages(pdf, str(tmp_path / "png"))

    assert len(pngs) == len(report.charts) == 2
    assert all(p.endswith(".png") and os.path.getsize(p) > 0 for p in pngs)
