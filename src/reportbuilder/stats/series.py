"""SeriesResult — the sole numeric contract every renderer/export reads (design §7)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Cell:
    pct: float | None = None        # 0..100
    count: float | None = None
    mean: float | None = None
    extra: tuple[tuple[str, float | None], ...] = ()  # registered non-core stat values

    def value(self, stat: str) -> float | None:
        """Return the cell value for the given statistic name."""
        if stat in ("pct", "count", "mean"):
            return getattr(self, stat)
        return dict(self.extra).get(stat)


@dataclass(frozen=True)
class SeriesResult:
    categories: tuple[str, ...]               # row labels, already in final sort order
    segments: tuple[str, ...]                 # column labels; always includes "Total"
    cells: dict[tuple[str, str], Cell]        # (category, segment) -> Cell
    base_n: dict[str, int]                    # segment -> N  (REQ-C-24h)
    statistic: str                            # "pct" | "count" | "mean"

    def cell(self, category: str, segment: str) -> Cell:
        return self.cells[(category, segment)]
