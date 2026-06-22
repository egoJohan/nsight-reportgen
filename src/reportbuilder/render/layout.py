"""Native-chart layout solver: compute c:manualLayout coords (design §9a step 1)."""
from __future__ import annotations
from dataclasses import dataclass

# Rough average glyph advance as a fraction of em; deterministic, no font metrics needed.
_CHAR_EM = 0.55
_CHART_WIDTH_IN = 7.5

@dataclass(frozen=True)
class PlotLayout:
    x: float
    y: float
    w: float
    h: float

@dataclass(frozen=True)
class LayoutResult:
    plot: PlotLayout
    legend: PlotLayout

def measure_label_width(text: str, point_size: int) -> float:
    inches = len(text) * point_size * _CHAR_EM / 72.0
    return inches / _CHART_WIDTH_IN

def solve_column_layout(
    categories: tuple[str, ...],
    legend_labels: tuple[str, ...],
    *,
    point_size: int = 10,
) -> LayoutResult:
    legend_w = min(0.35, max(
        0.08,
        max((measure_label_width(s, point_size) for s in legend_labels), default=0.08) + 0.03,
    ))
    left_margin = 0.06
    top_margin = 0.12          # title band
    bottom_margin = 0.14       # category axis labels
    gap = 0.02
    plot_w = max(0.1, 1.0 - left_margin - legend_w - gap)
    plot = PlotLayout(
        x=left_margin, y=top_margin,
        w=plot_w, h=max(0.1, 1.0 - top_margin - bottom_margin),
    )
    legend = PlotLayout(
        x=plot.x + plot.w + gap, y=top_margin,
        w=legend_w, h=plot.h,
    )
    return LayoutResult(plot=plot, legend=legend)
