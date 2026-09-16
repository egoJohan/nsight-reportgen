"""Rendering contracts: Slot, StyleSpec, RenderContext, ChartRenderer (design §9)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol
from reportbuilder.model.report import ChartSpec, NumberFormat
from reportbuilder.stats.series import SeriesResult

@dataclass(frozen=True)
class Slot:
    slide_index: int
    left: int
    top: int
    width: int
    height: int
    name: str

_DEFAULT_PALETTE = ["1F77B4", "FF7F0E", "2CA02C", "D62728", "9467BD", "8C564B", "E377C2", "7F7F7F"]

class StyleSpec:
    """Base style spec; Phase 5 TemplateStyleSpec overrides from a template PPT."""
    def font_for(self, element_class: str) -> tuple[str, int]:
        return ("Arial", 10)

    def color_for(self, series_index: int) -> str:
        return _DEFAULT_PALETTE[series_index % len(_DEFAULT_PALETTE)]

@dataclass(frozen=True)
class RenderNote:
    """Something the AUTHOR should be told about a render.

    Raised in the editor, on the warning button and the slide-item icon, like
    every other slide problem — never printed on the slide. A deck handed to a
    client does not explain its own compromises; the person who can still fix
    them is the only one who needs to know. (Johan, 2026-09-16)

    `count` is whatever the note counts — categories left unlabelled, say — and
    0 when it counts nothing.
    """
    kind: str
    count: int = 0


@dataclass
class RenderContext:
    slide: Any            # python-pptx slide
    slot: Slot
    style: StyleSpec
    spec: ChartSpec
    series: SeriesResult
    fmt: NumberFormat
    title: str = ""       # chart title text (Task 5.14)
    #: Where a builder records what the author should be told. None means
    #: nobody is collecting — the deck export does not ask — so a builder must
    #: never require it. See `note`.
    notes: list[RenderNote] | None = None

def note(ctx: RenderContext, kind: str, count: int = 0) -> None:
    """Record a `RenderNote` on *ctx*, if anyone is collecting.

    A no-op otherwise, deliberately: the deck export renders the same charts and
    has nobody to tell, and a builder that had to check for itself would either
    grow a guard at every call site or crash the export the first time one was
    forgotten.
    """
    if ctx.notes is not None:
        ctx.notes.append(RenderNote(kind=kind, count=count))


class ChartRenderer(Protocol):
    def render(self, ctx: RenderContext) -> None: ...
