from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "input"
WORK_DIR = ROOT / "work"
BRIEFS_DIR = ROOT / "briefs"

ATTENDO_SAV = INPUT_DIR / "spss AttendoSuomi-Brandiseuranta_112025.sav"
ATTENDO_TEMPLATE = INPUT_DIR / "Attendo Bränditutkimus Marraskuu 2025.pptx"

SURVEY_DB = WORK_DIR / "survey.duckdb"
CODEBOOK_JSON = WORK_DIR / "codebook.json"
WAVES_JSON = WORK_DIR / "waves.json"
GENERATED_PPTX = WORK_DIR / "attendo_generated.pptx"

WORK_DIR.mkdir(parents=True, exist_ok=True)
