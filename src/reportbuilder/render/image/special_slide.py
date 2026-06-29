"""Render a "special" (non-chart) slide: Overview / Conclusion / Demographics.

Special slides carry no data series — their content is a heading (``slide_title``)
plus a list of bullet strings in ``spec.options["bullets"]``. They are drawn as
plain PowerPoint textboxes (house style: cream background, teal accent bar, bold
ink heading, muted bullet list), entirely independent of the chart pipeline —
no RenderContext, no SeriesResult, no plugin dispatch.
"""
from __future__ import annotations

from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from reportbuilder.model.report import ChartSpec
from reportbuilder.render.house_style import PX_CREAM, PX_INK, PX_TEAL
from reportbuilder.render.image.slide_chrome import _FONT, _slide_dims


def render_special_slide(slide, slot, style, spec: ChartSpec) -> None:
    """Paint a heading + bullet list onto *slide* (house style)."""
    sw, sh = _slide_dims(slide)

    # 1 — Cream background (full slide)
    bg = slide.shapes.add_shape(1, 0, 0, sw, sh)
    bg.fill.solid()
    bg.fill.fore_color.rgb = PX_CREAM
    bg.line.fill.background()
    bg.shadow.inherit = False

    # 2 — Teal accent bar (top-left)
    acc = slide.shapes.add_shape(
        1, Inches(0.55), Inches(0.42), Inches(0.10), Inches(0.92)
    )
    acc.fill.solid()
    acc.fill.fore_color.rgb = PX_TEAL
    acc.line.fill.background()
    acc.shadow.inherit = False

    # 3 — Heading (slide_title)
    heading = (getattr(spec, "slide_title", None) or "").strip()
    if heading:
        _heading_box(slide, sw, heading)

    # 4 — Bullet list. Tolerate a bare string (don't iterate it into characters).
    raw = spec.options.get("bullets") or []
    if isinstance(raw, str):
        raw = [raw]
    bullets = [str(b).strip() for b in raw if str(b).strip()]
    if bullets:
        _bullet_box(slide, sw, sh, bullets)


def _heading_box(slide, sw, text: str) -> None:
    tb = slide.shapes.add_textbox(
        Inches(0.80), Inches(0.42), sw - Inches(1.0), Inches(0.80)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    r = p.add_run()
    r.text = text
    r.font.size = Pt(26)
    r.font.bold = True
    r.font.color.rgb = PX_INK
    r.font.name = _FONT


def _bullet_box(slide, sw, sh, bullets: list[str]) -> None:
    tb = slide.shapes.add_textbox(
        Inches(0.85), Inches(1.55), sw - Inches(1.6), sh - Inches(2.1)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, text in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(10)
        # Teal bullet glyph, then the ink body text.
        dot = p.add_run()
        dot.text = "•  "
        dot.font.size = Pt(16)
        dot.font.bold = True
        dot.font.color.rgb = PX_TEAL
        dot.font.name = _FONT
        body = p.add_run()
        body.text = text
        body.font.size = Pt(16)
        body.font.color.rgb = PX_INK
        body.font.name = _FONT
