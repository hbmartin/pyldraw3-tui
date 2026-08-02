"""Semantic state for a selected instruction step."""

from __future__ import annotations

from dataclasses import fields
from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import Static

if TYPE_CHECKING:
    from ldraw.instructions import InstructionStep


class InstructionDetails(Static):
    """Renderer-neutral rotation, camera, layout, and callout state."""

    def show_step(self, step: InstructionStep, *, total_steps: int) -> None:
        """Render the effective semantics for one section-local step."""
        text = Text()

        def line(label: str, value: str) -> None:
            if text:
                text.append("\n")
            text.append(f"{label:>24}  ", style="bold dim")
            text.append(value)

        line("instruction step", f"{step.number} of {total_steps}")
        line("source lines", _source_lines(step))
        line("added occurrences", str(len(step.added_occurrences())))
        line("cumulative occurrences", str(len(step.cumulative_occurrences())))
        line("rotation", _rotation(step))
        line("camera", _camera(step))
        line("callouts", _callouts(step))
        line(
            "multi-step group",
            "—" if step.multi_step_group is None else str(step.multi_step_group),
        )
        line("page break before", _yes_no(value=step.page_break_before))
        line("suppressed", _yes_no(value=step.suppressed))
        self.update(text)


def _source_lines(step: InstructionStep) -> str:
    start, end = step.source_start_line, step.source_end_line
    if start is None:
        return "—"
    return str(start) if end is None or end == start else f"{start}-{end}"


def _rotation(step: InstructionStep) -> str:
    rotation = step.rotation
    if rotation is None:
        return "—"
    if rotation.angles is None:
        return rotation.mode.value
    angles = ", ".join(f"{value:g}" for value in rotation.angles)
    return f"{rotation.mode.value} ({angles})"


def _camera(step: InstructionStep) -> str:
    values = [
        f"{item.name}={_value(getattr(step.camera, item.name))}"
        for item in fields(step.camera)
        if getattr(step.camera, item.name) is not None
    ]
    return "; ".join(values) if values else "—"


def _callouts(step: InstructionStep) -> str:
    values = [
        f"{callout.mode.value}: {', '.join(callout.references) or '—'}"
        for callout in step.callouts
    ]
    return "; ".join(values) if values else "—"


def _value(value: object) -> str:
    if isinstance(value, tuple):
        return f"({', '.join(str(item) for item in value)})"
    return str(value)


def _yes_no(*, value: bool) -> str:
    return "yes" if value else "no"
