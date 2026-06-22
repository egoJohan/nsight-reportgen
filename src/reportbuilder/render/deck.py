"""Deck assembly entry point (Task 5.14 — design §C2).

render_report: open template, render each ChartSpec into its slot,
dispatch by render_mode.

render_to_file: convenience wrapper that saves to disk and returns the path
(REQ-C-29a).
"""
from __future__ import annotations

from pptx import Presentation
from pptx.util import Inches

from reportbuilder.model.report import Report
from reportbuilder.render.base import RenderContext, Slot
from reportbuilder.render.elements import apply_elements, add_n_annotation, add_filter_annotation
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.render.native import NATIVE_BUILDERS


def render_report(
    report: Report,
    series_by_ref: dict,
    style,
    titles: dict | None = None,
) -> Presentation:
    """Open the template, render each ChartSpec into its slot.

    Parameters
    ----------
    report:
        The Report definition (charts, render_mode, template_ref).
    series_by_ref:
        Maps ChartSpec.question_ref -> SeriesResult.
    style:
        A StyleSpec (base) or TemplateStyleSpec.  When a TemplateStyleSpec
        carries a template source file, that Presentation is used; otherwise
        a blank Presentation is created.
    titles:
        Optional mapping question_ref -> chart title text.  When omitted,
        chart titles default to "".
    """
    # --- Open or create the Presentation ---
    spec_source = getattr(style, "spec_source", None)
    # Only try to open if spec_source looks like a real path (not the
    # sentinel strings used by TemplateStyleSpec when built from load_style_spec).
    # A safe heuristic: try Presentation(spec_source) and fall back on any error.
    prs = None
    if spec_source and spec_source not in ("generic", "attendo-interim-proxy"):
        try:
            prs = Presentation(spec_source)
        except Exception:
            prs = None
    if prs is None:
        prs = Presentation()

    _titles = titles or {}

    for spec in report.charts:
        # --- Resolve slot and slide ---
        slot = _resolve_slot(prs, style, spec.template_slot)
        # slide_index may reference an existing slide or was just appended
        slide = prs.slides[slot.slide_index]

        # --- Build context ---
        series = series_by_ref[spec.question_ref]
        title = _titles.get(spec.question_ref, "")
        ctx = RenderContext(
            slide=slide,
            slot=slot,
            style=style,
            spec=spec,
            series=series,
            fmt=spec.number_format,
            title=title,
        )

        # --- Dispatch ---
        if report.render_mode == "native":
            gf = NATIVE_BUILDERS[spec.chart_type](ctx)
            apply_elements(gf.chart, ctx, title)
            add_n_annotation(ctx)
            add_filter_annotation(ctx)
        else:
            IMAGE_BUILDERS[spec.chart_type](ctx)

    return prs


def render_to_file(
    report: Report,
    series_by_ref: dict,
    style,
    out_path: str,
    titles: dict | None = None,
) -> str:
    """Render report to *out_path* and return the path (REQ-C-29a)."""
    prs = render_report(report, series_by_ref, style, titles)
    prs.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_slot(prs: Presentation, style, slot_name: str) -> Slot:
    """Return a Slot for *slot_name*, falling back to a new blank slide.

    Tries style.slot(slot_name) first.  If that raises KeyError (slot not in
    template) or AttributeError (base StyleSpec has no slot() method), a fresh
    blank slide is appended to *prs* and a synthesised Slot is returned.
    """
    try:
        return style.slot(slot_name)
    except (KeyError, AttributeError):
        pass

    # Fallback: add a new blank slide and synthesise a slot covering most of it
    layout = prs.slide_layouts[6]  # blank layout
    slide = prs.slides.add_slide(layout)
    slide_index = len(prs.slides) - 1
    return Slot(
        slide_index=slide_index,
        left=int(Inches(0.8)),
        top=int(Inches(1.0)),
        width=int(Inches(8.5)),
        height=int(Inches(5.0)),
        name=slot_name,
    )
