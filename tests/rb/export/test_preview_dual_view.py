"""Tests for dual-view preview rasterization (REQ-C-19a/b, C-20).

TDD — these tests must be written before the implementation.
Skip if LibreOffice (soffice) or poppler (pdftoppm) are not installed.
"""
from __future__ import annotations
import shutil
import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None or shutil.which("pdftoppm") is None,
    reason="LibreOffice + poppler required",
)

from reportbuilder.model.question import Variable, ValueLabel, Question, QuestionModel
from reportbuilder.model.report import ChartSpec, Report, SortSpec, NumberFormat, ElementToggles
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.preview import rasterize_pages, slide_view, page_view

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _two_chart_model_and_data():
    """Two distinct categorical question vars (q1, q2)."""
    q1_var = Variable(
        name="q1", label="Satisfaction", measurement="categorical",
        value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
        missing_values=frozenset(),
    )
    q2_var = Variable(
        name="q2", label="Likelihood", measurement="categorical",
        value_labels=(ValueLabel(1.0, "High"), ValueLabel(2.0, "Low")),
        missing_values=frozenset(),
    )
    model = QuestionModel(
        variables={"q1": q1_var, "q2": q2_var},
        questions=[
            Question(qid="q1", kind="single", variables=("q1",), text="Satisfaction"),
            Question(qid="q2", kind="single", variables=("q2",), text="Likelihood"),
        ],
    )
    data = pd.DataFrame({"q1": [1.0, 1.0, 2.0, 2.0, 1.0], "q2": [1.0, 2.0, 1.0, 2.0, 1.0]})
    return model, data


def _two_chart_report() -> Report:
    def _spec(question_ref: str, slot: str) -> ChartSpec:
        return ChartSpec(
            question_ref=question_ref,
            chart_type="vertical_bar",
            statistic="pct",
            classifying_var=None,
            number_format=NumberFormat(),
            sort=SortSpec(basis="data_order"),
            template_slot=slot,
            elements=ElementToggles(),
        )

    return Report(
        name="R2",
        render_mode="native",
        template_ref="t.pptx",
        charts=(_spec("q1", "slot1"), _spec("q2", "slot2")),
    )


def _one_chart_model_and_data():
    """Single categorical question var (q1)."""
    q1_var = Variable(
        name="q1", label="Satisfaction", measurement="categorical",
        value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
        missing_values=frozenset(),
    )
    model = QuestionModel(
        variables={"q1": q1_var},
        questions=[
            Question(qid="q1", kind="single", variables=("q1",), text="Satisfaction"),
        ],
    )
    data = pd.DataFrame({"q1": [1.0, 1.0, 2.0, 2.0, 1.0]})
    return model, data


def _one_chart_report() -> Report:
    return Report(
        name="R1",
        render_mode="native",
        template_ref="t.pptx",
        charts=(ChartSpec(
            question_ref="q1",
            chart_type="vertical_bar",
            statistic="pct",
            classifying_var=None,
            number_format=NumberFormat(),
            sort=SortSpec(basis="data_order"),
            template_slot="slot1",
            elements=ElementToggles(),
        ),),
    )


def test_dual_view_same_artifact(tmp_path):
    """slide_view and page_view yield the same PNG set over a 2-chart deck.

    Both PPT-style (slide-per-page) and PDF-style (continuous) pagination views
    are selectable and operate over the same PDF artifact. (REQ-C-19a, REQ-C-19b)
    """
    model, data = _two_chart_model_and_data()
    report = _two_chart_report()

    pptx_path = build_pptx(report, model, data, str(tmp_path / "r.pptx"))
    pdf_path = pptx_to_pdf(pptx_path, str(tmp_path / "pdf_out"))

    slides = slide_view(pdf_path, str(tmp_path / "slide"))
    pages = page_view(pdf_path, str(tmp_path / "page"))

    # Both views must produce the same number of pages (>= 2 for a 2-chart deck)
    assert len(slides) == len(pages) >= 2

    # All paths must end with .png
    assert all(p.endswith(".png") for p in slides)
    assert all(p.endswith(".png") for p in pages)

    # First PNG from each view must start with PNG magic bytes
    with open(slides[0], "rb") as f:
        assert f.read(8) == PNG_MAGIC
    with open(pages[0], "rb") as f:
        assert f.read(8) == PNG_MAGIC


def test_rasterize_pages_count(tmp_path):
    """A 1-chart deck rasterizes to exactly 1 page."""
    model, data = _one_chart_model_and_data()
    report = _one_chart_report()

    pptx_path = build_pptx(report, model, data, str(tmp_path / "one.pptx"))
    pdf_path = pptx_to_pdf(pptx_path, str(tmp_path / "pdf_out"))

    out_dir = str(tmp_path / "pages")
    pages = rasterize_pages(pdf_path, out_dir)
    assert len(pages) == 1
