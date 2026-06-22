import pandas as pd
from nsight.tabulate import share, perception_split
from nsight.tabulate import awareness_by_brand, top_of_mind


def test_share_of_value_unweighted():
    frame = pd.DataFrame({"aware": [1, 1, 0, 1, 0, 0]})
    res = share(frame, var="aware", positive_values=[1.0])
    assert res.pct == 50.0
    assert res.n == 6


def test_share_excludes_missing():
    frame = pd.DataFrame({"aware": [1, 1, None, 1, None]})
    res = share(frame, var="aware", positive_values=[1.0])
    assert res.pct == 100.0
    assert res.n == 3


def test_share_weighted():
    frame = pd.DataFrame({"aware": [1, 0], "w": [3.0, 1.0]})
    res = share(frame, var="aware", positive_values=[1.0], weight="w")
    assert res.pct == 75.0


def test_perception_split_three_way():
    frame = pd.DataFrame({"op": [1, 2, 3, 4, 5, 1]})
    res = perception_split(frame, var="op", positive=[1, 2], neutral=[3], negative=[4, 5])
    assert res.positive == 50.0
    assert res.neutral == round(100 / 6, 0)
    assert res.negative == round(200 / 6, 0)


def test_awareness_by_brand_multi_columns():
    frame = pd.DataFrame({
        "aw_attendo": [1, 1, 1, 0],
        "aw_esperi":  [1, 0, 0, 0],
    })
    res = awareness_by_brand(frame, brand_vars={"Attendo": "aw_attendo", "Esperi": "aw_esperi"})
    assert res["Attendo"].pct == 75.0
    assert res["Esperi"].pct == 25.0


def test_top_of_mind_first_mention():
    frame = pd.DataFrame({"first": ["Attendo", "attendo ", "Esperi", "Attendo"]})
    res = top_of_mind(frame, first_mention_var="first", brand="Attendo")
    assert res.pct == 75.0


def test_share_weighted_excludes_weight_nan():
    frame = pd.DataFrame({"aware": [1, 1, 0], "w": [2.0, None, 1.0]})
    res = share(frame, var="aware", positive_values=[1.0], weight="w")
    # Only rows 0 and 2 are valid (row 1 has NaN weight).
    # weighted pct = 2 / (2 + 1) * 100 = 66.666... → rounds to 67
    assert res.pct == 67.0
    assert res.n == 2


def test_top_of_mind_excludes_weight_nan():
    frame = pd.DataFrame({"first": ["Attendo", "Attendo", "Esperi"], "w": [1.0, None, 1.0]})
    res = top_of_mind(frame, first_mention_var="first", brand="Attendo", weight="w")
    # Row 1 has NaN weight → excluded. Valid rows: 0 (Attendo) and 2 (Esperi).
    # pct = 1 / (1 + 1) * 100 = 50.0
    assert res.pct == 50.0
    assert res.n == 2
