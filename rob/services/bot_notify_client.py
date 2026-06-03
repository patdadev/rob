from __future__ import annotations

import logging

from aiohttp import ClientError, ClientSession, ClientTimeout

log = logging.getLogger(__name__)


async def notify_bot_send(
    *,
    notify_url: str | None,
    secret: str | None,
    send_id: int,
    guild_id: int,
    timeout_seconds: float = 5.0,
) -> bool:
    if not notify_url:
        return False

    headers: dict[str, str] = {}
    if secret:
        headers["X-Rob-Ops-Secret"] = secret

    payload = {"send_id": int(send_id), "guild_id": int(guild_id)}
    timeout = ClientTimeout(total=timeout_seconds)
    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.post(notify_url, json=payload, headers=headers) as response:
                if 200 <= response.status < 300:
                    return True
                body = await response.text()
                log.warning(
                    "Bot send notification failed status=%s send_id=%s guild_id=%s response=%s",
                    response.status,
                    send_id,
                    guild_id,
                    body[:200],
                )
                return False
    except (ClientError, TimeoutError):
        log.exception(
            "Bot send notification failed send_id=%s guild_id=%s.",
            send_id,
            guild_id,
        )
        return False
