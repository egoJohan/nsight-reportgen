"""A chart preview without running LibreOffice per chart.

The Design page asks for one PNG per chart, and each one used to be a whole
miniature deck: build a one-slide .pptx, hand it to LibreOffice, get a PDF back,
rasterize it. Measured on a real report that is 4.4s a chart, of which 3.3s is
LibreOffice — and the page asks for sixty of them.

But every one of those sixty conversions renders the SAME thing behind the
chart: the customer's ground, their band, their logo. Only the chart on top
changes. So LibreOffice runs once per template to produce that ground, the image
is cached, and each preview is the chart composited onto a copy of it.

LibreOffice stays the authority on what a customer's template looks like — this
is the same conversion the deck goes through, not a re-drawing of their design —
it just stops being paid sixty times over.

Falls back to the caller's slow path on anything unexpected: a preview that is
wrong is worse than a preview that is slow.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.preview import rasterize_pages

log = logging.getLogger(__name__)

EMU_PER_INCH = 914400
# PowerPoint's own text-frame insets, applied when a shape does not state its own.
_DEFAULT_LR_INSET = 91440      # 0.1in
_DEFAULT_TB_INSET = 45720      # 0.05in
_CACHE = Path(tempfile.gettempdir()) / "nsight-preview-ground"


def _key(style, dpi: int) -> str:
    """Identity of a ground: which template file, as it is right now, at what dpi."""
    source = str(getattr(style, "spec_source", "") or "generic")
    stamp = ""
    try:
        stamp = str(os.path.getmtime(source))
    except OSError:
        pass
    raw = f"{source}|{stamp}|{dpi}|{getattr(style, 'slide_width', 0)}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def ground_image(style, dpi: int = 110):
    """The customer's empty slide, rendered once and cached. None if it cannot be.

    "Empty" means built exactly as a chart slide is — from their layout, or with
    their harvested furniture redrawn — and then left without a chart or any of
    our text.
    """
    _CACHE.mkdir(parents=True, exist_ok=True)
    cached = _CACHE / f"{_key(style, dpi)}.png"
    if cached.exists():
        try:
            return Image.open(cached).convert("RGB")
        except OSError:
            cached.unlink(missing_ok=True)

    from pptx import Presentation
    from pptx.util import Inches

    from reportbuilder.render.deck import _resolve_slot, _strip_slides
    from reportbuilder.render.image.slide_chrome import template_ground

    source = getattr(style, "spec_source", None)
    work = Path(tempfile.mkdtemp(prefix="nsight-ground-"))
    try:
        prs = None
        if source and source not in ("generic", "attendo-interim-proxy"):
            try:
                prs = Presentation(source)
                _strip_slides(prs)
            except Exception:  # noqa: BLE001 — unreadable template: no fast path
                prs = None
        if prs is None:
            prs = Presentation()
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)

        # The same slide the renderer would build, minus the chart and the text.
        slot = _resolve_slot(prs, style, "preview", "image", title="")
        slide = prs.slides[slot.slide_index]
        if not template_ground(slide, style):
            _house_ground(slide, int(prs.slide_width), int(prs.slide_height), style)
        # An empty title placeholder would print PowerPoint's own prompt text.
        for shape in list(slide.shapes):
            if shape.is_placeholder and shape.has_text_frame and not shape.text_frame.text:
                shape._element.getparent().remove(shape._element)

        path = str(work / "ground.pptx")
        prs.save(path)
        pdf = pptx_to_pdf(path, str(work))
        pngs = rasterize_pages(pdf, str(work / "png"), dpi=dpi, workers=1)
        if not pngs:
            return None
        image = Image.open(pngs[0]).convert("RGB")
        image.save(cached)
        return image
    except Exception:  # noqa: BLE001 — the slow path is always available
        log.warning("could not pre-render the template ground; previews stay slow",
                    exc_info=True)
        return None
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)


def _house_ground(slide, sw: int, sh: int, style) -> None:
    """nSight's own ground, for a report with no template."""
    from reportbuilder.render.image.slide_chrome import theme_colours

    bg, _ink, _accent = theme_colours(style)
    shape = slide.shapes.add_shape(1, 0, 0, sw, sh)
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg
    shape.line.fill.background()
    shape.shadow.inherit = False


