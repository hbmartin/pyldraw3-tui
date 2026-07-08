"""Unit tests for the ldraw.org URL builder."""

from __future__ import annotations

from pyldraw3_tui.data.web import part_url


def test_part_url():
    assert (
        part_url("3001") == "https://library.ldraw.org/parts/list?tableSearch=3001.dat"
    )


def test_part_url_quotes_unsafe_characters():
    assert (
        part_url("s/3001s01")
        == "https://library.ldraw.org/parts/list?tableSearch=s/3001s01.dat"
    )
    assert "%20" in part_url("weird code")
