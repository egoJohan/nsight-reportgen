"""The parsed-SAV cache under concurrent requests.

`_parse` keeps the last few parsed SAV files in a module-level OrderedDict,
shared by every request. The frame it hands back is copied and the model is
immutable, so the DATA is safe. The cache BOOKKEEPING is not: a hit reads the
entry, then calls `move_to_end` on it, and between those two steps another
thread inserting a different material can evict that key. `move_to_end` then
raises KeyError and the request 500s.

It needs more materials in play than the cache holds, which is why it does not
show up on a single-material dev box and would show up on a shared one.
"""
import threading

import pytest

from reportbuilder.api import model_loader as ML


@pytest.fixture
def fake_sav(monkeypatch):
    """Parsing is irrelevant here; the cache bookkeeping is the subject."""
    import pandas as pd

    from reportbuilder.model.question import QuestionModel

    def read_sav(path):
        return pd.DataFrame({"a": [1]}), QuestionModel(variables={}, questions=[])

    monkeypatch.setattr(ML, "read_sav", read_sav)
    monkeypatch.setattr(ML, "sav_file_label", lambda p: "")
    ML._forget_parsed_savs()
    return read_sav


def test_concurrent_parses_across_many_materials_do_not_crash(fake_sav):
    """More distinct materials than the cache holds, hammered together."""
    blobs = [f"sav-{i}".encode() for i in range(ML._PARSED_MAX * 3)]
    errors: list[BaseException] = []
    start = threading.Barrier(8)

    def worker(n: int):
        start.wait()
        for i in range(150):
            try:
                ML._parse(blobs[(n + i) % len(blobs)])
            except BaseException as e:  # noqa: BLE001
                errors.append(e)
                return

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"{type(errors[0]).__name__}: {errors[0]}"


def test_an_entry_evicted_between_the_hit_and_the_touch(fake_sav, monkeypatch):
    """The exact interleaving, forced rather than raced for.

    A cache HIT reads the entry and then calls `move_to_end` on it. If another
    request evicts that key in between — which needs only that it inserts a
    material while the cache is full — the touch raises KeyError and the
    request fails. The GIL makes the natural window tiny, so this widens it
    instead of hoping to hit it.
    """
    from collections import OrderedDict

    gate = threading.Event()
    opened = threading.Event()

    class SlowHit(OrderedDict):
        """Stalls inside the read, exactly where the real window is."""

        def get(self, key, default=None):
            hit = super().get(key, default)
            if hit is not None and not opened.is_set():
                opened.set()
                gate.wait(2)          # another request runs here
            return hit

    cache = SlowHit()
    monkeypatch.setattr(ML, "_PARSED", cache)

    victim = b"sav-victim"
    ML._parse(victim)                                  # seed the victim entry
    for i in range(ML._PARSED_MAX - 1):                # fill to capacity
        ML._parse(f"sav-filler-{i}".encode())

    failure: list[BaseException] = []

    def reader():
        try:
            ML._parse(victim)                          # hit, then stall, then touch
        except BaseException as e:  # noqa: BLE001
            failure.append(e)

    t = threading.Thread(target=reader)
    t.start()
    assert opened.wait(2), "the reader never reached the cache read"
    ML._parse(b"sav-evictor")                          # overflows -> evicts the victim
    gate.set()
    t.join(5)

    assert not failure, (
        f"a concurrent eviction broke a cache hit: "
        f"{type(failure[0]).__name__}: {failure[0]}")
