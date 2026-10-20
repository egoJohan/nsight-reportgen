"""The hive reads a preview repeats, served from this process instead.

In the hour before staging's backend was killed for memory (2026-09-29) it
fetched one material's .config from the hive 4,476 times and the whole .sav
1,003 times — for sixty-odd requests from one author. The .sav never changes
after upload; the .config is written only by this process. The two access
settings are asked on every request.

What may be cached, and for how long, is the policy under test here: a cache
that serves something stale is a wrong chart or, for the access settings, a
person reaching a customer an admin has just closed.
"""
from __future__ import annotations

import threading

import pytest

from reportbuilder.store import paths as P
from reportbuilder.store.caching_objects import CachingObjectStore
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.seam import AuthContext, NotFound, StoreError

AUTH = AuthContext(token="t")
SAV = P.material_path("cust-aaaaaaaaaaaa", "case-bbbbbbbbbbbb", "mat-cccccccccccc")
CONFIG = P.material_config_path("cust-aaaaaaaaaaaa", "case-bbbbbbbbbbbb",
                                "mat-cccccccccccc")
ACCESS = P.settings_path("customer-access.json")
REPORT = P.report_path("cust-aaaaaaaaaaaa", "case-bbbbbbbbbbbb", "rep-dddddddddddd")


class Counting:
    """The real in-memory store, counting reads that reach it."""

    def __init__(self):
        self.inner = InMemoryObjectStore()
        self.gets: list[str] = []
        self.fail_next_get = False

    def put(self, auth, path, data, content_type, labels=()):
        return self.inner.put(auth, path, data, content_type, labels)

    def get(self, auth, path):
        self.gets.append(path)
        if self.fail_next_get:
            self.fail_next_get = False
            raise StoreError("hive timed out", status_code=504)
        return self.inner.get(auth, path)

    def list(self, auth, path_prefix="", labels=()):
        return self.inner.list(auth, path_prefix, labels)

    def delete(self, auth, path):
        self.inner.delete(auth, path)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def world():
    hive = Counting()
    clock = Clock()
    return hive, CachingObjectStore(hive, clock=clock), clock


def _delete(store, path):
    """The in-memory store, like datahive, wants consent before a delete."""
    from reportbuilder.store.seam import ConsentRequired
    try:
        store.delete(AUTH, path)
    except ConsentRequired as consent:
        store.inner.inner.approve(consent.request_id)
        store.delete(AUTH, path)


def test_a_material_is_fetched_from_the_hive_once(world):
    hive, store, clock = world
    hive.put(AUTH, SAV, b"sav-bytes", "application/octet-stream")

    for _ in range(5):
        assert store.get(AUTH, SAV) == b"sav-bytes"
        clock.now += 3600

    assert hive.gets.count(SAV) == 1


def test_a_deleted_material_is_gone_at_once(world):
    hive, store, _ = world
    store.put(AUTH, SAV, b"sav-bytes", "application/octet-stream")
    store.get(AUTH, SAV)

    _delete(store, SAV)

    with pytest.raises(NotFound):
        store.get(AUTH, SAV)


def test_only_a_few_materials_are_held(world):
    hive, store, _ = world
    paths = [P.material_path("cust-aaaaaaaaaaaa", "case-bbbbbbbbbbbb",
                             f"mat-{i:012d}") for i in range(store.MAX_MATERIALS + 1)]
    for p in paths:
        hive.put(AUTH, p, p.encode(), "application/octet-stream")
        store.get(AUTH, p)

    store.get(AUTH, paths[0])

    assert hive.gets.count(paths[0]) == 2, "the oldest material was not evicted"


def test_a_config_is_asked_of_the_hive_once_per_window(world):
    hive, store, clock = world
    hive.put(AUTH, CONFIG, b'{"v": 1}', "application/json")

    for _ in range(50):
        store.get(AUTH, CONFIG)
        clock.now += 1

    assert hive.gets.count(CONFIG) == 1


