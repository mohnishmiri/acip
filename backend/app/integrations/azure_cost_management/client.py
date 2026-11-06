"""Azure Resource Manager / Cost Management access for the collection identity.

Used for:
  * subscription discovery and per-subscription access validation,
  * validating Cost Management read permission (tiny query, admin-triggered only),
  * listing configured exports (read-only),
  * optional Cost Details API report generation for backfill,
  * optional Azure Advisor cost recommendations and Activity Log lookups.

The dashboards never call these APIs; all reporting reads PostgreSQL.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import httpx

from app.core.config import get_settings
from app.integrations.azure_auth.credentials import ARM_SCOPE, get_credential

log = logging.getLogger(__name__)

API_SUBSCRIPTIONS = "2022-12-01"
API_COST_QUERY = "2023-11-01"
API_EXPORTS = "2023-11-01"
API_COST_DETAILS = "2023-11-01"
API_ADVISOR = "2023-01-01"
API_ACTIVITY = "2015-04-01"


class ArmError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class ArmClient:
    def __init__(self, credential=None):
        s = get_settings()
        self.credential = credential or get_credential()
        self.base = s.azure_arm_endpoint.rstrip("/")
        self.timeout = s.azure_http_timeout_seconds

    def _headers(self) -> dict[str, str]:
        token = self.credential.get_token(ARM_SCOPE).token
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def request(self, method: str, path: str, *, params: dict | None = None, json: Any = None, retries: int = 3) -> httpx.Response:
        url = path if path.startswith("http") else f"{self.base}{path}"
        attempt = 0
        while True:
            attempt += 1
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(method, url, params=params, json=json, headers=self._headers())
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < retries:
                    wait = int(resp.headers.get("Retry-After", "0") or 0) or min(2 ** attempt, 30)
                    # Cost Management returns x-ms-ratelimit-microsoft.costmanagement-*-retry-after
                    for h, v in resp.headers.items():
                        if h.lower().endswith("retry-after") and v.isdigit():
                            wait = max(wait, int(v))
                    log.warning("ARM throttled/failed; retrying", extra={"status": resp.status_code, "wait_s": wait, "url": url.split("?")[0]})
                    time.sleep(min(wait, 60))
                    continue
            return resp

    @staticmethod
    def raise_for(resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        code, message = "Error", resp.text[:500]
        try:
            err = resp.json().get("error", {})
            code, message = err.get("code", code), err.get("message", message)
        except Exception:  # noqa: BLE001
            pass
        raise ArmError(resp.status_code, code, message)

    # ---------------------------------------------------------------------------------
    def list_subscriptions(self) -> list[dict[str, Any]]:
        resp = self.request("GET", "/subscriptions", params={"api-version": API_SUBSCRIPTIONS})
        self.raise_for(resp)
        return resp.json().get("value", [])

    def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        resp = self.request("GET", f"/subscriptions/{subscription_id}", params={"api-version": API_SUBSCRIPTIONS})
        self.raise_for(resp)
        return resp.json()

    def cost_query_probe(self, subscription_id: str, day: date) -> dict[str, Any]:
        """Minimal one-day aggregate query that validates Cost Management read access."""
        body = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {"from": f"{day.isoformat()}T00:00:00Z", "to": f"{day.isoformat()}T23:59:59Z"},
            "dataset": {"granularity": "None", "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}}},
        }
        resp = self.request(
            "POST",
            f"/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query",
            params={"api-version": API_COST_QUERY},
            json=body,
            retries=2,
        )
        self.raise_for(resp)
        return resp.json()

    def list_exports(self, subscription_id: str) -> list[dict[str, Any]]:
        resp = self.request(
            "GET",
            f"/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/exports",
            params={"api-version": API_EXPORTS},
        )
        self.raise_for(resp)
        return resp.json().get("value", [])

    def generate_cost_details(self, subscription_id: str, metric: str, start: date, end: date, poll_seconds: int = 20, max_wait_seconds: int = 1800) -> list[str]:
        """Cost Details API: asynchronous report generation (max one month per request).

        Returns the blob URLs (time-limited SAS links on Microsoft-managed storage) of the
        generated CSV files, or an empty list when Azure reports no data for the range.
        No customer storage account is involved.
        """
        body = {"metric": metric, "timePeriod": {"start": start.isoformat(), "end": end.isoformat()}}
        resp = self.request(
            "POST",
            f"/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/generateCostDetailsReport",
            params={"api-version": API_COST_DETAILS},
            json=body,
        )
        self.raise_for(resp)
        if resp.status_code == 204:
            return []
        payload: dict[str, Any] = {}
        if resp.status_code == 200 and resp.content:
            payload = resp.json()
        else:
            location = resp.headers.get("Location") or resp.headers.get("location")
            if not location:
                raise ArmError(resp.status_code, "NoLocation", "Cost Details API did not return an operation location")
            waited = 0
            wait = self._retry_after(resp, poll_seconds)
            while True:
                time.sleep(wait)
                waited += wait
                poll = self.request("GET", location)
                self.raise_for(poll)
                if poll.status_code == 204:
                    return []
                if poll.status_code == 200 and poll.content:
                    payload = poll.json()
                    status = str(payload.get("status", "")).lower()
                    if status in ("completed", "succeeded", "nodatafound", "failed", "canceled", "cancelled", "timedout", ""):
                        break
                if waited > max_wait_seconds:
                    raise ArmError(408, "Timeout", "Cost Details report generation timed out")
                wait = self._retry_after(poll, poll_seconds)
        status = str(payload.get("status", "completed")).lower()
        if status == "nodatafound":
            return []
        if status not in ("completed", "succeeded"):
            err = payload.get("error") or {}
            raise ArmError(500, payload.get("status", "Failed"), err.get("message") or f"Cost Details report finished with status {payload.get('status')}")
        blobs = (payload.get("manifest") or {}).get("blobs", [])
        return [b["blobLink"] for b in blobs if b.get("blobLink")]

    @staticmethod
    def _retry_after(resp: httpx.Response, default: int) -> int:
        v = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        try:
            return max(5, min(int(v), 120)) if v else default
        except ValueError:
            return default

    def list_advisor_cost_recommendations(self, subscription_id: str) -> list[dict[str, Any]]:
        resp = self.request(
            "GET",
            f"/subscriptions/{subscription_id}/providers/Microsoft.Advisor/recommendations",
            params={"api-version": API_ADVISOR, "$filter": "Category eq 'Cost'"},
        )
        self.raise_for(resp)
        return resp.json().get("value", [])

    def list_activity_log(self, subscription_id: str, resource_id: str, start: date, end: date) -> list[dict[str, Any]]:
        flt = (
            f"eventTimestamp ge '{start.isoformat()}T00:00:00Z' and eventTimestamp le '{end.isoformat()}T23:59:59Z' "
            f"and resourceUri eq '{resource_id}'"
        )
        resp = self.request(
            "GET",
            f"/subscriptions/{subscription_id}/providers/Microsoft.Insights/eventtypes/management/values",
            params={"api-version": API_ACTIVITY, "$filter": flt, "$select": "eventTimestamp,operationName,status,caller,resourceId,level"},
        )
        self.raise_for(resp)
        return resp.json().get("value", [])
