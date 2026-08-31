"""Abandoned intermediates get reclaimed.

Every temp file nSight writes is unlinked by the code that made it — on the
happy path. An exception between creating one and unlinking it leaks it, and
nothing swept the scratch directory, so a leak was permanent. It is on disk
now rather than in RAM, which makes it cheaper but not free.
"""
import os
import time

import pytest

from reportbuilder import cache_dirs
from reportbuilder.export import cleanup


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    monkeypatch.setenv("NSIGHT_CACHE_DIR", str(tmp_path))
    # cleanup binds its roots at import; rebind them to this test's cache root.
    monkeypatch.setattr(cleanup, "SCRATCH_ROOT", cache_dirs.scratch_root())
    return cache_dirs.scratch_root()


def test_an_abandoned_intermediate_is_swept(scratch):
    leaked = scratch / "nsight-upload-abandoned.sav"
    leaked.write_bytes(b"x" * 1024)
    old = time.time() - (48 * 60 * 60)
    os.utime(leaked, (old, old))
    n = cleanup.sweep_stale(scratch, 24 * 60 * 60)
    assert n == 1 and not leaked.exists()


def test_an_intermediate_still_in_use_is_left_alone(scratch):
    """A long render holds its work file open; sweeping it mid-write would
    break the request that created it."""
    live = scratch / "nsight-upload-live.sav"
    live.write_bytes(b"x" * 1024)
    assert cleanup.sweep_stale(scratch, 24 * 60 * 60) == 0
    assert live.exists()


def test_sweep_all_covers_the_scratch_directory(scratch, monkeypatch):
    """The regression this guards: scratch was not in sweep_all at all, so a
    leaked upload stayed forever."""
    leaked = scratch / "nsight-leaked.zip"
    leaked.write_bytes(b"x")
    old = time.time() - (48 * 60 * 60)
    os.utime(leaked, (old, old))
    result = cleanup.sweep_all()
    assert result.scratch == 1, result
    assert not leaked.exists()
    assert result.total >= 1
