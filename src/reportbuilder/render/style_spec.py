"""Load a StyleSpec (fonts/colors/slots) from a template .pptx (REQ-C-25/27a)."""
from __future__ import annotations

import logging

from pptx import Presentation
from reportbuilder import config
from reportbuilder.render.base import Slot, StyleSpec

log = logging.getLogger(__name__)

_DEFAULT_FONTS: dict[str, tuple[str, int]] = {
    "title": ("Arial", 14),
    "axis_values": ("Arial", 10),
    "axis_names": ("Arial", 10),
    "category_names": ("Arial", 10),
    "data_labels": ("Arial", 10),
    "legend": ("Arial", 10),
    "n_annotation": ("Arial", 9),
    "filter_var": ("Arial", 9),
}
_DEFAULT_PALETTE = ["1F77B4", "FF7F0E", "2CA02C", "D62728", "9467BD", "8C564B", "E377C2", "7F7F7F"]

# PowerPoint's own default themes. A template whose accents are exactly one of
# these has never had its theme edited, so it states no brand — and using it
# would paint a client's deck in Office blue. `attendo_agent_deck.pptx` is that
# case: stock Office masters under slides drawn in cream and teal by hand.
_STOCK_THEMES: tuple[tuple[str, ...], ...] = (
    ("4F81BD", "C0504D", "9BBB59", "8064A2", "4BACC6", "F79646"),   # Office 2007-10
    ("5B9BD5", "ED7D31", "A5A5A5", "FFC000", "4472C4", "70AD47"),   # Office 2013+
)


def states_a_brand(palette) -> bool:
    """True when a theme's accents are a deliberate choice, not Office's default."""
    return bool(palette) and tuple(c.upper() for c in palette[:6]) not in _STOCK_THEMES


class TemplateStyleSpec(StyleSpec):
    # This style came from a real .pptx. Chart colours, background and ink
    # follow the template whichever way its slides are built, so this is the
    # flag for "a template applies" — chart_layout_index is not, since a deck
    # whose design lives on its slides has none.
    from_template: bool = True
    # Which layout new chart slides are built from, and where the chart goes on
    # it. None means the design was harvested off a slide instead (or no usable
    # layout was found), and the renderer builds the slide itself.
    chart_layout_index: int | None = None
    chart_slot: Slot | None = None
    # What to borrow from the template when its design is NOT in the layouts:
    # the title's style and box, and the furniture that repeats on every slide.
    profile: object | None = None
    # The template's type and colour, resolved ONCE — see template_cache.resolve,
    # which sets this. None on a style built without a template (or built
    # directly rather than through resolve), in which case the renderers measure
    # as they did before. Carried here because the renderers are handed a style,
    # not a ResolvedTemplate, at far too many call sites to thread a new one.
    resolved_spec: object | None = None
    # Hex, no leading '#'. Empty means "no template opinion", and the house
    # cream/ink apply.
    background: str = ""
    ink: str = ""
    # The theme's accents when the template actually states a brand — empty when
    # its theme is untouched Office. Charts use these in order when present.
    brand_palette: list[str] = []
    # The one colour this template leads with: its first brand accent, else the
    # colour its own slides are drawn in. Chart ramps are built from it.
    accent: str = ""
    # The template theme's own typefaces. Used for the text nSight draws itself
    # (subtitle, footer): those are textboxes, not placeholders, so they inherit
    # nothing and would otherwise sit on a customer's slide in our font.
    heading_font: str = ""
    body_font: str = ""
    #: Overrides for the two elements that have no box of their own. The
    #: subtitle sits a fixed gap above the chart and the footer a fixed gap
    #: above the template's own foot, so there is nothing to move — but their
    #: SIZE is the thing an author reaches for first: "kysymystekstin
    #: pienentäminen", shrinking a question that runs too long.
    #: True once an author has placed the content area themselves. The renderer
    #: otherwise reserves room under the title and puts the chart below it, which
    #: is the right guess when nobody has said where the chart goes — and simply
    #: overrides them when somebody has.
    content_is_authored: bool = False
    title_size_pt: float = 0.0
    title_colour: str = ""
    subtitle_font: str = ""
    subtitle_size_pt: float = 0.0
    subtitle_colour: str = ""
    #: The methodology line's own face. It IS a font role ("n_annotation"), but
    #: the textbox that draws it asks for `body_font` — so setting only the role
    #: stored the choice and drew the old face. (Johan, 2026-09-08)
    footer_font: str = ""
    footer_colour: str = ""
    #: The colour a chart's own text is drawn in — tick labels, legend, data
    #: labels outside a bar. Stated by the CONTENT area of the layout editor,
    #: whose colour was kept by the API and read by nothing. Blank means the
    #: contrast-derived ink `furniture_colors` picks for the slide's ground.
    chart_text_colour: str = ""

    def __init__(self, slide_width, slide_height, slots, fonts, palette, spec_source="generic"):
        self.slide_width = slide_width
        self.slide_height = slide_height
        self._slots = slots
        self._fonts = fonts
        self._palette = palette
        self.spec_source = spec_source
        self.matches_client_spec = False

    def font_for(self, element_class: str) -> tuple[str, int]:
        return self._fonts.get(element_class, ("Arial", 10))

    def color_for(self, series_index: int) -> str:
        return self._palette[series_index % len(self._palette)]

    def slot(self, name: str) -> Slot:
        return self._slots[name]

    def slots(self) -> dict[str, Slot]:
        return dict(self._slots)


