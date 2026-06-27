"""Statistics-engine orchestrator: compute(question, spec, data, model) -> SeriesResult.

Ties together aggregate_counts, base rules, statistics helpers, and sort into the
SeriesResult — the spine output (R1). REQ-C-14/15/16, M-03.
"""
from __future__ import annotations
import pandas as pd
from reportbuilder.model.question import Question, QuestionModel, Variable
from reportbuilder.model.report import ChartSpec
from reportbuilder.stats.aggregate import aggregate_counts
from reportbuilder.stats.base_rules import single_base, multi_base, segment_bases
from reportbuilder.stats.registry import statistic as get_statistic
from reportbuilder.stats.series import Cell, SeriesResult
from reportbuilder.stats.sorting import sort_categories
from reportbuilder.stats.statistics import pct, count_value, summary_value
# Import statistics module to trigger built-in registrations
import reportbuilder.stats.statistics  # noqa: F401

# Label used for the aggregated missing-values bucket (REQ-D-06, MV).
# Module constant so it can be imported by tests and localised in future.
NOT_ANSWERED_LABEL: str = "Not answered"


def _summary(question: Question, spec: ChartSpec, data: pd.DataFrame,
             model: QuestionModel, stat) -> SeriesResult:
    """Compute a summary-statistic SeriesResult — one category × segments.

    Works for any registered summary statistic (mean, median, sum, …).
    For mean: stores value in the named `mean` field for backward-compat.
    For others: stores in cell.extra so cell.value(stat.name) retrieves it.
    (REQ-C-15, REQ-N-02)
    """
    var = model.variable(question.variables[0])   # single var; multi: first var
    label = question.text or var.label
    fmt = spec.number_format
    if spec.classifying_var:
        bases = segment_bases(data, var, spec.classifying_var)   # {"Total":N, "1":N, ...}
        seg_codes = pd.to_numeric(data[spec.classifying_var], errors="coerce")
        segments = tuple(s for s in bases if s != "Total") + ("Total",)
        cells: dict[tuple[str, str], Cell] = {}
        for seg in segments:
            vals = (data[var.name] if seg == "Total"
                    else data.loc[seg_codes == float(seg), var.name])
            v = summary_value(vals, var, fmt, stat)
            if stat.name == "mean":
                cells[(label, seg)] = Cell(pct=None, count=None, mean=v)
            else:
                cells[(label, seg)] = Cell(pct=None, count=None, mean=None,
                                           extra=((stat.name, v),))
        base_n = {s: bases.get(s, 0) for s in segments}
    else:
        segments = ("Total",)
        vals = data[var.name]
        v = summary_value(vals, var, fmt, stat)
        if stat.name == "mean":
            cells = {(label, "Total"): Cell(pct=None, count=None, mean=v)}
        else:
            cells = {(label, "Total"): Cell(pct=None, count=None, mean=None,
                                            extra=((stat.name, v),))}
        base_n = {"Total": single_base(data, var)}
    return SeriesResult(categories=(label,), segments=segments, cells=cells,
                        base_n=base_n, statistic=stat.name)


def _cell_is_zero(cell: Cell | None) -> bool:
    """True when a category cell carries no value (0 pct AND 0 count). Used to
    detect empty (0%) categories for show_empty_categories=False. (REQ-options)"""
    if cell is None:
        return True
    pct_zero = cell.pct in (0, 0.0) or cell.pct is None
    count_zero = cell.count in (0, 0.0) or cell.count is None
    return pct_zero and count_zero


def _effective_missing(spec: ChartSpec, var: Variable) -> set[float]:
    """Resolve the effective "Not answered" code set.

    When spec.not_answered_codes is provided (not None) it overrides the
    SAV-detected user-missing set; otherwise the variable's own missing_values
    is used. System-missing/NaN is always treated as "Not answered" on top of
    this set. (REQ-D-06)
    """
    codes = getattr(spec, "not_answered_codes", None)
    if codes is not None:
        return set(codes)
    return set(var.missing_values)


def _missing_counts(data: pd.DataFrame, var: Variable, eff: set[float],
                    classifying_var: str | None = None) -> dict[str, int]:
    """Count sysmis + "not answered" rows per segment using the effective set.

    Returns a dict of {segment_label: count}. Always includes "Total".
    For segmented data the per-segment count only considers rows whose
    classifying variable has a valid (non-NaN) code — consistent with the
    segment_bases convention. (REQ-D-06, REQ-MV-01, REQ-MV-02)
    """
    s = pd.to_numeric(data[var.name], errors="coerce")
    missing_mask = s.isna() | s.isin(eff)
    result: dict[str, int] = {"Total": int(missing_mask.sum())}
    if classifying_var is not None:
        seg = pd.to_numeric(data[classifying_var], errors="coerce")
        for code in sorted(seg.dropna().unique()):
            seg_label = str(int(code)) if float(code).is_integer() else str(code)
            result[seg_label] = int((missing_mask & (seg == code)).sum())
    return result


