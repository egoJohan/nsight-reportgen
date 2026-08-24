"""A pie asked for counts has to print counts.

matplotlib hands `autopct` the wedge's PERCENTAGE, and that number was being
formatted and printed whatever statistic the author chose. With `count` the
formatter drops the "%" sign and rounds to a whole number, so a wedge holding
300 respondents printed "30" — a percentage wearing a count's clothes, on a
chart whose legend and n= footer both say counts. Nothing about it looks wrong.
"""
from __future__ import annotations

from reportbuilder.render.image.pie import _build_pie_figure
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import make_ctx


def _series(counts: dict[str, float], statistic: str) -> SeriesResult:
    total = sum(counts.values())
    cells = {(c, "Total"): Cell(pct=n / total * 100.0, count=n, mean=None)
             for c, n in counts.items()}
    return SeriesResult(categories=tuple(counts), segments=("Total",), cells=cells,
                        base_n={"Total": total}, statistic=statistic)


def _wedge_labels(statistic: str) -> list[str]:
    counts = {"Kyllä": 300.0, "Ei": 500.0, "En osaa sanoa": 200.0}
    series = _series(counts, statistic)
    _prs, _slide, _slot, ctx = make_ctx("pie", series, statistic=statistic)
    fig = _build_pie_figure(ctx, donut=False)
    return [t.get_text() for ax in fig.axes for t in ax.texts if t.get_text()]


def test_a_count_pie_labels_wedges_with_the_counts():
    assert _wedge_labels("count") == ["300", "500", "200"]


def test_a_percentage_pie_is_unchanged():
    assert _wedge_labels("pct") == ["30 %", "50 %", "20 %"]
