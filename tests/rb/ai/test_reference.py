"""Unit tests for the reference-label corpus matching (C.3).

Uses a tiny in-memory corpus — no real pptx required.
"""
from __future__ import annotations

from reportbuilder.ai.reference import ReferenceLabels, _normalize


def _corpus() -> ReferenceLabels:
    # Short reference labels (the human-authored short forms).
    return ReferenceLabels(
        labels=[
            "Erittäin tyytyväinen",
            "Melko tyytyväinen",
            "En osaa sanoa",
            "Attendo",
        ],
        titles=["Asiakastyytyväisyys"],
    )


def test_exact_normalized_hit_returns_shorter_reference() -> None:
    ref = _corpus()
    # Full label differs only by trailing punctuation/space -> normalizes equal,
    # and the reference candidate is strictly shorter than the raw input.
    out = ref.match("Erittäin tyytyväinen.")
    assert out == "Erittäin tyytyväinen"


def test_fuzzy_hit_above_threshold() -> None:
    ref = _corpus()
    # Near-identical longer label (normalizes differently -> not an exact hit),
    # ratio ~0.94 against "Melko tyytyväinen", and strictly longer than it.
    out = ref.match("Melko tyytyväinen 1")
    assert out == "Melko tyytyväinen"


def test_miss_returns_none() -> None:
    ref = _corpus()
    assert ref.match("Täysin eri mieltä olevat vastaajat") is None


def test_never_returns_longer_or_equal() -> None:
    ref = _corpus()
    # Input shorter than every corpus label -> no candidate may be returned,
    # even though "Attendo" is an exact normalized match for "Attendo".
    assert ref.match("Attendo") is None  # equal length -> rejected
    assert ref.match("Att") is None      # shorter than corpus -> rejected


def test_match_guarantee_property() -> None:
    ref = _corpus()
    for probe in ["Erittäin tyytyväinen.", "Melko tyytyväinen kaikkeen", "Attendo", "x"]:
        out = ref.match(probe)
        if out is not None:
            assert len(out) < len(probe)


def test_examples_are_short_and_deduped() -> None:
    ref = _corpus()
    ex = ref.examples(2)
    assert len(ex) == 2
    assert len(set(ex)) == 2
    # shortest-first ordering
    assert ex[0] == "Attendo"


def test_load_tolerates_missing_files(tmp_path) -> None:
    missing = tmp_path / "nope.pptx"
    ref = ReferenceLabels.load([missing])
    assert ref.labels == []
    assert ref.match("anything") is None


def test_normalize() -> None:
    assert _normalize("  Erittäin,  Tyytyväinen!  ") == "erittäin tyytyväinen"
