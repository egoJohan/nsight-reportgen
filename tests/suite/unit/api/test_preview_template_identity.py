"""A re-uploaded template is a different template, whatever its length.

The preview writes the chosen template to a temp file and renders from there.
That file used to be rewritten only when its LENGTH differed, so re-uploading a
template that happened to be the same number of bytes kept serving the old one
— and now that resolution is cached on the file, it would keep the old fonts,
palette and type sizes with it.

The name is now built from an IDENTITY string rather than from the bytes: the
caller passes the store's etag where there is one, so a warm preview can name
the cached file without downloading 600KB to hash it, and a sha256 of the blob
otherwise. Both are content-derived, which is the property these tests are
about — but the derivation itself moved to the caller, and lives in
`test_preview_template_is_not_refetched.test_a_changed_template_is_picked_up`.
(Johan, 2026-09-16)
"""
from __future__ import annotations

import hashlib

from reportbuilder.api.routes_questions import _preview_template_filename


def _identity(blob: bytes) -> str:
    """What `_preview_template` passes when the store offers no etag."""
    return hashlib.sha256(blob).hexdigest()


def test_same_length_different_bytes_get_different_files():
    a, b = b"A" * 4096, b"B" * 4096
    assert (_preview_template_filename("tpl-1", identity=_identity(a))
            != _preview_template_filename("tpl-1", identity=_identity(b)))


def test_identical_bytes_get_the_same_file():
    blob = b"A" * 4096
    assert (_preview_template_filename("tpl-1", identity=_identity(blob))
            == _preview_template_filename("tpl-1", identity=_identity(blob)))


def test_the_name_carries_the_identity():
    blob = b"A" * 4096
    assert _identity(blob)[:16] in _preview_template_filename(
        "tpl-1", identity=_identity(blob))


def test_different_templates_do_not_share_a_file():
    blob = b"A" * 4096
    assert (_preview_template_filename("tpl-1", identity=_identity(blob))
            != _preview_template_filename("tpl-2", identity=_identity(blob)))


def test_a_missing_template_id_still_names_a_file():
    assert _preview_template_filename(
        "", identity=_identity(b"A" * 16)).startswith("default.")


def test_two_identities_never_collide_in_the_name():
    """The name truncates the identity, so the truncation has to be the part
    that varies — a rule that would be wrong if it took a suffix."""
    a, b = _identity(b"A" * 4096), _identity(b"B" * 4096)
    assert a[:16] != b[:16]
