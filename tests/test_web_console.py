"""Web console API: request guard, catalog, task previews, history and costs (no Azure calls)."""

import os

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from demo_common.reporting import RunRecorder  # noqa: E402
from demo_common.scenarios import CheckResult, find_scenario, render  # noqa: E402
from demo_common.settings import Settings  # noqa: E402
from web_console.app import create_app  # noqa: E402
from web_console_fakes import PNG, FakeRunner  # noqa: E402

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
SECRET = "InstrumentationKey=must-never-reach-the-browser"
SETTINGS = Settings(project_endpoint="https://unit-test.services.ai.azure.com/api/projects/test",
                    demo_site_url="https://demo.contoso.example", browser_connection_id="/x/connections/browserautomation",
                    applicationinsights_connection_string=SECRET, playwright_access_token="pw-secret-token",
                    subscription_id="00000000-0000-0000-0000-000000000001", resource_groups=["rg-a"])


@pytest.fixture
def client(tmp_path):
    app = create_app(settings=SETTINGS, runs_dir=tmp_path, runner=FakeRunner(tmp_path), port=PORT)
    with TestClient(app, base_url=BASE) as test_client:
        token = test_client.get("/api/bootstrap").json()["token"]
        test_client.headers.update({"X-Console-Token": token, "Origin": BASE})
        test_client.runs_dir = tmp_path
        yield test_client


def record_run(runs_dir, scenario="02-site-search", mode="cua", with_shot=True):
    rendered = render(find_scenario(scenario))
    recorder = RunRecorder(rendered, mode, "gpt-5.4-mini", quiet=True, runs_dir=runs_dir)
    recorder.emit("info", "Watch https://live.playwright.microsoft.com/#lv=secret-in-history")
    if with_shot:
        recorder.screenshot(PNG, "start")
    result = recorder.finish("Report within **14 days**.", [CheckResult("contains '14 days'", True),
                                                            CheckResult("regex /a|b/", False, "no match")], None)
    return os.path.basename(result.run_dir)


def test_guard_blocks_other_hosts_origins_sites_and_missing_tokens(client):
    assert client.get("/", headers={"Host": "evil.example:8765"}).status_code == 421
    assert client.get("/api/scenarios", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/scenarios", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/scenarios", headers={"X-Console-Token": "stale"}).status_code == 403
    request = client.build_request("POST", "/api/render", json={"scenario_id": "02-site-search"})
    del request.headers["origin"]
    assert client.send(request).status_code == 403
    assert client.post("/api/render", content="scenario_id=02", headers={"Content-Type": "text/plain"}).status_code == 415
    # A link from another site may open the console itself, but nothing else.
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"}).status_code == 200


def test_bootstrap_exposes_settings_but_no_secrets(client):
    response = client.get("/api/bootstrap")
    body = response.text
    assert SECRET not in body and "pw-secret-token" not in body
    data = response.json()
    assert data["settings"]["demo_site_url"] == "https://demo.contoso.example"
    assert data["settings"]["connection_name"] == "browserautomation"
    assert data["models"]["prompt"] == ["gpt-4.1-mini", "gpt-5.4-mini"] and data["job"] is None


def test_security_headers_on_pages_and_errors(client):
    for response in (client.get("/"), client.get("/api/nope"), client.get("/", headers={"Host": "evil:1"})):
        assert "default-src 'self'" in response.headers["content-security-policy"]
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cross-origin-opener-policy"] == "same-origin-allow-popups"
    assert client.get("/static/js/main.js").headers["cache-control"] == "no-cache"
    assert client.get("/api/scenarios").headers["cache-control"] == "no-store"


def test_catalog_lists_scenarios_with_cards(client):
    scenarios = {s["id"]: s for s in client.get("/api/scenarios").json()["scenarios"]}
    assert len(scenarios) == 14
    claim = scenarios["07-file-claim"]
    assert claim["modes"] == ["prompt", "hosted", "cua", "local"] and claim["level"] == 3
    assert "Result verified through the site API" in claim["checks"]
    assert {"key": "witnesses", "kind": "number"} in claim["inputs"]
    assert scenarios["12-passive-security-review"]["allowed_domains"] == ["${DEMO_SITE_HOST}"]
    assert "{{" not in scenarios["06-quote-calculator"]["summary"]


def test_render_preview_applies_url_and_changed_inputs(client):
    data = client.post("/api/render", json={"scenario_id": "07-file-claim", "inputs": {"first_name": "Jo", "witnesses": 3},
                                            "modes": ["hosted"]}).json()
    assert data["url"] == "https://demo.contoso.example/claims/new"
    assert "Policyholder: Jo Morales" in data["task"] and "(3 witnesses)" in data["task"]
    assert data["defaults"]["first_name"] == "Ana" and data["inputs"]["witnesses"] == 3
    assert data["allowlist_error"] is None and data["warnings"] == []
    yaml_data = client.post("/api/render", json={"scenario_id": "02-site-search", "inputs_yaml": "query: hail damage\n",
                                                 "url": "https://demo.contoso.example/search"}).json()
    assert yaml_data["url"] == "https://demo.contoso.example/search" and '"hail damage"' in yaml_data["task"]
    adhoc = client.post("/api/render", json={"adhoc": {"url": "https://example.com", "task": "Count the links."}}).json()
    assert adhoc["task"].startswith("Start at https://example.com.") and adhoc["scenario_id"] == "adhoc"


