"""GOLDEN test: general-opinion engine output vs Attendo deck (Task 3.7, REQ-C-15/16, MV-01).

The deck's opinion proportions sum to 1.0 over ALL respondents (n=1001) including
"En osaa sanoa" (DK = code 10058). So DK must be treated as a CATEGORY, not excluded
as a missing value. We override missing_values=frozenset() for these vars only.
"""
import pytest
from dataclasses import replace
from reportbuilder import config
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, NumberFormat, SortSpec, ElementToggles
from reportbuilder.stats.engine import compute
from reportbuilder.testing.fixtures import (
    OPINION_PRIVATE_VAR, OPINION_PUBLIC_VAR, DECK_OPINION_DIST, DECK_OPINION_POSITIVE,
)


def _opinion_model_and_q(model, var):
    # DK (10058) is a real category here: empty the var's missing set so it isn't dropped.
    v = replace(model.variables[var], missing_values=frozenset())
    new_vars = dict(model.variables); new_vars[var] = v
    model2 = QuestionModel(variables=new_vars, questions=[])
    q = Question(qid=var, kind="single", variables=(var,), text="General opinion")
    return model2, q


@pytest.mark.integration
@pytest.mark.parametrize("key,var", [("private", OPINION_PRIVATE_VAR), ("public", OPINION_PUBLIC_VAR)])
def test_general_opinion_distribution_matches_deck(key, var):
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")
    df, model = read_sav(config.ATTENDO_SAV)
    model2, q = _opinion_model_and_q(model, var)
    spec = ChartSpec(question_ref=var, chart_type="vertical_bar", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(pct_decimals=0),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())
    res = compute(q, spec, df, model2)
    for label, want_prop in DECK_OPINION_DIST[key].items():
        got = res.cell(label, "Total").pct / 100.0
        assert abs(got - want_prop) <= 0.01, f"{key} {label}: {got} vs {want_prop}"
    positive = sum(res.cell(lbl, "Total").pct for lbl in ("Hyvä", "Erittäin hyvä"))
    assert abs(round(positive) - DECK_OPINION_POSITIVE[key]) <= 1
