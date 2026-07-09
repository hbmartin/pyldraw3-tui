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

OPAQUE_ALPHA = 255
_SWATCH_GLYPHS = "██"


def resolve_colour(colour: Colour, parts: Parts | None) -> Colour:
    """Return the palette colour for a placement colour when known.

    Placement colours parsed from files carry only a code; the palette
    entry adds name/rgb/alpha. Direct colours pass through unchanged.
    """
    if colour.code is None or parts is None:
        return colour
    return parts.colours_by_code.get(colour.code, colour)


def colour_chip(colour: Colour, parts: Parts | None = None) -> Text:
    """Return a small true-colour swatch followed by the colour's label."""
    resolved = resolve_colour(colour, parts)
    chip = Text()
    if resolved.rgb is not None:
        chip.append(_SWATCH_GLYPHS, style=resolved.rgb)
    else:
        chip.append(_SWATCH_GLYPHS, style="dim")
    chip.append(f" {colour_label(resolved)}")
    return chip


def colour_label(colour: Colour) -> str:
    """Return a short textual name for a colour."""
    if colour.name is not None:
        return colour.name
    if colour.code is not None:
        return str(colour.code)
    if colour.rgb is not None:
        return colour.rgb
    return "?"


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
                if colour.alpha is not None and colour.alpha < OPAQUE_ALPHA:
                    text.append(f" (alpha {colour.alpha})", style="dim italic")
                if colour.colour_attributes:
                    attributes = ", ".join(colour.colour_attributes)
                    text.append(f" [{attributes}]", style="dim")
        self.update(text)
