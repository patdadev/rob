from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class BotOpsResponse:
    ok: bool
    status_code: int | None
    payload: dict
    error: str | None = None


class BotOpsClient:
    def __init__(self, *, host: str, port: int, secret: str | None) -> None:
        self.base_url = f"http://{host}:{port}"
        self.secret = secret or ""

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.secret:
            headers["X-Rob-Ops-Secret"] = self.secret
        return headers

    def _request(self, method: str, path: str, *, json_payload: dict | None = None) -> BotOpsResponse:
        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.request(
                    method=method,
                    url=f"{self.base_url}{path}",
                    headers=self._headers(),
                    json=json_payload,
                )
        except httpx.ConnectTimeout:
            return BotOpsResponse(ok=False, status_code=None, payload={}, error="Timed out")
        except httpx.ConnectError as exc:
            message = str(exc).lower()
            if "name or service not known" in message or "nodename nor servname provided" in message:
                return BotOpsResponse(ok=False, status_code=None, payload={}, error="DNS lookup failed")
            if "connection refused" in message:
                return BotOpsResponse(ok=False, status_code=None, payload={}, error="Connection refused")
            return BotOpsResponse(ok=False, status_code=None, payload={}, error="Connection failed")
        try:
            payload = response.json()
        except ValueError:
            return BotOpsResponse(
                ok=False,
                status_code=response.status_code,
                payload={},
                error=f"Invalid JSON response (HTTP {response.status_code})",
            )
        error: str | None = None
        if response.status_code == 403:
            error = "Forbidden - check ROB_OPS_SECRET"
        elif response.status_code >= 500:
            error = f"HTTP {response.status_code} - bot ops bridge error"
        elif response.status_code >= 400:
            error = f"HTTP {response.status_code}"
        return BotOpsResponse(ok=response.status_code < 400, status_code=response.status_code, payload=payload, error=error)

    def health(self) -> BotOpsResponse:
        return self._request("GET", "/health")

    def refresh_public_names(self, guild_id: int) -> BotOpsResponse:
        return self._request("POST", f"/guilds/{guild_id}/leaderboard/public/refresh-names")

    def refresh_leaderboard(self, guild_id: int) -> BotOpsResponse:
        return self._request("POST", f"/guilds/{guild_id}/leaderboard/refresh")

    def set_maintenance(self, *, enabled: bool, reason: str | None = None) -> BotOpsResponse:
        payload = {"enabled": enabled, "reason": reason or ""}
        return self._request("POST", "/maintenance", json_payload=payload)
