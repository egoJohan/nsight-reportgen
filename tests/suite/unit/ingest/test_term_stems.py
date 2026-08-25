"""A registered term has to match the forms Finnish actually writes.

datahive matches deny-list terms as case-insensitive substrings, which already
covers most inflection — `Attendo` catches `Attendosta`, `Attendon`,
`Attendolla`, because the stem does not move. Finnish nominals whose stem DOES
move are the hole, and they are not exotic: every `-nen` word takes `-se-`
(`Mehiläinen` → `Mehiläisen`, `Mehiläisestä`), and that is one of the commonest
shapes a Finnish company name has.

Measured against the live hive before this existed: `Mehiläisestä` and
`Mehiläisen palvelut` were not detected at all. A missed mention is a real name
reaching the model.

Over-generating is the safe direction. An extra stem masks a little more than
it must; a missing one leaks.
"""
from __future__ import annotations

import pytest

from reportbuilder.ingest.sensitive_terms import expand_term_stems


def _covers(term: str, *forms: str) -> list[str]:
    """Forms that no generated stem matches — i.e. what would still leak."""
    stems = [s.lower() for s in expand_term_stems(term)]
    return [f for f in forms if not any(s in f.lower() for s in stems)]


def test_a_nen_word_matches_its_inflected_stem():
    """The case that was leaking."""
    assert _covers("Mehiläinen",
                   "Mehiläinen", "Mehiläisen", "Mehiläisestä", "Mehiläiselle",
                   "Mehiläisellä", "Mehiläistä") == []


def test_another_nen_company():
    assert _covers("Terveyskeskuksinen", "Terveyskeskuksisen") == []


def test_a_stable_stem_is_left_alone():
    """Most names do not move: `Attendo` already covers every form, and
    inventing extra stems for it would only widen what gets masked."""
    assert expand_term_stems("Attendo") == ["Attendo"]
    assert _covers("Attendo", "Attendo", "Attendosta", "Attendon", "Attendolla") == []


def test_multi_word_names_inflect_on_the_last_word_only():
    """Finnish inflects the final element of a multi-word name; the rest stay
    put. So the stem to add is the whole name with only its tail changed."""
    assert _covers("Esperi Care Oy", "Esperi Care Oy", "Esperi Care Oy:n") == []
    stems = expand_term_stems("Suomen Hoivapalveluinen")
    assert any(s.startswith("Suomen Hoivapalvelui") for s in stems), stems


def test_it_never_returns_a_stem_short_enough_to_match_anything():
    """A two-character stem would match half the language. Anything that short
    is dropped rather than registered — masking every word is not privacy, it
    is a broken report."""
    # The term itself is always kept — an analyst who typed it meant it. It is
    # the DERIVED stems that must not be trivially short.
    derived = expand_term_stems("Nen")[1:]
    assert derived == [], f"generated a stem from a 3-letter word: {derived}"
    derived = expand_term_stems("Suominen")[1:]
    assert all(len(s) >= 4 for s in derived), derived


def test_the_original_always_comes_first():
    """datahive substitutes longest-first, and the caller sorts on that; the
    nominative must still be in the list at all."""
    stems = expand_term_stems("Mehiläinen")
    assert stems[0] == "Mehiläinen"
    assert "Mehiläis" in stems, stems


def test_empty_and_odd_input_is_not_a_crash():
    assert expand_term_stems("") == []
    assert expand_term_stems("   ") == []
