"""Clipboard helpers with graceful degradation.

``pyperclip`` raises when no platform clipboard mechanism is available
(e.g. a headless Linux box without xclip); callers fall back to showing
the text for manual copy.
"""

from __future__ import annotations

import pyperclip


def copy_text(text: str) -> bool:
    """Copy text to the system clipboard; return False if unavailable."""
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException:
        return False
    return True
