"""Statistics helpers: pct, count_value, mean. (REQ-N-01/02/03, REQ-C-15)"""
from __future__ import annotations
import math
import pandas as pd
from reportbuilder.model.question import Variable
from reportbuilder.model.report import NumberFormat


def pct(count: float, base: int, fmt: NumberFormat) -> float:
    """Percentage 0..100, rounded to fmt.pct_decimals. (REQ-N-01)"""
    if not base:
        return 0.0
    return round(count / base * 100.0, fmt.pct_decimals)


def count_value(count: float, fmt: NumberFormat) -> float:
    """Integer count; round UP (ceil) if fmt.count_round_up else round-to-nearest. (REQ-N-03)"""
    return float(math.ceil(count) if fmt.count_round_up else round(count))


def mean(values: pd.Series, var: Variable, fmt: NumberFormat) -> float:
    """Mean over valid (non-missing) numeric values, rounded to fmt.mean_decimals. (REQ-N-02)"""
    s = pd.to_numeric(values, errors="coerce")
    s = s[s.notna() & ~s.isin(var.missing_values)]
    return round(float(s.mean()), fmt.mean_decimals) if len(s) else 0.0


def summary_value(values: pd.Series, var: Variable, fmt: NumberFormat, stat) -> float:
    """Aggregate a series using stat.summary_fn, excluding missing/NaN values. (REQ-C-15)"""
    s = pd.to_numeric(values, errors="coerce")
    s = s[s.notna() & ~s.isin(var.missing_values)]
    return round(float(stat.summary_fn(s)), fmt.mean_decimals) if len(s) else 0.0


# ---------------------------------------------------------------------------
# Built-in statistic registrations (done here to avoid circular imports —
# registry.py must not import from statistics.py).
# ---------------------------------------------------------------------------
from reportbuilder.stats.registry import (  # noqa: E402
    Statistic, register, _pct_fmt, _dec_fmt, _int_fmt,
)

register(Statistic(
    "pct", "distribution", _pct_fmt,
    cell_fn=lambda c, base, fmt: pct(c, base, fmt),
))
register(Statistic(
    "count", "distribution", _int_fmt,
    cell_fn=lambda c, base, fmt: count_value(c, fmt),
))
register(Statistic(
    "mean", "summary", _dec_fmt,
    summary_fn=lambda s: float(s.mean()),
))
register(Statistic(
    "median", "summary", _dec_fmt,
    summary_fn=lambda s: float(s.median()),
))
register(Statistic(
    "sum", "summary", _dec_fmt,
    summary_fn=lambda s: float(s.sum()),
))
