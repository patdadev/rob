from __future__ import annotations

from typing import Any

from aiohttp import ClientResponseError, ClientSession, ClientTimeout


class AgeVerificationBackendClientError(RuntimeError):
    """Raised when the backend age-verification bridge fails."""


class AgeVerificationBackendClient:
    def __init__(
        self,
        *,
        base_url: str | None,
        secret: str | None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.secret = secret
        self.timeout_seconds = timeout_seconds

    async def start(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/age-verification/start",
            json_payload={
                "guild_id": int(guild_id),
                "discord_user_id": int(discord_user_id),
            },
        )

    async def status(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/age-verification/status",
            params={
                "guild_id": str(int(guild_id)),
                "discord_user_id": str(int(discord_user_id)),
            },
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.base_url:
            raise AgeVerificationBackendClientError(
                "ROB_BACKEND_URL is not configured."
            )
        if not self.secret:
            raise AgeVerificationBackendClientError(
                "ROB_BACKEND_SECRET is not configured."
            )
        headers = {"Authorization": f"Bearer {self.secret}"}
        timeout = ClientTimeout(total=self.timeout_seconds)
        url = f"{self.base_url}{path}"
        try:
            async with ClientSession(timeout=timeout) as session:
                async with session.request(
                    method,
                    url,
                    params=params,
                    json=json_payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
        except ClientResponseError as exc:
            raise AgeVerificationBackendClientError(
                f"Age verification backend returned HTTP {exc.status}."
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive network handling
            raise AgeVerificationBackendClientError(
                "Rob couldn't reach the age verification backend."
            ) from exc
        if not isinstance(data, dict):
            raise AgeVerificationBackendClientError(
                "Age verification backend returned an unexpected response."
            )
        return data
