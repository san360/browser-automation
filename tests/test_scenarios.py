"""Tests for the scenario catalog, templating, allow-list and scoring."""

import pytest

from demo_common import scenarios as sc


def test_catalog_loads_all_scenarios():
    catalog = sc.load_catalog()
    assert len(catalog) >= 14
    for scenario in catalog.values():
        assert scenario.task.strip()
        assert set(scenario.modes) <= {"prompt", "hosted", "cua", "local"}
        # Local mode runs the hosted agent's code, so it follows the hosted mode.
        assert ("local" in scenario.modes) == ("hosted" in scenario.modes)
        assert 1 <= scenario.level <= 5


@pytest.mark.parametrize("key", ["07", "07-file-claim"])
def test_find_and_render(key):
    rendered = sc.render(sc.find_scenario(key), overrides={"first_name": "Jo"})
    assert rendered.url == "https://demo.contoso.example/claims/new"
    assert "Jo Morales" in rendered.task
    assert "{{" not in rendered.task


def test_url_override_and_nested_template():
    rendered = sc.render(sc.find_scenario("10"), url="https://demo.contoso.example/bug-lab/claims/new")
    assert "https://demo.contoso.example/bug-lab/claims/new (beta claim form" in rendered.task
    assert "https://demo.contoso.example/ (home page)" in rendered.task


def test_env_expansion_with_default(monkeypatch):
    monkeypatch.delenv("NOT_SET_VAR", raising=False)
    assert sc.expand_env("${NOT_SET_VAR:-fallback}/x") == "fallback/x"
    assert sc.expand_env({"a": ["${DEMO_SITE_HOST}"]}) == {"a": ["demo.contoso.example"]}


def test_security_scenarios_enforce_allow_list():
    scenario = sc.find_scenario("12")
    sc.enforce_allowlist(sc.render(scenario))  # demo host is allowed
    with pytest.raises(sc.ScenarioError):
        sc.enforce_allowlist(sc.render(scenario, url="https://www.example.org/"))


def test_parse_overrides():
    assert sc.parse_overrides(["witnesses=3", "phone=+1 555"]) == {"witnesses": 3, "phone": "+1 555"}
    with pytest.raises(sc.ScenarioError):
        sc.parse_overrides(["oops"])


def test_evaluate_regex_contains_and_capture(monkeypatch):
    rendered = sc.render(sc.find_scenario("07"))

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"policy_number": "CI-100200", "estimated_amount": 1250.5, "witness_count": 2}

    monkeypatch.setattr(sc.httpx, "get", lambda url, timeout: FakeResponse())
    results = sc.evaluate(rendered, "Done. Your claim reference is CLM-2026-01234.")
    assert all(r.passed for r in results), results


def test_answer_key_scoring():
    scenario = sc.find_scenario("09")
    report = ("Travel policies show an empty coverage dropdown. Submitting returns 404 Not Found. "
              "The close button of the cookie banner does nothing. Hint text has low contrast.")
    score = sc.score_answer_key(scenario, report)
    assert {"BL-05", "BL-10", "BL-01", "BL-12"} <= set(score.found)
    assert 0 < score.recall < 1
