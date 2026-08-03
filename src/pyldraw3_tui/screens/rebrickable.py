"""Offline-first Rebrickable catalog and read-only collection browser."""

# Textual lifecycle hooks and event handlers are intentionally public.
# ruff: noqa: D102

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

from rebrickable import CatalogStatus, Part, part_url, set_url
from rebrickable.api.models import ApiPart
from rich.text import Text
from textual import on, work
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    LoadingIndicator,
    Select,
    Static,
)

from pyldraw3_tui.data.rebrickable import (
    CollectionKind,
    CollectionPage,
    CollectionRow,
    EntityDetails,
    EntityKind,
    LiveDetails,
    LiveSetInventory,
    RebrickableDataProtocol,
)
from pyldraw3_tui.screens.chooser import ChooserScreen

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

_PAGE_SIZE = 100
_SEARCH_DEBOUNCE = 0.15


class UserTokenScreen(ModalScreen[str | None]):
    """Collect an existing Rebrickable user token without persisting it."""

    BINDINGS: ClassVar = [Binding("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    UserTokenScreen {
        align: center middle;
    }
    UserTokenScreen > Vertical {
        width: 66;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        """Show a masked, session-only token input."""
        with Vertical():
            yield Static("[bold]Rebrickable user token[/]")
            yield Static(
                "The token is kept only in memory for this run and is used "
                "only for read-only collection requests."
            )
            yield Input(password=True, placeholder="user token", id="user-token")
            yield Button("Use for this session", variant="primary", id="use-token")

    def on_mount(self) -> None:
        self.query_one("#user-token", expect_type=Input).focus()

    @on(Button.Pressed, "#use-token")
    def _submit(self, event: Button.Pressed) -> None:
        event.stop()
        token = self.query_one("#user-token", expect_type=Input).value.strip()
        self.dismiss(token or None)

    @on(Input.Submitted, "#user-token")
    def _input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


def _label_text(lines: list[tuple[str, str]]) -> Text:
    text = Text()
    for label, value in lines:
        if text:
            text.append("\n")
        text.append(f"{label:>12}  ", style="bold dim")
        text.append(value)
    return text


def _local_details_text(details: EntityDetails) -> Text:
    entity = details.entity
    if isinstance(entity, Part):
        return _label_text(
            [
                ("part", entity.part_num),
                ("name", entity.name),
                (
                    "category",
                    details.category.name
                    if details.category is not None
                    else str(entity.category_id),
                ),
                ("material", entity.material or "—"),
                ("page", entity.page_url),
            ]
        )
    return _label_text(
        [
            ("set", entity.set_num),
            ("name", entity.name),
            ("year", str(entity.year)),
            (
                "theme",
                details.theme.name
                if details.theme is not None
                else str(entity.theme_id),
            ),
            ("parts", str(entity.num_parts)),
            ("page", entity.page_url),
        ]
    )


def _live_details_text(details: LiveDetails) -> Text:
    payload = details.payload
    if isinstance(payload, ApiPart):
        lines = [
            ("live part", payload.part_num),
            ("name", payload.name),
            ("category", str(payload.part_cat_id or "—")),
            ("material", payload.part_material or "—"),
            ("years", f"{payload.year_from or '—'}-{payload.year_to or '—'}"),
            ("print of", payload.print_of or "—"),
            ("page", details.page_url),
        ]
    else:
        lines = [
            ("live set", payload.set_num),
            ("name", payload.name),
            ("year", str(payload.year or "—")),
            ("theme", str(payload.theme_id or "—")),
            ("parts", str(payload.num_parts or "—")),
            ("page", details.page_url),
        ]
    return _label_text(lines)


class RebrickableView(Vertical):
    """Browse the local catalog and explicit read-only API surfaces."""

    BINDINGS: ClassVar = [
        Binding("slash", "focus_search", "Search", key_display="/"),
    ]

    DEFAULT_CSS = """
    RebrickableView > #rb-toolbar {
        height: 3;
        padding: 0 1;
    }
    RebrickableView #rb-mode {
        width: 18;
    }
    RebrickableView #rb-kind {
        width: 20;
    }
    RebrickableView #rb-search {
        width: 1fr;
    }
    RebrickableView #rb-state {
        height: auto;
        min-height: 1;
        padding: 0 1;
    }
    RebrickableView #rb-loading {
        height: 1;
        display: none;
    }
    RebrickableView.working #rb-loading {
        display: block;
    }
    RebrickableView > #rb-content {
        height: 1fr;
    }
    RebrickableView #rb-results {
        width: 1fr;
        border: round $primary;
    }
    RebrickableView #rb-detail-pane {
        width: 52;
        min-width: 36;
        border: round $primary-muted;
        padding: 0 1;
    }
    RebrickableView #rb-detail {
        height: auto;
        min-height: 8;
    }
    RebrickableView #rb-actions {
        height: auto;
    }
    RebrickableView #rb-inventory {
        height: 1fr;
    }
    RebrickableView #rb-pager {
        height: 3;
        align: center middle;
    }
    RebrickableView #rb-pager Button {
        width: 14;
    }
    RebrickableView #rb-page-label {
        width: auto;
        margin: 0 2;
    }
    """

    def __init__(
        self,
        data: RebrickableDataProtocol | None = None,
        *,
        config_error: str | None = None,
        id: str | None = None,  # noqa: A002 - Textual idiom
    ) -> None:
        super().__init__(id=id)
        self._data = data
        self._config_error = config_error
        self._ready = False
        self._mode = "catalog"
        self._entity_kind = EntityKind.PART
        self._collection_kind = CollectionKind.SETS
        self._page = 1
        self._total = 0
        self._has_next = False
        self._rows: dict[str, str | CollectionRow] = {}
        self._selected_key: str | None = None
        self._selected_details: EntityDetails | None = None
        self._live_cache: dict[tuple[EntityKind, str], LiveDetails] = {}
        self._live_inventory_cache: dict[str, LiveSetInventory] = {}
        self._contents_list_id: int | None = None
        self._contents_page = 1
        self._contents_has_next = False
        self._search_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        """Lay out source controls, results, details, and bounded paging."""
        with Horizontal(id="rb-toolbar"):
            yield Select[str](
                [("Catalog", "catalog"), ("Collection", "collection")],
                value="catalog",
                allow_blank=False,
                id="rb-mode",
            )
            yield Select[str](
                [("Parts", EntityKind.PART.value), ("Sets", EntityKind.SET.value)],
                value=EntityKind.PART.value,
                allow_blank=False,
                id="rb-kind",
            )
            yield Input(placeholder="search parts…", id="rb-search")
            yield Button("Refresh", id="rb-refresh")
            yield Button("Token", id="rb-token")
        yield Static("Checking Rebrickable catalog…", id="rb-state")
        yield LoadingIndicator(id="rb-loading")
        with Horizontal(id="rb-content"):
            yield DataTable[str](id="rb-results")
            with Vertical(id="rb-detail-pane"):
                yield Static("No Rebrickable entity selected.", id="rb-detail")
                with Horizontal(id="rb-actions"):
                    yield Button("Local inventory", id="rb-local-inventory")
                    yield Button("Live details", id="rb-live-details")
                    yield Button("Live inventory", id="rb-live-inventory")
                    yield Button("Contents", id="rb-list-contents")
                    yield Button("<", id="rb-contents-previous")
                    yield Button(">", id="rb-contents-next")
                yield DataTable[str](id="rb-inventory")
        with Horizontal(id="rb-pager"):
            yield Button("Previous", id="rb-previous")
            yield Static("Page 1", id="rb-page-label")
            yield Button("Next", id="rb-next")

    def on_mount(self) -> None:
        results = self.query_one("#rb-results", expect_type=DataTable)
        results.cursor_type = "row"
        results.zebra_stripes = True
        results.add_columns("ID", "Name", "Details")
        inventory = self.query_one("#rb-inventory", expect_type=DataTable)
        inventory.cursor_type = "row"
        inventory.zebra_stripes = True
        inventory.add_columns("ID", "Name / color", "Qty", "Flags")
        self._sync_controls()
        self._load_state()

    def set_data(
        self,
        data: RebrickableDataProtocol | None,
        *,
        config_error: str | None = None,
    ) -> None:
        """Replace the service before or after mounting, primarily for setup/tests."""
        self._data = data
        self._config_error = config_error
        if self.is_mounted:
            self._load_state()

    @property
    def selected_page_url(self) -> str | None:
        """Return the selected entity's locally constructed public page URL."""
        if self._selected_details is not None:
            return self._selected_details.page_url
        if self._mode == "catalog" and self._selected_key is not None:
            if self._entity_kind is EntityKind.PART:
                return part_url(self._selected_key)
            return set_url(self._selected_key)
        selected = self._selected_collection_row()
        return selected.page_url if selected is not None else None

    @property
    def selected_identifier(self) -> str | None:
        if self._selected_details is not None:
            return self._selected_details.identifier
        if self._mode == "catalog":
            return self._selected_key
        selected = self._selected_collection_row()
        return selected.entity_id if selected is not None else None

    def action_focus_search(self) -> None:
        self.query_one("#rb-search", expect_type=Input).focus()

    def _set_working(self, *, working: bool, message: str | None = None) -> None:
        self.set_class(working, "working")
        if message is not None:
            self.query_one("#rb-state", expect_type=Static).update(message)

    @work(exclusive=True, group="rb-state")
    async def _load_state(self) -> None:
        if self._data is None:
            reason = self._config_error or "Rebrickable is unavailable."
            self._ready = False
            self.query_one("#rb-state", expect_type=Static).update(
                f"[red]Rebrickable configuration error:[/] {reason}"
            )
            self._sync_controls()
            return
        try:
            state = await self._data.state()
        except Exception as error:  # noqa: BLE001
            self._ready = False
            self.query_one("#rb-state", expect_type=Static).update(
                f"[red]Could not inspect Rebrickable catalog:[/] {error}"
            )
            self._sync_controls()
            return
        self._ready = state.status is CatalogStatus.READY
        if self._ready:
            retrieved = (
                state.retrieved_at.date().isoformat()
                if state.retrieved_at is not None
                else "unknown date"
            )
            self.query_one("#rb-state", expect_type=Static).update(
                f"Local snapshot {retrieved} · ordinary browsing is offline"
            )
        else:
            diagnostics = "; ".join(state.diagnostics) or state.status.value
            self.query_one("#rb-state", expect_type=Static).update(
                "[yellow]Local Rebrickable catalog is not ready.[/] "
                f"{diagnostics}. Use Refresh to download it without an API key."
            )
        self._sync_controls()
        if self._mode == "collection" or self._ready:
            self._query()

    def _sync_controls(self) -> None:
        catalog = self._mode == "catalog"
        self.query_one("#rb-refresh", expect_type=Button).display = catalog
        self.query_one("#rb-token", expect_type=Button).display = not catalog
        is_set = (
            self._selected_details is not None
            and self._selected_details.kind is EntityKind.SET
        )
        self.query_one("#rb-local-inventory", expect_type=Button).display = (
            catalog and is_set
        )
        self.query_one("#rb-live-details", expect_type=Button).display = catalog
        self.query_one("#rb-live-inventory", expect_type=Button).display = (
            catalog and is_set
        )
        self.query_one("#rb-list-contents", expect_type=Button).display = (
            not catalog
            and self._collection_kind
            in {CollectionKind.PART_LISTS, CollectionKind.SET_LISTS}
        )
        list_mode = not catalog and self._collection_kind in {
            CollectionKind.PART_LISTS,
            CollectionKind.SET_LISTS,
        }
        previous = self.query_one("#rb-contents-previous", expect_type=Button)
        next_button = self.query_one("#rb-contents-next", expect_type=Button)
        previous.display = list_mode
        next_button.display = list_mode
        previous.disabled = self._contents_page <= 1
        next_button.disabled = not self._contents_has_next
        self._sync_page_buttons()

    @on(Select.Changed, "#rb-mode")
    def _mode_changed(self, event: Select.Changed) -> None:
        event.stop()
        if not isinstance(event.value, str):
            return
        self._mode = event.value
        kind = self.query_one("#rb-kind", expect_type=Select)
        if self._mode == "catalog":
            options = [
                ("Parts", EntityKind.PART.value),
                ("Sets", EntityKind.SET.value),
            ]
            value = self._entity_kind.value
        else:
            options = [
                ("Owned sets", CollectionKind.SETS.value),
                ("Loose parts", CollectionKind.PARTS.value),
                ("Part lists", CollectionKind.PART_LISTS.value),
                ("Set lists", CollectionKind.SET_LISTS.value),
            ]
            value = self._collection_kind.value
        with kind.prevent(Select.Changed):
            kind.set_options(options)
            kind.value = value
        self._page = 1
        self._clear_detail()
        self._sync_search_placeholder()
        self._sync_controls()
        self._query()

    @on(Select.Changed, "#rb-kind")
    def _kind_changed(self, event: Select.Changed) -> None:
        event.stop()
        if not isinstance(event.value, str):
            return
        if self._mode == "catalog":
            self._entity_kind = EntityKind(event.value)
        else:
            self._collection_kind = CollectionKind(event.value)
        self._page = 1
        self._clear_detail()
        self._sync_search_placeholder()
        self._sync_controls()
        self._query()

    def _sync_search_placeholder(self) -> None:
        search = self.query_one("#rb-search", expect_type=Input)
        if self._mode == "catalog":
            label = "parts" if self._entity_kind is EntityKind.PART else "sets"
            search.placeholder = f"search {label}…"
            search.disabled = False
        else:
            searchable = self._collection_kind in {
                CollectionKind.SETS,
                CollectionKind.PARTS,
            }
            search.placeholder = (
                "search collection…" if searchable else "lists are paged by name…"
            )
            search.disabled = not searchable

    @on(Input.Changed, "#rb-search")
    def _search_changed(self, event: Input.Changed) -> None:
        event.stop()
        if self._search_timer is not None:
            self._search_timer.stop()
        self._search_timer = self.set_timer(_SEARCH_DEBOUNCE, self._run_search)

    def _run_search(self) -> None:
        self._search_timer = None
        self._page = 1
        self._query()

    @work(exclusive=True, group="rb-query")
    async def _query(self) -> None:
        data = self._data
        if data is None:
            return
        if self._mode == "catalog" and not self._ready:
            self._set_rows(())
            return
        if self._mode == "collection":
            if not data.api_key_available:
                self.query_one("#rb-state", expect_type=Static).update(
                    "Set REBRICKABLE_API_KEY to read the live collection."
                )
                self._set_rows(())
                return
            if not data.user_token_available:
                self.query_one("#rb-state", expect_type=Static).update(
                    "Provide REBRICKABLE_USER_TOKEN or use Token for this session."
                )
                self._set_rows(())
                return
        self._set_working(working=True, message="Loading Rebrickable data…")
        query = self.query_one("#rb-search", expect_type=Input).value.strip()
        try:
            if self._mode == "catalog":
                result = await data.search(
                    self._entity_kind,
                    query,
                    limit=_PAGE_SIZE,
                    offset=(self._page - 1) * _PAGE_SIZE,
                )
                self._total = result.total
                self._has_next = self._page * _PAGE_SIZE < result.total
                self._rows = {hit.canonical_id: hit.canonical_id for hit in result.hits}
                self._render_rows(
                    tuple(
                        (hit.canonical_id, hit.title, hit.subtitle or "")
                        for hit in result.hits
                    )
                )
                self._restore_catalog_status()
            else:
                page = await data.collection_page(
                    self._collection_kind,
                    page=self._page,
                    page_size=_PAGE_SIZE,
                    query=query,
                )
                self._apply_collection_page(page)
                self.query_one("#rb-state", expect_type=Static).update(
                    "Live read-only collection · no mutation actions are exposed"
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            self._set_rows(())
            self.query_one("#rb-state", expect_type=Static).update(
                f"[red]Rebrickable request failed:[/] {error}"
            )
        finally:
            self._set_working(working=False)
            self._sync_page_buttons()

    def _restore_catalog_status(self) -> None:
        self.query_one("#rb-state", expect_type=Static).update(
            f"Offline {self._entity_kind.value} results · {self._total} total"
        )

    def _apply_collection_page(self, page: CollectionPage) -> None:
        self._total = page.total
        self._has_next = page.has_next
        self._rows = {row.key: row for row in page.rows}
        self._render_rows(
            tuple((row.key, row.title, row.subtitle) for row in page.rows)
        )

    def _set_rows(self, rows: tuple[tuple[str, str, str], ...]) -> None:
        self._rows = {}
        self._render_rows(rows)

    def _render_rows(self, rows: tuple[tuple[str, str, str], ...]) -> None:
        table = self.query_one("#rb-results", expect_type=DataTable)
        table.clear()
        for key, title, subtitle in rows:
            table.add_row(key, title, subtitle, key=key)
        self._selected_key = rows[0][0] if rows else None
        if not rows:
            self._clear_detail()
        self._sync_page_buttons()

    @on(DataTable.RowHighlighted, "#rb-results")
    def _row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        key = event.row_key.value if event.row_key is not None else None
        self._selected_key = key
        if key is None:
            self._clear_detail()
        elif self._mode == "catalog":
            self._load_details(key)
        else:
            self._show_collection_row()

    @work(exclusive=True, group="rb-detail")
    async def _load_details(self, identifier: str) -> None:
        data = self._data
        if data is None:
            return
        try:
            details = await data.details(self._entity_kind, identifier)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            self.query_one("#rb-detail", expect_type=Static).update(
                f"[red]Could not load details:[/] {error}"
            )
            return
        if identifier != self._selected_key:
            return
        self._selected_details = details
        text = _local_details_text(details)
        cached = self._live_cache.get((details.kind, details.identifier))
        if cached is not None:
            text.append("\n\n")
            text.append_text(_live_details_text(cached))
        self.query_one("#rb-detail", expect_type=Static).update(text)
        is_set = details.kind is EntityKind.SET
        self.query_one("#rb-local-inventory", expect_type=Button).display = is_set
        self.query_one("#rb-live-inventory", expect_type=Button).display = is_set

    def _selected_collection_row(self) -> CollectionRow | None:
        if self._selected_key is None:
            return None
        value = self._rows.get(self._selected_key)
        return value if isinstance(value, CollectionRow) else None

    def _show_collection_row(self) -> None:
        self._selected_details = None
        row = self._selected_collection_row()
        if row is None:
            self._clear_detail()
            return
        self.query_one("#rb-detail", expect_type=Static).update(
            _label_text(
                [
                    ("id", row.key),
                    ("name", row.title),
                    ("details", row.subtitle),
                    ("page", row.page_url or "—"),
                ]
            )
        )

    def _clear_detail(self) -> None:
        self._selected_details = None
        self._contents_list_id = None
        self._contents_page = 1
        self._contents_has_next = False
        self.query_one("#rb-detail", expect_type=Static).update(
            "No Rebrickable entity selected."
        )
        self.query_one("#rb-inventory", expect_type=DataTable).clear()

    @on(Button.Pressed, "#rb-previous")
    def _previous(self, event: Button.Pressed) -> None:
        event.stop()
        if self._page > 1:
            self._page -= 1
            self._query()

    @on(Button.Pressed, "#rb-next")
    def _next(self, event: Button.Pressed) -> None:
        event.stop()
        if self._has_next:
            self._page += 1
            self._query()

    def _sync_page_buttons(self) -> None:
        if not self.is_attached:
            return
        self.query_one("#rb-previous", expect_type=Button).disabled = self._page <= 1
        self.query_one("#rb-next", expect_type=Button).disabled = not self._has_next
        pages = max(1, (self._total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        self.query_one("#rb-page-label", expect_type=Static).update(
            f"Page {self._page} of {pages} · {self._total} rows"
        )

    @on(Button.Pressed, "#rb-refresh")
    def _confirm_refresh(self, event: Button.Pressed) -> None:
        event.stop()
        options = [
            (
                "Download/refresh all 12 catalog datasets",
                "refresh",
            ),
            ("Cancel", "cancel"),
        ]
        self.app.push_screen(
            ChooserScreen("Refresh the local Rebrickable catalog?", options),
            self._refresh_choice,
        )

    def _refresh_choice(self, choice: str | None) -> None:
        if choice == "refresh":
            self._refresh()

    @work(exclusive=True, group="rb-refresh")
    async def _refresh(self) -> None:
        data = self._data
        if data is None:
            return
        self._set_working(
            working=True,
            message="Starting explicit catalog refresh…",
        )

        def progress(event: object) -> None:
            message = str(getattr(event, "message", ""))
            dataset = getattr(event, "dataset", None)
            current = getattr(event, "current", None)
            total = getattr(event, "total", None)
            label = message or str(getattr(event, "stage", "refresh"))
            if dataset:
                label = f"{label}: {dataset}"
            if current is not None and total:
                label = f"{label} ({current}/{total})"
            self.query_one("#rb-state", expect_type=Static).update(label)

        try:
            report = await data.refresh(progress=progress)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            self.query_one("#rb-state", expect_type=Static).update(
                f"[red]Catalog refresh failed:[/] {error}"
            )
        else:
            self.app.notify(f"Rebrickable catalog {report.outcome.value}.")
            worker = self._load_state()
            await worker.wait()
        finally:
            self._set_working(working=False)

    @on(Button.Pressed, "#rb-token")
    def _prompt_token(self, event: Button.Pressed) -> None:
        event.stop()
        self.app.push_screen(UserTokenScreen(), self._token_entered)

    def _token_entered(self, token: str | None) -> None:
        if token is None or self._data is None:
            return
        self._data.set_user_token(token)
        self._page = 1
        self._query()

    @on(Button.Pressed, "#rb-local-inventory")
    def _local_inventory_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if (
            self._selected_details is not None
            and self._selected_details.kind is EntityKind.SET
        ):
            self._load_local_inventory(self._selected_details.identifier)

    @work(exclusive=True, group="rb-inventory")
    async def _load_local_inventory(self, set_num: str) -> None:
        data = self._data
        if data is None:
            return
        self._set_working(
            working=True,
            message=f"Loading local inventory for {set_num}…",
        )
        try:
            inventory = await data.inventory(set_num)
            rows = [
                (
                    item.part.part_num,
                    f"{item.part.name} · {item.color.name} ({item.color.id})",
                    str(item.quantity),
                    "spare" if item.is_spare else "",
                )
                for item in inventory.parts
            ]
            rows.extend(
                (
                    item.set.set_num,
                    item.set.name,
                    str(item.quantity),
                    "contained set",
                )
                for item in inventory.sets
            )
            rows.extend(
                (
                    item.minifig.fig_num,
                    item.minifig.name,
                    str(item.quantity),
                    "minifig",
                )
                for item in inventory.minifigs
            )
            self._render_inventory(tuple(rows))
            self.query_one("#rb-state", expect_type=Static).update(
                f"Local newest inventory v{inventory.version} · {len(rows)} rows"
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            self.query_one("#rb-state", expect_type=Static).update(
                f"[red]Could not load inventory:[/] {error}"
            )
        finally:
            self._set_working(working=False)

    @on(Button.Pressed, "#rb-live-details")
    def _live_details_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if self._selected_details is not None:
            self._load_live_details(
                self._selected_details.kind,
                self._selected_details.identifier,
            )

    @work(exclusive=True, group="rb-live")
    async def _load_live_details(self, kind: EntityKind, identifier: str) -> None:
        data = self._data
        if data is None:
            return
        self._set_working(
            working=True,
            message=f"Fetching live {kind.value} details…",
        )
        try:
            details = await data.live_details(kind, identifier)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            self.query_one("#rb-state", expect_type=Static).update(
                f"[red]Live request failed:[/] {error}"
            )
        else:
            self._live_cache[(kind, identifier)] = details
            if self._selected_details is not None:
                text = _local_details_text(self._selected_details)
                text.append("\n\n")
                text.append_text(_live_details_text(details))
                self.query_one("#rb-detail", expect_type=Static).update(text)
            self.query_one("#rb-state", expect_type=Static).update(
                "Live details fetched explicitly · image metadata not displayed"
            )
        finally:
            self._set_working(working=False)

    @on(Button.Pressed, "#rb-live-inventory")
    def _live_inventory_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if (
            self._selected_details is not None
            and self._selected_details.kind is EntityKind.SET
        ):
            self._load_live_inventory(self._selected_details.identifier)

    @work(exclusive=True, group="rb-live-inventory")
    async def _load_live_inventory(self, set_num: str) -> None:
        data = self._data
        if data is None:
            return
        self._set_working(
            working=True,
            message=(
                "Fetching live parts, minifigures, and contained sets sequentially…"
            ),
        )
        try:
            inventory = await data.live_set_inventory(set_num)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            self.query_one("#rb-state", expect_type=Static).update(
                f"[red]Live inventory failed:[/] {error}"
            )
        else:
            self._live_inventory_cache[set_num] = inventory
            rows = [
                (
                    item.part.part_num,
                    f"{item.part.name} · {item.color.name}",
                    str(item.quantity),
                    "spare" if item.is_spare else "live",
                )
                for item in inventory.parts
            ]
            rows.extend(
                (
                    item.set_num or "—",
                    "contained set",
                    str(item.quantity),
                    "live",
                )
                for item in inventory.sets
            )
            rows.extend(
                (
                    item.set_num or "—",
                    "minifig",
                    str(item.quantity),
                    "live",
                )
                for item in inventory.minifigs
            )
            self._render_inventory(tuple(rows))
            self.query_one("#rb-state", expect_type=Static).update(
                f"Live inventory fetched explicitly · {len(rows)} rows"
            )
        finally:
            self._set_working(working=False)

    @on(Button.Pressed, "#rb-list-contents")
    def _list_contents_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        row = self._selected_collection_row()
        if row is not None:
            self._contents_list_id = int(row.key)
            self._contents_page = 1
            self._load_list_contents()

    @on(Button.Pressed, "#rb-contents-previous")
    def _contents_previous(self, event: Button.Pressed) -> None:
        event.stop()
        if self._contents_list_id is not None and self._contents_page > 1:
            self._contents_page -= 1
            self._load_list_contents()

    @on(Button.Pressed, "#rb-contents-next")
    def _contents_next(self, event: Button.Pressed) -> None:
        event.stop()
        if self._contents_list_id is not None and self._contents_has_next:
            self._contents_page += 1
            self._load_list_contents()

    @work(exclusive=True, group="rb-list-contents")
    async def _load_list_contents(self) -> None:
        data = self._data
        list_id = self._contents_list_id
        if data is None or list_id is None:
            return
        self._set_working(
            working=True,
            message="Loading read-only list contents…",
        )
        try:
            page = await data.collection_list_page(
                self._collection_kind,
                list_id,
                page=self._contents_page,
                page_size=_PAGE_SIZE,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            self.query_one("#rb-state", expect_type=Static).update(
                f"[red]Could not load list contents:[/] {error}"
            )
        else:
            rows = tuple(
                (row.entity_id or row.key, row.title, "", row.subtitle)
                for row in page.rows
            )
            self._render_inventory(rows)
            self._contents_has_next = page.has_next
            self._sync_controls()
            self.query_one("#rb-state", expect_type=Static).update(
                f"Read-only list contents · page {self._contents_page} · "
                f"{page.total} total"
            )
        finally:
            self._set_working(working=False)

    def _render_inventory(self, rows: tuple[tuple[str, str, str, str], ...]) -> None:
        table = self.query_one("#rb-inventory", expect_type=DataTable)
        table.clear()
        for row in rows:
            table.add_row(*row)

    def on_unmount(self) -> None:
        if self._search_timer is not None:
            self._search_timer.stop()
            self._search_timer = None
