"""What the author sees when a .sav will not parse.

A file nSight Studio cannot read is the AUTHOR'S problem to act on — wrong file,
corrupt export — and it must say so where they are standing. It was raising out
of the route as a 500, and the web app treats any 500 as a service outage and
covers the screen with the internal-error page: the upload appeared to break the
whole product, named neither the file nor the reason, and offered only "retry",
which would fail identically every time.
"""
from __future__ import annotations


def _case(client) -> str:
    cust = client.post("/customers", json={"name": "Alpha"}).json()["id"]
    return client.post(f"/customers/{cust}/cases", json={"name": "Alpha"}).json()["id"]


def test_unreadable_file_is_rejected_not_a_server_error(client_memory):
    cid = _case(client_memory)

    resp = client_memory.post(
        f"/cases/{cid}/materials",
        files={"file": ("notes.sav", b"this is not an SPSS file at all",
                        "application/octet-stream")},
    )

    # 4xx: the request was bad, not the server. Anything >= 500 raises the
    # outage screen over the whole app.
    assert resp.status_code == 422, resp.text
    assert "notes.sav" in resp.json()["detail"]


def test_a_readable_file_still_uploads(client_memory, synthetic_bytes):
    cid = _case(client_memory)

    resp = client_memory.post(
        f"/cases/{cid}/materials",
        files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["question_count"] > 0
