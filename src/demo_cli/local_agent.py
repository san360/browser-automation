"""Local mode: run the hosted agent's code (src/hosted_agent) on this machine.

For each run the launcher starts `main.py` with the hosted agent's virtual environment, bound to 127.0.0.1 on a free
port, calls it over the Responses protocol exactly like the deployed agent, and then stops it together with its whole
process tree (Node.js, Playwright MCP and the browser).

* Default browser: Playwright MCP on this machine (Edge on Windows), so the agent can reach localhost and intranet
  sites, and no Playwright Workspaces minutes are used. Needs Node.js (npx).
* remote_browser=True: the same local agent uses the Foundry Browser Automation tool through the toolbox (cloud
  browser), which is handy for debugging the hosted agent before `azd deploy`.

The model, and the toolbox when used, stay in your Foundry project.
"""

from __future__ import annotations

import collections
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import openai
from rich.console import Console

from demo_common.reporting import RunRecorder, RunResult, redact
from demo_common.responses_stream import consume_stream, create_with_fallback
from demo_common.scenarios import RenderedScenario, evaluate, score_answer_key
from demo_common.settings import REPO_ROOT, Settings

HOSTED_AGENT_DIR = REPO_ROOT / "src" / "hosted_agent"
READY_TIMEOUT_S = 120


class LocalAgentError(RuntimeError):
    pass


def agent_python() -> Path:
    """Python of the hosted agent's virtual environment (override with LOCAL_AGENT_PYTHON)."""
    override = os.getenv("LOCAL_AGENT_PYTHON")
    if override:
        return Path(override)
    venv = HOSTED_AGENT_DIR / ".venv"
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def setup_hint() -> str:
    return ("Create the hosted agent's environment first:\n"
            "  py -3.11 -m venv src/hosted_agent/.venv   (python3 -m venv on macOS/Linux)\n"
            "  src/hosted_agent/.venv/Scripts/python -m pip install -r src/hosted_agent/requirements.txt\n"
            "The local browser also needs Node.js 18+ (npx).")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def allowed_origins(rendered: RenderedScenario) -> list[str]:
    """Origins for Playwright MCP's --allowed-origins, only for scenarios that declare a domain allow-list."""
    if not rendered.allowed_domains:
        return []
    start = urlparse(rendered.url)
    origins = {f"{start.scheme}://{start.netloc}"} if start.scheme and start.netloc else set()
    for host in rendered.allowed_domains:
        origins.update({f"https://{host}", f"http://{host}"})
    return sorted(origins)


def server_env(settings: Settings, rendered: RenderedScenario, *, model: str, port: int, remote_browser: bool,
               headed: bool, output_dir: str, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    hosts = [host for host in [settings.demo_site_host, *rendered.allowed_domains] if host]
    env.update({
        "FOUNDRY_PROJECT_ENDPOINT": settings.project_endpoint,
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": model,
        "BROWSER_BACKEND": "toolbox" if remote_browser else "local",
        "AGENT_HOST": "127.0.0.1",
        "PORT": str(port),
        "DEMO_SITE_URL": settings.demo_site_url,
        "ALLOWED_SCAN_HOSTS": ",".join(dict.fromkeys(hosts)),
        # Keep prompts, page content and tool results out of telemetry, and keep local runs out of the shared
        # Application Insights (an empty value also stops load_dotenv from restoring it from .env).
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "",
        "LOCAL_BROWSER_HEADLESS": "false" if headed else "true",
        "LOCAL_BROWSER_OUTPUT_DIR": output_dir,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    })
    if settings.subscription_id:
        # The agent uses the Azure CLI account that owns this subscription, whatever the CLI's default account is.
        env["AZURE_CLI_SUBSCRIPTION"] = settings.subscription_id
    if remote_browser:
        env["TOOLBOX_NAME"] = settings.toolbox_name
    else:
        origins = allowed_origins(rendered)
        if origins:
            env["LOCAL_BROWSER_ALLOWED_ORIGINS"] = ";".join(origins)
    return env


class LocalAgentServer:
    """The hosted agent's server as a child process; output goes to a redacted log file."""

    def __init__(self, env: dict[str, str], port: int, log_path: Path) -> None:
        self.env = env
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self.log_path = log_path
        self.proc: subprocess.Popen | None = None
        self._tail: collections.deque[str] = collections.deque(maxlen=40)
        self._reader: threading.Thread | None = None

    def __enter__(self) -> "LocalAgentServer":
        python = agent_python()
        if not python.exists():
            raise LocalAgentError(f"Hosted agent environment not found ({python}).\n{setup_hint()}")
        kwargs: dict = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        self.proc = subprocess.Popen(
            [str(python), "main.py"], cwd=HOSTED_AGENT_DIR, env=self.env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", **kwargs,
        )
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        try:
            self._wait_ready()
        except BaseException:
            self.stop()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        with self.log_path.open("w", encoding="utf-8") as log:
            for line in self.proc.stdout:
                clean = redact(line)
                log.write(clean)
                self._tail.append(clean.rstrip())

    def tail(self) -> str:
        return "\n".join(self._tail)

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise LocalAgentError(f"The local agent exited with code {self.proc.returncode}:\n{self.tail()}")
            try:
                if httpx.get(f"{self.url}/readiness", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise LocalAgentError(f"The local agent was not ready after {READY_TIMEOUT_S}s:\n{self.tail()}")

    def stop(self) -> None:
        """Stop the server and everything it started (npx, Node.js, the browser)."""
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False)
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        if self._reader:
            self._reader.join(timeout=5)


def run_local_scenario(rendered: RenderedScenario, settings: Settings, *, remote_browser: bool = False,
                       headed: bool = False, console: Console | None = None, listeners=None,
                       quiet: bool = False) -> RunResult:
    model = os.getenv("HOSTED_AGENT_MODEL", settings.prompt_model)
    recorder = RunRecorder(rendered, "local", model, console=console, listeners=listeners, quiet=quiet)
    final_text, status, error = "", "completed", None
    started = time.monotonic()
    output_dir = tempfile.mkdtemp(prefix="web-qa-agent-playwright-")
    browser = "Azure (Browser Automation tool via the toolbox)" if remote_browser else "this machine (Playwright MCP)"
    try:
        port = free_port()
        env = server_env(settings, rendered, model=model, port=port, remote_browser=remote_browser, headed=headed,
                         output_dir=output_dir)
        recorder.emit("info", f"Starting the hosted agent's code locally · browser: {browser}")
        with LocalAgentServer(env, port, recorder.dir / "local-agent.log") as server:
            recorder.emit("info", f"Local agent ready on {server.url} (server log: local-agent.log)")
            client = openai.OpenAI(base_url=server.url, api_key="local-dev",
                                   timeout=float(rendered.limits.timeout_seconds), max_retries=0)
            stream = create_with_fallback(client, {"input": rendered.task, "stream": True},
                                          {"max_output_tokens": rendered.limits.max_output_tokens}, recorder)
            outcome = consume_stream(stream, recorder)
            final_text, status, error = outcome.text, outcome.status, outcome.error
    except Exception as exc:
        status, error = "failed", f"{type(exc).__name__}: {exc}"
        recorder.emit("error", error[:1500])
        recorder.note_content_filter(error)
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
    checks = evaluate(rendered, final_text) if final_text else []
    score = score_answer_key(rendered.scenario, final_text) if final_text else None
    # A local browser costs nothing; with the cloud browser the session time is billed like the hosted agent's.
    return recorder.finish(final_text, checks, score, status=status, error=error,
                           browser_seconds=(time.monotonic() - started) if remote_browser else 0.0)
