"""Scenario catalog, task previews and demo-site health."""

from __future__ import annotations

from contextlib import nullcontext

import httpx
from fastapi import APIRouter, HTTPException

from demo_common.scenarios import ScenarioError, enforce_allowlist, load_catalog
from demo_common.settings import Settings

from .jobs import JobManager
from .rendering import (
    demo_site,
    http_url,
    parse_inputs,
    preview,
    render_request,
    scenario_card,
    site_override,
    warnings_for,
)
from .schemas import RenderRequest


def catalog_router(settings: Settings, jobs: JobManager) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/scenarios")
    def scenarios() -> dict:
        return {"scenarios": [scenario_card(s) for s in load_catalog().values()]}

    @router.post("/render")
    def render_preview(body: RenderRequest) -> dict:
        site = site_override(body.site_url, settings)
        active = jobs.active
        if active and active.site != site:
            # The running job's demo-site override is process-wide until it finishes (see rendering.ENV_LOCK).
            raise HTTPException(409, "A run against another demo-site target is in progress; the task preview "
                                     "is available again when it finishes.")
        with nullcontext() if active else demo_site(site):
            rendered, defaults = render_request(body, load_catalog())
            try:
                enforce_allowlist(rendered)
                allowlist_error = None
            except ScenarioError as exc:
                allowlist_error = str(exc)
        notes = warnings_for(rendered, body.modes, remote_browser=body.options.remote_browser,
                             overrides=parse_inputs(body))
        return preview(rendered, defaults, notes, allowlist_error)

    @router.get("/site-health")
    def site_health(url: str | None = None) -> dict:
        target = http_url(url or settings.demo_site_url or "", "The demo-site URL").rstrip("/")
        try:
            response = httpx.get(f"{target}/healthz", timeout=45)
        except httpx.HTTPError as exc:
            return {"url": target, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}
        try:
            data = response.json()
        except ValueError:
            data = None
        ok = response.status_code == 200 and isinstance(data, dict) and data.get("status") == "ok"
        detail = data if isinstance(data, dict) else response.text[:200]
        return {"url": target, "ok": ok, "status": response.status_code, "detail": detail}

    return router
