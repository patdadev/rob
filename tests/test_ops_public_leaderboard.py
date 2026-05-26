from __future__ import annotations

import asyncio
from types import SimpleNamespace

from scripts.ops import build_parser, handle_leaderboard


def test_public_parser_create_and_rotate():
    args = build_parser().parse_args(["leaderboard", "public", "create", "--guild-id", "1", "--title", "Send Leaderboard"])
    assert args.leaderboard_command == "public"
    assert args.leaderboard_public_command == "create"


class _Repo:
    def __init__(self):
        self.created = None
        self.rotated = None

    async def create(self, **kwargs):
        self.created = kwargs
        return SimpleNamespace(public_token="tok", guild_id=kwargs["guild_id"], title=kwargs["title"], enabled=True, created_at="c", updated_at="u")

    async def list_for_guild(self, guild_id: int):
        return []

    async def set_enabled(self, *, token: str, enabled: bool):
        return None

    async def rotate_token(self, *, token: str, new_token: str):
        self.rotated = (token, new_token)
        return SimpleNamespace(public_token="newtok")


def test_public_create_and_rotate_outputs_url(capsys):
    repo = _Repo()
    ctx = SimpleNamespace(settings=SimpleNamespace(rob_public_base_url="https://rob-dev.barecoding.com"), public_leaderboards=repo)
    create_args = SimpleNamespace(leaderboard_command="public", leaderboard_public_command="create", guild_id=1, title="Send Leaderboard")
    rotate_args = SimpleNamespace(leaderboard_command="public", leaderboard_public_command="rotate-token", token="tok")
    asyncio.run(handle_leaderboard(ctx, create_args))
    out = capsys.readouterr().out
    assert "https://rob-dev.barecoding.com/public/leaderboard/" in out
    asyncio.run(handle_leaderboard(ctx, rotate_args))
    out2 = capsys.readouterr().out
    assert "Public Leaderboard Token Rotated" in out2


def test_create_context_sets_public_leaderboards(monkeypatch):
    from scripts import ops as ops_module

    class _FakeSettings:
        database_url = "postgresql://example"
        throne_test_gifter_usernames: tuple[str, ...] = ()

    class _FakeDatabase:
        def __init__(self, _url: str):
            self.url = _url

        async def connect(self):
            return None

    monkeypatch.setattr(ops_module, "load_base_settings", lambda: _FakeSettings())
    monkeypatch.setattr(ops_module, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ops_module, "Database", _FakeDatabase)

    ctx = asyncio.run(ops_module.create_context())

    assert ctx.public_leaderboards is not None