def test_a_config_written_here_is_read_back_at_once(world):
    hive, store, _ = world
    store.put(AUTH, CONFIG, b'{"v": 1}', "application/json")
    store.get(AUTH, CONFIG)
    store.put(AUTH, CONFIG, b'{"v": 2}', "application/json")

    assert store.get(AUTH, CONFIG) == b'{"v": 2}'


def test_a_write_the_hive_refused_leaves_nothing_held(world):
    """It may have landed anyway (a timeout after the commit): what the hive
    holds is unknown, so the next read asks it."""
    hive, store, _ = world
    store.put(AUTH, CONFIG, b'{"v": 1}', "application/json")
    store.get(AUTH, CONFIG)
    real_put = hive.put

    def put_then_time_out(*a, **k):
        real_put(*a, **k)
        raise StoreError("hive timed out", status_code=504)

    hive.put = put_then_time_out
    with pytest.raises(StoreError):
        store.put(AUTH, CONFIG, b'{"v": 2}', "application/json")
    hive.put = real_put

    assert store.get(AUTH, CONFIG) == b'{"v": 2}'


def test_two_writes_at_once_leave_the_hives_answer(world):
    """The hive keeps whichever write landed last; the cache must not keep the
    other one. Writes drop the held copy rather than replace it."""
    hive, store, _ = world
    landed = []
    real_put = hive.put
    second_landed, first_may_finish = threading.Event(), threading.Event()

    def ordered_put(auth, path, data, ct, labels=()):
        if data == b'{"v": "first"}':
            real_put(auth, path, data, ct, labels)       # lands first...
            landed.append("first")
            first_may_finish.wait(5)                     # ...returns last
        else:
            real_put(auth, path, data, ct, labels)
            landed.append("second")
            second_landed.set()

    hive.put = ordered_put
    t = threading.Thread(target=store.put,
                         args=(AUTH, CONFIG, b'{"v": "first"}', "application/json"))
    t.start()
    while not landed:
        pass
    store.put(AUTH, CONFIG, b'{"v": "second"}', "application/json")
    second_landed.wait(5)
    first_may_finish.set()
    t.join(5)
    hive.put = real_put

    assert store.get(AUTH, CONFIG) == hive.inner.get(AUTH, CONFIG) == b'{"v": "second"}'


def test_a_config_changed_elsewhere_is_seen_once_it_expires(world):
    hive, store, clock = world
    hive.put(AUTH, CONFIG, b'{"v": 1}', "application/json")
    store.get(AUTH, CONFIG)
    hive.put(AUTH, CONFIG, b'{"v": 2}', "application/json")  # a backup restore

    clock.now += store.CONFIG_SECONDS + 1

    assert store.get(AUTH, CONFIG) == b'{"v": 2}'


def test_access_settings_are_asked_of_the_hive_once_per_window(world):
    hive, store, clock = world
    hive.put(AUTH, ACCESS, b'{"modes": {}}', "application/json")

    for _ in range(20):
        store.get(AUTH, ACCESS)
        clock.now += 0.1

    assert hive.gets.count(ACCESS) == 1


def test_access_settings_changed_here_apply_at_once(world):
    hive, store, _ = world
    store.put(AUTH, ACCESS, b'{"modes": {}}', "application/json")
    store.get(AUTH, ACCESS)

    store.put(AUTH, ACCESS, b'{"modes": {"cust-x": "manual"}}', "application/json")

    assert store.get(AUTH, ACCESS) == b'{"modes": {"cust-x": "manual"}}'


def test_access_settings_changed_elsewhere_apply_within_seconds(world):
    hive, store, clock = world
    hive.put(AUTH, ACCESS, b'{"modes": {}}', "application/json")
    store.get(AUTH, ACCESS)
    hive.put(AUTH, ACCESS, b'{"modes": {"cust-x": "manual"}}', "application/json")

    assert store.ACCESS_SECONDS <= 5
    clock.now += store.ACCESS_SECONDS + 0.01

    assert store.get(AUTH, ACCESS) == b'{"modes": {"cust-x": "manual"}}'