def load_style_spec(template_path: str,
                    force_layout: int | None = None) -> TemplateStyleSpec:
    prs = Presentation(template_path)
    fonts = dict(_DEFAULT_FONTS)
    slots: dict[str, Slot] = {}
    for i, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            name = shape.name or ""
            slots[name] = Slot(slide_index=i, left=int(shape.left or 0), top=int(shape.top or 0),
                               width=int(shape.width or 0), height=int(shape.height or 0), name=name)
            if name.startswith("style:"):
                cls = name.split(":", 1)[1]
                try:
                    run = shape.text_frame.paragraphs[0].runs[0]
                    fn = run.font.name or "Arial"
                    sz = int(run.font.size.pt) if run.font.size is not None else 10
                    fonts[cls] = (fn, sz)
                except (AttributeError, IndexError):
                    pass
    spec = TemplateStyleSpec(prs.slide_width, prs.slide_height, slots, fonts,
                             list(_DEFAULT_PALETTE), spec_source=str(template_path))

    # The layout a chart slide should be BUILT FROM, rather than a blank one we
    # then guess geometry on. The client's designer already decided where a
    # title and a content area belong on their slide; template_check finds that
    # layout by the size of its content placeholder, which survives the fact
    # that the same layout is called "1 layout area", "Innehåll" and "Title and
    # Content" in three real client decks.
    from reportbuilder.render.template_check import inspect_template
    from reportbuilder.render.template_profile import extract_profile

    report = inspect_template(str(template_path))
    spec.heading_font = report.theme.heading_font or ""
    spec.body_font = report.theme.body_font or ""
    if report.best is not None:
        spec.chart_layout_index = report.best.index
        layout = prs.slide_layouts[report.best.index]
        content = _largest_content_placeholder(layout)
        if content is not None:
            spec.chart_slot = Slot(
                slide_index=-1,  # -1: a slide is added per chart, not reused
                left=int(content.left or 0), top=int(content.top or 0),
                width=int(content.width or 0), height=int(content.height or 0),
                name="chart")
        # The template's own theme colours beat our defaults: accent1-6 is what
        # PowerPoint's charts use for series, so a deck in Attendo's template
        # gets Attendo's palette rather than nSight teal. Untouched Office
        # accents are not a brand and are not used — see states_a_brand.
        if states_a_brand(report.theme.palette):
            spec.brand_palette = list(report.theme.palette)
            spec._palette = list(report.theme.palette)
            spec.accent = report.theme.palette[0]
        spec.background = report.theme.background
        spec.ink = report.theme.ink

    # Where the design actually lives. A layout carries it only when the deck's
    # own slides are built on one — Attendo's are, Synsam's and the agent deck's
    # are not, and building those from their (stock Office) layouts is what made
    # a client deck come out looking like plain PowerPoint. When it does not,
    # the profile carries the title's style and box and the repeating furniture,
    # and the renderer draws the slide itself.
    try:
        spec.profile = extract_profile(str(template_path), force_layout)
    except Exception:  # noqa: BLE001 — a template we cannot harvest still renders
        # LOUDLY. Swallowed, this reverts to building on the template's layouts,
        # and for a stock-Office file that is the plain-PowerPoint deck this
        # whole module exists to prevent — with nothing in the log to say why.
        log.warning("could not harvest a style profile from %s; falling back",
                    template_path, exc_info=True)
        spec.profile = None
    if spec.profile is None and not spec.brand_palette:
        # Nothing harvested AND no brand in the theme: whatever layouts this
        # file has are Office's own, and a 44pt centred title placeholder on a
        # white slide is worse than nSight's house style. Take the house style.
        spec.chart_layout_index = None
        spec.chart_slot = None
    if spec.profile is not None:
        spec.chart_layout_index = spec.profile.layout_index
        spec.chart_slot = None
        # The title is drawn by US, on the ground the template gives us — so it
        # has to be the colour that template writes its titles in, whichever
        # branch below we take. This used to be set only when the design lived
        # on SLIDES, which is the one case where it rarely matters: Arla's
        # design lives in a LAYOUT whose title is white on a black band, so the
        # harvested white was discarded and the default black drawn onto black.
        # The headline was there on every slide and could not be read.
        if spec.profile.title is not None and spec.profile.title.colour:
            spec.ink = spec.profile.title.colour
        if spec.profile.layout_index is None:
            # Design on the slides means colours on the slides too. The theme of
            # such a file describes nothing that is on screen: attendo_agent_deck
            # renders cream and teal while its theme says white, black and Office
            # blue, and reading the theme is what made a client's deck come back
            # in colours that appear nowhere in their template.
            spec.background = spec.profile.background or spec.background
            spec.accent = spec.accent or spec.profile.accent
        if spec.profile.layout_index is not None:
            # The ground this LAYOUT states, which the theme does not describe.
            try:
                stated = layout_background(
                    prs.slide_layouts[spec.profile.layout_index],
                    _theme_colours(prs))
            except Exception:  # noqa: BLE001 — never fail a style over a colour
                stated = ""
            if stated:
                spec.background = stated
            # …and the colours that layout writes its own text in. An author's
            # override still wins: these are only set where nobody has said.
            try:
                from pptx.enum.shapes import PP_PLACEHOLDER as _PP

                _layout = prs.slide_layouts[spec.profile.layout_index]
                _theme = _theme_colours(prs)
                if not spec.chart_text_colour:
                    spec.chart_text_colour = layout_text_colour(
                        _layout, {_PP.OBJECT, _PP.BODY}, _theme)
                if not getattr(spec, "footer_colour", ""):
                    spec.footer_colour = layout_text_colour(
                        _layout, {_PP.FOOTER}, _theme)
            except Exception:  # noqa: BLE001 — never fail a style over a colour
                pass
        if (spec.profile.layout_index is not None
                and spec.profile.layout_content_is_chart_area):
            content = _largest_content_placeholder(
                prs.slide_layouts[spec.profile.layout_index])
            if content is not None:
                spec.chart_slot = Slot(
                    slide_index=-1,  # -1: a slide is added per chart, not reused
                    left=int(content.left or 0), top=int(content.top or 0),
                    width=int(content.width or 0), height=int(content.height or 0),
                    name="chart")
    return spec


