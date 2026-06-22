import pandas as pd

from nsight.brief import Brief, SlideJob
from nsight.agent.workflow import generate_fills


def _frame():
    return pd.DataFrame({"aw_attendo": [1, 1, 1, 0], "aw_esperi": [1, 0, 0, 0]})


BRAND_VARS = {"Attendo": "aw_attendo", "Esperi": "aw_esperi"}


def test_generate_fills_offline_narrator():
    job = SlideJob(
        id="aw",
        slide_idx=14,
        metric="aided_awareness",
        chart={"name": "Content Placeholder 9", "series_name": "W"},
        key_message={"name": "km"},
    )
    brief = Brief(jobs=[job])
    fills = generate_fills(
        brief,
        _frame(),
        brand_vars=BRAND_VARS,
        weight=None,
        narrator=lambda job, numbers: "Attendo on tunnetuin.",
    )
    assert len(fills) == 1
    assert fills[0].charts[0].values_by_category == {"Attendo": 0.75, "Esperi": 0.25}
    assert fills[0].texts[0].value == "Attendo on tunnetuin."


def test_generate_fills_no_key_message():
    job = SlideJob(
        id="aw",
        slide_idx=14,
        metric="aided_awareness",
        chart={"name": "Content Placeholder 9", "series_name": "W"},
    )
    fills = generate_fills(
        Brief(jobs=[job]),
        _frame(),
        brand_vars=BRAND_VARS,
        weight=None,
        narrator=lambda job, numbers: "should not be used",
    )
    assert fills[0].texts == []
