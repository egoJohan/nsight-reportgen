"""Findings for an AI slide title, for series that have no overall Total column.

`SeriesResult` documents that a "Total" segment is usual but NOT guaranteed —
"Read a segment's presence, never assume it". `_findings_from_series` assumed
it, so any series without one yielded no findings at all, and the route's
"nothing to summarise" fallback returned the raw question text. That is the
reported defect: a comparison slide never gets a generated headline.
"""
from reportbuilder.api.routes_ai import _findings_from_series
from reportbuilder.stats.series import Cell, SeriesResult


def _series(categories, segments, values, statistic="pct"):
    cells = {(c, s): Cell(pct=v) for (c, s), v in values.items()}
    return SeriesResult(categories=tuple(categories), segments=tuple(segments),
                        cells=cells, base_n={"Total": 100}, statistic=statistic)


def test_a_total_series_is_unchanged():
    s = _series(["Kyllä", "Ei"], ["Total"],
                {("Kyllä", "Total"): 62.0, ("Ei", "Total"): 21.0})
    assert _findings_from_series(s, 5) == [("Kyllä", 62.0), ("Ei", 21.0)]


def test_a_comparison_yields_findings_despite_having_no_total():
    """A comparison overlays its member questions AS the segments, so there is
    no Total column and every lookup missed."""
    s = _series(["Luotettava", "Kallis"], ["Vuorikoti", "Lehtoranta"],
                {("Luotettava", "Vuorikoti"): 44.0,
                 ("Kallis", "Vuorikoti"): 12.0,
                 ("Luotettava", "Lehtoranta"): 31.0,
                 ("Kallis", "Lehtoranta"): 28.0})
    out = _findings_from_series(s, 5)
    assert out, "a comparison must produce findings, not fall back to the question text"
    labels = [lbl for lbl, _ in out]
    assert any("Vuorikoti" in l for l in labels)
    assert any("Lehtoranta" in l for l in labels)


def test_every_compared_entity_is_represented():
    """A plain global top-N can return several cells from ONE entity and lose the
    contrast, which is the whole point of a comparison slide."""
    s = _series(["A", "B", "C"], ["X", "Y"],
                {("A", "X"): 90.0, ("B", "X"): 80.0, ("C", "X"): 70.0,
                 ("A", "Y"): 10.0, ("B", "Y"): 5.0, ("C", "Y"): 1.0})
    out = _findings_from_series(s, 2)
    labels = " | ".join(l for l, _ in out)
    assert "X" in labels and "Y" in labels, labels


def test_separate_layout_per_panel_totals_also_work():
    """The SEPARATE layout emits '<variable> · Total' instead of a bare Total."""
    s = _series(["Kyllä", "Ei"], ["Sukupuoli · Total"],
                {("Kyllä", "Sukupuoli · Total"): 55.0,
                 ("Ei", "Sukupuoli · Total"): 45.0})
    out = _findings_from_series(s, 5)
    assert out and out[0][1] == 55.0


def test_missing_cells_are_skipped_not_fatal():
    """B has no cell for X; that must be skipped, not crash or blank the result."""
    s = _series(["A", "B"], ["X"], {("A", "X"): 12.0})
    out = _findings_from_series(s, 5)
    assert len(out) == 1 and out[0][1] == 12.0


def test_top_n_is_respected_and_sorted():
    s = _series(["A", "B", "C"], ["X"],
                {("A", "X"): 1.0, ("B", "X"): 9.0, ("C", "X"): 5.0})
    out = _findings_from_series(s, 2)
    assert [v for _, v in out] == [9.0, 5.0]


# --------------------------------------------------- through the real engine ---
def test_a_real_comparison_series_produces_findings():
    """End to end through `compute()`, not a hand-built series.

    The reported defect: "Vertailu-slidet ei saa tekoälyn tekemää otsikkoa" —
    a comparison slide gets the raw question text instead of a headline, because
    the route treats "no findings" as "nothing to summarise".
    """
    import pandas as pd

    from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
    from reportbuilder.model.report import (
        ChartSpec, ElementToggles, NumberFormat, SortSpec,
    )
    from reportbuilder.stats import engine

    def tick(name, label):
        return Variable(name=name, label=label, measurement="categorical",
                        value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                        missing_values=frozenset())

    vars_ = {n: tick(n, n.split("_")[1].upper())
             for n in ("r_is", "r_il", "l_is", "l_il")}
    q_r = Question(qid="rohkea", kind="multi", variables=("r_is", "r_il"),
                   text="Rohkea")
    q_l = Question(qid="luot", kind="multi", variables=("l_is", "l_il"),
                   text="Luotettava")
    comp = Question(qid="compare-x", kind="comparison",
                    variables=("r_is", "r_il", "l_is", "l_il"),
                    text="Vertailu", members=("rohkea", "luot"))
    model = QuestionModel(variables=vars_, questions=[q_r, q_l, comp])
    df = pd.DataFrame({"r_is": [1, 1, 1, 0], "r_il": [1, 0, 0, 0],
                       "l_is": [1, 0, 0, 0], "l_il": [1, 1, 1, 0]})
    spec = ChartSpec(question_ref="compare-x", chart_type="radar", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s",
                     elements=ElementToggles())

    series = engine.compute(comp, spec, df, model)
    assert "Total" not in series.segments, "precondition: a comparison has no Total"

    findings = _findings_from_series(series, 5)
    assert findings, "the comparison slide would fall back to its question text"
    labels = " | ".join(lbl for lbl, _ in findings)
    assert "Rohkea" in labels and "Luotettava" in labels, labels
