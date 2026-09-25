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
from pptx.oxml.ns import qn

from reportbuilder.model.report import ChartSpec
from reportbuilder.render.house_style import PX_INK, PX_TEAL
from reportbuilder.render.image.slide_chrome import (
    _FONT, _furniture_px, _slide_dims, body_font, content_floor,
    draw_methodology_line, draw_template_heading, methodology_text,
    template_ground, theme_colours, TITLE_PT,
)


# Inline markdown: **bold** / __bold__ and *italic* / _italic_ (non-nested).
#
# An underscore only marks emphasis at the EDGE of a word. Bullets are ordinary
# prose that happens to contain identifiers — "asiakas_tyytyvaisyys_indeksi" —
# and treating every underscore as a marker silently deleted them and italicised
# the middle of the name: the slide did not say what the author wrote. The same
# rule every markdown renderer uses, and the reason it has it.
_MD_RE = re.compile(
    r"(\*\*|__)(.+?)\1"          # **bold** / __bold__
    r"|(\*)(.+?)\3"              # *italic*
    r"|(?<![^\W_])_(?!\s)(.+?)(?<!\s)_(?![^\W_])"   # _italic_, at word edges
)


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
        elif m.group(3):  # *italic*
            runs.append((m.group(4), False, True))
        else:  # _italic_ around a whole word
            runs.append((m.group(5), False, True))
        pos = m.end()
    if pos < len(text):
        runs.append((text[pos:], False, False))
    return runs or [(text, False, False)]


def render_special_slide(slide, slot, style, spec: ChartSpec, heading: str = "",
                         base_n: int | None = None) -> None:
    """Paint a heading + bullet list onto *slide* (house style).

    The heading is ``spec.slide_title`` when set, else the ``heading`` fallback
    (used by a themes slide, whose heading is the open-ended question text)."""
    sw, sh = _slide_dims(slide)

    # 0 — The customer's design, when there is one. An overview or conclusion
    #     slide in nSight cream between chart slides in the client's brand is
    #     the half-and-half deck this was meant to stop.
    owned = template_ground(slide, style)

    # The slide's own background/ink — house cream/ink when the template states
    # neither, the template's stated colours otherwise, ink derived from the
    # background (house_style.furniture_colors) when the template states a
    # background but no ink, so a dark, un-owned background still gets legible
    # text instead of near-black on near-black.
    theme_bg, theme_ink, _theme_accent = theme_colours(style)

    # 1 — Background (full slide), only when no template supplied one.
    if not owned:
        bg = slide.shapes.add_shape(1, 0, 0, sw, sh)
        bg.fill.solid()
        bg.fill.fore_color.rgb = theme_bg
        bg.line.fill.background()
        bg.shadow.inherit = False

    # 2 — Heading text (compute first so the accent bar can match its height).
    heading_text = (getattr(spec, "slide_title", None) or heading or "").strip()

    # 3 — Teal accent bar (top-left), sized to the heading's actual line height so
    #     it doesn't tower over a short one-line title (capped at the box height).
    #     House furniture, so a templated slide does without: what sits beside a
    #     title there is the customer's business.
    if not owned:
        _hlines = _heading_line_count(heading_text, sw) if heading_text else 1
        _line_h = Pt(_heading_size(heading_text or "x") * 1.25)
        bar_h = min(int(Inches(0.92)), _hlines * int(_line_h) + int(Inches(0.06)))
        acc = slide.shapes.add_shape(
            1, Inches(0.55), Inches(0.42), Inches(0.10), bar_h
        )
        acc.fill.solid()
        # The TEMPLATE's accent, like the bullet glyphs below already use — this
        # was PX_TEAL, so a branded deck carried the client's colour on its
        # chart slides and nSight's green beside its section headings.
        acc.fill.fore_color.rgb = _theme_accent
        acc.line.fill.background()
        acc.shadow.inherit = False

    # 4 — Heading (slide_title, else the fallback — e.g. the question text).
    #     In the template's own title placeholder or its title style when it has
    #     one; the house box otherwise.
    title_bottom = draw_template_heading(slide, style, heading_text) if owned else 0
    if heading_text and not title_bottom:
        _heading_box(slide, sw, heading_text, theme_ink)

    # 4 — Bullet list. Each raw line is a markdown bullet: leading whitespace sets
    # the nesting level and a leading -,*,+,• marker is stripped. Tolerate a bare
    # string (don't iterate it into characters).
    raw = spec.options.get("bullets") or []
    if isinstance(raw, str):
        raw = [raw]
    # Drop degenerate "odd" bullets — empties, markdown code-fence lines
    # ("```question:yes_no"), or lines that are only markers / punctuation with no
    # real letters (defence in depth, in case options carry junk from a saved report).
    parsed: list[tuple[int, str]] = []
    for item in raw:
        for line in str(item).split("\n"):
            level, text = _bullet_level(line)
            if (text
                    and not text.startswith("```")
                    and not text.startswith("~~~")
                    and re.search(r"[^\s\-•*_:.,–—]", text)):
                parsed.append((level, text))
    # 5 — Key themes report their N like every chart slide: the respondents who
    #     wrote an answer, in the same bottom-left place, same look, same "N"
    #     toggle and footer note ("Key themes kysymystyypissä ei näy n-lukua",
    #     2026-09-25). The bullets then stop at the content's bottom, where the
    #     N line starts. Special slides (overview, conclusions) have no question
    #     and no N, and are laid out exactly as before.
    n_text = ""
    if getattr(spec, "chart_type", "") == "themes":
        n_text = methodology_text(spec, base_n, getattr(spec, "statistic", ""),
                                  stat_fallback=False)
    floor = content_floor(slide, sw, sh)
    if n_text:
        floor = min(floor, int(slot.top) + int(slot.height))
    if parsed:
        top = title_bottom + int(Inches(0.28)) if title_bottom else int(Inches(1.55))
        _bullet_box(slide, sw, sh, parsed, top=top, floor=floor,
                    accent=_theme_accent, ink=theme_ink, font=body_font(style) or _FONT)
    if n_text:
        draw_methodology_line(slide, slot, style, n_text, _furniture_px(style)[1])


