"""Web console jobs: runs and comparisons in a worker thread, streamed as Server-Sent Events (fake runner)."""

import json
import os
import threading

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from demo_common.settings import Settings  # noqa: E402
from web_console.app import create_app  # noqa: E402
from web_console.local_mirror import ENV_VAR  # noqa: E402
from web_console.sse import coalesce  # noqa: E402
from web_console_fakes import ANSWER, JPEG, LIVE_URL, FakeRunner  # noqa: E402

BASE = "http://127.0.0.1:8765"
SETTINGS = Settings(project_endpoint="https://unit-test.services.ai.azure.com/api/projects/test",
                    demo_site_url="https://demo.contoso.example")


@pytest.fixture
def console(tmp_path):
    runner = FakeRunner(tmp_path)
    app = create_app(settings=SETTINGS, runs_dir=tmp_path, runner=runner, port=8765)
    with TestClient(app, base_url=BASE) as client:
        client.headers.update({"X-Console-Token": client.get("/api/bootstrap").json()["token"], "Origin": BASE})
        client.runner, client.runs_dir, client.app_jobs = runner, tmp_path, app.state.jobs
        yield client


def start(client, **body):
    response = client.post("/api/jobs", json={"scenario_id": "02-site-search", "modes": ["prompt"], **body})
    assert response.status_code == 202, response.text
    return response.json()["job"]


def stream(client, job_id, after=0):
    events = []
    with client.stream("GET", f"/api/jobs/{job_id}/events?after={after}") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
                if events[-1]["kind"] == "job_done":
                    break
    return events


def test_run_streams_events_answer_and_result(console):
    job = start(console)
    assert job["status"] == "running" and job["steps"][0]["model"] == "gpt-4.1-mini"
    events = stream(console, job["id"])
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "step_start" and kinds[-2:] == ["step_done", "job_done"]
    assert {"run_folder", "action", "live_view", "text_delta", "message"} <= set(kinds)
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)
    live = next(e for e in events if e["kind"] == "live_view")
    assert live["url"] == f"{LIVE_URL}-prompt" and LIVE_URL not in live["message"]  # link only in its own field
    assert "".join(e["message"] for e in events if e["kind"] == "text_delta") == ANSWER
    result = next(e for e in events if e["kind"] == "step_done")["result"]
    assert result["status"] == "completed" and result["checks_passed"] == 2 and len(result["checks"]) == 2
    folder = next(e for e in events if e["kind"] == "run_folder")["folder"]
    assert result["folder"] == folder and "run_dir" not in result
    assert result["browser_session_ids"] == ["test-browser-prompt"]
    assert next(e for e in events if e["kind"] == "browser_session")["browserSessionId"] == "test-browser-prompt"
    on_disk = (console.runs_dir / folder / "events.jsonl").read_text(encoding="utf-8")
    assert LIVE_URL not in on_disk and "<live-view-link-redacted>" in on_disk
    assert "test-browser-prompt" in on_disk
    history = console.get(f"/api/history/{folder}").json()
    assert history["result"]["browser_session_ids"] == ["test-browser-prompt"]
    summary = console.get(f"/api/jobs/{job['id']}").json()["job"]
    assert summary["status"] == "completed" and summary["finished"]
    assert console.get("/api/jobs/current").json() == {"job": summary, "active": False}


def test_stream_resumes_after_the_last_event(console):
    job = start(console)
    events = stream(console, job["id"])
    later = stream(console, job["id"], after=events[2]["seq"])
    assert later[0]["seq"] > events[2]["seq"] and later[-1]["kind"] == "job_done"


def test_only_one_run_at_a_time(console):
    console.runner.gate = threading.Event()
    job = start(console)
    busy = console.post("/api/jobs", json={"scenario_id": "05-find-agent", "modes": ["hosted"]})
    assert busy.status_code == 409 and "one runs at a time" in busy.json()["detail"]
    assert console.get("/api/health").json()["busy"] is True
    console.runner.gate.set()
    assert stream(console, job["id"])[-1]["status"] == "completed"
    assert console.get("/api/health").json()["busy"] is False


