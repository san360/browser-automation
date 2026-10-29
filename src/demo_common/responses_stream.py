"""Helpers for streaming Responses API calls to Foundry agents (prompt and hosted)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import openai

from .reporting import RunRecorder

TOOL_ITEM_TYPES = {"remote_function_call", "function_call", "mcp_call", "custom_tool_call", "computer_call", "web_search_call"}
OUTPUT_ITEM_TYPES = {"remote_function_call_output", "function_call_output", "mcp_call_output"}


@dataclass
class StreamOutcome:
    text: str = ""
    response_id: str | None = None
    status: str = "completed"
    error: str | None = None


def _json(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        # raw_decode tolerates trailing data (some hosts emit the arguments object twice: '{...}{...}').
        parsed, _ = json.JSONDecoder().raw_decode(str(value).strip())
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except (TypeError, json.JSONDecodeError):
        return {"raw": str(value)[:500]}


def create_with_fallback(client: openai.OpenAI, params: dict, optional: dict, recorder: RunRecorder):
    """Call responses.create with optional cost-limit parameters, dropping any the endpoint rejects."""
    optional = {k: v for k, v in optional.items() if v}
    while True:
        try:
            return client.responses.create(**params, **optional)
        except openai.BadRequestError as exc:
            message = str(exc).lower()
            rejected = [k for k in optional if k in message]
            if not rejected:
                raise
            for key in rejected:
                recorder.emit("warning", f"Endpoint rejected '{key}'; retrying without it.")
                optional.pop(key)


def consume_stream(stream, recorder: RunRecorder) -> StreamOutcome:
    """Process a Responses event stream without raising; errors are returned in the outcome."""
    outcome = StreamOutcome()
    texts: list[str] = []
    try:
        for event in stream:
            etype = getattr(event, "type", "")
            if etype == "response.created":
                outcome.response_id = event.response.id
                recorder.emit("info", f"Response {outcome.response_id} started")
            elif etype == "response.output_text.delta":
                recorder.text_delta(getattr(event, "delta", ""))
            elif etype == "response.output_text.done":
                text = getattr(event, "text", "") or ""
                texts.append(text)
                recorder.detect_live_view(text)
                preview = text.strip().splitlines()[0][:160] if text.strip() else ""
                recorder.emit("message", preview, chars=len(text))
            elif etype == "response.output_item.done":
                item = event.item
                itype = getattr(item, "type", "")
                if itype in TOOL_ITEM_TYPES:
                    name = getattr(item, "name", None) or getattr(item, "server_label", None) or itype
                    recorder.action(name, _json(getattr(item, "arguments", None)), item_type=itype,
                                    call_id=getattr(item, "call_id", None) or getattr(item, "id", None))
                elif itype in OUTPUT_ITEM_TYPES:
                    raw_output = getattr(item, "output", "") or ""
                    recorder.detect_browser_session(raw_output)
                    output = str(raw_output)
                    recorder.detect_live_view(output)
                    if '"error"' in output[:400].lower():
                        recorder.emit("warning", f"Tool reported an error: {output[:200]}")
                elif itype not in ("message", "reasoning"):
                    recorder.emit("info", f"Output item: {itype}")
                if itype == "mcp_call":
                    recorder.detect_browser_session(getattr(item, "output", None))
            elif etype in ("response.completed", "response.incomplete"):
                response = event.response
                recorder.add_usage(getattr(response, "usage", None))
                if etype == "response.incomplete":
                    outcome.status = "incomplete"
                    details = getattr(response, "incomplete_details", None)
                    recorder.emit("warning", f"Response incomplete: {details}")
                    recorder.note_content_filter(details)
            elif etype == "response.failed":
                response = getattr(event, "response", None)
                recorder.add_usage(getattr(response, "usage", None))
                outcome.status, outcome.error = "failed", f"Response failed: {getattr(response, 'error', None)}"
            elif etype == "error":
                outcome.status, outcome.error = "failed", f"Stream error: {getattr(event, 'message', event)}"
    except openai.APIError as exc:
        outcome.status, outcome.error = "failed", f"{type(exc).__name__}: {exc}"
    outcome.text = "\n\n".join(t for t in texts if t)
    if outcome.error:
        recorder.emit("error", outcome.error[:600])
        recorder.note_content_filter(outcome.error)
    return outcome
