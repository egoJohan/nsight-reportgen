"""One request, one resolution — shared across dependencies.

`RepositoryClient` memoises the case it resolves, but the auth guard resolves
it too, through `repo.find_case` directly. Two dependencies of the SAME request
therefore each paid for the same lookup, which is why `case.json` still showed
up twice per request after the client-side memo. They need to share one scope.
"""
from types import SimpleNamespace

from reportbuilder.api.deps import request_scope


def _request():
    return SimpleNamespace(state=SimpleNamespace())


def test_the_same_request_gets_the_same_dict():
    r = _request()
    a = request_scope(r, "case")
    a["k"] = 1
    assert request_scope(r, "case") is a


def test_different_names_do_not_collide():
    r = _request()
    assert request_scope(r, "case") is not request_scope(r, "material")


def test_a_different_request_starts_empty():
    """The scope must not outlive the request, or a later caller could be
    served a case whose access has since changed."""
    first = request_scope(_request(), "case")
    first["k"] = 1
    assert request_scope(_request(), "case") == {}


def test_it_survives_a_request_without_usable_state():
    """An internal caller may have no Request at all; it must still work,
    just without sharing."""
    assert request_scope(None, "case") == {}
