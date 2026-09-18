"""A band's numeric value is its middle, not the number it starts with.

`_rating_scale` maps a value label's leading integer to a scale point — right
for a rating, where that integer IS the point ("5 - Vastaa erittäin hyvin" → 5).
The combo's secondary variable runs through the same map to get "the numeric
values of the classes", and a banded variable's labels are RANGES, so "55-64"
came back as 55: the band's lower bound.

On the mobiilivarmenne slide that made "Ikäluokka (keskiarvo)" read 59.6, which
is not the mean age of anyone. It is the mean of the band START values, about
four and a half years below the truth, printed against an unlabelled axis.
("En ymmärrä ikäluokan kuvaustapaa", Johan, 2026-09-18.)

Only labels that actually state a range move. A rating label has one number and
then words, so every rating scale in the product is untouched.
"""
from __future__ import annotations

import pytest

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.stats.engine import _rating_scale


def _points(labels: list[str]) -> list[float]:
    var = Variable(name="v", label="v", measurement="nominal", missing_values=[],
                   value_labels=[ValueLabel(value=float(i + 1), label=l)
                                 for i, l in enumerate(labels)])
    scale = _rating_scale(var)
    return [scale[float(i + 1)] for i in range(len(labels)) if float(i + 1) in scale]


AGE_BANDS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75+"]


def test_an_age_band_maps_to_its_midpoint():
    assert _points(AGE_BANDS) == [21.0, 29.5, 39.5, 49.5, 59.5, 69.5, 75.0]


def test_an_open_ended_top_band_keeps_its_stated_bound():
    """"75+" has no upper end to take a middle of. The stated bound is the only
    number the file gives, and inventing a ceiling would be inventing data."""
    assert _points(["75+"]) == [75.0]


@pytest.mark.parametrize("dash", ["-", "–", "—"])
def test_any_dash_counts_as_a_range(dash):
    assert _points([f"1000{dash}1999"]) == [1499.5]


def test_spaces_around_the_dash_are_fine():
    assert _points(["55 - 64"]) == [59.5]


def test_a_range_with_words_after_it_still_counts():
    assert _points(["1-2 kertaa viikossa"]) == [1.5]


# --- the rating scales this must not disturb -------------------------------

def test_a_numbered_rating_label_is_unchanged():
    assert _points(["1 - Täysin eri mieltä", "2", "3", "4",
                    "5 - Täysin samaa mieltä"]) == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_a_number_followed_by_words_is_not_a_range():
    """"5 - Vastaa erittäin hyvin" has a dash but no second number."""
    assert _points(["5 - Vastaa erittäin hyvin"]) == [5.0]


def test_a_bare_number_is_unchanged():
    assert _points(["3"]) == [3.0]


def test_a_label_with_no_number_is_still_omitted():
    """Unchanged behaviour: no leading integer means no scale point at all."""
    assert _points(["En osaa sanoa"]) == []
