"""Rebrickable annotation of the BOM currently displayed by the Model view."""

# Textual lifecycle hooks and public state properties are framework-facing.
# ruff: noqa: D102

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

from rebrickable import MappingStatus, TranslationReport, part_url
from rich.text import Text
from textual import on, work
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, LoadingIndicator, Static

from pyldraw3_tui.screens.chooser import ChooserScreen

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw.bom import BomRow
    from ldraw.parts import Parts
    from rebrickable import TranslatedBomRow
    from textual.app import ComposeResult
    from textual.worker import Worker

    from pyldraw3_tui.data.rebrickable import RebrickableDataProtocol


def _match_detail(row: TranslatedBomRow) -> Text:
    text = Text()
    text.append(f"{row.status.value.upper()}\n", style="bold")
    text.append(
        f"LDraw {row.ldraw_part_num} / color {row.ldraw_color_code} x {row.quantity}\n"
    )
    text.append(
        f"Rebrickable {row.rebrickable_part_num or '—'} / color "
        f"{row.rebrickable_color_id if row.rebrickable_color_id is not None else '—'}"
        "\n\n"
    )
    text.append("Part mapping\n", style="bold dim")
    text.append(f"{row.part_match.source.value}: {row.part_match.explanation or '—'}\n")
    for candidate in row.part_match.candidates:
        name = f" · {candidate.name}" if candidate.name else ""
        text.append(
            f"  {candidate.identifier}{name} · {candidate.reason} "
            f"({candidate.confidence:.2f})\n"
        )
    text.append("\nColor mapping\n", style="bold dim")
    text.append(
        f"{row.color_match.source.value}: {row.color_match.explanation or '—'}\n"
    )
    for candidate in row.color_match.candidates:
        name = f" · {candidate.name}" if candidate.name else ""
        text.append(
            f"  {candidate.identifier}{name} · {candidate.reason} "
            f"({candidate.confidence:.2f})\n"
        )
    return text


