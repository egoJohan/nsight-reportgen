from __future__ import annotations
from reportbuilder.model.report import Report, renders_as_bullets
from reportbuilder.model.question import QuestionModel
from reportbuilder.render.base import StyleSpec
from reportbuilder.render.deck import render_to_file
from reportbuilder.stats.engine import compute


def build_pptx(report: Report, model: QuestionModel, data, out_path: str,
               style: StyleSpec | None = None) -> str:
    """Compute each chart's SeriesResult, then render the Report to a .pptx (REQ-C-22/18)."""
    if style is None:
        style = StyleSpec()   # generic base style (no template); deck synthesizes slides
    series_by_ref: dict = {}
    titles: dict = {}
    for spec in report.charts:
        # Special (non-chart) slides carry no question/series — they render as
        # text/bullet slides in render_report. Skip stats for them.
        if renders_as_bullets(spec):
            continue
        q = model.question(spec.question_ref)
        series_by_ref[spec.question_ref] = compute(q, spec, data, model)
        titles[spec.question_ref] = q.text
    return render_to_file(report, series_by_ref, style, out_path, titles=titles)
