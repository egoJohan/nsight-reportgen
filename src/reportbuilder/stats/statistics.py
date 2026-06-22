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
