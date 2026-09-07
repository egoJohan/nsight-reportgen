"""Category sorting for chart elements (REQ-S-01/02/03, C-26)."""
from __future__ import annotations
from reportbuilder.model.report import SortSpec

_KEY = {"pct": "pct", "count": "count", "mean": "mean", "topbox_sum": "topbox"}
# Stacked-only bases reorder the BARS in the engine; for CATEGORY sorting they carry no
# per-category key, so they keep data order here rather than erroring.
_STACKED_ONLY = {"top3_sum", "bottom2_sum", "bottom3_sum"}


def sort_categories(rows: list[tuple[str, float, dict]], spec: SortSpec) -> list[str]:
    """Return category labels in final order. Each row is (label, code, vals) where
    vals carries {"pct","count","mean","data_index","topbox"}. The engine supplies
    `topbox` (the summed top-box pct from spec.topbox_codes). "data_order" preserves
    data_index; otherwise sort by the basis value, with a stable pre-sort by
    data_index so ties keep data order. (REQ-S-01/02/03, C-26)"""
    # "manual" is data order over a REWRITTEN data_index: the author's drag is
    # applied where the full labels are still in scope (`manual_reindex`), so by
    # the time rows reach here the order they asked for IS the data order. That
    # is what carries it into every builder and every chart family at once.
    if spec.basis in ("data_order", "manual") or spec.basis in _STACKED_ONLY:
        # data_order, or a stacked-only basis (e.g. top3_sum) that doesn't apply to these
        # categories → keep data order (the bar reorder happens in the engine).
        ordered = sorted(rows, key=lambda r: r[2]["data_index"])
        return [r[0] for r in ordered]
    key = _KEY[spec.basis]
    base = sorted(rows, key=lambda r: r[2]["data_index"])
    ordered = sorted(base, key=lambda r: r[2][key], reverse=spec.descending)
    return [r[0] for r in ordered]


def apply_manual_order(rows, full_labels, spec: SortSpec):
    """Rewrite each row's `data_index` to the order the author dragged.

    `rows` are the (label, code, vals) triples every builder already assembles,
    and `full_labels` runs parallel to them carrying each one's STORED identity
    — the label the order was written against, before any display override, so
    shortening a category does not move it.

    Rewriting the index rather than sorting here is deliberate. `data_index` is
    what every builder already orders by, and several paths deliberately force
    "data_order": a partially-labelled scale, and a stacked rating scale, both
    because a FREQUENCY sort would scramble the scale. An author dragging items
    is not a frequency sort — it is an instruction — so re-indexing makes those
    paths honour it without being taught anything.

    Categories the order does not name keep their relative data order BEHIND the
    ones it does: a re-imported dataset carrying a new option must still draw it.
    A name the data no longer has is simply absent, and costs nothing.
    """
    if spec.basis != "manual" or not spec.manual_order:
        return rows
    rank = {label: i for i, label in enumerate(spec.manual_order)}
    unnamed = sorted((i for i, full in enumerate(full_labels) if full not in rank),
                     key=lambda i: rows[i][2]["data_index"])
    behind = {i: len(rank) + k for k, i in enumerate(unnamed)}
    out = []
    for i, ((label, code, vals), full) in enumerate(zip(rows, full_labels)):
        placed = rank[full] if full in rank else behind[i]
        out.append((label, code, {**vals, "data_index": placed}))
    return out
