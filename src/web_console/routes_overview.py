"""Environment checks (like `python -m demo_cli doctor`) and cost summaries (like `costs --azure`)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter

from demo_cli.summaries import cost_totals, doctor_checks
from demo_common.reporting import load_results
from demo_common.settings import Settings

AUTH_HINT = ("Reading Azure Cost Management needs Cost Management Reader (or Reader) on the demo resource groups, "
             "and data lags by up to a day.")


def overview_router(settings: Settings, runs_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/doctor")
    def doctor() -> dict:
        checks = [asdict(check) for check in doctor_checks(settings)]
        try:
            from prompt_agent.agent import list_demo_agents

            agents, agents_error = list_demo_agents(settings), None
        except Exception as exc:
            agents, agents_error = [], f"{type(exc).__name__}: {exc}"
        return {"checks": checks, "ok": all(c["passed"] or c["optional"] for c in checks),
                "agents": [{key: str(value) for key, value in row.items()} for row in agents],
                "agents_error": agents_error}

    @router.get("/costs")
    def costs() -> dict:
        results = load_results(runs_dir)

        def rows(key: str) -> list[dict]:
            return sorted(({"key": name, "runs": t["runs"], "input_tokens": t["in"], "output_tokens": t["out"],
                            "browser_minutes": t["min"], "cost": round(t["cost"], 6), "currency": t["cur"]}
                           for name, t in cost_totals(results, key).items()), key=lambda r: -r["cost"])

        passed = sum(1 for r in results if r.get("checks_total") and r["checks_passed"] == r["checks_total"])
        return {
            "by_mode": rows("mode"), "by_scenario": rows("scenario_id"), "by_model": rows("model"),
            "totals": {
                "runs": len(results), "cost": round(sum(r.get("est_cost") or 0.0 for r in results), 6),
                "input_tokens": sum(r["input_tokens"] for r in results),
                "cached_tokens": sum(r.get("cached_tokens", 0) for r in results),
                "output_tokens": sum(r["output_tokens"] for r in results),
                "browser_minutes": sum(r.get("est_browser_minutes", 0) for r in results),
                "all_checks_passed": passed, "with_checks": sum(1 for r in results if r.get("checks_total")),
            },
            "currency": results[-1].get("currency", "USD") if results else "USD",
        }

    @router.get("/costs/azure")
    def azure_costs() -> dict:
        from demo_cli.costs import month_to_date_by_service

        try:
            data = month_to_date_by_service(settings)
        except Exception as exc:  # no permission, not signed in, offline...
            return {"groups": [], "error": f"{type(exc).__name__}: {exc}", "hint": AUTH_HINT}
        groups = []
        for group, rows in data.items():
            errors = [service for service, _, _ in rows if service.startswith("error ")]
            groups.append({"resource_group": group, "error": errors[0] if errors else None,
                           "rows": [{"service": s, "cost": round(c, 6), "currency": cur}
                                    for s, c, cur in rows if not s.startswith("error ")]})
        return {"groups": groups, "error": None, "hint": AUTH_HINT}

    return router
