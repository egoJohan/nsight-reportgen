"""Password hashing for the username/password sign-in method.

Spec §13 lists password sign-in as out of scope, and D1 chose Google + O365
"so nothing [is] to hash, reset, rotate or leak". The customer asked for a
password option anyway; this module is the one place that decision costs
anything.

Argon2id via argon2-cffi, at the library's own RFC 9106 "low memory"
defaults (argon2-cffi 25.1.0's PasswordHasher): time_cost=3,
memory_cost=65536 KiB, parallelism=4, hash_len=32, salt_len=16. Not
overridden — see the plan's Task 3 for why these are used as-is.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()

#: A real hash of a value nobody will ever type, so a caller can always run a
#: verify — same cost whether the account exists or not. See routes_auth.py.
DUMMY_HASH = _hasher.hash("nsight-timing-safe-dummy-3f9c2a")


def hash_password(password: str) -> str:
    """A self-describing Argon2id hash string, safe to store as-is."""
    if not password:
        raise ValueError("password must not be empty")
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """True if *password* matches *password_hash*. Never raises — a missing
    or malformed hash is just "does not match"."""
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
