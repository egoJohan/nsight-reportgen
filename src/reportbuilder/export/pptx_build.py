from __future__ import annotations
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    is_demographics_grid,
    renders_as_bullets,
)
from reportbuilder.model.question import QuestionModel
from reportbuilder.render.base import StyleSpec
from reportbuilder.render.deck import render_to_file
from reportbuilder.stats.engine import compute


def _cell_spec(ref: str, chart_type: str) -> ChartSpec:
    """A minimal spec for one demographics-grid cell chart."""
    return ChartSpec(
        question_ref=ref, chart_type=chart_type, statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="pct"), template_slot="cell", elements=ElementToggles(),
    )


def build_pptx(report: Report, model: QuestionModel, data, out_path: str,
               style: StyleSpec | None = None) -> str:
    """Compute each chart's SeriesResult, then render the Report to a .pptx (REQ-C-22/18)."""
    if style is None:
        style = StyleSpec()   # generic base style (no template); deck synthesizes slides
    series_by_ref: dict = {}
    titles: dict = {}
    for spec in report.charts:
        # Demographics grid: compute a series per cell chart (by question_ref).
        if is_demographics_grid(spec):
            for c in (spec.options.get("charts") or []):
                ref = c.get("question_ref")
                ctype = c.get("chart_type") or "vertical_bar"
                try:
                    q = model.question(ref)
                    series_by_ref[ref] = compute(q, _cell_spec(ref, ctype), data, model)
                    titles[ref] = q.text
                except Exception:
                    pass
            continue
        # Bullet slides (special slides + themes) carry no series — they render
        # as text in render_report. Skip stats, but record the question text so a
        # themes slide can use it as its heading.
        if renders_as_bullets(spec):
            try:
                titles[spec.question_ref] = model.question(spec.question_ref).text
            except Exception:
                pass
            continue
        q = model.question(spec.question_ref)
        series_by_ref[spec.question_ref] = compute(q, spec, data, model)
        titles[spec.question_ref] = q.text
    return render_to_file(report, series_by_ref, style, out_path, titles=titles)
