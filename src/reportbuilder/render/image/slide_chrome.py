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


def _rgb(hex6: str):
    """'122D49' -> RGBColor. Empty/short input returns None."""
    from pptx.dml.color import RGBColor
    if not hex6 or len(hex6) != 6:
        return None
    try:
        return RGBColor(int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16))
    except ValueError:
        return None


def _theme_colours(ctx):
    """(background, ink, accent) for this slide, preferring the template's own.

    A deck built on the client's template should not carry nSight's cream ground
    and teal accent bar. Anything the template does not state falls back to the
    house value, so a template with a partial theme still renders.
    """
    style = getattr(ctx, "style", None)
    bg = _rgb(getattr(style, "background", "") or "") or PX_CREAM
    ink = _rgb(getattr(style, "ink", "") or "") or PX_INK
    accent = PX_TEAL
    try:
        if getattr(style, "chart_layout_index", None) is not None:
            accent = _rgb(style.color_for(0)) or PX_TEAL
    except Exception:  # noqa: BLE001 — styling must not break a render
        pass
    return bg, ink, accent
from reportbuilder.stats.engine import scale_endpoint_gloss

_FONT = "Liberation Sans"
# One fixed title size for EVERY slide (chart + special) so titles never vary in
# size between slides. (Shared by special_slide's heading.)
TITLE_PT = 18
_IN = Inches(1)

_STACKED_BAR_TYPES = frozenset({"stacked_horizontal_bar", "stacked_vertical_bar"})


# `scale_endpoint_gloss` lives in stats.engine so the questions API can offer the SAME
# default text to the frontend's Subtitle box (the subtitle owns the whole line).

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
        prs = slide.part.package.presentation_part.presentation
        return int(prs.slide_width), int(prs.slide_height)
    except Exception:
        # fallback: 13.333" × 7.5" (the deck default — 16:9 widescreen)
        return int(Inches(13.333)), int(Inches(7.5))


