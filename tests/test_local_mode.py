"""Tests for local mode: browser backend selection, Playwright MCP arguments and the local agent launcher."""

import os
from pathlib import Path

import pytest

import browser_backend as bb
from demo_cli import local_agent
from demo_cli.__main__ import main
from demo_common import scenarios as sc
from demo_common.settings import Settings

INSTRUCTIONS = (Path(__file__).resolve().parents[1] / "src" / "hosted_agent" / "instructions.md").read_text(encoding="utf-8")


def test_backend_defaults_to_toolbox(monkeypatch):
    monkeypatch.delenv("BROWSER_BACKEND", raising=False)
    assert bb.browser_backend() == "toolbox"
    assert bb.browser_backend("LOCAL") == "local"
    with pytest.raises(ValueError):
        bb.browser_backend("selenium")


def test_instructions_keep_only_the_selected_backend():
    local = bb.select_sections(INSTRUCTIONS, "local")
    cloud = bb.select_sections(INSTRUCTIONS, "toolbox")
    for text in (local, cloud):
        assert "<!-- browser" not in text and "<!-- /browser" not in text
        assert "{{ALLOWED_SCAN_HOSTS}}" in text
        for step in ("1. ", "2. ", "3. ", "4. ", "5. ", "6. "):
            assert f"\n{step}" in text
    assert "create_browser_session" not in local and "liveViewUrl" not in local and "`browser_close`" in local
    assert "create_browser_session" in cloud and "liveViewUrl" in cloud and "Playwright MCP" not in cloud


def test_playwright_mcp_args_are_isolated_and_pinned():
    args = bb.playwright_mcp_args(headless=True, browser="msedge", output_dir="out")
    assert args[:2] == ["-y", bb.PLAYWRIGHT_MCP_PACKAGE] and "@" in bb.PLAYWRIGHT_MCP_PACKAGE[1:]
    assert "--isolated" in args and "--headless" in args and "--allowed-origins" not in args
    assert args[args.index("--browser") + 1] == "msedge"
    assert "--allow-unrestricted-file-access" not in args
    assert "--init-page" not in args
    headed = bb.playwright_mcp_args(headless=False, allowed_origins=["https://a.example", "", "http://localhost:8000"])
    assert "--headless" not in headed
    assert headed[headed.index("--allowed-origins") + 1] == "https://a.example;http://localhost:8000"
    mirrored = bb.playwright_mcp_args(init_page="C:/tmp/mirror.cjs")
    assert mirrored[mirrored.index("--init-page") + 1] == "C:/tmp/mirror.cjs"


def test_tool_allow_lists_exclude_code_execution(monkeypatch):
    monkeypatch.delenv("LOCAL_BROWSER_TOOLS", raising=False)
    monkeypatch.delenv("BROWSER_TOOLS", raising=False)
    local = bb.allowed_tool_names("local")
    assert "browser_snapshot" in local and "browser_close" in local
    assert not {"browser_run_code_unsafe", "browser_evaluate", "browser_file_upload"} & set(local)
    cloud = bb.allowed_tool_names("toolbox")
    assert all(name.startswith("browserautomation___") for name in cloud)
    assert "browserautomation___create_browser_session" in cloud
    # Every page-changing local action gets a fresh snapshot appended, and only allowed tools are listed.
    assert bb.SNAPSHOT_AFTER <= set(local) and "browser_snapshot" not in bb.SNAPSHOT_AFTER


def test_merge_results_appends_snapshot():
    assert bb._merge_results(["action"], ["snapshot"]) == ["action", "snapshot"]
    assert bb._merge_results("clicked", ["page"]) == "clicked\npage"
    assert bb._merge_results(None, "page") == "\npage"


SETTINGS = Settings(project_endpoint="https://unit.services.ai.azure.com/api/projects/p",
                    demo_site_url="https://demo.contoso.example", toolbox_name="browser-automation-tools",
                    subscription_id="00000000-0000-0000-0000-000000000001")


def test_server_env_for_local_browser():
    rendered = sc.render(sc.find_scenario("02"))
    env = local_agent.server_env(SETTINGS, rendered, model="gpt-4.1-mini", port=8123, remote_browser=False,
                                 headed=False, output_dir="tmp", base_env={"TOOLBOX_NAME": "x"})
    assert env["BROWSER_BACKEND"] == "local" and env["AGENT_HOST"] == "127.0.0.1" and env["PORT"] == "8123"
    assert env["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "false"
    assert env["APPLICATIONINSIGHTS_CONNECTION_STRING"] == ""
    assert env["AZURE_CLI_SUBSCRIPTION"] == SETTINGS.subscription_id
    assert env["LOCAL_BROWSER_HEADLESS"] == "true" and env["ALLOWED_SCAN_HOSTS"] == "demo.contoso.example"
    assert "LOCAL_BROWSER_ALLOWED_ORIGINS" not in env  # no domain allow-list in this scenario


def test_server_env_for_cloud_browser_and_allow_listed_scenario():
    rendered = sc.render(sc.find_scenario("12"))
    remote = local_agent.server_env(SETTINGS, rendered, model="m", port=1, remote_browser=True, headed=True,
                                    output_dir="tmp", base_env={})
    assert remote["BROWSER_BACKEND"] == "toolbox" and remote["TOOLBOX_NAME"] == "browser-automation-tools"
    local = local_agent.server_env(SETTINGS, rendered, model="m", port=1, remote_browser=False, headed=True,
                                   output_dir="tmp", base_env={})
    origins = local["LOCAL_BROWSER_ALLOWED_ORIGINS"].split(";")
    assert "https://demo.contoso.example" in origins and local["LOCAL_BROWSER_HEADLESS"] == "false"


def test_agent_python_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_AGENT_PYTHON", str(tmp_path / "python"))
    assert local_agent.agent_python() == tmp_path / "python"
    monkeypatch.delenv("LOCAL_AGENT_PYTHON")
    assert local_agent.HOSTED_AGENT_DIR / ".venv" in local_agent.agent_python().parents


def test_site_url_points_scenarios_at_another_copy(monkeypatch):
    monkeypatch.setenv("DEMO_SITE_URL", os.environ["DEMO_SITE_URL"])
    monkeypatch.setenv("DEMO_SITE_HOST", os.environ["DEMO_SITE_HOST"])
    assert main(["show", "07", "--site-url", "http://localhost:8000/"]) == 0
    assert os.environ["DEMO_SITE_URL"] == "http://localhost:8000" and os.environ["DEMO_SITE_HOST"] == "localhost"
    assert sc.render(sc.find_scenario("07")).url == "http://localhost:8000/claims/new"
