"""Run a scenario against the prompt agent (Browser Automation tool) through the Responses API."""

from __future__ import annotations

import time

from rich.console import Console

from demo_common.reporting import RunRecorder, RunResult
from demo_common.responses_stream import StreamOutcome, consume_stream, create_with_fallback
from demo_common.scenarios import RenderedScenario, evaluate, score_answer_key
from demo_common.settings import Settings

from .agent import ensure_prompt_agent, project_client

DATA_ZONE_MODELS = {"gpt-5.4-mini"}
RECOVERY_PROMPT = (
    "The previous browser action failed with this error: {error}\n"
    "Do not start over. Take a fresh browser_snapshot of the current page (create a new browser session and navigate "
    "back to {url} only if the session is gone), target elements by the refs from that snapshot, and continue the "
    "original task until it is complete. If the same element failed before, record it as a defect and move on "
    "instead of retrying it. Then give the final answer in the requested format."
)


def run_prompt_scenario(rendered: RenderedScenario, settings: Settings, *, model: str | None = None,
                        console: Console | None = None, listeners=None, quiet: bool = False) -> RunResult:
    model = model or settings.prompt_model
    recorder = RunRecorder(rendered, "prompt", model, console=console, listeners=listeners, quiet=quiet)
    outcome = StreamOutcome(status="failed")
    texts: list[str] = []
    started = time.monotonic()
    try:
        client = project_client(settings)
        recorder.emit("info", f"Ensuring prompt agent for model {model} ...")
        agent = ensure_prompt_agent(settings, model, client=client)
        recorder.emit("info", f"Using agent {agent.name} version {agent.version} (tool: browser_automation)")
        limits = rendered.limits
        openai_client = client.get_openai_client().with_options(timeout=float(limits.timeout_seconds), max_retries=1)
        reference = {"agent_reference": {"name": agent.name, "version": agent.version, "type": "agent_reference"}}
        optional = {"max_output_tokens": limits.max_output_tokens, "max_tool_calls": limits.max_tool_calls}

        stream = create_with_fallback(openai_client, {"input": rendered.task, "stream": True, "extra_body": reference}, optional, recorder)
        outcome = consume_stream(stream, recorder)
        texts.append(outcome.text)

        # Browser actions can time out (for example on a guessed selector) and end the response.
        # Continue the same conversation from the failed response instead of starting over.
        attempts = 0
        while outcome.error and attempts < limits.max_recoveries:
            attempts += 1
            if "rate limit" in outcome.error.lower():
                # The agent's server-side tool loop surfaces model 429s as stream errors; back off before continuing.
                delay = min(20 * attempts, 60)
                recorder.emit("warning", f"Model deployment rate limit reached; waiting {delay}s before continuing.")
                time.sleep(delay)
            recorder.emit("warning", f"Recovering after a failed browser action (attempt {attempts}/{limits.max_recoveries})")
            prompt = RECOVERY_PROMPT.format(error=outcome.error[:400], url=rendered.url)
            params = {"input": prompt, "stream": True, "extra_body": reference}
            if outcome.response_id:
                params["previous_response_id"] = outcome.response_id
            else:
                params["input"] = f"{rendered.task}\n\n{prompt}"
            try:
                stream = create_with_fallback(openai_client, params, optional, recorder)
            except Exception as exc:  # previous_response_id not usable: restart with the original task
                recorder.emit("warning", f"Could not continue the conversation ({type(exc).__name__}); restarting the task.")
                params = {"input": f"{rendered.task}\n\n{prompt}", "stream": True, "extra_body": reference}
                stream = create_with_fallback(openai_client, params, optional, recorder)
            outcome = consume_stream(stream, recorder)
            texts.append(outcome.text)
    except Exception as exc:  # report every failure as a result instead of crashing the demo
        outcome = StreamOutcome(status="failed", error=f"{type(exc).__name__}: {exc}")
        recorder.emit("error", outcome.error)
        recorder.note_content_filter(outcome.error)
    final_text = outcome.text or "\n\n".join(t for t in texts if t)
    checks = evaluate(rendered, final_text) if final_text else []
    score = score_answer_key(rendered.scenario, final_text) if final_text else None
    return recorder.finish(final_text, checks, score, status=outcome.status, error=outcome.error,
                           sku="DataZoneStandard" if model in DATA_ZONE_MODELS else "GlobalStandard",
                           browser_seconds=time.monotonic() - started)