def test_a_failed_read_is_not_remembered(world):
    hive, store, _ = world
    hive.put(AUTH, ACCESS, b'{"modes": {}}', "application/json")
    hive.fail_next_get = True

    with pytest.raises(StoreError):
        store.get(AUTH, ACCESS)

    assert store.get(AUTH, ACCESS) == b'{"modes": {}}'


def test_an_absent_object_is_not_remembered(world):
    hive, store, _ = world
    with pytest.raises(NotFound):
        store.get(AUTH, CONFIG)
    hive.put(AUTH, CONFIG, b'{"v": 1}', "application/json")

    assert store.get(AUTH, CONFIG) == b'{"v": 1}'


def test_everything_else_goes_to_the_hive_every_time(world):
    hive, store, _ = world
    hive.put(AUTH, REPORT, b"{}", "application/json")

    store.get(AUTH, REPORT)
    store.get(AUTH, REPORT)

    assert hive.gets.count(REPORT) == 2


def test_a_read_racing_a_write_cannot_put_back_the_old_value(world):
    """A read that left for the hive before a write must not store what it
    brings back over what was written meanwhile."""
    hive, store, _ = world
    hive.put(AUTH, CONFIG, b'{"v": 1}', "application/json")
    in_flight, release = threading.Event(), threading.Event()
    real_get = hive.get

    def slow_get(auth, path):
        data = real_get(auth, path)
        in_flight.set()
        release.wait(5)
        return data

    hive.get = slow_get
    reader = threading.Thread(target=store.get, args=(AUTH, CONFIG))
    reader.start()
    in_flight.wait(5)
    store.put(AUTH, CONFIG, b'{"v": 2}', "application/json")
    release.set()
    reader.join(5)
    hive.get = real_get

    assert store.get(AUTH, CONFIG) == b'{"v": 2}'


def test_the_deployed_repository_reads_the_hive_through_the_cache(monkeypatch):
    from reportbuilder.api.deps_store import build_repository
    from reportbuilder.store.datahive_objects import DataHiveObjectStore

    monkeypatch.setenv("NSIGHT_DATAHIVE_URL", "http://hive.invalid:7891")
    store = build_repository().store

    assert isinstance(store, CachingObjectStore)
    assert isinstance(store.inner, DataHiveObjectStore)


class TestReadModifyWriteReadsTheHive:
    """A change made behind the cache — by the second backend a deploy runs
    beside the first, or a restore — must not be overwritten by a write that
    started from the held copy. Serving a stale read for a minute is a wrong
    chart; writing one back is a lost edit."""

    def _repo(self, world):
        from reportbuilder.store.repository import Repository
        hive, store, _ = world
        repo = Repository(store)
        cu = repo.create_customer(AUTH, "K", owner_id="usr-1")
        ca = repo.create_case(AUTH, cu.id, "T")
        mat = repo.attach_material(AUTH, cu.id, ca.id, "s.sav", b"sav")
        return hive, repo, cu.id, ca.id, mat.id

    def test_a_material_config_update(self, world):
        hive, repo, cu, ca, mid = self._repo(world)
        repo.update_material_config(AUTH, cu, ca, mid, lambda c: c.update(a=1))
        repo.load_material_config(AUTH, cu, ca, mid)  # now held

        path = P.material_config_path(cu, ca, mid)
        import json
        d = json.loads(hive.inner.get(AUTH, path))
        d["config"]["b"] = 2                               # the other backend
        hive.put(AUTH, path, json.dumps(d).encode(), "application/json")

        out = repo.update_material_config(AUTH, cu, ca, mid, lambda c: c.update(c=3))

        assert out == {"a": 1, "b": 2, "c": 3}

    def test_a_customer_access_mode(self, world):
        hive, repo, *_ = self._repo(world)
        repo.set_customer_mode(AUTH, "cust-one", "manual")
        repo.customer_modes(AUTH)  # now held

        hive.put(AUTH, ACCESS, b'{"modes": {"cust-one": "manual", "cust-two": "manual"}}',
                 "application/json")
        modes = repo.set_customer_mode(AUTH, "cust-three", "manual")

        assert modes == {"cust-one": "manual", "cust-two": "manual",
                         "cust-three": "manual"}
