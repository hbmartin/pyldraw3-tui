"""Summary statistics for the selected model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import Static

from pyldraw3_tui.widgets.colour_swatches import colour_chip

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw.parts import Parts
    from ldraw.pieces import Piece


def _extent(values: Sequence[float]) -> str:
    return f"{min(values):g} … {max(values):g}"


class StatsPanel(Static):
    """Piece counts, colours used, and placement extents.

    Extents are the min/max of piece *origins* on each axis — not a true
    geometry bounding box, which would need the (cut) geometry pipeline.
    """

    def show_model(self, pieces: Sequence[Piece], parts: Parts | None) -> None:
        """Render the stats for a model's leaf pieces."""
        if not pieces:
            self.update("Model has no pieces.")
            return
        text = Text()

        def line(label: str, value: Text | str) -> None:
            if text:
                text.append("\n")
            text.append(f"{label:>24}  ", style="bold dim")
            text.append(value)

        colours = {piece.colour for piece in pieces}
        line("pieces", str(len(pieces)))
        line("distinct parts", str(len({piece.part for piece in pieces})))
        line("distinct colours", str(len(colours)))
        for colour in sorted(
            colours,
            key=lambda c: c.code if c.code is not None else -1,
        ):
            line("", colour_chip(colour, parts))
        line("placement extents", "(piece origins, not true bounds)")
        line("x", _extent([piece.position.x for piece in pieces]))
        line("y", _extent([piece.position.y for piece in pieces]))
        line("z", _extent([piece.position.z for piece in pieces]))
        self.update(text)
