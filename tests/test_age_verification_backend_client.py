from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from rob.services.age_verification_backend_client import (
    AgeVerificationBackendClient,
    AgeVerificationBackendClientError,
)


@pytest.mark.asyncio
async def test_backend_client_preserves_http_error(tmp_path):
    async def start(_request: web.Request) -> web.Response:
        return web.Response(text="<html>bad gateway</html>", status=502)

    app = web.Application()
    app.router.add_post("/age-verification/start", start)

    async with TestServer(app) as server:
        client = AgeVerificationBackendClient(
            base_url=str(server.make_url("")).rstrip("/"),
            secret="shared",
        )

        with pytest.raises(
            AgeVerificationBackendClientError,
            match="returned HTTP 502",
        ):
            await client.start(guild_id=123, discord_user_id=456)
