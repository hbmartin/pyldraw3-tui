"""Right-hand detail pane: part metadata, palette, and sub-part tree."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ldraw.errors import PartError
from rich.text import Text
from textual import on, work
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane
from textual.worker import Worker, WorkerState

from pyldraw3_tui.data.snippets import import_snippet
from pyldraw3_tui.widgets.colour_swatches import ColourSwatches
from pyldraw3_tui.widgets.connections import PartConnections
from pyldraw3_tui.widgets.stats_panel import size_label
from pyldraw3_tui.widgets.subpart_tree import SubPartTree

if TYPE_CHECKING:
    from ldraw import PartGeometry
    from ldraw.parts import CatalogEntry, Parts
    from textual.app import ComposeResult

logger = logging.getLogger(__name__)


def _library_root(parts: Parts) -> Path | None:
    """Return the root folder that contains parts, primitives, and parts.lst."""
    parts_lst = getattr(parts, "path", None)
    if parts_lst is None:
        return None
    path = Path(parts_lst)
    return path.parent if path.name.lower() == "parts.lst" else path


def _display_path(path: Path, library_root: Path | None) -> str:
    """Prefer stable library-relative paths over machine-specific absolutes."""
    if library_root is not None:
        try:
            return path.relative_to(library_root).as_posix()
        except ValueError:
            pass
    return str(path)


def _geometry_lines(geometry: PartGeometry) -> list[tuple[str, str]]:
    """Return compact geometry and connection summary lines."""
    lines: list[tuple[str, str]] = []
    if geometry.bounds is not None:
        size = geometry.bounds.size
        lines.append(("size", size_label([size.x, size.y, size.z])))
    top_studs = len(geometry.top_studs)
    if top_studs:
        lines.append(("studs", f"{top_studs} top"))
    lines.append(("connections", str(len(geometry.connections))))
    if geometry.connection_metadata is not None:
        lines.append(("coverage", geometry.connection_metadata.coverage.value))
    return lines


def _metadata_text(
    entry: CatalogEntry,
    library_root: Path | None = None,
    geometry: PartGeometry | None = None,
    geometry_error: str | None = None,
) -> Text:
    """Render an entry's metadata as labelled lines."""
    text = Text()

    def line(label: str, value: str) -> None:
        if text:
            text.append("\n")
        text.append(f"{label:>12}  ", style="bold dim")
        text.append(value)

    line("code", entry.code)
    line("description", entry.description)
    line("category", entry.category.value)
    if entry.minifig_section is not None:
        line("minifig", entry.minifig_section.value)
    if entry.keywords:
        line("keywords", ", ".join(entry.keywords))
    if geometry is not None:
        for label, value in _geometry_lines(geometry):
            line(label, value)
    elif geometry_error is not None:
        line("geometry", f"unavailable: {geometry_error}")
    if entry.part is not None:
        line(
            "file",
            _display_path(
                path=Path(entry.part.path),
                library_root=library_root,
            ),
        )
    if (import_line := import_snippet(entry)) is not None:
        line("import", import_line)
    return text


