"""Theme names and the dark/light toggle."""

from __future__ import annotations

DARK_THEME = "textual-dark"
LIGHT_THEME = "textual-light"


def toggled_theme(current: str) -> str:
    """Return the other theme: dark becomes light and anything else dark."""
    return LIGHT_THEME if current == DARK_THEME else DARK_THEME
