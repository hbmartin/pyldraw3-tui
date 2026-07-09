"""LDraw palette swatches and shared colour-rendering helpers.

LDraw part files are colour-agnostic (geometry uses the special main/edge
colours), so the Info pane shows the palette as *reference* swatches — the
colours a part could be placed in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import Static

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ldraw.colour import Colour
    from ldraw.parts import Parts

_SWATCH_GLYPHS = "██"


def resolve_colour(colour: Colour, parts: Parts | None) -> Colour:
    """Return the palette colour for a placement colour when known.

    Placement colours parsed from files carry only a code; the palette
    entry adds name/rgb/alpha. Direct colours pass through unchanged.
    """
    return colour if parts is None else parts.resolve_colour(colour)


def colour_chip(colour: Colour, parts: Parts | None = None) -> Text:
    """Return a small true-colour swatch followed by the colour's label."""
    resolved = resolve_colour(colour, parts)
    chip = Text()
    if resolved.swatch_rgb is not None:
        chip.append(_SWATCH_GLYPHS, style=resolved.swatch_rgb)
    else:
        chip.append(_SWATCH_GLYPHS, style="dim")
    chip.append(f" {resolved.display_label}")
    return chip


def colour_label(colour: Colour) -> str:
    """Return a short textual name for a colour."""
    return colour.display_label


class ColourSwatches(Static):
    """The LDraw palette rendered as one labelled chip per line."""

    def set_palette(self, colours: Iterable[Colour]) -> None:
        """Render palette colours sorted by code."""
        text = Text()
        for colour in sorted(
            colours, key=lambda c: c.code if c.code is not None else -1
        ):
            if text:
                text.append("\n")
            text.append(colour_chip(colour))
            text.append(f" {colour.code}", style="bold")
            if colour.is_solid:
                text.append(" [solid]", style="dim")
            else:
                if colour.is_transparent:
                    text.append(
                        f" (alpha {colour.swatch_alpha})",
                        style="dim italic",
                    )
                if colour.colour_attributes:
                    attributes = ", ".join(colour.colour_attributes)
                    text.append(f" [{attributes}]", style="dim")
        self.update(text)
