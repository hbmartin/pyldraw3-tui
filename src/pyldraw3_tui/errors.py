"""UI-facing error types for pyldraw3-tui."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class PyldrawTuiError(Exception):
    """Base class for errors surfaced in the TUI."""


class ModelLoadError(PyldrawTuiError):
    """A model file could not be read or parsed."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"could not load model {path}: {reason}")


class LibraryMissingError(PyldrawTuiError):
    """The configured LDraw library has no parts.lst."""

    def __init__(self, parts_lst: Path) -> None:
        self.parts_lst = parts_lst
        super().__init__(f"no LDraw library found at {parts_lst}")
