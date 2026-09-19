"""A preview asks the store each thing once.

Every call here is a round-trip to the hive — a separate 1-CPU VM on staging,
~50-200 ms each — and a preview the server had ALREADY drawn still made about
a dozen of them before returning the cached picture: the material resolved five
times (each re-reading its record), the customer's templates listed three times
by one resolution (each listing reading every template's record), the
template's corrections read twice. (perf, 2026-09-19)
"""
from __future__ import annotations

import collections
import pathlib
import traceback

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

_DECK = pathlib.Path("src/reportbuilder/render/assets/nsight_default.pptx")


class _Counting:
    """The in-memory store, counting what is asked of it."""

    def __init__(self, inner):
        self.inner = inner
        self.calls: list[tuple[str, str]] = []
        self.where: dict = collections.defaultdict(list)

    def _note(self, call):
        self.calls.append(call)
        # Where it was asked from, so a failure names the code that asked again.
        self.where[call].append(" < ".join(
            f"{f.name}:{f.lineno}" for f in reversed(traceback.extract_stack(limit=12))
            if "reportbuilder" in f.filename)[:300])

    def get(self, auth, path):
        self._note(("get", path))
        return self.inner.get(auth, path)

    def list(self, auth, path_prefix="", labels=()):
        self._note(("list", path_prefix))
        return self.inner.list(auth, path_prefix, labels)

    def put(self, *a, **k):
        return self.inner.put(*a, **k)

    def delete(self, *a, **k):
        return self.inner.delete(*a, **k)


@pytest.fixture
def seeded(tiny_sav):
    from reportbuilder.api.app import create_app
    from reportbuilder.api.deps_auth import current_user
    from reportbuilder.api.deps_store import get_auth, get_repository
    from reportbuilder.store.memory_objects import InMemoryObjectStore
    from reportbuilder.store.repository import Repository
    from reportbuilder.store.seam import AuthContext

    store = _Counting(InMemoryObjectStore())
    repo = Repository(store)
    auth = AuthContext(token="test")
    customer = repo.create_customer(auth, "Asiakas")
    case = repo.create_case(auth, customer.id, "Tutkimus")
    material = repo.attach_material(auth, customer.id, case.id, "tiny.sav",
                                    tiny_sav.read_bytes())
    template = repo.upload_template(auth, customer.id, "Pohja", _DECK.read_bytes())
    from reportbuilder.auth.permissions import Grant, User
    # A fixed user: the suite's usual override lists every customer on every
    # request, which is a store call production does not make.
    user = User(id="dev", email="dev@localhost", name="Dev", is_admin=True,
                grants=(Grant(customer.id, "edit"),))
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = lambda: user
    from reportbuilder.ingest.sav_reader import read_sav
    _df, model = read_sav(str(tiny_sav))
    qid = next(q.qid for q in model.questions if q.kind == "single")
    return TestClient(app), store, material.id, qid, template.id


def _body(qid: str, **extra) -> dict:
    return {**extra, "question_ref": qid, "chart_type": "vertical_bar",
            "statistic": "pct", "classifying_var": None,
            "number_format": {"mode": "auto"},
            "sort": {"basis": "data_order", "descending": True},
            "template_slot": "s1", "elements": {}, "render_title": False}


def _cached_preview_calls(seeded, **extra):
    client, store, material_id, qid, _tpl = seeded
    first = client.post(f"/materials/{material_id}/preview-chart", json=_body(qid, **extra))
    assert first.status_code == 200, first.text
    store.calls.clear()
    store.where.clear()
    again = client.post(f"/materials/{material_id}/preview-chart", json=_body(qid, **extra))
    assert again.status_code == 200, again.text
    return store


def test_a_cached_preview_asks_the_store_each_thing_once(seeded):
    """The editor names the report's template, as the Design page does."""
    store = _cached_preview_calls(seeded, template_id=seeded[4])
    repeated = {call: n for call, n in collections.Counter(store.calls).items() if n > 1}
    assert repeated == {}, "asked more than once:\n" + "\n".join(
        f"{call} x{n}:\n    " + "\n    ".join(store.where[call]) for call, n in repeated.items())


def test_resolving_the_template_server_side_stays_bounded(seeded):
    """With no template named, the server resolves it — report, pin, case and
    customer rungs — and names its file by listing the folder. Before
    2026-09-19 a cached preview made 17 store calls this way (7 now); the listing that
    resolution and the file's etag both need is still made twice."""
    store = _cached_preview_calls(seeded)
    assert len(store.calls) <= 8, store.calls
