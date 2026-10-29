"""Run history (runs/*/result.json), run details and safe access to run files."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from demo_common.reporting import load_results

from .artifacts import FOLDER, read_events, read_text, result_payload, safe_run_dir, safe_run_file, started_at

SUMMARY_KEYS = ("scenario_id", "title", "mode", "model", "status", "duration_s", "tool_calls", "checks_passed",
                "checks_total", "answer_key_recall", "est_cost", "currency", "input_tokens", "output_tokens",
                "cached_tokens", "est_browser_minutes")


def history_router(runs_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/api/history")

    @router.get("")
    def runs() -> dict:
        rows = []
        for result in reversed(load_results(runs_dir)):
            folder = Path(result.get("run_dir") or "").name
            if not FOLDER.fullmatch(folder) or not (runs_dir / folder / "result.json").is_file():
                continue
            rows.append({**{key: result.get(key) for key in SUMMARY_KEYS}, "folder": folder,
                         "started": started_at(folder), "has_error": bool(result.get("error"))})
        return {"runs": rows}

    @router.get("/{folder}")
    def run(folder: str) -> dict:
        path = safe_run_dir(runs_dir, folder)
        try:
            result = json.loads(read_text(path / "result.json") or "null")
        except ValueError:
            result = None
        payload = result_payload({**result, "run_dir": str(path)}, runs_dir) if isinstance(result, dict) else None
        return {"folder": folder, "started": started_at(folder), "result": payload,
                "report": read_text(path / "report.md"), "task": read_text(path / "task.md"),
                "events": read_events(path)}

    @router.get("/{folder}/files/{name}")
    def file(folder: str, name: str) -> FileResponse:
        path, media = safe_run_file(runs_dir, folder, name)
        return FileResponse(path, media_type=media, headers={"Cache-Control": "no-cache",
                                                             "Content-Disposition": "inline"})

    return router
