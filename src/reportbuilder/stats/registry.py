"""Pluggable statistic registry — one register() call per new statistic.

Format helpers and Statistic descriptor are defined here.
Built-in registrations (pct, count, mean, median, sum) live at the bottom of
statistics.py to avoid a circular import.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional
import pandas as pd
from reportbuilder.model.report import NumberFormat


@dataclass(frozen=True)
class Statistic:
    name: str                                    # "pct" | "count" | "mean" | ...
    family: str                                  # "distribution" | "summary"
    fmt_code: Callable[[NumberFormat], str]      # Excel-style number format for data labels
    # distribution stats: value of one cell from its (count, base, fmt); None for summary
    cell_fn: Optional[Callable[[float, int, NumberFormat], float]] = None
    # summary stats: aggregate a CLEAN numeric Series -> float; None for distribution
    summary_fn: Optional[Callable[[pd.Series], float]] = None


STATISTICS: dict[str, Statistic] = {}


def register(s: Statistic) -> None:
    STATISTICS[s.name] = s


def statistic(name: str) -> Statistic:
    try:
        return STATISTICS[name]
    except KeyError:
        raise KeyError(
            f"unknown statistic {name!r}; registered: {sorted(STATISTICS)}"
        )


# ---------------------------------------------------------------------------
# Format helpers (used by built-in registrations and available for new ones)
# ---------------------------------------------------------------------------

def _pct_fmt(fmt: NumberFormat) -> str:
    return "0" + ("." + "0" * fmt.pct_decimals if fmt.pct_decimals else "") + '"%"'


def _dec_fmt(fmt: NumberFormat) -> str:
    return "0" + ("." + "0" * fmt.mean_decimals if fmt.mean_decimals else "")


def _int_fmt(fmt: NumberFormat) -> str:
    return "0"
