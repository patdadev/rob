from __future__ import annotations

from datetime import datetime

import discord

from rob.database.repositories.age_verification import (
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_MANUAL_REVIEW_REQUIRED,
    STATUS_NOT_STARTED,
    STATUS_PENDING,
    STATUS_REVOKED,
    STATUS_VERIFIED_18_PLUS,
)
from rob.ui.emojis import ROBBLANK, ROBNO, ROBYES
from rob.ui.render import RenderedMessage
from rob.ui.theme import COLOR_DANGER, COLOR_INFO, COLOR_SUCCESS


def _timestamp_text(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return f"<t:{int(value.timestamp())}:F>"


def _link_button(*, label: str, url: str) -> discord.ui.Button:
    return discord.ui.Button(
        style=discord.ButtonStyle.link,
        label=label,
        url=url,
    )


def _status_meta(status: str) -> tuple[str, discord.Colour]:
    if status == STATUS_VERIFIED_18_PLUS:
        return f"{ROBYES} Age verified", COLOR_SUCCESS
    if status in {STATUS_FAILED, STATUS_REVOKED, STATUS_EXPIRED}:
        return f"{ROBNO} Verification update", COLOR_DANGER
    return f"{ROBBLANK} Age verification", COLOR_INFO


def _status_body(
    *,
    status: str,
    subject: str,
    expires_at: datetime | None,
    method: str | None,
    summary: str | None,
    reason: str | None,
) -> str:
    if status == STATUS_NOT_STARTED:
        return (
            f"{subject} has not started Yoti age verification yet.\n\n"
            "Run `/verify-age` in the test server when you're ready."
        )
    if status == STATUS_PENDING:
        expiry_line = ""
        expiry_text = _timestamp_text(expires_at)
        if expiry_text:
            expiry_line = f"\n\nSession expires: {expiry_text}"
        return (
            f"{subject} has a Yoti age verification session waiting to be completed."
            f"{expiry_line}"
        )
    if status == STATUS_VERIFIED_18_PLUS:
        method_line = f"\n\nMethod: `{method}`" if method else ""
        summary_line = f"\n\n{summary}" if summary else ""
        return (
            f"{subject} is marked as verified 18+ in this test server."
            f"{method_line}"
            f"{summary_line}"
        )
    if status == STATUS_FAILED:
        return (
            f"Yoti did not confirm an 18+ result for {subject}."
            + (f"\n\nDetails: {summary}" if summary else "")
        )
    if status == STATUS_MANUAL_REVIEW_REQUIRED:
        return (
            f"Rob could not safely auto-approve {subject}'s Yoti result."
            + (f"\n\nReason: {reason or summary}" if (reason or summary) else "")
            + "\n\nA staff member will need to review it."
        )
    if status == STATUS_EXPIRED:
        return (
            f"{subject}'s Yoti verification session expired before it finished.\n\n"
            "Run `/verify-age` to start a fresh session."
        )
    if status == STATUS_REVOKED:
        return (
            f"{subject}'s verified status has been revoked by staff."
            + (f"\n\nReason: {reason}" if reason else "")
        )
    return f"Rob recorded the current status for {subject} as `{status}`."


def age_verification_launch_card(
    *,
    verification_url: str,
    expires_at: datetime | str | None,
) -> RenderedMessage:
    view = discord.ui.LayoutView(timeout=1800)
    container = discord.ui.Container(accent_color=COLOR_INFO)
    container.add_item(discord.ui.TextDisplay(f"### {ROBBLANK} Age verification ready"))
    body = (
        "Your secure Yoti age-check link is ready.\n\n"
        "Open it below, complete the check, then run `/age-status` back in Discord."
    )
    expiry_text = _timestamp_text(expires_at)
    if expiry_text:
        body += f"\n\nSession expires: {expiry_text}"
    container.add_item(discord.ui.TextDisplay(body))
    container.add_item(discord.ui.Separator())
    container.add_item(
        discord.ui.ActionRow(
            _link_button(label="Open Yoti verification", url=verification_url)
        )
    )
    view.add_item(container)
    return RenderedMessage(view=view)


def age_verification_status_card(
    *,
    status: str,
    subject: str,
    expires_at: datetime | str | None = None,
    verification_url: str | None = None,
    method: str | None = None,
    summary: str | None = None,
    reason: str | None = None,
) -> RenderedMessage:
    title, color = _status_meta(status)
    body = _status_body(
        status=status,
        subject=subject,
        expires_at=expires_at,
        method=method,
        summary=summary,
        reason=reason,
    )
    view = discord.ui.LayoutView(timeout=1800)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"### {title}"))
    container.add_item(discord.ui.TextDisplay(body))
    if verification_url and status == STATUS_PENDING:
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.ActionRow(
                _link_button(label="Resume Yoti verification", url=verification_url)
            )
        )
    view.add_item(container)
    return RenderedMessage(view=view)