def _font(family: str, size_px: float, *, bold: bool = False,
          italic: bool = False):
    """A PIL font for *family*, resolved the way THIS HOST would render it.

    Through the configured substitutions first: a template naming Calibri on a
    host without it is drawn by LibreOffice in whatever stands in for Calibri,
    and a preview that picked something else instead would differ from the deck
    in the one place a preview is supposed to be trusted.
    """
    from reportbuilder.render import fonts as F

    wanted = (family or "").strip()
    try:
        wanted = F.substitutions().get(wanted, wanted)
    except Exception:  # noqa: BLE001
        pass
    path = _font_file(wanted, bold=bold, italic=italic)
    if path:
        try:
            # A FRACTIONAL size, deliberately: 11pt at 110 dpi is 16.81px, and
            # rounding that to 17 stretches every glyph by 1.2% — which is
            # invisible on one word and several pixels of drift by the end of a
            # long subtitle line.
            return ImageFont.truetype(path, size_px)
        except (OSError, TypeError):
            pass
    try:
        return ImageFont.truetype(path, int(round(size_px)))
    except (OSError, TypeError, ValueError):
        pass
    try:
        return ImageFont.load_default(size_px)
    except TypeError:
        return ImageFont.load_default()


_FONT_FILES: dict[tuple, str] = {}


def _font_file(family: str, *, bold: bool = False, italic: bool = False) -> str:
    """The font file this host would actually use for *family*.

    fontconfig, because that is who LibreOffice asks: on a host without Calibri,
    `fc-match Calibri` answers Liberation Sans and the deck is drawn in Liberation
    Sans, while matplotlib's own fallback would have said DejaVu — a preview in a
    different typeface from the deck it is previewing.
    """
    cache_key = (family, bold, italic)
    if cache_key in _FONT_FILES:
        return _FONT_FILES[cache_key]
    path = ""
    try:
        pattern = family or "sans-serif"
        if bold:
            pattern += ":bold"
        if italic:
            pattern += ":italic"
        out = subprocess.run(["fc-match", "-f", "%{file}", pattern],
                             capture_output=True, text=True, timeout=5)
        path = out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        path = ""
    if not path:
        try:
            from matplotlib import font_manager

            path = font_manager.findfont(
                font_manager.FontProperties(family=family or None),
                fallback_to_default=True)
        except Exception:  # noqa: BLE001
            path = ""
    _FONT_FILES[cache_key] = path
    return path


def compose_from_slide(style, slide, dpi: int = 110):
    """The finished preview: the cached ground with THIS slide's own shapes on it.

    Reads what the renderer actually put on the slide — the chart picture where
    it landed, the footer in the font and colour it was given — rather than
    re-deriving any of it. The .pptx is the layout description; this just draws
    it, for the one slide a preview needs, instead of starting LibreOffice.

    Everything else on the slide (ground, band, logo) is already in the cached
    image, because that image was built from the same template by the same code.

    Returns a PIL image, or None when there is no ground to build on.
    """
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    ground = ground_image(style, dpi)
    if ground is None:
        return None
    image = ground.convert("RGB").copy()
    slide_w = int(getattr(style, "slide_width", 0) or 0) or int(13.333 * EMU_PER_INCH)
    px = image.width / slide_w

    def to_px(emu: float) -> int:
        return int(round(emu * px))

    draw = ImageDraw.Draw(image)
    for shape in slide.shapes:
        try:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                _paste_picture(image, shape, to_px)
            elif shape.has_text_frame and (shape.text_frame.text or "").strip():
                _draw_text(draw, shape, to_px, dpi, style)
        except Exception:  # noqa: BLE001 — one shape must not lose the preview
            log.warning("preview: could not draw %s", getattr(shape, "name", "?"),
                        exc_info=True)
    return image


def _paste_picture(image, shape, to_px) -> None:
    """The chart, at the box the renderer gave it — letterboxing included."""
    import io

    with Image.open(io.BytesIO(shape.image.blob)) as chart:
        chart = chart.convert("RGBA")
        box = (max(1, to_px(int(shape.width or 0))), max(1, to_px(int(shape.height or 0))))
        resized = chart.resize(box, Image.LANCZOS)
    image.paste(resized, (to_px(int(shape.left or 0)), to_px(int(shape.top or 0))),
                resized)


