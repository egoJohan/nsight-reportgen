import pandas as pd
from nsight.segments import segment_mask, SEGMENTS


def _frame():
    # var11O19 client, O20 relative, O21 work, O22 none; var158O706 recommend Attendo
    return pd.DataFrame(
        {
            "var11O19": [1, 0, 0, 0],
            "var11O20": [0, 1, 0, 0],
            "var11O21": [0, 0, 1, 0],
            "var11O22": [0, 0, 0, 1],
            "var158O706": [1, 0, 1, 0],
        }
    )


def test_all_segment_selects_everyone():
    mask = segment_mask("kaikki", _frame())
    assert mask.tolist() == [True, True, True, True]


def test_experienced_segment_predicate():
    # Experienced = any of client/relative/work checked.
    mask = segment_mask("kokemusta_omaavat", _frame())
    assert mask.tolist() == [True, True, True, False]


def test_inexperienced_segment_predicate():
    mask = segment_mask("kokemattomat", _frame())
    assert mask.tolist() == [False, False, False, True]


def test_professionals_segment_predicate():
    mask = segment_mask("ammattilaiset", _frame())
    assert mask.tolist() == [False, False, True, False]


def test_recommenders_segment_predicate():
    mask = segment_mask("suosittelijat", _frame())
    assert mask.tolist() == [True, False, True, False]


def test_unknown_segment_raises():
    frame = pd.DataFrame({"x": [1]})
    try:
        segment_mask("nope", frame)
        assert False, "expected KeyError"
    except KeyError:
        pass
