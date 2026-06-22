"""SeriesResult — the sole numeric contract every renderer/export reads (design §7)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Cell:
    pct: float | None       # 0..100
    count: float | None
    mean: float | None


@dataclass(frozen=True)
class SeriesResult:
    categories: tuple[str, ...]               # row labels, already in final sort order
    segments: tuple[str, ...]                 # column labels; always includes "Total"
    cells: dict[tuple[str, str], Cell]        # (category, segment) -> Cell
    base_n: dict[str, int]                    # segment -> N  (REQ-C-24h)
    statistic: str                            # "pct" | "count" | "mean"

    def cell(self, category: str, segment: str) -> Cell:
        return self.cells[(category, segment)]
