"""Unit tests for the Rebrickable data boundary and secret handling."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from rebrickable import Config, Part, Set

from pyldraw3_tui.data.rebrickable import (
    CollectionKind,
    CollectionRow,
    EntityDetails,
    EntityKind,
    LiveApiUnavailableError,
    RebrickableData,
    UserTokenUnavailableError,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_entity_and_collection_page_urls_are_constructed_locally() -> None:
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


async def test_live_read_without_api_key_fails_before_network(
    tmp_path: Path,
) -> None:
    data = RebrickableData(
        Config(
            database_path=tmp_path / "catalog.sqlite",
            cache_path=tmp_path / "cache",
        )
    )
    with pytest.raises(LiveApiUnavailableError):
        await data.live_details(EntityKind.PART, "3001")
    await data.close()


async def test_collection_read_without_user_token_fails_before_network(
    tmp_path: Path,
) -> None:
    data = RebrickableData(
        Config(
            database_path=tmp_path / "catalog.sqlite",
            cache_path=tmp_path / "cache",
            api_key="api-secret",
        )
    )
    data.set_user_token(None)
    try:
        with pytest.raises(UserTokenUnavailableError):
            await data.collection_page(
                CollectionKind.SETS,
                page=1,
                page_size=10,
                query="",
            )
    finally:
        await data.close()


async def test_user_token_is_environment_or_memory_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
