"""A scale worded only at its ends is still a scale.

"Radar-kuvaajan testaaminen ei nyt onnistu sillä en saa määritettyä
muuttujanippua oikein."

Five attributes — Luotettava, Viihdyttävä, Edelläkävijä, Ammattitaitoinen,
Palveleva — each a 1..5 rating carrying TWO value labels:

    (1.0, 'Erittäin huonosti')   (5.0, 'Erittäin hyvin')

`scale_levels` refuses anything with fewer than three labelled points, so all
five reported `scale=False` with no compat key, never entered the grouping
pool, could not be made into a battery, and the radar fell back to charting one
variable's scale points as its axes.

The rest of the product already knows this shape: `_partial_scale` charts "1..7
with words on 1 and 7" as numbered categories with the wording in a caption. It
was a scale everywhere except where you try to GROUP one.

So the data decides, the way it already does for tick-boxes (`is_tickbox`): with
no labels to go on, a column holding a contiguous run of 3..11 integers is a
scale of that many points. Without a DataFrame the answer is exactly what it was
before, so no existing caller changes. (Johan, 2026-09-16)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reportbuilder.model.question import ValueLabel, Variable
from reportbuilder.stats.engine import scale_levels

pytestmark = pytest.mark.unit

_ENDS = (ValueLabel(1.0, "Erittäin huonosti"), ValueLabel(5.0, "Erittäin hyvin"))
_ATTRS = ("Luotettava", "Viihdyttävä", "Edelläkävijä", "Ammattitaitoinen",
          "Palveleva")


def _var(name: str, labels=_ENDS) -> Variable:
    return Variable(name, name, "ordinal", tuple(labels), frozenset())


def _df(names=_ATTRS, values=(1, 2, 3, 4, 5)) -> pd.DataFrame:
    rng = np.random.default_rng(4)
    return pd.DataFrame({n: rng.choice(values, size=200).astype(float)
                         for n in names})


def test_without_data_the_answer_is_unchanged():
    """Every existing caller passes no frame and must see what it saw before."""
    assert scale_levels(_var("Luotettava")) == []


def test_the_data_makes_it_a_five_point_scale():
    levels = scale_levels(_var("Luotettava"), _df())
    assert [p for _c, _l, p in levels] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_the_endpoint_wording_is_kept():
    levels = scale_levels(_var("Luotettava"), _df())
    labels = [l for _c, l, _p in levels]
    assert labels[0] == "Erittäin huonosti"
    assert labels[-1] == "Erittäin hyvin"


def test_the_unlabelled_middle_is_numbered():
    """Nothing to call them but their point, which is what `_partial_scale`
    already does for this shape."""
    labels = [l for _c, l, _p in scale_levels(_var("Luotettava"), _df())]
    assert labels[1:4] == ["2", "3", "4"]


def test_all_five_attributes_share_one_scale():
    """The property that lets them form a battery."""
    df = _df()
    keys = {tuple(p for _c, _l, p in scale_levels(_var(a), df)) for a in _ATTRS}
    assert len(keys) == 1, keys


def test_a_fully_labelled_scale_is_untouched():
    labelled = tuple(ValueLabel(float(i), f"{i} - taso") for i in range(1, 6))
    with_df = scale_levels(_var("q", labelled), _df(("q",)))
    without = scale_levels(_var("q", labelled))
    assert with_df == without


def test_a_free_number_is_not_a_scale():
    """An age or a euro amount is not a rating, however many values it has."""
    ages = pd.DataFrame({"ika": np.arange(18, 80, dtype=float)})
    assert scale_levels(_var("ika", ()), ages) == []


def test_a_binary_flag_is_not_a_scale():
    """Two points is a tick-box's business, not a rating's."""
    flags = pd.DataFrame({"f": np.array([0.0, 1.0] * 50)})
    assert scale_levels(_var("f", ()), flags) == []


def test_a_column_that_is_not_in_the_frame_is_not_guessed_at():
    assert scale_levels(_var("missing"), _df()) == []


def test_the_scale_does_not_shrink_when_nobody_picked_the_top():
    """The one that would have let this ship broken.

    In a 41-person sample nobody rated `Luotettava` a 5. Reading the extent off
    the DATA gave it four points where its four siblings had five, so its compat
    key differed and the five attributes still could not form a battery — the
    very thing this fixes. The labelled endpoints state the range; the sample
    does not get a vote on it.
    """
    df = _df(("a", "b"))
    df["a"] = df["a"].replace(5.0, 4.0)          # nobody picked the top
    a = scale_levels(_var("a"), df)
    b = scale_levels(_var("b"), df)
    assert [p for _c, _l, p in a] == [p for _c, _l, p in b] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_a_gap_in_the_middle_is_still_the_same_scale():
    """Nobody chose 3 either; a rating keeps its points."""
    df = _df(("a",))
    df["a"] = df["a"].replace(3.0, 2.0)
    assert len(scale_levels(_var("a"), df)) == 5


def test_labels_too_far_apart_are_not_a_rating():
    """1 and 99 is a code list, not a scale — more than 11 points apart.

    Both labels must be REAL ones: "Ei osaa sanoa" on 99 is a non-answer, which
    is discarded before the range is read, and what is left (clean 1..5 data) is
    a rating. That is correct, and it is not what this test is about.
    """
    ends = (ValueLabel(1.0, "Pienin"), ValueLabel(99.0, "Suurin"))
    assert scale_levels(_var("q", ends), _df(("q",))) == []
