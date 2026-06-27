"""Chart-type ids + native/image capability table (REQ-C-13, design §9a)."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class ChartType(str, Enum):
    LINE = "line"
    PIE = "pie"
    VERTICAL_BAR = "vertical_bar"
    STACKED_VERTICAL_BAR = "stacked_vertical_bar"
    HORIZONTAL_BAR = "horizontal_bar"
    STACKED_HORIZONTAL_BAR = "stacked_horizontal_bar"
    RADAR = "radar"
    DOUGHNUT = "doughnut"
    SCATTER = "scatter"
    FUNNEL = "funnel"
    COMBO = "combo"
    WORDCLOUD = "wordcloud"


@dataclass(frozen=True)
class Capability:
    native: bool
    native_kind: str   # "own" | "stacked_bar_approx" | "none"
    image: bool


_OWN = Capability(native=True, native_kind="own", image=True)

CAPABILITIES: dict[ChartType, Capability] = {
    ChartType.LINE: _OWN,
    ChartType.PIE: _OWN,
    ChartType.VERTICAL_BAR: _OWN,
    ChartType.STACKED_VERTICAL_BAR: _OWN,
    ChartType.HORIZONTAL_BAR: _OWN,
    ChartType.STACKED_HORIZONTAL_BAR: _OWN,
    ChartType.RADAR: _OWN,
    ChartType.DOUGHNUT: _OWN,
    ChartType.SCATTER: _OWN,
    ChartType.FUNNEL: Capability(native=True, native_kind="stacked_bar_approx", image=True),
    ChartType.COMBO: Capability(native=False, native_kind="none", image=True),
    # Word cloud is image-only (no native OOXML equivalent), like combo (Task J).
    ChartType.WORDCLOUD: Capability(native=False, native_kind="none", image=True),
}


def supports(chart_type: ChartType, mode: str) -> bool:
    cap = CAPABILITIES[chart_type]
    if mode == "native":
        return cap.native
    if mode == "image":
        return cap.image
    raise ValueError(f"unknown mode: {mode!r}")
