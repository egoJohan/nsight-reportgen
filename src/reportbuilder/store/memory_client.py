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

Thread-safe within one process (a single re-entrant lock guards all state), but
still SINGLE-PROCESS: running multiple workers would give each its own in-memory
copy and clobber the shared files. Not for production — back the API with a real
transactional store / DB for multi-worker, multi-tenant use.
"""
from __future__ import annotations

import json
import os
import threading


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
        # report_id -> {"case_id", "name"} so reports can be listed per case
        # (the verbatim JSON stays in _reports). Legacy reports without an entry
        # here remain loadable by id but aren't listed per case.
        self._report_meta: dict[str, dict] = {}
        self._n = 0
        # FastAPI runs sync routes on a threadpool → these methods are called from
        # multiple threads in parallel. A single re-entrant lock makes every
        # read-modify-write (and the multi-file _save) atomic: no torn IDs, no
        # "dict changed size during iteration", no interleaved persistence.
        self._lock = threading.RLock()
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
        report_meta = self._read_json(os.path.join(d, "report_meta.json"), {})
        state = self._read_json(os.path.join(d, "state.json"), {})
        self._cases = cases if isinstance(cases, dict) else {}
        self._material_meta = meta if isinstance(meta, dict) else {}
        self._reports = reports if isinstance(reports, dict) else {}
        self._report_meta = report_meta if isinstance(report_meta, dict) else {}
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
        self._atomic_write_json(os.path.join(d, "report_meta.json"), self._report_meta)
        self._atomic_write_json(os.path.join(d, "state.json"), {"_n": self._n})

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    # --- cases ---
    def create_case(self, name: str) -> str:
        with self._lock:
            cid = self._id("case-")
            self._cases[cid] = {"id": cid, "name": name}
            self._save()
            return cid

    def list_cases(self) -> list[dict]:
        with self._lock:
            return [dict(c) for c in self._cases.values()]

    def rename_case(self, case_id: str, name: str) -> None:
        with self._lock:
            c = self._cases.get(case_id)
            if c is None:
                raise KeyError(case_id)
            c["name"] = name
            self._save()

    def delete_case(self, case_id: str) -> None:
        with self._lock:
            if case_id not in self._cases:
                raise KeyError(case_id)
            del self._cases[case_id]
            # Cascade: drop this case's materials AND reports.
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
            rids = [r for r, meta in self._report_meta.items()
                    if meta.get("case_id") == case_id]
            for rid in rids:
                self._reports.pop(rid, None)
                self._report_meta.pop(rid, None)
            self._save()

    # --- materials (byte-exact) ---
    def attach_material(self, case_id: str, name: str, sav_bytes: bytes,
                        codebook_summary: str) -> str:
        with self._lock:
            mid = self._id("mat-")
            data = bytes(sav_bytes)
            self._materials[mid] = data
            self._material_meta[mid] = {"case_id": case_id, "name": name}
            if self.storage_dir is not None:
                self._atomic_write(os.path.join(self._materials_dir(), f"{mid}.sav"), data)
            self._save()
            return mid

    def list_materials(self, case_id: str) -> list[dict]:
        """List a case's materials (newest first) — {material_id, name}."""
        with self._lock:
            out = [{"material_id": mid, "name": meta.get("name", mid)}
                   for mid, meta in self._material_meta.items()
                   if meta.get("case_id") == case_id]
            out.reverse()
            return out

    def get_material(self, material_id: str) -> bytes:
        with self._lock:
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
        with self._lock:
            rid = report_id or self._id("rep-")
            self._reports[rid] = report_json
            # Prefer the report's own display name; fall back to the readable summary.
            try:
                name = json.loads(report_json).get("name") or readable or "report"
            except (ValueError, TypeError):
                name = readable or "report"
            self._report_meta[rid] = {"case_id": case_id, "name": name}
            self._save()
            return rid

    def load_report(self, case_id: str, report_doc_id: str) -> str:
        with self._lock:
            return self._reports[report_doc_id]

    def list_reports(self, case_id: str) -> list[dict]:
        """List a case's reports (newest first) — {report_id, name}."""
        with self._lock:
            out = [{"report_id": rid, "name": meta.get("name", rid)}
                   for rid, meta in self._report_meta.items()
                   if meta.get("case_id") == case_id]
            out.reverse()
            return out

    def delete_report(self, case_id: str, report_doc_id: str) -> None:
        with self._lock:
            self._reports.pop(report_doc_id, None)
            self._report_meta.pop(report_doc_id, None)
            self._save()

    # --- aggregation (demo stub) ---
    def aggregate(self, material_id: str, group_by: list[str], filters: dict,
                  weight: str | None = None) -> dict:
        return {"dimensions": list(group_by), "cells": [], "total": 0}
