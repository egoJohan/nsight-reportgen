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
    # Optional caption rendered under the chart — e.g. the endpoint legend of a
    # partially-labelled numeric scale ("1 = täysin eri mieltä · 7 = …"). (REQ-C-24c)
    caption: str | None = None

    def cell(self, category: str, segment: str) -> Cell:
        return self.cells[(category, segment)]

    @property
    def n_series(self) -> int:
        """Number of segments (series). 1 = a single overall series."""
        return len(self.segments)

    def is_partition(self, segment: str | None = None, *, tol: float = 1.0) -> bool:
        """True when *segment*'s categories partition its base: every counted
        unit falls in exactly one category (mutually exclusive AND exhaustive).

        This is the structural precondition for a pie/doughnut — "parts of one
        whole". Because the multi-response base is "respondents with >=1
        selection" (not total selections), a partition is exactly: the category
        counts sum to the base.  Single-choice questions satisfy this by
        construction; a multi-response set satisfies it only when respondents
        effectively chose one option (no overlap).

        Prefers exact integer counts; falls back to the percentage shares
        (sum ~= 100%) when counts are absent.  ``tol`` absorbs float/rounding
        noise only — it is not slack for genuine overlap.
        """
        seg = segment if segment is not None else (
            self.segments[0] if self.segments else None
        )
        if seg is None:
            return False
        base = self.base_n.get(seg)
        if not base:
            return False
        counts: list[float | None] = []
        pcts: list[float | None] = []
        for cat in self.categories:
            cell = self.cells.get((cat, seg))
            if cell is None:
                return False
            counts.append(cell.count)
            pcts.append(cell.pct)
        if counts and all(c is not None for c in counts):
            return abs(sum(counts) - base) <= tol  # type: ignore[arg-type]
        if pcts and all(p is not None for p in pcts):
            return abs(sum(pcts) - 100.0) <= tol  # type: ignore[arg-type]
        return False
