"""Integration test: ingest the real Attendo .sav and validate known properties.

Task 2.6 — Phase-2 validates on real data.
Marked @pytest.mark.integration; skipped automatically when the file is absent.
"""
from __future__ import annotations

import pytest
from reportbuilder import config
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.ingest.multi_group import suggest_multi_groups, apply_groups


@pytest.mark.integration
def test_attendo_variable_and_value_labels():
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")
    df, model = read_sav(config.ATTENDO_SAV)
    assert len(df) == 1001
    aided = model.variable("var18O45")
    codes = {vl.value: vl.label for vl in aided.value_labels}
    assert set(codes) == {0.0, 1.0}                       # binary tickbox
    op = {vl.value: vl.label for vl in model.variable("var20").value_labels}
    assert op.get(10056.0) == "Hyvä"
    assert op.get(10058.0) == "En osaa sanoa"


@pytest.mark.integration
def test_attendo_aided_grid_autosuggested_as_multi():
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")
    _, model = read_sav(config.ATTENDO_SAV)
    groups = suggest_multi_groups(model)
    aided = [g for g in groups if "var18O45" in g][0]      # the group containing var18O45
    for v in ("var18O45", "var18O46", "var18O47", "var18O48", "var18O49",
              "var18O50", "var18O51", "var18O52", "var18O53"):
        assert v in aided                                  # the 9 aided brands are in the group
    model2 = apply_groups(model, [aided])
    multi = [q for q in model2.questions
             if q.kind == "multi" and "var18O45" in q.variables][0]
    assert multi.kind == "multi"
    assert len(multi.variables) == len(aided)
