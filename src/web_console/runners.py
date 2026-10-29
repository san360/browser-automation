"""Dispatch a run to one of the four runners. Each is blocking, accepts listeners and writes its own run folder."""

from __future__ import annotations

import os
from collections.abc import Callable

from demo_common.reporting import RunResult
from demo_common.scenarios import RenderedScenario, ScenarioError
from demo_common.settings import Settings

from .schemas import JobRequest, Options

MODES = ("prompt", "hosted", "local", "cua")
Runner = Callable[..., RunResult]


def hosted_model(settings: Settings) -> str:
    """The model the hosted agent's code uses (the same expression as the hosted and local runners)."""
    return os.getenv("HOSTED_AGENT_MODEL", settings.prompt_model)


def prompt_models(settings: Settings) -> list[str]:
    return list(dict.fromkeys([settings.prompt_model, settings.strong_model]))


def cua_models(settings: Settings) -> list[str]:
    return list(dict.fromkeys([settings.computer_use_model, settings.strong_model]))


def step_model(mode: str, settings: Settings, request: JobRequest) -> str:
    if mode == "prompt":
        model = request.prompt_model or settings.prompt_model
        if model not in prompt_models(settings):
            # Each prompt model gets its own agent version in the project, so only the configured ones are offered.
            raise ScenarioError(f"Prompt agent model must be one of {', '.join(prompt_models(settings))}.")
        return model
    if mode == "cua":
        return request.cua_model or settings.computer_use_model
    return hosted_model(settings)


def run_mode(mode: str, rendered: RenderedScenario, settings: Settings, *, model: str, options: Options,
             listeners: list) -> RunResult:
    if mode == "prompt":
        from prompt_agent.runner import run_prompt_scenario

        return run_prompt_scenario(rendered, settings, model=model, listeners=listeners, quiet=True)
    if mode == "hosted":
        from demo_cli.hosted_client import run_hosted_scenario

        return run_hosted_scenario(rendered, settings, listeners=listeners, quiet=True)
    if mode == "local":
        from demo_cli.local_agent import run_local_scenario

        return run_local_scenario(rendered, settings, remote_browser=options.remote_browser,
                                  headed=options.headed and not options.remote_browser, listeners=listeners, quiet=True)
    if mode == "cua":
        from computer_use.runner import run_cua_scenario

        return run_cua_scenario(rendered, settings, model=model, headless=not options.headed,
                                auto_ack=options.auto_ack, listeners=listeners, quiet=True)
    raise ScenarioError(f"Unknown mode {mode}")
