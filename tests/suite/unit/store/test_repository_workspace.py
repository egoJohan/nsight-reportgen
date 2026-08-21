"""Per-user, per-case UI state (spec §8) -- the material pointer and
report list that used to live in the browser's localStorage.
"""
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


def test_an_unset_workspace_is_empty(repo, auth):
    assert repo.get_workspace(auth, "usr-1") == {}


def test_setting_one_cases_state_is_readable_back(repo, auth):
    repo.set_case_workspace(auth, "usr-1", "case-a", {"materialId": "mat-1", "reports": []})
    assert repo.get_workspace(auth, "usr-1") == {
        "case-a": {"materialId": "mat-1", "reports": []}}


def test_setting_a_second_case_does_not_disturb_the_first(repo, auth):
    repo.set_case_workspace(auth, "usr-1", "case-a", {"materialId": "mat-1", "reports": []})
    repo.set_case_workspace(auth, "usr-1", "case-b", {"materialId": "mat-2", "reports": []})
    ws = repo.get_workspace(auth, "usr-1")
    assert ws["case-a"]["materialId"] == "mat-1"
    assert ws["case-b"]["materialId"] == "mat-2"


def test_workspaces_are_isolated_per_user(repo, auth):
    repo.set_case_workspace(auth, "usr-1", "case-a", {"materialId": "mat-1", "reports": []})
    assert repo.get_workspace(auth, "usr-2") == {}


def test_overwriting_a_case_replaces_its_state_wholesale(repo, auth):
    repo.set_case_workspace(auth, "usr-1", "case-a", {"materialId": "mat-1", "reports": ["r1"]})
    repo.set_case_workspace(auth, "usr-1", "case-a", {"materialId": "mat-2", "reports": []})
    assert repo.get_workspace(auth, "usr-1")["case-a"] == {"materialId": "mat-2", "reports": []}
