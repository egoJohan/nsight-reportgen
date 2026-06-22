"""DataHive REST client (D1/D2/D3) — the system-of-record contract the nSight backend
depends on. The real REST implementation is a separate datahive-integration effort; this
module defines the interface (methods raise NotImplementedError), and API route tests mock it."""
from __future__ import annotations


class DataHiveClient:
    """Client for datahive's projects app (Case/Material/Report) + aggregation primitive."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = base_url
        self.token = token

    def create_case(self, name: str) -> str:
        """Create a Case (datahive project); return the case/project id. (REQ-C-03/07)"""
        raise NotImplementedError

    def list_cases(self) -> list[dict]:
        """List cases (projects). (REQ-C-07)"""
        raise NotImplementedError

    def attach_material(self, case_id: str, name: str, sav_bytes: bytes,
                        codebook_summary: str) -> str:
        """Attach a SAV material doc under a case; return the material doc id. (REQ-C-04)"""
        raise NotImplementedError

    def save_report(self, case_id: str, report_id: str | None, report_json: str,
                    readable: str) -> str:
        """Save (create or versioned-replace) a report doc; return its id. (REQ-C-08, D3)"""
        raise NotImplementedError

    def load_report(self, report_doc_id: str) -> str:
        """Return the exact report-definition JSON for a report doc. (REQ-C-08)"""
        raise NotImplementedError

    def aggregate(self, material_id: str, group_by: list[str], filters: dict,
                  weight: str | None = None) -> dict:
        """Generic filtered GROUP BY / cross-tab cell counts over a tabular material. (D1)"""
        raise NotImplementedError
