"""Scenario catalog: loading, templating, allow-list enforcement, success checks and answer-key scoring."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml
from jinja2 import Environment, StrictUndefined

from .settings import SCENARIOS_DIR, load_environment

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::?-([^}]*))?\}")
_URL_IN_TEXT = re.compile(r"https?://[^\s)\"'<>]+")
_jinja = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)


def expand_env(value: Any) -> Any:
    """Expand ${VAR} and ${VAR:-default} recursively using the merged environment."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1)) or (m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


@dataclass
class Limits:
    max_output_tokens: int = 4000
    max_tool_calls: int = 40
    timeout_seconds: int = 600
    max_cua_steps: int = 60
    # Prompt agent: how many times to continue after a failed browser action (ToolTimeout ends the response).
    max_recoveries: int = 2


def with_local_mode(modes) -> list[str]:
    """Local mode runs the hosted agent's code on this machine, so it supports every scenario the hosted agent does."""
    result = list(modes)
    if "hosted" in result and "local" not in result:
        result.append("local")
    return result


@dataclass
class Scenario:
    id: str
    title: str
    level: int
    category: str
    modes: list[str]
    url: str
    task: str
    inputs: dict[str, Any] = field(default_factory=dict)
    allowed_domains: list[str] = field(default_factory=list)
    success_criteria: list[dict[str, Any]] = field(default_factory=list)
    answer_key: str | None = None
    limits: Limits = field(default_factory=Limits)
    description: str = ""
    source: Path | None = None

    @classmethod
    def from_file(cls, path: Path) -> "Scenario":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            id=data["id"],
            title=data["title"],
            level=int(data.get("level", 1)),
            category=data.get("category", "navigation"),
            modes=with_local_mode(data.get("modes", ["prompt", "hosted", "cua"])),
            url=data.get("url", ""),
            task=data["task"],
            inputs=dict(data.get("inputs") or {}),
            allowed_domains=list(data.get("allowed_domains") or []),
            success_criteria=list(data.get("success_criteria") or []),
            answer_key=data.get("answer_key"),
            limits=Limits(**(data.get("limits") or {})),
            description=data.get("description", ""),
            source=path,
        )


@dataclass
class RenderedScenario:
    scenario: Scenario
    url: str
    task: str
    inputs: dict[str, Any]
    allowed_domains: list[str]

    @property
    def limits(self) -> Limits:
        return self.scenario.limits


class ScenarioError(Exception):
    pass


def load_catalog(directory: Path = SCENARIOS_DIR) -> dict[str, Scenario]:
    catalog = {}
    for path in sorted(directory.glob("*.yaml")):
        scenario = Scenario.from_file(path)
        catalog[scenario.id] = scenario
    return catalog


def find_scenario(key: str, catalog: dict[str, Scenario] | None = None) -> Scenario:
    catalog = catalog or load_catalog()
    if key in catalog:
        return catalog[key]
    matches = [s for sid, s in catalog.items() if sid.startswith(key) or sid.split("-", 1)[0] == key.zfill(2)]
    if len(matches) == 1:
        return matches[0]
    raise ScenarioError(f"Unknown scenario '{key}'. Use `python -m demo_cli list`.")


