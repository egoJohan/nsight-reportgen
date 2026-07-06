"""Deck assembly entry point (Task 5.14 — design §C2).

render_report: open template, render each ChartSpec into its slot,
dispatch by render_mode.

render_to_file: convenience wrapper that saves to disk and returns the path
(REQ-C-29a).
"""
from __future__ import annotations

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.exc import PackageNotFoundError
from pptx.util import Inches

from reportbuilder.model.report import Report, is_demographics_grid, renders_as_bullets
from reportbuilder.render.base import RenderContext, Slot
from reportbuilder.render.elements import apply_elements, add_n_annotation, add_filter_annotation
from reportbuilder.render.image.slide_chrome import add_image_slide_chrome
from reportbuilder.render.image.special_slide import render_special_slide
from reportbuilder.render.image.demographics_grid import render_demographics_grid
from reportbuilder.render.image._mpl import render_empty_chart, series_is_empty
import reportbuilder.render.plugins as _plugins  # registers all plugins as side-effect


# ---------------------------------------------------------------------------
# Completeness and purity guards (REQ-C-18, REQ-C-23a)
# ---------------------------------------------------------------------------

class CompletenessError(Exception):
    """Generated deck doesn't match the report definition (REQ-C-18)."""


class NativePurityError(Exception):
    """A native-mode report has a picture shape in a chart slot (REQ-C-23a)."""


def _count_chart_shapes(prs: Presentation) -> tuple[int, int]:
    """Return (chart_count, picture_count) across all slides in *prs*."""
    charts = sum(
        1 for s in prs.slides for sh in s.shapes if getattr(sh, "has_chart", False)
    )
    pics = sum(
        1 for s in prs.slides for sh in s.shapes
        if sh.shape_type == MSO_SHAPE_TYPE.PICTURE
    )
    return charts, pics


def assert_complete(prs: Presentation, report: Report,
                    expected_pics: int | None = None) -> None:
    """The deck contains exactly one rendered chart object per ChartSpec, nothing extra.

    Native mode: counts c:chart shapes.  Image mode: counts PICTURE shapes.
    Raises CompletenessError if the tally doesn't match. Bullet slides add no
    chart object; a demographics grid adds several pictures, so the caller passes
    ``expected_pics`` (computed where the series are known). (REQ-C-18)
    """
    charts, pics = _count_chart_shapes(prs)
    rendered = charts if report.render_mode == "native" else pics
    if expected_pics is not None and report.render_mode != "native":
        expected = expected_pics
    else:
        # Bullet/grid slides don't add exactly one picture; exclude them.
        expected = len([
            c for c in report.charts
            if not renders_as_bullets(c) and not is_demographics_grid(c)
        ])
    if rendered != expected:
        raise CompletenessError(
            f"expected {expected} {report.render_mode} chart objects, found {rendered}"
        )


def assert_no_pictures_in_chart_slots(prs: Presentation, report: Report, style=None) -> None:
    """Native-mode reports must contain ZERO picture shapes (editability gate, REQ-C-23a).

    No-op for image mode (image reports legitimately use pictures).
    """
    if report.render_mode != "native":
        return
    _charts, pics = _count_chart_shapes(prs)
    if pics > 0:
        raise NativePurityError(
            f"native-mode report has {pics} picture shape(s) in chart slots"
        )


class RenderCancelled(Exception):
    """Raised to abort a deck render mid-way when the caller signals cancellation
    (e.g. the client aborted the request). Checked between slides so a long run
    (hundreds of slides) stops promptly instead of grinding to the end."""


