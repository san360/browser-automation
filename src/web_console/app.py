"""FastAPI application: API routers, the request guard and the static single-page console."""

from __future__ import annotations

import threading
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from demo_cli.summaries import local_mode_checks
from demo_common.scenarios import ScenarioError
from demo_common.settings import RUNS_DIR, Settings, get_settings

from .jobs import JobManager
from .routes_catalog import catalog_router
from .routes_history import history_router
from .routes_jobs import jobs_router
from .routes_overview import overview_router
from .runners import Runner, cua_models, hosted_model, prompt_models, run_mode
from .security import ConsoleGuard, loopback_hosts, new_token

STATIC = Path(__file__).parent / "static"


def public_settings(settings: Settings) -> dict:
    """What the browser may see: endpoints and names, never connection strings or tokens."""
    return {
        "project_endpoint": settings.project_endpoint, "project_host": urlparse(settings.project_endpoint).hostname,
        "demo_site_url": settings.demo_site_url, "demo_site_host": settings.demo_site_host,
        "prompt_agent_name": settings.prompt_agent_name, "hosted_agent_name": settings.hosted_agent_name,
        "toolbox_name": settings.toolbox_name, "connection_name": settings.browser_connection_id.rsplit("/", 1)[-1],
        "prompt_model": settings.prompt_model, "strong_model": settings.strong_model,
        "computer_use_model": settings.computer_use_model, "hosted_model": hosted_model(settings),
        "resource_groups": settings.resource_groups,
    }


def create_app(*, settings: Settings | None = None, runs_dir: Path = RUNS_DIR, runner: Runner = run_mode,
               port: int = 8765, bind_host: str = "127.0.0.1") -> FastAPI:
    # get_settings() also exports .env and azd values to os.environ before any demo-site override can happen.
    settings = settings or get_settings()
    token = new_token()
    jobs = JobManager(settings, runs_dir, runner)
    app = FastAPI(title="Foundry Browser Automation console", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.jobs = jobs
    app.state.settings = settings
    app.add_middleware(ConsoleGuard, token=token, hosts=loopback_hosts(port, bind_host))

    @app.exception_handler(ScenarioError)
    async def scenario_error(_, exc: ScenarioError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "busy": jobs.active is not None}

    local: list[dict] = []
    local_lock = threading.Lock()

    @app.get("/api/bootstrap")
    def bootstrap() -> dict:
        with local_lock:  # computed once (it runs `node --version`), even when the first requests overlap
            if not local:
                local.extend([asdict(check) for check in local_mode_checks()])
        job = jobs.latest()
        return {
            "token": token, "settings": public_settings(settings), "local": local,
            "models": {"prompt": prompt_models(settings), "cua": cua_models(settings)},
            "job": job.summary() if job else None, "active": jobs.active is not None,
        }

    app.include_router(catalog_router(settings, jobs))
    app.include_router(jobs_router(jobs))
    app.include_router(history_router(runs_dir))
    app.include_router(overview_router(settings, runs_dir))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html; charset=utf-8")

    return app
