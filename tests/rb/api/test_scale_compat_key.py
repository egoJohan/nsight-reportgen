"""Battery-compatibility of rating scales — `_scale_compat_key` groups variables by
their POINT SET (1..N), so differently-worded scales of the same length can form a
battery, while the exact `_scale_key` still distinguishes their labels. (customer:
"add any similar-scale variable group to a battery")"""
from reportbuilder.model.question import ValueLabel, Variable
from reportbuilder.api.routes_questions import _scale_key, _scale_compat_key


def _scale(name, labels):
    return Variable(
        name=name, label=name, measurement="scale",
        value_labels=tuple(ValueLabel(float(i + 1), lbl) for i, lbl in enumerate(labels)),
        missing_values=frozenset(),
    )


def test_differently_worded_same_length_scales_are_compatible():
    grade = _scale("grade", ["1 - Erittäin huono", "2", "3", "4", "5 - Erittäin hyvä"])
    agree = _scale("agree", ["Täysin eri mieltä", "Eri mieltä", "Neutraali",
                             "Samaa mieltä", "Täysin samaa mieltä"])
    # Exact signatures differ (labels differ)…
    assert _scale_key(grade) != _scale_key(agree)
    # …but the compatibility key (point set) matches → they can battery together.
    assert _scale_compat_key(grade) == _scale_compat_key(agree)


def test_different_length_scales_are_incompatible():
    five = _scale("five", ["1", "2", "3", "4", "5"])
    seven = _scale("seven", ["1", "2", "3", "4", "5", "6", "7"])
    assert _scale_compat_key(five) != _scale_compat_key(seven)


def test_non_scale_has_no_compat_key():
    region = Variable(name="region", label="Region", measurement="categorical",
                      value_labels=(ValueLabel(1.0, "North"), ValueLabel(2.0, "South")),
                      missing_values=frozenset())
    assert _scale_compat_key(region) is None
