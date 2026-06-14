from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace


from rob.discord.cogs.registration import RegistrationCog


class _FakeResponse:
    def __init__(self):
        self.messages: list[dict] = []
        self.modal = None

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)

    async def send_modal(self, modal):
        self.modal = modal


class _FakeUser:
    def __init__(self, user_id: int = 123):
        self.id = user_id
        self.display_name = f"user-{user_id}"
        self.name = f"user-{user_id}"


class _FakeInteraction:
    def __init__(self, *, user: _FakeUser | None = None):
        self.guild = SimpleNamespace(id=1)
        self.user = user or _FakeUser()
        self.response = _FakeResponse()


class _FakeRegistrationService:
    def __init__(self):
        self.sub_calls: list[dict] = []
        self.domme_calls: list[dict] = []

    async def register_sub(self, **kwargs):
        self.sub_calls.append(kwargs)
        return SimpleNamespace(send_names=tuple(kwargs["send_names"]))


class _FakeDMOnboardingCog:
    def __init__(self, *, ok: bool = True):
        self.calls: list[dict] = []
        self._ok = ok

    async def start_onboarding_dm(self, *, user, guild_id):
        self.calls.append({"user": user, "guild_id": guild_id})
        if self._ok:
            return True, SimpleNamespace(id=1), None
        return False, None, "dm_blocked"


class _FakeBot:
    def __init__(self, settings, *, maintenance_enabled: bool = False, dm_cog=None):
        self.guild_settings_repo = SimpleNamespace(get=self._get_settings)
        self.registration_service = _FakeRegistrationService()
        self._settings = settings
        self._maintenance_enabled = maintenance_enabled
        self._dm_cog = dm_cog
        self.maintenance_service = SimpleNamespace(
            registrations_blocked=self._registrations_blocked
        )

    def get_cog(self, name: str):
        if name == "DMOnboardingCog":
            return self._dm_cog
        return None

    async def _get_settings(self, guild_id: int):
        del guild_id
        return self._settings

    async def _registrations_blocked(self):
        return self._maintenance_enabled


def _view_text(payload: dict) -> str:
    view = payload.get("view")
    if view is None:
        return str(payload.get("content", ""))
    chunks: list[str] = []
    for top_level in view.children:
        for child in getattr(top_level, "children", []):
            content = getattr(child, "content", None)
            if content:
                chunks.append(str(content))
    return "\n".join(chunks)


def test_register_commands_do_not_take_slash_options():
    domme_params = list(inspect.signature(RegistrationCog.register_domme.callback).parameters)
    sub_params = list(inspect.signature(RegistrationCog.register_sub.callback).parameters)
    assert domme_params == ["self", "interaction"]
    assert sub_params == ["self", "interaction"]


