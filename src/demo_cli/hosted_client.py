"""Invoke the deployed hosted agent (web-qa-agent) through its agent endpoint (Responses protocol)."""

from __future__ import annotations

import os
import time

from rich.console import Console

from demo_common.reporting import RunRecorder, RunResult
from demo_common.responses_stream import consume_stream, create_with_fallback
from demo_common.scenarios import RenderedScenario, evaluate, score_answer_key
from demo_common.settings import Settings
from prompt_agent.agent import project_client


def run_hosted_scenario(rendered: RenderedScenario, settings: Settings, *, console: Console | None = None,
                        listeners=None, quiet: bool = False) -> RunResult:
    model = os.getenv("HOSTED_AGENT_MODEL", settings.prompt_model)
    recorder = RunRecorder(rendered, "hosted", model, console=console, listeners=listeners, quiet=quiet)
    final_text, status, error = "", "completed", None
    started = time.monotonic()
    try:
        # Agent endpoints are exposed through get_openai_client(agent_name=...), which requires allow_preview=True.
        client = project_client(settings, allow_preview=True)
        recorder.emit("info", f"Invoking hosted agent '{settings.hosted_agent_name}' (Agent Framework + Foundry Toolbox)")
        openai_client = client.get_openai_client(agent_name=settings.hosted_agent_name).with_options(
            timeout=float(rendered.limits.timeout_seconds), max_retries=1
        )
        params = {"input": rendered.task, "stream": True}
        stream = create_with_fallback(openai_client, params, {"max_output_tokens": rendered.limits.max_output_tokens}, recorder)
        outcome = consume_stream(stream, recorder)
        final_text, status, error = outcome.text, outcome.status, outcome.error
    except Exception as exc:
        status, error = "failed", f"{type(exc).__name__}: {exc}"
        recorder.emit("error", error)
        recorder.note_content_filter(error)
    checks = evaluate(rendered, final_text) if final_text else []
    score = score_answer_key(rendered.scenario, final_text) if final_text else None
    return recorder.finish(final_text, checks, score, status=status, error=error, browser_seconds=time.monotonic() - started)
