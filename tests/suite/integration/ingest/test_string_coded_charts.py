"""A string-coded question does not just load — it charts, and its declared
missing values are excluded from the base.

Loading was the reported failure, but a file that loads and then counts "not
asked" as an answer is worse than one that refuses: the percentages are wrong and
nothing says so. This goes SAV -> read_sav -> engine.compute, the same path a
slide takes.
"""
from __future__ import annotations

import pandas as pd
import pyreadstat
import pytest

from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _spec(qid: str) -> ChartSpec:
    return ChartSpec(question_ref=qid, chart_type="vertical_bar", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s",
                     elements=ElementToggles())


@pytest.fixture
def charted(tmp_path):
    """20x Kyllä, 10x Ei, 6x '-' where '-' is DECLARED missing."""
    df = pd.DataFrame({"q1": ["Kyllä"] * 20 + ["Ei"] * 10 + ["-"] * 6})
    path = tmp_path / "coded.sav"
    pyreadstat.write_sav(
        df, str(path),
        column_labels={"q1": "Suosittelisitko?"},
        variable_value_labels={"q1": {"Kyllä": "Kyllä", "Ei": "Ei", "-": "Ei kysytty"}},
        missing_ranges={"q1": [{"lo": "-", "hi": "-"}]},
    )
    frame, model = read_sav(str(path))
    qid = model.questions[0].qid
    return engine.compute(model.questions[0], _spec(qid), frame, model)


def test_the_declared_missing_answers_are_out_of_the_base(charted):
    # 36 rows, 6 of them declared missing.
    assert charted.base_n == {"Total": 30}


def test_the_declared_missing_category_is_not_a_bar(charted):
    assert "Ei kysytty" not in charted.categories
    assert set(charted.categories) == {"Kyllä", "Ei"}


def test_counts_and_percentages_are_of_the_answered_base(charted):
    seg = charted.segments[0]
    cells = {c: charted.cells[(c, seg)] for c in charted.categories}
    assert cells["Kyllä"].count == 20 and cells["Ei"].count == 10
    # Of 30, not of 36 — the six "Ei kysytty" would drag both down.
    assert cells["Kyllä"].pct == pytest.approx(67, abs=1)
    assert cells["Ei"].pct == pytest.approx(33, abs=1)
