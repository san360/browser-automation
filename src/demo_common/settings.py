"""Configuration and credentials.

Values are resolved in this order: process environment > repo-root .env (written by the azd
postprovision hook) > `azd env get-values` (when azd is available). Nothing secret is stored.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = REPO_ROOT / "scenarios"
RUNS_DIR = REPO_ROOT / "runs"


def _azd_env_values() -> dict[str, str]:
    if not shutil.which("azd") or not (REPO_ROOT / "azure.yaml").exists():
        return {}
    try:
        out = subprocess.run(
            ["azd", "env", "get-values"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    values: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"')
    return values


@lru_cache(maxsize=1)
def load_environment() -> dict[str, str]:
    """Merge azd values, .env and the process environment and export them to os.environ."""
    merged: dict[str, str] = {}
    env_file = REPO_ROOT / ".env"
    file_values = {k: v for k, v in dotenv_values(env_file).items() if v is not None} if env_file.exists() else {}
    if "FOUNDRY_PROJECT_ENDPOINT" not in os.environ and "FOUNDRY_PROJECT_ENDPOINT" not in file_values:
        merged.update(_azd_env_values())
    merged.update(file_values)
    merged.update(dict(os.environ))
    for key, value in merged.items():
        os.environ.setdefault(key, value)
    return merged


@dataclass
class Settings:
    project_endpoint: str
    tenant_id: str | None = None
    prompt_model: str = "gpt-4.1-mini"
    strong_model: str = "gpt-5.4-mini"
    computer_use_model: str = "gpt-5.4-mini"
    prompt_agent_name: str = "browser-automation-agent"
    hosted_agent_name: str = "web-qa-agent"
    browser_connection_id: str = ""
    toolbox_name: str = "browser-automation-tools"
    demo_site_url: str = ""
    playwright_browser_endpoint: str = ""
    playwright_access_token: str | None = field(default=None, repr=False)
    applicationinsights_connection_string: str | None = field(default=None, repr=False)
    subscription_id: str | None = None
    resource_groups: list[str] = field(default_factory=list)
    openai_endpoint: str = ""

    @property
    def demo_site_host(self) -> str:
        return urlparse(self.demo_site_url).hostname or ""

    @property
    def openai_v1_base_url(self) -> str:
        """Account-level Azure OpenAI v1 endpoint (used by the client-executed Computer Use loop)."""
        endpoint = self.openai_endpoint
        if not endpoint and self.project_endpoint:
            host = urlparse(self.project_endpoint).hostname or ""
            endpoint = "https://" + host.replace(".services.ai.azure.com", ".openai.azure.com")
        return endpoint.rstrip("/") + "/openai/v1/" if endpoint else ""


def get_settings() -> Settings:
    env = load_environment()
    endpoint = env.get("FOUNDRY_PROJECT_ENDPOINT") or env.get("AZURE_AI_PROJECT_ENDPOINT") or ""
    rgs = [rg for rg in (env.get("AZURE_FOUNDRY_RESOURCE_GROUP"), env.get("AZURE_PLATFORM_RESOURCE_GROUP")) if rg]
    return Settings(
        project_endpoint=endpoint,
        tenant_id=env.get("AZURE_TENANT_ID") or None,
        prompt_model=env.get("PROMPT_AGENT_MODEL", "gpt-4.1-mini"),
        strong_model=env.get("STRONG_MODEL", "gpt-5.4-mini"),
        computer_use_model=env.get("COMPUTER_USE_MODEL", "gpt-5.4-mini"),
        prompt_agent_name=env.get("PROMPT_AGENT_NAME", "browser-automation-agent"),
        hosted_agent_name=env.get("HOSTED_AGENT_NAME", "web-qa-agent"),
        browser_connection_id=env.get("BROWSER_AUTOMATION_PROJECT_CONNECTION_ID", ""),
        toolbox_name=env.get("TOOLBOX_NAME", "browser-automation-tools"),
        demo_site_url=env.get("DEMO_SITE_URL", "").rstrip("/"),
        playwright_browser_endpoint=env.get("PLAYWRIGHT_BROWSER_ENDPOINT", ""),
        playwright_access_token=env.get("PLAYWRIGHT_SERVICE_ACCESS_TOKEN") or None,
        applicationinsights_connection_string=env.get("APPLICATIONINSIGHTS_CONNECTION_STRING") or None,
        subscription_id=env.get("AZURE_SUBSCRIPTION_ID") or None,
        resource_groups=rgs,
        openai_endpoint=env.get("AZURE_OPENAI_ENDPOINT", ""),
    )


class FallThroughCredential:
    """Let ChainedTokenCredential try the next source when this one fails to authenticate.

    ChainedTokenCredential stops at the first ClientAuthenticationError (for example azd signed in to another tenant:
    "failed to resolve user ... access to subscription"), so a working source further down is never tried. This wrapper
    reports such failures as CredentialUnavailableError instead.
    """

    def __init__(self, credential) -> None:
        self.credential = credential

    def _call(self, method: str, *args, **kwargs):
        from azure.core.exceptions import ClientAuthenticationError
        from azure.identity import CredentialUnavailableError

        try:
            return getattr(self.credential, method)(*args, **kwargs)
        except CredentialUnavailableError:
            raise
        except ClientAuthenticationError as exc:
            raise CredentialUnavailableError(message=f"{type(self.credential).__name__}: {exc.message}") from exc

    def get_token(self, *scopes, **kwargs):
        return self._call("get_token", *scopes, **kwargs)

    def get_token_info(self, *scopes, options=None):
        return self._call("get_token_info", *scopes, options=options)

    def close(self) -> None:
        close = getattr(self.credential, "close", None)
        if close:
            close()

    def __enter__(self) -> "FallThroughCredential":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def get_credential():
    """Credential chain for developer machines that are signed in to several tenants.

    1. Azure CLI, for the account that owns AZURE_SUBSCRIPTION_ID, even when the CLI's default account is in another
       tenant (the same as `az account get-access-token --subscription <id>`).
    2. Azure Developer CLI, then the Azure CLI's default account, both for AZURE_TENANT_ID.
    3. The other DefaultAzureCredential sources (environment, managed identity, ...).
    A source that fails no longer stops the chain. Set AZURE_TOKEN_CREDENTIALS (e.g. 'AzureCliCredential', 'dev',
    'prod') to let DefaultAzureCredential decide instead.
    """
    from azure.identity import AzureCliCredential, AzureDeveloperCliCredential, ChainedTokenCredential, DefaultAzureCredential

    load_environment()
    if os.getenv("AZURE_TOKEN_CREDENTIALS"):
        return DefaultAzureCredential()
    tenant = os.getenv("AZURE_TENANT_ID") or None
    subscription = os.getenv("AZURE_SUBSCRIPTION_ID") or None
    sources: list = []
    if subscription:
        sources.append(FallThroughCredential(AzureCliCredential(subscription=subscription, process_timeout=30)))
    sources += [
        FallThroughCredential(AzureDeveloperCliCredential(tenant_id=tenant, process_timeout=30)),
        FallThroughCredential(AzureCliCredential(tenant_id=tenant, process_timeout=30)),
        DefaultAzureCredential(exclude_cli_credential=True, exclude_developer_cli_credential=True),
    ]
    return ChainedTokenCredential(*sources)
