# 02 · Use cases and demo script

This guide maps what the Browser Automation tool is good for onto the **14 scenarios** in [`scenarios/`](../scenarios).
They range from reading a page, through a four-step claim form, to hunting UI bugs and reviewing a site's security
posture. You'll also find how to point any scenario at your own URL and inputs, two ready-to-present talk tracks
(15 and 45 minutes) with exact commands and what to point out, and how to add your own scenario. Every scenario runs
unchanged against the **prompt agent**, the **hosted agent**, the hosted agent's code on your PC (**local mode**) and,
where it makes sense, **Computer Use**.

**On this page:** [Modes](#the-four-modes) · [Scenario ladder](#the-scenario-ladder) · [Real-world use cases](#beyond-the-demo-real-world-use-cases) ·
[Configure URL and inputs](#configure-the-target-url-and-inputs) · [Web console](#web-console) · [Before you present](#before-you-present) ·
[Foundry portal](#if-you-demo-in-the-foundry-portal) ·
[15-minute track](#15-minute-talk-track) · [45-minute track](#45-minute-talk-track) · [Talking points](#what-to-point-out) ·
[Add a scenario](#add-your-own-scenario)

---

## The four modes

| Mode (`--mode`) | What runs | Browser | Best for |
|---|---|---|---|
| `prompt` | Foundry prompt agent with the GA `BrowserAutomationTool` ([`src/prompt_agent`](../src/prompt_agent)) | Cloud browser (Playwright Workspaces) | Most tasks. Cheapest and simplest. |
| `hosted` | Hosted agent `web-qa-agent`: Agent Framework, Browser Automation through a Foundry Toolbox, plus `inspect_http_security`, `scan_page_source` and `check_links` ([`src/hosted_agent`](../src/hosted_agent)) | Cloud browser, plus allow-listed plain HTTP | QA and security work that needs evidence the browser can't see (headers, cookie flags, broken links) |
| `local` | The hosted agent's code on your PC, started and stopped per run ([`local_agent.py`](../src/demo_cli/local_agent.py)). The model stays in Foundry. | Edge or Chrome on your PC through the open-source Playwright MCP server (headless unless `--headed`), or the cloud browser with `--remote-browser` | Apps on `localhost` or an intranet, debugging the hosted agent before `azd deploy`, runs without browser minutes ([01](01-browser-automation-tool.md#local-mode-the-hosted-agents-code-on-your-pc)) |
| `cua` | Computer Use loop: screenshots in, mouse and keyboard actions out, on `gpt-5.4-mini` ([`src/computer_use`](../src/computer_use)) | Local Chromium (headless unless `--headed`) | Comparisons and visual checks. Not used for security scenarios. |

---

## The scenario ladder

The "best mode" column is a recommendation for demos. Run `python -m demo_cli compare <id>` to check it on your own
deployment.

| Level | Scenario | What it shows | Best mode | Automatic success check |
|---|---|---|---|---|
| 1 | `01-page-summary` | Open any page, scroll and summarise it for an audience. Defaults to the demo site; pass `--url` for any public page. | `prompt` | Answer is at least 200 characters |
| 1 | `02-site-search` | Use the site's own search box (no URL guessing), open the best article and quote facts exactly | `prompt` (measured: 37 s, 8 actions, ≈ $0.014). Computer Use was faster and cheaper (23.4 s, ≈ $0.008) but invented the article URL. | Contains "14 days" and "Home Premium" |
| 1 | `03-extract-plans-table` | Turn the `/products` table into a typed JSON array, then name the cheapest plan per type | `prompt` (reads the DOM, no OCR) | Contains "Travel Annual multi-trip" and "Auto Premium", plus a value matching `37` / `37.00` |
| 2 | `04-compare-plans` | Tick "Compare" checkboxes, use the compare page, recommend a plan with reasons | `prompt` | Contains "Home Premium" and mentions flood |
| 2 | `05-find-agent` | Filter a directory with dropdowns and language checkboxes; search again without the language criterion if nothing matches | `prompt`. Good for `compare` across all three modes (measured, all 2/2: prompt 33 s ≈ $0.014, hosted 56 s ≈ $0.017, Computer Use 33 s ≈ $0.018). | Contains "Ana Morales" and "206-555-0141" |
| 2 | `06-quote-calculator` | Fill the same form three times with different profiles and tabulate the results | `prompt` | Contains 92.40, 706.56 and 78.10 (from the site's pricing rules) |
| 2 | `14-public-web-research` | Bring your own URL. Answer a question from that page and at most 3 linked pages, with citations. | `prompt` | Answer is at least 300 characters |
| 3 | `07-file-claim` | 4-step wizard. Dropdowns depend on policy type; some fields only appear after a checkbox or radio choice (witness count, police report number). Review and declaration. | `hosted` (measured: 134 s, 27 tool calls, 2/2 checks, ≈ $0.06) | Claim reference `CLM-YYYY-NNNNN` captured, then `GET /api/claims/{ref}` must show policy `CI-100200`, amount `1250.5` and 2 witnesses |
| 3 | `08-validation-recovery` | Enter a wrong phone number and policy number on purpose, record the validation messages, fix them using the page hints, then submit | `hosted` | Claim reference, a `CI-` policy number, and the API shows `policy_type: auto` |
| 4 | `09-ui-bug-hunt` | Exploratory testing of the beta wizard (`/bug-lab/claims/new`), which has **12 planted defects**. Output: defect table and release recommendation. The wizard is broken on purpose, so expect **long runs**: each defective control can cost about 60 s of `ToolTimeout`. | `hosted` (console, network and `check_links` evidence). Measured: 646 s, 40 tool calls, 5 of 12 defects, 1/2 checks, ≈ $0.16, two thirds of it browser minutes. The prompt agent stopped early with 1 of 12. For higher recall, run several focused runs (one per wizard step). | Mentions Travel and 404 (or "not found"), plus answer-key recall against `answer-keys/bug-lab.yaml` |
| 4 | `10-accessibility-review` | WCAG 2.2 AA review: alt text, labels, error announcements, contrast, keyboard use, headings, language | `prompt` or `hosted`, since the accessibility tree is the agent's native view. Contrast needs a visual or manual check. | Mentions alt text and labels, plus recall against `answer-keys/accessibility.yaml` (4 issues) |
| 4 | `11-regression-smoke-test` | Run a natural-language test plan (T1 to T8) and report PASS/FAIL with evidence | `prompt` | `SUMMARY: 8/8` |
| 5 | `12-passive-security-review` | Passive review of `/security-lab/`, which has **13 planted, fake** misconfigurations, mapped to OWASP. Allow-listed. | `hosted`, the only mode that sees raw headers and cookie flags (measured: 38 s, 3 tool calls, 12 of 13 issues found, ≈ $0.015) | Mentions the admin path and the fake API key, plus recall against `answer-keys/security-lab.yaml` |
| 5 | `13-security-before-after` | Compare the insecure page with its hardened twin `/security-lab/secure`, control by control. Allow-listed. | `hosted` (measured: 42 s, 4 tool calls, ≈ $0.015) | Mentions CSRF and BEFORE |

**About `--strong`.** It switches prompt mode to `gpt-5.4-mini`. Use it for short, reasoning-heavy scenarios such as
`03`, `04` and `13`, not for long browser loops in prompt mode: on `09` it hit repeated 429s even at 300K TPM, because
the agent service reserves an output budget for every internal model call and the prompt agent definition can't cap it
([04](04-cost-management.md#8-measured-09-ui-bug-hunt-on-a-deliberately-broken-ui)). Run long tasks on the hosted agent.

The target site, **Contoso Insurance** ([`src/demo_site`](../src/demo_site)), is a FastAPI app on Azure Container Apps.
It has search, products and compare, a quote calculator, FAQ, a find-an-agent directory with filters, and the claim
wizard. `/api/claims/{ref}` lets the runner verify what the agent actually submitted. Everything on the site is fake.
The lab pages only *look* misconfigured.

---

## Beyond the demo: real-world use cases

| Use case | Typical task | Closest scenario | Recommended approach | Watch out for |
|---|---|---|---|---|
| **Form filling on legacy portals without APIs** | Partner onboarding, claims intake, government or supplier portals | `07`, `08` | Prompt agent for one-off tasks. Hosted agent when you need custom tools or a workflow around it. | Sign-in and MFA go to a human via the live view. Pause before the final submit. Verify the result through an API or a confirmation page. |
| **Research and structured extraction** | Pricing and product tables, public registries, documentation Q&A with citations | `03`, `14` | Prompt agent with `gpt-4.1-mini` | Site terms and robots rules. Bound pagination. Snapshots are truncated at 64 KiB. |
| **QA regression and smoke tests** | Run a natural-language test plan after each deployment | `11` | Prompt agent next to your deterministic Playwright tests | Agent runs aren't deterministic. Keep hard assertions in success checks. Don't replace your CI test suite. |
| **Exploratory testing and bug reports** | Find defects and write repro steps with console and network evidence | `09` | Hosted agent (`check_links`, console messages, network requests) | Verify every reported defect. Measure the agent with an answer key. |
| **Accessibility audits** | WCAG checks on key journeys | `10` | Browser Automation (accessibility tree), plus manual or visual verification | Contrast, focus order and screen-reader output need human verification. The scenario asks the agent to flag these as "needs manual verification". |
| **Support issue reproduction** | Follow a customer's steps on staging and capture the error | `08`, `09` | Hosted agent | Use test accounts, never customer credentials. Traces may contain PII. |
| **Passive security posture checks of sites you own** | Security headers, cookie flags, information disclosure, insecure forms | `12`, `13` | Hosted agent with deterministic tools, allow-list and SSRF guard | Get written authorization. Stay passive. Findings are indicators to verify, not proof of exploitability. |
| **Competitive and price monitoring** | Track public prices and features on a schedule | `03`, `14` | Prompt agent | Terms of service can forbid automated access. Don't bypass logins, paywalls, bot protection or robots rules. Rate-limit and get a legal review. |
| **Testing your own app before it's deployed** | Smoke-test a feature branch on `localhost`, or an intranet app | `07` with `--site-url http://localhost:8000` | Local mode: the same agent code with a browser on your PC (measured on `07`: 46.6 s, about $0.028, no browser minutes) | The local browser has your PC's network access. Use test data, and keep it away from production systems ([07](07-security-and-responsible-ai.md#threat-model)). |
| **Desktop, canvas or remote-desktop apps** | Thick clients, VDI | none | Computer Use ([03](03-computer-use-vs-browser-automation.md)) | Preview and limited access for `computer-use-preview`. Run in a sandboxed VM. |

---

## Configure the target URL and inputs

### Command line

```powershell
python -m demo_cli list                     # catalog; --level 3 filters
python -m demo_cli show 07 --set first_name=Jo          # render the exact task text, no run
python -m demo_cli run 01 --url https://learn.microsoft.com/azure/foundry/ --set bullets=3 --mode prompt
python -m demo_cli run 07-file-claim --mode hosted --set first_name=Jo --set "last_name=Doe"
python -m demo_cli ask --url https://example.com "What is this page about?" --mode prompt   # ad-hoc task
python -m demo_cli compare 05-find-agent --modes prompt,hosted,cua                          # side-by-side table
python -m demo_cli run 05-find-agent --mode local --headed                                  # hosted-agent code, browser on this PC
python -m demo_cli run 07-file-claim --mode local --site-url http://localhost:8000          # against a local copy of the site
```

- Scenario IDs accept the numeric prefix: `07` resolves to `07-file-claim`.
- `--url` replaces the start URL. `--set key=value` overrides an input and can be repeated.
- `--set` values are **parsed as YAML**. `3` becomes a number, and `No` / `Yes` become booleans and render as
  `False` / `True`. Quote values that must stay strings: `--set "police_report='No'"`.
- Run options: `--strong` (prompt mode on `gpt-5.4-mini`, for short runs), `--model <deployment>`, `--auto-ack`
  (Computer Use), and `--headed` and `--remote-browser` (Computer Use and local mode). In local mode,
  `--remote-browser` swaps the local browser for the cloud browser through the toolbox.
- `--site-url <url>` points every `${DEMO_SITE_URL}` and `${DEMO_SITE_HOST}` in the scenarios (start URLs and API
  checks) at another copy of the demo site, for example one started with
  `python -m uvicorn app:app --app-dir src\demo_site --port 8000`. Every scenario that supports `hosted` also supports
  `local`.
- `compare` writes `runs/compare-<timestamp>-<id>.md` next to the per-mode run folders.

### Scenario YAML

Edit `scenarios/<id>.yaml`. The task is a Jinja2 template with `{{ url }}` and `{{ inputs.<name> }}`. `${VAR}` and
`${VAR:-default}` are expanded from the environment, and azd outputs such as `DEMO_SITE_URL` are loaded automatically.
The schema is in [scenarios/README.md](../scenarios/README.md) and [below](#add-your-own-scenario).

### Web console

```powershell
pip install -e ".[ui]"            # FastAPI + uvicorn (the dev extra includes them too)
python -m web_console --open      # http://127.0.0.1:8765; --port to change it; also: python -m demo_cli ui
```

The console ([`src/web_console`](../src/web_console)) is a FastAPI app with plain HTML, CSS and JavaScript modules, and
no build step. It has six pages:

| Page | What it does |
|---|---|
| **Overview** | Environment, doctor-style health checks, the agents in the Foundry project, and the local-mode prerequisites |
| **Scenarios** | The catalog as cards, with search and level, category and mode filters |
| **Run** | Left column: scenario, start URL, inputs as fields or YAML, the demo-site target (the deployed site or another copy such as `http://localhost:8000`, like `--site-url`), mode, model and options. Press **Run** (Ctrl+Enter), and the same column shows the live run: a step timeline, the streamed answer, the final answer as safe Markdown, checks, answer-key recall, tokens and cost. Right column: sticky **Preview**, **Task** and **Events** tabs. |
| **Compare** | One scenario in several modes, one after another, with **stop after current**, a comparison table, and `runs/compare-*.md` like `demo_cli compare` |
| **History** | Any run's `report.md`, rendered safely, plus a replay of its steps, its screenshots and its log |
| **Costs** | Estimated totals by mode, model and scenario, plus the actual month-to-date Azure spend on request, with a permission hint when Cost Management can't be read |

The **Preview** tab follows the agent's browser by itself:

| Mode | Preview |
|---|---|
| Prompt, hosted, and local with the cloud browser | The live-view page can't be embedded (it sends `X-Frame-Options: DENY`), so the console opens a window beside itself inside the **Run** click and navigates it to the live view when the agent starts its browser session. A comparison reuses the same window. Allow pop-ups for the console; otherwise a button opens it. |
| Local, browser on your PC | Screenshots of the agent's browser about once a second, with no extra tokens ([how](01-browser-automation-tool.md#local-mode-the-hosted-agents-code-on-your-pc)) |
| Computer Use | Every screenshot the model acts on, with a filmstrip |

- **One run at a time.** Runs use real Azure resources, and a response can't be cancelled once it has started.
- **Use Edge or Chrome.** Browser panels embedded in apps (WebView2, for example the Copilot app's Browser canvas)
  refuse new windows, so the cloud live view can't open there, and the console says so. The local and Computer Use
  previews work anywhere.
- **Verified** on `02-site-search`: prompt mode in 26 s (≈ $0.014), with the side window on the live view about 11 s
  after **Run**; local mode in 35 s (≈ $0.0046) with real Edge screenshots in the preview; Computer Use in 16 s with 4
  screenshots; and a prompt-and-hosted comparison that moved the same window to the second live view.
- The console's own security controls are in [07](07-security-and-responsible-ai.md#12-the-web-console).

### Environment variables that change behaviour

| Variable | Default | Effect |
|---|---|---|
| `PROMPT_AGENT_MODEL` | `gpt-4.1-mini` | Model of the default prompt agent |
| `STRONG_MODEL` | `gpt-5.4-mini` | Model used by `--strong` |
| `COMPUTER_USE_MODEL` | `gpt-5.4-mini` | Model for `--mode cua` |
| `HOSTED_AGENT_MODEL` | `gpt-4.1-mini` | Hosted agent model. Set with `azd env set`, then `azd deploy web-qa-agent`. Local mode uses it too (default: `PROMPT_AGENT_MODEL`). |
| `LOCAL_AGENT_PYTHON` | `src/hosted_agent/.venv` | Python that runs the hosted agent's code in local mode |
| `LOCAL_BROWSER` | `msedge` on Windows, `chrome` elsewhere | Browser that Playwright MCP drives in local mode |
| `PROMPT_AGENT_NAME` / `HOSTED_AGENT_NAME` | `browser-automation-agent` / `web-qa-agent` | Agent names |
| `DEMO_SITE_URL` | from azd | Default start URL for most scenarios |
| `PLAYWRIGHT_SERVICE_ACCESS_TOKEN` | unset | Only for the experimental `--remote-browser` Computer Use mode |

### Allow-list rule

Security scenarios (category `security`) and any scenario with `allowed_domains` refuse to run unless the start URL
**and every URL in the task** are allow-listed. By default the only entry is the demo site host:

```text
> python -m demo_cli run 12 --url https://www.example.org/
Refusing to run: 'www.example.org' is not in allowed_domains ['<demo-site-host>']. Only test systems you own or are authorised to test.
```

The hosted agent's HTTP tools have their own allow-list, `ALLOWED_SCAN_HOSTS` plus the `DEMO_SITE_URL` host, set at
deploy time in `azure.yaml`.

---

## Before you present

- [ ] `python -m demo_cli doctor` shows ✅ everywhere. "Prompt agent exists" turns green after
      `python -m demo_cli agents ensure` or the first prompt-mode run.
- [ ] **Avoid cold starts.** The demo site scales to zero. For a live audience, run
      `azd env set DEMO_SITE_MIN_REPLICAS 1` then `azd provision`, and set it back to `0` afterwards. Hosted agents also
      scale to zero, so warm the hosted agent up with one request, for example
      `python -m demo_cli ask --mode hosted --url <demo-site-url> "What is the page title?"`.
- [ ] Run `python -m demo_cli run 02-site-search --mode prompt` once. That wakes the site, refreshes the prompt agent and
      proves the Playwright connection works.
- [ ] Open the Foundry portal on the project (**Agents**, **Traces**) in a browser tab.
- [ ] Keep a **recorded run** of every scenario you plan to show (`runs/<...>/report.md`) as a fallback. Run times vary,
      so rehearse with your own timings.
- [ ] Use a wide terminal; the summary tables need it.
- [ ] **Showing local mode?** Install Node.js 18+ and create the hosted agent's environment
      (`py -3.11 -m venv src\hosted_agent\.venv`, then
      `src\hosted_agent\.venv\Scripts\python -m pip install -r src\hosted_agent\requirements.txt`). `doctor` lists both
      as optional checks. Do one local run beforehand: npx downloads the pinned Playwright MCP package on first use.
- [ ] **Run long scenarios one at a time.** Parallel runs share the deployment's TPM limit, and every model call
      reserves its output budget against it. Running the prompt and hosted versions of `09` together on a 100K-TPM
      deployment ended in a 429 "Model deployment rate limit exceeded"; both deployments now have 300K TPM. Capacity
      is a rate limit, not a cost: both are pay-per-token. Even 300K didn't stop 429s for `--strong` on a long
      prompt-mode run, so keep `--strong` for short scenarios.
- [ ] The CLI prints the live view link in the terminal ("Watch the cloud browser live: ...") so you can open it.
      Anyone who can read it on a shared or recorded screen could take control until the session closes or idles out
      for 15 minutes. That's acceptable on the fake demo site. On real targets, keep the terminal off-screen, or present
      from the web console, which opens the live view in a side window and never shows the link.
- [ ] **Presenting from the web console?** Start it with `python -m web_console --open` in Edge or Chrome, and allow
      pop-ups for `http://127.0.0.1:8765`, so the live view opens beside it without a click.

### If you demo in the Foundry portal

The prompt agents also work in the portal playground (**Build > Agents**): `browser-automation-agent` (`gpt-4.1-mini`)
and `browser-automation-agent-gpt-5-4-mini`.

- A failed browser action, for example a `ToolTimeout`, ends a prompt agent's turn with an error. The CLI recovers
  automatically; in the playground, reply "take a snapshot and continue", and the agent picks up in the same browser
  session (sessions stay alive for 15 idle minutes).
- Use `browser-automation-agent-gpt-5-4-mini` rather than switching the model of `browser-automation-agent` in the
  portal. `python -m demo_cli agents ensure` creates a new agent version whenever the repo's instructions change, so
  edits made in the portal are replaced on the next run.
- Three playground runs on `gpt-5.4-mini` timed out because the model mangled frame-prefixed refs (`f1e30` became
  `e30` or `e1f30`). The instructions now say to copy refs character for character, and the same task passes
  ([01](01-browser-automation-tool.md#copy-refs-exactly-frame-prefixes)).

---

## 15-minute talk track

Every command in both tracks also works from the web console: **Run** for single runs, **Compare** for `compare`, and
**Costs** for `costs`.

| Time | Do | Command | Point out |
|---|---|---|---|
| 0:00 to 2:00 | Frame it: agents that use websites the way people do | Show the diagram in the [README](../README.md) or [01](01-browser-automation-tool.md#architecture) | GA since 2026-10-19. Foundry runs the loop. Cloud browsers in Playwright Workspaces. Keyless auth. |
| 2:00 to 6:00 | Simple task on the prompt agent | `python -m demo_cli run 02-site-search --mode prompt` | Action log: `create_browser_session`, `browser_navigate`, `browser_snapshot`, then `browser_type target=e24` and `browser_click target=e25`. Open the **🔴 live view** link. Snapshots and refs vs screenshots. 2/2 checks and the cost line (about $0.014 measured). |
| 6:00 to 10:30 | Complex form on the hosted agent (measured: about 2 min 15 s) | `python -m demo_cli run 07-file-claim --mode hosted` | Dependent dropdowns and conditional fields, filled without asking between fields. The claim reference. The automatic check calls `/api/claims/{ref}` to prove the data really landed. Hosted agent = Agent Framework + toolbox (`browserautomation___*` tools). |
| 10:30 to 13:30 | Security review of a page we own (measured: about 38 s) | `python -m demo_cli run 12-passive-security-review --mode hosted` | The custom tools find what the browser can't see: response headers, cookie flags, `robots.txt`. Allow-list, passive only. Answer-key recall out of 13. |
| 13:30 to 15:00 | Cost and wrap-up | `python -m demo_cli costs` | Cost per run, budget alerts, `azd down --purge`. Where Computer Use fits ([03](03-computer-use-vs-browser-automation.md)). |

If the hosted runs are too slow for your slot, show the `07` run as a recorded report (`runs/<...>/report.md`), or run
it in local mode against a local copy of the site (`--mode local --site-url http://localhost:8000`, measured 46.6 s).
Don't switch it to `--mode prompt --strong`: long prompt-mode loops on `gpt-5.4-mini` hit 429s.

---

## 45-minute talk track

| Time | Segment | Commands | Point out |
|---|---|---|---|
| 0:00 to 5:00 | **Context.** What GA means; prompt vs hosted vs local vs Computer Use. | Show [01](01-browser-automation-tool.md#architecture) and [03](03-computer-use-vs-browser-automation.md#side-by-side) | Who executes actions. What the model sees. Toolbox reuse. |
| 5:00 to 12:00 | **Basics and extraction** | `python -m demo_cli run 01 --url https://learn.microsoft.com/azure/foundry/ --set bullets=3`<br/>`python -m demo_cli run 03-extract-plans-table --mode prompt`<br/>`python -m demo_cli show 07 --set first_name=Jo` | Works on any public page. DOM to JSON with no OCR. How scenarios are templated and configured. |
| 12:00 to 22:00 | **Complex forms** | `python -m demo_cli run 07-file-claim --mode hosted`<br/>`python -m demo_cli run 08-validation-recovery --mode hosted` | Validation messages captured verbatim and fixed from page hints. Verification through the site API. Why long loops run on the hosted agent, and where `--strong` fits: short, reasoning-heavy tasks such as `03` or `04`. |
| 22:00 to 31:00 | **QA** | `python -m demo_cli run 09-ui-bug-hunt --mode hosted` (show a recorded run: the measured run took 646 s, longer than this segment)<br/>`python -m demo_cli run 11-regression-smoke-test --mode prompt`<br/>(optional) `python -m demo_cli run 10-accessibility-review --mode prompt` | Defect table with repro steps. Console `TypeError`, the 404 on submit, `check_links` finding the broken logo and Terms link. Answer-key recall out of 12: the measured run reported 5. Explain why broken controls make agents slow (each failing action waits about a minute, so browser minutes were two thirds of its $0.16), and why this needs the hosted agent's long-running loop (the prompt agent stopped early with 1 of 12). `SUMMARY: 8/8`. |
| 31:00 to 38:00 | **Security (owned targets only)** | `python -m demo_cli run 13-security-before-after --mode hosted`<br/>`python -m demo_cli run 12 --url https://www.example.org/` | Before/after control table. The second command is **refused** by the allow-list, and that's the point. |
| 38:00 to 43:00 | **Computer Use comparison** | `python -m demo_cli compare 02-site-search --modes prompt,cua`<br/>or `python -m demo_cli run 09-ui-bug-hunt --mode cua --headed`<br/>(optional) `python -m demo_cli run 02-site-search --mode local --headed` | The comparison table (duration, tool calls, tokens, checks, cost): Computer Use is faster and cheaper on `02`. Then read both answers: the Computer Use answer contains an invented article URL, because the model only sees pixels. Open `runs/<...>-cua/step-*.png`. Your code executes every click. |
| 43:00 to 45:00 | **Cost and cleanup** | `python -m demo_cli costs --azure` | Estimated vs actual spend (Cost Management lags up to 24 h). Budget alerts. `azd down --purge`, then delete the budget: it survives teardown. |

---

## What to point out

- **Live view.** Every Browser Automation run prints a 🔴 live view event in the terminal, and the web console opens the
  live view in a window beside itself (on `02`, about 11 s after **Run**). Watch the cloud browser, and mention **Take
  control** for CAPTCHA and MFA handoffs. The URL is signed, so treat it as a secret: the hosted agent is instructed to
  share it once, unaltered, the run reports redact it, and the web console never displays it.
- **Refs.** In the action log, targets look like `e24` and `e25`. They come from the accessibility snapshot, not from
  pixels. Tell the story of the first failed run: a guessed `aria-label` selector, a `ToolTimeout`, the whole response
  failed. Then the fix: ref-only instructions plus automatic recovery. After a navigation, refs can carry a frame
  prefix (`f1e30`), and they must be copied exactly: `gpt-5.4-mini` once shortened them in the portal playground, and
  every click timed out.
- **Local mode.** The same agent code runs on your PC; only the browser changes. It reaches `localhost` and costs no
  browser minutes (`07` against a local copy of the site: 46.6 s, about $0.028, against about $0.06 on the hosted
  agent). The Browser Automation tool itself has no local version, so local mode uses the open-source Playwright MCP
  server.
- **Toolbox.** The hosted agent never declares the browser tool. It discovers `browserautomation___*` tools from the
  toolbox's MCP endpoint, through the same connection the prompt agent uses, and exposes only a curated 15-tool subset
  to its model (no `browser_run_code` or `browser_evaluate`).
- **Custom tools see what the browser can't.** In `12` and `13`, `inspect_http_security` reports missing CSP and HSTS,
  `Server: Apache/2.2.15`, `X-Powered-By: PHP/5.4.16`, CORS `*` with credentials, and a `sessionid` cookie without
  Secure, HttpOnly and SameSite. The prompt agent can only say it couldn't verify those. Compare both modes on `12`.
- **Proof, not prose.** `07` and `08` are checked through `/api/claims/{ref}`. QA and security runs get a heuristic
  recall score against an answer key.
- **Cost line.** Each run ends with tokens (in/cached/out), browser minutes and an estimated cost. Short runs cost
  one to two cents. Even the 4-step claim wizard on the hosted agent (27 tool calls) costs about $0.06, half of it
  browser minutes, with 87% of its input tokens served from the prompt cache. See
  [04](04-cost-management.md#worked-examples).
- **Measure, don't trust one number.** The hosted agent's reported usage was once inflated 10 to 12 times by a
  framework bug; Application Insights spans and Azure Monitor metrics showed the truth. A good story for engineers.
- **Computer Use screenshots and accuracy.** `runs/<...>-cua/step-NNN.png` shows exactly what the model saw. Safety
  checks stop the run unless you acknowledge them. On `02` the automatic checks passed, yet the answer contained an
  invented URL. Pixels carry less truth than the DOM, so read Computer Use answers critically.
- **Traces.** Open the same response in the Foundry portal under **Traces** to show the server-side view.

---

## Add your own scenario

1. **Create a file** with a unique numeric prefix, because `find_scenario` resolves `15` to `15-...`. Use the file name
   (without `.yaml`) as the `id`.

   ```yaml
   # scenarios/15-faq-answer.yaml (example)
   id: 15-faq-answer
   title: Find an answer in the FAQ accordion
   level: 1
   category: navigation          # navigation | extraction | form-filling | qa | accessibility | security | research
   modes: [prompt, hosted, cua]
   url: ${DEMO_SITE_URL}/faq
   inputs:
     question: How long does a claim take?
   task: |
     Open {{ url }}. Find the question "{{ inputs.question }}", expand it and quote the answer exactly.
     Then list three other questions shown on the page.
   success_criteria:
     - {type: contains, value: "10 business days"}
   limits:
     max_output_tokens: 1000
     max_tool_calls: 10
     timeout_seconds: 240
     max_cua_steps: 15
     max_recoveries: 2           # prompt agent: continuations after a failed browser action (ToolTimeout)
   ```

2. **Render it:** `python -m demo_cli show 15`. Check the URL, the inputs and the final task text.
   **Word tasks neutrally.** Azure AI Content Safety (Prompt Shields) screens the task. An earlier version of `05` said
   "relax only the language filter", which was flagged as a jailbreak attempt and blocked before any tool call. It now
   says "search again without the language criterion". Avoid phrasing like "relax / ignore / bypass the filter or the
   rules". When a run is blocked with `content_filter`, the CLI prints a hint.
3. **Run it** in prompt mode first, then the others: `python -m demo_cli run 15 --mode prompt`, then
   `python -m demo_cli compare 15 --modes prompt,hosted,cua`.
4. **Add checks.**

   | `type` | Fields | Passes when |
   |---|---|---|
   | `contains` | `value` | The value appears in the answer (case-insensitive) |
   | `regex` | `pattern`, optional `capture_as` | The pattern matches. The captured text can be used as `{name}` in `http_json`. |
   | `min_length` | `value` | The answer has at least that many characters |
   | `http_json` | `url` (with `{captures}`), `expect` | A GET returns HTTP 200 JSON whose fields match. Numbers match within ±0.01; strings case-insensitively. |

5. **QA or security scenarios:** on pages that are broken on purpose, raise `max_recoveries` (`09` uses 6, `11` uses 4)
   and the time limits, and keep `max_output_tokens` close to the expected report length. Add an answer key and
   reference it with `answer_key: answer-keys/<file>.yaml`. An issue
   counts as found when every keyword group matches, with any one keyword per group:

   ```yaml
   issues:
     - id: BL-05
       severity: Critical
       title: Coverage level dropdown is empty for Travel policies, blocking travel claims
       match_all_groups: [["travel"], ["coverage"]]
   ```

6. **Security scenarios:** use `category: security` and `modes: [prompt, hosted]`, and set `allowed_domains` to
   `["${DEMO_SITE_HOST}"]` or to hosts you own or are authorized to test. To let the hosted agent's HTTP tools reach a
   new host, add it to `ALLOWED_SCAN_HOSTS` in `azure.yaml` and redeploy.
7. **Validate the catalog:** `python -m pytest tests/test_scenarios.py -q`. It checks that every scenario loads, its level
   is 1 to 5, and its modes are valid.