def test_register_domme_denied_when_role_missing_from_config(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.registration.member_has_role", lambda *_a, **_k: True)
    interaction = _FakeInteraction()
    bot = _FakeBot(SimpleNamespace(domme_role_id=None, sub_role_id=22, send_track_channel_id=77))
    cog = RegistrationCog(bot)

    asyncio.run(RegistrationCog.register_domme.callback(cog, interaction))

    assert interaction.response.messages[0]["ephemeral"] is True
    assert interaction.response.messages[0]["view"] is not None


def test_register_domme_denied_when_member_lacks_configured_role(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.registration.member_has_role", lambda *_a, **_k: False)
    interaction = _FakeInteraction()
    bot = _FakeBot(SimpleNamespace(domme_role_id=11, sub_role_id=22, send_track_channel_id=77))
    cog = RegistrationCog(bot)

    asyncio.run(RegistrationCog.register_domme.callback(cog, interaction))

    assert interaction.response.messages[0]["ephemeral"] is True
    assert interaction.response.messages[0]["view"] is not None


def test_register_domme_allowed_routes_to_dm_onboarding(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.registration.member_has_role", lambda *_a, **_k: True)
    dm_cog = _FakeDMOnboardingCog(ok=True)
    interaction = _FakeInteraction()
    bot = _FakeBot(
        SimpleNamespace(domme_role_id=11, sub_role_id=22, send_track_channel_id=77),
        dm_cog=dm_cog,
    )
    cog = RegistrationCog(bot)

    asyncio.run(RegistrationCog.register_domme.callback(cog, interaction))

    assert len(dm_cog.calls) == 1
    assert dm_cog.calls[0]["guild_id"] == interaction.guild.id
    assert interaction.response.messages[0]["ephemeral"] is True
    assert "Setup Sent" in _view_text(interaction.response.messages[0])


def test_register_domme_reports_dm_blocked(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.registration.member_has_role", lambda *_a, **_k: True)
    dm_cog = _FakeDMOnboardingCog(ok=False)
    interaction = _FakeInteraction()
    bot = _FakeBot(
        SimpleNamespace(domme_role_id=11, sub_role_id=22, send_track_channel_id=77),
        dm_cog=dm_cog,
    )
    cog = RegistrationCog(bot)

    asyncio.run(RegistrationCog.register_domme.callback(cog, interaction))

    assert interaction.response.messages[0]["ephemeral"] is True
    assert "couldn't DM you" in _view_text(interaction.response.messages[0])


def test_register_domme_blocked_during_maintenance(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.registration.member_has_role", lambda *_a, **_k: True)
    interaction = _FakeInteraction()
    bot = _FakeBot(
        SimpleNamespace(domme_role_id=11, sub_role_id=22, send_track_channel_id=77),
        maintenance_enabled=True,
    )
    cog = RegistrationCog(bot)

    asyncio.run(RegistrationCog.register_domme.callback(cog, interaction))

    assert interaction.response.messages[0]["ephemeral"] is True
    assert "maintenance" in _view_text(interaction.response.messages[0]).lower()


def test_register_sub_allowed_opens_modal(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.registration.member_has_role", lambda *_a, **_k: True)
    interaction = _FakeInteraction()
    bot = _FakeBot(SimpleNamespace(domme_role_id=11, sub_role_id=22, send_track_channel_id=77))
    cog = RegistrationCog(bot)

    asyncio.run(RegistrationCog.register_sub.callback(cog, interaction))

    assert interaction.response.modal is not None
    assert type(interaction.response.modal).__name__ == "_SubRegistrationModal"
    assert bot.registration_service.sub_calls == []


def test_register_sub_blocked_during_maintenance(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.registration.member_has_role", lambda *_a, **_k: True)
    interaction = _FakeInteraction()
    bot = _FakeBot(
        SimpleNamespace(domme_role_id=11, sub_role_id=22, send_track_channel_id=77),
        maintenance_enabled=True,
    )
    cog = RegistrationCog(bot)

    asyncio.run(RegistrationCog.register_sub.callback(cog, interaction))

    assert interaction.response.modal is None
    assert interaction.response.messages[0]["ephemeral"] is True
    assert "maintenance" in _view_text(interaction.response.messages[0]).lower()


def test_register_sub_denied_when_role_missing_from_config(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.registration.member_has_role", lambda *_a, **_k: True)
    interaction = _FakeInteraction()
    bot = _FakeBot(SimpleNamespace(domme_role_id=11, sub_role_id=None, send_track_channel_id=77))
    cog = RegistrationCog(bot)

    asyncio.run(RegistrationCog.register_sub.callback(cog, interaction))

    assert interaction.response.messages[0]["ephemeral"] is True
    assert interaction.response.messages[0]["view"] is not None
    assert bot.registration_service.sub_calls == []


def test_register_sub_denied_when_member_lacks_configured_role(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.registration.member_has_role", lambda *_a, **_k: False)
    interaction = _FakeInteraction()
    bot = _FakeBot(SimpleNamespace(domme_role_id=11, sub_role_id=22, send_track_channel_id=77))
    cog = RegistrationCog(bot)

    asyncio.run(RegistrationCog.register_sub.callback(cog, interaction))

    assert interaction.response.messages[0]["ephemeral"] is True
    assert interaction.response.messages[0]["view"] is not None
    assert bot.registration_service.sub_calls == []
