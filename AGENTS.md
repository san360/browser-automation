# Agent instructions

This project was built with the microsoft-foundry skill. Before working on or answering questions about foundry agents, read the microsoft-foundry skill first.

- Hosted agent code lives in `src/hosted_agent` (deployed by `azd deploy web-qa-agent`); the prompt agent is created by
  `python -m demo_cli agents ensure` (azure-ai-projects SDK) and the Computer Use loop lives in `src/computer_use`.
- Local mode (`--mode local`, `src/demo_cli/local_agent.py`) runs `src/hosted_agent/main.py` on 127.0.0.1 with its own
  venv; `BROWSER_BACKEND` selects the Foundry Toolbox (default, the only option in Foundry) or Playwright MCP (local
  only, needs Node.js). Keep `instructions.md` backend-specific text inside `<!-- browser:NAME -->` blocks.
- Infrastructure uses azd layers: `infra/foundry` (generated, microsoft.foundry provider) and `infra/platform` (Bicep).
- Use azd's identity (`azd auth token`) in scripts; the Azure CLI may be signed in to another tenant. Python code uses
  `demo_common.settings.get_credential()`, which picks the Azure CLI account that owns `AZURE_SUBSCRIPTION_ID`.
- Hosted agent gotchas: keep `FoundryToolbox(..., tool_result_content="content_first")` (snapshots live in `content`),
  never rewrite the response text stream in middleware, and keep `usage_fix.apply()` until
  agent-framework-foundry-hosting honours cumulative (`merge_mode="replace"`) usage. Verify token usage against the
  Application Insights `gen_ai.usage.*` spans or Azure Monitor `InputTokens` metrics, not only the API response.
- Computer Use calls the account-level `/openai/v1` endpoint (project endpoint rejects large screenshot outputs).
- The web console (`src/web_console`, `python -m web_console`) is FastAPI + vanilla ES modules with no build step and a
  250-line ceiling per `.py`/`.js` file. It reuses the runners, `demo_common` and `demo_cli.summaries` instead of
  duplicating them, builds untrusted text with `textContent` (or `static/js/markdown.js`) never `innerHTML`, and must
  never display, log or persist the signed live-view link (it only navigates the live-view window).
- Run `python -m pytest -q` after changes; browser tests need `python -m playwright install chromium`.
