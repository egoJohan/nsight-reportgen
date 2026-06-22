"""Repo paths for reportbuilder tests (plan §C7 / Task 0.11)."""
from __future__ import annotations
from pathlib import Path

# src/reportbuilder/config.py -> parents[2] is the repo root (proto/)
_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = _ROOT / "input"
WORK_DIR = _ROOT / "work"
ATTENDO_SAV = INPUT_DIR / "spss AttendoSuomi-Brandiseuranta_112025.sav"
ATTENDO_TEMPLATE = WORK_DIR / "attendo_blanked.pptx"
