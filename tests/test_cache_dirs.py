"""Where nSight keeps its on-disk caches.

Every one of these used to hang off `tempfile.gettempdir()`. On a host where
/tmp is a tmpfs — which is the default on this developer's machine and on many
distributions — that is RAM: 61 MB of rendered previews were sitting in memory
on a box with 4 GB. Rendered decks (`nsight-render`) are worse, being whole
PPTX/PDF files.
"""
import os
from pathlib import Path

import pytest

from reportbuilder import cache_dirs


def test_explicit_setting_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("NSIGHT_CACHE_DIR", str(tmp_path / "chosen"))
    assert cache_dirs.cache_root() == tmp_path / "chosen"


def test_falls_back_to_the_xdg_cache_location(monkeypatch, tmp_path):
    monkeypatch.delenv("NSIGHT_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert cache_dirs.cache_root() == tmp_path / "xdg" / "nsight"


def test_falls_back_to_home_cache(monkeypatch, tmp_path):
    monkeypatch.delenv("NSIGHT_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert cache_dirs.cache_root() == tmp_path / "home" / ".cache" / "nsight"


def test_the_root_is_created(monkeypatch, tmp_path):
    monkeypatch.setenv("NSIGHT_CACHE_DIR", str(tmp_path / "made"))
    assert cache_dirs.cache_root().is_dir()


def test_no_cache_lands_in_the_temp_dir_by_default(monkeypatch, tmp_path):
    """The whole point: a default install must not put caches on what may be a
    ramdisk. Asserted against HOME rather than the absence of the temp path —
    pytest's own tmp_path lives under /tmp, so a naive check tests the fixture
    instead of the code."""
    home = tmp_path / "home"
    monkeypatch.delenv("NSIGHT_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(home))
    expected = home / ".cache" / "nsight"
    for root in (cache_dirs.preview_root(), cache_dirs.render_root(),
                 cache_dirs.ground_root(), cache_dirs.template_root(),
                 cache_dirs.profile_root()):
        assert root.is_relative_to(expected), root
    # and never the temp-dir fallback, which only a broken config reaches
    assert "nsight-cache" not in str(cache_dirs.cache_root())


def test_each_root_is_distinct(monkeypatch, tmp_path):
    monkeypatch.setenv("NSIGHT_CACHE_DIR", str(tmp_path / "c"))
    roots = [cache_dirs.preview_root(), cache_dirs.render_root(),
             cache_dirs.ground_root(), cache_dirs.template_root(),
             cache_dirs.profile_root()]
    assert len(set(roots)) == len(roots)


def test_an_unwritable_setting_falls_back_rather_than_crashing(monkeypatch):
    """A cache that cannot be created must not take the server down; degrade to
    the temp dir and let the sweeper deal with it."""
    monkeypatch.setenv("NSIGHT_CACHE_DIR", "/proc/nsight-cannot-exist")
    root = cache_dirs.cache_root()
    assert root.is_dir()


# ------------------------------------------------------- intermediate files ---
# The caches were the visible half. The other half is every intermediate file
# written through `tempfile` directly — uploaded .sav files, backup/restore
# ZIPs, template .pptx uploads, chart PNGs — all of which defaulted to /tmp and
# so, on a tmpfs host, to RAM. An uploaded SPSS file is not small.

def test_scratch_is_under_the_cache_root(monkeypatch, tmp_path):
    monkeypatch.setenv("NSIGHT_CACHE_DIR", str(tmp_path / "c"))
    assert cache_dirs.scratch_root().is_relative_to(cache_dirs.cache_root())


def test_adopting_the_scratch_dir_redirects_plain_tempfile_use(monkeypatch, tmp_path):
    """One switch has to cover all fourteen call sites, not fourteen edits."""
    import tempfile
    monkeypatch.setenv("NSIGHT_CACHE_DIR", str(tmp_path / "c"))
    cache_dirs.use_disk_backed_tempdir()
    fd, path = tempfile.mkstemp()
    os.close(fd)
    try:
        assert Path(path).is_relative_to(cache_dirs.scratch_root())
    finally:
        os.unlink(path)
    d = tempfile.mkdtemp()
    assert Path(d).is_relative_to(cache_dirs.scratch_root())


def test_it_exports_tmpdir_so_subprocesses_follow(monkeypatch, tmp_path):
    """LibreOffice writes its own intermediates during a PPTX->PDF conversion.
    It is a child process, so only the environment reaches it."""
    monkeypatch.setenv("NSIGHT_CACHE_DIR", str(tmp_path / "c"))
    cache_dirs.use_disk_backed_tempdir()
    assert os.environ["TMPDIR"] == str(cache_dirs.scratch_root())


def test_adopting_twice_is_harmless(monkeypatch, tmp_path):
    monkeypatch.setenv("NSIGHT_CACHE_DIR", str(tmp_path / "c"))
    first = cache_dirs.use_disk_backed_tempdir()
    assert cache_dirs.use_disk_backed_tempdir() == first
