"""Turn console requests into rendered scenarios by reusing demo_common.scenarios (render, ad-hoc, allow-list)."""

from __future__ import annotations

import ipaddress
import os
import re
import threading
from contextlib import contextmanager
from dataclasses import asdict
from urllib.parse import urlparse

import yaml
from jinja2 import TemplateError

from demo_common.scenarios import RenderedScenario, Scenario, ScenarioError, adhoc_scenario, render
from demo_common.settings import Settings

from .schemas import RenderRequest

SITE_KEYS = ("DEMO_SITE_URL", "DEMO_SITE_HOST")
# render() and the API checks at the end of every run read ${DEMO_SITE_URL} from os.environ, so an override for another
# copy of the demo site is process-wide: a job holds this lock (and the override) from its first step to its last.
ENV_LOCK = threading.RLock()
CHECK_LABELS = {
    "contains": lambda c: f"Answer contains “{c.get('value')}”",
    "regex": lambda c: f"Answer matches /{c.get('pattern')}/",
    "min_length": lambda c: f"Answer has at least {c.get('value')} characters",
    "http_json": lambda c: "Result verified through the site API",
}


def site_override(value: str | None, settings: Settings) -> str | None:
    """Validate a demo-site target. None means the deployed site (DEMO_SITE_URL)."""
    if not value or not value.strip():
        return None
    site = value.strip().rstrip("/")
    parsed = urlparse(site)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.query or parsed.fragment:
        raise ScenarioError("The demo-site target must be an http(s) URL such as http://localhost:8000.")
    return None if site == settings.demo_site_url else site


@contextmanager
def demo_site(site: str | None):
    """Point ${DEMO_SITE_URL}/${DEMO_SITE_HOST} at another copy of the demo site, like the CLI's --site-url."""
    if not site:
        yield
        return
    with ENV_LOCK:
        saved = {key: os.environ.get(key) for key in SITE_KEYS}
        os.environ["DEMO_SITE_URL"] = site
        os.environ["DEMO_SITE_HOST"] = urlparse(site).hostname or ""
        try:
            yield
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def http_url(value: str, what: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ScenarioError(f"{what} must be an http(s) URL.")
    return value


def parse_inputs(req: RenderRequest) -> dict:
    if req.inputs_yaml is not None:
        try:
            data = yaml.safe_load(req.inputs_yaml) or {}
        except yaml.YAMLError as exc:
            raise ScenarioError(f"The inputs YAML is not valid: {exc}") from exc
        if not isinstance(data, dict):
            raise ScenarioError("The inputs YAML must be a mapping of input names to values.")
        return {str(key): value for key, value in data.items()}
    return dict(req.inputs or {})


def scenario_for(req: RenderRequest, catalog: dict[str, Scenario]) -> Scenario:
    if req.adhoc:
        return adhoc_scenario(http_url(req.adhoc.url, "The URL"), req.adhoc.task.strip())
    if not req.scenario_id:
        raise ScenarioError("Pick a scenario or describe an ad-hoc task.")
    if req.scenario_id not in catalog:
        raise ScenarioError(f"Unknown scenario '{req.scenario_id}'.")
    return catalog[req.scenario_id]


def render_request(req: RenderRequest, catalog: dict[str, Scenario]) -> tuple[RenderedScenario, dict]:
    """Render with the request's start URL and input overrides; also return the default inputs for comparison."""
    scenario = scenario_for(req, catalog)
    url = http_url(req.url, "The start URL") if req.url and req.url.strip() else None
    try:
        defaults = render(scenario, url=url).inputs
        rendered = render(scenario, url=url, overrides=parse_inputs(req))
    except TemplateError as exc:
        raise ScenarioError(f"The task template could not be rendered: {exc}") from exc
    http_url(rendered.url, "The start URL")
    return rendered, defaults


def is_private_host(host: str) -> bool:
    host = (host or "").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def warnings_for(rendered: RenderedScenario, modes: list[str], *, remote_browser: bool = False,
                 overrides: dict | None = None) -> list[str]:
    scenario, notes = rendered.scenario, []
    unsupported = [m for m in modes if m not in scenario.modes]
    if unsupported and scenario.id != "adhoc":
        notes.append(f"{scenario.id} is not designed for {', '.join(unsupported)} "
                     f"(supported: {', '.join(scenario.modes)}); it runs anyway.")
    host = urlparse(rendered.url).hostname or ""
    cloud = [m for m in modes if m in ("prompt", "hosted") or (m == "local" and remote_browser)]
    if cloud and is_private_host(host):
        notes.append(f"Cloud browsers ({', '.join(cloud)}) cannot reach {host}: use local mode with the browser "
                     "on this PC, or Computer Use.")
    unknown = sorted(set(overrides or {}) - set(scenario.inputs))
    if unknown and scenario.id != "adhoc":
        notes.append(f"Unknown inputs are ignored by the task template: {', '.join(unknown)}.")
    return notes


class _BlockDumper(yaml.SafeDumper):
    pass


_BlockDumper.add_representer(str, lambda dumper, value: dumper.represent_scalar(
    "tag:yaml.org,2002:str", value, style="|" if "\n" in value else None))


def inputs_yaml(inputs: dict) -> str:
    return yaml.dump(inputs, Dumper=_BlockDumper, sort_keys=False, allow_unicode=True) if inputs else ""


def preview(rendered: RenderedScenario, defaults: dict, notes: list[str], allowlist_error: str | None) -> dict:
    return {
        "scenario_id": rendered.scenario.id, "url": rendered.url, "task": rendered.task, "inputs": rendered.inputs,
        "defaults": defaults, "inputs_yaml": inputs_yaml(rendered.inputs), "allowed_domains": rendered.allowed_domains,
        "limits": asdict(rendered.limits), "warnings": notes, "allowlist_error": allowlist_error,
    }


def input_kind(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "text" if "\n" in value or len(value) > 70 else "string"
    return "yaml"


def summary(scenario: Scenario) -> str:
    """The task's opening sentences with template placeholders replaced, for scenario cards."""
    text = re.sub(r"\{\{\s*url\s*\}\}", "the start page", scenario.task)
    text = re.sub(r"\{\{\s*inputs\.(\w+)\s*\}\}", lambda m: str(scenario.inputs.get(m.group(1), m.group(1))), text)
    text = re.sub(r"\$\{DEMO_SITE_URL[^}]*\}", "the demo site", text)
    text = " ".join(re.sub(r"\{[{%#].*?[}%#]\}", "", text).split())
    sentences = re.split(r"(?<=[.!?:])\s", text)
    result = sentences[0]
    for sentence in sentences[1:]:
        if len(result) >= 70 or len(result) + len(sentence) > 220:
            break
        result = f"{result} {sentence}"
    return result if len(result) <= 220 else result[:219] + "…"


def scenario_card(scenario: Scenario) -> dict:
    return {
        "id": scenario.id, "title": scenario.title, "level": scenario.level, "category": scenario.category,
        "modes": scenario.modes, "url_template": scenario.url, "summary": summary(scenario),
        "description": scenario.description, "allowed_domains": scenario.allowed_domains,
        "inputs": [{"key": key, "kind": input_kind(value)} for key, value in scenario.inputs.items()],
        "checks": [CHECK_LABELS.get(c.get("type"), lambda c: f"Check: {c.get('type')}")(c)
                   for c in scenario.success_criteria],
        "answer_key": bool(scenario.answer_key), "limits": asdict(scenario.limits),
    }
