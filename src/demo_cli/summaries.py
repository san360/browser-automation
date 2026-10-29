"""Summaries shared by the CLI and the web console: environment checks, cost totals and mode comparisons."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from pathlib import Path

import httpx

from demo_common.settings import RUNS_DIR, Settings


@dataclass
class Check:
    label: str
    passed: bool
    detail: str = ""
    optional: bool = False  # optional checks (local mode) never fail the doctor


def doctor_checks(settings: Settings) -> Iterator[Check]:
    """Configuration and connectivity checks, yielded one by one (the demo site may take a minute to wake up)."""
    yield Check("FOUNDRY_PROJECT_ENDPOINT", bool(settings.project_endpoint), settings.project_endpoint)
    yield Check("Browser Automation connection id", bool(settings.browser_connection_id),
                settings.browser_connection_id.rsplit("/", 1)[-1])
    yield Check("Demo site URL", bool(settings.demo_site_url), settings.demo_site_url)
    if settings.demo_site_url:
        try:
            health = httpx.get(f"{settings.demo_site_url}/healthz", timeout=60).json()
            yield Check("Demo site healthy", health.get("status") == "ok", json.dumps(health))
        except Exception as exc:
            yield Check("Demo site healthy", False, str(exc))
    try:
        from prompt_agent.agent import project_client

        client = project_client(settings)
        connection = client.connections.get(settings.browser_connection_id.rsplit("/", 1)[-1])
        yield Check("Project reachable + connection", True, f"{connection.name} ({connection.type})")
        names = [a.name for a in client.agents.list()]
        yield Check("Hosted agent deployed", settings.hosted_agent_name in names, settings.hosted_agent_name)
        yield Check("Prompt agent exists", settings.prompt_agent_name in names,
                    f"{settings.prompt_agent_name} (created on first run)")
    except Exception as exc:
        yield Check("Project reachable", False, f"{type(exc).__name__}: {exc}")
    try:
        import playwright  # noqa: F401

        yield Check("Playwright installed (Computer Use)", True)
    except ImportError:
        yield Check("Playwright installed (Computer Use)", False,
                    "pip install playwright && python -m playwright install chromium")
    yield from local_mode_checks()


def local_mode_checks() -> Iterator[Check]:
    """Local mode is optional: report its prerequisites without failing the doctor."""
    from demo_cli.local_agent import agent_python

    python = agent_python()
    yield Check("Local mode: hosted agent environment", python.exists(),
                str(python) if python.exists() else "(optional) see README · Local mode", optional=True)
    npx, node = shutil.which("npx"), shutil.which("node")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=False).stdout.strip() if node else ""
    yield Check("Local mode: Node.js / npx (local browser)", bool(npx and node),
                version or "(optional) install Node.js 18+", optional=True)


def cost_totals(results: Iterable[Mapping], key: str = "mode") -> dict[str, dict]:
    """Totals of recorded runs (runs/*/result.json) grouped by `key` (mode, scenario_id or model)."""
    totals: dict[str, dict] = {}
    for r in results:
        t = totals.setdefault(r[key], {"runs": 0, "in": 0, "out": 0, "min": 0, "cost": 0.0,
                                       "cur": r.get("currency", "USD")})
        t["runs"] += 1
        t["in"] += r["input_tokens"]
        t["out"] += r["output_tokens"]
        t["min"] += r.get("est_browser_minutes", 0)
        t["cost"] += r.get("est_cost") or 0.0
    return totals


COMPARISON_COLUMNS = ("Mode", "Model", "Status", "Duration (s)", "Tool calls", "Tokens in/out", "Checks", "Answer key",
                      "Est. cost")


def comparison_row(result) -> list[str]:
    """One comparison table row for a RunResult (or its dict form)."""
    r = asdict(result) if is_dataclass(result) else dict(result)
    cost = "n/a" if r["est_cost"] is None else f"{r['est_cost']:.4f} {r['currency']}"
    key = "-" if r["answer_key_recall"] is None else f"{r['answer_key_recall']:.0%}"
    return [r["mode"], r["model"], r["status"], f"{r['duration_s']}", str(r["tool_calls"]),
            f"{r['input_tokens']}/{r['output_tokens']}", f"{r['checks_passed']}/{r['checks_total']}", key, cost]


def save_comparison(title: str, scenario_id: str, rows: list[list[str]], runs_dir: Path = RUNS_DIR) -> Path:
    """Write the comparison as Markdown to runs/compare-<timestamp>-<scenario>.md."""
    lines = [f"# Comparison: {title}", "", "| " + " | ".join(COMPARISON_COLUMNS) + " |",
             "|" + "---|" * len(COMPARISON_COLUMNS)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    runs_dir.mkdir(exist_ok=True)
    out = runs_dir / f"compare-{datetime.now():%Y%m%d-%H%M%S}-{scenario_id}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