class PartDetail(Vertical):
    """Tabbed metadata, connections, palette, and sub-part references."""

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__(id=id)
        self._parts: Parts | None = None
        self._library_root: Path | None = None
        self._entry: CatalogEntry | None = None
        self._geometry_worker: Worker[None] | None = None
        self._geometry_request_id = 0
        self._active_geometry: tuple[str, Parts, int] | None = None
        self._pending_geometry: tuple[str, Parts] | None = None
        self._displayed_geometry: tuple[str, Parts, PartGeometry] | None = None

    def compose(self) -> ComposeResult:
        """Lay out the Info and Sub-parts tabs."""
        with TabbedContent(id="detail-tabs"):
            with TabPane("Info", id="tab-info"), VerticalScroll():
                yield Static("No part selected", id="part-metadata")
                yield Static("Palette (reference)", id="palette-heading")
                yield ColourSwatches(id="palette-swatches")
            with TabPane("Connections", id="tab-connections"):
                yield PartConnections(id="part-connections")
            with TabPane("Sub-parts", id="tab-subparts"):
                yield SubPartTree(id="subpart-tree")

    def set_parts(self, parts: Parts) -> None:
        """Provide the catalog: fills the palette and enables drill-down."""
        self._parts = parts
        self._library_root = _library_root(parts)
        self.query_one("#palette-swatches", expect_type=ColourSwatches).set_palette(
            parts.colours_by_code.values(),
        )
        self.query_one("#subpart-tree", expect_type=SubPartTree).set_parts(parts)
        if self._entry is not None:
            self.show_entry(self._entry)

    def show_entry(self, entry: CatalogEntry | None) -> None:
        """Display metadata and the sub-part tree for an entry."""
        self._entry = entry
        metadata = self.query_one("#part-metadata", expect_type=Static)
        connections = self.query_one("#part-connections", expect_type=PartConnections)
        if entry is None:
            self._pending_geometry = None
            metadata.update("No part selected")
            connections.show_empty()
        elif self._parts is None:
            metadata.update(
                _metadata_text(entry=entry, library_root=self._library_root)
            )
            self._pending_geometry = None
            connections.show_unavailable("Catalog not loaded.")
        elif (
            self._displayed_geometry is not None
            and self._displayed_geometry[0] == entry.code
            and self._displayed_geometry[1] is self._parts
        ):
            self._pending_geometry = None
            self._geometry_ready(
                code=entry.code,
                parts=self._parts,
                geometry=self._displayed_geometry[2],
            )
        else:
            metadata.update(
                _metadata_text(entry=entry, library_root=self._library_root)
            )
            connections.show_loading(entry.code)
            self._request_geometry(code=entry.code, parts=self._parts)
        self.query_one("#subpart-tree", expect_type=SubPartTree).set_root_entry(entry)

    def _request_geometry(self, code: str, parts: Parts) -> None:
        """Coalesce highlights so only one recursive geometry query runs at once."""
        request = (code, parts)
        worker = self._geometry_worker
        if worker is not None and (worker.is_cancelled or worker.is_finished):
            self._geometry_worker = None
            self._active_geometry = None
        if (
            self._active_geometry is not None
            and self._active_geometry[0] == code
            and self._active_geometry[1] is parts
        ):
            self._pending_geometry = None
            return
        self._pending_geometry = request
        if self._geometry_worker is None or self._geometry_worker.is_finished:
            self._start_pending_geometry()

    def _start_pending_geometry(self) -> None:
        """Start the newest queued geometry request, if one exists."""
        request = self._pending_geometry
        if request is None:
            return
        self._pending_geometry = None
        self._geometry_request_id += 1
        request_id = self._geometry_request_id
        self._active_geometry = (*request, request_id)
        code, parts = request
        self._geometry_worker = self._load_geometry(
            code=code,
            parts=parts,
            request_id=request_id,
        )

    @work(
        thread=True,
        group="part-geometry",
        exit_on_error=False,
    )
    def _load_geometry(self, code: str, parts: Parts, request_id: int) -> None:
        """Resolve one part off-thread and finish through the serialized queue."""
        try:
            geometry = parts.geometry(code)
        except (OSError, PartError, ValueError) as error:
            reason = str(error) or type(error).__name__
            self.app.call_from_thread(
                self._geometry_finished,
                code=code,
                parts=parts,
                request_id=request_id,
                geometry=None,
                reason=reason,
            )
            return
        except Exception as error:
            logger.exception("Unexpected geometry failure for %s", code)
            reason = str(error) or type(error).__name__
            self.app.call_from_thread(
                self._geometry_finished,
                code=code,
                parts=parts,
                request_id=request_id,
                geometry=None,
                reason=reason,
            )
            return
        self.app.call_from_thread(
            self._geometry_finished,
            code=code,
            parts=parts,
            request_id=request_id,
            geometry=geometry,
            reason=None,
        )

    def _geometry_finished(
        self,
        code: str,
        parts: Parts,
        request_id: int,
        geometry: PartGeometry | None,
        reason: str | None,
    ) -> None:
        """Render the current result, then start only the latest queued request."""
        if self._active_geometry is None or self._active_geometry[2] != request_id:
            return
        self._geometry_worker = None
        self._active_geometry = None
        try:
            if geometry is not None:
                self._geometry_ready(code=code, parts=parts, geometry=geometry)
            else:
                self._geometry_failed(
                    code=code,
                    parts=parts,
                    reason=reason or "Unknown geometry failure",
                )
        finally:
            self._start_pending_geometry()

    @on(Worker.StateChanged)
    def _geometry_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Release a request whose worker ended before reporting its result."""
        if event.worker is not self._geometry_worker or event.state not in {
            WorkerState.CANCELLED,
            WorkerState.ERROR,
        }:
            return
        active = self._active_geometry
        pending = self._pending_geometry
        self._geometry_worker = None
        self._active_geometry = None
        if active is not None and pending is None:
            error = event.worker.error
            reason = (
                str(error) or type(error).__name__
                if error is not None
                else "Geometry loading was cancelled"
            )
            self._geometry_failed(code=active[0], parts=active[1], reason=reason)
        self._start_pending_geometry()

    def _geometry_ready(
        self,
        code: str,
        parts: Parts,
        geometry: PartGeometry,
    ) -> None:
        """Render a completed geometry query if its selection is current."""
        if self._entry is None or self._entry.code != code or self._parts is not parts:
            return
        self._displayed_geometry = (code, parts, geometry)
        self.query_one("#part-metadata", expect_type=Static).update(
            _metadata_text(
                entry=self._entry,
                library_root=self._library_root,
                geometry=geometry,
            )
        )
        self.query_one("#part-connections", expect_type=PartConnections).show_geometry(
            geometry
        )

    def _geometry_failed(self, code: str, parts: Parts, reason: str) -> None:
        """Render a nonfatal geometry failure if its selection is current."""
        if self._entry is None or self._entry.code != code or self._parts is not parts:
            return
        self._displayed_geometry = None
        self.query_one("#part-metadata", expect_type=Static).update(
            _metadata_text(
                entry=self._entry,
                library_root=self._library_root,
                geometry_error=reason,
            )
        )
        self.query_one(
            "#part-connections", expect_type=PartConnections
        ).show_unavailable(reason)
