# 05 · Deploy in an Azure tenant

This is the step-by-step deployment of the demo into your own Azure subscription. Your subscription may be governed
by Azure Policy assignments and MFA enforcement, and your Azure CLI may be signed in to a different tenant than the
one you deploy to. Everything is deployed with **azd**. The
`foundry` layer creates the Foundry account, project and models. The `platform` layer adds the Playwright workspace,
connections, RBAC, monitoring, the demo site and a budget. Hooks create the Browser Automation toolbox and the prompt
agent. No API keys are used for Foundry, the models or Playwright, so the deployment is compliant with the
"disable local auth" control. Check your organization's policies separately; this is not a compliance certification.
This page covers prerequisites, sign-in, environment setup,
quota, provisioning, deployment, verification, what gets created, region choice, policy notes, a troubleshooting table
and teardown.

**On this page:** [What gets created](#what-gets-created) · [Prerequisites](#prerequisites) · [Steps 1 to 8](#step-by-step) ·
[Configuration](#configuration-reference) · [Region choice](#region-choice) · [Policy considerations](#policy-considerations) ·
[Troubleshooting](#troubleshooting) · [Teardown](#teardown)

---

## What gets created

`<env>` is your azd environment name and `<token>` is a deterministic suffix.

| Resource | Type | Resource group | Name | Notes |
|---|---|---|---|---|
| Foundry account | `Microsoft.CognitiveServices/accounts` (kind `AIServices`, S0) | `rg-<env>-foundry` | `cog-<token>` | `disableLocalAuth: true`, system-assigned identity, public network access |
| Model deployments | `.../accounts/deployments` | `rg-<env>-foundry` | `gpt-4.1-mini`, `gpt-5.4-mini` | `gpt-4.1-mini` 2025-04-14 GlobalStandard 300 (300K TPM); `gpt-5.4-mini` 2026-03-17 DataZoneStandard 300 (300K TPM) |
| Foundry project | `.../accounts/projects` | `rg-<env>-foundry` | `<env>` (`AZURE_AI_PROJECT_NAME`) | System-assigned identity. This identity calls Playwright. |
| Project connections | `.../projects/connections` | `rg-<env>-foundry` | `browserautomation`, `appinsights` | `PlaywrightWorkspace` with `ProjectManagedIdentity`; `AppInsights` for tracing |
| Role assignments for you | `Microsoft.Authorization/roleAssignments` | project scope | | Foundry User + Foundry Project Manager |
| Role assignment for you on the account | `Microsoft.Authorization/roleAssignments` | account scope | | **Cognitive Services OpenAI User**, because Computer Use calls the account-level endpoint, which project-scoped roles don't cover |
| Playwright workspace | `Microsoft.LoadTestService/playwrightWorkspaces@2025-09-01` | `rg-<env>` | `pww<token>` | `westeurope` by default, `localAuth: Disabled`, `regionalAffinity: Enabled` |
| Role assignments on the workspace | `Microsoft.Authorization/roleAssignments` | workspace scope | | **Playwright Workspace Contributor** for the project identity and for you |
| Log Analytics | `Microsoft.OperationalInsights/workspaces` | `rg-<env>` | `log-<token>` | PerGB2018, 30-day retention, **1 GB/day cap** |
| Application Insights | `Microsoft.Insights/components` | `rg-<env>` | `appi-<token>` | Workspace-based |
| Container registry | `Microsoft.ContainerRegistry/registries` (Basic) | `rg-<env>` | `cr<token>` | Admin user disabled. Holds the demo-site image. |
| Pull identity | `Microsoft.ManagedIdentity/userAssignedIdentities` | `rg-<env>` | `id-demo-site-<token>` | AcrPull on the registry |
| Container Apps environment | `Microsoft.App/managedEnvironments` | `rg-<env>` | `cae-<token>` | Consumption workload profile, logs to Log Analytics |
| Demo site | `Microsoft.App/containerApps` | `rg-<env>` | `ca-demo-site-<token>` | External ingress on port 8000, 0.25 vCPU / 0.5 GiB, 0 to 2 replicas. Runs a placeholder image until the first `azd deploy demo-site`; later provisions keep the deployed image (`SERVICE_DEMO_SITE_RESOURCE_EXISTS`, `fetch-container-image.bicep`; verified). |
| Budget | `Microsoft.Consumption/budgets` | subscription scope | `budget-<env>-<yyyymm>` | Filtered on both resource groups. Alerts at 50% and 90% actual and 100% forecast. **Not removed by `azd down`** ([teardown](#teardown)). |
| Toolbox | Foundry toolbox (postprovision hook) | Foundry project | `browser-automation-tools` | One `browser_automation` tool, published |
| Hosted agent | Foundry hosted agent (`azd deploy`) | Foundry project | `web-qa-agent` | Code deploy, `python_3_13`, remote build, 0.5 vCPU / 1 GiB |
| Prompt agent | Foundry prompt agent (postdeploy hook or first run) | Foundry project | `browser-automation-agent` | `BrowserAutomationTool` on `gpt-4.1-mini` |

---

## Prerequisites

| Requirement | Details |
|---|---|
| **Azure Developer CLI** | `>= 1.37.0`, plus the extensions pinned in `azure.yaml`: `azure.ai.agents >= 1.0.0-beta.22`, `azure.ai.projects >= 1.0.0-beta.15`, `azure.ai.toolboxes >= 1.0.0-beta.12`. Install any that are missing with `azd ext install <id>`. |
| **PowerShell 7 (`pwsh`)** | Windows hooks run with `shell: pwsh`. POSIX hooks (`sh`) exist too. |
| **Python 3.11+ (x64)** | Needed for the CLI, the console, Computer Use and local mode. On Windows on ARM, install the **x64** build: ARM64 Python 3.12 had no `cryptography` wheel. |
| **Azure CLI** | Recommended. The CLI and console use the Azure CLI account that owns `AZURE_SUBSCRIPTION_ID`, even when the CLI's default account is in another tenant, and fall back to azd ([step 1](#1-sign-in-with-azd-to-the-external-tenant)). Also used for the quota check and manual cleanup. |
| **Local mode (optional)** | Node.js 18+ (`npx`) and Edge (Windows) or Chrome for the local browser, plus the hosted agent's own virtual environment in `src/hosted_agent/.venv` ([setup](01-browser-automation-tool.md#local-mode-the-hosted-agents-code-on-your-pc)). Not needed for the cloud modes. |
| **Permissions** | **Owner** on the subscription, or **Contributor + Role Based Access Control Administrator**. The templates create resource groups, role assignments (Playwright Workspace Contributor, Foundry User, Foundry Project Manager, Cognitive Services OpenAI User, AcrPull) and a subscription-scope budget. |
| **MFA** | Follow your tenant's MFA requirements for resource write and delete operations. Sign in interactively. |
| **Quota** | `gpt-4.1-mini` GlobalStandard **300K TPM** and `gpt-5.4-mini` DataZoneStandard **300K TPM** free in `AZURE_LOCATION` (see [step 3](#3-check-model-quota)). |

---

## Step by step

### 1. Sign in with azd to the external tenant

```powershell
azd auth login --tenant-id <external-tenant-id>
azd auth login --check-status
```

Sign in with the account that belongs to the **external tenant**. By default azd keeps its own sign-in, separate from
the Azure CLI. azd's identity provisions, deploys and runs the hooks; the Python tools prefer the Azure CLI account that
owns the subscription:

- The hooks get tokens with `azd auth token --scope https://ai.azure.com/.default`.
- The CLI and the console use `get_credential()` ([`settings.py`](../src/demo_common/settings.py)). It tries, in
  order: `AzureCliCredential(subscription=AZURE_SUBSCRIPTION_ID)`, which picks the Azure CLI account that owns that
  subscription even when the CLI's default account is in another tenant (the same as
  `az account get-access-token --subscription <id>`); azd; the Azure CLI's default account; then the other
  `DefaultAzureCredential` sources. Each CLI source is wrapped so that an authentication failure moves on to the next
  source instead of ending the chain. If you set `AZURE_TOKEN_CREDENTIALS`, the choice goes to `DefaultAzureCredential`
  instead.
- Local mode passes `AZURE_CLI_SUBSCRIPTION` to the local agent server, which then uses the same approach
  ([`dev_credential.py`](../src/hosted_agent/dev_credential.py)). In Foundry, the hosted agent uses its managed identity.
- A hand-started agent server reads `src/hosted_agent/.env`, and `.env.example` sets
  `AZURE_TOKEN_CREDENTIALS=AzureDeveloperCliCredential`.

The Azure CLI needs a cached sign-in that can see the target subscription (`az account list`). If it has none, run
`az login --tenant <external-tenant-id>` once, and switch your default back with `az account set` if you like.

> azd's configuration and sign-in live in your user profile, so every terminal shares them. Two things can silently
> switch the account this demo uses: someone runs `azd auth login` with another account, or, when azd's config has
> **`auth.useAzCliAuth` set to `true`**, someone changes the Azure CLI's default account (`az login`,
> `az account set`) in another window. With that setting azd simply follows the CLI.
> Check it with `azd config get auth.useAzCliAuth`.

#### Pin one terminal to the external tenant

Running scenarios no longer needs this: the CLI and console pick the right Azure CLI account by subscription (see
above). `azd provision`, `azd deploy` and the hooks still use azd's sign-in, though. When you work in several tenants at
once, either run `azd auth login --tenant-id <external-tenant-id>` first, or isolate the sign-in for one terminal
instead of changing the global one. These variables only affect the current PowerShell session:

```powershell
# A private copy of the Azure CLI configuration, pinned to the external subscription
Copy-Item -Recurse "$HOME\.azure" "$HOME\.azure-external"
$env:AZURE_CONFIG_DIR    = "$HOME\.azure-external"
$env:AZURE_EXTENSION_DIR = "$HOME\.azure\cliextensions"     # keeps az extensions working
az account set --subscription <external-subscription-id>

# A private azd configuration that follows this terminal's Azure CLI account. Copy everything except azd's own
# sign-in cache (auth); the copy keeps the installed azd extensions working.
New-Item -ItemType Directory -Force "$HOME\.azd-external" | Out-Null
Get-ChildItem "$HOME\.azd" -Force | Where-Object Name -ne 'auth' | Copy-Item -Destination "$HOME\.azd-external" -Recurse -Force
$env:AZD_CONFIG_DIR = "$HOME\.azd-external"
azd config set auth.useAzCliAuth true

azd deploy web-qa-agent
```

This configuration only works while the Azure CLI still has the target account
in its token cache. Otherwise run
`az login --tenant <external-tenant-id>` in the pinned terminal first. Hooks and the Python tools started from that
terminal use the same account, because they get their tokens through azd and the Azure CLI.

To point the demo CLI at another copy of the project (another azd environment), or to force a credential for the
current session, dot-source the helper. Process environment variables take precedence over the repo `.env`:

```powershell
. .\scripts\use-azd-env.ps1 -ProjectDir C:\dev\other-copy -Credential AzureDeveloperCliCredential
```

### 2. Create and configure the environment

```powershell
azd env new <env-name>                                  # 3 to 32 letters, digits or hyphens
azd env set AZURE_SUBSCRIPTION_ID <subscription-id>
azd env set AZURE_LOCATION swedencentral
azd env set AZURE_TENANT_ID <external-tenant-id>

# Optional (defaults shown)
azd env set PLAYWRIGHT_LOCATION westeurope              # eastus, westus3, westeurope, eastasia, japaneast, australiaeast, switzerlandnorth
azd env set BUDGET_AMOUNT 100                           # monthly, in the subscription's billing currency (minimum 10)
azd env set DEMO_SITE_MIN_REPLICAS 0                    # 1 = no cold starts during a live demo
azd env set HOSTED_AGENT_MODEL gpt-4.1-mini             # or gpt-5.4-mini
```

- **Environment name.** It becomes the Foundry project name (3 to 32 characters) and appears in `rg-<env>`,
  `rg-<env>-foundry` and the budget name.
- **`AZURE_TENANT_ID`.** Hooks receive azd environment values, so hook-run Python pins its tokens to this tenant. The
  generated `.env` doesn't include it. For manual runs, set `$env:AZURE_TENANT_ID = "<external-tenant-id>"` in your
  session or profile. This is optional while azd is signed in to the right tenant.

### 3. Check model quota

Quota is shared by the whole subscription for a given model and deployment type (the usage API reports it per region).
Other deployments in the subscription consume it.

```powershell
az login --tenant <external-tenant-id>      # only if your Azure CLI is signed in elsewhere
az cognitiveservices usage list --location swedencentral --subscription <subscription-id> `
  --query "[?contains(name.value, 'gpt-4.1-mini') || contains(name.value, 'gpt-5.4-mini')].{name:name.value, used:currentValue, limit:limit}" -o table
```

You need 300 units (thousand TPM) free for each deployment. Capacity is a rate limit, not a cost: both deployments are
pay-per-token. The 300K TPM leaves room for long browser runs, which resend their context on every step, and for the
output budget that each call reserves against the limit. With 100K TPM, two long scenarios in parallel failed with 429.
Long prompt-mode loops on `gpt-5.4-mini` hit 429s even at 300K ([troubleshooting](#troubleshooting)). If you don't
have the quota:

- Lower `capacity` in **both** `azure.yaml` (the `ai-project` deployments) and `infra/foundry/main.parameters.json`
  (`deployments`). The ejected Foundry layer deploys what's in its parameters file, and `azure.yaml` carries the same
  list, so always change both. Then run long scenarios one at a time.
- Or pick another region.
- Or pick another model that supports the Browser Automation tool. Not `gpt-5-mini`, `gpt-5-nano`, `gpt-5.1`, `gpt-5.2`
  or `computer-use-preview` ([models](01-browser-automation-tool.md#supported-models-and-regions)).

### 4. Provision

```powershell
azd provision
```

1. **`foundry` layer** (`infra/foundry`, `microsoft.foundry` provider, generated by `azd ai agent init --infra`): creates
   `rg-<env>-foundry`, the Foundry account with `disableLocalAuth: true`, the model deployments (one at a time) and the
   project with its managed identity.
2. **`platform` layer** (`infra/platform`, Bicep, `dependsOn: foundry`): creates `rg-<env>`, monitoring, the Playwright
   workspace and its RBAC, both project connections, your Foundry roles, the registry, the Container Apps environment,
   the demo-site app (with a placeholder image until deploy) and the budget.
3. **`postprovision` hook**: creates and publishes the toolbox `browser-automation-tools`, retrying 5 times every 15 s
   while RBAC propagates. It sets `TOOLBOX_NAME`, `TOOLBOX_CONNECTION_ID` and `TOOLBOX_ENDPOINT`, then writes the
   repo-root **`.env`** with the endpoints the CLI needs.

Outputs are stored in `.azure/<env>/.env`. To regenerate the local `.env`, run `azd hooks run postprovision`.

### 5. Create the local Python environment

Do this **before** `azd deploy`, so the `postdeploy` hook can create the prompt agent.

```powershell
py -3.11 -m venv .venv                                   # any x64 Python 3.11+
.\.venv\Scripts\Activate.ps1
python -c "import platform; print(platform.machine())"   # expect AMD64
python -m pip install --upgrade pip
pip install -e ".[ui]"                                   # web console; add dev for tests: pip install -e ".[ui,dev]"
python -m playwright install chromium                    # Computer Use and the browser tests
```

Use **pip**. If your network uses TLS inspection, configure its approved certificate chain.

### 6. Deploy

```powershell
azd deploy                      # or individually: azd deploy web-qa-agent / azd deploy demo-site
```

- **`web-qa-agent`** is a code deployment: runtime `python_3_13`, dependencies installed by a remote build from
  `src/hosted_agent/requirements.txt`. No Docker or registry is involved. Its environment comes from `azure.yaml`:
  model, toolbox name, demo site URL and the scan allow-list.
- **`demo-site`** is built remotely in the platform registry (Docker) and rolled out as a Container Apps revision.
- The **`postdeploy` hook** (`continueOnError: true`) calls `<DEMO_SITE_URL>/healthz`, prints any `AGENT_*` endpoint
  values, and runs `python -m demo_cli agents ensure` when `.venv` exists.

### 7. Verify

```powershell
python -m demo_cli doctor
```

The checks are: `FOUNDRY_PROJECT_ENDPOINT`, the Browser Automation connection ID, the demo site URL, demo site health,
project reachable plus connection, hosted agent deployed, prompt agent exists, and Playwright installed. "Prompt agent
exists" passes once `python -m demo_cli agents ensure` or a prompt-mode run has created it. Two optional checks report
the local-mode prerequisites (the hosted agent's environment, and Node.js with npx) without failing. The web console's
**Overview** page runs the same checks.

### 8. First runs

```powershell
python -m demo_cli list
python -m demo_cli run 02-site-search --mode prompt
python -m demo_cli run 07-file-claim --mode hosted
python -m demo_cli run 05-find-agent --mode cua --headed
python -m web_console --open          # web console on http://127.0.0.1:8765 (also: python -m demo_cli ui)
```

Talk tracks are in [02-use-cases-and-demo-script.md](02-use-cases-and-demo-script.md).

---

## Configuration reference

| Variable (`azd env set`) | Default | Used by |
|---|---|---|
| `AZURE_SUBSCRIPTION_ID`, `AZURE_LOCATION` | (required) | Both layers |
| `AZURE_TENANT_ID` | unset | Python credential chain (when present in the process environment) |
| `PLAYWRIGHT_LOCATION` | `westeurope` | Playwright workspace region (7 allowed values) |
| `PLAYWRIGHT_LOCAL_AUTH` | `Disabled` | `Enabled` allows workspace access tokens. Only for the experimental `--remote-browser` Computer Use mode. |
| `BUDGET_AMOUNT` / `ENABLE_BUDGET` | `100` / `true` | Monthly budget and alerts |
| `DEMO_SITE_MIN_REPLICAS` | `0` | 0 = scale to zero; 1 = no cold start (0 to 2 allowed) |
| `LOG_ANALYTICS_DAILY_CAP_GB` | `1` | Ingestion cap; `-1` disables it |
| `HOSTED_AGENT_MODEL` | `gpt-4.1-mini` | Hosted agent model (`AZURE_AI_MODEL_DEPLOYMENT_NAME`) |
| `CAPTURE_MESSAGE_CONTENT` | `false` | Sets the hosted agent's `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`. `true` sends prompts, page snapshots, tool results and the live view link to Application Insights, so use it only for debugging, then switch back. Redeploy `web-qa-agent` after changing it. |
| `TOOLBOX_NAME` | `browser-automation-tools` | Toolbox created by the hook and used by the hosted agent |
| `AZURE_PRINCIPAL_TYPE` | `User` | Use `ServicePrincipal` when a pipeline runs azd |
| `AZURE_AI_PROJECT_NAME` / `AZURE_FOUNDRY_RESOURCE_GROUP` | `<env>` / `rg-<env>-foundry` | Foundry layer names |

**Hosted agent runtime settings.** These are read by `src/hosted_agent/main.py`. They aren't in the `env:` map of
`web-qa-agent` in `azure.yaml`, so the defaults apply until you add them there and run `azd deploy web-qa-agent`.

| Variable | Default | Effect |
|---|---|---|
| `BROWSER_BACKEND` | `toolbox` | `toolbox` (Browser Automation tool through the toolbox) is the only option in Foundry. `local` (Playwright MCP) is for local runs; local mode sets it. |
| `BROWSER_TOOLS` | 15 tools (no `browser_run_code`, `browser_evaluate`, file upload, screenshots, hover, drag, tabs) | Comma-separated short names of the browser tools exposed to the model |
| `DETAILED_TOOL_ERRORS` | `true` | Passes a failing tool's error text to the model (`include_detailed_errors`), so it can read why an action failed |
| `AGENT_HOST` | `0.0.0.0` (`127.0.0.1` with the local backend) | Bind address. The container needs all interfaces; keep loopback on a dev machine, because the server has no authentication. |
| `BROWSER_TOOL_PREFIX` | `browserautomation` | Prefix of the toolbox tool names |
| `CONTEXT_BUDGET_TOKENS` | `48000` | Context size at which old tool results are compacted |
| `MAX_CONSECUTIVE_TOOL_ERRORS` | `6` | Consecutive tool errors before Agent Framework stops calling tools and asks for a final answer (its own default is 3). QA runs on broken pages fail actions by design. |
| `LOG_LEVEL` | `INFO` | Log level of the hosted agent |

Computer Use calls the account-level endpoint from `AZURE_OPENAI_ENDPOINT`, a `foundry` layer output that the
postprovision hook copies to `.env`. Local-only variables (`PROMPT_AGENT_MODEL`, `STRONG_MODEL`, `COMPUTER_USE_MODEL`, `AZURE_TOKEN_CREDENTIALS`,
`PLAYWRIGHT_SERVICE_ACCESS_TOKEN`, `LOCAL_AGENT_PYTHON`, `LOCAL_BROWSER`) are described in
[02](02-use-cases-and-demo-script.md#environment-variables-that-change-behaviour).
Budget alert e-mails beyond subscription Owners go in the `budgetContactEmails` parameter of
`infra/platform/main.bicep`. That parameter isn't mapped to an environment variable.

---

## Region choice

| Component | Region | Why |
|---|---|---|
| Foundry account, project, models | **Sweden Central** (`AZURE_LOCATION`) | `gpt-4.1-mini` GlobalStandard and `gpt-5.4-mini` DataZoneStandard (EU data zone) are available. Hosted agents run there. It's also one of the three `computer-use-preview` regions if you add that model later. |
| Playwright workspace | **West Europe** (`PLAYWRIGHT_LOCATION`) | Playwright Workspaces only exists in `eastus`, `westus3`, `westeurope`, `eastasia`, `japaneast`, `australiaeast` and `switzerlandnorth`, and Sweden Central isn't one of them. West Europe keeps the cloud browsers in the EU, close to the project. The cross-region connection is verified working. |
| Monitoring, registry, demo site | `AZURE_LOCATION` | Close to the project. Nothing region-specific. |

Choose regions before the first `azd provision`. Changing them later creates new resources. Check quota and model
availability in any other region you pick.

---

## Policy considerations

Check your target subscription's policies before provisioning. The following are general considerations,
not observations about any organization's environment.

| Policy or control | What it does | Impact here |
|---|---|---|
| **Allowed resources, regions and SKUs** | Deny policies can block provisioning | Verify that the resource types, regions and SKUs in the templates are permitted. |
| **Disable local authentication** | Policies can require Entra ID instead of API keys | The template sets `disableLocalAuth: true`, and the demo uses Entra ID. |
| **Network isolation** | Policies can restrict public access | Check policies for `Microsoft.CognitiveServices/accounts`, kind `AIServices`; policies for other resource types may differ. |
| **MFA enforcement** | MFA required for resource write and delete | Run `azd provision`, `azd deploy` and `azd down` after an interactive MFA sign-in. |
| **Keyless by design** | | The Playwright connection uses `ProjectManagedIdentity`, the workspace has `localAuth: Disabled`, the registry has `adminUserEnabled: false`, and the demo site pulls images with a managed identity. Enabling `PLAYWRIGHT_LOCAL_AUTH` creates access tokens, so check your policy first. |

The Foundry layer also has optional network-isolation parameters (`enableNetworkIsolation` and related). Review
and validate those settings for your environment. Network injection can only be set when the Foundry account is created
([networking options](https://learn.microsoft.com/azure/foundry/agents/concepts/networking-options)).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| **401/403** from hooks or azd commands after it worked before | azd's sign-in was switched to another account or tenant (it's shared across terminals) | `azd auth login --tenant-id <external-tenant-id>` with the external-tenant account, then `azd auth login --check-status` |
| **azd suddenly targets another tenant** (401/403 or the wrong subscription), although nobody ran `azd auth login` | azd's config has `auth.useAzCliAuth: true`, so azd follows the Azure CLI's default account, and another terminal changed it | Scenario runs are unaffected: the CLI and console use the Azure CLI account that owns the subscription. For `azd provision` and `azd deploy`, [pin a terminal](#pin-one-terminal-to-the-external-tenant): an isolated `AZURE_CONFIG_DIR` (a copy of `~/.azure` with `az account set --subscription <external>`, plus `AZURE_EXTENSION_DIR` pointing to `~/.azure/cliextensions`) and an `AZD_CONFIG_DIR` whose config has `auth.useAzCliAuth` set to `true`. Or set it to `false` and use `azd auth login --tenant-id <external-tenant-id>`. |
| azd and the Azure CLI are signed in to **different tenants** (calls fail with 401/403 or "tenant not found") | Separate tools can retain different sign-ins | Supported by design: the hooks use `azd auth token`; the CLI and console try the Azure CLI account that owns `AZURE_SUBSCRIPTION_ID`, then azd, then the Azure CLI's default account. If none of them can reach the subscription, sign the Azure CLI in to the external tenant once (`az login --tenant <external-tenant-id>`), or sign azd in to it. To force one source, set `AZURE_TOKEN_CREDENTIALS=AzureCliCredential` (or `AzureDeveloperCliCredential`). |
| `ChainedTokenCredential failed ... AzureDeveloperCliCredential: ERROR: getting the subscription from system environment (AZURE_SUBSCRIPTION_ID): failed to resolve user '...' access to subscription ...` (seen in the Streamlit console) | azd follows the Azure CLI's default account (`auth.useAzCliAuth` is `true`), which is in another tenant and can't access the external subscription. The earlier credential chain stopped at that first `ClientAuthenticationError`, so later sources were never tried. | Fixed in this repo's `get_credential()`: the Azure CLI account that owns the subscription comes first, and failures fall through to the next source. Check that `az account get-access-token --subscription <id>` works; if not, run `az login --tenant <external-tenant-id>`. |
| `uv` fails with TLS handshake errors | Network or TLS inspection | Use `python -m pip install -e ".[ui]"` |
| `pip` can't build `cryptography` | ARM64 Python 3.12 on Windows has no wheel | Install an **x64** Python 3.11+ and recreate `.venv` |
| Hosted agent won't start locally | Python older than 3.11 | Use Python 3.11+ |
| Local mode: "Hosted agent environment not found" | The hosted agent's own virtual environment doesn't exist | `py -3.11 -m venv src\hosted_agent\.venv`, then `src\hosted_agent\.venv\Scripts\python -m pip install -r src\hosted_agent\requirements.txt`. Or point `LOCAL_AGENT_PYTHON` at another Python that has those packages. |
| Local mode: "The local agent exited with code ..." or "was not ready after 120s" | The agent server failed at start-up, for example a missing package, setting or sign-in | Read the server output printed with the error, and `runs/<run>/local-agent.log` (redacted) |
| `doctor` shows ➖ for "Local mode: Node.js / npx (local browser)" | Node.js isn't installed, or not on `PATH` | Install Node.js 18+, open a new terminal and run `doctor` again. `--remote-browser` doesn't need Node.js. |
| Local mode on macOS or Linux: the browser doesn't start | Outside Windows, Playwright MCP uses the Chrome channel | Install Google Chrome, or set `LOCAL_BROWSER` |
| Provision fails with `InsufficientQuota` or a quota error | Not enough TPM for the model and deployment type; other deployments in the subscription use it too | Run the [quota check](#3-check-model-quota). Lower the capacity in `azure.yaml` and `infra/foundry/main.parameters.json`, or change region or model. |
| `MissingSubscriptionRegistration` | A resource provider isn't registered (for example `Microsoft.LoadTestService` or `Microsoft.App`) | `az provider register --namespace <namespace>`, then provision again |
| Agent creation fails, or the tool isn't supported for the model | The model doesn't support Browser Automation (`gpt-5-mini`, `gpt-5-nano`, `gpt-5.1`, `gpt-5.2`, `computer-use-preview`) | Use `gpt-4.1-mini`, `gpt-5.4-mini` or another model from the [matrix](https://learn.microsoft.com/azure/foundry/agents/concepts/limits-quotas-regions#tool-support-by-region-and-model) |
| **403 on the toolbox** (hook: "Could not create a toolbox version"; runtime: MCP call rejected) | Role assignments not propagated yet, a missing project role, or the toolbox isn't published | Wait a few minutes, then `azd hooks run postprovision`. Check that you hold Foundry Project Manager and Foundry User on the project. Confirm the publish step succeeded. The deployed hosted agent needed no extra role in this deployment: its default agent identity could call the toolbox ([hosted agent permissions](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions)). |
| **`ToolTimeout`** on `browser_fill_form` / `browser_click` / `browser_wait_for`, and the **whole response fails** | The model guessed a CSS selector (for example `[aria-label=...]`) instead of a snapshot ref, used a stale ref, waited for text that never appeared, or clicked a control that doesn't respond. Each one takes about 60 s. | Ref-only instructions are already in place ("use snapshot refs only"), and the prompt-agent runner continues from the failed response with `previous_response_id` up to `limits.max_recoveries` times (2 by default). Both agents' instructions say to check loading with a fresh `browser_snapshot` instead of `browser_wait_for` with text. For short scenarios, retry with `--strong`; for long ones, use the hosted agent. Watch the live view to see the page state. The failed response reports `usage: None`, but its turns are billed, so check Azure Monitor metrics for real consumption. |
| Prompt agent run **fails after several `ToolTimeout`s and reports 0 tokens** | Every response failed, so the recoveries ran out and no response reported usage. Seen on `09-ui-bug-hunt`, whose wizard is broken on purpose: three `ToolTimeout`s used up 2 recoveries after 243.8 s. | Raise `limits.max_recoveries` for scenarios on broken pages (`09` uses 6, `11` uses 4). The instructions now say to record a defect after two failures on the same element and move on. Check Azure Monitor metrics for the tokens actually consumed. |
| Hosted agent **stops calling tools** after a few failed browser actions and answers early | Agent Framework's default `max_consecutive_errors_per_request` is 3. After that it asks for a final answer with `tool_choice="none"`. | `MAX_CONSECUTIVE_TOOL_ERRORS` (default 6 in `main.py`) raises the limit. Add it to the `env:` map of `web-qa-agent` in `azure.yaml` to change it, then run `azd deploy web-qa-agent`. |
| **429 "Model deployment rate limit exceeded"** in the middle of a long run | The deployment's TPM limit is shared by every run on it. Each call reserves `max_output_tokens` (5,000 for `09`) on top of its input. Running the prompt and hosted versions of `09` at the same time on a 100K-TPM deployment hit it. | Run long scenarios one at a time. Raise `capacity` in `azure.yaml` and `infra/foundry/main.parameters.json` (this repo now uses 300 for both models), then `azd provision`. Lower `max_output_tokens` for scenarios with short answers. |
| **Repeated 429s with `--strong`** (prompt mode on `gpt-5.4-mini`) on a long run, although Azure Monitor shows only about 17K to 26K input tokens per minute on the deployment | The agent service runs the tool loop server-side, and each internal model call reserves its output budget against the TPM limit. `PromptAgentDefinition` has no `max_output_tokens` field (its fields are `model`, `instructions`, `tools`, `temperature`, `top_p`, `reasoning`, `text`, `tool_choice`, `structured_inputs`, `skills` and `harness`), so that reservation can't be capped from the agent. Seen on `09` at 300K TPM. | Use `gpt-4.1-mini` for prompt-mode browser loops, the hosted agent for long runs, or much more capacity on the strong deployment if your quota allows. Keep `--strong` for short, reasoning-heavy scenarios (`03`, `04`, `13`). The runner backs off on rate-limit errors (20 s × attempt, at most 60 s) before continuing with `previous_response_id`; on `09` that worked, but the run still used up its 6 recoveries. |
| **Portal playground**: `ToolTimeout` on `browser_click` ends the turn, for example after switching an agent to `gpt-5.4-mini` | The model mangled a frame-prefixed ref (`f1e30` became `e30` or `e1f30`). A malformed ref is treated as a selector that matches nothing, so the action times out, which ends a prompt agent's turn. The `responsesapi` spans in Application Insights show it in `gen_ai.tool.call.arguments`. | Run `python -m demo_cli agents ensure` so the agents get the current instructions (copy refs character for character). Use `browser-automation-agent-gpt-5-4-mini` instead of switching the default agent's model in the portal. In the playground, reply "take a snapshot and continue" to resume in the same browser session ([01](01-browser-automation-tool.md#copy-refs-exactly-frame-prefixes)). |
| Hosted agent can't find elements: **no refs in tool results**, guessed selectors, "can't see the page" | Agent Framework's default `tool_result_content="structured_first"` returns only `structuredContent` (URL and title). The accessibility snapshot is in `content`. | Create the toolbox with `FoundryToolbox(credential, tool_result_content="content_first", allowed_tools=...)`, as `src/hosted_agent/main.py` does |
| Hosted agent fails with **`server_error: Cannot project a divergent replacement text snapshot onto an append-only Responses stream`** | A known issue in `agent-framework-foundry-hosting` 1.0.0b261015. Middleware that rewrites the streamed text triggers it, but it also happened **without any middleware**, on `09`, after consecutive tool errors stopped the tool loop. The root cause isn't identified. | Don't modify the response stream (this repo deleted its `live_view.py` middleware). Keep `apply_text_projection_fix()` in `main.py`: `text_projection_fix.py` makes the replacement the final text instead of failing the response, and switches itself off once the package is fixed. Streaming clients may briefly show superseded text. See [known issues](01-browser-automation-tool.md#6-known-issues-in-the-current-preview-hosting-stack). |
| Hosted agent reports **implausibly high token usage** (roughly 10 times what the work suggests) | `agent-framework-foundry-hosting` 1.0.0b261015 adds up the cumulative usage snapshots that `agent-framework-core` 1.22.0 streams. Billing follows real usage; only the reported number is wrong. | Keep `usage_fix.apply()` in `main.py` (it switches itself off once the package is fixed). Check the `gen_ai.usage.*` attributes of the agent's `chat` spans in Application Insights, or Azure Monitor `InputTokens` metrics. Ignore hosted runs in `runs/` recorded before 13:15 UTC on 2026-10-26. |
| Prompts, page snapshots or the live view link show up in **Application Insights** | `azure-ai-agentserver-core` defaults message-content capture to `true`. Hosted agent versions before v3 used that default, or `CAPTURE_MESSAGE_CONTENT` is set to `true`. | `azd env set CAPTURE_MESSAGE_CONTENT false`, then `azd deploy web-qa-agent`. Data already ingested stays until retention (30 days) expires. |
| Computer Use: **401/403** on `<account>.openai.azure.com` | No inference role at account scope. Project-scoped Foundry roles don't cover the account-level endpoint. | Run `azd provision` again (Bicep now assigns Cognitive Services OpenAI User at account scope), or assign Cognitive Services OpenAI User, or Foundry User at account scope or above, yourself. Allow a few minutes for propagation. |
| Computer Use: the **second** turn fails with **`400 Invalid URI: The Uri string is too long`** | The loop called the **project-scoped** endpoint (`.../api/projects/<project>/openai/v1`), which parses the base64 screenshot in `computer_call_output` (over about 64 KB) as a URI | Use the **account-level** endpoint `https://<account>.openai.azure.com/openai/v1/` with a token for `https://cognitiveservices.azure.com/.default`. The runner does this using `AZURE_OPENAI_ENDPOINT` from `.env`. |
| A long action fails after about 100 s | The Foundry non-streaming MCP client timeout is 100 s; the service command limit is 3.5 min | Split the work into smaller steps. Avoid long waits. |
| Hosted agent version **failed** after `azd deploy` | Remote build or start-up error (dependencies, missing environment variable, import error) | Read the version's `error.message` (see the snippet below), `azd ai agent show`, or the Foundry portal. Stream logs with `azd ai agent monitor --follow`. |
| `doctor`: "Demo site healthy" fails or times out | Cold start (`minReplicas: 0`), or the placeholder image is still running because `demo-site` isn't deployed | Retry, or run `azd deploy demo-site`. For live demos: `azd env set DEMO_SITE_MIN_REPLICAS 1`, then `azd provision`. |
| The demo site shows the Container Apps **quickstart page** | The app still runs the placeholder image: `demo-site` hasn't been deployed in this environment yet | `azd deploy demo-site`. After that, `azd provision` keeps the deployed image (verified). |
| `doctor`: connection ID or endpoint missing | No `.env` yet, or it was deleted | `azd hooks run postprovision` |
| Web console: "The web console needs FastAPI and uvicorn" | The `ui` extra isn't installed (the old `console` extra is gone) | `pip install -e ".[ui]"` |
| Web console: "Port 8765 is already in use" | Another console, or another app, uses the port | `python -m web_console --port <another port>` |
| Web console: the live view doesn't open beside the console | The browser blocked the pop-up (the console then shows a button), or the console runs in a browser panel embedded in an app (WebView2), which refuses new windows. The live-view page can't be embedded (`X-Frame-Options: DENY`). | Allow pop-ups for `http://127.0.0.1:8765`, or click the button. In an app panel, open the console in Edge or Chrome instead. Local and Computer Use previews work anywhere. |
| Web console: 403 "Missing or stale console token: reload the page" | The console restarted, and its per-process API token changed | Reload the page |
| Web console: 421 "This console only answers on its loopback address" | The console was opened through another host name or address | Open `http://127.0.0.1:8765` (or `localhost`) on the same machine |
| Web console: "A run is already in progress" | One run at a time; a started response can't be cancelled | Wait for the run to finish. In **Compare**, use **stop after current**. |
| "Refusing to run: '<host>' is not in allowed_domains" | Security scenarios only target allow-listed hosts | This is intended. Add hosts you own or are authorized to test. |
| Run blocked **before any tool call** with `content_filter` (jailbreak) | Azure AI Content Safety Prompt Shields read the task wording as a jailbreak attempt. Observed with "relax only the language filter" in `05`. | Rephrase neutrally, for example "search again without the language criterion". The CLI prints a hint for `content_filter` blocks. |
| Computer Use: `Executable doesn't exist` | Chromium isn't installed for Playwright | `python -m playwright install chromium` |
| Computer Use run ends with status `blocked` | The model raised `pending_safety_checks` | Review the checks. Use `--auto-ack` only against your own demo site. |
| Computer Use: "Remote browser needs PLAYWRIGHT_SERVICE_ACCESS_TOKEN" | `--remote-browser` needs workspace access tokens | Prefer the local browser. Otherwise set `PLAYWRIGHT_LOCAL_AUTH=Enabled`, run `azd provision`, create a token and export it (experimental). |
| Warning "Endpoint rejected 'max_tool_calls'" | That endpoint doesn't accept the parameter | No action needed: the runner retries without it. |
| Re-provision fails because the account name is taken | A soft-deleted Foundry account from an earlier `azd down` without `--purge` | `az cognitiveservices account list-deleted`, then `az cognitiveservices account purge ...` |
| Budget deployment fails | Budget permissions or offer type | `azd env set ENABLE_BUDGET false`, then create the budget in the portal |

Check a hosted agent version's status with azd's token:

```powershell
$token = (azd auth token --scope "https://ai.azure.com/.default" --output json | ConvertFrom-Json).token
$ep = azd env get-value FOUNDRY_PROJECT_ENDPOINT
$versions = Invoke-RestMethod -Headers @{ Authorization = "Bearer $token" } -Uri "$ep/agents/web-qa-agent/versions?api-version=v1"
$versions.data | Select-Object version, status                                    # creating | active | failed | ...
$v = Invoke-RestMethod -Headers @{ Authorization = "Bearer $token" } -Uri "$ep/agents/web-qa-agent/versions/<version>?api-version=v1"
$v.status; $v.error.message                                                       # error is populated when status is failed
```

---

## Teardown

```powershell
azd down --purge          # deletes both resource groups and purges the soft-deleted Foundry account
```

The validation environment's teardown took 32 min 39 s. It deleted both resource groups and purged Log Analytics and
the Foundry account, but **not the budget**: subscription-scope budgets survive `azd down --purge`. Delete your own
budgets (one per month in which you provisioned) and nobody else's:

```powershell
az consumption budget list --query "[?starts_with(name, 'budget-<env>-')].name" -o tsv
az consumption budget delete --budget-name budget-<env>-<yyyymm>
```

Then clean up local files (`runs/`, `.env`, `.azure/<env>/`). The full checklist is in
[04-cost-management.md](04-cost-management.md#cleanup-checklist).