#: The theme slot a `<a:schemeClr>` in a background refers to. bg1/tx1 are the
#: light/dark pair swapped by the slide master; lt1/dk1 name them directly.
_BG_SCHEME_SLOT = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2",
                   "lt1": "lt1", "dk1": "dk1", "lt2": "lt2", "dk2": "dk2"}


def _theme_colours(prs) -> dict:
    """{slot: RRGGBB} for the theme's own colour scheme, so a `<a:schemeClr>`
    in a layout's background can be resolved to a colour."""
    import xml.etree.ElementTree as _ET

    _A = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    out: dict[str, str] = {}
    try:
        part = prs.slide_masters[0].part.part_related_by(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme")
        root = _ET.fromstring(part.blob)
    except Exception:  # noqa: BLE001 — no theme is no colours, not a failure
        return out
    slots = ["lt1", "dk1", "lt2", "dk2"] + [f"accent{i}" for i in range(1, 7)]
    for slot in slots:
        el = root.find(f".//a:clrScheme/a:{slot}", _A)
        if el is None:
            continue
        srgb = el.find("a:srgbClr", _A)
        sysc = el.find("a:sysClr", _A)
        value = srgb.get("val") if srgb is not None else (
            sysc.get("lastClr") if sysc is not None else None)
        if value:
            out[slot] = value.upper()
    return out


def layout_text_colour(layout, wanted, theme: dict) -> str:
    """The colour a LAYOUT states for one of its placeholders, or "".

    A template says what colour its own text is, and on a layout with a ground
    of its own it is the only thing that does: Alflorex's "Sisältö_tumma2"
    writes its title and content in `schemeClr accent2` (FAEA90) over a navy
    background, while "Sisältö_valkoinen" writes both in `tx2` (31415A). We
    were deriving a colour from the ground instead — legible, but not theirs —
    so a deck came back in colours that appear nowhere in the template.
    (Johan, 2026-09-18: "Correct the coloring.")

    Read in the order PowerPoint resolves it: a run's own colour, the
    paragraph's, then the placeholder's list style.
    """
    import re as _re

    for shape in getattr(layout, "placeholders", []):
        try:
            if shape.placeholder_format.type not in wanted:
                continue
            xml = shape._element.xml
        except Exception:  # noqa: BLE001
            continue
        literal = _re.search(r'<a:(?:solidFill)>\s*<a:srgbClr val="([0-9A-Fa-f]{6})"', xml)
        named = _re.search(r'<a:(?:solidFill)>\s*<a:schemeClr val="(\w+)"', xml)
        if literal:
            return literal.group(1).upper()
        if named:
            slot = _BG_SCHEME_SLOT.get(named.group(1), named.group(1))
            value = (theme or {}).get(slot, "")
            if value:
                return str(value).lstrip("#").upper()
    return ""


def layout_background(layout, theme: dict) -> str:
    """The ground a LAYOUT states for itself, or "" when it inherits one.

    A layout may override the master's background outright — Alflorex's
    "Sisältö_tumma2" states `srgbClr 31415A` while "Sisältö_valkoinen" inherits
    `schemeClr bg1`. Both were described as the theme's lt1, so a dark layout
    was drawn with the ink, muted and grid of a light one, and the text came out
    dark on a dark slide. (Johan, 2026-09-18)

    Only what the layout itself says. An inherited background is the master's
    and the theme already answers for it.
    """
    import re as _re

    try:
        xml = layout.element.xml
    except Exception:  # noqa: BLE001 — a layout we cannot read states nothing
        return ""
    found = _re.search(r"<p:bg>.*?</p:bg>", xml, _re.S)
    if not found:
        return ""
    frag = found.group(0)
    literal = _re.search(r'srgbClr val="([0-9A-Fa-f]{6})"', frag)
    if literal:
        return literal.group(1).upper()
    named = _re.search(r'schemeClr val="(\w+)"', frag)
    if named:
        slot = _BG_SCHEME_SLOT.get(named.group(1))
        if slot:
            return str((theme or {}).get(slot, "") or "").lstrip("#").upper()
    return ""


def _largest_content_placeholder(layout):
    """The placeholder a chart should occupy: the biggest content area."""
    from pptx.enum.shapes import PP_PLACEHOLDER

    wanted = {PP_PLACEHOLDER.OBJECT, PP_PLACEHOLDER.BODY}
    best, area = None, 0
    for ph in layout.placeholders:
        if ph.placeholder_format.type not in wanted:
            continue
        size = int(ph.width or 0) * int(ph.height or 0)
        if size > area:
            best, area = ph, size
    return best


def attendo_interim_spec() -> TemplateStyleSpec:
    """Interim proxy style spec from the Attendo deck. Satisfies REQ-C-27a (renders
    against *a* spec); REQ-C-27b (match the *client's* spec) remains BLOCKED — marked
    via spec_source/matches_client_spec."""
    spec = load_style_spec(str(config.ATTENDO_TEMPLATE))
    spec.spec_source = "attendo-interim-proxy"
    return spec

# ---------------------------------------------------------------------------
# What an author says, on top of what we harvested
# ---------------------------------------------------------------------------

#: Geometry is given in INCHES, because that is what PowerPoint's own ruler
#: says and what somebody dragging a box on screen is really adjusting. EMU is
#: an implementation detail of the file format and belongs on this side of the
#: boundary only.
_EMU_PER_INCH = 914400


def _hex(value) -> str:
    """A colour an author typed, or "" for "no opinion"."""
    text = str(value or "").strip().lstrip("#").upper()
    return text if len(text) in (6, 8) and all(c in "0123456789ABCDEF" for c in text) else ""


def _num(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 or out == 0 else None


def apply_template_overrides(spec, overrides: dict | None) -> None:
    """Apply an author's corrections to a harvested style, in place.

    Harvesting is a guess made from a file nobody wrote for us, and each of the
    three customer templates we have is unusual in a different way. The rules
    are better now; the next template will find a new way. So an author can say
    what the answer is and be believed — per template, because everything we
    have seen is a property of the template rather than of one deck.

    BLANK MEANS INHERIT, everywhere. A template nobody has touched renders
    exactly as the harvester decided, which is what keeps this an override
    rather than a second place the truth has to be maintained.
    """
    if not overrides:
        return

    title = overrides.get("title") or {}
    content = overrides.get("content") or {}

    if _hex(title.get("colour")):
        spec.ink = _hex(title["colour"])
        spec.title_colour = _hex(title["colour"])
    if _num(title.get("size")):
        spec.title_size_pt = _num(title["size"])
    if _hex(overrides.get("accent")):
        spec.accent = _hex(overrides["accent"])
        # And the harvested BRAND palette goes. `template_palette` prefers a
        # template's own brand colours over any accent, which is right until an
        # author states one — at which point the palette is the very answer they
        # are correcting, and leaving it in place made the accent field change
        # nothing on a template that had one. The ramp is rebuilt from their
        # colour. (Johan, 2026-09-08)
        spec.brand_palette = []
    if _hex(overrides.get("background")):
        spec.background = _hex(overrides["background"])

    profile = getattr(spec, "profile", None)
    if profile is not None and getattr(profile, "title", None) is not None:
        _apply_text(profile.title, title)
        _apply_box(profile.title, title)
        # Remember that a PERSON stated it. The renderer writes the headline
        # into the layout's title placeholder when there is one and lets the
        # placeholder's own inheritance supply position, font and colour — which
        # is right for a template nobody has corrected, and is exactly why a
        # correction was stored, shown back in the editor, and never drawn.
        if any(_num(title.get(k)) is not None for k in ("x", "y", "w", "h")):
            profile.title.authored = True
        if _hex(title.get("colour")):
            profile.title.colour = _hex(title["colour"]).lstrip("#")
        if title.get("font") or _hex(title.get("colour")) or _num(title.get("size")):
            profile.title.authored_text = True
    # AND the font role, which is where the drawn title actually gets its size:
    # `build_spec` reads `fonts["title"]`, not the profile, so setting only the
    # profile stored the number, showed it back in the editor, and left the
    # headline exactly as it was.
    if title.get("font") or _num(title.get("size")):
        had_family, had_size = spec.font_for("title")
        _set_fonts(spec, {"title": (str(title.get("font") or had_family),
                                    int(_num(title.get("size")) or had_size))})
    _apply_chart_text(spec, content)

    subtitle = overrides.get("subtitle") or {}
    if subtitle.get("font"):
        spec.subtitle_font = str(subtitle["font"])
    if _num(subtitle.get("size")):
        spec.subtitle_size_pt = _num(subtitle["size"])
    if _hex(subtitle.get("colour")):
        spec.subtitle_colour = _hex(subtitle["colour"])
    _apply_subtitle_box(spec, subtitle)

    # The footer is the "n = 3144" line. It is a font role already, so its size
    # and face go where every other chart-text size goes.
    footer = overrides.get("footer") or {}
    if footer.get("font") or _num(footer.get("size")):
        had_family, had_size = spec.font_for("n_annotation")
        _set_fonts(spec, {"n_annotation": (
            str(footer.get("font") or had_family),
            int(_num(footer.get("size")) or had_size))})
    if footer.get("font"):
        spec.footer_font = str(footer["font"])
    if _hex(footer.get("colour")):
        spec.footer_colour = _hex(footer["colour"])

    _apply_slot(spec, content)


#: The chart's own text. "Content font/size" means these: the row labels down
#: the side, the numbers in the bars, the legend and the axis. Naming them is
#: what makes the setting do the thing an author asked for — the first complaint
#: about a rendered slide was row labels overlapping each other, and the answer
#: to that is a smaller category font, not a different body font somewhere.
_CHART_TEXT_ROLES = ("category_names", "data_labels", "axis_values",
                     "axis_names", "legend")


def _set_fonts(spec, changes: dict[str, tuple[str, int]]) -> None:
    """Change what `font_for` answers.

    It reads `_fonts`, which the constructor set — assigning a `fonts` attribute
    instead made a new one that nothing reads, so a content or footer size was
    stored, echoed back by the API, and had no effect on a single pixel.

    The resolved spec is dropped with it: it was built from the sizes as they
    were, and anything reading it would go on answering with those.
    """
    fonts = dict(getattr(spec, "_fonts", {}) or {})
    fonts.update(changes)
    spec._fonts = fonts
    spec.resolved_spec = None


def _apply_chart_text(spec, given: dict) -> None:
    colour = _hex(given.get("colour"))
    if colour:
        spec.chart_text_colour = colour
    family = str(given.get("font") or "").strip()
    size = _num(given.get("size"))
    if not family and not size:
        return
    if family:
        spec.body_font = family
    _set_fonts(spec, {
        role: (family or spec.font_for(role)[0],
               int(size) if size else spec.font_for(role)[1])
        for role in _CHART_TEXT_ROLES
    })


def _apply_text(style, given: dict) -> None:
    if given.get("font"):
        style.font = str(given["font"])
    size = _num(given.get("size"))
    if size:
        style.size_pt = size
        # Not a starting point to shrink from: see TextStyle.size_locked.
        if hasattr(style, "size_locked"):
            style.size_locked = True


def _apply_box(style, given: dict) -> None:
    for key, attr in (("x", "left"), ("y", "top"), ("w", "width"), ("h", "height")):
        value = _num(given.get(key))
        if value is not None and hasattr(style, attr):
            setattr(style, attr, int(value * _EMU_PER_INCH))


def effective_content_rect(spec) -> tuple[int, int, int, int]:
    """Where the chart actually goes on this style, in EMU.

    The layout's own content placeholder when we are taking it, and otherwise
    the renderer's own placement — under the title, inside the template's side
    margins. There is no third answer, and every caller needs the same one: the
    editor draws this rectangle, and a drag has to amend THIS rectangle rather
    than an absence.
    """
    sw = int(getattr(spec, "slide_width", 0) or 0)
    sh = int(getattr(spec, "slide_height", 0) or 0)
    slot = getattr(spec, "chart_slot", None)
    if slot is not None and int(slot.width or 0) > 0 and int(slot.height or 0) > 0:
        rect = (int(slot.left), int(slot.top), int(slot.width), int(slot.height))
    else:
        profile = getattr(spec, "profile", None)
        title = getattr(profile, "title", None) if profile is not None else None
        if title is not None and getattr(title, "positioned", False):
            from reportbuilder.render.image.slide_chrome import harvested_chart_box

            rect = harvested_chart_box(profile, "", sw, sh)
        else:
            margin = int(0.05 * sw)
            rect = (margin, int(0.28 * sh), sw - 2 * margin, int(0.60 * sh))

    left, top, width, height = rect
    inch = _EMU_PER_INCH
    width = max(inch, min(width, sw or width))
    height = max(inch, min(height, sh or height))
    left = max(0, min(left, (sw or left + width) - width))
    top = max(0, min(top, (sh or top + height) - height))
    return left, top, width, height


def _apply_subtitle_box(spec, given: dict) -> None:
    """The question's own rectangle — the SUB area in the layout editor.

    It had none until 2026-09-18: it was placed relative to the content, a fixed
    gap above the chart, sharing the title's left and width. That is still the
    DEFAULT and stays exactly as it was when nobody has dragged SUB — absence
    here means the derivation, not a blank rectangle.

    Only the BOTTOM edge of this box is an anchor. The question is drawn
    bottom-anchored inside it and grows upward, so its length moves nothing but
    its own top edge, and it can never reach down into the content.
    """
    edges = {k: _num(given.get(k)) for k in ("x", "y", "w", "h")}
    if all(v is None for v in edges.values()):
        return
    current = getattr(spec, "subtitle_rect", None)
    left, top, width, height = current or (0, 0, 0, 0)
    spec.subtitle_rect = (
        int(edges["x"] * _EMU_PER_INCH) if edges["x"] is not None else int(left),
        int(edges["y"] * _EMU_PER_INCH) if edges["y"] is not None else int(top),
        int(edges["w"] * _EMU_PER_INCH) if edges["w"] is not None else int(width),
        int(edges["h"] * _EMU_PER_INCH) if edges["h"] is not None else int(height),
    )


def _apply_slot(spec, given: dict) -> None:
    """The chart's own box. Absent edges keep whatever they had."""
    edges = {k: _num(given.get(k)) for k in ("x", "y", "w", "h")}
    if all(v is None for v in edges.values()):
        return
    spec.content_is_authored = True
    current = getattr(spec, "chart_slot", None)
    if current is None:
        # No slot does not mean no rectangle. Where a template offers us no
        # usable content area — Arla, whose every layout is two-column — the
        # renderer places the chart itself, and THAT is what a drag is amending.
        # Requiring all four numbers here meant dragging such a chart, which
        # sends only x and y, changed nothing at all.
        base_l, base_t, base_w, base_h = effective_content_rect(spec)
        current = Slot(slide_index=-1, left=base_l, top=base_t,
                       width=base_w, height=base_h, name="chart")
    spec.chart_slot = Slot(
        slide_index=current.slide_index,
        left=int(edges["x"] * _EMU_PER_INCH) if edges["x"] is not None else current.left,
        top=int(edges["y"] * _EMU_PER_INCH) if edges["y"] is not None else current.top,
        width=int(edges["w"] * _EMU_PER_INCH) if edges["w"] is not None else current.width,
        height=int(edges["h"] * _EMU_PER_INCH) if edges["h"] is not None else current.height,
        name=current.name)