def _line_step(shape, style, font) -> int:
    """Pixels from one baseline to the next, as PowerPoint computes it.

    `lnSpc` is a percentage of the FONT'S OWN line height — ascent plus descent,
    about 1.36em for Noto Sans — not of the point size. Multiplying the point
    size by Holiday Club's 90% made every line 26% too tight, so a two-line
    title came out crammed together while wrapping at exactly the right words.
    """
    ascent, descent = font.getmetrics()
    natural = ascent + descent
    if shape.is_placeholder:
        title = getattr(getattr(style, "profile", None), "title", None)
        if title is not None and title.line_spacing:
            return int(round(natural * title.line_spacing))
    return int(round(natural))


_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _caps(shape, run, style) -> bool:
    """Does this run render upper-case whatever was typed?

    `cap="all"` is a rendering instruction, not stored text: Holiday Club's
    title carries it, so LibreOffice prints the headline in capitals while the
    .pptx still holds mixed case. Drawing what the XML says instead of what
    PowerPoint shows made every Holiday Club preview visibly wrong.
    """
    rpr = run._r.find(f"{_A_NS}rPr")
    if rpr is not None and rpr.get("cap"):
        return rpr.get("cap") == "all"
    if shape.is_placeholder:
        title = getattr(getattr(style, "profile", None), "title", None)
        if title is not None:
            return bool(title.caps)
    return False


def _run_style(shape, para, run, style):
    """(family, size_pt, colour, bold, italic) for one RUN.

    Per run, not per paragraph: a bullet line is a teal glyph followed by ink
    body text, and colouring the whole line from the first run painted the body
    teal. A title PLACEHOLDER states nothing and inherits from the layout and
    master — which is what the template profile already read off the template.
    """
    family = run.font.name or ""
    size_pt = float(run.font.size.pt) if run.font.size is not None else 0.0
    bold = bool(run.font.bold)
    italic = bool(run.font.italic)
    colour = ""
    try:
        if run.font.color is not None and run.font.color.type is not None:
            colour = str(run.font.color.rgb)
    except (AttributeError, ValueError):
        pass
    if not (family and size_pt and colour) and shape.is_placeholder:
        title = getattr(getattr(style, "profile", None), "title", None)
        if title is not None:
            family = family or title.font
            size_pt = size_pt or title.size_pt
            colour = colour or title.colour
            if run.font.bold is None:
                bold = bool(title.bold)
    return family, size_pt or 11.0, colour or "2B2B2B", bold, italic


def _indents(para, to_px) -> tuple[int, int]:
    """(first-line x, wrapped-line x) offsets from the shape's left edge.

    A bullet paragraph sets `marL` (where the text sits) and a negative `indent`
    (how far back the glyph hangs). Without them every bullet drew flush left and
    the nesting levels collapsed onto each other.
    """
    ppr = para._p.find(
        "{http://schemas.openxmlformats.org/drawingml/2006/main}pPr")
    if ppr is None:
        return 0, 0
    try:
        mar_l = int(ppr.get("marL") or 0)
        indent = int(ppr.get("indent") or 0)
    except ValueError:
        return 0, 0
    return to_px(mar_l + indent), to_px(mar_l)


