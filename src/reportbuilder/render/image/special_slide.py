"""Render a "special" (non-chart) slide: Overview / Conclusion / Demographics.

Special slides carry no data series — their content is a heading (``slide_title``)
plus a list of bullet strings in ``spec.options["bullets"]``. They are drawn as
plain PowerPoint textboxes (house style: cream background, teal accent bar, bold
ink heading, muted bullet list), entirely independent of the chart pipeline —
no RenderContext, no SeriesResult, no plugin dispatch.
"""
from __future__ import annotations

import re

from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from reportbuilder.model.report import ChartSpec
from reportbuilder.render.house_style import PX_CREAM, PX_INK, PX_TEAL
from reportbuilder.render.image.slide_chrome import _FONT, _slide_dims


# Inline markdown: **bold** / __bold__ and *italic* / _italic_ (non-nested).
_MD_RE = re.compile(r"(\*\*|__)(.+?)\1|(\*|_)(.+?)\3")


def _md_runs(text: str) -> list[tuple[str, bool, bool]]:
    """Split inline markdown into (text, bold, italic) runs so slide bullets can
    render emphasis. Returns the plain text as a single run when no markers."""
    runs: list[tuple[str, bool, bool]] = []
    pos = 0
    for m in _MD_RE.finditer(text):
        if m.start() > pos:
            runs.append((text[pos:m.start()], False, False))
        if m.group(1):  # **bold** / __bold__
            runs.append((m.group(2), True, False))
        else:  # *italic* / _italic_
            runs.append((m.group(4), False, True))
        pos = m.end()
    if pos < len(text):
        runs.append((text[pos:], False, False))
    return runs or [(text, False, False)]


def render_special_slide(slide, slot, style, spec: ChartSpec, heading: str = "") -> None:
    """Paint a heading + bullet list onto *slide* (house style).

    The heading is ``spec.slide_title`` when set, else the ``heading`` fallback
    (used by a themes slide, whose heading is the open-ended question text)."""
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

    # 3 — Heading (slide_title, else the fallback — e.g. the question text)
    heading_text = (getattr(spec, "slide_title", None) or heading or "").strip()
    if heading_text:
        _heading_box(slide, sw, heading_text)

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
    # Hanging indent: the bullet glyph sits at the left edge and wrapped lines
    # align under the FIRST line's text (not under the bullet). marL = text
    # start; indent = -marL pulls the bullet back to the margin.
    _HANG = Inches(0.32)
    for i, text in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(10)
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(int(_HANG)))
        pPr.set("indent", str(-int(_HANG)))
        # Teal bullet glyph, then the ink body text (inline markdown → runs).
        dot = p.add_run()
        dot.text = "•  "
        dot.font.size = Pt(16)
        dot.font.bold = True
        dot.font.color.rgb = PX_TEAL
        dot.font.name = _FONT
        for seg, bold, italic in _md_runs(text):
            body = p.add_run()
            body.text = seg
            body.font.size = Pt(16)
            body.font.bold = bold
            body.font.italic = italic
            body.font.color.rgb = PX_INK
            body.font.name = _FONT
