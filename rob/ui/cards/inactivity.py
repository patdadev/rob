from __future__ import annotations

from rob.ui.components import make_card, render
from rob.ui.render import RenderedMessage
from rob.ui.theme import COLOR_PRIMARY, COLOR_SUCCESS


def _remove_time_text(remove_at_unix: int) -> str:
    return f"<t:{remove_at_unix}:R>"


def first_inactivity_warning_card(*, display_name: str, server_name: str, remove_at_unix: int, main_chat_channel: str) -> RenderedMessage:
    return render(
        make_card(
            title="🤔 Hello? Anyone there",
            body=(
                f"Hey **{display_name}**,\n\n"
                f"We're sending a heads up that you've been marked as inactive in **{server_name}** for around a week. "
                "Don't stress, you're not being removed yet.\n\n"
                "Rob automatically sends these notices and removes inactive members after **3 weeks of inactivity**. "
                f"If you remain inactive, you would be removed {_remove_time_text(remove_at_unix)}.\n\n"
                "We'll send another reminder in about a week if you're still inactive.\n\n"
                f"If you want this to clear, just become active again in {main_chat_channel}.\n\n"
                "Have a great day!"
            ),
            color=COLOR_PRIMARY,
            callout="This is automated, so there is no need to reply.",
            variant="warning",
        )
    )


def final_inactivity_warning_card(*, display_name: str, server_name: str, remove_at_unix: int, main_chat_channel: str) -> RenderedMessage:
    return render(
        make_card(
            title="🥹 I don't miss you, I swear",
            body=(
                f"Hey **{display_name}**,\n\n"
                f"We haven't seen you in a while in **{server_name}** and just wanted to remind you what happens if you're inactive for 3 weeks.\n\n"
                "You're on week 2 right now, and Rob will automatically remove you from VIB "
                f"{_remove_time_text(remove_at_unix)} if you remain inactive.\n\n"
                f"If you become active again in {main_chat_channel} before then, this clears automatically.\n\n"
                "Have a great day!"
            ),
            color=COLOR_PRIMARY,
            callout="This is automated, so there is no need to reply.",
            variant="warning",
        )
    )


def inactivity_test_sent_card(sent_count: int) -> RenderedMessage:
    return render(
        make_card(
            title="Inactivity test sent",
            body=f"Sent **{sent_count}** inactivity test message(s) to your DMs.",
            color=COLOR_SUCCESS,
            variant="success",
        )
    )


def inactivity_empty_list_card() -> RenderedMessage:
    return render(
        make_card(
            title="Inactive members",
            body="No eligible inactive members found.",
            color=COLOR_SUCCESS,
            variant="success",
        )
    )


def inactivity_list_card(lines: list[str], total: int) -> RenderedMessage:
    return render(
        make_card(
            title="Inactive members",
            body=f"Total: **{total}**\n\n" + "\n".join(lines),
            color=COLOR_PRIMARY,
            variant="default",
        )
    )
