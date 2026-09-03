"""A template, resolved once.

Every preview and every deck slide needs the same answers about a template —
where its chart goes, what its palette is, what face and size its headline is in
— and each answer used to cost a full `.pptx` parse plus a font measurement,
*per slide*. A 60-slide deck paid for all of it 60 times, which is most of why
opening a report made the rest of the page stop answering.

Two costs are removed here rather than cached around:

  * `load_style_spec` opens the file, walks every layout through
    `inspect_template` and harvests a slide through `extract_profile`.
  * `build_spec` measures the title and subtitle faces, loading a TTF through
    PIL to do it. `slide_chrome` called it per slide, passing a font it read off
    that slide's own title placeholder — but every chart slide is built from the
    same layout, so the face is a property of the TEMPLATE. It is settled here,
    before any slide exists, and those call sites become reads.

Resolution is a pure function of the file's bytes, so it is cached on identity:
path plus size plus mtime. A re-uploaded template is a different file by that
key and re-resolves on its own; nothing has to remember to invalidate it.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from functools import lru_cache

from reportbuilder.render.resolved_style import TemplateSpec, build_spec
from reportbuilder.render.style_spec import TemplateStyleSpec, load_style_spec

# Placeholder types that hold a slide headline (PP_PLACEHOLDER.TITLE and
# .CENTER_TITLE). Compared by value so this does not import the enum just to
# name two integers.
_TITLE_PLACEHOLDERS = (13, 1)


@dataclass(frozen=True)
class ResolvedTemplate:
    """Everything a render needs to know about a template."""

    style: TemplateStyleSpec
    spec: TemplateSpec


def _layout_title_font(template_path: str, layout_index: int | None) -> str:
    """The face this template gives a slide headline.

    `slide_chrome` used to ask this per slide, off the slide's own placeholder.
    Every chart slide is built from the same layout, so the answer is a property
    of the template and is settled here, once.

    Returns "" when the template cannot say, which is what `build_spec` already
    treats as "fall back to the theme's heading font".
    """
    # No usable layout: the design was harvested off a slide instead, and the
    # harvested profile already carries the title's face for build_spec.
    if layout_index is None:
        return ""
    try:
        from pptx import Presentation

        from reportbuilder.render.image.fast_preview import (
            _inherited_placeholder_style,
        )

        layout = Presentation(template_path).slide_layouts[layout_index]
        for ph in layout.placeholders:
            if ph.placeholder_format.type in _TITLE_PLACEHOLDERS:
                return _inherited_placeholder_style(ph)[0] or ""
    except Exception:  # noqa: BLE001 — styling must never break a render
        pass
    return ""


@lru_cache(maxsize=16)
def _resolve(path: str, size: int, mtime_ns: int) -> ResolvedTemplate:
    # size/mtime_ns are never read: they are the cache identity. A file whose
    # bytes changed has a different key and lands here again.
    style = load_style_spec(path)
    spec = build_spec(
        style, title_font=_layout_title_font(path, style.chart_layout_index))
    # The compositor and slide_chrome are handed a style, not a ResolvedTemplate,
    # at a lot of call sites. Letting the spec travel with the style is what
    # turns their per-slide build_spec calls into reads without threading a new
    # argument through all of them.
    style.resolved_spec = spec
    return ResolvedTemplate(style=style, spec=spec)


def resolve(template_path: str) -> ResolvedTemplate:
    """The resolved template at *template_path*, computed once per file.

    Concurrent first callers may both compute it — FastAPI runs sync endpoints in
    a threadpool. That is harmless: the result is a value, not a resource.
    """
    st = os.stat(template_path)
    return _resolve(template_path, st.st_size, st.st_mtime_ns)


def style_with_overrides(template_path: str, overrides: dict | None):
    """The resolved style, with an author's corrections applied to a COPY.

    `resolve` is cached on the file, and the corrections are not in the file —
    they are stored per template, and one customer's are not another's. Mutating
    the cached style would serve the first caller's corrections to everybody
    who renders on that template afterwards.
    """
    from reportbuilder.render.style_spec import apply_template_overrides

    style = resolve(template_path).style
    if not overrides:
        return style
    style = copy.deepcopy(style)
    apply_template_overrides(style, overrides)
    return style
