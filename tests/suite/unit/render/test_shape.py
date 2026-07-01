"""Unit tests for reportbuilder.render.shape — SeriesShape.of derivations,
the ADDITIVE_STATISTICS set, and the TIME_RE temporal-label detector."""
from __future__ import annotations

import pytest

from reportbuilder.render.shape import (
    ADDITIVE_STATISTICS, SeriesShape, TIME_RE,
)
from reportbuilder.testing.fixtures import known_series, tiny_question_model

from suite.unit.render import _builders as B


# ---- SeriesShape.of --------------------------------------------------------

def test_shape_of_single_series():
    q = tiny_question_model().question("q1")
    s = SeriesShape.of(q, known_series())
    assert s.n_series == 1
    assert s.n_categories == 2
    assert s.max_label_len == 3            # "Yes"/"No"
    assert s.is_multi is False
    assert s.is_temporal is False
    assert s.is_partition is True          # pct sums to 100
    assert s.statistic == "pct"


def test_shape_of_multi_group_counts_series():
    s = SeriesShape.of(B.q("single"), B.multi_group_series())
    assert s.n_series == 2                  # two segments
    assert s.n_categories == 4


def test_shape_is_multi_reads_question_kind():
    series = B.many_long_series()
    assert SeriesShape.of(B.q("multi"), series).is_multi is True
    assert SeriesShape.of(B.q("single"), series).is_multi is False


def test_shape_max_label_len_tracks_longest():
    s = SeriesShape.of(B.q(), B.many_long_series())
    assert s.max_label_len == len("Category number 0")   # 17


def test_shape_is_temporal_true_for_year_labels():
    assert SeriesShape.of(B.q(), B.temporal_series()).is_temporal is True


def test_shape_is_temporal_true_for_wave_labels():
    waves = B.build_series(("Wave 1", "Wave 2", "Wave 3"), pct=50.0)
    assert SeriesShape.of(B.q(), waves).is_temporal is True


def test_shape_is_temporal_false_for_nominal_labels():
    assert SeriesShape.of(B.q(), B.few_short_series()).is_temporal is False


def test_shape_is_partition_true_for_single_choice_partition():
    assert SeriesShape.of(B.q(), B.partition_series()).is_partition is True


def test_shape_is_partition_false_when_counts_miss_base():
    assert SeriesShape.of(B.q(), B.nonpartition_series()).is_partition is False


def test_shape_handles_question_without_kind_attr():
    # any object lacking `.kind` -> is_multi False (getattr default None).
    class NoKind:
        pass
    s = SeriesShape.of(NoKind(), B.few_short_series())
    assert s.is_multi is False


def test_shape_empty_series_zero_lengths():
    s = SeriesShape.of(B.q(), B.empty_series())
    assert s.n_categories == 0
    assert s.max_label_len == 0            # default when no categories


# ---- ADDITIVE_STATISTICS ---------------------------------------------------

def test_additive_statistics_membership():
    assert "pct" in ADDITIVE_STATISTICS
    assert "count" in ADDITIVE_STATISTICS
    assert "mean" not in ADDITIVE_STATISTICS


# ---- TIME_RE ---------------------------------------------------------------

@pytest.mark.parametrize("label", [
    "2019", "2025", "Q1", "q4", "H2", "wave 1", "Wave 3", "aalto",
    "kuu", "kuukausi", "tammi", "helmi", "kesä", "joulu",
    "Marraskuu 2025",   # matches via the year
])
def test_time_re_matches_temporal(label):
    assert TIME_RE.search(label) is not None


@pytest.mark.parametrize("label", [
    "hello", "random text", "Satisfaction", "Yes", "syksy",
    "tammikuu",   # NOTE: full Finnish month word is NOT matched (no \b before "kuu")
    "joulukuu",
])
def test_time_re_does_not_match_nontemporal(label):
    assert TIME_RE.search(label) is None
