"""The app, wired the way the acceptance suite drives it.

In-process, over an in-memory object store — the same shape
`tests/suite/conftest.py::client_memory` uses, reimplemented here rather than
imported so this suite does not depend on the other one. The sign-in override
is a dozen lines of product API; sharing it would couple two suites that are
meant to be separable.

Studies and templates are named, not paths: a case record says `"study":
"synthetic"`, and what that resolves to is this module's problem. Phase 3
replaces the registry below with the real corpus without touching a case
record or the runner.
"""
from __future__ import annotations

import contextlib
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parent.parent
# pytest supplies `src` from pyproject; a subprocess gets nothing, and relying
# on an editable install would work here and fail in the acceptance image.
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))


def _sign_in(repo, auth, *, admin: bool = True):
    """A `current_user` override granting every customer currently in *repo*.

    Recomputed on every call, so a customer created mid-run is visible on the
    next request without re-registering the override.
    """
    from reportbuilder.auth.permissions import Grant, User

    def _override():
        return User(id="acceptance", email="acceptance@localhost",
                    name="Acceptance", is_admin=admin,
                    grants=tuple(Grant(c.id, "edit")
                                 for c in repo.list_customers(auth)))
    return _override


def build_client():
    """A TestClient over the real app and an in-memory store."""
    from fastapi.testclient import TestClient

    from reportbuilder.api.app import create_app
    from reportbuilder.api.deps_auth import current_user
    from reportbuilder.api.deps_store import get_auth, get_repository
    from reportbuilder.store.memory_objects import InMemoryObjectStore
    from reportbuilder.store.repository import Repository
    from reportbuilder.store.seam import AuthContext

    app = create_app()
    repo = Repository(InMemoryObjectStore())
    auth = AuthContext(token="acceptance")
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = _sign_in(repo, auth)
    return TestClient(app)


def study_bytes(name: str) -> bytes:
    """The .sav a case names. Phase 3 adds the anonymised corpus here."""
    if name == "synthetic":
        from reportbuilder.testing.fixtures import synthetic_sav_bytes
        return synthetic_sav_bytes()
    raise KeyError(f"unknown study {name!r}")


def template_bytes(name: str) -> bytes:
    """The .pptx a case names. Phase 3 adds the generated templates here."""
    if name == "default":
        from reportbuilder.render.default_template import default_template_bytes
        return default_template_bytes()
    raise KeyError(f"unknown template {name!r}")


_PPTX = ("application/vnd.openxmlformats-officedocument"
         ".presentationml.presentation")


def render_case(case: dict, out_dir: pathlib.Path) -> dict:
    """Render one case's preview. Returns what happened, raises nothing routine.

    `render_title=False` is not optional: the composited fast path is gated on
    it (`routes_questions.py`), so a case sent without it silently takes
    LibreOffice — a different rasteriser, 10-20x slower, and not the picture
    the gate means to judge.
    """
    client = build_client()
    cid = client.post("/customers", json={"name": "Acceptance"}).json()["id"]
    kid = client.post(f"/customers/{cid}/cases",
                      json={"name": case["id"]}).json()["id"]
    mid = client.post(
        f"/cases/{kid}/materials",
        files={"file": ("study.sav", study_bytes(case["study"]),
                        "application/octet-stream")},
    ).json()["material_id"]
    up = client.post(
        f"/customers/{cid}/templates",
        files={"file": ("template.pptx", template_bytes(case["template"]), _PPTX)},
    )
    if up.status_code != 201:
        raise RuntimeError(f"template upload failed: {up.status_code} {up.text[:300]}")
    tid = up.json()["id"]

    spec = dict(case["spec"])
    if not spec.get("question_ref"):
        # Phase-4 records name their question; a hand-written one need not.
        qs = client.get(f"/materials/{mid}/questions").json()["questions"]
        if not qs:
            raise RuntimeError(f"study {case['study']!r} has no questions to chart")
        spec["question_ref"] = qs[0]["qid"]
    spec.update(render_title=False, template_id=tid)

    overlaps, judge_errors, undersized = [], [], []
    with _judging(overlaps, judge_errors, undersized):
        r = client.post(f"/materials/{mid}/preview-chart", json=spec)
    if r.status_code != 200:
        raise RuntimeError(f"preview failed: {r.status_code} {r.text[:300]}")

    out_dir.mkdir(parents=True, exist_ok=True)
    picture = out_dir / f"{case['id']}.png"
    picture.write_bytes(r.content)
    return {
        "picture": picture,
        "drawn_by": r.headers.get("X-Preview-Path", "unknown"),
        "bytes": len(r.content),
        "question_ref": spec["question_ref"],
        "overlaps": overlaps,
        "undersized": undersized,
        "judge_errors": judge_errors,
    }


@contextlib.contextmanager
def _judging(overlaps: list, errors: list, undersized: list | None = None):
    """Judge each figure while its artists are still alive.

    The only window is `Figure.savefig`: `render_png` clears the figure right
    after saving and the PNG is unlinked once python-pptx has embedded it, so
    by the time a preview comes back there is nothing left to measure. The
    existing regression tests use this same seam, which is why no product hook
    is needed.

    One preview can save several figures (a demographics grid draws one per
    cell), so findings accumulate.
    """
    from matplotlib.figure import Figure

    import oracles.legibility as legibility
    import oracles.overlap as overlap

    original = Figure.savefig

    def spy(self, *args, **kwargs):
        try:
            # Text metrics need a renderer; label_fit may have moved things
            # since the last draw.
            self.canvas.draw()
            overlaps.extend(overlap.collisions(self))
            if undersized is not None:
                # Both floors, from the same census. A tick label below 5pt is
                # caught by both rules, so the same artist is not listed twice
                # in the one output a human reads first.
                seen = {(u.text, u.points) for u in undersized}
                for hit in (legibility.too_small(self)
                            + legibility.names_too_small(self)):
                    if (hit.text, hit.points) not in seen:
                        seen.add((hit.text, hit.points))
                        undersized.append(hit)
        except Exception as exc:  # noqa: BLE001 — a rule that throws must be
            errors.append(f"{type(exc).__name__}: {exc}")   # seen, not fatal
        return original(self, *args, **kwargs)

    Figure.savefig = spy
    try:
        yield
    finally:
        Figure.savefig = original


def load_case(index: pathlib.Path, case_id: str) -> dict:
    """The one record named, from a `*.jsonl` index."""
    import json

    for line in index.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if record.get("id") == case_id:
            return record
    raise KeyError(case_id)
