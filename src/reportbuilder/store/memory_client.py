"""In-memory DataHiveClient — a self-contained store for local demos / offline runs.

Implements the same 8-method surface as DataHiveClient, holding cases, materials
(byte-exact .sav), and reports (verbatim JSON) in memory. Lets the whole nSight API
run end-to-end WITHOUT a live datahive or a token (NSIGHT_DEMO=1 in server.py).
Not for production — state is process-local and lost on restart.
"""
from __future__ import annotations


class InMemoryDataHiveClient:
    def __init__(self, base_url=None, token=None, **_kw):  # signature-compatible with DataHiveClient
        self.base_url = base_url
        self.token = token
        self._cases: dict[str, dict] = {}
        self._materials: dict[str, bytes] = {}
        self._material_meta: dict[str, dict] = {}
        self._reports: dict[str, str] = {}
        self._n = 0

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    # --- cases ---
    def create_case(self, name: str) -> str:
        cid = self._id("case-")
        self._cases[cid] = {"id": cid, "name": name}
        return cid

    def list_cases(self) -> list[dict]:
        return list(self._cases.values())

    # --- materials (byte-exact) ---
    def attach_material(self, case_id: str, name: str, sav_bytes: bytes,
                        codebook_summary: str) -> str:
        mid = self._id("mat-")
        self._materials[mid] = bytes(sav_bytes)
        self._material_meta[mid] = {"case_id": case_id, "name": name}
        return mid

    def get_material(self, material_id: str) -> bytes:
        return self._materials[material_id]

    # --- reports (verbatim JSON round-trip) ---
    def save_report(self, case_id: str, report_id: str | None, report_json: str,
                    readable: str) -> str:
        rid = report_id or self._id("rep-")
        self._reports[rid] = report_json
        return rid

    def load_report(self, case_id: str, report_doc_id: str) -> str:
        return self._reports[report_doc_id]

    def delete_report(self, case_id: str, report_doc_id: str) -> None:
        self._reports.pop(report_doc_id, None)

    # --- aggregation (demo stub) ---
    def aggregate(self, material_id: str, group_by: list[str], filters: dict,
                  weight: str | None = None) -> dict:
        return {"dimensions": list(group_by), "cells": [], "total": 0}
