"""UI-facing error types for pyldraw3-tui."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class PyldrawTuiError(Exception):
    """Base class for errors surfaced in the TUI."""


class ModelLoadError(PyldrawTuiError):
    """A model file could not be read or parsed."""

    def __init__(
        self,
        path: Path,
        reason: str,
        line_number: int | None = None,
    ) -> None:
        self.path = path
        self.reason = reason
        self.line_number = line_number
        location = str(path) if line_number is None else f"{path}:{line_number}"
        super().__init__(f"could not load model {location}: {reason}")


class LibraryMissingError(PyldrawTuiError):
    """The configured LDraw library has no parts.lst."""

    def __init__(self, parts_lst: Path) -> None:
        self.parts_lst = parts_lst
        super().__init__(f"no LDraw library found at {parts_lst}")
