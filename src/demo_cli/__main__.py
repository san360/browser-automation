"""Foundry browser automation demo CLI.

Examples
  python -m demo_cli list
  python -m demo_cli show 07 --set first_name=Jo
  python -m demo_cli run 02-site-search --mode prompt
  python -m demo_cli run 07-file-claim --mode hosted
  python -m demo_cli run 05-find-agent --mode local --headed
  python -m demo_cli run 07-file-claim --mode local --site-url http://localhost:8000
  python -m demo_cli run 09-ui-bug-hunt --mode cua --headed
  python -m demo_cli run 01 --url https://learn.microsoft.com/azure/foundry/ --mode prompt
  python -m demo_cli ask --url https://example.com "What is this page about?"
  python -m demo_cli compare 05-find-agent --modes prompt,hosted,cua,local
  python -m demo_cli agents ensure | list | delete
  python -m demo_cli doctor
  python -m demo_cli costs --azure
  python -m demo_cli ui
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from demo_common.reporting import RunResult, load_results
from demo_common.scenarios import (
    RenderedScenario,
    ScenarioError,
    adhoc_scenario,
    enforce_allowlist,
    find_scenario,
    load_catalog,
    parse_overrides,
    render,
)
from demo_common.settings import Settings, get_settings

from .summaries import COMPARISON_COLUMNS, comparison_row, cost_totals, doctor_checks, save_comparison

console = Console()
MODES = ("prompt", "hosted", "cua", "local")


# --------------------------------------------------------------------------- helpers


def _render_from_args(args) -> RenderedScenario:
    scenario = find_scenario(args.scenario)
    rendered = render(scenario, url=args.url, overrides=parse_overrides(args.set))
    enforce_allowlist(rendered)
    return rendered


def _execute(rendered: RenderedScenario, mode: str, settings: Settings, args) -> RunResult:
    if mode not in rendered.scenario.modes and rendered.scenario.id != "adhoc":
        console.print(f"[yellow]Scenario {rendered.scenario.id} is not designed for mode '{mode}' "
                      f"(supported: {', '.join(rendered.scenario.modes)}). Running anyway.[/yellow]")
    console.rule(f"[bold]{rendered.scenario.title}[/bold] · mode={mode}")
    if mode == "prompt":
        from prompt_agent.runner import run_prompt_scenario
        model = getattr(args, "model", None) or (settings.strong_model if getattr(args, "strong", False) else None)
        return run_prompt_scenario(rendered, settings, model=model, console=console)
    if mode == "hosted":
        from demo_cli.hosted_client import run_hosted_scenario
        return run_hosted_scenario(rendered, settings, console=console)
    if mode == "local":
        from demo_cli.local_agent import run_local_scenario
        return run_local_scenario(rendered, settings, remote_browser=getattr(args, "remote_browser", False),
                                  headed=getattr(args, "headed", False), console=console)
    if mode == "cua":
        from computer_use.runner import run_cua_scenario
        return run_cua_scenario(rendered, settings, model=getattr(args, "model", None) or settings.computer_use_model,
                                headless=not getattr(args, "headed", False),
                                remote_browser=getattr(args, "remote_browser", False),
                                auto_ack=getattr(args, "auto_ack", False), console=console)
    raise ScenarioError(f"Unknown mode {mode}")


def _print_answer(result: RunResult) -> None:
    if result.final_text:
        console.rule("Agent answer")
        console.print(Markdown(result.final_text))


# --------------------------------------------------------------------------- commands


def cmd_list(args) -> int:
    table = Table(title="Scenario catalog (scenarios/*.yaml)")
    for col in ("ID", "Level", "Category", "Modes", "Title"):
        table.add_column(col)
    for scenario in load_catalog().values():
        if args.level and scenario.level != args.level:
            continue
        table.add_row(scenario.id, str(scenario.level), scenario.category, ",".join(scenario.modes), scenario.title)
    console.print(table)
    return 0


def cmd_show(args) -> int:
    rendered = _render_from_args(args)
    console.print(f"[bold]{rendered.scenario.title}[/bold]  (level {rendered.scenario.level}, {rendered.scenario.category})")
    console.print(f"Start URL: {rendered.url}")
    if rendered.allowed_domains:
        console.print(f"Allowed domains: {', '.join(rendered.allowed_domains)}")
    console.print(f"Limits: {rendered.limits}")
    console.rule("Task sent to the agent")
    console.print(rendered.task, markup=False)
    return 0


def cmd_run(args) -> int:
    settings = get_settings()
    rendered = _render_from_args(args)
    result = _execute(rendered, args.mode, settings, args)
    _print_answer(result)
    return 0 if result.status == "completed" else 1


def cmd_ask(args) -> int:
    settings = get_settings()
    scenario = adhoc_scenario(args.url, args.task)
    rendered = render(scenario)
    result = _execute(rendered, args.mode, settings, args)
    _print_answer(result)
    return 0 if result.status == "completed" else 1


def cmd_compare(args) -> int:
    settings = get_settings()
    rendered = _render_from_args(args)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    results = [_execute(rendered, mode, settings, args) for mode in modes]
    rows = [comparison_row(r) for r in results]
    table = Table(title=f"Comparison · {rendered.scenario.id}")
    for col in COMPARISON_COLUMNS:
        table.add_column(col)
    for row in rows:
        table.add_row(*row)
    console.print(table)
    out = save_comparison(rendered.scenario.title, rendered.scenario.id, rows)
    console.print(f"Saved {out}")
    return 0


def cmd_agents(args) -> int:
    from prompt_agent.agent import delete_prompt_agents, ensure_prompt_agent, list_demo_agents

    settings = get_settings()
    if args.action == "ensure":
        for model in args.model or [settings.prompt_model]:
            version = ensure_prompt_agent(settings, model)
            console.print(f"[green]Prompt agent ready:[/green] {version.name} v{version.version} (model {model})")
    elif args.action == "list":
        table = Table(title="Agents in the Foundry project")
        for col in ("Name", "Kind", "Latest version", "Model"):
            table.add_column(col)
        for row in list_demo_agents(settings):
            table.add_row(row["name"], str(row["kind"]), str(row["version"]), str(row["model"]))
        console.print(table)
    elif args.action == "delete":
        deleted = delete_prompt_agents(settings, args.model or [settings.prompt_model, settings.strong_model])
        console.print(f"Deleted: {', '.join(deleted) or 'nothing'}")
    return 0


def cmd_doctor(args) -> int:
    ok = True
    for check in doctor_checks(get_settings()):
        ok &= check.passed or check.optional
        mark = "✅" if check.passed else ("➖" if check.optional else "❌")
        console.print(f"{mark} {check.label} {check.detail}")
    return 0 if ok else 1


def cmd_costs(args) -> int:
    table = Table(title="Estimated cost of recorded runs (runs/*/result.json)")
    for col in ("Mode", "Runs", "Tokens in", "Tokens out", "Browser min", "Est. cost"):
        table.add_column(col)
    for mode, t in cost_totals(load_results()).items():
        table.add_row(mode, str(t["runs"]), str(t["in"]), str(t["out"]), str(t["min"]), f"{t['cost']:.4f} {t['cur']}")
    console.print(table)
    if args.azure:
        from demo_cli.costs import month_to_date_by_service

        try:
            for rg, rows in month_to_date_by_service(get_settings()).items():
                azure = Table(title=f"Actual month-to-date cost · {rg} (Cost Management, lags up to 24h)")
                azure.add_column("Service")
                azure.add_column("Cost")
                for service, cost, currency in rows or [("(no charges yet)", 0.0, "")]:
                    azure.add_row(service, f"{cost:.4f} {currency}")
                console.print(azure)
        except Exception as exc:
            console.print(f"[yellow]Cost Management query failed: {exc}[/yellow]")
    return 0


def cmd_runs(args) -> int:
    table = Table(title="Recent runs")
    for col in ("When", "Scenario", "Mode", "Model", "Status", "s", "Checks", "Est. cost", "Folder"):
        table.add_column(col)
    for r in load_results()[-args.last:]:
        folder = Path(r["run_dir"]).name
        cost = "n/a" if r.get("est_cost") is None else f"{r['est_cost']:.4f}"
        table.add_row(folder[:15], r["scenario_id"], r["mode"], r["model"], r["status"], str(r["duration_s"]),
                      f"{r['checks_passed']}/{r['checks_total']}", cost, folder)
    console.print(table)
    return 0


def cmd_ui(args) -> int:
    try:
        from web_console.__main__ import serve
    except ImportError as exc:
        console.print(f"[red]The web console needs its extra: pip install -e \".[ui]\" ({exc})[/red]")
        return 2
    return serve(host=args.host, port=args.port, open_browser=args.open)


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m demo_cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="List scenarios")
    p.add_argument("--level", type=int)
    p.set_defaults(func=cmd_list)

    def scenario_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("scenario", help="Scenario id or numeric prefix, e.g. 07 or 07-file-claim")
        p.add_argument("--url", help="Override the start URL")
        p.add_argument("--set", action="append", metavar="KEY=VALUE", help="Override a scenario input (repeatable)")
        p.add_argument("--site-url", metavar="URL",
                       help="Use another copy of the demo site, e.g. http://localhost:8000 (sets DEMO_SITE_URL/HOST)")

    def runner_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--model", help="Model deployment (prompt: agent model; cua: computer-use model)")
        p.add_argument("--strong", action="store_true", help="Prompt mode: use STRONG_MODEL (gpt-5.4-mini)")
        p.add_argument("--headed", action="store_true", help="Computer Use and local mode: show the local browser window")
        p.add_argument("--remote-browser", action="store_true",
                       help="Browser in Azure. cua: Playwright workspace (access token); local: Browser Automation "
                            "tool through the toolbox")
        p.add_argument("--auto-ack", action="store_true", help="Computer Use: auto-acknowledge safety checks (demo only)")

    p = sub.add_parser("show", help="Render a scenario's task without running it")
    scenario_args(p)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("run", help="Run a scenario")
    scenario_args(p)
    p.add_argument("--mode", choices=MODES, default="prompt")
    runner_args(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("ask", help="Run an ad-hoc task against any URL")
    p.add_argument("task")
    p.add_argument("--url", required=True)
    p.add_argument("--mode", choices=MODES, default="prompt")
    runner_args(p)
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("compare", help="Run one scenario in several modes and compare")
    scenario_args(p)
    p.add_argument("--modes", default="prompt,hosted,cua")
    runner_args(p)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("agents", help="Manage the prompt agent(s)")
    p.add_argument("action", choices=("ensure", "list", "delete"))
    p.add_argument("--model", action="append")
    p.set_defaults(func=cmd_agents)

    p = sub.add_parser("doctor", help="Check configuration and connectivity")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("costs", help="Summarise estimated run costs (and actual Azure spend with --azure)")
    p.add_argument("--azure", action="store_true")
    p.set_defaults(func=cmd_costs)

    p = sub.add_parser("runs", help="List recent runs")
    p.add_argument("--last", type=int, default=20)
    p.set_defaults(func=cmd_runs)

    p = sub.add_parser("ui", help="Start the web console (http://127.0.0.1:8765)")
    p.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: loopback only)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open", action="store_true", help="Open the console in the default browser")
    p.set_defaults(func=cmd_ui)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    site_url = getattr(args, "site_url", None)
    if site_url:
        # Process environment wins over .env and azd values, so every ${DEMO_SITE_URL}/${DEMO_SITE_HOST} follows.
        os.environ["DEMO_SITE_URL"] = site_url.rstrip("/")
        os.environ["DEMO_SITE_HOST"] = urlparse(site_url).hostname or ""
    try:
        return args.func(args)
    except ScenarioError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
