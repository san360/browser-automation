"""One job at a time: a single run, or a comparison of several modes run one after another, in a worker thread.

Runner events are buffered per job with a sequence number and streamed to the browser as Server-Sent Events. The
buffer is in memory only: it holds the unredacted live-view link, which must never be logged or written to disk.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import nullcontext
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from demo_common.reporting import redact
from demo_common.scenarios import RenderedScenario, enforce_allowlist, load_catalog
from demo_common.settings import Settings
from demo_cli.summaries import comparison_row, save_comparison

from .artifacts import locate_run_folder, result_payload, run_folders
from .local_mirror import LocalMirror
from .rendering import demo_site, render_request, site_override, warnings_for
from .runners import Runner, step_model
from .schemas import JobRequest

KEEP_JOBS = 5
MAX_FRAMES = 30


class Busy(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def clean_event(event: dict) -> dict:
    """JSON-safe copy of a runner event. Only the live_view event keeps its signed link, for the presenter's UI."""
    data = json.loads(json.dumps(event, default=str, ensure_ascii=False))
    if data.get("kind") == "live_view":
        url = str(data.get("url") or "")
        data["url"] = url if url.startswith("https://") else None
        data["message"] = "Live view of the cloud browser is available."
    elif data.get("kind") != "text_delta" and isinstance(data.get("message"), str):
        data["message"] = redact(data["message"])
    return data


@dataclass
class Step:
    index: int
    mode: str
    model: str
    status: str = "pending"
    folder: str | None = None
    result: dict | None = None
    error: str | None = None
    started: float | None = None


class Job:
    def __init__(self, request: JobRequest, rendered: RenderedScenario, steps: list[Step], site: str | None,
                 notes: list[str]) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.request, self.rendered, self.steps, self.site, self.notes = request, rendered, steps, site, notes
        self.status = "running"
        self.stop_requested = False
        self.created = time.time()
        self.finished: float | None = None
        self.comparison: str | None = None
        self._events: list[dict] = []
        self._frames: OrderedDict[int, bytes] = OrderedDict()
        self._frame_seq = 0
        self._lock = threading.Lock()

    def emit(self, step: int | None, event: dict) -> None:
        with self._lock:
            self._events.append({**event, "seq": len(self._events) + 1, "step": step})

    def events_after(self, seq: int) -> list[dict]:
        with self._lock:
            return self._events[max(0, seq):]

    def add_frame(self, step: int, data: bytes, meta: dict) -> None:
        with self._lock:
            self._frame_seq += 1
            number = self._frame_seq
            self._frames[number] = data
            while len(self._frames) > MAX_FRAMES:
                self._frames.popitem(last=False)
        self.emit(step, {"kind": "frame", "frame": number, "url": str(meta.get("url") or ""),
                         "title": str(meta.get("title") or ""), "ts": now()})

    def frame(self, number: int) -> bytes | None:
        with self._lock:
            return self._frames.get(number)

    def summary(self) -> dict:
        scenario = self.rendered.scenario
        return {
            "id": self.id, "status": self.status, "scenario_id": scenario.id, "title": scenario.title,
            "level": scenario.level, "category": scenario.category, "url": self.rendered.url, "task": self.rendered.task,
            "allowed_domains": self.rendered.allowed_domains, "limits": asdict(self.rendered.limits), "site": self.site,
            "options": self.request.options.model_dump(), "steps": [asdict(s) for s in self.steps], "notes": self.notes,
            "created": self.created, "finished": self.finished, "stop_requested": self.stop_requested,
            "comparison": self.comparison,
        }


