"""Create, reuse and delete prompt agents that use the GA Browser Automation tool.

This is the canonical azure-ai-projects (>= 2.8) pattern:

    tool = BrowserAutomationTool(
        browser_automation=BrowserAutomationToolParameters(
            connection=BrowserAutomationToolConnectionParameters(project_connection_id=<connection ARM id>)))
    project.agents.create_version(agent_name, definition=PromptAgentDefinition(model=..., instructions=..., tools=[tool]))

Each change to the definition creates a new immutable agent version, so versions are reused when nothing changed
(a hash of the definition is stored in the version metadata).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentVersionDetails,
    BrowserAutomationTool,
    BrowserAutomationToolConnectionParameters,
    BrowserAutomationToolParameters,
    PromptAgentDefinition,
)
from azure.core.exceptions import ResourceNotFoundError

from demo_common.settings import Settings, get_credential

INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(encoding="utf-8").strip()
MANAGED_BY = "foundry-browser-automation-demo"


def project_client(settings: Settings, *, allow_preview: bool = False) -> AIProjectClient:
    if not settings.project_endpoint:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is not set. Run `azd provision` (or create a .env file).")
    return AIProjectClient(endpoint=settings.project_endpoint, credential=get_credential(), allow_preview=allow_preview)


def agent_name_for(settings: Settings, model: str) -> str:
    if model == settings.prompt_model:
        return settings.prompt_agent_name
    return f"{settings.prompt_agent_name}-{re.sub(r'[^a-z0-9]+', '-', model.lower()).strip('-')}"


def build_definition(settings: Settings, model: str) -> PromptAgentDefinition:
    if not settings.browser_connection_id:
        raise RuntimeError("BROWSER_AUTOMATION_PROJECT_CONNECTION_ID is not set. Run `azd provision`.")
    tool = BrowserAutomationTool(
        browser_automation=BrowserAutomationToolParameters(
            connection=BrowserAutomationToolConnectionParameters(project_connection_id=settings.browser_connection_id)
        )
    )
    return PromptAgentDefinition(model=model, instructions=INSTRUCTIONS, tools=[tool])


def _definition_hash(settings: Settings, model: str) -> str:
    payload = json.dumps({"model": model, "instructions": INSTRUCTIONS, "connection": settings.browser_connection_id}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def ensure_prompt_agent(settings: Settings, model: str | None = None, *, client: AIProjectClient | None = None,
                        force_new_version: bool = False) -> AgentVersionDetails:
    """Return the latest agent version for `model`, creating a new version only when the definition changed."""
    model = model or settings.prompt_model
    name = agent_name_for(settings, model)
    digest = _definition_hash(settings, model)
    client = client or project_client(settings)
    if not force_new_version:
        try:
            latest = next(iter(client.agents.list_versions(name, limit=1, order="desc")), None)
        except ResourceNotFoundError:
            latest = None
        if latest is not None and (latest.metadata or {}).get("definition_hash") == digest:
            return latest
    return client.agents.create_version(
        name,
        definition=build_definition(settings, model),
        description="Browser automation demo agent (GA Browser Automation tool + Playwright Workspaces).",
        metadata={"definition_hash": digest, "managed_by": MANAGED_BY, "model": model},
    )


def list_demo_agents(settings: Settings) -> list[dict]:
    client = project_client(settings)
    rows = []
    for agent in client.agents.list():
        versions = getattr(agent, "versions", None)
        latest = getattr(versions, "latest", None) if versions else None
        rows.append({
            "name": agent.name,
            "kind": getattr(getattr(latest, "definition", None), "kind", "?") if latest else "?",
            "version": getattr(latest, "version", "?") if latest else "?",
            "model": getattr(getattr(latest, "definition", None), "model", "") if latest else "",
        })
    return rows


def delete_prompt_agents(settings: Settings, models: list[str]) -> list[str]:
    client = project_client(settings)
    deleted = []
    for model in models:
        name = agent_name_for(settings, model)
        try:
            client.agents.delete(name, force=True)
            deleted.append(name)
        except ResourceNotFoundError:
            continue
    return deleted