class RebrickableTranslation(Vertical):
    """Translate and explain the current LDraw BOM without hiding uncertainty."""

    DEFAULT_CSS = """
    RebrickableTranslation #rb-translation-summary {
        height: auto;
        min-height: 2;
        padding: 0 1;
    }
    RebrickableTranslation #rb-translation-loading {
        height: 1;
        display: none;
    }
    RebrickableTranslation.working #rb-translation-loading {
        display: block;
    }
    RebrickableTranslation #rb-translation-content {
        height: 1fr;
    }
    RebrickableTranslation #rb-translation-table {
        width: 1fr;
    }
    RebrickableTranslation #rb-translation-detail-pane {
        width: 42;
        min-width: 32;
        border-left: solid $primary-muted;
        padding-left: 1;
    }
    RebrickableTranslation #rb-translation-detail {
        height: 1fr;
        overflow-y: auto;
    }
    RebrickableTranslation #rb-enrich-row {
        height: 3;
    }
    """

    def __init__(
        self,
        data: RebrickableDataProtocol | None = None,
        *,
        id: str | None = None,  # noqa: A002 - Textual idiom
    ) -> None:
        super().__init__(id=id)
        self._data = data
        self._bom_rows: tuple[BomRow, ...] = ()
        self._parts: Parts | None = None
        self._report: TranslationReport | None = None
        self._rows_by_key: dict[str, TranslatedBomRow] = {}
        self._selected_key: str | None = None
        self._generation = 0

    def compose(self) -> ComposeResult:
        yield Static(
            "Open a model to translate its displayed BOM.",
            id="rb-translation-summary",
        )
        yield LoadingIndicator(id="rb-translation-loading")
        with Horizontal(id="rb-translation-content"):
            yield DataTable[str](id="rb-translation-table")
            with Vertical(id="rb-translation-detail-pane"):
                yield Static("No translated row selected.", id="rb-translation-detail")
                yield Button(
                    "Verify candidates live",
                    id="rb-enrich-row",
                    disabled=True,
                )

    def on_mount(self) -> None:
        table = self.query_one("#rb-translation-table", expect_type=DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "Status",
            "LD part",
            "LD c",
            "Qty",
            "RB part",
            "RB c",
            "P src",
            "C src",
        )
        if self._bom_rows:
            self._start_translation()

    def set_data(self, data: RebrickableDataProtocol | None) -> None:
        self._data = data
        if self.is_mounted and self._bom_rows:
            self._start_translation()

    def set_bom(self, rows: Sequence[BomRow], parts: Parts | None) -> None:
        """Translate the exact BOM visible in the neighboring Model tab."""
        self._bom_rows = tuple(rows)
        self._parts = parts
        if not self.is_mounted:
            return
        if not self._bom_rows:
            # Invalidate a translation already in flight so it cannot repopulate
            # the table after the displayed BOM has been cleared.
            self._generation += 1
            self._report = None
            self._rows_by_key = {}
            self._selected_key = None
            self.query_one("#rb-translation-table", expect_type=DataTable).clear()
            self.query_one("#rb-translation-summary", expect_type=Static).update(
                "The displayed BOM is empty."
            )
            self.query_one("#rb-translation-detail", expect_type=Static).update(
                "No translated row selected."
            )
            self.query_one("#rb-enrich-row", expect_type=Button).disabled = True
            return
        self._start_translation()

    @property
    def report(self) -> TranslationReport | None:
        return self._report

    @property
    def selected_page_url(self) -> str | None:
        row = self.selected_row
        if row is None or row.rebrickable_part_num is None:
            return None
        return part_url(row.rebrickable_part_num)

    @property
    def selected_identifier(self) -> str | None:
        row = self.selected_row
        return row.rebrickable_part_num if row is not None else None

    @property
    def selected_row(self) -> TranslatedBomRow | None:
        if self._selected_key is None:
            return None
        return self._rows_by_key.get(self._selected_key)

    def _set_working(self, *, working: bool) -> None:
        self.set_class(working, "working")

    def _start_translation(self) -> Worker[None]:
        self._generation += 1
        # Cast: ty resolves the @work decorator's async overload imprecisely.
        return cast(
            "Worker[None]",
            self._translate(
                self._generation,
                self._bom_rows,
                self._parts,
            ),
        )

    @work(exclusive=True, group="rb-translation")
    async def _translate(
        self,
        generation: int,
        rows: tuple[BomRow, ...],
        parts: Parts | None,
    ) -> None:
        data = self._data
        if data is None:
            if generation == self._generation:
                self.query_one("#rb-translation-summary", expect_type=Static).update(
                    "Rebrickable is unavailable; check its configuration."
                )
            return
        self._set_working(working=True)
        self.query_one("#rb-translation-summary", expect_type=Static).update(
            "Translating displayed BOM against the local Rebrickable snapshot…"
        )
        try:
            report = await data.translate(rows, parts=parts)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            if generation == self._generation:
                self._report = None
                self._rows_by_key = {}
                self._selected_key = None
                self.query_one("#rb-translation-summary", expect_type=Static).update(
                    f"[red]Translation unavailable:[/] {error}. "
                    "Open Rebrickable and refresh its local catalog if needed."
                )
                self.query_one("#rb-translation-table", expect_type=DataTable).clear()
                self.query_one("#rb-translation-detail", expect_type=Static).update(
                    "No translated row selected."
                )
                self.query_one("#rb-enrich-row", expect_type=Button).disabled = True
        else:
            if generation == self._generation:
                self._show_report(report)
        finally:
            if generation == self._generation:
                self._set_working(working=False)

    def _show_report(self, report: TranslationReport) -> None:
        self._report = report
        table = self.query_one("#rb-translation-table", expect_type=DataTable)
        table.clear()
        self._rows_by_key = {}
        for index, row in enumerate(report.rows):
            key = f"{index}:{row.ldraw_part_num}:{row.ldraw_color_code}"
            self._rows_by_key[key] = row
            status_style = {
                MappingStatus.RESOLVED: "green",
                MappingStatus.AMBIGUOUS: "yellow",
                MappingStatus.UNRESOLVED: "red",
            }[row.status]
            table.add_row(
                Text(row.status.value, style=status_style),
                row.ldraw_part_num,
                str(row.ldraw_color_code),
                str(row.quantity),
                row.rebrickable_part_num or "—",
                str(row.rebrickable_color_id)
                if row.rebrickable_color_id is not None
                else "—",
                self._source_label(row.part_match.source.value),
                self._source_label(row.color_match.source.value),
                key=key,
            )
        self._selected_key = next(iter(self._rows_by_key), None)
        self.query_one("#rb-translation-summary", expect_type=Static).update(
            f"Resolved {report.resolved_count} · Ambiguous {report.ambiguous_count} · "
            f"Unresolved {report.unresolved_count} · snapshot {report.snapshot_id}"
        )
        # Refresh the pane from _selected_key rather than relying on the
        # RowHighlighted that clear() plus the first add_row happens to emit:
        # that emission is a DataTable implementation detail, and it never
        # arrives at all for an empty report, which would strand the enrich
        # button enabled for the previous report's row.
        table.move_cursor(row=0)
        self._show_selected_row()

    def _show_selected_row(self) -> None:
        detail = self.query_one("#rb-translation-detail", expect_type=Static)
        button = self.query_one("#rb-enrich-row", expect_type=Button)
        if (row := self.selected_row) is None:
            detail.update("No translated row selected.")
            button.disabled = True
            return
        detail.update(_match_detail(row))
        button.disabled = self._candidate_request_count(row) == 0

    @staticmethod
    def _source_label(source: str) -> str:
        return {
            "user_override": "override",
            "api_external_id": "api",
            "exact_canonical_id": "exact",
            "relationship_candidate": "candidate",
        }.get(source, source)

    @on(DataTable.RowHighlighted, "#rb-translation-table")
    def _row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._selected_key = event.row_key.value if event.row_key is not None else None
        self._show_selected_row()

    @staticmethod
    def _candidate_request_count(row: TranslatedBomRow) -> int:
        part = (
            len(row.part_match.candidates)
            if row.part_match.status is not MappingStatus.RESOLVED
            else 0
        )
        color = (
            len(row.color_match.candidates)
            if row.color_match.status is not MappingStatus.RESOLVED
            else 0
        )
        return part + color

    @on(Button.Pressed, "#rb-enrich-row")
    def _confirm_enrich(self, event: Button.Pressed) -> None:
        event.stop()
        row = self.selected_row
        if row is None:
            return
        count = self._candidate_request_count(row)
        if not count:
            self.app.notify(
                "This row has no known candidates to verify; it remains explicit.",
                severity="warning",
            )
            return
        self.app.push_screen(
            ChooserScreen(
                f"Verify {count} candidate{'s' if count != 1 else ''} sequentially?",
                [("Verify candidates", "verify"), ("Cancel", "cancel")],
            ),
            self._enrich_choice,
        )

    def _enrich_choice(self, choice: str | None) -> None:
        if choice == "verify":
            self._enrich()

    @work(exclusive=True, group="rb-enrichment")
    async def _enrich(self) -> None:
        row = self.selected_row
        data = self._data
        if row is None or data is None:
            return
        self._set_working(working=True)
        self.query_one("#rb-translation-summary", expect_type=Static).update(
            "Verifying selected-row candidates at the API client's paced rate…"
        )
        try:
            requests = await data.enrich_row(row)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            self.query_one("#rb-translation-summary", expect_type=Static).update(
                f"[red]Live candidate verification failed:[/] {error}"
            )
        else:
            self.app.notify(f"Verified {requests} mapping candidates.")
            worker = self._start_translation()
            await worker.wait()
        finally:
            self._set_working(working=False)
