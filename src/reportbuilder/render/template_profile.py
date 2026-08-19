"""What to borrow from a customer's template, and nothing more.

Johan's spec: take the title's style and POSITION, the subtitle font, graphics
belonging to the title, and the furniture that repeats on every slide (logo,
footer, background). nSight then draws its own slide with those. The chart and
the rest of the text stay at sizes and positions nSight chooses.

The reason this exists rather than either of the two obvious approaches:

  * Building from the template's LAYOUTS works only when the brand is in the
    layouts. `Attendo Bränditutkimus Marraskuu 2025.pptx` is like that — 28
    layouts, Century Gothic, navy palette.
  * Copying the template's SLIDES hands us someone else's slide geometry, and
    Johan does not want the slides reused.

`attendo_agent_deck.pptx` is the case that breaks the first approach: stock
Office masters (Calibri, the 4F81BD/C0504D palette, English layout names) with
every content slide on the `Blank` layout carrying ~7 hand-drawn shapes. The
design is on the slides, not in the layouts.

So the profile is harvested from whichever place the design actually lives: a
layout when a layout carries one, otherwise the template's most representative
slide. Same profile shape either way, so the renderer does not care which.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field

from pptx import Presentation
from pptx.util import Emu

# A shape covering this much of the slide is background, not content.
_BACKDROP_AREA = 0.75
# Text this large is a title rather than body copy, when nothing else says so.
_TITLE_MIN_PT = 14.0


@dataclass
class TextStyle:
    """How a piece of text looks, and (for the title) where it sits."""

    font: str = ""
    size_pt: float = 0.0
    bold: bool | None = None
    colour: str = ""          # hex, no '#'
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0

    @property
    def positioned(self) -> bool:
        return self.width > 0 and self.height > 0


@dataclass
class TemplateProfile:
    """The borrowed part of a template."""

    source: str = ""                  # "layout:<name>" | "slide:<n>" | ""
    title: TextStyle = field(default_factory=TextStyle)
    subtitle_font: str = ""
    #: Shape XML to clone onto every generated slide: background, logo, footer,
    #: and any graphic sitting with the title. Order preserved so z-order is.
    furniture: list = field(default_factory=list)
    slide_width: int = 0
    slide_height: int = 0

    @property
    def usable(self) -> bool:
        return bool(self.title.font or self.title.positioned or self.furniture)

    def describe(self) -> dict:
        """A summary safe to log or show in the UI."""
        return {"source": self.source, "title_font": self.title.font,
                "title_pt": self.title.size_pt, "title_colour": self.title.colour,
                "title_box_in": [round(Emu(v).inches, 2) for v in
                                 (self.title.left, self.title.top,
                                  self.title.width, self.title.height)],
                "subtitle_font": self.subtitle_font,
                "furniture_shapes": len(self.furniture)}


# --- reading text style -----------------------------------------------------

def _first_run(shape):
    try:
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                return run, para
            return None, para
    except AttributeError:
        pass
    return None, None


def _style_of(shape) -> TextStyle:
    """The style of *shape*'s first run, plus the shape's own box."""
    st = TextStyle(left=int(shape.left or 0), top=int(shape.top or 0),
                   width=int(shape.width or 0), height=int(shape.height or 0))
    run, para = _first_run(shape)
    holder = run.font if run is not None else (para.font if para is not None else None)
    if holder is None:
        return st
    st.font = holder.name or ""
    if holder.size is not None:
        st.size_pt = float(holder.size.pt)
    st.bold = holder.bold
    try:
        # An explicit RGB only. A theme-colour reference means "whatever the
        # theme says", which our own slide inherits anyway.
        if holder.color is not None and holder.color.type is not None:
            st.colour = str(holder.color.rgb)
    except (AttributeError, ValueError):
        pass
    return st


def _text_shapes(container) -> list:
    out = []
    for sh in container.shapes:
        try:
            if sh.has_text_frame:
                out.append(sh)
        except AttributeError:
            continue
    return out


def _looks_like_title(shape) -> bool:
    if shape.is_placeholder:
        try:
            # 13 = TITLE, 0 = CENTER_TITLE in python-pptx's enum values.
            if shape.placeholder_format.idx == 0:
                return True
        except (AttributeError, ValueError):
            pass
    name = (shape.name or "").lower()
    return "title" in name or "otsik" in name or "rubrik" in name


def _pick_title(container) -> object | None:
    """The shape acting as the title: a real title placeholder, else the
    largest text near the top. Names are unreliable across languages, so size
    and position decide when there is no placeholder to ask."""
    shapes = _text_shapes(container)
    if not shapes:
        return None
    for sh in shapes:
        if _looks_like_title(sh):
            return sh
    with_text = [sh for sh in shapes if (sh.text_frame.text or "").strip()]
    candidates = with_text or shapes
    scored = []
    for sh in candidates:
        st = _style_of(sh)
        # Bigger type wins; ties break toward the top of the slide.
        scored.append((st.size_pt or _TITLE_MIN_PT, -int(sh.top or 0), sh))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[0][2]


def _pick_subtitle(container, title) -> str:
    """The body font: the next text shape below the title."""
    below = []
    for sh in _text_shapes(container):
        if sh is title:
            continue
        if int(sh.top or 0) >= int(getattr(title, "top", 0) or 0):
            below.append(sh)
    below.sort(key=lambda sh: int(sh.top or 0))
    for sh in below:
        st = _style_of(sh)
        if st.font:
            return st.font
    return ""


# --- choosing where to harvest from -----------------------------------------

def _decoration(container) -> list:
    """Shapes that are furniture rather than content placeholders."""
    out = []
    for sh in container.shapes:
        if sh.is_placeholder:
            continue
        out.append(sh)
    return out


def _layout_with_design(prs):
    """A layout that carries actual design, or None.

    KNOWN WRONG, do not ship as-is: ranking by decoration count picks a
    decorated agenda or closing slide over the ordinary content layout. On real
    templates it chose "Agenda slide" for Attendo (title box 4.4in tall, 2.3in
    down — that is a content area) and "Slutbild" for Synsam (title box 0.14in
    tall at top -0.17in — off the slide). Replace with the area-based ranking in
    template_check.inspect_template, which already finds "1 layout area" and
    "Innehåll" correctly, and keep this only as the tie-breaker for which of
    those layouts carries furniture.

    "Carries design" means it has non-placeholder shapes of its own — a logo, a
    band, a footer. A layout with nothing but placeholders contributes no look,
    which is exactly the stock-Office case that made attendo_agent_deck render
    as plain slides.
    """
    best, best_n = None, 0
    for layout in prs.slide_layouts:
        n = len(_decoration(layout))
        if n > best_n:
            best, best_n = layout, n
    return best


def _representative_slide(prs):
    """The template's most typical content slide.

    Chosen by how many slides share its shape count: a deck's body slides
    outnumber its cover and section breaks, so the most common shape count is
    the ordinary content slide. Ties go to the later slide, which is more
    likely to be body content than a cover.
    """
    if not len(prs.slides):
        return None
    counts = Counter(len(s.shapes) for s in prs.slides)
    # Ignore near-empty slides: they carry no design to harvest.
    usable = [(n, c) for n, c in counts.items() if n >= 2]
    if not usable:
        return None
    target = max(usable, key=lambda t: (t[1], t[0]))[0]
    match = [s for s in prs.slides if len(s.shapes) == target]
    return match[len(match) // 2] if match else None


def _is_backdrop(shape, sw: int, sh_: int) -> bool:
    try:
        area = int(shape.width or 0) * int(shape.height or 0)
    except (TypeError, ValueError):
        return False
    return sw > 0 and sh_ > 0 and area >= _BACKDROP_AREA * sw * sh_


def _furniture(container, title, sw: int, sh_: int) -> list:
    """Shape XML to clone onto every slide: background, logos, footer, rules.

    Excludes the title itself (nSight draws that) and anything holding real
    body text — a chart placeholder's prompt or last year's bullet points must
    not travel onto this year's slide. A full-slide backdrop is kept even
    though it has no text, because it IS the design.
    """
    out = []
    for sh in _decoration(container):
        if sh is title:
            continue
        text = ""
        try:
            if sh.has_text_frame:
                text = (sh.text_frame.text or "").strip()
        except AttributeError:
            pass
        if text and not _is_backdrop(sh, sw, sh_):
            # Short text is furniture (a footer, a page number, a brand line);
            # a paragraph is somebody's content.
            if len(text) > 60:
                continue
        out.append(deepcopy(sh._element))
    return out


# --- the entry point --------------------------------------------------------

def extract_profile(template_path: str) -> TemplateProfile:
    """Harvest the borrowable part of *template_path*.

    Never raises on a readable .pptx: a template we cannot read a title from
    still yields a profile with whatever furniture it had, and the renderer
    falls back to its own placement for the rest.
    """
    prs = Presentation(template_path)
    sw, sh_ = int(prs.slide_width or 0), int(prs.slide_height or 0)
    profile = TemplateProfile(slide_width=sw, slide_height=sh_)

    layout = _layout_with_design(prs)
    slide = _representative_slide(prs)

    # Prefer whichever source actually carries design. A layout is the cleaner
    # source when it has any, because it is by definition repeatable; a slide is
    # the fallback for decks that were designed slide by slide.
    source = None
    if layout is not None and len(_decoration(layout)) >= 2:
        source, profile.source = layout, f"layout:{layout.name}"
    elif slide is not None:
        idx = list(prs.slides).index(slide) + 1
        source, profile.source = slide, f"slide:{idx}"
    elif layout is not None:
        source, profile.source = layout, f"layout:{layout.name}"
    if source is None:
        return profile

    title = _pick_title(source)
    if title is not None:
        profile.title = _style_of(title)
        profile.subtitle_font = _pick_subtitle(source, title)
    profile.furniture = _furniture(source, title, sw, sh_)
    return profile
