"""Actual Azure spend for the demo resource groups (Azure Cost Management Query API)."""

from __future__ import annotations

import httpx

from demo_common.settings import Settings, get_credential

API = "https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"


def month_to_date_by_service(settings: Settings) -> dict[str, list[tuple[str, float, str]]]:
    """Return {resource_group: [(service, cost, currency), ...]} for the current month. Data lags by ~8-24h."""
    if not settings.subscription_id or not settings.resource_groups:
        raise RuntimeError("AZURE_SUBSCRIPTION_ID and resource groups are unknown; run `azd provision` first.")
    token = get_credential().get_token("https://management.azure.com/.default").token
    body = {
        "type": "ActualCost",
        "timeframe": "MonthToDate",
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [{"type": "Dimension", "name": "ServiceName"}],
        },
    }
    results: dict[str, list[tuple[str, float, str]]] = {}
    with httpx.Client(timeout=60, headers={"Authorization": f"Bearer {token}"}) as client:
        for rg in settings.resource_groups:
            response = client.post(API.format(sub=settings.subscription_id, rg=rg), json=body)
            if response.status_code >= 400:
                results[rg] = [(f"error {response.status_code}: {response.text[:160]}", 0.0, "")]
                continue
            props = response.json().get("properties", {})
            columns = [c["name"] for c in props.get("columns", [])]
            rows = []
            for row in props.get("rows", []):
                record = dict(zip(columns, row))
                rows.append((record.get("ServiceName", "?"), float(record.get("Cost", 0.0)), record.get("Currency", "")))
            results[rg] = sorted(rows, key=lambda r: -r[1])
    return results
