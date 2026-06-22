import pandas as pd
import pytest

from nsight.brief import SlideJob
from nsight.build import build_slidefill


def _frame():
    return pd.DataFrame({"aw_attendo": [1, 1, 1, 0], "aw_esperi": [1, 0, 0, 0]})


BRAND_VARS = {"Attendo": "aw_attendo", "Esperi": "aw_esperi"}


def test_build_slidefill_aided_awareness():
    job = SlideJob(
        id="aw",
        slide_idx=14,
        metric="aided_awareness",
        chart={"name": "Content Placeholder 9", "series_name": "W"},
    )
    sf = build_slidefill(job, _frame(), brand_vars=BRAND_VARS, weight=None)
    assert len(sf.charts) == 1
    cf = sf.charts[0]
    assert cf.series_name == "W"
    assert cf.name == "Content Placeholder 9"
    assert cf.values_by_category == {"Attendo": 0.75, "Esperi": 0.25}


def test_build_slidefill_with_key_message():
    job = SlideJob(
        id="aw",
        slide_idx=14,
        metric="aided_awareness",
        chart={"name": "Content Placeholder 9", "series_name": "W"},
        key_message={"name": "km"},
    )
    sf = build_slidefill(job, _frame(), brand_vars=BRAND_VARS, weight=None,
                         key_message="Attendo on tunnetuin.")
    assert len(sf.texts) == 1
    assert sf.texts[0].name == "km"
    assert sf.texts[0].value == "Attendo on tunnetuin."


def test_build_slidefill_unknown_metric():
    job = SlideJob(id="x", slide_idx=1, metric="bogus")
    with pytest.raises(ValueError):
        build_slidefill(job, _frame(), brand_vars=BRAND_VARS, weight=None)