def test_compare_runs_modes_in_order_and_saves_the_table(console):
    job = start(console, modes=["prompt", "cua", "hosted"], cua_model="gpt-5.4-mini")
    events = stream(console, job["id"])
    assert [c["mode"] for c in console.runner.calls] == ["prompt", "cua", "hosted"]
    done = [e for e in events if e["kind"] == "step_done"]
    assert [(e["step"], e["mode"], e["status"]) for e in done] == [(0, "prompt", "completed"), (1, "cua", "completed"),
                                                                   (2, "hosted", "completed")]
    assert done[1]["result"]["screenshots"] == ["step-001.png", "step-002.png"]
    final = events[-1]
    assert final["comparison"].startswith("compare-") and (console.runs_dir / final["comparison"]).is_file()
    table = (console.runs_dir / final["comparison"]).read_text(encoding="utf-8")
    assert "| cua | gpt-5.4-mini | completed |" in table


def test_stop_after_current_skips_the_remaining_modes(console):
    console.runner.gate = threading.Event()
    job = start(console, modes=["prompt", "hosted"])
    stopped = console.post(f"/api/jobs/{job['id']}/stop", json={})
    assert stopped.json()["job"]["stop_requested"] is True
    console.runner.gate.set()
    final = stream(console, job["id"])[-1]
    assert final["status"] == "stopped" and [s["status"] for s in final["steps"]] == ["completed", "skipped"]
    assert len(console.runner.calls) == 1


def test_another_demo_site_is_used_for_the_whole_run(console):
    job = start(console, scenario_id="07-file-claim", modes=["local"], site_url="http://localhost:8000")
    assert job["url"] == "http://localhost:8000/claims/new" and job["site"] == "http://localhost:8000"
    stream(console, job["id"])
    call = console.runner.calls[0]
    assert call["site"] == "http://localhost:8000" and call["env_site"] == "http://localhost:8000"
    assert os.environ["DEMO_SITE_URL"] == "https://demo.contoso.example"


def test_local_mirror_frames_are_streamed_and_served(console):
    job = start(console, modes=["local"])
    events = stream(console, job["id"])
    frame = next(e for e in events if e["kind"] == "frame")
    assert frame["title"] == "Contoso Insurance" and frame["url"] == "https://demo.contoso.example/"
    image = console.get(f"/api/jobs/{job['id']}/frames/{frame['frame']}", headers={"X-Console-Token": ""})
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg" and image.content == JPEG
    assert console.get(f"/api/jobs/{job['id']}/frames/999").status_code == 404
    assert ENV_VAR not in os.environ  # the init-page hook is only set during local runs
    no_mirror = start(console, modes=["local"], options={"mirror": False})
    assert not [e for e in stream(console, no_mirror["id"]) if e["kind"] == "frame"]


def test_runner_failures_and_invalid_requests_are_reported(console):
    def broken(*args, **kwargs):
        raise RuntimeError("model deployment not found")

    console.app_jobs.runner = broken
    events = stream(console, start(console)["id"])
    assert events[-2]["status"] == "error" and "model deployment not found" in events[-2]["error"]
    assert events[-1]["status"] == "completed"
    assert console.post("/api/jobs", json={"scenario_id": "02-site-search", "modes": ["prompt"],
                                           "prompt_model": "gpt-9"}).status_code == 400
    assert console.post("/api/jobs", json={"scenario_id": "02-site-search", "modes": []}).status_code == 422
    assert console.post("/api/jobs", json={"scenario_id": "02-site-search", "modes": ["cua", "cua"]}).status_code == 422
    blocked = console.post("/api/jobs", json={"scenario_id": "12-passive-security-review", "modes": ["hosted"],
                                              "url": "https://example.com/"})
    assert blocked.status_code == 400 and "allowed_domains" in blocked.json()["detail"]
    assert console.get("/api/jobs/unknown").status_code == 404


def test_text_deltas_are_merged_per_step():
    events = [{"seq": 1, "step": 0, "kind": "text_delta", "message": "a"}, {"seq": 2, "step": 0, "kind": "text_delta",
              "message": "b"}, {"seq": 3, "step": 0, "kind": "action"}, {"seq": 4, "step": 1, "kind": "text_delta",
                                                                          "message": "c"}]
    merged = coalesce(events)
    assert [(e["seq"], e.get("message")) for e in merged] == [(2, "ab"), (3, None), (4, "c")]
