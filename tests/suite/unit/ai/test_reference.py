"""Unit tests for ``reportbuilder.ai.reference``: ``_normalize`` and the
in-memory ``ReferenceLabels`` matcher (no pptx / no network)."""
from __future__ import annotations

from reportbuilder.ai.reference import FUZZY_THRESHOLD, ReferenceLabels, _normalize


# --------------------------------------------------------------------------- #
# _normalize
# --------------------------------------------------------------------------- #
def test_normalize_lowercases_and_strips_punctuation():
    assert _normalize("Kyllä, ehkä!") == "kyllä ehkä"


def test_normalize_collapses_whitespace_and_dashes():
    assert _normalize("  A—B  ") == "a b"


def test_normalize_empty_and_none():
    assert _normalize("") == ""
    assert _normalize(None) == ""


# --------------------------------------------------------------------------- #
# ReferenceLabels construction
# --------------------------------------------------------------------------- #
def test_construction_filters_blank_labels():
    ref = ReferenceLabels(labels=["Hyvä", "  ", ""], titles=["Otsikko", " "])
    assert ref.labels == ["Hyvä"]
    assert ref.titles == ["Otsikko"]


# --------------------------------------------------------------------------- #
# .match
# --------------------------------------------------------------------------- #
def test_match_exact_normalized_and_strictly_shorter():
    ref = ReferenceLabels(labels=["Kyllä varmasti"], titles=[])
    # normalizes equal, and 14 < 15 chars -> reused.
    assert ref.match("Kyllä, varmasti") == "Kyllä varmasti"


def test_match_returns_none_when_candidate_not_strictly_shorter():
    # normalizes equal but same length -> rejected (never return equal-length).
    ref = ReferenceLabels(labels=["Kyllä!"], titles=[])
    assert ref.match("Kyllä.") is None


def test_match_fuzzy_hit_above_threshold_and_shorter():
    # One dropped 't' -> ratio ~0.97 (>= 0.9) and strictly shorter.
    ref = ReferenceLabels(labels=["Eritäin tyytyväinen"], titles=[])
    assert ref.match("Erittäin tyytyväinen") == "Eritäin tyytyväinen"


def test_match_no_hit_returns_none():
    ref = ReferenceLabels(labels=["Aivan eri asia"], titles=[])
    assert ref.match("Täysin toinen otsikko") is None


def test_match_fuzzy_below_threshold_returns_none():
    # A short reference that is only loosely similar stays below FUZZY_THRESHOLD.
    ref = ReferenceLabels(labels=["Kissa"], titles=[])
    assert ref.match("Koira ja hevonen") is None


def test_match_blank_input_returns_none():
    ref = ReferenceLabels(labels=["Hyvä"], titles=[])
    assert ref.match("") is None
    assert ref.match("   ") is None


def test_fuzzy_threshold_constant():
    assert FUZZY_THRESHOLD == 0.9


# --------------------------------------------------------------------------- #
# .examples
# --------------------------------------------------------------------------- #
def test_examples_shortest_first_and_distinct():
    ref = ReferenceLabels(labels=["bb", "a", "ccc", "a"], titles=[])
    assert ref.examples() == ["a", "bb", "ccc"]


def test_examples_respects_n_limit():
    ref = ReferenceLabels(labels=["a", "bb", "ccc", "dddd"], titles=[])
    assert ref.examples(n=2) == ["a", "bb"]
