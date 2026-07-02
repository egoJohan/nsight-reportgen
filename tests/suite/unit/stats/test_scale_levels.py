"""scale_levels — robust rating-scale detection (digit-labelled OR word-labelled 1..N)."""
from __future__ import annotations

from reportbuilder.model.question import ValueLabel, Variable
from reportbuilder.stats.engine import scale_levels


def _var(pairs, missing=()):
    return Variable(name="q", label="Q", measurement="scale",
                    value_labels=tuple(ValueLabel(float(c), l) for c, l in pairs),
                    missing_values=frozenset(float(m) for m in missing))


def _points(var):
    return [p for _, _, p in scale_levels(var)]


def test_digit_labelled_scale():
    v = _var([(1, "1 - eri"), (2, "2"), (3, "3"), (4, "4"), (5, "5 - samaa")])
    assert _points(v) == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_word_labelled_scale_uses_codes():
    v = _var([(1, "Ei lainkaan tärkeä"), (2, "Vain vähän tärkeä"), (3, "Melko tärkeä"),
              (4, "Tärkeä"), (5, "Erittäin tärkeä")])
    lv = scale_levels(v)
    assert [p for _, _, p in lv] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert lv[0][1] == "Ei lainkaan tärkeä" and lv[-1][1] == "Erittäin tärkeä"


def test_out_of_order_digit_codes_sorted_by_point():
    v = _var([(10, "2"), (20, "3"), (5, "1"), (30, "4"), (40, "5")])
    assert _points(v) == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_non_contiguous_codes_not_a_scale():
    v = _var([(1, "A"), (2, "B"), (4, "D"), (5, "E")])   # gap at 3, word labels
    assert scale_levels(v) == []


def test_binary_is_not_a_scale():
    v = _var([(0, "No"), (1, "Yes")])
    assert scale_levels(v) == []


def test_word_scale_with_missing_dontknow():
    v = _var([(1, "Ei lainkaan"), (2, "Vähän"), (3, "Keskiverto"), (4, "Paljon"),
              (5, "Erittäin"), (9, "En osaa sanoa")], missing=(9,))
    assert _points(v) == [1.0, 2.0, 3.0, 4.0, 5.0]   # 9 excluded, 1..5 contiguous
