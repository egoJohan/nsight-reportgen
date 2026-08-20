"""Argon2id hashing for the password sign-in method (see the module
docstring for why this exists despite spec §13 excluding it)."""
import pytest

from reportbuilder.auth.password import DUMMY_HASH, hash_password, verify_password


def test_a_hash_is_not_the_password_itself():
    h = hash_password("correct horse battery staple")
    assert "correct horse" not in h
    assert h.startswith("$argon2id$")


def test_the_right_password_verifies():
    h = hash_password("correct horse battery staple")
    assert verify_password(h, "correct horse battery staple") is True


def test_the_wrong_password_does_not_verify():
    h = hash_password("correct horse battery staple")
    assert verify_password(h, "wrong password entirely") is False


def test_two_hashes_of_the_same_password_differ():
    """Salted: identical passwords must not produce identical hashes."""
    assert hash_password("same password") != hash_password("same password")


def test_an_empty_password_is_refused():
    with pytest.raises(ValueError):
        hash_password("")


def test_verify_against_none_is_false_not_a_crash():
    assert verify_password(None, "anything") is False


def test_verify_against_garbage_is_false_not_a_crash():
    assert verify_password("not-a-real-hash", "anything") is False


def test_the_dummy_hash_never_verifies_a_real_password():
    """Used by routes_auth to keep an unknown-email login and a wrong-password
    login the same shape — see Task 5."""
    assert verify_password(DUMMY_HASH, "whatever the attacker guesses") is False
