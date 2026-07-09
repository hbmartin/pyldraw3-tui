"""Summary statistics for the selected model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ldraw import ModelSummary
from rich.text import Text
from textual.widgets import Static

from pyldraw3_tui.widgets.colour_swatches import colour_chip

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw.model import Model, ModelOccurrence
    from ldraw.part_geometry_types import BoundingBox
    from ldraw.parts import Parts
    from ldraw.pieces import Vector

MM_PER_LDU = 0.4


def _extent(values: Sequence[float]) -> str:
    return f"{min(values):g} … {max(values):g}"


def size_label(sizes: Sequence[float]) -> str:
    """Format per-axis sizes in LDU with the millimetre equivalent."""
    ldu = " x ".join(f"{size:g}" for size in sizes)
    mm = " x ".join(f"{size * MM_PER_LDU:.1f}" for size in sizes)
    return f"{ldu} LDU ({mm} mm)"


def _components(vector: Vector) -> list[float]:
    return [vector.x, vector.y, vector.z]


def _bounds_components(bounds: BoundingBox) -> tuple[list[float], list[float]]:
    return _components(bounds.min), _components(bounds.max)


class StatsPanel(Static):
    """Piece counts, colours used, building steps, and model bounds.

    Bounds come from ``ModelSummary``; when no piece geometry resolves, the
    panel falls back to the min/max of piece origins.
    """

    def show_model(
        self,
        model: Model,
        parts: Parts | None,
        steps: int | None = None,
    ) -> None:
        """Render the stats for a model's leaf pieces."""
        occurrences = tuple(model.iter_occurrences())
        if not occurrences:
            self.update("Model has no pieces.")
            return
        text = Text()

        def line(label: str, value: Text | str) -> None:
            if text:
                text.append("\n")
            text.append(f"{label:>24}  ", style="bold dim")
            text.append(value)

        summary = ModelSummary.from_model(model, parts) if parts is not None else None
        colours = {occurrence.colour for occurrence in occurrences}
        line(
            "pieces",
            str(summary.occurrence_count if summary is not None else len(occurrences)),
        )
        line(
            "distinct parts",
            str(
                len(summary.part_counts)
                if summary is not None
                else len({occurrence.part_code for occurrence in occurrences})
            ),
        )
        line("distinct colours", str(len(colours)))
        for colour in sorted(
            colours,
            key=lambda c: c.code if c.code is not None else -1,
        ):
            line("", colour_chip(colour, parts))
        if steps is not None:
            line("building steps", str(steps))
        if summary is not None and summary.bounds is not None:
            bounds = summary.bounds
            lows, highs = _bounds_components(bounds)
            line("bounding box", "(true part geometry)")
            for axis, low, high in zip("xyz", lows, highs, strict=True):
                line(axis, _extent([low, high]))
            line("size", size_label(_components(bounds.size)))
        else:
            lows, highs = _placement_bounds(occurrences, summary)
            line("placement extents", "(piece origins, not true bounds)")
            for axis, low, high in zip("xyz", lows, highs, strict=True):
                line(axis, _extent([low, high]))
        if summary is not None and summary.skipped_geometry:
            line("skipped geometry", str(len(summary.skipped_geometry)))
        self.update(text)


def _placement_bounds(
    occurrences: Sequence[ModelOccurrence],
    summary: ModelSummary | None,
) -> tuple[list[float], list[float]]:
    if summary is not None and summary.origin_bounds is not None:
        return _bounds_components(summary.origin_bounds)
    return (
        [
            min(occurrence.position.x for occurrence in occurrences),
            min(occurrence.position.y for occurrence in occurrences),
            min(occurrence.position.z for occurrence in occurrences),
        ],
        [
            max(occurrence.position.x for occurrence in occurrences),
            max(occurrence.position.y for occurrence in occurrences),
            max(occurrence.position.z for occurrence in occurrences),
        ],
    )
