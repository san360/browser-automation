"""Start, follow and stop runs (jobs); stream their events; serve local-browser preview frames."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from demo_common.scenarios import ScenarioError

from .jobs import Busy, Job, JobManager
from .schemas import JobRequest
from .sse import sse_response


def jobs_router(jobs: JobManager) -> APIRouter:
    router = APIRouter(prefix="/api/jobs")

    def find(job_id: str) -> Job:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Run not found (the console keeps the last few runs in memory).")
        return job

    @router.post("", status_code=202)
    def start(body: JobRequest) -> dict:
        try:
            job = jobs.start(body)
        except Busy as exc:
            raise HTTPException(409, str(exc)) from exc
        except ScenarioError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"job": job.summary()}

    @router.get("/current")
    def current() -> dict:
        job = jobs.latest()
        return {"job": job.summary() if job else None, "active": jobs.active is not None}

    @router.get("/{job_id}")
    def get(job_id: str) -> dict:
        return {"job": find(job_id).summary()}

    @router.get("/{job_id}/events")
    def events(job_id: str, after: int = 0):
        return sse_response(find(job_id), after)

    @router.post("/{job_id}/stop")
    def stop(job_id: str) -> dict:
        job = find(job_id)
        jobs.stop(job)
        return {"job": job.summary()}

    @router.get("/{job_id}/frames/{number}")
    def frame(job_id: str, number: int) -> Response:
        data = find(job_id).frame(number)
        if data is None:
            raise HTTPException(404, "Frame no longer available.")
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})

    return router
