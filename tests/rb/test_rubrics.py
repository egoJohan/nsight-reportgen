"""Test Claude-judge rubric registry."""

import pytest
from reportbuilder.testing.rubrics import RUBRICS, rubric_for


def test_r3_layout_rubric_present():
    """Verify R3-LAYOUT rubric exists and contains expected keywords."""
    rubric = rubric_for("R3-LAYOUT")
    assert isinstance(rubric, str)
    # Check for "overlap" and "trunc" (case-insensitive)
    assert "overlap" in rubric.lower()
    assert "trunc" in rubric.lower()


def test_rubrics_registry_is_str_to_str():
    """Verify RUBRICS dict maps strings to strings."""
    assert isinstance(RUBRICS, dict)
    for key, value in RUBRICS.items():
        assert isinstance(key, str), f"RUBRICS key {key!r} is not a string"
        assert isinstance(value, str), f"RUBRICS[{key!r}] is not a string"


def test_rubric_for_unknown_raises_keyerror():
    """Verify rubric_for raises KeyError for unknown requirement IDs."""
    with pytest.raises(KeyError):
        rubric_for("NOPE")