def test_render_with_another_demo_site_restores_the_environment(client):
    data = client.post("/api/render", json={"scenario_id": "07-file-claim", "site_url": "http://localhost:8000/",
                                            "modes": ["prompt", "local"]}).json()
    assert data["url"] == "http://localhost:8000/claims/new"
    assert any("cannot reach localhost" in note and "prompt" in note for note in data["warnings"])
    assert os.environ["DEMO_SITE_URL"] == "https://demo.contoso.example"
    assert os.environ["DEMO_SITE_HOST"] == "demo.contoso.example"


def test_render_reports_allow_list_and_input_errors(client):
    blocked = client.post("/api/render", json={"scenario_id": "12-passive-security-review", "url": "https://example.com/"})
    assert blocked.status_code == 200 and "Refusing to run: 'example.com'" in blocked.json()["allowlist_error"]
    bad_yaml = client.post("/api/render", json={"scenario_id": "02-site-search", "inputs_yaml": "query: [unclosed"})
    assert bad_yaml.status_code == 400 and "YAML" in bad_yaml.json()["detail"]
    assert client.post("/api/render", json={"scenario_id": "02-site-search", "inputs_yaml": "- a"}).status_code == 400
    assert client.post("/api/render", json={"scenario_id": "99-nope"}).status_code == 400
    assert client.post("/api/render", json={"scenario_id": "02-site-search", "url": "file:///etc/passwd"}).status_code == 400
    assert client.post("/api/render", json={"adhoc": {"url": "javascript:alert(1)", "task": "x"}}).status_code == 400
    assert client.post("/api/render", json={"scenario_id": "02-site-search", "site_url": "ftp://x"}).status_code == 400
    assert client.post("/api/render", json={"scenario_id": "02-site-search", "unknown": 1}).status_code == 422
    assert client.post("/api/render", json={"scenario_id": "../02"}).status_code == 422


def test_history_lists_runs_and_opens_one(client):
    folder = record_run(client.runs_dir)
    record_run(client.runs_dir, scenario="05-find-agent", mode="prompt", with_shot=False)
    runs = client.get("/api/history").json()["runs"]
    assert [r["scenario_id"] for r in runs] == ["05-find-agent", "02-site-search"]
    detail = client.get(f"/api/history/{folder}").json()
    result = detail["result"]
    assert result["folder"] == folder and result["screenshots"] == ["step-001.png"]
    assert result["checks"] == [{"name": "contains '14 days'", "passed": True, "detail": ""},
                                {"name": "regex /a|b/", "passed": False, "detail": "no match"}]
    assert "secret-in-history" not in str(detail) and detail["events"][0]["kind"] == "info"
    assert "Report within **14 days**." in detail["report"]
    image = client.get(f"/api/history/{folder}/files/step-001.png", headers={"X-Console-Token": ""})
    assert image.status_code == 200 and image.headers["content-type"] == "image/png" and image.content == PNG


@pytest.mark.parametrize("path", [
    "/api/history/..%2F..%2Fpyproject.toml", "/api/history/..", "/api/history/%2E%2E",
    "/api/history/20261026-000000-x/files/step-001.png", "/api/history/{folder}/files/result.json",
    "/api/history/{folder}/files/..%2Fresult.json", "/api/history/{folder}/files/step-001.png%00.txt",
    "/api/history/{folder}/files/STEP-001.PNG", "/api/history/{folder}/files/report.md",
])
def test_history_files_cannot_escape_the_run_folder(client, path):
    folder = record_run(client.runs_dir)
    (client.runs_dir / "secret.txt").write_text("nope", encoding="utf-8")
    response = client.get(path.replace("{folder}", folder))
    assert response.status_code in (404, 422) and "nope" not in response.text


def test_costs_totals_and_azure_errors(client, monkeypatch):
    record_run(client.runs_dir)
    record_run(client.runs_dir, mode="prompt")
    data = client.get("/api/costs").json()
    assert data["totals"]["runs"] == 2 and {r["key"] for r in data["by_mode"]} == {"cua", "prompt"}
    assert data["totals"]["with_checks"] == 2 and data["totals"]["all_checks_passed"] == 0

    import demo_cli.costs as costs

    def denied(settings):
        raise PermissionError("AuthorizationFailed: no access to Cost Management")

    monkeypatch.setattr(costs, "month_to_date_by_service", denied)
    azure = client.get("/api/costs/azure").json()
    assert azure["groups"] == [] and "AuthorizationFailed" in azure["error"] and "Reader" in azure["hint"]
    monkeypatch.setattr(costs, "month_to_date_by_service", lambda s: {"rg-a": [("error 403: denied", 0.0, "")],
                                                                      "rg-b": [("Container Apps", 1.5, "USD")]})
    groups = {g["resource_group"]: g for g in client.get("/api/costs/azure").json()["groups"]}
    assert groups["rg-a"]["error"] == "error 403: denied" and groups["rg-b"]["rows"][0]["cost"] == 1.5
