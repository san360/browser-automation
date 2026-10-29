"""Tests for cost estimation and run reporting."""

import json

import pytest

from demo_common import pricing
from demo_common.reporting import REDACTED_EMAIL, RunRecorder, redact
from demo_common.scenarios import CheckResult, find_scenario, render


def test_estimate_known_model():
    cost = pricing.estimate("gpt-4.1-mini", 1_000_000, 100_000, browser_seconds=61)
    assert cost.model_cost == pytest.approx(0.40 + 0.16)
    assert cost.browser_minutes == 2
    assert cost.total == pytest.approx(0.56 + 0.02)


def test_estimate_unknown_model_is_na():
    assert pricing.estimate("some-new-model", 10, 10).total is None


def test_estimate_prices_cached_tokens_at_cached_rate():
    # 1M input of which 800K cached: 200K x 0.40 + 800K x 0.10 + 0 output = 0.08 + 0.08
    cost = pricing.estimate("gpt-4.1-mini", 1_000_000, 0, cached_tokens=800_000)
    assert cost.model_cost == pytest.approx(0.16)
    # Data Zone deployments apply the multiplier to every meter
    dz = pricing.estimate("gpt-5.4-mini", 1_000_000, 0, cached_tokens=1_000_000, sku="DataZoneStandard")
    assert dz.model_cost == pytest.approx(0.0825)
    # Models without a cached price fall back to the input price; cached can never exceed input
    cua = pricing.estimate("computer-use-preview", 1_000, 0, cached_tokens=5_000)
    assert cua.model_cost == pytest.approx(0.003)


def test_recorder_writes_artifacts(tmp_path):
    rendered = render(find_scenario("02"))
    seen: list[dict] = []
    recorder = RunRecorder(rendered, "prompt", "gpt-4.1-mini", quiet=True, runs_dir=tmp_path, listeners=[seen.append])
    recorder.action("browser_navigate", {"url": rendered.url, "browserSessionId": "secret-session"})
    recorder.detect_live_view("Watch here: https://live.playwright.microsoft.com/#lv=abc123")
    recorder.emit("message", "Live view: [open](https://westeurope.liveview.playwright.microsoft.com/abc?sig=x)")
    recorder.add_usage({"input_tokens": 1000, "output_tokens": 200, "input_tokens_details": {"cached_tokens": 600}})
    result = recorder.finish("Answer with https://westeurope.liveview.playwright.microsoft.com/abc?sig=x link",
                             [CheckResult("contains", True)], None, browser_seconds=30)
    assert result.status == "completed" and result.checks_passed == 1
    assert result.cached_tokens == 600
    saved = json.loads((recorder.dir / "result.json").read_text(encoding="utf-8"))
    assert "liveview" not in saved["final_text"]  # live-view links are redacted from artifacts
    events = (recorder.dir / "events.jsonl").read_text(encoding="utf-8")
    assert "secret-session" in events
    assert saved["browser_session_ids"] == ["secret-session"]
    assert "secret-session" in (recorder.dir / "report.md").read_text(encoding="utf-8")
    assert "#lv=" not in events and "liveview" not in events  # signed links never reach disk
    assert any(e.get("url") == "https://live.playwright.microsoft.com/#lv=abc123" for e in seen)  # but the UI gets it
    assert "liveview" not in (recorder.dir / "report.md").read_text(encoding="utf-8")


def test_live_view_detection_ignores_docs_links(tmp_path):
    recorder = RunRecorder(render(find_scenario("02")), "prompt", "gpt-4.1-mini", quiet=True, runs_dir=tmp_path)
    recorder.detect_live_view("See https://playwright.dev/docs/intro for details")
    assert recorder.live_view_url is None


@pytest.mark.parametrize("email", ["person@example.org", "first.last+demo@example.co.uk",
                                  "USER@EXAMPLE.COM", "o'brien@example.org"])
def test_redact_email(email):
    assert redact(f"Authentication failed for '{email}'.") == f"Authentication failed for '{REDACTED_EMAIL}'."
    assert redact(f"Contact {email}.") == f"Contact {REDACTED_EMAIL}."


def test_recorder_redacts_emails_on_every_text_artifact(tmp_path):
    from dataclasses import replace

    email = "person@example.org"
    rendered = replace(render(find_scenario("02")), task=f"Contact {email}")
    recorder = RunRecorder(rendered, "prompt", "gpt-4.1-mini", quiet=True, runs_dir=tmp_path)
    recorder.emit("error", f"Authentication failed for {email}", detail={"account": email})
    result = recorder.finish(f"Contact {email}", [CheckResult("contains", False, email)], None,
                             status="failed", error=f"Authentication failed for {email}")
    assert email not in result.final_text
    assert email not in result.error
    for name in ("task.md", "events.jsonl", "result.json", "report.md"):
        text = (recorder.dir / name).read_text(encoding="utf-8")
        assert email not in text
        assert REDACTED_EMAIL in text
    json.loads((recorder.dir / "result.json").read_text(encoding="utf-8"))
    for line in (recorder.dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        json.loads(line)


def test_browser_sessions_capture_results_arguments_and_recoveries(tmp_path):
    seen = []
    recorder = RunRecorder(render(find_scenario("02")), "hosted", "gpt-4.1-mini", quiet=True,
                           runs_dir=tmp_path, listeners=[seen.append])
    recorder.detect_browser_session(json.dumps({"content": [{"type": "text", "text": json.dumps({
        "browserSessionId": "browser-1", "liveViewUrl": "https://live.playwright.microsoft.com/#lv=secret",
    })}]}))
    recorder.action("browser_navigate", {"browserSessionId": "browser-1", "url": "https://example.com"})
    recorder.detect_browser_session({"structuredContent": {"browserSessionId": "browser-2"}})
    for output in ("not JSON", None, {"browserSessionId": 123}, {"browserSessionId": ""}, "42"):
        recorder.detect_browser_session(output)
    result = recorder.finish("done", [], None)
    assert result.browser_session_ids == ["browser-1", "browser-2"]
    assert [e["browserSessionId"] for e in seen if e["kind"] == "browser_session"] == ["browser-1", "browser-2"]
    assert recorder.actions[0]["arguments"]["browserSessionId"] == "browser-1"
    assert "secret" not in (recorder.dir / "events.jsonl").read_text(encoding="utf-8")
