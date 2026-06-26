"""House-style slide chrome for image-mode slides (REQ-C-24/25/27a, REQ-D-04).

`add_image_slide_chrome` adds the slide-level decorations — cream background,
teal accent bar, bold title, and N annotation — to the slide *before* the chart
picture is placed by the image builder.  Because shapes are z-ordered by
insertion order, the chart picture (added last) lands on top of the chrome.

The function is intentionally generic: it reads title and base-N from the
RenderContext (driven by ChartSpec + SeriesResult) and never hard-codes any
Attendo-specific content.
"""
from __future__ import annotations

from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from reportbuilder.render.base import RenderContext
from reportbuilder.render.house_style import PX_CREAM, PX_INK, PX_TEAL, PX_MUTED

_FONT = "Liberation Sans"
_IN = Inches(1)


def _slide_dims(slide) -> tuple[int, int]:
    """Return (slide_width_emu, slide_height_emu) from the slide's parent presentation."""
    try:
        prs = slide.part.presentation
        return int(prs.slide_width), int(prs.slide_height)
    except Exception:
        # fallback: 10" × 7.5" (standard python-pptx default)
        return int(Inches(10)), int(Inches(7.5))


def _textbox(slide, l, t, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """Add a multi-run textbox.  `runs` is a list of (text, pt_size, rgb, bold) tuples."""
    tb = slide.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    first = True
    for txt, sz, col, bold in runs:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = align
        r = p.add_run()
        r.text = txt
        r.font.size = Pt(sz)
        r.font.bold = bold
        r.font.color.rgb = col
        r.font.name = _FONT
    return tb


def add_image_slide_chrome(ctx: RenderContext) -> None:
    """Decorate an image-mode slide with house-style chrome.

    Adds (in z-order, bottom → top):
    1. Cream background rectangle (full slide)
    2. Teal vertical accent bar (top-left)
    3. Title textbox (ctx.title, bold INK)  — REQ-C-24a, REQ-D-04
    4. N annotation textbox (base_n["Total"]) — REQ-C-24h

    Call this *before* the image builder so the chart picture lands on top.
    """
    slide = ctx.slide
    sw, sh = _slide_dims(slide)

    # 1 — Cream background (full slide, added first → sits at bottom of z-order)
    bg = slide.shapes.add_shape(1, 0, 0, sw, sh)
    bg.fill.solid()
    bg.fill.fore_color.rgb = PX_CREAM
    bg.line.fill.background()
    bg.shadow.inherit = False

    # 2 — Teal accent bar (thin vertical stripe, top-left)
    acc = slide.shapes.add_shape(
        1,
        Inches(0.55), Inches(0.42),
        Inches(0.10), Inches(0.92),
    )
    acc.fill.solid()
    acc.fill.fore_color.rgb = PX_TEAL
    acc.line.fill.background()
    acc.shadow.inherit = False

    # 3 — Title / question-text textbox  (REQ-C-24a, REQ-D-04)
    title = ctx.title or ""
    if title:
        _textbox(
            slide,
            Inches(0.80), Inches(0.38),
            sw - Inches(1.0), Inches(1.4),
            [(title, 21, PX_INK, True)],
        )

    # 4 — N annotation (bottom-right)  (REQ-C-24h)
    base_n = ctx.series.base_n.get("Total")
    if base_n is not None:
        _textbox(
            slide,
            sw - Inches(3.2), sh - Inches(0.50),
            Inches(3.0), Inches(0.40),
            [(f"n = {base_n}", 9.5, PX_MUTED, True)],
            align=PP_ALIGN.RIGHT,
        )
