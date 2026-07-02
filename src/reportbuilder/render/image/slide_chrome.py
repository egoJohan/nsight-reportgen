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

        # 3 — Title (top) + question subtitle (just above the chart)
        #     The top area is dedicated to the TITLE (AI key message when set,
        #     else the question). When a distinct headline is set, the actual
        #     QUESTION is a separate subtitle anchored to the BOTTOM of the header
        #     band — so the gap between the question and the chart stays constant
        #     no matter how many lines the question wraps to. It uses a lighter
        #     (non-bold) weight than the title. (REQ-C-24a, REQ-D-04)
        question = (ctx.title or "").strip()
        slide_title = (getattr(ctx.spec, "slide_title", None) or "").strip()
        slide_description = (getattr(ctx.spec, "slide_description", None) or "").strip()
        title = slide_title or question
        if slide_title and question and slide_title != question:
            secondary = question
        else:
            secondary = slide_description
        if title:
            # Title font steps down for a long (2-line) key message so it doesn't
            # grow to 3 lines and overrun the question subtitle below it.
            t_size = 21 if len(title) <= 60 else (18 if len(title) <= 110 else 16)
            _textbox(
                slide,
                Inches(0.80), Inches(0.34),
                sw - Inches(1.0), Inches(0.56),
                [(title, t_size, PX_INK, True)],
            )
        if secondary:
            # The question subtitle binds to the CHART: its box bottom sits just
            # above the chart (~1.84") and BOTTOM anchor makes multi-line questions
            # grow UPWARD toward the title. Its font steps down with length so a
            # long question always fits the box and is NEVER clipped at the top
            # (a bottom-anchored box clips overflow above it), while staying as
            # large as possible.
            n = len(secondary)
            s_size = 15 if n <= 110 else (13 if n <= 180 else (12 if n <= 260 else 11))
            _textbox(
                slide,
                Inches(0.80), Inches(0.92),
                sw - Inches(1.0), Inches(0.92),
                [(secondary, s_size, PX_MUTED, False)],
                anchor=MSO_ANCHOR.BOTTOM,
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
    # Scale endpoint legend for a partially-labelled numeric scale (e.g. "1 = täysin
    # eri mieltä · 7 = täysin samaa mieltä") — a small caption just above the footer,
    # so the numeric axis (1..7) reads cleanly and the text isn't lost. (REQ-C-24c)
    caption = getattr(ctx.series, "caption", None)
    if caption:
        # Right-aligned on the footer row (below the plot) so it never overlaps the
        # chart's x-axis; shares the line with the left-aligned methodology footer.
        _textbox(
            slide,
            sw - Inches(6.4), sh - Inches(0.50),
            Inches(6.0), Inches(0.40),
            [(caption, 9.5, PX_MUTED, False)],
            align=PP_ALIGN.RIGHT,
        )
    # n is shown once, in the methodology footer above (it already reads
    # "<stat label> · n = N"). The previous separate bottom-right "n = N"
    # annotation was redundant and has been removed.
