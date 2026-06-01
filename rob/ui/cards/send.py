from __future__ import annotations

import discord

from rob.database.repositories.models import SendRecord
from rob.ui.render import RenderedMessage, require_components_v2
from rob.ui.theme import COLOR_SEND
from rob.utils.money import format_money_from_cents, format_money_with_currency_name


def _normalized_amount_text(send: SendRecord) -> str:
    normalized_usd = format_money_from_cents(send.amount_cents, "USD")
    currency = (send.currency or "USD").upper()
    if currency == "USD":
        return normalized_usd
    original = format_money_with_currency_name(send.amount_cents, send.currency)
    return f"{normalized_usd} (normalized from {original})"


def send_card(
    *,
    send: SendRecord,
    domme_label: str,
    sub_display: str,
    rank: int | None = None,
    adjustment_note: str | None = None,
):
    del rank
    require_components_v2()
    view = discord.ui.LayoutView(timeout=1800)
    if send.source == "send_request":
        expected_fallback_note = f"Manual send via {send.method}" if send.method else "Manual send"
        lines = [
            f"**Sub:** {sub_display}",
            f"**Amount:** {_normalized_amount_text(send)}",
        ]
        if send.item_name and send.item_name != expected_fallback_note:
            lines.append(f"**Note:** {send.item_name}")
        lines.append(f"**Service:** {send.method or 'other'}")
        if adjustment_note:
            lines.append(adjustment_note)
        body = "\n\n".join(lines)
    else:
        lines = [
            f"**Sub:** {sub_display}\n\n"
            f"**Amount:** {_normalized_amount_text(send)}\n\n"
            f"**Item:** {send.item_name or 'Mystery send'}"
        ]
        if adjustment_note:
            lines.append(adjustment_note)
        body = "\n\n".join(lines)
    children: list[discord.ui.Item] = [
        discord.ui.TextDisplay(f"## 💸 New Send to {domme_label}! 💸"),
        discord.ui.Separator(),
    ]
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
