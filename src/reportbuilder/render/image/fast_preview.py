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


def _font(family: str, size_px: int):
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
    path = _font_file(wanted)
    if path:
        try:
            return ImageFont.truetype(path, size_px)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size_px)
    except TypeError:
        return ImageFont.load_default()


_FONT_FILES: dict[str, str] = {}


def _font_file(family: str) -> str:
    """The font file this host would actually use for *family*.

    fontconfig, because that is who LibreOffice asks: on a host without Calibri,
    `fc-match Calibri` answers Liberation Sans and the deck is drawn in Liberation
    Sans, while matplotlib's own fallback would have said DejaVu — a preview in a
    different typeface from the deck it is previewing.
    """
    if family in _FONT_FILES:
        return _FONT_FILES[family]
    path = ""
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", family or "sans-serif"],
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
    _FONT_FILES[family] = path
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
                _draw_text(draw, shape, to_px, dpi, image.width)
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


def _draw_text(draw, shape, to_px, dpi: int, image_width: int) -> None:
    """A textbox the renderer added — the footer, a caption, a subtitle."""
    from pptx.enum.text import PP_ALIGN

    frame = shape.text_frame
    for para in frame.paragraphs:
        text = "".join(r.text for r in para.runs).strip()
        if not text:
            continue
        run = para.runs[0]
        size_pt = float(run.font.size.pt) if run.font.size is not None else 11.0
        colour = "666666"
        try:
            if run.font.color is not None and run.font.color.type is not None:
                colour = str(run.font.color.rgb)
        except (AttributeError, ValueError):
            pass
        font = _font(run.font.name or "", max(6, int(round(size_pt * dpi / 72))))
        left, top = to_px(int(shape.left or 0)), to_px(int(shape.top or 0))
        if para.alignment == PP_ALIGN.RIGHT:
            width = draw.textlength(text, font=font)
            left = to_px(int(shape.left or 0) + int(shape.width or 0)) - int(width)
        draw.text((left, top), text, font=font, fill=f"#{colour}")
        # One paragraph per box is what the renderer writes; a second would need
        # line metrics we do not have here.
        break
