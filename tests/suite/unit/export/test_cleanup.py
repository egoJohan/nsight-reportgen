"""Evicting the temp caches.

Everything swept here is derived — the deck lives in datahive, the PDF and
rasters come from the deck, a LibreOffice profile is one process's scratch
space. So these tests care mostly about what must NOT be deleted.
"""
import os
import time
from pathlib import Path

import pytest

from reportbuilder.export import cleanup


@pytest.fixture
def roots(tmp_path, monkeypatch):
    render = tmp_path / "nsight-render"
    preview = tmp_path / "nsight-preview"
    profiles = tmp_path / "nsight-lo-profiles"
    templates = tmp_path / "nsight-preview-templates"
    ground = tmp_path / "nsight-preview-ground"
    # The scratch root is redirected too. Left pointing at the real one, a sweep
    # counted whatever ANY other test in the run had left there, so
    # `total == 3` held or failed depending on which tests ran first — and
    # adding a test elsewhere in the suite was enough to break this one.
    scratch = tmp_path / "nsight-scratch"
    for d in (render, preview, profiles, templates, ground, scratch):
        d.mkdir()
    monkeypatch.setattr(cleanup, "RENDER_ROOT", render)
    monkeypatch.setattr(cleanup, "PREVIEW_ROOT", preview)
    monkeypatch.setattr(cleanup, "PROFILE_ROOT", profiles)
    monkeypatch.setattr(cleanup, "TEMPLATE_ROOT", templates)
    monkeypatch.setattr(cleanup, "GROUND_ROOT", ground)
    monkeypatch.setattr(cleanup, "SCRATCH_ROOT", scratch)
    return render, preview, profiles


def _age(path: Path, seconds: float) -> None:
    old = time.time() - seconds
    os.utime(path, (old, old))


class TestStaleSweep:
    def test_old_preview_entries_go_and_fresh_ones_stay(self, roots):
        _, preview, _ = roots
        (preview / "old").mkdir()
        (preview / "fresh").mkdir()
        _age(preview / "old", 48 * 3600)

        assert cleanup.sweep_stale(preview, 24 * 3600) == 1
        assert not (preview / "old").exists()
        assert (preview / "fresh").exists()

    def test_render_cache_is_swept_per_report_not_per_case(self, roots):
        # depth=2: a case holds many reports, and one going cold must not take
        # the others with it.
        render, _, _ = roots
        case = render / "case-1"
        (case / "rep-old").mkdir(parents=True)
        (case / "rep-fresh").mkdir(parents=True)
        _age(case / "rep-old", 48 * 3600)

        assert cleanup.sweep_stale(render, 24 * 3600, depth=2) == 1
        assert not (case / "rep-old").exists()
        assert (case / "rep-fresh").exists()
        assert case.exists(), "a case with a live report must survive"

    def test_a_case_emptied_by_the_sweep_is_removed_too(self, roots):
        render, _, _ = roots
        case = render / "case-1"
        (case / "rep-old").mkdir(parents=True)
        _age(case / "rep-old", 48 * 3600)

        cleanup.sweep_stale(render, 24 * 3600, depth=2)
        assert not case.exists()

    def test_a_missing_root_is_not_an_error(self, tmp_path):
        assert cleanup.sweep_stale(tmp_path / "never-created", 1) == 0


class TestProfileSweep:
    def test_a_dead_process_profile_goes(self, roots):
        _, _, profiles = roots
        # A pid that cannot be running: os.kill(0) would raise ProcessLookupError.
        dead = profiles / "pid-999999"
        dead.mkdir()
        assert cleanup.sweep_orphaned_profiles() == 1
        assert not dead.exists()

    def test_our_own_profile_is_never_removed(self, roots):
        # Deleting the running process's own scratch space would break the very
        # render that is using it.
        _, _, profiles = roots
        mine = profiles / f"pid-{os.getpid()}"
        mine.mkdir()
        assert cleanup.sweep_orphaned_profiles() == 0
        assert mine.exists()

    def test_unrecognised_directory_names_are_left_alone(self, roots):
        _, _, profiles = roots
        (profiles / "not-a-pid-dir").mkdir()
        (profiles / "pid-notanumber").mkdir()
        assert cleanup.sweep_orphaned_profiles() == 0
        assert len(list(profiles.iterdir())) == 2


class TestSweepAll:
    def test_reports_what_it_removed(self, roots):
        render, preview, profiles = roots
        (render / "c" / "r").mkdir(parents=True)
        _age(render / "c" / "r", 48 * 3600)
        (preview / "p").mkdir()
        _age(preview / "p", 48 * 3600)
        (profiles / "pid-999999").mkdir()

        result = cleanup.sweep_all(24 * 3600)
        assert (result.render, result.preview, result.profiles) == (1, 1, 1)
        assert result.total == 3

    def test_it_sweeps_the_template_copies_and_the_blank_slides(self, roots,
                                                                tmp_path):
        """Neither root was ever swept.

        A copy of every distinct template CONTENT anyone has previewed with, and
        a LibreOffice-drawn blank slide per template, kept for the life of the
        host. They had reached 16 MB on this machine — in a /tmp that is a
        ramfs, so real memory — and nothing took any of them away again. Both
        are content-keyed caches: removing one costs the next request a rebuild
        and nothing else.
        """
        templates = tmp_path / "nsight-preview-templates"
        ground = tmp_path / "nsight-preview-ground"
        stale_tpl = templates / "tpl.abc123.pptx"
        stale_tpl.write_bytes(b"PK")
        _age(stale_tpl, 48 * 3600)
        stale_png = ground / "abc123.png"
        stale_png.write_bytes(b"\x89PNG")
        _age(stale_png, 48 * 3600)
        fresh = templates / "tpl.def456.pptx"
        fresh.write_bytes(b"PK")

        result = cleanup.sweep_all(24 * 3600)
        assert (result.templates, result.grounds) == (1, 1)
        assert not stale_tpl.exists() and not stale_png.exists()
        assert fresh.exists(), "a template in use today is not swept out from under it"

    def test_a_failure_never_propagates(self, roots, monkeypatch):
        # A janitor that stops the app from starting is worse than a full disk.
        monkeypatch.setattr(cleanup, "sweep_stale",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
        assert cleanup.sweep_all().total == 0
