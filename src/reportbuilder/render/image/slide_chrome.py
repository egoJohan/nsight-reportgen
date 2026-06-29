"""House-style slide chrome for image-mode slides (REQ-C-24/25/27a, REQ-D-04).

`add_image_slide_chrome` adds the slide-level decorations — cream background,
teal accent bar, bold title, N annotation, and methodology footer — to the
slide *before* the chart picture is placed by the image builder.  Because
shapes are z-ordered by insertion order, the chart picture (added last) lands
on top of the chrome.

The function is intentionally generic: it reads title, statistic, and base-N
from the RenderContext (driven by ChartSpec + SeriesResult) and never
hard-codes any Attendo-specific content.

Slide-text polish (R2):
- Title = full question text (ctx.title), word-wrapped to 2 lines if long.
  (REQ-D-04)
- Methodology footer bottom-left: statistic label + "· n = N"  (REQ-C-24h)
  e.g. "Osuus vastaajista (%) · n = 1001"
"""
from __future__ import annotations

from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from reportbuilder.render.base import RenderContext
from reportbuilder.render.house_style import PX_CREAM, PX_INK, PX_TEAL, PX_MUTED

_FONT = "Liberation Sans"
_IN = Inches(1)

# Statistic → Finnish methodology label (generic; no question-specific text)
_STAT_FOOTER: dict[str, str] = {
    "pct": "Osuus vastaajista (%)",
    "count": "Lukumäärä",
    "mean": "Keskiarvo",
    "median": "Mediaani",
    "sum": "Summa",
}


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
    3. Title textbox (ctx.title, bold INK, word-wrapped) — REQ-C-24a, REQ-D-04
    4. Methodology footer bottom-left (stat label + "· n = N") — REQ-C-24h
    5. N annotation textbox bottom-right (compact) — REQ-C-24h

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

    # The title block (accent bar + title + description) is gated on the
    # elements.title toggle. The live preview sets it False to render a
    # title-less PNG so the frontend can own the title region (progressive
    # "Generating title…" placeholder). The deck keeps it True (default).
    show_title = getattr(getattr(ctx.spec, "elements", None), "title", True)

    if show_title:
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

        # 3 — Title + question text  (REQ-C-24a, REQ-D-04)
        #     Headline = slide_title (AI key message) when set, else the question
        #     text. When a distinct headline is set, show the QUESTION TEXT as a
        #     secondary line so the actual question is always at the top; if no
        #     distinct headline, the secondary line is the optional description.
        question = (ctx.title or "").strip()
        slide_title = (getattr(ctx.spec, "slide_title", None) or "").strip()
        slide_description = (getattr(ctx.spec, "slide_description", None) or "").strip()
        title = slide_title or question
        if slide_title and question and slide_title != question:
            secondary = question
        else:
            secondary = slide_description
        if title:
            _textbox(
                slide,
                Inches(0.80), Inches(0.38),
                sw - Inches(1.0), Inches(0.60),
                [(title, 21, PX_INK, True)],
            )
        if secondary:
            _textbox(
                slide,
                Inches(0.80), Inches(1.02),
                sw - Inches(1.0), Inches(0.40),
                [(secondary, 13, PX_MUTED, False)],
            )

    # 4 — Methodology footer bottom-left (REQ-C-24h)
    #     Format: "<stat label> · n = <base_n>"
    base_n = ctx.series.base_n.get("Total")
    stat_label = _STAT_FOOTER.get(ctx.series.statistic, ctx.series.statistic)
    if base_n is not None:
        footer_text = f"{stat_label} · n = {base_n}"
    else:
        footer_text = stat_label
    _textbox(
        slide,
        Inches(0.62), sh - Inches(0.50),
        sw - Inches(4.0), Inches(0.40),
        [(footer_text, 9.5, PX_MUTED, False)],
        align=PP_ALIGN.LEFT,
    )
    # n is shown once, in the methodology footer above (it already reads
    # "<stat label> · n = N"). The previous separate bottom-right "n = N"
    # annotation was redundant and has been removed.
