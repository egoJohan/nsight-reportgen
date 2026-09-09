"""A template that changed must not look unchanged to the preview cache.

A slide's image fingerprint carried the template's ID. That is right for
"which template does this report use" and wrong for "has that template
changed": replacing the .pptx, or moving a box in the layout editor, leaves the
id alone, so every preview in every report drawn on it kept its fingerprint and
its stale picture. The layout editor dropped its own react-query cache on save,
which fixed the tab it was saved in and nothing else — not another tab, not
another user, not the next session.

The revision is what the fingerprint should carry instead: it changes whenever
anything that alters how the template DRAWS changes, and is derived rather than
stored, so nothing has to remember to bump it. (Johan, 2026-09-09)
"""
from __future__ import annotations

import pytest

from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


def _customer(repo, auth):
    return repo.create_customer(auth, "Attendo").id


def test_the_revision_changes_when_the_file_is_replaced(repo, auth):
    cid = _customer(repo, auth)
    t = repo.upload_template(auth, cid, "House", b"PK-one")
    before = repo.template_revision(auth, cid, t.id)

    t2 = repo.upload_template(auth, cid, "House", b"PK-two-different")
    after = repo.template_revision(auth, cid, t2.id)

    assert before and after and before != after


def test_the_revision_changes_when_the_layout_is_edited(repo, auth):
    cid = _customer(repo, auth)
    t = repo.upload_template(auth, cid, "House", b"PK-one")
    before = repo.template_revision(auth, cid, t.id)

    repo.record_template_layout(auth, cid, t.id, {"title": {"x": 2.0, "y": 1.0}})
    after = repo.template_revision(auth, cid, t.id)

    assert before != after, "moving the title box left every preview looking fresh"


def test_it_is_stable_when_nothing_changed(repo, auth):
    """A revision that moved on its own would re-render every slide of every
    report on every page load."""
    cid = _customer(repo, auth)
    t = repo.upload_template(auth, cid, "House", b"PK-one")
    assert repo.template_revision(auth, cid, t.id) == \
        repo.template_revision(auth, cid, t.id)


def test_two_templates_do_not_share_a_revision(repo, auth):
    cid = _customer(repo, auth)
    a = repo.upload_template(auth, cid, "A", b"PK-one")
    b = repo.upload_template(auth, cid, "B", b"PK-one")   # same bytes, different id
    assert repo.template_revision(auth, cid, a.id) != \
        repo.template_revision(auth, cid, b.id)


def test_a_template_that_is_gone_has_no_revision(repo, auth):
    """The house default is "no template", and must not look like a changed
    one on every call."""
    cid = _customer(repo, auth)
    assert repo.template_revision(auth, cid, "") == ""
    assert repo.template_revision(auth, cid, "tpl-missing") == ""
