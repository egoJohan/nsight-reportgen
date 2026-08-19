"""Tests for PDF page rasterization (REQ-C-20).

The "dual view" of REQ-C-19a/b is two views of ONE PDF, drawn in the browser —
there is nothing on this side to test but the rasterizer itself, which the
Design page's chart previews use.

TDD — these tests must be written before the implementation.
Skip if LibreOffice (soffice) or poppler (pdftoppm) are not installed.
"""
from __future__ import annotations
import pathlib
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
from reportbuilder.export.preview import rasterize_pages

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


def test_rasterize_pages_count(tmp_path):
    """A 1-chart deck rasterizes to exactly 1 page."""
    model, data = _one_chart_model_and_data()
    report = _one_chart_report()

    pptx_path = build_pptx(report, model, data, str(tmp_path / "one.pptx"))
    pdf_path = pptx_to_pdf(pptx_path, str(tmp_path / "pdf_out"))

    out_dir = str(tmp_path / "pages")
    pages = rasterize_pages(pdf_path, out_dir)
    assert len(pages) == 1


def test_chunked_rasterization_matches_a_single_process(tmp_path):
    """The pages go out in parallel chunks; the result must be identical.

    Safe only because pdftoppm pads the page number by the DOCUMENT's page
    count, not the chunk's — so page 9 of a 12-page deck is `page-09.png`
    whether it was rendered with pages 1-8 or on its own, and the sort still
    orders the deck. If that ever changes, this test says so.
    """
    model, data = _two_chart_model_and_data()
    report = _two_chart_report()
    pptx_path = build_pptx(report, model, data, str(tmp_path / "two.pptx"))
    pdf_path = pptx_to_pdf(pptx_path, str(tmp_path / "pdf_out"))

    one = rasterize_pages(pdf_path, str(tmp_path / "serial"), workers=1)
    many = rasterize_pages(pdf_path, str(tmp_path / "parallel"), workers=2)

    assert [pathlib.Path(p).name for p in one] == [pathlib.Path(p).name for p in many]
    assert len(many) == 2
    for path in many:
        with open(path, "rb") as f:
            assert f.read(8) == PNG_MAGIC
