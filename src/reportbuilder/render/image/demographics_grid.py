"""Render a demographics grid slide: a heading plus several compact charts in a
2-column grid, each labelled with its question.

The grid spec carries ``options["charts"] = [{"question_ref", "chart_type"}, …]``.
Each cell reuses the normal chart image-builder, but rendered into a small slot
(the cell rectangle) so multiple demographic charts fit one slide. Returns the
number of charts placed so completeness counting stays exact.
"""
from __future__ import annotations

import dataclasses

from pptx.util import Inches
from pptx.enum.text import PP_ALIGN

from reportbuilder.render.base import RenderContext, Slot
from reportbuilder.render.house_style import PX_CREAM, PX_INK, PX_TEAL
from reportbuilder.render.image.slide_chrome import (
    _slide_dims, _textbox, body_font, content_floor, draw_template_heading,
    template_ground, theme_colours,
)
import reportbuilder.render.plugins as _plugins

_COLS = 2


def render_demographics_grid(slide, slot, style, spec, series_by_ref, titles) -> int:
    """Paint the heading + grid of mini-charts. Returns the count of charts placed."""
    sw, sh = _slide_dims(slide)

    # The customer's design when the template supplies one, house style when it
    # does not — the same rule as every other kind of slide.
    owned = template_ground(slide, style)
    if not owned:
        bg = slide.shapes.add_shape(1, 0, 0, sw, sh)
        bg.fill.solid(); bg.fill.fore_color.rgb = PX_CREAM
        bg.line.fill.background(); bg.shadow.inherit = False
        acc = slide.shapes.add_shape(1, Inches(0.55), Inches(0.40), Inches(0.10), Inches(0.62))
        acc.fill.solid(); acc.fill.fore_color.rgb = PX_TEAL
        acc.line.fill.background(); acc.shadow.inherit = False
    _bg, ink, _accent = theme_colours(style)
    face = body_font(style)
    heading = (getattr(spec, "slide_title", None) or "Vastaajat").strip()
    title_bottom = draw_template_heading(slide, style, heading) if owned else 0
    if not title_bottom:
        _textbox(slide, Inches(0.80), Inches(0.34), sw - Inches(1.0), Inches(0.55),
                 [(heading, 22, ink, True)], font=face)

    charts = [
        c for c in (spec.options.get("charts") or [])
        if series_by_ref.get(c.get("question_ref")) is not None
    ]
    if not charts:
        return 0

    # Grid area below the heading, and above whatever the template puts at the
    # foot of the slide.
    area_l = Inches(0.55)
    area_t = title_bottom + int(Inches(0.20)) if title_bottom else Inches(1.15)
    area_w = sw - Inches(1.1)
    area_h = max(int(Inches(1.0)),
                 content_floor(slide, sw, sh) - int(Inches(0.30)) - area_t)
    cols = _COLS if len(charts) > 1 else 1
    rows = -(-len(charts) // cols)  # ceil
    cell_w, cell_h = area_w // cols, area_h // rows
    pad = Inches(0.14)
    title_h = Inches(0.32)

    placed = 0
    for i, c in enumerate(charts):
        ref = c["question_ref"]
        ctype = c.get("chart_type") or "vertical_bar"
        r, col = divmod(i, cols)
        cx, cy = area_l + col * cell_w, area_t + r * cell_h
        # Cell title (the question).
        _textbox(slide, int(cx + pad), int(cy), int(cell_w - 2 * pad), int(title_h),
                 [((titles.get(ref) or ref), 11, ink, True)], align=PP_ALIGN.LEFT,
                 font=face)
        # Chart placed in the cell area below the title.
        cell_slot = Slot(
            slide_index=slot.slide_index,
            left=int(cx + pad), top=int(cy + title_h),
            width=int(cell_w - 2 * pad), height=int(cell_h - title_h - pad),
            name="cell",
        )
        cell_spec = dataclasses.replace(spec, chart_type=ctype, options={})
        ctx = RenderContext(
            slide=slide, slot=cell_slot, style=style, spec=cell_spec,
            series=series_by_ref[ref], fmt=spec.number_format, title="",
        )
        try:
            _plugins.plugin(ctype).image_build(ctx)
            placed += 1
        except Exception:
            pass
    return placed
