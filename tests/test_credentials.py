"""Tests for the developer credential chain used on machines signed in to several tenants."""

import pytest
from azure.core.credentials import AccessToken, AccessTokenInfo
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import AzureCliCredential, ChainedTokenCredential, CredentialUnavailableError, DefaultAzureCredential

import dev_credential
from demo_common import settings

SUBSCRIPTION = "00000000-0000-0000-0000-000000000001"


class Failing:
    """Like azd signed in to another tenant: a hard authentication error."""

    def get_token(self, *scopes, **kwargs):
        raise ClientAuthenticationError(message="failed to resolve user access to subscription")

    def get_token_info(self, *scopes, options=None):
        raise ClientAuthenticationError(message="failed to resolve user access to subscription")


class Working:
    def get_token(self, *scopes, **kwargs):
        return AccessToken("token", 9999999999)

    def get_token_info(self, *scopes, options=None):
        return AccessTokenInfo("token", 9999999999)


@pytest.mark.parametrize("wrapper", [settings.FallThroughCredential, dev_credential.FallThroughCredential])
def test_failing_source_no_longer_stops_the_chain(wrapper):
    with pytest.raises(CredentialUnavailableError):
        wrapper(Failing()).get_token("scope")
    # Without the wrapper ChainedTokenCredential gives up at the first ClientAuthenticationError.
    with pytest.raises(ClientAuthenticationError):
        ChainedTokenCredential(Failing(), Working()).get_token("https://ai.azure.com/.default")
    chain = ChainedTokenCredential(wrapper(Failing()), Working())
    assert chain.get_token("https://ai.azure.com/.default").token == "token"
    assert chain.get_token_info("https://ai.azure.com/.default").token == "token"


def test_cli_and_console_prefer_the_cli_account_that_owns_the_subscription(monkeypatch):
    monkeypatch.delenv("AZURE_TOKEN_CREDENTIALS", raising=False)
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", SUBSCRIPTION)
    chain = settings.get_credential()
    first = chain.credentials[0]
    assert isinstance(first, settings.FallThroughCredential)
    assert isinstance(first.credential, AzureCliCredential) and first.credential.subscription == SUBSCRIPTION


def test_hosted_agent_credential(monkeypatch):
    monkeypatch.delenv("AZURE_CLI_SUBSCRIPTION", raising=False)
    assert isinstance(dev_credential.build_credential(), DefaultAzureCredential)  # Foundry: managed identity
    monkeypatch.setenv("AZURE_CLI_SUBSCRIPTION", SUBSCRIPTION)
    chain = dev_credential.build_credential()
    assert chain.credentials[0].credential.subscription == SUBSCRIPTION
