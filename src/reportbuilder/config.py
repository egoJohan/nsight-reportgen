"""Repo paths for reportbuilder tests (plan §C7 / Task 0.11)."""
from __future__ import annotations

import os
from pathlib import Path

from reportbuilder.store.datahive_client import DataHiveClient

# src/reportbuilder/config.py -> parents[2] is the repo root (proto/)
_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = _ROOT / "input"
WORK_DIR = _ROOT / "work"
ATTENDO_SAV = INPUT_DIR / "spss AttendoSuomi-Brandiseuranta_112025.sav"
ATTENDO_TEMPLATE = WORK_DIR / "attendo_blanked.pptx"


def datahive_client_from_env() -> DataHiveClient | None:
    """Build a DataHiveClient from env, or None if NSIGHT_DATAHIVE_URL is unset.

    Env: NSIGHT_DATAHIVE_URL, NSIGHT_DATAHIVE_TOKEN, NSIGHT_DATAHIVE_TENANT,
         NSIGHT_DATAHIVE_TEMPLATE (default 'wftemplate:dataset-report-study').
    """
    url = os.environ.get("NSIGHT_DATAHIVE_URL")
    if not url:
        return None
    return DataHiveClient(
        base_url=url,
        token=os.environ.get("NSIGHT_DATAHIVE_TOKEN"),
        tenant=os.environ.get("NSIGHT_DATAHIVE_TENANT"),
        template_ref=os.environ.get(
            "NSIGHT_DATAHIVE_TEMPLATE", "wftemplate:dataset-report-study"
        ),
    )
