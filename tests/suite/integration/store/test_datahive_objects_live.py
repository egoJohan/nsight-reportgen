"""The seam, exercised against a REAL datahive.

Skipped unless NSIGHT_DEV_HIVE_CREDS points at a creds file, so CI without a
hive still runs. This is the test that would have caught the original defect:
`datahive_client.py` was written against an assumed contract and only ever
tested through httpx.MockTransport, so five of its fourteen operations were
broken against a live instance and nobody knew.
"""
import json
import os
import pathlib
import uuid

import pytest

from reportbuilder.store import paths as P
from reportbuilder.store.datahive_objects import DataHiveObjectStore
from reportbuilder.store.seam import AuthContext, ConsentRequired, NotFound

CREDS = os.environ.get("NSIGHT_DEV_HIVE_CREDS", "work/datahive_creds.json")
pytestmark = pytest.mark.integration


def _creds():
    p = pathlib.Path(CREDS)
    if not p.exists():
        pytest.skip(f"no dev-hive creds at {CREDS}")
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def store():
    return DataHiveObjectStore(_creds()["base_url"])


@pytest.fixture(scope="module")
def auth():
    return AuthContext(token=_creds()["bearer"])


@pytest.fixture
def asiakas():
    """A throwaway customer subtree so a failed run cannot collide with a
    previous one, and cleanup is a single prefix."""
    return f"itest-{uuid.uuid4().hex[:8]}"


def _cleanup(store, auth, prefix):
    """Remove everything under *prefix*, approving consent via the CLI."""
    import subprocess
    d = "/home/johan/Projects/egoiq/egohive/egohive-datahive"
    sd = os.path.expanduser("~/.local/share/datahive/nsight-dev")
    for info in store.list(auth, path_prefix=prefix):
        try:
            store.delete(auth, info.path)
        except ConsentRequired as exc:
            subprocess.run(
                [f"{d}/.venv/bin/datahive", "consent", "approve", exc.request_id,
                 "--config", f"{sd}/datahive.yaml", "--state-dir", sd],
                capture_output=True)
            store.delete(auth, info.path)


class TestRoundTrip:
    def test_binary_material_survives_byte_exact(self, store, auth, asiakas):
        """A .sav is re-parsed on every case open, so a single altered byte is
        a corrupted dataset. Payload covers NULs, 0xFF, CRLF and every byte."""
        path = P.material_path(asiakas, "case-1", "mat-1")
        payload = bytes([0, 255, 254, 26]) + b"\r\n$FL2@(#) SPSS\x00" + bytes(range(256))
        try:
            store.put(auth, path, payload, "application/octet-stream",
                      labels=[P.LABEL_MATERIAL])
            assert store.get(auth, path) == payload
        finally:
            _cleanup(store, auth, P.customer_prefix(asiakas))

    def test_report_json_survives_byte_exact(self, store, auth, asiakas):
        """report_from_json(report_to_json(r)) == r is a serde invariant; a
        store that reorders keys or renormalises numbers breaks report load."""
        path = P.report_path(asiakas, "case-1", "rep-1")
        payload = json.dumps({"z": 1, "a": {"n": [1.0, 2.50]}, "m": "ää€"},
                             ensure_ascii=False).encode()
        try:
            store.put(auth, path, payload, "application/json", labels=[P.LABEL_REPORT])
            assert store.get(auth, path) == payload
        finally:
            _cleanup(store, auth, P.customer_prefix(asiakas))


class TestListing:
    def test_prefix_scopes_to_a_case_and_label_selects_a_type(self, store, auth, asiakas):
        try:
            store.put(auth, P.report_path(asiakas, "case-1", "r1"), b"{}",
                      "application/json", labels=[P.LABEL_REPORT])
            store.put(auth, P.material_path(asiakas, "case-1", "m1"), b"x",
                      "application/octet-stream", labels=[P.LABEL_MATERIAL])
            store.put(auth, P.report_path(asiakas, "case-2", "r2"), b"{}",
                      "application/json", labels=[P.LABEL_REPORT])

            case1 = {o.path for o in store.list(auth, P.case_prefix(asiakas, "case-1"))}
            assert case1 == {P.report_path(asiakas, "case-1", "r1"),
                             P.material_path(asiakas, "case-1", "m1")}

            reports = {o.path for o in store.list(auth, P.customer_prefix(asiakas),
                                                  labels=[P.LABEL_REPORT])}
            assert reports == {P.report_path(asiakas, "case-1", "r1"),
                               P.report_path(asiakas, "case-2", "r2")}
        finally:
            _cleanup(store, auth, P.customer_prefix(asiakas))

    def test_labels_are_hierarchical(self, store, auth, asiakas):
        """Writing nsight:report stores nsight too, so ?label=nsight finds
        everything we own regardless of type."""
        try:
            store.put(auth, P.report_path(asiakas, "case-1", "r1"), b"{}",
                      "application/json", labels=[P.LABEL_REPORT])
            [info] = store.list(auth, P.customer_prefix(asiakas), labels=[P.LABEL_ROOT])
            assert set(info.labels) >= {P.LABEL_ROOT, P.LABEL_REPORT}
        finally:
            _cleanup(store, auth, P.customer_prefix(asiakas))


class TestMissing:
    def test_absent_path_raises_not_found(self, store, auth, asiakas):
        with pytest.raises(NotFound):
            store.get(auth, P.report_path(asiakas, "nope", "nope"))


class TestDelete:
    def test_delete_asks_for_consent_and_succeeds_once_granted(self, store, auth, asiakas):
        """datahive gates destructive ops (floor rule 4). The seam must surface
        the envelope rather than swallow it — the caller drives approval."""
        import subprocess
        path = P.report_path(asiakas, "case-1", "doomed")
        store.put(auth, path, b"{}", "application/json", labels=[P.LABEL_REPORT])
        with pytest.raises(ConsentRequired) as caught:
            store.delete(auth, path)
        exc = caught.value
        assert exc.request_id and exc.action == "object.delete"
        assert exc.envelope.get("approval_urls")

        d = "/home/johan/Projects/egoiq/egohive/egohive-datahive"
        sd = os.path.expanduser("~/.local/share/datahive/nsight-dev")
        subprocess.run([f"{d}/.venv/bin/datahive", "consent", "approve", exc.request_id,
                        "--config", f"{sd}/datahive.yaml", "--state-dir", sd],
                       capture_output=True, check=True)
        store.delete(auth, path)
        with pytest.raises(NotFound):
            store.get(auth, path)
