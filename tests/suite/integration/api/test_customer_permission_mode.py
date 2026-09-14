"""Switching a customer between inheriting the domain policy and managing its own.

The Domains screen answers one question for the whole tenant. This is the other
half: the customer whose data only a named few may see, without unpicking the
domain grant everyone else relies on.

Admin-gated on purpose. Deciding who may reach a customer is administering
access, not working inside it — and gating it on the write right would let
anyone the domain currently admits switch a manual customer back to inherit and
re-admit themselves, which is the one thing the setting exists to prevent.
(Johan, 2026-09-14)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _customer(client, name="Attendo"):
    return client.post("/customers", json={"name": name}).json()["id"]


def test_a_customer_inherits_until_somebody_says_otherwise(client_memory):
    cid = _customer(client_memory)
    assert client_memory.get(f"/customers/{cid}").json()["permission_mode"] == "inherit"


def test_the_mode_can_be_switched_and_reads_back(client_memory):
    cid = _customer(client_memory)
    out = client_memory.put(f"/customers/{cid}/permission-mode", json={"mode": "manual"})
    assert out.status_code == 200, out.text
    assert out.json()["permission_mode"] == "manual"
    assert client_memory.get(f"/customers/{cid}").json()["permission_mode"] == "manual"


def test_it_rides_along_on_the_listing(client_memory):
    """The customer page shows it per row, so it must not cost a second fetch."""
    cid = _customer(client_memory)
    client_memory.put(f"/customers/{cid}/permission-mode", json={"mode": "manual"})
    rows = client_memory.get("/customers").json()
    row = next(r for r in rows if r["id"] == cid)
    assert row["permission_mode"] == "manual"


def test_switching_back_to_inherit_is_recorded(client_memory):
    """Stored rather than dropped: a customer deliberately returned to the
    domain policy reads differently from one nobody has decided about."""
    cid = _customer(client_memory)
    client_memory.put(f"/customers/{cid}/permission-mode", json={"mode": "manual"})
    client_memory.put(f"/customers/{cid}/permission-mode", json={"mode": "inherit"})
    assert client_memory.get(f"/customers/{cid}").json()["permission_mode"] == "inherit"


def test_an_unknown_mode_is_refused(client_memory):
    cid = _customer(client_memory)
    assert client_memory.put(f"/customers/{cid}/permission-mode",
                             json={"mode": "whatever"}).status_code == 422


def test_an_unknown_customer_is_404(client_memory):
    assert client_memory.put("/customers/cust-nope/permission-mode",
                             json={"mode": "manual"}).status_code == 404


def test_going_manual_leaves_the_owner_able_to_work(client_memory):
    """The owner created it; withdrawing the domain grant must not lock them
    out of their own customer."""
    cid = _customer(client_memory)
    client_memory.put(f"/customers/{cid}/permission-mode", json={"mode": "manual"})

    got = client_memory.get(f"/customers/{cid}")
    assert got.status_code == 200, got.text
    assert got.json()["can_edit"] is True, "the owner lost their own customer"


def test_the_owner_can_still_make_a_study_in_it(client_memory):
    """`can_edit` is a claim; this is the write it claims to allow."""
    cid = _customer(client_memory)
    client_memory.put(f"/customers/{cid}/permission-mode", json={"mode": "manual"})

    made = client_memory.post(f"/customers/{cid}/cases", json={"name": "Tutkimus"})
    assert made.status_code in (200, 201), made.text
