"""The house-style template.

Templates resolve report -> tutkimus -> asiakas -> THIS. Making the default a
real .pptx rather than a special case in the renderer means one code path: every
deck is rendered into some template, and "no template chosen" simply selects
this one. A branch for "no template" would be a second rendering path that only
the default exercises, and it would drift.

It encodes what render/house_style.py already draws — cream ground, teal
series, ink text — as a theme, so template_check reads it back exactly as it
reads a client's brand.
"""
from __future__ import annotations

from lxml import etree
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.render import house_style as hs

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

# The chart series palette, in the order a multi-series chart consumes it.
# Teal leads because a single-series chart is the common case and teal is the
# house colour; the alternating light variants keep adjacent bands legible.
_ACCENTS = [hs.TEAL, hs.TEAL_LT, hs.BLUE, hs.BLUE_LT, hs.RED, hs.RED_LT]

# Liberation Sans is what house_style registers for matplotlib and is present on
# the render host, so the deck and the chart images inside it agree. Naming a
# font the host lacks is the failure mode this avoids.
_HEADING_FONT = "Liberation Sans"
_BODY_FONT = "Liberation Sans"


def _hex(value: str) -> str:
    return value.lstrip("#").upper()


def _set_scheme(theme_root) -> None:
    """Overwrite the theme's colour and font scheme with the house style."""
    scheme = theme_root.find(f".//{{{_A}}}themeElements/{{{_A}}}clrScheme")
    if scheme is not None:
        for i, colour in enumerate(_ACCENTS, start=1):
            el = scheme.find(f"{{{_A}}}accent{i}")
            if el is None:
                continue
            for child in list(el):
                el.remove(child)
            srgb = etree.SubElement(el, f"{{{_A}}}srgbClr")
            srgb.set("val", _hex(colour))
        # dk1/lt1 drive default text and background, so the deck reads as the
        # house style even before a chart is placed.
        for tag, colour in (("dk1", hs.INK), ("lt1", hs.CREAM)):
            el = scheme.find(f"{{{_A}}}{tag}")
            if el is None:
                continue
            for child in list(el):
                el.remove(child)
            srgb = etree.SubElement(el, f"{{{_A}}}srgbClr")
            srgb.set("val", _hex(colour))

    fonts = theme_root.find(f".//{{{_A}}}themeElements/{{{_A}}}fontScheme")
    if fonts is not None:
        for kind, name in (("majorFont", _HEADING_FONT), ("minorFont", _BODY_FONT)):
            latin = fonts.find(f"{{{_A}}}{kind}/{{{_A}}}latin")
            if latin is not None:
                latin.set("typeface", name)


def build_default_template(path: str) -> str:
    """Write the house-style template to *path*; return the path.

    Built from python-pptx's blank presentation, whose layout 6 IS blank and
    whose layout 1 is Title and Content — so the result satisfies
    template_check's requirement (a title plus a large content placeholder)
    the same way a client template does, rather than by exception.
    """
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    master = prs.slide_master.part
    for rel in master.rels.values():
        if "theme" in rel.reltype:
            root = etree.fromstring(rel.target_part.blob)
            _set_scheme(root)
            rel.target_part._blob = etree.tostring(root, xml_declaration=True,
                                                   encoding="UTF-8", standalone=True)
            break

    prs.save(path)
    return path