def _single(question: Question, spec: ChartSpec, data: pd.DataFrame,
            model: QuestionModel) -> SeriesResult:
    var = model.variable(question.variables[0])
    eff = _effective_missing(spec, var)
    overrides = spec.label_override_map() if hasattr(spec, "label_override_map") else {}
    show_empty: bool = getattr(spec, "show_empty_categories", True)
    labels = {vl.value: vl.label for vl in var.value_labels
              if vl.value not in eff}
    if spec.classifying_var:
        bases = segment_bases(data, var, spec.classifying_var)
    else:
        bases = {"Total": single_base(data, var)}
    counts = aggregate_counts(data, var.name, spec.classifying_var)
    segments = tuple(s for s in bases if s != "Total")
    segments = (*segments, "Total") if segments else ("Total",)

    # When show_not_answered is True, recompute over total (valid + missing). (REQ-D-06, MV)
    show_na: bool = getattr(spec, "show_not_answered", False)
    if show_na:
        missing_n = _missing_counts(data, var, eff, spec.classifying_var)
        denom = {seg: bases.get(seg, 0) + missing_n.get(seg, 0) for seg in segments}
    else:
        denom = {seg: bases.get(seg, 0) for seg in segments}

    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    for idx, (code, label) in enumerate(labels.items()):
        display = overrides.get(label, label)
        for seg in segments:
            c = counts.get((code, seg), 0)
            base = denom.get(seg, 0)
            cells[(display, seg)] = Cell(pct=pct(c, base, spec.number_format),
                                         count=count_value(c, spec.number_format),
                                         mean=None)
        total_cell = cells[(display, "Total")]
        rows.append((display, code, {"pct": total_cell.pct, "count": total_cell.count,
                                     "mean": 0.0, "data_index": idx,
                                     "topbox": total_cell.pct}))

    # Hide empty (0%) categories: drop any row that is 0 across ALL segments. (show_empty_categories)
    if not show_empty:
        kept = []
        for r in rows:
            disp = r[0]
            all_zero = all(_cell_is_zero(cells.get((disp, seg))) for seg in segments)
            if all_zero:
                for seg in segments:
                    cells.pop((disp, seg), None)
            else:
                kept.append(r)
        rows = kept

    categories: list[str] = list(sort_categories(rows, spec.sort))

    if show_na:
        # Append "Not answered" last — after all real sorted categories.
        na_display = overrides.get(NOT_ANSWERED_LABEL, NOT_ANSWERED_LABEL)
        na_total = missing_n.get("Total", 0)
        # Suppress a 0-count "Not answered" bucket when empty categories are hidden.
        if show_empty or na_total != 0:
            for seg in segments:
                mc = missing_n.get(seg, 0)
                base = denom.get(seg, 0)
                cells[(na_display, seg)] = Cell(
                    pct=pct(mc, base, spec.number_format),
                    count=count_value(mc, spec.number_format),
                    mean=None,
                )
            categories.append(na_display)

    return SeriesResult(categories=tuple(categories), segments=segments, cells=cells,
                        base_n={s: denom.get(s, 0) for s in segments},
                        statistic=spec.statistic)


def _multi(question: Question, spec: ChartSpec, data: pd.DataFrame,
           model: QuestionModel) -> SeriesResult:
    vars_ = [model.variable(n) for n in question.variables]
    overrides = spec.label_override_map() if hasattr(spec, "label_override_map") else {}
    show_empty: bool = getattr(spec, "show_empty_categories", True)
    base = multi_base(data, vars_)
    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    for idx, v in enumerate(vars_):
        display = overrides.get(v.label, v.label)
        s = pd.to_numeric(data[v.name], errors="coerce")
        c = int(((s == 1.0) & ~s.isin(v.missing_values)).sum())
        cells[(display, "Total")] = Cell(pct=pct(c, base, spec.number_format),
                                         count=count_value(c, spec.number_format), mean=None)
        cell = cells[(display, "Total")]
        rows.append((display, float(idx), {"pct": cell.pct, "count": cell.count,
                                           "mean": 0.0, "data_index": idx, "topbox": cell.pct}))

    # Hide empty (0%) members when show_empty_categories is False.
    if not show_empty:
        kept = []
        for r in rows:
            disp = r[0]
            if _cell_is_zero(cells.get((disp, "Total"))):
                cells.pop((disp, "Total"), None)
            else:
                kept.append(r)
        rows = kept

    categories = tuple(sort_categories(rows, spec.sort))
    return SeriesResult(categories=categories, segments=("Total",), cells=cells,
                        base_n={"Total": base}, statistic=spec.statistic)


def compute(question: Question, spec: ChartSpec, data: pd.DataFrame,
            model: QuestionModel) -> SeriesResult:
    """Compute the SeriesResult for one question + chart spec (R1 spine)."""
    stat = get_statistic(spec.statistic)   # clear KeyError if unregistered
    if stat.family == "summary":
        return _summary(question, spec, data, model, stat)
    if question.kind == "multi":
        return _multi(question, spec, data, model)
    return _single(question, spec, data, model)
