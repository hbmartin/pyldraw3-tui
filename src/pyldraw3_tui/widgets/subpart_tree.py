"""Drillable tree of a part's type-1 sub-part references."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, ClassVar

from ldraw.errors import PartError
from ldraw.pieces import Piece
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.widgets import Tree

if TYPE_CHECKING:
    from ldraw.parts import CatalogEntry, Parts
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
        for code in references:
            node.add(
                self._reference_label(code),
                data=SubPartRef(code=code, primitive=self._is_primitive(code)),
            )
        if not references:
            node.allow_expand = False

    def _references(self, code: str) -> list[str]:
        """Return the sub-part codes referenced by a part file."""
        if self._parts is None:
            return []
        if (part := self._parts.find_part(code=code)) is None:
            return []
        try:
            return [obj.part for obj in part.objects if isinstance(obj, Piece)]
        except (PartError, OSError, UnicodeDecodeError):
            return []

    def _is_primitive(self, code: str) -> bool:
        if self._parts is None:
            return False
        return code.lower() in self._parts.primitives_by_code

    def _description(self, code: str) -> str | None:
        if self._parts is None:
            return None
        return self._parts.description_for(code) or self._parts.primitives_by_code.get(
            code.lower()
        )

    def _reference_label(self, code: str) -> Text:
        label = Text()
        label.append(code, style="bold")
        if (description := self._description(code)) is not None:
            label.append(f" — {description}")
        if self._is_primitive(code):
            label.append(" [primitive]", style="dim italic")
        return label
