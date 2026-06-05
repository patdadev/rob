from __future__ import annotations

from rob.ui.components import make_card, render
from rob.ui.copy import MAINTENANCE_FOOTER
from rob.ui.render import CardSection, RenderedMessage
from rob.ui.theme import COLOR_WARNING


def maintenance_embed(reason: str | None) -> RenderedMessage:
    return render(
        make_card(
            title="Rob | Maintenance Mode",
            body="New sends are being saved, but Discord posting is paused.",
            color=COLOR_WARNING,
            footer=MAINTENANCE_FOOTER,
            sections=[CardSection(title="Reason", text=reason or "No reason provided.")],
            variant="warning",
        )
    )


def rob_offline_embed() -> RenderedMessage:
    return render(
        make_card(
            title="Rob's Offline",
            body=(
                "-# Apologies, Rob is currently only running the bare features while "
                "the future of Robs features are decided and worked on.\n\n"
                "-# At current, only the following systems are online in VIB:\n\n"
                "-# - Count (No Recovery)\n"
                "-# - Manual Send Addition (no notification)\n\n"
                "-# Sends tracked automatically or manually will continue to update in the backend."
            ),
            color=COLOR_WARNING,
            variant="warning",
        )
    )
