"""A legend must not shorten BANDS to their first number.

Prima Pet, "Kuinka paljon arvioisit käyttäväsi rahaa koiran herkkuihin ja
purutuotteisiin kuukaudessa?" — the levels are "20–40 euroa / kuukausi",
"40–60 euroa / kuukausi" and "60–100 euroa / kuukausi". Every one of them
begins with a digit, so the numeric-rating-scale rule fired and the legend
read "20  40  60": the reader sees 82 % against "20" with nothing saying it
means twenty to forty euros a month. The words are not moved anywhere — they
are simply gone.

This is the SAME misreading already fixed once on the series legend, where
Finnish age bands drew "18  25  35  45" (Johan, 2026-09-09). That fix turned
shortening off for the classifier's groups; the CATEGORY legend kept doing it
to any level list whose labels happen to open with a figure.

A band states a RANGE. A rating scale's point is a single number that stands
for itself, which is what makes it safe to print alone.
"""
from __future__ import annotations

from reportbuilder.render.image.bars import _labels_are_a_numeric_scale


def test_money_bands_are_not_a_scale():
    assert not _labels_are_a_numeric_scale(
        ["20–40 euroa / kuukausi", "40–60 euroa / kuukausi",
         "60–100 euroa / kuukausi"])


def test_age_bands_are_not_a_scale():
    """The same shape the series legend already learned about."""
    assert not _labels_are_a_numeric_scale(
        ["18-24 vuotias", "25-34 vuotias", "35-44 vuotias", "45-54 vuotias"])


def test_a_real_rating_scale_still_shortens():
    assert _labels_are_a_numeric_scale(
        ["1 - Täysin eri mieltä", "2", "3", "4", "5 - Täysin samaa mieltä"])


def test_a_bare_numbered_scale_still_shortens():
    assert _labels_are_a_numeric_scale(["1", "2", "3", "4", "5", "6", "7"])


def test_a_categorical_list_is_not_a_scale():
    assert not _labels_are_a_numeric_scale(["Uusimaa", "Pirkanmaa", "Lappi"])


def test_two_levels_are_not_enough_to_be_a_scale():
    assert not _labels_are_a_numeric_scale(["1 - Kyllä", "2 - Ei"])


def test_an_open_ended_top_band_is_still_a_band():
    """"75+" and "yli 60" state a range as surely as "20–40" does."""
    assert not _labels_are_a_numeric_scale(
        ["alle 20 euroa", "20–40 euroa", "40–60 euroa", "yli 60 euroa"])
