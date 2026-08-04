"""Deterministic Rebrickable service fake; no test performs network I/O."""

# Test doubles intentionally mirror public protocol methods and use positional
# dataclass construction to keep fixtures compact.
# ruff: noqa: D102, FBT003

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rebrickable import (
    CatalogState,
    CatalogStatus,
    Color,
    ColorMatch,
    Inventory,
    InventoryMinifig,
    InventoryPart,
    InventorySet,
    MappingSource,
    MappingStatus,
    MatchCandidate,
    Minifig,
    Part,
    PartCategory,
    PartMatch,
    RefreshOutcome,
    RefreshReport,
    SearchHit,
    SearchKind,
    SearchResult,
    Set,
    Theme,
    TranslatedBomRow,
    TranslationReport,
)
from rebrickable.api.models import (
    ApiColor,
    ApiInventoryMinifig,
    ApiInventoryPart,
    ApiInventorySet,
    ApiPart,
    ApiSet,
)
from rebrickable.progress import ProgressEvent, ProgressStage

from pyldraw3_tui.data.rebrickable import (
    CollectionKind,
    CollectionPage,
    CollectionRow,
    EntityDetails,
    EntityKind,
    LiveDetails,
    LiveSetInventory,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ldraw.bom import BomRow
    from ldraw.parts import Parts
    from rebrickable.progress import ProgressCallback

PARTS = (
    Part(part_num="3001", name="Brick 2 x 4", category_id=11, material="Plastic"),
    Part(part_num="3022", name="Plate 2 x 2", category_id=14, material="Plastic"),
)
SETS = (
    Set(
        set_num="10497-1",
        name="Galaxy Explorer",
        year=2022,
        theme_id=721,
        num_parts=1254,
        image_url="https://cdn.rebrickable.com/media/sets/10497-1.jpg",
    ),
    Set(
        set_num="497-1",
        name="Galaxy Explorer",
        year=1979,
        theme_id=130,
        num_parts=338,
        image_url="https://cdn.rebrickable.com/media/sets/497-1.jpg",
    ),
)
COLORS = {
    4: Color(
        id=4,
        name="Red",
        rgb="C91A09",
        is_trans=False,
        num_parts=100,
        num_sets=100,
        year_from=1950,
        year_to=2026,
    ),
    15: Color(
        id=15,
        name="White",
        rgb="FFFFFF",
        is_trans=False,
        num_parts=100,
        num_sets=100,
        year_from=1950,
        year_to=2026,
    ),
}


class FakeRebrickableData:
    """In-memory implementation of the TUI's narrow data protocol."""

    def __init__(
        self,
        *,
        status: CatalogStatus = CatalogStatus.READY,
        api_key: bool = True,
        user_token: bool = True,
    ) -> None:
        self.status = status
        self.api_key_available = api_key
        self.user_token_available = user_token
        self.calls: list[str] = []
        self.closed = False

    def set_user_token(self, token: str | None) -> None:
        self.calls.append("set_user_token")
        self.user_token_available = bool(token)

    async def state(self) -> CatalogState:
        self.calls.append("state")
        return CatalogState(
            self.status,
            Path("/fixture/rebrickable/catalog.sqlite"),
            Path("/fixture/rebrickable/manifest.json"),
            snapshot_id="fixture-snapshot"
            if self.status is CatalogStatus.READY
            else None,
            retrieved_at=datetime(2026, 8, 2, tzinfo=UTC),
        )

    async def refresh(
        self,
        *,
        progress: ProgressCallback | None = None,
    ) -> RefreshReport:
        self.calls.append("refresh")
        if progress is not None:
            progress(ProgressEvent(stage=ProgressStage.DONE, message="Done"))
        self.status = CatalogStatus.READY
        return RefreshReport(
            RefreshOutcome.UPDATED,
            "fixture-snapshot",
            datetime(2026, 8, 2, tzinfo=UTC),
            (),
        )

    async def search(
        self,
        kind: EntityKind,
        query: str,
        *,
        limit: int,
        offset: int,
    ) -> SearchResult:
        self.calls.append(f"search:{kind.value}:{query}:{limit}:{offset}")
        entities = PARTS if kind is EntityKind.PART else SETS
        kind_value = SearchKind.PART if kind is EntityKind.PART else SearchKind.SET
        matches = [
            item
            for item in entities
            if not query
            or query.casefold()
            in (
                item.name + getattr(item, "part_num", getattr(item, "set_num", ""))
            ).casefold()
        ]
        hits = tuple(
            SearchHit(
                kind_value,
                item.part_num if isinstance(item, Part) else item.set_num,
                item.name,
                "fixture",
                1.0,
                "name",
                item.name,
            )
            for item in matches[offset : offset + limit]
        )
        return SearchResult(hits, len(matches), "fixture-snapshot")

    async def details(self, kind: EntityKind, identifier: str) -> EntityDetails:
        self.calls.append(f"details:{kind.value}:{identifier}")
        if kind is EntityKind.PART:
            part = next(item for item in PARTS if item.part_num == identifier)
            return EntityDetails(kind, part, category=PartCategory(11, "Bricks"))
        lego_set = next(item for item in SETS if item.set_num == identifier)
        return EntityDetails(
            kind,
            lego_set,
            theme=Theme(lego_set.theme_id, "Space", None),
        )

    async def inventory(self, set_num: str) -> Inventory:
        self.calls.append(f"inventory:{set_num}")
        return Inventory(
            set_num,
            1,
            (
                InventoryPart(
                    PARTS[0],
                    COLORS[4],
                    2,
                    False,
                    ("300121",),
                    "https://cdn.rebrickable.com/media/parts/3001.jpg",
                ),
            ),
            (InventorySet(SETS[1], 1),),
            (
                InventoryMinifig(
                    Minifig(
                        "fig-000001",
                        "Spaceperson",
                        4,
                        "https://cdn.rebrickable.com/media/figs/fig-000001.jpg",
                    ),
                    1,
                ),
            ),
        )

    async def live_details(self, kind: EntityKind, identifier: str) -> LiveDetails:
        self.calls.append(f"live_details:{kind.value}:{identifier}")
        if kind is EntityKind.PART:
            return LiveDetails(
                kind,
                ApiPart(
                    part_num=identifier,
                    name="Brick 2 x 4 (live)",
                    part_cat_id=11,
                    part_img_url="https://cdn.rebrickable.com/live-part.jpg",
                ),
            )
        return LiveDetails(
            kind,
            ApiSet(
                set_num=identifier,
                name="Galaxy Explorer (live)",
                year=2022,
                theme_id=721,
                num_parts=1254,
                set_img_url="https://cdn.rebrickable.com/live-set.jpg",
            ),
        )

    async def live_set_inventory(self, set_num: str) -> LiveSetInventory:
        self.calls.append(f"live_inventory:{set_num}")
        return LiveSetInventory(
            (
                ApiInventoryPart(
                    part=ApiPart(part_num="3001", name="Brick 2 x 4"),
                    color=ApiColor(id=4, name="Red"),
                    quantity=2,
                    part_img_url="https://cdn.rebrickable.com/live-inventory.jpg",
                ),
            ),
            (ApiInventoryMinifig(set_num="fig-000001", quantity=1),),
            (ApiInventorySet(set_num="497-1", quantity=1),),
        )

    async def collection_page(
        self,
        kind: CollectionKind,
        *,
        page: int,
        page_size: int,
        query: str,
    ) -> CollectionPage:
        self.calls.append(f"collection:{kind.value}:{page}:{page_size}:{query}")
        rows = {
            CollectionKind.SETS: (
                CollectionRow(
                    key="10497-1",
                    title="Galaxy Explorer",
                    subtitle="quantity 1",
                    entity_kind=EntityKind.SET,
                    entity_id="10497-1",
                ),
            ),
            CollectionKind.PARTS: (
                CollectionRow(
                    key="3001:4",
                    title="Brick 2 x 4",
                    subtitle="Red · quantity 2",
                    entity_kind=EntityKind.PART,
                    entity_id="3001",
                ),
            ),
            CollectionKind.PART_LISTS: (
                CollectionRow(key="7", title="Wanted parts", subtitle="2 parts"),
            ),
            CollectionKind.SET_LISTS: (
                CollectionRow(key="9", title="Space sets", subtitle="1 set"),
            ),
        }[kind]
        return CollectionPage(
            rows=rows,
            total=len(rows),
            page=page,
            has_next=False,
            has_previous=page > 1,
        )

    async def collection_list_page(
        self,
        kind: CollectionKind,
        list_id: int,
        *,
        page: int,
        page_size: int,
    ) -> CollectionPage:
        self.calls.append(f"list:{kind.value}:{list_id}:{page}:{page_size}")
        if kind is CollectionKind.PART_LISTS:
            row = CollectionRow(
                key="3001:4",
                title="Brick 2 x 4",
                subtitle="quantity 2",
                entity_kind=EntityKind.PART,
                entity_id="3001",
            )
        else:
            row = CollectionRow(
                key="10497-1",
                title="Galaxy Explorer",
                subtitle="quantity 1",
                entity_kind=EntityKind.SET,
                entity_id="10497-1",
            )
        return CollectionPage(
            rows=(row,),
            total=1,
            page=page,
            has_next=False,
            has_previous=False,
        )

    async def translate(
        self,
        rows: Iterable[BomRow],
        *,
        parts: Parts | None,
    ) -> TranslationReport:
        del parts
        self.calls.append("translate")
        translated = []
        for source in rows:
            part = str(source.part)
            color = source.colour_code if source.colour_code is not None else -1
            part_match = PartMatch(
                part,
                part,
                MappingStatus.RESOLVED,
                MappingSource.EXACT_CANONICAL_ID,
                1.0,
                (),
                "normalized identifiers are equal",
                "fixture-snapshot",
            )
            if color == 47:
                color_match = ColorMatch(
                    color,
                    None,
                    MappingStatus.AMBIGUOUS,
                    MappingSource.RGB,
                    0.5,
                    (
                        MatchCandidate("47", "Trans Clear", "RGB candidate", 0.5),
                        MatchCandidate("1055", "Trans White", "RGB candidate", 0.5),
                    ),
                    "multiple color candidates",
                    "fixture-snapshot",
                )
                status = MappingStatus.AMBIGUOUS
                target_color = None
            else:
                color_match = ColorMatch(
                    color,
                    color,
                    MappingStatus.RESOLVED,
                    MappingSource.RGB,
                    1.0,
                    (),
                    "unique RGB match",
                    "fixture-snapshot",
                )
                status = MappingStatus.RESOLVED
                target_color = color
            translated.append(
                TranslatedBomRow(
                    part,
                    color,
                    part,
                    target_color,
                    source.quantity,
                    status,
                    part_match,
                    color_match,
                )
            )
        translated_rows = tuple(translated)
        return TranslationReport(
            translated_rows,
            sum(row.status is MappingStatus.RESOLVED for row in translated_rows),
            sum(row.status is MappingStatus.AMBIGUOUS for row in translated_rows),
            sum(row.status is MappingStatus.UNRESOLVED for row in translated_rows),
            "fixture-snapshot",
        )

    async def enrich_row(self, row: TranslatedBomRow) -> int:
        count = len(row.part_match.candidates) + len(row.color_match.candidates)
        self.calls.append(f"enrich:{count}")
        return count

    async def close(self) -> None:
        self.closed = True
