"""Statistics-engine orchestrator: compute(question, spec, data, model) -> SeriesResult.

Ties together aggregate_counts, base rules, statistics helpers, and sort into the
SeriesResult — the spine output (R1). REQ-C-14/15/16, M-03.
"""
from __future__ import annotations
import pandas as pd
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec
from reportbuilder.stats.aggregate import aggregate_counts
from reportbuilder.stats.base_rules import single_base, multi_base, segment_bases
from reportbuilder.stats.series import Cell, SeriesResult
from reportbuilder.stats.sorting import sort_categories
from reportbuilder.stats.statistics import pct, count_value


def _single(question: Question, spec: ChartSpec, data: pd.DataFrame,
            model: QuestionModel) -> SeriesResult:
    var = model.variable(question.variables[0])
    labels = {vl.value: vl.label for vl in var.value_labels
              if vl.value not in var.missing_values}
    if spec.classifying_var:
        bases = segment_bases(data, var, spec.classifying_var)
    else:
        bases = {"Total": single_base(data, var)}
    counts = aggregate_counts(data, var.name, spec.classifying_var)
    segments = tuple(s for s in bases if s != "Total")
    segments = (*segments, "Total") if segments else ("Total",)

    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    for idx, (code, label) in enumerate(labels.items()):
        for seg in segments:
            c = counts.get((code, seg), 0)
            base = bases.get(seg, 0)
            cells[(label, seg)] = Cell(pct=pct(c, base, spec.number_format),
                                       count=count_value(c, spec.number_format),
                                       mean=None)
        total_cell = cells[(label, "Total")]
        rows.append((label, code, {"pct": total_cell.pct, "count": total_cell.count,
                                   "mean": 0.0, "data_index": idx,
                                   "topbox": total_cell.pct}))
    categories = tuple(sort_categories(rows, spec.sort))
    return SeriesResult(categories=categories, segments=segments, cells=cells,
                        base_n={s: bases.get(s, 0) for s in segments},
                        statistic=spec.statistic)


def _multi(question: Question, spec: ChartSpec, data: pd.DataFrame,
           model: QuestionModel) -> SeriesResult:
    vars_ = [model.variable(n) for n in question.variables]
    base = multi_base(data, vars_)
    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    for idx, v in enumerate(vars_):
        s = pd.to_numeric(data[v.name], errors="coerce")
        c = int(((s == 1.0) & ~s.isin(v.missing_values)).sum())
        cells[(v.label, "Total")] = Cell(pct=pct(c, base, spec.number_format),
                                         count=count_value(c, spec.number_format), mean=None)
        cell = cells[(v.label, "Total")]
        rows.append((v.label, float(idx), {"pct": cell.pct, "count": cell.count,
                                           "mean": 0.0, "data_index": idx, "topbox": cell.pct}))
    categories = tuple(sort_categories(rows, spec.sort))
    return SeriesResult(categories=categories, segments=("Total",), cells=cells,
                        base_n={"Total": base}, statistic=spec.statistic)


def compute(question: Question, spec: ChartSpec, data: pd.DataFrame,
            model: QuestionModel) -> SeriesResult:
    """Compute the SeriesResult for one question + chart spec (R1 spine)."""
    if question.kind == "multi":
        return _multi(question, spec, data, model)
    return _single(question, spec, data, model)
