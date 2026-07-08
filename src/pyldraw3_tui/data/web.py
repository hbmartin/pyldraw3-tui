"""URL builder for the ldraw.org parts library.

The per-part detail page uses an internal numeric database id that cannot
be derived from a part code, so links go to the parts-list search, which
lands on the part reliably by its number.
"""

from __future__ import annotations

from urllib.parse import quote

_PART_SEARCH_URL = "https://library.ldraw.org/parts/list?tableSearch="


def part_url(code: str) -> str:
    """Return the ldraw.org parts-list search URL for a part code."""
    return f"{_PART_SEARCH_URL}{quote(f'{code}.dat')}"
