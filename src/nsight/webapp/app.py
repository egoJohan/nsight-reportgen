from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from nsight import config
from nsight.fidelity.compare import compare_decks
from nsight.fidelity.extract import extract_deck
from nsight.generate import generate_deck


class RunRequest(BaseModel):
    sav: str
    brief: str


def run_generation(sav: str, brief: str) -> dict:
    out = generate_deck(
        sav=config.INPUT_DIR / sav, brief_path=config.BRIEFS_DIR / brief,
        template=config.ATTENDO_TEMPLATE, out=config.GENERATED_PPTX,
    )
    rep = compare_decks(extract_deck(out), extract_deck(config.ATTENDO_TEMPLATE))
    return {"chart_score": rep.chart_score, "mismatches": rep.mismatches[:50],
            "deck_path": str(out)}


def create_app() -> FastAPI:
    import nsight.webapp.app as _mod

    app = FastAPI(title="nSight deck generator")

    @app.get("/api/inputs")
    def inputs() -> dict:
        return {"savs": [p.name for p in config.INPUT_DIR.glob("*.sav")],
                "briefs": [p.name for p in config.BRIEFS_DIR.glob("*.md")]}

    @app.post("/api/run")
    def run(req: RunRequest) -> dict:
        return _mod.run_generation(req.sav, req.brief)

    @app.get("/api/download")
    def download() -> FileResponse:
        return FileResponse(config.GENERATED_PPTX, filename="attendo_generated.pptx")

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    return app


app = create_app()
