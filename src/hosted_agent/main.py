"""Web QA hosted agent for Microsoft Foundry.

* Model: the deployment in AZURE_AI_MODEL_DEPLOYMENT_NAME (azure.yaml env).
* Browser (browser_backend.py, BROWSER_BACKEND):
  - toolbox (default, deployed): the GA Browser Automation tool through the Foundry Toolbox MCP endpoint
    (FoundryToolbox resolves it from FOUNDRY_PROJECT_ENDPOINT + TOOLBOX_NAME or TOOLBOX_ENDPOINT).
  - local (local runs only): the open-source Playwright MCP server driving a browser on this machine.
* Deterministic tools (web_tools.py): HTTP security headers/cookies, page-source signals, link checker.
* Protocol: OpenAI Responses (ResponsesHostServer) on port 8088 (PORT); AGENT_HOST sets the bind address.
* Tuning (env): BROWSER_TOOLS / LOCAL_BROWSER_TOOLS (tool allow-lists), CONTEXT_BUDGET_TOKENS (compaction budget,
  default 48000), MAX_CONSECUTIVE_TOOL_ERRORS (default 6).
* Workarounds for agent-framework-foundry-hosting 1.0.0b261015, both self-disabling once the package changes:
  usage_fix.py (reported token usage was summed from cumulative snapshots) and text_projection_fix.py (a divergent
  text snapshot failed the whole response).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from agent_framework import Agent, ContextWindowCompactionStrategy
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from dotenv import load_dotenv

from audit import tool_audit
from browser_backend import browser_backend, create_browser_tool, local_snapshot_middleware, select_sections
from dev_credential import build_credential
from text_projection_fix import apply as apply_text_projection_fix
from usage_fix import apply as apply_usage_fix
from web_tools import WEB_TOOLS, allowed_hosts

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("web_qa_agent")
apply_usage_fix()
apply_text_projection_fix()

BROWSER_BACKEND = browser_backend()
INSTRUCTIONS = select_sections((Path(__file__).parent / "instructions.md").read_text(encoding="utf-8"), BROWSER_BACKEND)

# One credential for the process; tokens are cached and refreshed by azure-identity. Managed identity in Foundry;
# locally, AZURE_CLI_SUBSCRIPTION (set by demo_cli's local mode) selects the Azure CLI account for that subscription.
credential = build_credential()


def create_agent() -> Agent:
    """Factory used by the hosting server: a fresh agent (and browser tool session) per request."""
    tools: list = []
    middleware: list = [tool_audit]
    browser_tool = create_browser_tool(BROWSER_BACKEND, credential)
    if browser_tool is not None:
        tools.append(browser_tool)
        if BROWSER_BACKEND == "local":
            middleware.append(local_snapshot_middleware(browser_tool))
    else:
        logger.warning("TOOLBOX_NAME/TOOLBOX_ENDPOINT not set: running without the Browser Automation tool.")
    tools.extend(WEB_TOOLS)

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    # Browser actions on a broken page fail by design (QA scenarios); the default of 3 consecutive tool errors stops
    # the tool loop too early.
    client.function_invocation_configuration["max_consecutive_errors_per_request"] = int(
        os.getenv("MAX_CONSECUTIVE_TOOL_ERRORS", "6")
    )
    # Let the model read why a browser action failed ("does not match any elements", "timed out ... take a snapshot")
    # instead of a generic error; it otherwise keeps retrying blindly. The model runs in your own Foundry project.
    client.function_invocation_configuration["include_detailed_errors"] = (
        os.getenv("DETAILED_TOOL_ERRORS", "true").strip().lower() in ("1", "true", "yes")
    )
    allow = ", ".join(allowed_hosts()) or "(none configured)"
    return Agent(
        client=client,
        name="web-qa-agent",
        instructions=INSTRUCTIONS.replace("{{ALLOWED_SCAN_HOSTS}}", allow),
        tools=tools,
        middleware=middleware,
        # Old browser snapshots are stale once the page changes: evict old tool results when the context grows.
        compaction_strategy=ContextWindowCompactionStrategy(
            max_context_window_tokens=int(os.getenv("CONTEXT_BUDGET_TOKENS", "48000")),
            max_output_tokens=4000,
            keep_last_tool_call_groups=4,
        ),
        # Conversation history is managed by the hosting infrastructure.
        default_options={"store": False},
    )


def main() -> None:
    logger.info("Starting web-qa-agent (model=%s, browser=%s, toolbox=%s, scan allow-list=%s)",
                os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME"), BROWSER_BACKEND, os.getenv("TOOLBOX_NAME"), allowed_hosts())
    # The hosted container must listen on all interfaces; the local launcher binds 127.0.0.1 (AGENT_HOST), and the
    # local browser backend defaults to loopback so a dev machine never exposes the agent on the network by accident.
    host = os.getenv("AGENT_HOST") or ("127.0.0.1" if BROWSER_BACKEND == "local" else "0.0.0.0")
    ResponsesHostServer(agent=create_agent).run(host=host)


if __name__ == "__main__":
    main()