def wrapped_line_count(text: str, box_width_emu: int, size_pt: int) -> int:
    """Approximate how many lines *text* wraps to in a box *box_width_emu* wide at
    font *size_pt* (honours explicit '\\n'). Used to size the accent bar to the
    title/heading's actual height instead of a fixed box."""
    if not text:
        return 1
    box_pt = box_width_emu / 914400 * 72
    chars_per_line = max(1, int(box_pt / (size_pt * 0.55)))  # ~0.55·size pt per avg char
    lines = 0
    for seg in text.split("\n"):
        lines += max(1, -(-len(seg) // chars_per_line))       # ceil-divide
    return max(1, lines)


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


def _from_template(ctx) -> bool:
    """True when this slide was built from the template's OWN chart layout.

    Then the layout already carries the customer's design — background, brand
    furniture, title styling — and anything we paint on top hides what they
    asked us to use. nSight contributes text and the chart, nothing else.
    """
    return getattr(ctx.style, "chart_layout_index", None) is not None


def _fill_title_placeholder(slide, title: str) -> bool:
    """Put *title* in the layout's title placeholder. False if there isn't one.

    Only the TEXT is set: size, font, colour and position stay inherited, which
    is the whole point of using the customer's layout. An unused placeholder is
    removed so PowerPoint does not show its "Click to add title" prompt.
    """
    try:
        ph = slide.shapes.title
    except (AttributeError, KeyError):
        return False
    if ph is None:
        return False
    if not title:
        ph._element.getparent().remove(ph._element)
        return True
    tf = ph.text_frame
    tf.text = title
    return True


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

    _bg, _ink, _accent = _theme_colours(ctx)
    templated = _from_template(ctx)

    # 1 — Cream background. Only when NO template laid this slide out: a
    #     full-slide rectangle would cover the customer's own background,
    #     brand furniture and everything else their layout provides.
    if not templated:
        bg = slide.shapes.add_shape(1, 0, 0, sw, sh)
        bg.fill.solid()
        bg.fill.fore_color.rgb = _bg
        bg.line.fill.background()
        bg.shadow.inherit = False

    # The title block (accent bar + title + description) is gated on the
    # elements.title toggle. The live preview sets it False to render a
    # title-less PNG so the frontend can own the title region (progressive
    # "Generating title…" placeholder). The deck keeps it True (default).
    show_title = getattr(getattr(ctx.spec, "elements", None), "title", True)

    if show_title:
        # 2 — Title (top) + question subtitle (just above the chart)
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
        # Subtitle (the line just above the chart) is the editable slide_description; when
        # blank it defaults to the QUESTION — but only when the title is a DISTINCT headline
        # (otherwise the title already IS the question, so no redundant subtitle).
        has_distinct_title = bool(slide_title) and slide_title != question
        secondary = slide_description or (question if has_distinct_title else "")
        # On a STACKED bar the scale sits in the legend as bare numbers; move the endpoint
        # wording (1 = … · 7 = …) into the subtitle so the meaning isn't lost. (customer)
        # Only as the DEFAULT: an authored slide_description owns the whole line, so the
        # author can reword or drop a gloss that fits only one battery member (the levels
        # come from the first member with a parseable scale). The frontend prefills its
        # Subtitle box with this same default, so what you edit is what renders.
        if not slide_description and getattr(ctx.spec, "chart_type", "") in _STACKED_BAR_TYPES:
            gloss = scale_endpoint_gloss(ctx.series.categories)
            if gloss:
                secondary = f"{secondary}   {gloss}" if secondary else gloss
        # One fixed title size for every slide (no length-based stepping).
        t_size = TITLE_PT

        # 3 — Teal accent bar. House furniture, so it is skipped on a templated
        #     slide: the customer's layout decides what sits beside a title.
        # Teal accent bar (thin vertical stripe, top-left), sized to the TITLE's
        #     actual height (its wrapped line count) so it doesn't tower over a short
        #     one-line headline. Capped at the title box height.
        if title:
            _n = wrapped_line_count(title, sw - Inches(1.0), t_size)
            bar_h = min(int(Inches(1.30)), _n * int(Pt(t_size * 1.25)) + int(Inches(0.06)))
        else:
            bar_h = int(Inches(0.30))
        if not templated:
            acc = slide.shapes.add_shape(
                1, Inches(0.55), Inches(0.42), Inches(0.10), bar_h
            )
            acc.fill.solid()
            acc.fill.fore_color.rgb = _accent
            acc.line.fill.background()
            acc.shadow.inherit = False

        # 4 — Title. On a templated slide it goes into the layout's own title
        #     placeholder, so it inherits the customer's font, size, colour and
        #     position. Only a template without a title placeholder falls
        #     through to a box of our own.
        placed = _fill_title_placeholder(slide, title) if templated else False
        if title and not placed:
            # Tall, TOP-anchored box so the title can span up to ~4 lines (customers'
            # headlines are often 3) and honour manual line breaks ("\n") instead of
            # being clipped at 2. A short title still sits at the top (empty space
            # below is invisible); a long one grows DOWN toward the chart — if it meets
            # the question subtitle the author shortens the text.
            _textbox(
                slide,
                Inches(0.80), Inches(0.42),
                sw - Inches(1.0), Inches(1.30),
                [(title, t_size, _ink, True)],
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
            # On a templated slide the title placeholder owns the top of the
            # slide and we do not know how tall it is, so the subtitle hangs off
            # the CHART instead: its box bottom sits just above the plot.
            if templated:
                sub_h = int(Inches(0.62))
                sub_top = max(0, int(ctx.slot.top) - sub_h)
                sub_left, sub_w = int(ctx.slot.left), int(ctx.slot.width)
            else:
                sub_h, sub_top = int(Inches(0.92)), int(Inches(0.92))
                sub_left, sub_w = int(Inches(0.80)), int(sw - Inches(1.0))
            _textbox(
                slide,
                sub_left, sub_top, sub_w, sub_h,
                [(secondary, s_size, PX_MUTED, False)],
                anchor=MSO_ANCHOR.BOTTOM,
            )

    # 4 — Methodology footer bottom-left (REQ-C-24h)
    #     Auto format: a simple "N = <base_n>". An author can override it per slide via
    #     spec.footer_note; "{n}" expands to the base and "{stat}" to the statistic label
    #     (e.g. "{stat} · n = {n}" restores the verbose form), so "N = {n}" keeps the
    #     count live.
    base_n = ctx.series.base_n.get("Total")
    stat_label = _STAT_FOOTER.get(ctx.series.statistic, ctx.series.statistic)
    override = (getattr(ctx.spec, "footer_note", None) or "").strip()
    if override:
        footer_text = override.replace("{n}", str(base_n if base_n is not None else "")) \
                              .replace("{stat}", stat_label)
    elif base_n is not None:
        footer_text = f"N = {base_n}"
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
