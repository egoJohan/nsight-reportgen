"""A process that has rendered a preview must exit cleanly.

Any process that runs the stats engine and then exits normally dies with
`terminate called without an active exception` — SIGABRT, exit code 134, core
dumped. The work finishes first; the abort happens at interpreter teardown:

    DuckDBPyConnection::~DuckDBPyConnection()   <- destructor, during finalize
    PyEval_RestoreThread
    __GI___pthread_exit
    _Unwind_ForcedUnwind                        <- cannot cross a C++ frame
    std::terminate() -> abort()

`stats/aggregate.py` keeps one connection per thread in a `threading.local()`,
deliberately never closed ("kept for the life of it"), and nothing registers an
`atexit`. Harmless in a server that never exits, and invisible to this suite —
these tests drive the engine on the MAIN thread and exit 0. It bites anything
batch-shaped: a worker that renders its share and exits is reported as crashed
whatever its assertions said, and leaves a core dump behind.

The engine has to run on a request thread for this to reproduce: a connection
on a joined worker thread, or on a live daemon thread, both exit 0. So this
drives the real app through TestClient.

`build_pptx` is deliberately NOT stubbed. The engine runs inside the chart
build, not in `df_model_for_material` (which only reads the SAV and applies the
grouping override), so a test that stubs the build makes no DuckDB connection
at all and passes whether or not the defect exists. Only the two steps AFTER
the build are stubbed, which is what keeps LibreOffice out of it.
(Johan, 2026-09-12)
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

_RENDER_THEN_EXIT = textwrap.dedent("""
    import sys
    sys.path.insert(0, "tests")
    from unittest.mock import patch

    import matplotlib
    matplotlib.use("Agg")

    from fastapi.testclient import TestClient
    from reportbuilder.api.app import create_app
    from reportbuilder.api.deps_auth import current_user
    from reportbuilder.api.deps_store import get_auth, get_repository
    from reportbuilder.store.memory_objects import InMemoryObjectStore
    from reportbuilder.store.repository import Repository
    from reportbuilder.store.seam import AuthContext
    from reportbuilder.testing.fixtures import synthetic_sav_bytes
    from suite._helpers import sign_in_override

    stub_png = sys.argv[1]
    RQ = "reportbuilder.api.routes_questions"

    app = create_app()
    repo = Repository(InMemoryObjectStore())
    auth = AuthContext(token="t")
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth)
    c = TestClient(app)

    cu = c.post("/customers", json={"name": "K"}).json()["id"]
    ca = c.post(f"/customers/{cu}/cases", json={"name": "T"}).json()["id"]
    mid = c.post(
        f"/cases/{ca}/materials",
        files={"file": ("s.sav", synthetic_sav_bytes(), "application/octet-stream")},
    ).json()["material_id"]
    qid = c.get(f"/materials/{mid}/questions").json()["questions"][0]["qid"]

    spec = {
        "question_ref": qid,
        "chart_type": "vertical_bar",
        "statistic": "pct",
        "classifying_var": None,
        "number_format": {"mode": "auto"},
        "sort": {"basis": "data_order", "descending": True},
        "template_slot": "s1",
        "elements": {},
    }
    # build_pptx runs for real: it is where the stats engine (and so duckdb) is
    # reached. Only the LibreOffice steps after it are stubbed.
    with patch(f"{RQ}.shutil.which", return_value="soffice"), \\
         patch(f"{RQ}.pptx_to_pdf", return_value="ignored.pdf"), \\
         patch(f"{RQ}.rasterize_pages", return_value=[stub_png]):
        r = c.post(f"/materials/{mid}/preview-chart", json=spec)

    print("STATUS", r.status_code, flush=True)
    assert r.status_code == 200, r.text
    print("REACHED END OF SCRIPT", flush=True)
""")


def test_a_process_that_rendered_a_preview_exits_cleanly(tmp_path):
    """Exit code, read directly. Through a pipe it would be the pipe's status,
    which is how this stayed invisible: the work succeeds, then the abort."""
    stub = tmp_path / "page-1.png"
    stub.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

    proc = subprocess.run(
        [sys.executable, "-c", _RENDER_THEN_EXIT, str(stub)],
        capture_output=True, text=True, timeout=300,
    )

    assert "REACHED END OF SCRIPT" in proc.stdout, (
        f"the script did not finish its work, so the exit code says nothing "
        f"about teardown:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    assert proc.returncode == 0, (
        f"a process that rendered a preview aborted at exit "
        f"(returncode {proc.returncode}); a batch worker doing this is reported "
        f"as crashed whatever its assertions said\n{proc.stderr[-2000:]}")
