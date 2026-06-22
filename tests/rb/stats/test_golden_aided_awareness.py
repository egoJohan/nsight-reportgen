"""GOLDEN test: aided-awareness engine output vs Attendo deck (Task 3.6, REQ-M-03, R1)."""
import pytest
from reportbuilder import config
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import ChartSpec, NumberFormat, SortSpec, ElementToggles
from reportbuilder.stats.engine import compute
from reportbuilder.testing.fixtures import aided_question, DECK_AIDED_AWARENESS


@pytest.mark.integration
def test_aided_awareness_matches_deck():
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")
    df, model = read_sav(config.ATTENDO_SAV)
    model2, q = aided_question(model)
    spec = ChartSpec(question_ref="aided", chart_type="horizontal_bar", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())
    res = compute(q, spec, df, model2)
    assert abs(res.base_n["Total"] - 1001) <= 1, f"base {res.base_n['Total']} vs ~1001"
    for brand, want in DECK_AIDED_AWARENESS.items():
        got = res.cell(brand, "Total").pct
        assert abs(got - want) <= 1, f"{brand}: computed {got} vs deck {want}"
