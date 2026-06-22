"""Layer-2 conversion-drift fidelity check (design §10, REQ-C-20).

Confirms that chart data-label numbers survive the PPTX -> PDF (LibreOffice)
conversion and can be extracted from the rendered PDF as selectable text via
pdfplumber.  This is the §10 layer-2 drift guard.
"""
from __future__ import annotations

import shutil

import pytest

from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.testing.fidelity import assert_series_match, numbers_from_pdf
from reportbuilder.testing.fixtures import (
    known_pcts,
    known_series,
    one_chart_report,
    tiny_model_and_data,
)

pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None,
    reason="LibreOffice required",
)


def _build_pdf(tmp_path) -> str:
    """Build a one-chart PPTX from tiny_model_and_data / one_chart_report, then convert."""
    model, data = tiny_model_and_data()
    report = one_chart_report()
    pptx = build_pptx(report, model, data, str(tmp_path / "r.pptx"))
    return pptx_to_pdf(pptx, str(tmp_path))


def test_pdf_numbers_survive_conversion(tmp_path):
    """Data-label numbers (60.0, 40.0) appear as selectable text in the converted PDF (REQ-C-20)."""
    pdf = _build_pdf(tmp_path)
    nums = numbers_from_pdf(pdf)
    for expected in known_pcts():
        assert any(abs(n - expected) <= 0.5 for n in nums), (
            f"{expected} missing from PDF numbers {nums} — "
            "layer-2 drift: data labels may not have rendered as selectable text "
            "or LibreOffice rasterized them."
        )


def test_pdf_numbers_via_assert_series_match(tmp_path):
    """assert_series_match confirms all SeriesResult values present in PDF text (REQ-C-20)."""
    pdf = _build_pdf(tmp_path)
    assert_series_match({"pdf": numbers_from_pdf(pdf)}, known_series(), tol=0.5)
