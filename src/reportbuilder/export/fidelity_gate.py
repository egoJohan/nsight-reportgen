"""Three-layer fidelity gate — wires §10 fidelity layers into one callable (REQ-C-20, design §10).

Layer 1 (native): pptx chart-data == SeriesResult (catches render bugs).
Layer 2 (native): pdf data-label numbers == SeriesResult (catches LibreOffice drift).
Layer 3 (image):  series that fed the builder == engine.compute output (identity check; §C4).
"""
from __future__ import annotations
from reportbuilder.model.report import Report
from reportbuilder.model.question import QuestionModel
from reportbuilder.stats.series import SeriesResult
from reportbuilder.stats.engine import compute
from reportbuilder.testing.fidelity import numbers_from_pptx, numbers_from_pdf, assert_series_match


def run_fidelity_gate(report: Report, model: QuestionModel, data,
                      pptx_path: str, pdf_path: str | None,
                      series: SeriesResult, *, tol: float = 0.5) -> None:
    """Assert the rendered artifacts faithfully carry `series` (the single-chart SeriesResult).
    Raises AssertionError if any applicable layer fails. (REQ-C-20, design §10)
    - native: layer 1 (pptx chart-data == series) + layer 2 (pdf data-label numbers == series, drift guard).
    - image: layer 3 (the series that fed the builder == engine.compute output — identity check; §C4)."""
    if report.render_mode == "native":
        # layer 1 — pptx chart series values == SeriesResult (catches render bugs)
        assert_series_match(numbers_from_pptx(pptx_path), series, tol=tol)
        # layer 2 — pdf data-label numbers == SeriesResult (catches LibreOffice drift)
        if pdf_path is None:
            raise AssertionError("native mode requires a PDF for the layer-2 drift check")
        assert_series_match({"pdf": numbers_from_pdf(pdf_path)}, series, tol=tol)
    else:
        # layer 3 — image numbers are pixels (not artifact-extractable); verify the inputs:
        # the series that fed each builder equals the engine's compute output.
        for spec in report.charts:
            recomputed = compute(model.question(spec.question_ref), spec, data, model)
            # every value of `series` must be reproduced by recompute (identity within tol)
            extracted = {seg: [getattr(recomputed.cell(c, seg), recomputed.statistic) or 0.0
                               for c in recomputed.categories]
                         for seg in recomputed.segments}
            assert_series_match(extracted, series, tol=tol)
