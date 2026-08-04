"""Async Rebrickable session/client lifecycle for the read-only TUI."""

# Protocol declarations intentionally omit redundant one-line method docs.
# ruff: noqa: D102

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from rebrickable import (
    CatalogState,
    Config,
    Inventory,
    MappingStatus,
    Part,
    PartCategory,
    RebrickableClient,
    RebrickableSession,
    SearchKind,
    Set,
    Theme,
    TranslationReport,
    part_url,
    set_url,
)
from rebrickable.api.models import (
    ApiInventoryMinifig,
    ApiInventoryPart,
    ApiInventorySet,
    ApiPart,
    ApiSet,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ldraw.bom import BomRow
    from ldraw.parts import Parts
    from rebrickable import RefreshReport, SearchResult, TranslatedBomRow
    from rebrickable.api.query_types import UsersPartsListQuery, UsersSetsListQuery
    from rebrickable.progress import ProgressCallback


class LiveApiUnavailableError(RuntimeError):
    """A live read was requested without an API key."""

    def __init__(self) -> None:
        super().__init__("set REBRICKABLE_API_KEY to use live Rebrickable data")


class UserTokenUnavailableError(RuntimeError):
    """A collection read was requested without a user token."""

    def __init__(self) -> None:
        super().__init__("a Rebrickable user token is required")


class EntityKind(StrEnum):
    """Rebrickable entity kinds exposed by the catalog browser."""

    PART = "part"
    SET = "set"


class CollectionKind(StrEnum):
    """Read-only personal collection surfaces exposed by the TUI."""

    SETS = "sets"
    PARTS = "parts"
    PART_LISTS = "part_lists"
    SET_LISTS = "set_lists"


@dataclass(frozen=True, slots=True)
class EntityDetails:
    """One local entity plus related display metadata."""

    kind: EntityKind
    entity: Part | Set
    category: PartCategory | None = None
    theme: Theme | None = None

    @property
    def identifier(self) -> str:
        """Return the canonical Rebrickable identifier."""
        if isinstance(self.entity, Part):
            return self.entity.part_num
        return self.entity.set_num

    @property
    def page_url(self) -> str:
        """Return the locally constructed public entity page."""
        return self.entity.page_url


@dataclass(frozen=True, slots=True)
class LiveDetails:
    """Live API DTO retained intact alongside a locally constructed page URL."""

    kind: EntityKind
    payload: ApiPart | ApiSet

    @property
    def page_url(self) -> str:
        """Return the locally constructed public entity page."""
        if isinstance(self.payload, ApiPart):
            return part_url(self.payload.part_num)
        return set_url(self.payload.set_num)


@dataclass(frozen=True, slots=True)
class LiveSetInventory:
    """Three public read-only inventory surfaces for a live set."""

    parts: tuple[ApiInventoryPart, ...]
    minifigs: tuple[ApiInventoryMinifig, ...]
    sets: tuple[ApiInventorySet, ...]


@dataclass(frozen=True, slots=True)
class CollectionRow:
    """Source-neutral row retaining its upstream DTO outside the presentation layer."""

    key: str
    title: str
    subtitle: str
    entity_kind: EntityKind | None = None
    entity_id: str | None = None
    upstream: object | None = None

    @property
    def page_url(self) -> str | None:
        """Return a locally constructed public part/set page when applicable."""
        match self.entity_kind:
            case EntityKind.PART if self.entity_id is not None:
                return part_url(self.entity_id)
            case EntityKind.SET if self.entity_id is not None:
                return set_url(self.entity_id)
            case _:
                return None


@dataclass(frozen=True, slots=True)
class CollectionPage:
    """One bounded server page of personal collection records."""

    rows: tuple[CollectionRow, ...]
    total: int
    page: int
    has_next: bool
    has_previous: bool


class RebrickableDataProtocol(Protocol):
    """Narrow, injectable interface consumed by Textual views."""

    @property
    def api_key_available(self) -> bool: ...

    @property
    def user_token_available(self) -> bool: ...

    def set_user_token(self, token: str | None) -> None: ...

    async def state(self) -> CatalogState: ...

    async def refresh(
        self, *, progress: ProgressCallback | None = None
    ) -> RefreshReport: ...

    async def search(
        self,
        kind: EntityKind,
        query: str,
        *,
        limit: int,
        offset: int,
    ) -> SearchResult: ...

    async def details(self, kind: EntityKind, identifier: str) -> EntityDetails: ...

    async def inventory(self, set_num: str) -> Inventory: ...

    async def live_details(self, kind: EntityKind, identifier: str) -> LiveDetails: ...

    async def live_set_inventory(self, set_num: str) -> LiveSetInventory: ...

    async def collection_page(
        self,
        kind: CollectionKind,
        *,
        page: int,
        page_size: int,
        query: str,
    ) -> CollectionPage: ...

    async def collection_list_page(
        self,
        kind: CollectionKind,
        list_id: int,
        *,
        page: int,
        page_size: int,
    ) -> CollectionPage: ...

    async def translate(
        self, rows: Iterable[BomRow], *, parts: Parts | None
    ) -> TranslationReport: ...

    async def enrich_row(self, row: TranslatedBomRow) -> int: ...

    async def close(self) -> None: ...


class RebrickableData:
    """Compose offline catalog reads and explicit, paced live API reads."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = Config.load() if config is None else config
        self._session: RebrickableSession | None = None
        self._client: RebrickableClient | None = None
        self._user_token = os.environ.get("REBRICKABLE_USER_TOKEN") or None
        self._session_lock = asyncio.Lock()

    @property
    def api_key_available(self) -> bool:
        """Return whether a live API client can be created."""
        return bool(self.config.api_key)

    @property
    def user_token_available(self) -> bool:
        """Return whether collection reads are currently authenticated."""
        return bool(self._user_token)

    def set_user_token(self, token: str | None) -> None:
        """Keep a user token only in process memory for read calls."""
        normalized = token.strip() if token is not None else ""
        self._user_token = normalized or None

    async def _local(self) -> RebrickableSession:
        # Concurrent workers share this instance, so the open must not race:
        # a second session would silently replace the first and leak it past
        # close(). RebrickableSession.open happens not to suspend today, but
        # that is an upstream detail this boundary should not depend on.
        if self._session is not None:
            return self._session
        async with self._session_lock:
            if self._session is None:
                self._session = await RebrickableSession.open(self.config)
            return self._session

    def _live(self) -> RebrickableClient:
        if self._client is not None:
            return self._client
        api_key = self.config.api_key
        if not api_key:
            raise LiveApiUnavailableError
        self._client = RebrickableClient(api_key=api_key, config=self.config)
        return self._client

    def _token(self) -> str:
        if not self._user_token:
            raise UserTokenUnavailableError
        return self._user_token

    async def state(self) -> CatalogState:
        """Classify the local catalog without contacting the network."""
        return await (await self._local()).state()

    async def refresh(
        self, *, progress: ProgressCallback | None = None
    ) -> RefreshReport:
        """Explicitly refresh the transactional local catalog."""
        return await (await self._local()).refresh_catalog(progress=progress)

    async def search(
        self,
        kind: EntityKind,
        query: str,
        *,
        limit: int,
        offset: int,
    ) -> SearchResult:
        """Search one bounded local entity kind."""
        search_kind = SearchKind.PART if kind is EntityKind.PART else SearchKind.SET
        return await (await self._local()).search(
            query,
            kinds={search_kind},
            limit=limit,
            offset=offset,
        )

    async def details(self, kind: EntityKind, identifier: str) -> EntityDetails:
        """Load one local entity and its category or theme label."""
        session = await self._local()
        if kind is EntityKind.PART:
            part = await session.parts.require(identifier)
            category = await session.categories.get(part.category_id)
            return EntityDetails(kind, part, category=category)
        lego_set = await session.sets.require(identifier)
        theme = await session.themes.get(lego_set.theme_id)
        return EntityDetails(kind, lego_set, theme=theme)

    async def inventory(self, set_num: str) -> Inventory:
        """Load the newest local direct inventory for a set."""
        return await (await self._local()).sets.inventory(set_num)

    async def live_details(self, kind: EntityKind, identifier: str) -> LiveDetails:
        """Fetch one explicitly requested current API entity."""
        client = self._live()
        if kind is EntityKind.PART:
            payload = await client.get_part(identifier, inc_part_details=True)
        else:
            payload = await client.get_set(identifier)
        return LiveDetails(kind, payload)

    async def live_set_inventory(self, set_num: str) -> LiveSetInventory:
        """Fetch live set inventory endpoints sequentially."""
        client = self._live()
        parts = tuple(
            [
                item
                async for item in client.iter_set_parts(
                    set_num,
                    inc_part_details=True,
                    inc_color_details=True,
                )
            ]
        )
        minifigs = tuple([item async for item in client.iter_set_minifigs(set_num)])
        sets = tuple([item async for item in client.iter_set_sets(set_num)])
        return LiveSetInventory(parts, minifigs, sets)

    async def _local_set_name(self, set_num: str) -> str:
        try:
            lego_set = await (await self._local()).sets.get(set_num)
        except Exception:  # noqa: BLE001 - local enrichment is optional
            return set_num
        return lego_set.name if lego_set is not None else set_num

    async def collection_page(
        self,
        kind: CollectionKind,
        *,
        page: int,
        page_size: int,
        query: str,
    ) -> CollectionPage:
        """Fetch one bounded read-only personal collection page."""
        client = self._live()
        token = self._token()
        match kind:
            case CollectionKind.SETS:
                sets_query: UsersSetsListQuery = {
                    "page": page,
                    "page_size": page_size,
                }
                if query:
                    sets_query["search"] = query
                result = await client.list_user_sets(
                    user_token=token,
                    **sets_query,
                )
                rows = tuple(
                    [
                        CollectionRow(
                            key=item.set_num,
                            title=await self._local_set_name(item.set_num),
                            subtitle=(
                                f"quantity {item.quantity} · spares "
                                f"{'included' if item.include_spares else 'excluded'}"
                            ),
                            entity_kind=EntityKind.SET,
                            entity_id=item.set_num,
                            upstream=item,
                        )
                        for item in result.results
                    ]
                )
            case CollectionKind.PARTS:
                parts_query: UsersPartsListQuery = {
                    "page": page,
                    "page_size": page_size,
                    "inc_part_details": True,
                }
                if query:
                    parts_query["search"] = query
                result = await client.list_user_parts(
                    user_token=token,
                    **parts_query,
                )
                rows = tuple(
                    CollectionRow(
                        key=f"{item.part.part_num}:{item.color.id}",
                        title=item.part.name,
                        subtitle=(
                            f"{item.part.part_num} · {item.color.name} · "
                            f"quantity {item.quantity}"
                        ),
                        entity_kind=EntityKind.PART,
                        entity_id=item.part.part_num,
                        upstream=item,
                    )
                    for item in result.results
                )
            case CollectionKind.PART_LISTS:
                result = await client.list_user_part_lists(
                    user_token=token,
                    page=page,
                    page_size=page_size,
                )
                rows = tuple(
                    CollectionRow(
                        key=str(item.id),
                        title=item.name,
                        subtitle=(
                            f"{item.num_parts} parts"
                            if item.num_parts is not None
                            else "unknown parts"
                        ),
                        upstream=item,
                    )
                    for item in result.results
                )
            case CollectionKind.SET_LISTS:
                result = await client.list_user_set_lists(
                    user_token=token,
                    page=page,
                    page_size=page_size,
                )
                rows = tuple(
                    CollectionRow(
                        key=str(item.id),
                        title=item.name,
                        subtitle=(
                            f"{item.num_sets} sets"
                            if item.num_sets is not None
                            else "unknown sets"
                        ),
                        upstream=item,
                    )
                    for item in result.results
                )
            case _:
                msg = f"unsupported collection kind: {kind!r}"
                raise ValueError(msg)
        return CollectionPage(
            rows,
            result.count,
            page,
            result.next is not None,
            result.previous is not None,
        )

    async def collection_list_page(
        self,
        kind: CollectionKind,
        list_id: int,
        *,
        page: int,
        page_size: int,
    ) -> CollectionPage:
        """Fetch one bounded page from a personal part or set list."""
        client = self._live()
        token = self._token()
        match kind:
            case CollectionKind.PART_LISTS:
                result = await client.list_user_part_list_parts(
                    list_id,
                    user_token=token,
                    page=page,
                    page_size=page_size,
                    inc_part_details=True,
                    inc_color_details=True,
                )
                rows_list: list[CollectionRow] = []
                for item in result.results:
                    part_num = item.part_num or (
                        item.part.part_num if item.part is not None else ""
                    )
                    color_id = item.color_id
                    if color_id is None and item.color is not None:
                        color_id = item.color.id
                    rows_list.append(
                        CollectionRow(
                            key=(
                                f"{part_num}:{color_id if color_id is not None else ''}"
                            ),
                            title=(
                                item.part.name
                                if item.part is not None
                                else (item.part_num or "part")
                            ),
                            subtitle=(
                                f"quantity {item.quantity}"
                                + (
                                    f" · {item.color.name}"
                                    if item.color is not None
                                    else ""
                                )
                            ),
                            entity_kind=EntityKind.PART,
                            entity_id=part_num or None,
                            upstream=item,
                        )
                    )
                rows = tuple(rows_list)
            case CollectionKind.SET_LISTS:
                result = await client.list_user_set_list_sets(
                    list_id,
                    user_token=token,
                    page=page,
                    page_size=page_size,
                )
                rows = tuple(
                    [
                        CollectionRow(
                            key=item.set_num,
                            title=await self._local_set_name(item.set_num),
                            subtitle=(
                                f"quantity {item.quantity} · spares "
                                f"{'included' if item.include_spares else 'excluded'}"
                            ),
                            entity_kind=EntityKind.SET,
                            entity_id=item.set_num,
                            upstream=item,
                        )
                        for item in result.results
                    ]
                )
            case _:
                msg = "only part and set lists have list contents"
                raise ValueError(msg)
        return CollectionPage(
            rows,
            result.count,
            page,
            result.next is not None,
            result.previous is not None,
        )

    async def translate(
        self, rows: Iterable[BomRow], *, parts: Parts | None
    ) -> TranslationReport:
        """Annotate public pyldraw3 BOM rows without modifying them."""
        return await (await self._local()).ldraw.annotate_pyldraw_bom(
            rows,
            parts=parts,
        )

    async def enrich_row(self, row: TranslatedBomRow) -> int:
        """Verify known candidates for one incomplete row, sequentially."""
        client = self._live()
        bridge = (await self._local()).ldraw
        requests = 0
        if row.part_match.status is not MappingStatus.RESOLVED:
            for candidate in row.part_match.candidates:
                await bridge.enrich_part_mapping(
                    part_num=candidate.identifier,
                    client=client,
                )
                requests += 1
        if row.color_match.status is not MappingStatus.RESOLVED:
            for candidate in row.color_match.candidates:
                await bridge.enrich_color_mapping(
                    color_id=int(candidate.identifier),
                    client=client,
                )
                requests += 1
        return requests

    async def close(self) -> None:
        """Close live and local resources and discard session credentials."""
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._user_token = None
