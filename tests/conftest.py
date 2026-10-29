import os

# Deterministic environment for tests (no Azure calls are made by the unit tests). Force the values so a shell that
# has loaded a real azd environment (scripts/use-azd-env.ps1) cannot change test behaviour.
os.environ["DEMO_SITE_URL"] = "https://demo.contoso.example"
os.environ["DEMO_SITE_HOST"] = "demo.contoso.example"
os.environ["FOUNDRY_PROJECT_ENDPOINT"] = "https://unit-test.services.ai.azure.com/api/projects/test"
os.environ.pop("ALLOWED_SCAN_HOSTS", None)
