"""A re-uploaded template is a different template, whatever its length.

The preview writes the chosen template to a temp file and renders from there.
That file used to be rewritten only when its LENGTH differed, so re-uploading a
template that happened to be the same number of bytes kept serving the old one
— and now that resolution is cached on the file, it would keep the old fonts,
palette and type sizes with it.
"""
from __future__ import annotations

import hashlib

from reportbuilder.api.routes_questions import _preview_template_filename


def test_same_length_different_bytes_get_different_files():
    a = b"A" * 4096
    b = b"B" * 4096
    assert _preview_template_filename("tpl-1", a) != _preview_template_filename("tpl-1", b)


def test_identical_bytes_get_the_same_file():
    blob = b"A" * 4096
    assert _preview_template_filename("tpl-1", blob) == _preview_template_filename("tpl-1", blob)


def test_the_name_carries_the_content_hash():
    blob = b"A" * 4096
    assert hashlib.sha256(blob).hexdigest()[:16] in _preview_template_filename("tpl-1", blob)


def test_different_templates_do_not_share_a_file():
    blob = b"A" * 4096
    assert _preview_template_filename("tpl-1", blob) != _preview_template_filename("tpl-2", blob)


def test_a_missing_template_id_still_names_a_file():
    assert _preview_template_filename("", b"A" * 16).startswith("default.")
