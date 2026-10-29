"""Start the web console:  python -m web_console [--port 8765] [--open]   (also: python -m demo_cli ui)."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import webbrowser

LOOPBACK = ("127.0.0.1", "localhost", "::1")


def port_free(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def stop_child_processes() -> None:
    """Best effort when the console exits mid-run: stop the local agent, Playwright and browsers it started."""
    pid = os.getpid()
    try:
        if os.name == "nt":
            query = f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}').ProcessId"
            out = subprocess.run(["powershell", "-NoProfile", "-Command", query], capture_output=True, text=True,
                                 timeout=30).stdout
            for child in out.split():
                if child.isdigit():
                    subprocess.run(["taskkill", "/PID", child, "/T", "/F"], capture_output=True, check=False)
        else:
            out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, timeout=30).stdout
            for child in out.split():
                subprocess.run(["pkill", "-TERM", "-g", child], capture_output=True, check=False)
                subprocess.run(["kill", "-TERM", child], capture_output=True, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> int:
    try:
        import uvicorn
    except ImportError:
        print('The web console needs FastAPI and uvicorn: pip install -e ".[ui]"', file=sys.stderr)
        return 2
    if not port_free(host, port):
        print(f"Port {port} is already in use on {host}. Start the console with --port <another port>.", file=sys.stderr)
        return 2
    if host not in LOOPBACK:
        print(f"Warning: binding to {host} exposes a console that runs agents on your Azure subscription.",
              file=sys.stderr)
    from .app import create_app

    app = create_app(port=port, bind_host=host)
    url = f"http://{host if host in LOOPBACK else '127.0.0.1'}:{port}/".replace("::1", "[::1]")
    print(f"Foundry Browser Automation console: {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False, server_header=False,
                            timeout_graceful_shutdown=3)
    uvicorn.Server(config).run()
    if app.state.jobs.active is not None:
        stop_child_processes()
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m web_console", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: loopback only)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the console in the default browser")
    args = parser.parse_args(argv)
    return serve(host=args.host, port=args.port, open_browser=args.open)


if __name__ == "__main__":
    raise SystemExit(main())
