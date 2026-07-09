"""Drillable tree of a part's type-1 sub-part references."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, ClassVar

from ldraw.errors import PartError
from ldraw.parts import PartReferenceKind
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.widgets import Tree

if TYPE_CHECKING:
    from ldraw.parts import CatalogEntry, PartReference, Parts
    from textual.widgets.tree import TreeNode


@dataclass(frozen=True, slots=True)
class SubPartRef:
    """One reference in the sub-part tree; ``loaded`` gates lazy expansion."""

    code: str
    primitive: bool = False
    loaded: bool = False


class SubPartTree(Tree[SubPartRef]):
    """Lazy-expanding tree: each node's children are its own references."""

    BINDINGS: ClassVar = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__("No part selected", id=id)
        self._parts: Parts | None = None

    def set_parts(self, parts: Parts) -> None:
        """Provide the catalog used to resolve references."""
        self._parts = parts

    def set_root_entry(self, entry: CatalogEntry | None) -> None:
        """Show the reference tree for a catalog entry (or clear it)."""
        self.clear()
        if entry is None or self._parts is None:
            self.root.set_label("No part selected")
            self.root.data = None
            return
        self.root.set_label(f"{entry.code} — {entry.description}")
        self.root.data = SubPartRef(code=entry.code)
        self._populate(self.root)
        self.root.expand()

    @on(Tree.NodeExpanded)
    def _lazy_load(self, event: Tree.NodeExpanded[SubPartRef]) -> None:
        event.stop()
        if event.node.data is not None and not event.node.data.loaded:
            self._populate(event.node)

    def _populate(self, node: TreeNode[SubPartRef]) -> None:
        if node.data is None:
            return
        node.data = replace(node.data, loaded=True)
        references = self._references(node.data.code)
        for reference in references:
            node.add(
                self._reference_label(reference),
                data=SubPartRef(
                    code=reference.code,
                    primitive=reference.kind is PartReferenceKind.PRIMITIVE,
                ),
            )
        if not references:
            node.allow_expand = False

    def _references(self, code: str) -> tuple[PartReference, ...]:
        """Return the sub-part codes referenced by a part file."""
        if self._parts is None:
            return ()
        try:
            return self._parts.references_for(code)
        except (PartError, OSError, UnicodeDecodeError):
            return ()

    def _reference_label(self, reference: PartReference) -> Text:
        label = Text()
        label.append(reference.code, style="bold")
        if reference.description is not None:
            label.append(f" — {reference.description}")
        if reference.kind is PartReferenceKind.PRIMITIVE:
            label.append(" [primitive]", style="dim italic")
        return label
