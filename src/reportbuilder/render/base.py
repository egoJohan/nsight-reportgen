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

@dataclass
class RenderContext:
    slide: Any            # python-pptx slide
    slot: Slot
    style: StyleSpec
    spec: ChartSpec
    series: SeriesResult
    fmt: NumberFormat

class ChartRenderer(Protocol):
    def render(self, ctx: RenderContext) -> None: ...
