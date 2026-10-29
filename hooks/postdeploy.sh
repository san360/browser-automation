#!/bin/sh
# Post-deploy hook (Linux / macOS): smoke-checks the demo site and ensures the prompt agent exists.
SITE="$(azd env get-value DEMO_SITE_URL 2>/dev/null || true)"
if [ -n "$SITE" ]; then
  if curl -fsS --max-time 60 "$SITE/healthz" >/dev/null; then
    echo "Demo site healthy: $SITE"
  else
    echo "Demo site not responding yet at $SITE/healthz (cold start or not deployed)."
  fi
fi
azd env get-values | grep -E '^AGENT_.*_(NAME|VERSION|RESPONSES_ENDPOINT)=' || true

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -x "$ROOT/.venv/bin/python" ]; then
  echo "Ensuring the prompt agent exists (Browser Automation tool)..."
  (cd "$ROOT" && .venv/bin/python -m demo_cli agents ensure) || true
else
  echo "Tip: create the Python venv (see README) and run 'python -m demo_cli agents ensure'."
fi
