"""CONV tests: pdf_page_count matches slide count after pptx_to_pdf (REQ-C-21/28a, Task 6.2)."""
from __future__ import annotations
import shutil
import pandas as pd
import pytest
from pptx import Presentation

from reportbuilder.export.pdf_convert import pptx_to_pdf, pdf_page_count
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.model.question import Variable, ValueLabel, Question, QuestionModel
from reportbuilder.model.report import ChartSpec, Report, SortSpec, NumberFormat, ElementToggles
from reportbuilder.testing.fixtures import tiny_model_and_data, one_chart_report

pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None or shutil.which("pdfinfo") is None,
    reason="LibreOffice + poppler required",
)


def test_pdf_page_count_matches_slides(tmp_path):
    """pptx_to_pdf produces a valid PDF whose page count equals the slide count (REQ-C-21/28a)."""
    model, data = tiny_model_and_data()
    report = one_chart_report()
    pptx = build_pptx(report, model, data, str(tmp_path / "r.pptx"))
    pdf = pptx_to_pdf(pptx, str(tmp_path))

    # REQ-C-28a: file is a valid PDF
    with open(pdf, "rb") as fh:
        assert fh.read(5) == b"%PDF-", "PDF must start with %PDF- magic bytes"

    # REQ-C-21: page count == slide count
    slide_count = len(Presentation(pptx).slides._sldIdLst)
    assert pdf_page_count(pdf) == slide_count


def test_pdf_page_count_two_charts(tmp_path):
    """Two-chart report → two-page PDF (REQ-C-21)."""
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

    report = Report(
        name="R2",
        render_mode="native",
        template_ref="t.pptx",
        charts=(_spec("q1", "slot1"), _spec("q2", "slot2")),
    )
    pptx = build_pptx(report, model, data, str(tmp_path / "two.pptx"))
    pdf = pptx_to_pdf(pptx, str(tmp_path))

    assert pdf_page_count(pdf) == 2
