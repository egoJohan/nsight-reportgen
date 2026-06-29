"""In-memory DataHiveClient — a self-contained store for local demos / offline runs.

Implements the same 8-method surface as DataHiveClient, holding cases, materials
(byte-exact .sav), and reports (verbatim JSON) in memory. Lets the whole nSight API
run end-to-end WITHOUT a live datahive or a token (NSIGHT_DEMO=1 in server.py).

Optional durability: pass ``storage_dir`` to make the store persist to disk so cases,
materials, and reports survive process restarts. When ``storage_dir`` is None the client
is purely in-memory (and behaves exactly as the original demo store). When a dir is
given, state is loaded on construction and re-saved atomically after every mutation.

Layout under ``storage_dir``:
  - ``cases.json``         — map of case_id -> case dict
  - ``material_meta.json`` — map of material_id -> metadata dict
  - ``reports.json``       — map of report_id -> verbatim report JSON string
  - ``state.json``         — scalars (the id counter ``_n``)
  - ``materials/<id>.sav`` — raw material bytes (kept out of JSON)

Not for production — even with disk persistence this is a single-process demo store.
"""
from __future__ import annotations

import json
import os


class InMemoryDataHiveClient:
    def __init__(self, base_url=None, token=None, storage_dir: str | None = None, **_kw):
        # signature-compatible with DataHiveClient (extra storage_dir is opt-in)
        self.base_url = base_url
        self.token = token
        self.storage_dir = storage_dir
        self._cases: dict[str, dict] = {}
        self._materials: dict[str, bytes] = {}
        self._material_meta: dict[str, dict] = {}
        self._reports: dict[str, str] = {}
        self._n = 0
        if self.storage_dir is not None:
            self._load()

    # --- persistence helpers ---
    def _materials_dir(self) -> str:
        return os.path.join(self.storage_dir, "materials")

    def _atomic_write(self, path: str, data: bytes) -> None:
        """Write bytes to path atomically (temp file in same dir, then os.replace)."""
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _atomic_write_json(self, path: str, obj) -> None:
        self._atomic_write(path, json.dumps(obj).encode("utf-8"))

    @staticmethod
    def _read_json(path: str, default):
        """Read JSON, tolerating missing/empty/corrupt files (-> default)."""
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except (OSError, FileNotFoundError):
            return default
        if not raw.strip():
            return default
        try:
            return json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            return default

    def _load(self) -> None:
        """Restore state from storage_dir; tolerate anything missing/corrupt."""
        d = self.storage_dir
        cases = self._read_json(os.path.join(d, "cases.json"), {})
        meta = self._read_json(os.path.join(d, "material_meta.json"), {})
        reports = self._read_json(os.path.join(d, "reports.json"), {})
        state = self._read_json(os.path.join(d, "state.json"), {})
        self._cases = cases if isinstance(cases, dict) else {}
        self._material_meta = meta if isinstance(meta, dict) else {}
        self._reports = reports if isinstance(reports, dict) else {}
        n = state.get("_n", 0) if isinstance(state, dict) else 0
        self._n = n if isinstance(n, int) and n >= 0 else 0
        # Material bytes are loaded lazily from disk in get_material; nothing to do here.

    def _save(self) -> None:
        if self.storage_dir is None:
            return
        d = self.storage_dir
        os.makedirs(d, exist_ok=True)
        self._atomic_write_json(os.path.join(d, "cases.json"), self._cases)
        self._atomic_write_json(os.path.join(d, "material_meta.json"), self._material_meta)
        self._atomic_write_json(os.path.join(d, "reports.json"), self._reports)
        self._atomic_write_json(os.path.join(d, "state.json"), {"_n": self._n})

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    # --- cases ---
    def create_case(self, name: str) -> str:
        cid = self._id("case-")
        self._cases[cid] = {"id": cid, "name": name}
        self._save()
        return cid

    def list_cases(self) -> list[dict]:
        return list(self._cases.values())

    def rename_case(self, case_id: str, name: str) -> None:
        c = self._cases.get(case_id)
        if c is None:
            raise KeyError(case_id)
        c["name"] = name
        self._save()

    def delete_case(self, case_id: str) -> None:
        if case_id not in self._cases:
            raise KeyError(case_id)
        del self._cases[case_id]
        # Cascade: drop this case's materials (reports are tracked client-side).
        mids = [m for m, meta in self._material_meta.items()
                if meta.get("case_id") == case_id]
        for mid in mids:
            self._materials.pop(mid, None)
            self._material_meta.pop(mid, None)
            if self.storage_dir is not None:
                try:
                    os.remove(os.path.join(self._materials_dir(), f"{mid}.sav"))
                except OSError:
                    pass
        self._save()

    # --- materials (byte-exact) ---
    def attach_material(self, case_id: str, name: str, sav_bytes: bytes,
                        codebook_summary: str) -> str:
        mid = self._id("mat-")
        data = bytes(sav_bytes)
        self._materials[mid] = data
        self._material_meta[mid] = {"case_id": case_id, "name": name}
        if self.storage_dir is not None:
            self._atomic_write(os.path.join(self._materials_dir(), f"{mid}.sav"), data)
        self._save()
        return mid

    def get_material(self, material_id: str) -> bytes:
        if material_id in self._materials:
            return self._materials[material_id]
        if self.storage_dir is not None:
            path = os.path.join(self._materials_dir(), f"{material_id}.sav")
            with open(path, "rb") as f:
                data = f.read()
            self._materials[material_id] = data
            return data
        raise KeyError(material_id)

    # --- reports (verbatim JSON round-trip) ---
    def save_report(self, case_id: str, report_id: str | None, report_json: str,
                    readable: str) -> str:
        rid = report_id or self._id("rep-")
        self._reports[rid] = report_json
        self._save()
        return rid

    def load_report(self, case_id: str, report_doc_id: str) -> str:
        return self._reports[report_doc_id]

    def delete_report(self, case_id: str, report_doc_id: str) -> None:
        self._reports.pop(report_doc_id, None)
        self._save()

    # --- aggregation (demo stub) ---
    def aggregate(self, material_id: str, group_by: list[str], filters: dict,
                  weight: str | None = None) -> dict:
        return {"dimensions": list(group_by), "cells": [], "total": 0}
