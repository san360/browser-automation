# 04 · Cost management

Running this demo costs very little, but browser agents spend money in several places at once: **model tokens** (page
snapshots are text the model reads), **cloud browser minutes** in Azure Playwright Workspaces, **hosted agent compute**
while sessions are active, and a small amount of **fixed infrastructure** (container registry, log ingestion). This page
lists every cost component and the price used for estimates, works through real numbers measured in this repo, explains
the levers that keep spend down (model choice, scenario limits, snapshots instead of screenshots, local mode for
development, scale to zero, the log cap, budgets, the Playwright free trial, closing sessions, deleting agent versions,
`azd down --purge`), shows how to
see actual spend, and ends with a cleanup checklist. Prices are list prices from October 2026. Check them against your
agreement before quoting anyone.

**On this page:** [Cost model](#cost-model-per-component) · [How runs are estimated](#how-the-demo-estimates-a-run) ·
[Worked examples](#worked-examples) · [Levers](#levers) · [See actual spend](#see-actual-spend) · [Cleanup](#cleanup-checklist)

---

## Cost model per component

| Component | You pay for | Price used for estimates | Idle cost | This repo's setting |
|---|---|---|---|---|
| **Model tokens: `gpt-4.1-mini`** | Input, cached input and output tokens, including snapshot text the model reads | Per 1M tokens: Global $0.40 input / **$0.10 cached** / $1.60 output. Data Zone $0.44 / $0.11 / $1.76. | None | Default for the prompt and hosted agents. GlobalStandard, 300K TPM (capacity is a rate limit, not a cost). |
| **Model tokens: `gpt-5.4-mini`** | Same, plus reasoning tokens, which count as output | Per 1M tokens: Global $0.75 / **$0.075 cached** / $4.50. Data Zone $0.825 / $0.0825 / $4.95. | None | `--strong` and Computer Use. DataZoneStandard, 300K TPM. |
| **Model tokens: `computer-use-preview`** | Text and screenshot tokens | $3 / $12 per 1M (Global Standard). Regional $3.63 / $13.20, Data Zone $3.30 / $13.20. | None | Not deployed. Optional, needs approved access. |
| **Browser Automation tool** | Nothing extra | No separate tool fee ([cost considerations](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/browser-automation#cost-considerations)) | None | |
| **Playwright Workspaces cloud browser** | Browser minutes, by OS | About $0.01 per Linux minute (Windows is higher). This price needs checking: the Retail Prices API returned $0.00 at query time. 30-day free trial with 100 browser minutes. | None (pay per minute) | One workspace, West Europe, `localAuth` disabled |
| **Local mode browser** (`--mode local`) | Nothing: Edge or Chrome on your PC, driven by the open-source Playwright MCP server | Free | None | `--remote-browser` uses the cloud browser, and its minutes, instead |
| **Prompt agents, toolbox, connections** | Nothing beyond model and tool usage | | None | `browser-automation-agent` (plus `-gpt-5-4-mini`) |
| **Hosted agent compute** | vCPU-hours and GiB-hours while sessions are active | Not publicly listed at the time of writing. Check Cost Management after a run. | Scales to zero after the idle timeout (default 15 min, configurable from 2 to 240 min) | `web-qa-agent`, 0.5 vCPU / 1 GiB |
| **Container Apps (demo site)** | vCPU and memory seconds while replicas run (consumption plan) | Calculator (verify) | **$0 at `minReplicas: 0`**, at the price of a cold start | 0.25 vCPU / 0.5 GiB per replica, 0 to 2 replicas (`DEMO_SITE_MIN_REPLICAS`) |
| **Container Registry (Basic)** | A fixed daily rate | About $5 per month (verify) | Yes, the only real fixed cost | `cr<token>`, holds the demo-site image (azd remote build) |
| **Log Analytics + Application Insights** | Ingested GB (pay-as-you-go), retention | Standard per-GB ingestion (verify for your region) | Small: only what gets ingested | Daily cap **1 GB** (`LOG_ANALYTICS_DAILY_CAP_GB`), 30-day retention |
| **Image builds** | The demo-site build runs in ACR (`remoteBuild: true`). The hosted agent uses a platform-managed remote build. | Small, per build (verify) | None | Only on `azd deploy` |
| **Budget** | Nothing | Free | None | Alerts at 50% and 90% (actual) and 100% (forecast) of `BUDGET_AMOUNT` (default 100) |

Model prices were verified with the Azure Retail Prices API (Sweden Central, USD, October 2026). Cached input is 75%
cheaper than normal input for `gpt-4.1-mini` and 90% cheaper for `gpt-5.4-mini`, which matters a lot for long browser
runs ([example 4](#4-measured-hosted-agent-07-file-claim-a-long-client-side-loop)).

Pricing sources: [Foundry Models (Azure OpenAI)](https://azure.microsoft.com/pricing/details/ai-foundry-models/aoai/),
[Azure App Testing / Playwright Workspaces](https://azure.microsoft.com/pricing/details/app-testing/),
[Foundry Agent Service](https://azure.microsoft.com/pricing/details/foundry-agent-service/), and the
[Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices).
The pricing pages are rendered client-side, so query the Retail Prices API for exact numbers.

> **Budgets alert; they don't cap spending.** The only hard stops in this repo are the scenario limits, the log
> ingestion cap and `azd down`.

---

## How the demo estimates a run

Every run ends with a line such as
`model 0.0042 + cloud browser 0.0100 (1 min) = 0.0141 USD (estimate)`. It comes from
[`src/demo_common/pricing.py`](../src/demo_common/pricing.py), and you can override the prices in
[`pricing.yaml`](../pricing.yaml).

```text
model cost   = ((input_tokens - cached_tokens) × input_price + cached_tokens × cached_input_price
                + output_tokens × output_price) / 1,000,000 × deployment multiplier
               (GlobalStandard 1.0, DataZoneStandard 1.1)
browser cost = ceil(browser seconds / 60) × playwright_per_minute (0.01)
```

- **Cached input.** Prompt-cache hits (`input_tokens_details.cached_tokens`) are priced at `cached_input` from
  `pricing.yaml`: $0.10 per 1M for `gpt-4.1-mini` and $0.075 for `gpt-5.4-mini` (Global; the Data Zone multiplier of
  1.1 is applied on top). Multi-step browser runs resend the same prefix on every turn, so most input tokens are often
  cached. The run summary shows `Tokens (in/cached/out)`. A `pricing.yaml` entry replaces the whole default entry for
  that model, so if you edit one, keep `cached_input`, or cached tokens are priced as normal input.
- **Tokens** come from the `usage` object of `response.completed`. **A failed response reports no usage at all**, yet
  its model turns were consumed and are billed: `responses.retrieve(<id>)` on a failed response returns
  `status: failed` and `usage: None`. For exact consumption, use Azure Monitor metrics ([see actual spend](#see-actual-spend)).
- **Hosted agent usage** was over-reported about 10 to 12 times by a framework bug
  (`agent-framework-foundry-hosting` 1.0.0b261015 added up cumulative usage snapshots). `src/hosted_agent/usage_fix.py`
  corrects it, and reported usage now equals the Application Insights sums. This and the other
  [known issues of the preview hosting stack](01-browser-automation-tool.md#6-known-issues-in-the-current-preview-hosting-stack)
  have workarounds in `src/hosted_agent`. Hosted-mode files in `runs/` created before
  13:15 UTC on 2026-10-26 still carry the inflated numbers, so don't use them for cost.
- **Browser seconds.** Prompt and hosted runs use the whole run duration. That's an upper bound for the active session,
  but it doesn't cover a session the model leaves open (see the next point). It also counts a minute when the agent
  used no browser at all, as in example 5. Computer Use with the local browser counts 0 browser minutes, and so does
  local mode; with `--remote-browser`, local mode counts the run duration, like the hosted agent.
- **Unclosed sessions.** In the measured run the model never called `close_browser_session`. If browser minutes accrue
  until the 15-minute idle timeout, such a session could bill up to about 15 extra minutes, roughly $0.15 (verify how
  idle sessions are metered). That's why both instruction files tell the agent to close the session.
- **Not included in the estimate:** hosted agent compute, fixed infrastructure, log ingestion. Use
  `python -m demo_cli costs --azure` for those.
- A model missing from the price table shows `n/a`. Add it to `pricing.yaml`.

---

## Worked examples

All examples except 7 and 10 are measured runs on this deployment.

### 1. Measured: scenario `02-site-search`, prompt agent, `gpt-4.1-mini`

37 s, 8 browser actions, 8,324 input / 513 output tokens, both checks passed.

| Item | Calculation | Cost |
|---|---|---|
| Input tokens | 8,324 × $0.40 / 1M | $0.0033 |
| Output tokens | 513 × $1.60 / 1M | $0.0008 |
| **Model** | | **$0.0042** |
| Browser | ceil(37 s / 60) = 1 min × $0.01 | $0.0100 |
| **Total** | | **≈ $0.014** |

The browser minute costs more than the model. Inside the free trial's 100 minutes, the run costs about **$0.004**.
This measurement predates cached-token tracking and prices all input at the full rate. If part of the input was a
prompt-cache hit ($0.10 instead of $0.40 per 1M), the real model cost was lower.

### 2. Measured: failed responses report no usage

On the first, failed attempt at `02`, the model guessed a CSS selector, `browser_fill_form` hit a `ToolTimeout`, and
the platform failed the response after about 110 s, after 4 actions.

| Item | Calculation | Cost |
|---|---|---|
| Model | consumed and billed, but `usage` is `None` on a failed response | not reported (see Azure Monitor metrics) |
| Browser | ceil(110 s / 60) = 2 min × $0.01 | $0.0200 |
| **Total (estimated)** | | **≥ $0.02** |

The same thing happened on `05-find-agent` in the validation environment: the first response made 8 browser calls,
then `browser_wait_for` hit a `ToolTimeout`. `responses.retrieve(<id>)` returned `status: failed`,
`error.code: tool_user_error` and `usage: None` (16 output items). The runner recovered with `previous_response_id`
(7,415 input, 5,632 of them cached, and 110 output tokens) and the run passed 2/2 in 89.3 s with 9 tool calls. The
reported tokens cover only the recovery response: the 8 model turns of the failed response are billed but appear in no
API usage.

**Failures cost more than they show.** Ref-only targeting, a fresh `browser_snapshot` instead of `browser_wait_for`
with text, and bounded recovery are cost controls as much as reliability fixes. For real consumption, use Azure Monitor
metrics or Cost Management.

### 3. Measured: the same scenario with Computer Use, `gpt-5.4-mini` (Data Zone)

23.4 s, 5 actions (screenshot, click, type, click, click), 19,978 input tokens of which 12,544 cached, 221 output,
2/2 checks. The browser ran locally, so there are no browser minutes.

| Item | Calculation | Cost |
|---|---|---|
| Uncached input | 7,434 × $0.825 / 1M | $0.0061 |
| Cached input | 12,544 × $0.0825 / 1M | $0.0010 |
| Output | 221 × $4.95 / 1M | $0.0011 |
| **Total** | | **≈ $0.008** |

Cheaper and faster than the prompt agent on the same task, but the answer contained an **invented article URL**: the
model only sees pixels, and a headless viewport shows no address bar. Cheap isn't the same as correct
([03](03-computer-use-vs-browser-automation.md#measured-the-same-task-both-ways)). On `05-find-agent`, all three modes
cost between about $0.014 and $0.018 per run (same section).

### 4. Measured: hosted agent, `07-file-claim`, a long client-side loop

The 4-step claim wizard is the most complex task in the catalog. On the hosted agent (`gpt-4.1-mini`, external tenant,
after the usage fix) it took **133.6 s, 27 tool calls and 28 model calls**. Reported usage was 204,393 input tokens
(178,560 cached, 87%) and 1,401 output, exactly the Application Insights sums. Both checks passed: the claim
`CLM-2026-21403` was verified through the site API.

| Item | Calculation | Cost |
|---|---|---|
| Uncached input | 25,833 × $0.40 / 1M | $0.010 |
| Cached input | 178,560 × $0.10 / 1M | $0.018 |
| Output | 1,401 × $1.60 / 1M | $0.002 |
| **Model** | | **≈ $0.030** |
| Browser | ceil(133.6 s / 60) = 3 min × $0.01 | $0.03 |
| **Total** (excluding hosted compute) | | **≈ $0.06** |

What shaped that number (true token counts from Application Insights, validation environment):

| Configuration | Model calls | Input tokens | Output tokens | Largest context per call |
|---|---|---|---|---|
| All 22 browser tools, no compaction | 27 | 223,930 | 1,425 | 12,373 |
| 15-tool allow-list (`BROWSER_TOOLS`) + compaction (48,000-token budget) | 24 | 174,538 | 1,659 | 11,212 |

Individual runs vary: the reference run above made 28 model calls, this optimised validation run 24.

Lessons:

- The Agent Framework loop runs client-side and resends the full context on every model call, but Browser Automation
  snapshots are compact: the context stayed between about 3K and 12K tokens per call.
- The **tool allow-list** cut input tokens by 22%, through smaller tool schemas on every call and fewer calls.
  **Compaction never triggered**; keep it as a safety net for long runs.
- **Prompt caching** cut the model cost by about 64%: without it, the same tokens would cost about $0.084. Cached input
  is 75% cheaper on `gpt-4.1-mini` and 90% cheaper on `gpt-5.4-mini`.
- At this size, **browser minutes are half the bill**. The levers are the allow-list, step limits (`max_tool_calls`,
  `max_cua_steps`), a smaller model and closing sessions promptly.
- Before the usage fix, the hosted agent reported about 10 to 12 times these token counts. Hosted runs in `runs/` from
  before 13:15 UTC on 2026-10-26 carry those inflated numbers.
- Measure long tasks in both modes before choosing a default:
  `python -m demo_cli compare 07 --modes prompt,hosted`. The prompt agent's loop runs server-side in Agent Service.

### 5. Measured: hosted agent, security scenarios (`12`, `13`)

`12-passive-security-review`: 38 s, 3 tool calls (only the deterministic HTTP tools, no browser session), 9,663 input
tokens (5,376 cached) and 1,770 output, 2/2 checks, 12 of the 13 planted issues found (recall 0.92).

| Item | Calculation | Cost |
|---|---|---|
| Uncached input | 4,287 × $0.40 / 1M | $0.0017 |
| Cached input | 5,376 × $0.10 / 1M | $0.0005 |
| Output | 1,770 × $1.60 / 1M | $0.0028 |
| **Model** | | **$0.0051** |
| Browser (as estimated) | ceil(38 s / 60) = 1 min × $0.01 | $0.0100 |
| **Total (estimate)** | | **≈ $0.015** |

The estimate counts one browser minute because it uses the run's duration. This run never opened a browser session,
so the real cost was about $0.005 plus hosted compute.

`13-security-before-after` (compare the insecure page with its hardened twin): 42.0 s, 4 tool calls, 9,911 input tokens
(2,560 cached) and 819 output, 2/2 checks, **≈ $0.0145** (about $0.0045 in model tokens plus the estimated browser
minute).

### 6. Measured: the same task on `gpt-5.4-mini` (`--strong`)

After the ref-copy fix ([01](01-browser-automation-tool.md#copy-refs-exactly-frame-prefixes)), `02-site-search` on the
prompt agent with `gpt-5.4-mini` (Data Zone) took 23.2 s, 7,615 input / 554 output tokens, 2/2 checks.

| Item | Calculation | Cost |
|---|---|---|
| Input tokens | 7,615 × $0.825 / 1M | $0.0063 |
| Output tokens | 554 × $4.95 / 1M | $0.0027 |
| **Model** | | **$0.0090** |
| Browser | ceil(23.2 s / 60) = 1 min × $0.01 | $0.0100 |
| **Total** | | **≈ $0.019** |

For similar token counts, the model cost about 2.1 times as much as `gpt-4.1-mini` in example 1 ($0.0090 against
$0.0042), and reasoning tokens are billed as output. It was faster here (23.2 s against 37 s). Use it (`--strong`) for
short, reasoning-heavy scenarios such as `03`, `04` and `13`, not everywhere: on a long prompt-mode loop it hit repeated
429s even at 300K TPM ([example 8](#8-measured-09-ui-bug-hunt-on-a-deliberately-broken-ui)).

### 7. `computer-use-preview`: why step limits matter (upper bound)

Computer Use sends a screenshot on every step, and the context grows across the `previous_response_id` chain until
`truncation="auto"` drops older items. For the preview model, its context limits give a hard upper bound per call:

| `computer-use-preview` | Calculation | Upper bound |
|---|---|---|
| One step (full 8,192-token context, 1,024 output tokens) | 8,192 × $3 / 1M + 1,024 × $12 / 1M | **$0.037** |
| 20 steps | 20 × $0.037 | $0.74 |
| Scenario `09` cap (`max_cua_steps: 120`) | 120 × $0.037 | $4.42 |

### 8. Measured: `09-ui-bug-hunt` on a deliberately broken UI

The beta claim wizard has 12 planted defects, and several controls simply don't respond. These runs, in order, shaped
the current code and guidance:

| Run | Result | What happened |
|---|---|---|
| Hosted agent v3, before the fixes | **Failed** after 224.6 s, 7 tool calls | Three browser actions on defective controls each ended in a `ToolTimeout` after about 60 s. Agent Framework then hit its default of 3 consecutive tool errors, stopped tool calls and asked for a final answer, and the server failed with the divergent-text-snapshot error ([known issues](01-browser-automation-tool.md#6-known-issues-in-the-current-preview-hosting-stack)). |
| Hosted agent v4, with `text_projection_fix.py` and `MAX_CONSECUTIVE_TOOL_ERRORS=6` | Stopped by **429** after 359 s, 42 tool calls, 5 of 12 defects reported | The divergent-text failure didn't recur. The run then hit "Model deployment rate limit exceeded", because the prompt-mode `09` ran at the same time on the same 100K-TPM deployment and every call also reserves `max_output_tokens` (5,000 for `09`). Fix: capacity 300K TPM. |
| Prompt agent, 2 recoveries | **Failed** after 243.8 s, 14 tool calls, 1/2 checks, **0 tokens reported** | Three `ToolTimeout`s (two `browser_wait_for` on text, one `browser_click` on a defective control) used up the 2 recoveries. Every response failed, so no usage was reported at all, although the model turns were billed. Fixes: `limits.max_recoveries: 6` for `09`, and instructions to take a snapshot instead of waiting for text and to move on after two failures on the same element. |
| **Hosted agent v5** (the new instructions), run alone at 300K TPM | **Completed** in 646 s, 40 tool calls, 1/2 checks, **5 of 12** defects (answer-key recall 0.42), **≈ $0.16** | No divergent-text failure and no 429. It found the Travel-only defect (first check), but its report mentioned no 404, so the second check failed. |
| Prompt agent (`gpt-4.1-mini`), new instructions, 6 recoveries | **Completed** in 81.5 s, 17 tool calls, 1/2 checks, **1 of 12** defects, ≈ $0.026 | 11,481 input tokens (2,304 cached) and 1,226 output. The model ended its turn with a plan (*"I will now bypass this issue by switching the claim type …"*) instead of carrying it out. |
| Prompt agent with `--strong` (`gpt-5.4-mini`) | Repeated **429**s at 300K TPM; used up its 6 recoveries | Azure Monitor showed only about 17K to 26K input tokens per minute on the deployment. The agent service's server-side loop makes each internal model call reserve its output budget against the TPM limit, and `PromptAgentDefinition` has no `max_output_tokens` field, so that reservation can't be capped from the agent. The runner's backoff (20 s × attempt, at most 60 s) worked, but didn't save the run. |

The completed hosted run (`gpt-4.1-mini`, Global, external tenant):

| Item | Calculation | Cost |
|---|---|---|
| Uncached input | 41,776 × $0.40 / 1M | $0.0167 |
| Cached input | 322,048 × $0.10 / 1M (88% of the 363,824 input tokens) | $0.0322 |
| Output | 3,071 × $1.60 / 1M | $0.0049 |
| **Model** | | **≈ $0.054** |
| Browser | ceil(646 s / 60) = 11 min × $0.01 | $0.11 |
| **Total** (excluding hosted compute) | | **≈ $0.16** |

What this means for cost and planning:

- **Time is the cost driver.** Browser minutes are two thirds of that bill, because each defective control burns about
  a minute of `ToolTimeout`: browser time (and hosted compute) spent waiting. For comparison, the working 4-step wizard
  (`07`) takes 134 s and costs about $0.06.
- **Reported tokens can't be trusted for failed runs.** A run made only of failed responses reports zero tokens. Use
  Azure Monitor metrics for the real consumption ([see actual spend](#see-actual-spend)).
- **Capacity is a rate limit, not a cost.** Both deployments are pay-per-token, so a larger capacity costs nothing
  extra. It keeps long or parallel runs from failing with 429, but even
  300K TPM didn't make `--strong` work for a long prompt-mode loop. Use `gpt-4.1-mini` or the hosted agent there.
- **Exploratory QA needs a long-running loop.** The hosted agent, with its client-side loop and stronger instructions,
  reported 5 of 12 defects; the prompt agent stopped after 17 tool calls with 1. Expect partial recall in a single
  pass. For more, run several focused runs (one per wizard step) instead of `--strong` in prompt mode.

### 9. Measured: local mode, browser on the PC

Local mode runs the hosted agent's code on your PC, with Edge driven by Playwright MCP, so there are **no browser
minutes**: you pay for model tokens only ([01](01-browser-automation-tool.md#local-mode-the-hosted-agents-code-on-your-pc)).

`07-file-claim` against a copy of the demo site on `http://localhost:8000` (`gpt-4.1-mini`): 46.6 s, 17 tool calls,
211,018 input tokens (189,952 cached) and 598 output, 2/2 checks, with the claim verified through the local API.

| Item | Calculation | Cost |
|---|---|---|
| Uncached input | 21,066 × $0.40 / 1M | $0.0084 |
| Cached input | 189,952 × $0.10 / 1M | $0.0190 |
| Output | 598 × $1.60 / 1M | $0.0010 |
| **Model** | | **≈ $0.028** |
| Browser | Local browser | $0 |
| **Total** | | **≈ $0.028** |

| `07-file-claim` | Hosted agent, cloud browser ([example 4](#4-measured-hosted-agent-07-file-claim-a-long-client-side-loop)) | Local mode, browser on the PC |
|---|---|---|
| Time | 133.6 s | 46.6 s |
| Tool calls | 27 | 17 |
| Input tokens (cached) | 204,393 (178,560) | 211,018 (189,952) |
| Estimated cost | ≈ $0.06, half of it browser minutes | ≈ $0.028, tokens only |

- **Tokens stay about the same.** It's the same client-side loop, and the prompt cache serves most of the input in both
  runs.
- **Browser minutes disappear.** The run was also faster and needed fewer tool calls, partly because there's no session
  to create or close and page-changing actions already return a fresh snapshot.
- **`02-site-search`** in local mode: 39 s, 3 tool calls, 20,033 input tokens (8,704 cached) and 234 output, ≈ $0.006,
  2/2 (an earlier run: 29 s, 4 tool calls, ≈ $0.005). The prompt agent pays about $0.014 for the same task, most of it
  for the browser minute.
- **`--remote-browser`** brings the cloud browser back, and the run's duration counts as browser minutes again.

### 10. Planning a demo day (estimate)

- **Short runs** such as `02`, `05` or `12` cost about $0.01 to $0.02 each, mostly the browser minute. In local mode
  they cost tokens only (`02`: about $0.006).
- **The 4-step wizard** (`07`) on the hosted agent costs about $0.06. `09` on the broken wizard took 646 s and about
  $0.16 on the hosted agent, two thirds of it browser minutes. Run it on its own, or show a recorded run.
- A **45-minute track** of about 10 runs lands around $0.10 to $0.30 in model tokens plus 15 to 30 browser minutes
  ($0.15 to $0.30, or free within the trial): well under $1 in total.
- **Fixed:** about $5 per month for the Basic registry, plus whatever logs you ingest (capped at 1 GB per day). Add the
  replica cost if you raise `DEMO_SITE_MIN_REPLICAS` to 1 for the day.
- After a rehearsal, check the real numbers with `python -m demo_cli costs` and cross-check them against Azure Monitor
  metrics ([see actual spend](#see-actual-spend)).

---

## Levers

| Lever | Where | Default | Effect |
|---|---|---|---|
| **Model choice** | `PROMPT_AGENT_MODEL`, `--strong`, `HOSTED_AGENT_MODEL`, `COMPUTER_USE_MODEL` | `gpt-4.1-mini` | `gpt-5.4-mini` costs about 1.9× per input token and 2.8× per output token, plus about 10% for Data Zone. In prompt mode, keep it for short, reasoning-heavy scenarios (`03`, `04`, `13`): on a long loop it hit 429s even at 300K TPM (example 8). |
| **Output and tool-call caps** | `limits.max_output_tokens`, `limits.max_tool_calls` in `scenarios/*.yaml` | 4000 / 40 | Bounds runaway responses. Every model call also reserves `max_output_tokens` against the deployment's TPM limit, so keep it close to the expected answer length. The prompt agent's server-side loop reserves an output budget for each internal call that the agent definition can't cap. The runner drops a parameter the endpoint rejects. Whether `max_tool_calls` caps Browser Automation remote calls isn't documented (verify). |
| **Deployment capacity (TPM)** | `capacity` in `azure.yaml` **and** `infra/foundry/main.parameters.json` | 300 for both models | A rate limit, not a cost, on pay-per-token deployments. Too little capacity turns long or parallel runs into 429 failures, which waste the browser minutes already spent. |
| **Time caps** | `limits.timeout_seconds` | 600 | Client timeout per request |
| **Computer Use step cap** | `limits.max_cua_steps` | 60 | Bounds screenshot loops (see example 7) |
| **Bounded recovery** | `limits.max_recoveries` in `scenarios/*.yaml` | 2 (`09`: 6, `11`: 4) | Limits continuations after a failed browser action. Each recovery costs another model turn, and on broken pages often another minute of `ToolTimeout`. |
| **Consecutive tool errors (hosted agent)** | `MAX_CONSECUTIVE_TOOL_ERRORS` in the hosted agent's environment | 6 (Agent Framework default: 3) | Lets QA runs continue past broken controls. Each extra failure can cost about a minute of browser time. |
| **Local browser for development** | `--mode local` | Cloud browser in the other modes | No browser minutes: model tokens only (`07`: about $0.028, against $0.06 on the hosted agent). For development and `localhost` targets ([07](07-security-and-responsible-ai.md#threat-model), row 14). |
| **Snapshots, not screenshots** | Instructions | Snapshot first | Text is cheaper than images. Prefer `browser_find` and `target` / `depth`-scoped snapshots. Use screenshots only as evidence (JPEG, viewport or element). |
| **Context compaction (hosted agent)** | `CONTEXT_BUDGET_TOKENS` in the hosted agent's environment | 48,000 | A safety net: evicts old tool results (stale snapshots) once the context passes the budget and keeps the last 4 tool-call groups. It never triggered in the measured runs (largest context 12,373 tokens). |
| **Fewer tools (hosted agent)** | `BROWSER_TOOLS` in the hosted agent's environment | 15 of 22 browser tools | Every exposed tool schema is resent on each call. On `07`, 15 instead of 22 tools cut input tokens by 22% (223,930 to 174,538, per Application Insights). |
| **Prompt caching** | Automatic | | Cached input is 75% (`gpt-4.1-mini`) to 90% (`gpt-5.4-mini`) cheaper; 87% of the input in the `07` reference run was cached. Keep instructions and tool lists stable during a run so the prefix stays cacheable. |
| **Close sessions** | Instructions; 15-minute idle timeout | | Ends browser minutes early, and stops the model from re-reading a stale page |
| **Demo site scale to zero** | `DEMO_SITE_MIN_REPLICAS` | 0 | No idle compute. Set 1 only during live demos to avoid cold starts. |
| **Hosted agent scale to zero** | Platform idle timeout | 15 min | Compute only while sessions are active |
| **Log ingestion cap** | `LOG_ANALYTICS_DAILY_CAP_GB` | 1 | Hard stop on ingestion per day. Telemetry gaps appear once it trips. |
| **Trace sampling** | `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG` in the hosted agent's `env:` map | 100% | Fewer spans ingested ([agentserver-core README](https://learn.microsoft.com/python/api/overview/azure/ai-agentserver-core-readme)) |
| **Budget alerts** | `BUDGET_AMOUNT`, `ENABLE_BUDGET` | 100, true | Monthly `Microsoft.Consumption/budgets` filtered on **both** resource groups. Alerts at 50% and 90% actual and 100% forecast go to subscription Owners. Extra e-mails: the `budgetContactEmails` Bicep parameter. |
| **Playwright free trial** | Automatic | 30 days / 100 min | The first browser minutes are free |
| **Delete agent versions** | `python -m demo_cli agents delete`; SDK `project.agents.delete_version(name, version)` | | Versions are immutable and pile up. The demo reuses a version when the definition hash matches. For hosted agents, `delete(..., force=True)` also deletes active sessions. |
| **Compare sparingly** | `python -m demo_cli compare` | | Runs the same scenario 2 or 3 times |
| **Tear down** | `azd down --purge`, then `az consumption budget delete` | | Deletes both resource groups and purges the soft-deleted Foundry account. Subscription-scope budgets survive it ([cleanup](#cleanup-checklist)). |
| **Your own prices** | `pricing.yaml` | List prices | Makes the estimates match your agreement |

---

## See actual spend

```powershell
python -m demo_cli costs            # estimates from runs/*/result.json, grouped by mode
python -m demo_cli costs --azure    # also actual month-to-date cost per service, for both resource groups
python -m demo_cli runs --last 20   # recent runs with status, duration, checks and estimated cost
```

The web console's **Costs** page shows the same estimates by mode, model and scenario, and queries the actual
month-to-date spend when you ask for it. If Cost Management can't be read, it shows the error with a permission hint.

- `--azure` calls the **Cost Management Query API** (`ActualCost`, `MonthToDate`, grouped by `ServiceName`) for
  `rg-<env>-foundry` and `rg-<env>`, with the CLI's credential chain (the Azure CLI account that owns the subscription,
  then azd). The data lags 8 to 24 hours. You need permission to read cost
  data on those resource groups, for example Cost Management Reader (verify for your tenant).
- **Azure portal:** Cost Management, then Cost analysis. Filter by the two resource groups. Platform resources also
  carry the tags `azd-env-name`, `workload: foundry-browser-automation-demo` and `cost-center: demo`. The Foundry layer
  doesn't set these tags, so filter by resource group to catch everything.
- **Budget:** Cost Management, then Budgets, `budget-<env>-<yyyymm>`. A new month's start date produces a new budget
  name, because budget start dates can't be moved.
- **Free trial and browser minutes:** look at the Playwright workspace in the portal and at the Azure App Testing meters
  in Cost analysis.
- **Old hosted runs:** `costs` sums `runs/*/result.json`. Hosted-mode runs recorded before 13:15 UTC on 2026-10-26
  carry inflated token counts (see below), so delete those folders or ignore them.

### Token ground truth

Cost Management lags and is aggregated per service. When you need exact token counts per run, or a reported number
looks wrong, use these two sources:

- **Azure Monitor metrics on the Foundry account.** In the portal, open the Foundry account, then **Metrics**:
  `InputTokens`, `ProcessedPromptTokens` (which includes cached tokens) and `GeneratedTokens`, split by
  `ModelDeploymentName`. They show what the service consumed, including the turns of failed responses that report
  `usage: None`. For Computer Use (direct model calls), the metrics matched the reported usage exactly.
- **The hosted agent's OpenTelemetry spans in Application Insights.** Each `chat <model>` span carries
  `gen_ai.usage.input_tokens`, `gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.output_tokens`. These spans
  exposed the hosted agent's over-reported usage. Summing them per run looks like this (verified: one run is one
  `operation_Id`). Filter on the agent's role name: the platform's `responsesapi` role records matching `chat` spans
  in the same trace, so summing every role counts each model call twice.

  ```kusto
  dependencies
  | where timestamp > ago(1d)
  | where cloud_RoleName == "web-qa-agent" and name startswith "chat "
  | summarize model_calls = count(),
              input  = sum(toint(customDimensions["gen_ai.usage.input_tokens"])),
              cached = sum(toint(customDimensions["gen_ai.usage.cache_read.input_tokens"])),
              output = sum(toint(customDimensions["gen_ai.usage.output_tokens"]))
      by operation_Id
  | order by input desc
  ```

  From the CLI, `az monitor app-insights query` searches only the last hour unless you pass `--offset` (for example
  `--offset 24h`), whatever the query's own time filter says.

Message content isn't needed for this: the usage attributes stay on the spans when content capture is off, which is
this repo's default ([07](07-security-and-responsible-ai.md#10-telemetry-without-message-content)).

---

## Cleanup checklist

- [ ] Stop anything still running locally: the web console (Ctrl+C in its terminal), a local hosted agent.
- [ ] Optional: `python -m demo_cli agents delete` removes the prompt agents. They go with the project anyway.
- [ ] `azd down --purge` removes both resource groups and **purges** the soft-deleted Foundry account, so the name and
      quota are released and you can provision again. Add `--force` to skip the prompt.
- [ ] If you deleted resources some other way, check for soft-deleted accounts:
      `az cognitiveservices account list-deleted` and `az cognitiveservices account purge ...`. Make sure the Azure CLI is
      signed in to the external tenant.
- [ ] **Budgets:** `azd down --purge` does **not** remove them (verified: after a 32-minute teardown that deleted both
      resource groups and purged Log Analytics and the Foundry account, `budget-<env>-202610` was still there). They're
      subscription-scope resources, and every `azd provision` in a new month creates a new one. Delete only your own,
      with the Azure CLI signed in to the external tenant:
      `az consumption budget delete --budget-name budget-<env>-<yyyymm>`.
- [ ] If you enabled `PLAYWRIGHT_LOCAL_AUTH` for the remote Computer Use experiment, revoke the access tokens. Deleting
      the workspace removes them too.
- [ ] Delete local artifacts: `runs/` (task text, answers, screenshots), `.env`, and `.azure/<env>/` if you won't
      reuse the environment.
- [ ] A day later, check Cost analysis to confirm spend stopped (cost data lags).
