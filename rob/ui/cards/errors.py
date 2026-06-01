from __future__ import annotations

from rob.ui.components import make_card, render
from rob.ui.copy import PERMISSION_ROLE_MISSING
from rob.ui.theme import COLOR_DANGER


def error_card(message: str, detail: str | None = None):
    description = message if detail is None else f"{message}\n\n{detail}"
    return render(
        make_card(
            title="Rob hit a snag",
            body=description,
            color=COLOR_DANGER,
            variant="error",
            callout="What to try next: double-check the details and try again.",
        )
    )


def error_permission(detail: str = PERMISSION_ROLE_MISSING):
    return render(
        make_card(
            title="Rob can't do that from this account",
            body=detail,
            color=COLOR_DANGER,
            variant="error",
        )
    )
