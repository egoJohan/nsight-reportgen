"""Category sorting for chart elements (REQ-S-01/02/03, C-26)."""
from __future__ import annotations
from reportbuilder.model.report import SortSpec

_KEY = {"pct": "pct", "count": "count", "mean": "mean", "topbox_sum": "topbox"}
# Stacked-only bases reorder the BARS in the engine; for CATEGORY sorting they carry no
# per-category key, so they keep data order here rather than erroring.
_STACKED_ONLY = {"top3_sum"}


def sort_categories(rows: list[tuple[str, float, dict]], spec: SortSpec) -> list[str]:
    """Return category labels in final order. Each row is (label, code, vals) where
    vals carries {"pct","count","mean","data_index","topbox"}. The engine supplies
    `topbox` (the summed top-box pct from spec.topbox_codes). "data_order" preserves
    data_index; otherwise sort by the basis value, with a stable pre-sort by
    data_index so ties keep data order. (REQ-S-01/02/03, C-26)"""
    if spec.basis == "data_order" or spec.basis in _STACKED_ONLY:
        # data_order, or a stacked-only basis (e.g. top3_sum) that doesn't apply to these
        # categories → keep data order (the bar reorder happens in the engine).
        ordered = sorted(rows, key=lambda r: r[2]["data_index"])
        return [r[0] for r in ordered]
    key = _KEY[spec.basis]
    base = sorted(rows, key=lambda r: r[2]["data_index"])
    ordered = sorted(base, key=lambda r: r[2][key], reverse=spec.descending)
    return [r[0] for r in ordered]
