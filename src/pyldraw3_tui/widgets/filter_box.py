"""Live filter input for the parts list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on
from textual.widgets import Input

from pyldraw3_tui.messages import FilterChanged

if TYPE_CHECKING:
    from textual.timer import Timer

DEBOUNCE_SECONDS = 0.1


class FilterBox(Input):
    """Posts :class:`FilterChanged` after keystrokes settle briefly."""

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__(placeholder="filter parts…", id=id)
        self._debounce_timer: Timer | None = None

    @on(Input.Changed)
    def _schedule(self, event: Input.Changed) -> None:
        event.stop()
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        self._debounce_timer = self.set_timer(DEBOUNCE_SECONDS, self._fire)

    def _fire(self) -> None:
        self._debounce_timer = None
        self.post_message(FilterChanged(self.value))

    def on_unmount(self) -> None:
        """Stop pending debounce work when the input leaves the DOM."""
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer = None
