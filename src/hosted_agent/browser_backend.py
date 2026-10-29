"""Browser backends for the web QA agent.

* ``toolbox`` (default, and the only option in Foundry): the GA Browser Automation tool through the Foundry Toolbox
  MCP endpoint. The browser runs in Azure Playwright Workspaces.
* ``local`` (local runs only): the open-source Playwright MCP server (``npx @playwright/mcp``) driving Edge or Chrome on
  this machine, so the agent can reach localhost and intranet sites. Needs Node.js, which the hosted container lacks.

The helpers below import nothing from Agent Framework at module level, so the unit tests can use them without the
hosted agent's dependencies.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from collections.abc import Iterable

BACKENDS = ("toolbox", "local")
PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp@0.0.83"

# Browser tools exposed to the model. Fewer tools mean smaller prompts and a smaller attack surface: code execution
# (browser_run_code / browser_run_code_unsafe), browser_evaluate, file upload and screenshots are never exposed by
# default.
DEFAULT_TOOLBOX_TOOLS = (
    "create_browser_session,browser_navigate,browser_navigate_back,browser_snapshot,browser_find,browser_click,"
    "browser_type,browser_fill_form,browser_select_option,browser_press_key,browser_wait_for,browser_handle_dialog,"
    "browser_console_messages,browser_network_requests,close_browser_session"
)
DEFAULT_LOCAL_TOOLS = (
    "browser_navigate,browser_navigate_back,browser_snapshot,browser_find,browser_click,browser_type,"
    "browser_fill_form,browser_select_option,browser_press_key,browser_wait_for,browser_handle_dialog,"
    "browser_console_messages,browser_network_requests,browser_tabs,browser_close"
)

_SECTION = re.compile(r"<!-- browser:(\w+) -->\n(.*?)<!-- /browser -->\n", re.DOTALL)


def browser_backend(value: str | None = None) -> str:
    backend = (value or os.getenv("BROWSER_BACKEND") or "toolbox").strip().lower()
    if backend not in BACKENDS:
        raise ValueError(f"BROWSER_BACKEND must be one of {', '.join(BACKENDS)}, not {backend!r}.")
    return backend


def select_sections(text: str, backend: str) -> str:
    """Keep the instruction blocks marked for this backend (<!-- browser:NAME --> ... <!-- /browser -->)."""
    return _SECTION.sub(lambda match: match.group(2) if match.group(1) == backend else "", text)


def _names(value: str) -> list[str]:
    return [name.strip() for name in value.split(",") if name.strip()]


def allowed_tool_names(backend: str) -> list[str]:
    if backend == "local":
        return _names(os.getenv("LOCAL_BROWSER_TOOLS", DEFAULT_LOCAL_TOOLS))
    prefix = os.getenv("BROWSER_TOOL_PREFIX", "browserautomation")
    return [f"{prefix}___{name}" for name in _names(os.getenv("BROWSER_TOOLS", DEFAULT_TOOLBOX_TOOLS))]


def default_local_browser() -> str:
    # Edge ships with Windows; elsewhere use the Chrome channel (install Chrome, or set LOCAL_BROWSER).
    return "msedge" if sys.platform == "win32" else "chrome"


def playwright_mcp_args(*, headless: bool = True, browser: str | None = None, allowed_origins: Iterable[str] = (),
                        output_dir: str | None = None, viewport: str = "1440,900",
                        package: str = PLAYWRIGHT_MCP_PACKAGE, init_page: str | None = None) -> list[str]:
    """npx arguments for the Playwright MCP server.

    --isolated keeps the browser profile in memory, so no cookies or history from your own browser are used or kept.
    --allowed-origins narrows which origins the browser may request; Playwright documents that it is not a security
    boundary, so it complements rather than replaces the allow-lists enforced elsewhere.
    --init-page (optional) runs a script against every new page; the web console uses it to mirror screenshots of this
    browser into its preview pane without changing what the tools return to the model.
    """
    args = ["-y", package, "--isolated", "--browser", browser or default_local_browser(), "--viewport-size", viewport,
            "--image-responses", "omit",
            "--output-dir", output_dir or os.path.join(tempfile.gettempdir(), "web-qa-agent-playwright")]
    if headless:
        args.append("--headless")
    origins = [origin for origin in allowed_origins if origin]
    if origins:
        args += ["--allowed-origins", ";".join(origins)]
    if init_page:
        args += ["--init-page", init_page]
    return args


def _flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None or value == "" else value.strip().lower() in ("1", "true", "yes")


# Page-changing actions. The cloud tool returns a fresh accessibility snapshot after each of them; Playwright MCP only
# links to a snapshot file, so local runs append one (see local_snapshot_middleware).
SNAPSHOT_AFTER = frozenset({
    "browser_navigate", "browser_navigate_back", "browser_click", "browser_type", "browser_fill_form",
    "browser_select_option", "browser_press_key", "browser_handle_dialog", "browser_tabs",
})


def _merge_results(result, extra):
    if isinstance(result, list) and isinstance(extra, list):
        return [*result, *extra]

    def text(value) -> str:
        if isinstance(value, list):
            return "\n".join(getattr(item, "text", None) or str(item) for item in value)
        return "" if value is None else str(value)

    return f"{text(result)}\n{text(extra)}"


def local_snapshot_middleware(browser_tool):
    """Function middleware for the local backend: append a fresh page snapshot to page-changing actions."""
    from agent_framework import function_middleware

    @function_middleware
    async def append_snapshot(context, call_next) -> None:
        await call_next()
        name = getattr(getattr(context, "function", None), "name", "") or ""
        if name not in SNAPSHOT_AFTER:
            return
        snapshot = next((f for f in getattr(browser_tool, "functions", []) if f.name == "browser_snapshot"), None)
        if snapshot is None:
            return
        try:
            fresh = await snapshot.invoke(arguments={})
        except Exception:  # keep the action's own result if the page can't be captured
            return
        context.result = _merge_results(context.result, fresh)

    return append_snapshot


def create_browser_tool(backend: str, credential):
    """The MCP tool that gives the agent a browser, or None when no browser is configured."""
    if backend == "local":
        from agent_framework import MCPStdioTool

        return MCPStdioTool(
            name="localbrowser",
            command=os.getenv("NPX_COMMAND", "npx"),
            args=playwright_mcp_args(
                headless=_flag("LOCAL_BROWSER_HEADLESS", True),
                browser=os.getenv("LOCAL_BROWSER") or None,
                allowed_origins=(os.getenv("LOCAL_BROWSER_ALLOWED_ORIGINS") or "").split(";"),
                output_dir=os.getenv("LOCAL_BROWSER_OUTPUT_DIR") or None,
                init_page=os.getenv("LOCAL_BROWSER_INIT_PAGE") or None,
            ),
            description="Browser on this machine (Playwright MCP)",
            load_prompts=False,
            # Snapshots are returned as text content; Agent Framework's default (structured_first) would hide them.
            tool_result_content="content_first",
            allowed_tools=allowed_tool_names("local"),
        )
    if os.getenv("TOOLBOX_ENDPOINT") or os.getenv("TOOLBOX_NAME"):
        from agent_framework_foundry_hosting import FoundryToolbox

        # The Browser Automation tools return the accessibility snapshot in `content` and only metadata in
        # `structuredContent`; Agent Framework defaults to structured_first, which would hide the snapshot.
        return FoundryToolbox(credential, tool_result_content="content_first", allowed_tools=allowed_tool_names("toolbox"))
    return None