def render_report(
    report: Report,
    series_by_ref: dict,
    style,
    titles: dict | None = None,
    cancel_check=None,
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
        except (FileNotFoundError, PackageNotFoundError):
            prs = None
    if prs is None:
        # Wizard/generic reports render on a blank deck at 16:9 (13.333"×7.5"), the
        # modern presentation standard. Template-based decks keep their own size.
        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

    _titles = titles or {}

    for spec in report.charts:
        # Cooperative cancellation: bail out promptly between slides when signalled.
        if cancel_check is not None and cancel_check():
            raise RenderCancelled()
        # --- Resolve slot and slide ---
        slot = _resolve_slot(prs, style, spec.template_slot, report.render_mode)
        # slide_index may reference an existing slide or was just appended
        slide = prs.slides[slot.slide_index]

        # --- Demographics grid: several compact charts on one slide ---
        if is_demographics_grid(spec):
            render_demographics_grid(slide, slot, style, spec, series_by_ref, _titles)
            continue

        # --- Bullet slides (special slides + themes): render text, no series ---
        if renders_as_bullets(spec):
            render_special_slide(
                slide, slot, style, spec, heading=_titles.get(spec.question_ref, "")
            )
            continue

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

        # --- Dispatch via ChartPlugin registry (REQ-C-13) ---
        p = _plugins.plugin(spec.chart_type)
        if report.render_mode == "native":
            gf = p.native_build(ctx)
            apply_elements(gf.chart, ctx, title)
            add_n_annotation(ctx)
            add_filter_annotation(ctx)
        else:
            # Add house-style slide chrome first so chart image lands on top
            # (REQ-C-24a/h, REQ-C-25, REQ-C-27a, REQ-D-04)
            add_image_slide_chrome(ctx)
            # A chart with nothing to plot (e.g. a scale variable with no value
            # labels) degrades to a placeholder instead of crashing the builder.
            if series_is_empty(series):
                render_empty_chart(ctx)
            else:
                p.image_build(ctx)

    # Expected pictures: 1 per normal chart, 0 per bullet slide, and one per grid
    # cell that actually has a series (computed above).
    expected_pics = 0
    for spec in report.charts:
        if renders_as_bullets(spec):
            continue
        if is_demographics_grid(spec):
            expected_pics += sum(
                1
                for c in (spec.options.get("charts") or [])
                if series_by_ref.get(c.get("question_ref")) is not None
            )
        else:
            expected_pics += 1
    assert_complete(prs, report, expected_pics=expected_pics)
    assert_no_pictures_in_chart_slots(prs, report, style)
    return prs


def render_to_file(
    report: Report,
    series_by_ref: dict,
    style,
    out_path: str,
    titles: dict | None = None,
    cancel_check=None,
) -> str:
    """Render report to *out_path* and return the path (REQ-C-29a)."""
    prs = render_report(report, series_by_ref, style, titles, cancel_check=cancel_check)
    prs.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_slot(prs: Presentation, style, slot_name: str,
                  render_mode: str = "native") -> Slot:
    """Return a Slot for *slot_name*, falling back to a new blank slide.

    Tries style.slot(slot_name) first.  If that raises KeyError (slot not in
    template) or AttributeError (base StyleSpec has no slot() method), a fresh
    blank slide is appended to *prs* and a synthesised Slot is returned.

    For image mode, the slot starts lower on the slide to leave room for the
    house-style title / accent chrome added by add_image_slide_chrome.
    """
    try:
        return style.slot(slot_name)
    except (KeyError, AttributeError):
        pass

    # Fallback: add a new blank slide and synthesise a slot covering most of it
    layout = prs.slide_layouts[6]  # blank layout
    slide = prs.slides.add_slide(layout)
    slide_index = len(prs.slides) - 1

    # Slots scale to the slide so they fill it at any aspect (4:3 or 16:9): fixed
    # side margins + top chrome, the rest of the width/height is the content area.
    sw, sh = int(prs.slide_width), int(prs.slide_height)
    if render_mode == "image":
        # Leave ~1.9" at top for house-style title chrome (REQ-C-24a, REQ-D-04)
        return Slot(
            slide_index=slide_index,
            left=int(Inches(0.62)),
            top=int(Inches(1.9)),
            width=sw - int(Inches(1.24)),
            height=sh - int(Inches(2.6)),
            name=slot_name,
        )
    return Slot(
        slide_index=slide_index,
        left=int(Inches(0.8)),
        top=int(Inches(1.0)),
        width=sw - int(Inches(1.6)),
        height=sh - int(Inches(2.5)),
        name=slot_name,
    )