def _heading_size(text: str) -> int:
    """The special-slide heading is a slide title just like a chart's key message,
    so it uses the one shared fixed title size (slide_chrome.TITLE_PT)."""
    return TITLE_PT


def _heading_line_count(text: str, sw: int) -> int:
    """Approximate how many lines the heading wraps to in its box (width sw - 1.0"),
    so the accent bar can match the title's actual height instead of a fixed box."""
    if not text:
        return 1
    size = _heading_size(text)
    box_pt = (sw / 914400 - 1.0) * 72              # heading box width in points
    chars_per_line = max(1, int(box_pt / (size * 0.55)))  # ~0.55·size pt per avg char
    lines = 0
    for seg in text.split("\n"):
        lines += max(1, -(-len(seg) // chars_per_line))   # ceil-divide
    return max(1, lines)


def _heading_box(slide, sw, text: str, ink=PX_INK) -> None:
    tb = slide.shapes.add_textbox(
        Inches(0.80), Inches(0.42), sw - Inches(1.0), Inches(0.92)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    r = p.add_run()
    r.text = text
    r.font.size = Pt(_heading_size(text))
    r.font.bold = True
    r.font.color.rgb = ink
    r.font.name = _FONT


def _bullet_level(raw: str) -> tuple[int, str]:
    """(nesting level, text) for one raw markdown bullet line.

    Leading whitespace sets the level — a tab or two spaces per level, capped at 3 —
    and a leading list marker (-, *, +, •, ·, ◦) is stripped. So "  * Foo" → (1, "Foo")
    and "- Bar" → (0, "Bar"). A plain line (no marker) is a level-0 bullet."""
    expanded = raw.replace("\t", "  ")
    body = expanded.lstrip(" ")
    lead = len(expanded) - len(body)
    level = min(lead // 2, 3)
    text = re.sub(r"^[-*+•·◦]\s+", "", body).strip()
    return level, text


# Per-level bullet glyph + body font size (deeper levels are smaller / softer).
_LEVEL_GLYPH = {0: "•", 1: "–", 2: "·", 3: "·"}
_LEVEL_PT = {0: 16, 1: 14, 2: 13, 3: 13}


#: Hanging indent, and how far each nesting level steps right. Module level so
#: the fitter measures against the SAME usable width the drawing code uses.
_HANG = Inches(0.30)
_STEP = Inches(0.34)
#: Line height as a multiple of the type size, and the gap after a paragraph.
_BULLET_LINE_SPACING = 1.22
_BULLET_SPACE_AFTER_PT = {0: 10, 1: 4, 2: 4, 3: 4}
#: Below this the text is too small to be worth reading; an author is better
#: served by visible overflow than by a slide nobody can read.
_BULLET_MIN_PT = 9.0


def _bullet_plain(text: str) -> str:
    """The bullet's text without its markdown, for measuring."""
    return "".join(seg for seg, _b, _i in _md_runs(text))


def bullets_height(bullets, width_emu: int, font: str, scale: float) -> int:
    """How tall this bullet list really is at *scale*, measured with the host's
    own font — the same measurement the title fitter uses, so the two agree."""
    from types import SimpleNamespace

    from reportbuilder.render.image.slide_chrome import measured_line_count

    total = 0
    for level, text in bullets:
        pt = _LEVEL_PT.get(level, 13) * scale
        # The hanging indent and the level's step both eat usable width.
        usable = int(width_emu) - int(_HANG) - level * int(_STEP)
        st = SimpleNamespace(font=font, caps=False, bold=False,
                             line_spacing=_BULLET_LINE_SPACING)
        lines = measured_line_count(_bullet_plain(text), max(usable, 1), pt, st)
        total += int(lines * Pt(pt * _BULLET_LINE_SPACING))
        total += int(Pt(_BULLET_SPACE_AFTER_PT.get(level, 4)))
    return total


def fit_bullet_scale(bullets, width_emu: int, height_emu: int,
                     font: str) -> float:
    """The factor to draw this list at so it fits its box.

    1.0 whenever the list already fits, which is the common case — a themes
    slide of four short points never moves off its own type size. Otherwise the
    size steps down until the measured text fits, stopping at `_BULLET_MIN_PT`.

    Taffel's five-theme slide overflowed the slide's bottom edge: the fifth
    theme was cut off mid-sentence and the footer was pushed off entirely, with
    nothing on the slide saying that text was missing. The box height and the
    type sizes were both fixed and nothing measured the text against them.
    """
    if not bullets or width_emu <= 0 or height_emu <= 0:
        return 1.0
    biggest = max(_LEVEL_PT.get(lvl, 13) for lvl, _t in bullets)
    floor = _BULLET_MIN_PT / biggest if biggest else 1.0
    scale = 1.0
    while scale > floor:
        if bullets_height(bullets, width_emu, font, scale) <= height_emu:
            return scale
        scale -= 0.04
    return max(floor, round(floor, 4))


def _bullet_box(slide, sw, sh, bullets: list[tuple[int, str]],
                top: int | None = None, floor: int | None = None,
                accent=PX_TEAL, ink=PX_INK, font: str = _FONT) -> None:
    """The bullet list. *top* is the heading's bottom on a templated slide, where
    the customer's title is not where ours would have been; *floor* is the top of
    whatever their design puts at the foot of the slide. Colours and typeface are
    the template's when it has an opinion, so a conclusion slide does not arrive
    in nSight teal in the middle of a client deck."""
    top = int(Inches(1.55)) if top is None else int(top)
    bottom = (sh - int(Inches(0.55))) if floor is None else (floor - int(Inches(0.25)))
    tb = slide.shapes.add_textbox(
        Inches(0.85), top, sw - Inches(1.6), max(int(Inches(1.0)), bottom - top)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    # Hanging indent: the bullet glyph sits at the paragraph's left margin and
    # wrapped lines align EXACTLY under the first line's text. Nesting shifts the
    # whole paragraph right by _STEP per level; marL is the text start (offset by
    # level), indent = -_HANG pulls the glyph back, and a left TAB STOP at marL
    # snaps the first line's text to the same x as its wrapped continuation lines.
    scale = fit_bullet_scale(bullets, int(sw - Inches(1.6)),
                             max(int(Inches(1.0)), bottom - top), font)
    for i, (level, text) in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(_BULLET_SPACE_AFTER_PT.get(level, 4))
        pPr = p._p.get_or_add_pPr()
        mar_l = int(_HANG) + level * int(_STEP)
        pPr.set("marL", str(mar_l))
        pPr.set("indent", str(-int(_HANG)))
        tab_lst = pPr.makeelement(qn("a:tabLst"), {})
        tab_lst.append(pPr.makeelement(qn("a:tab"), {"pos": str(mar_l), "algn": "l"}))
        pPr.append(tab_lst)
        pt = _LEVEL_PT.get(level, 13) * scale
        # Teal bullet glyph + tab (snaps body text to the marL tab stop).
        dot = p.add_run()
        dot.text = f"{_LEVEL_GLYPH.get(level, '·')}\t"
        dot.font.size = Pt(pt)
        dot.font.bold = True
        dot.font.color.rgb = accent
        dot.font.name = font
        for seg, bold, italic in _md_runs(text):
            body = p.add_run()
            body.text = seg
            body.font.size = Pt(pt)
            body.font.bold = bold
            body.font.italic = italic
            body.font.color.rgb = ink
            # The template's face, as the glyph beside it already used. The
            # bullet said "typeface is the template's" and then set the house
            # font here, so a customer's deck drew the dot in their face and the
            # sentence next to it in ours.
            body.font.name = font