def parse_overrides(pairs: list[str] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ScenarioError(f"Override '{pair}' must look like key=value")
        key, value = pair.split("=", 1)
        result[key.strip()] = yaml.safe_load(value) if value.strip() else ""
    return result


def adhoc_scenario(url: str, task: str, *, category: str = "navigation") -> Scenario:
    return Scenario(id="adhoc", title="Ad-hoc task", level=0, category=category, modes=["prompt", "hosted", "cua", "local"],
                    url=url, task="Start at {{ url }}.\n" + task)


def render(scenario: Scenario, *, url: str | None = None, overrides: dict[str, Any] | None = None) -> RenderedScenario:
    load_environment()
    start_url = url or expand_env(scenario.url)
    if not start_url:
        raise ScenarioError(f"Scenario {scenario.id} has no URL; pass --url.")
    inputs = expand_env(dict(scenario.inputs))
    inputs.update(overrides or {})
    context = {"url": start_url}
    rendered_inputs = {
        k: _jinja.from_string(v).render(**context) if isinstance(v, str) and "{{" in v else v for k, v in inputs.items()
    }
    task = _jinja.from_string(scenario.task).render(url=start_url, inputs=rendered_inputs).strip()
    allowed = [d for d in expand_env(scenario.allowed_domains) if d]
    return RenderedScenario(scenario=scenario, url=start_url, task=task, inputs=rendered_inputs, allowed_domains=allowed)


def host_allowed(host: str, allowed: list[str]) -> bool:
    host = (host or "").lower()
    for entry in allowed:
        entry = entry.lower()
        if entry.startswith("*.") and (host == entry[2:] or host.endswith(entry[1:])):
            return True
        if host == entry:
            return True
    return False


def enforce_allowlist(rendered: RenderedScenario) -> None:
    """Security scenarios (or scenarios with allowed_domains) may only target allow-listed hosts."""
    needs_check = rendered.scenario.category == "security" or bool(rendered.scenario.allowed_domains)
    if not needs_check:
        return
    if not rendered.allowed_domains:
        raise ScenarioError(
            "This scenario requires an allow-list but it resolved empty. Run `azd provision` (DEMO_SITE_HOST) "
            "or add your own authorised host to allowed_domains."
        )
    for target in [rendered.url, *_URL_IN_TEXT.findall(rendered.task)]:
        host = urlparse(target).hostname or ""
        if not host_allowed(host, rendered.allowed_domains):
            raise ScenarioError(
                f"Refusing to run: '{host}' is not in allowed_domains {rendered.allowed_domains}. "
                "Only test systems you own or are authorised to test."
            )


# --------------------------------------------------------------------------- success checks


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def evaluate(rendered: RenderedScenario, final_text: str, *, timeout: float = 20.0) -> list[CheckResult]:
    results: list[CheckResult] = []
    captures: dict[str, str] = {}
    text = final_text or ""
    for criterion in rendered.scenario.success_criteria:
        kind = criterion.get("type")
        if kind == "contains":
            value = str(criterion["value"])
            results.append(CheckResult(f"contains '{value}'", value.lower() in text.lower()))
        elif kind == "regex":
            match = re.search(criterion["pattern"], text)
            if match and criterion.get("capture_as"):
                captures[criterion["capture_as"]] = match.group(0)
            results.append(CheckResult(f"regex /{criterion['pattern']}/", bool(match), match.group(0) if match else ""))
        elif kind == "min_length":
            results.append(CheckResult(f"answer length >= {criterion['value']}", len(text) >= int(criterion["value"]), f"{len(text)} chars"))
        elif kind == "http_json":
            results.append(_check_http_json(criterion, captures, timeout))
        else:
            results.append(CheckResult(f"unknown check '{kind}'", False, "unsupported"))
    return results


def _check_http_json(criterion: dict, captures: dict[str, str], timeout: float) -> CheckResult:
    template = expand_env(criterion["url"])
    try:
        url = template.format(**captures)
    except KeyError as missing:
        return CheckResult(f"verify via API {template}", False, f"no value captured for {missing}")
    try:
        response = httpx.get(url, timeout=timeout)
        data = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return CheckResult(f"verify via API {url}", False, f"request failed: {exc}")
    if response.status_code != 200:
        return CheckResult(f"verify via API {url}", False, f"HTTP {response.status_code}")
    mismatches = []
    for key, expected in (criterion.get("expect") or {}).items():
        actual = data.get(key)
        same = abs(float(actual) - float(expected)) < 0.01 if isinstance(expected, (int, float)) and actual is not None else str(actual).lower() == str(expected).lower()
        if not same:
            mismatches.append(f"{key}: expected {expected!r}, got {actual!r}")
    return CheckResult(f"verify via API {url}", not mismatches, "; ".join(mismatches) or "record matches")


# --------------------------------------------------------------------------- answer keys (heuristic recall)


@dataclass
class AnswerKeyScore:
    found: list[str]
    missed: list[str]
    titles: dict[str, str]

    @property
    def total(self) -> int:
        return len(self.found) + len(self.missed)

    @property
    def recall(self) -> float:
        return len(self.found) / self.total if self.total else 0.0


def score_answer_key(scenario: Scenario, text: str) -> AnswerKeyScore | None:
    if not scenario.answer_key:
        return None
    path = (scenario.source.parent if scenario.source else SCENARIOS_DIR) / scenario.answer_key
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    lowered = (text or "").lower()
    found, missed, titles = [], [], {}
    for issue in data.get("issues", []):
        titles[issue["id"]] = issue["title"]
        groups = issue.get("match_all_groups", [])
        hit = bool(groups) and all(any(keyword.lower() in lowered for keyword in group) for group in groups)
        (found if hit else missed).append(issue["id"])
    return AnswerKeyScore(found=found, missed=missed, titles=titles)
