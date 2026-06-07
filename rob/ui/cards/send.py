from __future__ import annotations

import hashlib

import discord

from rob.config.guilds import is_test_guild
from rob.database.repositories.models import SendRecord
from rob.ui.render import RenderedMessage, require_components_v2
from rob.ui.theme import COLOR_SEND
from rob.ui.emojis import ROBDROOL
from rob.utils.money import format_money_from_cents, format_money_with_currency_name

_RANDOM_FACTS = (
    "Honey never spoils.",
    "Octopuses have three hearts.",
    "Bananas are berries, but strawberries are not.",
    "A day on Venus is longer than a year on Venus.",
    "Sharks existed before trees.",
    "Scotland's national animal is the unicorn.",
    "Wombat poop is cube-shaped.",
    "Sea otters hold hands while they sleep.",
)


def _amount_text(send: SendRecord) -> str:
    currency = (send.currency or "USD").upper()
    if currency == "USD":
        usd = format_money_from_cents(send.amount_cents, "USD")
        original_currency = (send.original_currency or "").upper()
        if send.original_amount_cents is not None and original_currency and original_currency != "USD":
            original = format_money_with_currency_name(send.original_amount_cents, original_currency)
            return f"{usd} (converted from {original})"
        return usd
    return format_money_with_currency_name(send.amount_cents, send.currency)


def _fact_for_send(send: SendRecord) -> str:
    seed = send.event_id or send.fallback_event_hash or str(send.id)
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return _RANDOM_FACTS[digest[0] % len(_RANDOM_FACTS)]


def _button_label(item_name: str | None) -> str:
    if not item_name:
        return "View on Throne"
    label = f"{item_name} on Throne!"
    if len(label) <= 80:
        return label
    return f"{item_name[:65].rstrip()}... on Throne!"


def _throne_headline(send: SendRecord, *, domme_label: str) -> str:
    item_name = send.item_name or "something lovely"
    if send.sub_user_id is not None:
        return f"{domme_label} just received **{item_name}** from <@{send.sub_user_id}> via Throne!"
    return f"{domme_label} just received **{item_name}** via Throne!"


def send_card(
    *,
    send: SendRecord,
    domme_label: str,
    sub_display: str,
    rank: int | None = None,
    adjustment_note: str | None = None,
    throne_url: str | None = None,
):
    del rank
    require_components_v2()
    view = discord.ui.LayoutView(timeout=1800)
    if send.source == "throne_webhook" and is_test_guild(send.guild_id):
        body = (
            f"{_throne_headline(send, domme_label=domme_label)}\n\n"
            f"**Amount:** {_amount_text(send)}"
        )
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"### {ROBDROOL} New Send Alert!"),
            accent_color=COLOR_SEND,
        )
        if adjustment_note:
            container.add_item(discord.ui.TextDisplay(adjustment_note))
        container.add_item(discord.ui.Separator())
        if send.item_image_url:
            container.add_item(
                discord.ui.Section(
                    discord.ui.TextDisplay(body),
                    accessory=discord.ui.Thumbnail(media=send.item_image_url),
                )
            )
        else:
            container.add_item(discord.ui.TextDisplay(body))
        if throne_url:
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.ActionRow(
                    discord.ui.Button(
                        label=_button_label(send.item_name),
                        style=discord.ButtonStyle.link,
                        url=throne_url,
                    )
                )
            )
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# Random Fact: {_fact_for_send(send)}"))
        view.add_item(container)
        return RenderedMessage(view=view)

    if send.source == "send_request":
        expected_fallback_note = f"Manual send via {send.method}" if send.method else "Manual send"
        lines = [
            f"**Sub:** {sub_display}",
            f"**Amount:** {_amount_text(send)}",
        ]
        if send.item_name and send.item_name != expected_fallback_note:
            lines.append(f"**Note:** {send.item_name}")
        lines.append(f"**Service:** {send.method or 'other'}")
        body = "\n\n".join(lines)
    else:
        body = (
            f"**Sub:** {sub_display}\n\n"
            f"**Amount:** {_amount_text(send)}\n\n"
            f"**Item:** {send.item_name or 'Mystery send'}"
        )
    children: list[discord.ui.Item] = [
        discord.ui.TextDisplay(f"### 💸 New Send to {domme_label}! 💸"),
    ]
    if adjustment_note:
        children.append(discord.ui.TextDisplay(adjustment_note))
    children.append(discord.ui.Separator())
    if send.item_image_url:
        children.append(
            discord.ui.Section(
                discord.ui.TextDisplay(body),
                accessory=discord.ui.Thumbnail(media=send.item_image_url),
            )
        )
    else:
        children.append(discord.ui.TextDisplay(body))
    view.add_item(discord.ui.Container(*children, accent_color=COLOR_SEND))
    return RenderedMessage(view=view)
