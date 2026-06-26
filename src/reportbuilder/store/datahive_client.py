"""DataHive REST client (D1/D2/D3) — the system-of-record contract the nSight backend
depends on.

Slice 1 (this implementation): projects, report opaque-doc round-trip, aggregate.
Slice 2 (later): attach_material / get_material via /ingest/sav — datahive serves
  data in-process from cache, so there is no byte-download endpoint by design.

Auth: Authorization: Bearer <token>.  The tenant is derived from the token server-side.
Base path: /api/v1.
"""
from __future__ import annotations

import uuid

import httpx


class DataHiveClient:
    """Client for datahive's projects app (Case/Material/Report) + aggregation primitive."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        tenant: str | None = None,
        template_ref: str = "wftemplate:dataset-report-study",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url
        self.token = token
        self.tenant = tenant
        self.template_ref = template_ref

        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self._client = httpx.Client(
            base_url=base_url or "",
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    # ------------------------------------------------------------------
    # Context-manager / lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

    def __enter__(self) -> "DataHiveClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.is_error:
            snippet = resp.text[:200]
            raise RuntimeError(
                f"DataHive error {resp.status_code} {resp.request.method} "
                f"{resp.request.url}: {snippet!r}"
            )

    # ------------------------------------------------------------------
    # Projects / Cases  (REQ-C-03/07)
    # ------------------------------------------------------------------

    def create_case(self, name: str) -> str:
        """Create a Case (datahive project); return the case/project id. (REQ-C-03/07)"""
        resp = self._client.post(
            "/api/v1/projects",
            json={"name": name, "template_ref": self.template_ref},
        )
        self._raise_for_status(resp)
        data = resp.json()
        # The datahive API returns either "id" or "project_id"; handle both.
        return data.get("id") or data["project_id"]

    def list_cases(self) -> list[dict]:
        """List cases (projects). (REQ-C-07)"""
        resp = self._client.get("/api/v1/projects")
        self._raise_for_status(resp)
        return resp.json()["projects"]

    # ------------------------------------------------------------------
    # Report docs  (REQ-C-08/12)
    # ------------------------------------------------------------------

    def save_report(
        self,
        case_id: str,
        report_id: str | None,
        report_json: str,
        readable: str,
    ) -> str:
        """Save (create or versioned-replace) a report doc; return its id. (REQ-C-08, D3)"""
        ref_id = report_id if report_id is not None else f"report-{uuid.uuid4().hex}"
        name = (readable[:120] if readable else None) or "report"
        body = {
            "label": "report",
            "name": name,
            "reference_id": ref_id,
            "text": report_json,
        }
        resp = self._client.post(f"/api/v1/projects/{case_id}/docs", json=body)
        self._raise_for_status(resp)
        return resp.json()["reference_id"]

    def load_report(self, case_id: str, report_doc_id: str) -> str:
        """Return the exact report-definition JSON for a report doc. (REQ-C-08)

        GET /api/v1/projects/{case_id}/docs/{report_doc_id} → {"text": <json>}.
        """
        resp = self._client.get(f"/api/v1/projects/{case_id}/docs/{report_doc_id}")
        self._raise_for_status(resp)
        return resp.json()["text"]

    def delete_report(self, case_id: str, report_doc_id: str) -> None:
        """Delete a report doc. (REQ-C-12)

        DELETE /api/v1/projects/{case_id}/docs/{report_doc_id} → 2xx.
        """
        resp = self._client.delete(f"/api/v1/projects/{case_id}/docs/{report_doc_id}")
        self._raise_for_status(resp)

    # ------------------------------------------------------------------
    # Aggregation  (D1)
    # ------------------------------------------------------------------

    def aggregate(
        self,
        material_id: str,
        group_by: list[str],
        filters: list[dict] | dict | None = None,
        weight: str | None = None,
    ) -> dict:
        """Generic filtered GROUP BY / cross-tab cell counts over a tabular material. (D1)

        `weight` is accepted for signature compatibility but not forwarded —
        datahive aggregate is counts-only.
        """
        if isinstance(filters, dict):
            # Normalise legacy callers that passed a single dict
            filters_list: list[dict] = [filters] if filters else []
        else:
            filters_list = filters or []

        resp = self._client.post(
            f"/api/v1/aggregation/{material_id}",
            json={"group_columns": group_by, "filters": filters_list},
        )
        self._raise_for_status(resp)
        return resp.json()

    # ------------------------------------------------------------------
    # Materials — Slice 2
    # ------------------------------------------------------------------

    def attach_material(
        self,
        case_id: str,
        name: str,
        sav_bytes: bytes,
        codebook_summary: str,
    ) -> str:
        """Attach a SAV material doc under a case; return the material doc id. (REQ-C-04)

        Slice 2: materials via /ingest/sav; nSight serves data in-process from cache
        — datahive has no byte-download by design.
        """
        raise NotImplementedError(
            "Slice 2: materials via /ingest/sav; nSight serves data in-process from cache"
            " — datahive has no byte-download by design."
        )

    def get_material(self, material_id: str) -> bytes:
        """Return the raw stored bytes of a material doc (e.g. the .sav). (REQ-C-05)

        Slice 2: materials via /ingest/sav; nSight serves data in-process from cache
        — datahive has no byte-download by design.
        """
        raise NotImplementedError(
            "Slice 2: materials via /ingest/sav; nSight serves data in-process from cache"
            " — datahive has no byte-download by design."
        )
