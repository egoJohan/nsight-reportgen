from nsight.fidelity.extract import DeckData, SlideData, ChartData
from nsight.fidelity.compare import compare_decks


def _deck(v):
    return DeckData(slides=[SlideData(idx=0, charts=[
        ChartData(name="c", categories=["Attendo"], series={"S": [v]})])])


def test_identical_decks_score_100():
    rep = compare_decks(_deck(0.92), _deck(0.92))
    assert rep.chart_score == 100.0
    assert rep.charts_matched == 1


def test_value_within_rounding_tolerance_matches():
    rep = compare_decks(_deck(0.921), _deck(0.918))
    assert rep.chart_score == 100.0


def test_value_off_by_more_than_one_pct_fails():
    rep = compare_decks(_deck(0.92), _deck(0.80))
    assert rep.chart_score == 0.0
    assert rep.mismatches


def test_none_matches_none():
    # Both-None counts as matched
    deck_none = DeckData(slides=[SlideData(idx=0, charts=[
        ChartData(name="c", categories=["Attendo"], series={"S": [None]})])])
    rep = compare_decks(deck_none, deck_none)
    assert rep.chart_score == 100.0
    assert rep.charts_matched == 1
    assert not rep.mismatches

    # One None vs a real value is a mismatch
    deck_val = _deck(0.5)
    rep2 = compare_decks(deck_val, deck_none)
    assert rep2.chart_score == 0.0
    assert rep2.mismatches


def test_duplicate_named_charts_paired_by_position():
    """Two charts with identical name on the same slide must be paired by index,
    not by first-name-match. Self-compare must yield 100% and charts_matched==2."""
    slide = SlideData(idx=0, charts=[
        ChartData(name="dup", categories=["X"], series={"S": [0.1]}),
        ChartData(name="dup", categories=["X"], series={"S": [0.9]}),
    ])
    deck = DeckData(slides=[slide])
    rep = compare_decks(deck, deck)
    assert rep.chart_score == 100.0, (
        f"Expected 100.0 but got {rep.chart_score}; mismatches: {rep.mismatches}"
    )
    assert rep.charts_matched == 2, f"Expected 2 matched data points, got {rep.charts_matched}"
    assert not rep.mismatches
