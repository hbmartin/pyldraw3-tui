"""Right-hand detail pane: part metadata, palette, and sub-part tree."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ldraw.errors import NoGeometryError, PartNotFoundError
from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane

from pyldraw3_tui.data.snippets import import_snippet
from pyldraw3_tui.widgets.colour_swatches import ColourSwatches
from pyldraw3_tui.widgets.stats_panel import size_label
from pyldraw3_tui.widgets.subpart_tree import SubPartTree

if TYPE_CHECKING:
    from ldraw.parts import CatalogEntry, Parts
    from textual.app import ComposeResult


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


def _geometry_lines(entry: CatalogEntry, parts: Parts | None) -> list[tuple[str, str]]:
    """Return size/stud metadata lines, empty when geometry is unavailable."""
    if parts is None:
        return []
    try:
        size = parts.bounding_box(entry.code).size
        top_studs = len(parts.stud_positions(entry.code))
    except (PartNotFoundError, NoGeometryError):
        return []
    lines = [("size", size_label([size.x, size.y, size.z]))]
    if top_studs:
        lines.append(("studs", f"{top_studs} top"))
    return lines


def _metadata_text(
    entry: CatalogEntry,
    library_root: Path | None = None,
    parts: Parts | None = None,
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
    for label, value in _geometry_lines(entry, parts):
        line(label, value)
    if entry.part is not None:
        line("file", _display_path(Path(entry.part.path), library_root))
    if (import_line := import_snippet(entry)) is not None:
        line("import", import_line)
    return text


class PartDetail(Vertical):
    """Tabbed Info (metadata + palette swatches) and Sub-parts views."""

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__(id=id)
        self._parts: Parts | None = None
        self._library_root: Path | None = None
        self._entry: CatalogEntry | None = None

    def compose(self) -> ComposeResult:
        """Lay out the Info and Sub-parts tabs."""
        with TabbedContent(id="detail-tabs"):
            with TabPane("Info", id="tab-info"), VerticalScroll():
                yield Static("No part selected", id="part-metadata")
                yield Static("Palette (reference)", id="palette-heading")
                yield ColourSwatches(id="palette-swatches")
            with TabPane("Sub-parts", id="tab-subparts"):
                yield SubPartTree(id="subpart-tree")

    def set_parts(self, parts: Parts) -> None:
        """Provide the catalog: fills the palette and enables drill-down."""
        self._parts = parts
        self._library_root = _library_root(parts)
        self.query_one("#palette-swatches", ColourSwatches).set_palette(
            parts.colours_by_code.values(),
        )
        self.query_one("#subpart-tree", SubPartTree).set_parts(parts)
        if self._entry is not None:
            self.show_entry(self._entry)

    def show_entry(self, entry: CatalogEntry | None) -> None:
        """Display metadata and the sub-part tree for an entry."""
        self._entry = entry
        metadata = self.query_one("#part-metadata", Static)
        if entry is None:
            metadata.update("No part selected")
        else:
            metadata.update(_metadata_text(entry, self._library_root, self._parts))
        self.query_one("#subpart-tree", SubPartTree).set_root_entry(entry)
