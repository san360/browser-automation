"""Cost estimation for demo runs.

List prices change. Defaults below were taken from the Azure Retail Prices API in October 2026 and are
only used to give the audience an order of magnitude. Override them in pricing.yaml at the repo root.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import yaml

from .settings import REPO_ROOT

DEFAULTS = {
    "currency": "USD",
    # USD per 1M tokens (Global Standard). Data Zone deployments are typically ~10% higher.
    # cached_input applies to prompt-cache hits (input_tokens_details.cached_tokens).
    "models": {
        "gpt-4.1-mini": {"input": 0.40, "cached_input": 0.10, "output": 1.60},
        "gpt-5.4-mini": {"input": 0.75, "cached_input": 0.075, "output": 4.50},
        "gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
        "computer-use-preview": {"input": 3.00, "output": 12.00},
    },
    # Playwright Workspaces (Azure App Testing) cloud browser, Linux, per minute. First 100 minutes free (30-day trial).
    "playwright_per_minute": 0.01,
    "deployment_multiplier": {"DataZoneStandard": 1.1, "GlobalStandard": 1.0},
}


@lru_cache(maxsize=1)
def price_table() -> dict:
    table = {**DEFAULTS, "models": dict(DEFAULTS["models"])}
    override = REPO_ROOT / "pricing.yaml"
    if override.exists():
        data = yaml.safe_load(override.read_text(encoding="utf-8")) or {}
        table["models"].update(data.get("models") or {})
        for key in ("currency", "playwright_per_minute", "deployment_multiplier"):
            if key in data:
                table[key] = data[key]
    return table


@dataclass
class CostEstimate:
    model_cost: float | None
    browser_cost: float
    browser_minutes: int
    currency: str

    @property
    def total(self) -> float | None:
        return None if self.model_cost is None else round(self.model_cost + self.browser_cost, 6)

    def describe(self) -> str:
        model = "n/a" if self.model_cost is None else f"{self.model_cost:.4f}"
        total = "n/a" if self.total is None else f"{self.total:.4f}"
        return (f"model {model} + cloud browser {self.browser_cost:.4f} ({self.browser_minutes} min) = "
                f"{total} {self.currency} (estimate)")


def estimate(model: str | None, input_tokens: int, output_tokens: int, *, browser_seconds: float = 0.0,
             sku: str = "GlobalStandard", cached_tokens: int = 0) -> CostEstimate:
    table = price_table()
    prices = table["models"].get(model or "")
    multiplier = float(table.get("deployment_multiplier", {}).get(sku, 1.0))
    model_cost = None
    if prices:
        cached = min(cached_tokens, input_tokens)
        cached_price = prices.get("cached_input", prices["input"])
        model_cost = round(((input_tokens - cached) * prices["input"] + cached * cached_price
                            + output_tokens * prices["output"]) / 1_000_000 * multiplier, 6)
    minutes = math.ceil(browser_seconds / 60) if browser_seconds > 0 else 0
    return CostEstimate(model_cost=model_cost, browser_cost=round(minutes * float(table["playwright_per_minute"]), 4),
                        browser_minutes=minutes, currency=table["currency"])
