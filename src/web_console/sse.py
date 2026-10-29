"""Server-Sent Events for a job's event buffer, resumable with ?after=<last seq> (the browser reads it with fetch)."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from .jobs import Job

POLL_SECONDS = 0.15
HEARTBEAT_SECONDS = 15.0


def coalesce(events: list[dict]) -> list[dict]:
    """Merge consecutive text deltas of the same step into one event (the id is the last merged seq)."""
    merged: list[dict] = []
    for event in events:
        last = merged[-1] if merged else None
        if (last and event.get("kind") == "text_delta" and last.get("kind") == "text_delta"
                and last.get("step") == event.get("step")):
            merged[-1] = {**last, "message": last.get("message", "") + event.get("message", ""), "seq": event["seq"]}
        else:
            merged.append(event)
    return merged


def format_event(event: dict) -> str:
    return f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def job_events(job: Job, after: int) -> AsyncIterator[str]:
    yield "retry: 1500\n\n"
    last_write = time.monotonic()
    while True:
        finished = job.finished is not None  # read before the batch: job_done is emitted before `finished` is set
        batch = job.events_after(after)
        if batch:
            for event in coalesce(batch):
                yield format_event(event)
            after = batch[-1]["seq"]
            last_write = time.monotonic()
            continue
        if finished:
            return
        if time.monotonic() - last_write > HEARTBEAT_SECONDS:
            yield ": keep-alive\n\n"
            last_write = time.monotonic()
        await asyncio.sleep(POLL_SECONDS)


def sse_response(job: Job, after: int) -> StreamingResponse:
    return StreamingResponse(job_events(job, max(0, after)), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
