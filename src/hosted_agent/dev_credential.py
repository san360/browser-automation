"""Credential for the web QA agent.

In Foundry the agent runs with its managed identity (DefaultAzureCredential). Local runs started by
`python -m demo_cli run ... --mode local` set AZURE_CLI_SUBSCRIPTION: the Azure CLI then uses the account that owns that
subscription even when its default account is in another tenant, and a failing source no longer stops the chain.
This mirrors demo_common.settings.get_credential, which the CLI and console use.
"""

from __future__ import annotations

import os

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import (
    AzureCliCredential,
    AzureDeveloperCliCredential,
    ChainedTokenCredential,
    CredentialUnavailableError,
    DefaultAzureCredential,
)


class FallThroughCredential:
    """Report authentication failures as CredentialUnavailableError so ChainedTokenCredential tries the next source."""

    def __init__(self, credential) -> None:
        self.credential = credential

    def _call(self, method: str, *args, **kwargs):
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


def build_credential():
    subscription = os.getenv("AZURE_CLI_SUBSCRIPTION")
    if not subscription:
        return DefaultAzureCredential()
    tenant = os.getenv("AZURE_TENANT_ID") or None
    return ChainedTokenCredential(
        FallThroughCredential(AzureCliCredential(subscription=subscription, process_timeout=30)),
        FallThroughCredential(AzureDeveloperCliCredential(tenant_id=tenant, process_timeout=30)),
        DefaultAzureCredential(exclude_cli_credential=True, exclude_developer_cli_credential=True),
    )