class JobManager:
    def __init__(self, settings: Settings, runs_dir: Path, runner: Runner) -> None:
        self.settings, self.runs_dir, self.runner = settings, runs_dir, runner
        self.jobs: OrderedDict[str, Job] = OrderedDict()
        self.active: Job | None = None
        self._lock = threading.Lock()

    def latest(self) -> Job | None:
        return self.active or next(reversed(self.jobs.values()), None)

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def start(self, request: JobRequest) -> Job:
        with self._lock:
            if self.active:
                raise Busy("A run is already in progress. Runs use real Azure resources, so only one runs at a time.")
            site = site_override(request.site_url, self.settings)
            with demo_site(site):
                rendered, _ = render_request(request, load_catalog())
                enforce_allowlist(rendered)
            steps = [Step(i, mode, step_model(mode, self.settings, request)) for i, mode in enumerate(request.modes)]
            notes = warnings_for(rendered, request.modes, remote_browser=request.options.remote_browser,
                                 overrides=request.inputs or {})
            job = Job(request, rendered, steps, site, notes)
            self.jobs[job.id] = job
            while len(self.jobs) > KEEP_JOBS:
                self.jobs.popitem(last=False)
            self.active = job
        threading.Thread(target=self._work, args=(job,), name=f"job-{job.id}", daemon=True).start()
        return job

    def stop(self, job: Job) -> None:
        if job is self.active and not job.stop_requested:
            job.stop_requested = True
            job.emit(None, {"kind": "info", "ts": now(),
                            "message": "Stop requested: the current run finishes, the remaining modes are skipped."})

    def _work(self, job: Job) -> None:
        settings = replace(self.settings, demo_site_url=job.site) if job.site else self.settings
        try:
            with demo_site(job.site):
                for note in job.notes:
                    job.emit(None, {"kind": "warning", "message": note, "ts": now()})
                for step in job.steps:
                    if job.stop_requested:
                        step.status = "skipped"
                        continue
                    self._run_step(job, step, settings)
            job.status = "stopped" if any(s.status == "skipped" for s in job.steps) else "completed"
        except Exception as exc:  # never leave the console stuck in "running"
            job.status = "failed"
            job.emit(None, {"kind": "error", "message": redact(f"{type(exc).__name__}: {exc}"), "ts": now()})
        finally:
            self._save_comparison(job)
            job.emit(None, {"kind": "job_done", "status": job.status, "ts": now(), "comparison": job.comparison,
                            "steps": [asdict(s) for s in job.steps]})
            job.finished = time.time()
            with self._lock:
                self.active = None

    def _run_step(self, job: Job, step: Step, settings: Settings) -> None:
        before = run_folders(self.runs_dir)
        suffix = f"-{job.rendered.scenario.id}-{step.mode}"

        def listener(event: dict) -> None:
            if step.folder is None and event.get("ts"):
                step.folder = locate_run_folder(self.runs_dir, before, suffix, event["ts"])
                if step.folder:
                    job.emit(step.index, {"kind": "run_folder", "folder": step.folder})
            job.emit(step.index, clean_event(event))

        step.status, step.started = "running", time.time()
        job.emit(step.index, {"kind": "step_start", "mode": step.mode, "model": step.model, "ts": now()})
        try:
            with self._mirror(job, step):
                result = self.runner(step.mode, job.rendered, settings, model=step.model, options=job.request.options,
                                     listeners=[listener])
            step.result = result_payload(asdict(result), self.runs_dir)
            step.status, step.folder = result.status, step.result.get("folder") or step.folder
        except Exception as exc:
            step.status, step.error = "error", redact(f"{type(exc).__name__}: {exc}")
            job.emit(step.index, {"kind": "error", "message": step.error, "ts": now()})
        job.emit(step.index, {"kind": "step_done", "mode": step.mode, "status": step.status, "result": step.result,
                              "error": step.error, "ts": now()})

    def _mirror(self, job: Job, step: Step):
        options = job.request.options
        if step.mode == "local" and options.mirror and not options.remote_browser:
            return LocalMirror(lambda data, meta: job.add_frame(step.index, data, meta))
        return nullcontext()

    def _save_comparison(self, job: Job) -> None:
        rows = [comparison_row(s.result) for s in job.steps if s.result]
        if len(job.steps) < 2 or not rows:
            return
        try:
            path = save_comparison(job.rendered.scenario.title, job.rendered.scenario.id, rows, self.runs_dir)
            job.comparison = path.name
        except OSError:
            pass
