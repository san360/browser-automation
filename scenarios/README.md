# Scenario catalog

Each `*.yaml` file in this folder is one demo scenario. Scenarios run unchanged against the
**prompt agent** (Foundry Browser Automation tool), the **hosted agent** (Agent Framework + Foundry
Toolbox + custom web-analysis tools), and, where it makes sense, the **Computer Use** agent.

| Level | Meaning |
|------:|---------|
| 1 | Simple: navigate, read, extract |
| 2 | Intermediate: filters, multi-page navigation, comparisons, repeated form filling |
| 3 | Advanced: complex multi-step forms with dependent fields and validation recovery |
| 4 | Expert QA: exploratory UI bug hunting, accessibility review, smoke-test execution |
| 5 | Security (passive, owned targets only): page and header review, before/after diff |

## Schema

```yaml
id: 07-file-claim                # unique id (file name without .yaml)
title: File a multi-step claim
level: 3
category: form-filling           # navigation | extraction | form-filling | qa | accessibility | security | research
modes: [prompt, hosted, cua]     # agent modes that support the scenario
url: ${DEMO_SITE_URL}/claims/new # default start URL; override with --url
allowed_domains: []              # optional allow-list; required for security scenarios
inputs:                          # variables for the task template; override with --set key=value
  first_name: Ana
task: |                          # Jinja2 template; {{ url }} and {{ inputs.<name> }} are available
  Go to {{ url }} ...
success_criteria:                # optional automatic checks of the final answer
  - {type: contains, value: "CLM-"}
  - {type: regex, pattern: "CLM-\\d{4}-\\d{5}", capture_as: claim_ref}
  - {type: http_json, url: "${DEMO_SITE_URL}/api/claims/{claim_ref}", expect: {policy_number: CI-100200}}
answer_key: answer-keys/bug-lab.yaml   # optional keyword-based recall score for QA/security scenarios
limits:                          # cost guardrails applied by the runners
  max_output_tokens: 4000
  max_tool_calls: 40
  timeout_seconds: 600
  max_cua_steps: 40
  max_recoveries: 2              # prompt agent: continuations after a failed browser action (ToolTimeout)
```

`${VAR}` and `${VAR:-default}` are expanded from the environment (azd outputs are loaded automatically).
Security scenarios refuse to run unless every target host is in `allowed_domains`, and the demo
site host is the only default entry. Add your own hosts only for systems you own or are authorised to test.
