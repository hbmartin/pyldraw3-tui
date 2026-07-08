"""Category and minifig-section tree for the catalog screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual import on
from textual.binding import Binding
from textual.widgets import Tree

from pyldraw3_tui.messages import CategoryScope, CategorySelected

if TYPE_CHECKING:
    from ldraw.parts import PartsCatalog


class CategoryTree(Tree[CategoryScope]):
    """Tree of All ▸ categories ▸ Minifig ▸ sections, with entry counts."""

    BINDINGS: ClassVar = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("l", "expand_cursor", show=False),
        Binding("h", "collapse_cursor", show=False),
    ]

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__("All parts", data=CategoryScope(), id=id)

    def set_catalog(self, catalog: PartsCatalog) -> None:
        """Rebuild the tree from the loaded catalog's contents."""
        self.clear()
        self.root.set_label(f"All parts ({len(catalog.by_code)})")
        for category in sorted(catalog.by_category):
            entries = catalog.entries_by_category(category)
            if not entries:
                continue
            self.root.add_leaf(
                f"{category.value.title()} ({len(entries)})",
                data=CategoryScope(category=category),
            )
        if catalog.by_minifig_section:
            minifig = self.root.add(
                f"Minifig ({len(catalog.minifig_entries())})",
                data=CategoryScope(minifig_only=True),
            )
            for section in sorted(catalog.by_minifig_section):
                entries = catalog.minifig_entries(section)
                minifig.add_leaf(
                    f"{section.value.title()} ({len(entries)})",
                    data=CategoryScope(minifig_section=section),
                )
        self.root.expand()

    @on(Tree.NodeSelected)
    def _selected(self, event: Tree.NodeSelected[CategoryScope]) -> None:
        event.stop()
        if event.node.data is not None:
            self.post_message(CategorySelected(event.node.data))

    def action_expand_cursor(self) -> None:
        """Expand the node under the cursor."""
        if self.cursor_node is not None and self.cursor_node.allow_expand:
            self.cursor_node.expand()

    def action_collapse_cursor(self) -> None:
        """Collapse the node under the cursor, or jump to its parent."""
        node = self.cursor_node
        if node is None:
            return
        if node.is_expanded and node.allow_expand:
            node.collapse()
        elif node.parent is not None:
            self.cursor_line = node.parent.line
