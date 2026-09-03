"""The preview namespace must outlive a restart, without outliving a redeploy.

`_PREVIEW_CACHE_SALT` used to be `uuid4()`, so every server start threw away
every rendered preview and the first page load after a restart redrew the whole
report — one LibreOffice run per slide, minutes of an author's time spent on
pictures that had not changed.

Two properties keep that fixed and are both quiet to break: it must be STABLE
across processes (or restarts wipe the cache again), and it must MOVE when the
drawing code does (or a redeploy serves pictures the old code drew).
"""
import subprocess
import sys
import textwrap

_READ_SALT = textwrap.dedent("""
    from reportbuilder.api.routes_questions import _PREVIEW_CACHE_SALT
    print(_PREVIEW_CACHE_SALT)
""")


def _salt(env: dict) -> str:
    """The salt as a FRESH process computes it — the thing under test is what
    survives an interpreter, so it cannot be read from this one."""
    out = subprocess.run([sys.executable, "-c", _READ_SALT], capture_output=True,
                         text=True, env=env, check=True)
    return out.stdout.strip()


def _env(monkeypatch_environ: dict, **over) -> dict:
    env = dict(monkeypatch_environ)
    env.pop("NSIGHT_DATAHIVE_URL", None)
    env.update({k: v for k, v in over.items() if v is not None})
    return env


def test_a_durable_store_keeps_its_previews_across_a_restart(monkeypatch):
    import os
    env = _env(os.environ, NSIGHT_DATAHIVE_URL="https://hive.example")
    assert _salt(env) == _salt(env), (
        "the salt changed between processes, so every restart discards every "
        "cached preview and the next page load re-renders the whole report")


def test_an_in_memory_store_does_not(monkeypatch):
    """The original reason for a per-process salt, and it still holds.

    The in-memory store hands out `mat-1`, `mat-2`… from zero on each boot, so
    the same id means a DIFFERENT material after a restart. A stable salt there
    would serve one material's picture for another — worse than re-rendering.
    """
    import os
    env = _env(os.environ)
    assert _salt(env) != _salt(env), (
        "material ids are reused by the in-memory store, so the preview "
        "namespace must not survive a restart")


def test_the_salt_moves_when_the_drawing_code_does(tmp_path):
    """Otherwise a redeploy keeps serving pictures the previous code drew."""
    import os
    import pathlib

    import reportbuilder
    from reportbuilder.api.routes_questions import _render_code_identity

    before = _render_code_identity()
    target = pathlib.Path(reportbuilder.__file__).parent / "render" / "base.py"
    st = target.stat()
    try:
        os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        assert _render_code_identity() != before
    finally:
        os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert _render_code_identity() == before


def test_the_salt_moves_when_what_a_slide_CARRIES_changes(tmp_path):
    """The drawing code is not the only code that decides what a picture shows.

    A slide's elements are declared in `model/report.py` and mapped onto the
    preview's ChartSpec in `api/routes_questions.py`. Adding the "show a
    subtitle" switch changed both — and a cached preview drawn before the
    switch existed kept being served for a request that said `subtitle=false`,
    so turning the subtitle off appeared to do nothing at all. Scoping the
    identity to `render/` alone is what let a picture disagree with its own
    cache key.
    """
    import os
    import pathlib

    import reportbuilder
    from reportbuilder.api.routes_questions import _render_code_identity

    root = pathlib.Path(reportbuilder.__file__).parent
    for rel in ("model/report.py", "api/routes_questions.py"):
        before = _render_code_identity()
        target = root / rel
        st = target.stat()
        try:
            os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
            assert _render_code_identity() != before, (
                f"{rel} decides what a slide carries, but the preview cache "
                f"cannot tell that it changed")
        finally:
            os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
        assert _render_code_identity() == before
