"""Summary statistics for the selected model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ldraw.errors import NoGeometryError, PartNotFoundError
from rich.text import Text
from textual.widgets import Static

from pyldraw3_tui.widgets.colour_swatches import colour_chip

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw.parts import Parts
    from ldraw.pieces import Piece

MM_PER_LDU = 0.4


def _extent(values: Sequence[float]) -> str:
    return f"{min(values):g} … {max(values):g}"


def size_label(sizes: Sequence[float]) -> str:
    """Format per-axis sizes in LDU with the millimetre equivalent."""
    ldu = " x ".join(f"{size:g}" for size in sizes)
    mm = " x ".join(f"{size * MM_PER_LDU:.1f}" for size in sizes)
    return f"{ldu} LDU ({mm} mm)"


def _model_bounds(
    pieces: Sequence[Piece],
    parts: Parts | None,
) -> tuple[list[float], list[float]] | None:
    """Fold world-space part bounding boxes into whole-model bounds.

    Each piece's box corners are transformed by the piece's own placement;
    pieces whose part is unknown or draws no geometry are skipped.
    """
    if parts is None:
        return None
    lows: list[float] | None = None
    highs: list[float] | None = None
    for piece in pieces:
        try:
            box = parts.bounding_box(piece.part)
        except (PartNotFoundError, NoGeometryError):
            continue
        for corner in box.corners():
            world = piece.matrix * corner + piece.position
            point = [world.x, world.y, world.z]
            if lows is None or highs is None:
                lows = list(point)
                highs = list(point)
                continue
            lows = [min(lo, value) for lo, value in zip(lows, point, strict=True)]
            highs = [max(hi, value) for hi, value in zip(highs, point, strict=True)]
    if lows is None or highs is None:
        return None
    return lows, highs


class StatsPanel(Static):
    """Piece counts, colours used, building steps, and model bounds.

    Bounds fold each piece's true part geometry (via
    ``Parts.bounding_box``); when no piece geometry resolves, the panel
    falls back to the min/max of piece origins.
    """

    def show_model(
        self,
        pieces: Sequence[Piece],
        parts: Parts | None,
        steps: int | None = None,
    ) -> None:
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
        if steps is not None:
            line("building steps", str(steps))
        if (bounds := _model_bounds(pieces, parts)) is not None:
            lows, highs = bounds
            line("bounding box", "(true part geometry)")
            for axis, low, high in zip("xyz", lows, highs, strict=True):
                line(axis, _extent([low, high]))
            sizes = [high - low for low, high in zip(lows, highs, strict=True)]
            line("size", size_label(sizes))
        else:
            line("placement extents", "(piece origins, not true bounds)")
            line("x", _extent([piece.position.x for piece in pieces]))
            line("y", _extent([piece.position.y for piece in pieces]))
            line("z", _extent([piece.position.z for piece in pieces]))
        self.update(text)