def _draw_text(draw, shape, to_px, dpi: int, style) -> None:
    """A text shape on the slide — a title, a subtitle, a footer, a bullet list.

    Drawn run by run and line by line, so a paragraph made of several runs (a
    coloured bullet glyph then ink body text) keeps each run's own font, weight
    and colour, and a hanging indent puts the glyph where PowerPoint puts it.
    """
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

    frame = shape.text_frame
    # A text frame insets its text from the shape's edges. nSight's own boxes set
    # all four to zero; a PLACEHOLDER inherits PowerPoint's defaults — 0.1in left
    # and right, 0.05in top and bottom — which at 110 dpi is the 10px left and
    # 5px down that every composited title was out by.
    l_ins = frame.margin_left if frame.margin_left is not None else _DEFAULT_LR_INSET
    t_ins = frame.margin_top if frame.margin_top is not None else _DEFAULT_TB_INSET
    r_ins = frame.margin_right if frame.margin_right is not None else _DEFAULT_LR_INSET
    b_ins = frame.margin_bottom if frame.margin_bottom is not None else _DEFAULT_TB_INSET
    left_emu = int(shape.left or 0) + int(l_ins)
    top_emu = int(shape.top or 0) + int(t_ins)
    width_px = max(1, to_px(int(shape.width or 0) - int(l_ins) - int(r_ins)))
    height_px = max(1, to_px(int(shape.height or 0) - int(t_ins) - int(b_ins)))
    y = to_px(top_emu)

    lines: list[tuple[list, object, int, int, bool]] = []
    line_steps: list[int] = []
    for para in frame.paragraphs:
        runs = [r for r in para.runs if r.text]
        if not runs:
            continue
        first_x, wrap_x = _indents(para, to_px)
        step, para_lines = 0, []
        # One drawable segment per run: (text, font, colour).
        segments = []
        for run in runs:
            family, size_pt, colour, bold, italic = _run_style(shape, para, run, style)
            font = _font(family, max(6.0, size_pt * dpi / 72), bold=bold, italic=italic)
            step = max(step, _line_step(shape, style, font))
            text = run.text.replace("\t", "  ")
            if _caps(shape, run, style):
                text = text.upper()
            segments.append((text, font, colour))
        avail = width_px - first_x
        for i, chunk in enumerate(_wrap_segments(draw, segments, avail,
                                                 width_px - wrap_x)
                                  if frame.word_wrap is not False else [segments]):
            para_lines.append((chunk, para.alignment, first_x, wrap_x, i == 0))
        lines.extend(para_lines)
        line_steps.extend(step for _ in para_lines)

    if not lines:
        return
    if frame.vertical_anchor == MSO_ANCHOR.BOTTOM:
        y = to_px(top_emu) + height_px - sum(line_steps)
    for (segments, alignment, first_x, wrap_x, is_first), step in zip(lines, line_steps):
        x = to_px(left_emu) + (first_x if is_first else wrap_x)
        if alignment in (PP_ALIGN.RIGHT, PP_ALIGN.CENTER):
            width = sum(draw.textlength(t, font=f) for t, f, _c in segments)
            if alignment == PP_ALIGN.RIGHT:
                x = to_px(left_emu) + width_px - int(width)
            else:
                x = to_px(left_emu) + (width_px - int(width)) // 2
        for text, font, colour in segments:
            draw.text((x, y), text, font=font, fill=f"#{colour}")
            x += int(round(draw.textlength(text, font=font)))
        y += step


def _wrap_segments(draw, segments, first_width: int, wrap_width: int) -> list[list]:
    """Break a run-styled paragraph into lines, keeping each run's styling.

    Wrapping happens across the whole paragraph, not per run, because a line
    break can fall in the middle of a run — which is what makes this different
    from wrapping a plain string.
    """
    out: list[list] = []
    current: list = []
    used = 0.0
    limit = first_width
    for text, font, colour in segments:
        for word in _tokens(text):
            w = draw.textlength(word, font=font)
            if current and used + w > limit and word.strip():
                out.append(current)
                current, used, limit = [], 0.0, wrap_width
            if current and current[-1][1] is font and current[-1][2] == colour:
                current[-1] = (current[-1][0] + word, font, colour)
            else:
                current.append((word, font, colour))
            used += w
    if current:
        out.append(current)
    return out or [[]]


def _tokens(text: str) -> list[str]:
    """Words with their trailing spaces kept, so re-joining preserves spacing."""
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch == " ":
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


    if not lines:
        return
    if frame.vertical_anchor == MSO_ANCHOR.BOTTOM:
        y = to_px(top_emu) + height_px - sum(step for _, step in line_steps)
    for (segments, alignment, first_x, wrap_x, is_first), step in zip(lines, [s for _, s in line_steps]):
        x = to_px(left_emu) + (first_x if is_first else wrap_x)
        if alignment in (PP_ALIGN.RIGHT, PP_ALIGN.CENTER):
            width = sum(draw.textlength(t, font=f) for t, f, _c in segments)
            edge = to_px(left_emu + int(shape.width or 0))
            x = edge - int(width) if alignment == PP_ALIGN.RIGHT else \
                to_px(left_emu) + (width_px - int(width)) // 2
        for text, font, colour in segments:
            draw.text((x, y), text, font=font, fill=f"#{colour}")
            x += int(round(draw.textlength(text, font=font)))
        y += step
