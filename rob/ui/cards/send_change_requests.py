from __future__ import annotations

import discord

from rob.database.repositories.models import SendChangeRequest, SendRecord
from rob.ui.components import make_card, render
from rob.ui.render import CardSection, RenderedMessage
from rob.ui.theme import COLOR_DANGER, COLOR_PRIMARY, COLOR_SUCCESS, COLOR_WARNING
from rob.utils.money import format_money_from_cents


def send_change_request_card(
    request: SendChangeRequest,
    *,
    domme_label: str,
    target_send: SendRecord | None = None,
    view: discord.ui.LayoutView | None = None,
) -> RenderedMessage:
    if request.action == "send_add":
        summary = (
            "A backend send addition is waiting for your approval.\n\n"
            "Rob will not apply it until you approve it here."
        )
        details = [
            ("Dom/me", domme_label),
            ("Amount", format_money_from_cents(request.amount_cents or 0)),
            ("Sender", request.requested_sub_name or "Unclaimed"),
            ("Method", request.method or "manual"),
            ("Requested By", request.requested_by),
        ]
        if request.note:
            details.append(("Note", request.note))
        color = COLOR_WARNING
        title = "Rob | Approve Send Add"
    elif request.action == "send_remove":
        existing_amount = (
            format_money_from_cents(target_send.amount_cents)
            if target_send is not None
            else "(unknown)"
        )
        existing_sender = (
            target_send.sub_name if target_send is not None and target_send.sub_name else "Unclaimed"
        )
        sent_at = target_send.sent_at.isoformat() if target_send is not None else "(unknown)"
        summary = (
            "A backend send removal is waiting for your approval.\n\n"
            "Rob will not remove it from tracked totals until you approve it here."
        )
        details = [
            ("Dom/me", domme_label),
            ("Send ID", str(request.target_send_id or 0)),
            ("Amount", existing_amount),
            ("Sender", existing_sender),
            ("Sent At", sent_at),
            ("Requested By", request.requested_by),
        ]
        color = COLOR_DANGER
        title = "Rob | Approve Send Removal"
    else:
        existing_amount = (
            format_money_from_cents(target_send.amount_cents, "USD")
            if target_send is not None
            else "(unknown)"
        )
        summary = (
            "A backend send amount adjustment is waiting for your approval.\n\n"
            "Rob will not edit the tracked send or announcement until you approve it here."
        )
        details = [
            ("Dom/me", domme_label),
            ("Send ID", str(request.target_send_id or 0)),
            ("Current Amount", existing_amount),
            ("New Amount", format_money_from_cents(request.amount_cents or 0, "USD")),
            ("Requested By", request.requested_by),
            ("Reason", request.note or "No reason provided."),
        ]
        color = COLOR_WARNING
        title = "Rob | Approve Send Update"

    return render(
        make_card(
            title=title,
            body=summary,
            color=color,
            sections=[CardSection(title=label, text=value) for label, value in details],
            footer="Approve only if this backend change matches what you actually received.",
            variant="warning",
        ),
        view=view,
    )


def send_change_result_card(
    *,
    title: str,
    summary: str,
    details: list[tuple[str, str]],
    approved: bool,
    view: discord.ui.LayoutView | None = None,
) -> RenderedMessage:
    return render(
        make_card(
            title=title,
            body=summary,
            color=COLOR_SUCCESS if approved else COLOR_PRIMARY,
            sections=[CardSection(title=label, text=value) for label, value in details],
            footer="Rob logged the decision for backend traceability.",
            variant="success" if approved else "default",
        ),
        view=view,
    )
