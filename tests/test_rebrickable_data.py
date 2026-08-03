"""Unit tests for the Rebrickable data boundary and secret handling."""

from __future__ import annotations

import pytest
from rebrickable import Config, Part, Set

from pyldraw3_tui.data.rebrickable import (
    CollectionRow,
    EntityDetails,
    EntityKind,
    LiveApiUnavailableError,
    RebrickableData,
)


def test_entity_and_collection_page_urls_are_constructed_locally():
    part = EntityDetails(EntityKind.PART, Part("3001", "Brick", 11, "Plastic"))
    lego_set = EntityDetails(
        EntityKind.SET,
        Set("10497-1", "Galaxy Explorer", 2022, 721, 1254, "https://image"),
    )
    collection = CollectionRow(
        "10497-1",
        "Galaxy Explorer",
        "quantity 1",
        EntityKind.SET,
        "10497-1",
    )

    assert part.page_url == "https://rebrickable.com/parts/3001/"
    assert lego_set.page_url == "https://rebrickable.com/sets/10497-1/"
    assert collection.page_url == "https://rebrickable.com/sets/10497-1/"
    assert "image" not in collection.page_url


async def test_live_read_without_api_key_fails_before_network(tmp_path):
    data = RebrickableData(
        Config(
            database_path=tmp_path / "catalog.sqlite",
            cache_path=tmp_path / "cache",
        )
    )
    with pytest.raises(LiveApiUnavailableError):
        await data.live_details(EntityKind.PART, "3001")
    await data.close()


async def test_user_token_is_environment_or_memory_only(tmp_path, monkeypatch):
    monkeypatch.setenv("REBRICKABLE_USER_TOKEN", "environment-token")
    data = RebrickableData(
        Config(
            database_path=tmp_path / "catalog.sqlite",
            cache_path=tmp_path / "cache",
            api_key="api-secret",
        )
    )
    assert data.user_token_available
    assert "api-secret" not in repr(data.config)

    data.set_user_token(None)
    assert not data.user_token_available
    assert not (tmp_path / "catalog.sqlite").exists()

    data.set_user_token("session-token")
    await data.close()
    assert not data.user_token_available
