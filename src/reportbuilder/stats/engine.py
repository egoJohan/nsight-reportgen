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

# Task G.3: actionable message raised when a non-chartable (open-ended text)
# question reaches the engine, instead of a cryptic "could not convert string
# to float" further down the render chain.
TEXT_NOT_CHARTABLE_MSG: str = (
    "This question has open-ended text answers and can't be charted"
)


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


def _auto_pct_decimals(values: list[float | None]) -> int:
    """Decimals auto mode would DISPLAY for these pct values (Task G.4).

    Mirrors the pct branch of render.image._mpl.auto_decimals (kept in sync) so
    the engine can decide whether a category's *displayed* value rounds to zero
    without importing the (matplotlib-heavy) image layer.
    """
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return 0
    all_large = all(v >= 10.0 for v in clean)
    frac_trivial = all(abs(v % 1) < 0.05 for v in clean)
    if all_large or frac_trivial:
        return 0
    sorted_vals = sorted(clean)
    if len(sorted_vals) > 1:
        min_spread = min(b - a for a, b in zip(sorted_vals, sorted_vals[1:]))
    else:
        min_spread = 1.0
    if any(v < 10.0 for v in clean) or min_spread < 1.0:
        return 1
    return 0


def _effective_pct_decimals(values: list[float | None], fmt) -> int:
    """Decimals actually shown for pct given the NumberFormat (auto or manual)."""
    if getattr(fmt, "mode", "auto") == "manual":
        return getattr(fmt, "pct_decimals", 0)
    return _auto_pct_decimals(values)


def _displayed_zero(cell: Cell | None, statistic: str, decimals: int) -> bool:
    """True when the cell's DISPLAYED value rounds to zero (Task G.4).

    For ``count`` the displayed integer rounds to 0; for ``pct`` (and other
    distribution stats) the value rounds to 0 at the effective decimals shown.
    A missing cell is treated as zero. This is what drives the
    show_empty_categories=False hide-empty filter — a tiny-but-nonzero category
    such as 4/1001 → "0 %" is now dropped, while a "0.4 %" (1-decimal) is kept.
    """
    if cell is None:
        return True
    if statistic == "count":
        return cell.count is None or round(float(cell.count)) == 0
    return cell.pct is None or round(float(cell.pct), decimals) == 0


def _drop_displayed_zero_rows(rows, cells, segments, statistic, fmt):
    """Drop rows whose displayed value rounds to 0 across ALL segments (Task G.4).

    Computes the effective per-segment pct decimals from the surviving category
    values (matching how the renderer formats the series), removes the dropped
    cells from ``cells`` in place, and returns the kept rows.
    """
    displays = [r[0] for r in rows]
    seg_dec = {
        seg: _effective_pct_decimals(
            [cells[(d, seg)].pct for d in displays if (d, seg) in cells], fmt
        )
        for seg in segments
    }
    kept = []
    for r in rows:
        disp = r[0]
        if all(
            _displayed_zero(cells.get((disp, seg)), statistic, seg_dec[seg])
            for seg in segments
        ):
            for seg in segments:
                cells.pop((disp, seg), None)
        else:
            kept.append(r)
    return kept


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
        bases = segment_bases(data, var, spec.classifying_var, missing_override=eff)
    else:
        bases = {"Total": single_base(data, var, missing_override=eff)}
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

    # Hide categories whose DISPLAYED value rounds to 0 across ALL segments. (Task G.4)
    if not show_empty:
        rows = _drop_displayed_zero_rows(
            rows, cells, segments, spec.statistic, spec.number_format
        )

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

    # Hide members whose DISPLAYED value rounds to 0 when show_empty is False. (Task G.4)
    if not show_empty:
        rows = _drop_displayed_zero_rows(
            rows, cells, ("Total",), spec.statistic, spec.number_format
        )

    categories = tuple(sort_categories(rows, spec.sort))
    return SeriesResult(categories=categories, segments=("Total",), cells=cells,
                        base_n={"Total": base}, statistic=spec.statistic)


def compute(question: Question, spec: ChartSpec, data: pd.DataFrame,
            model: QuestionModel) -> SeriesResult:
    """Compute the SeriesResult for one question + chart spec (R1 spine)."""
    # Task G.3: open-ended text questions have no numeric basis — fail early with
    # an actionable message instead of a cryptic float-conversion error downstream.
    qvars = [model.variable(n) for n in question.variables]
    if qvars and all(v.measurement == "text" for v in qvars):
        raise ValueError(TEXT_NOT_CHARTABLE_MSG)
    stat = get_statistic(spec.statistic)   # clear KeyError if unregistered
    if stat.family == "summary":
        return _summary(question, spec, data, model, stat)
    if question.kind == "multi":
        return _multi(question, spec, data, model)
    return _single(question, spec, data, model)
