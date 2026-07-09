"""Resolve configuration, classify data freshness, and load catalog/models.

This is the only module that touches ``pyldraw3`` configuration and the
persistent catalog index. The app asks :meth:`CatalogSource.classify`
once at startup to decide between the setup screen, a build-progress
overlay, or an instant load.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Self

from ldraw import LDrawSession
from ldraw.config import Config
from ldraw.errors import PartError
from ldraw.session import LDrawStateReason

from pyldraw3_tui.errors import ModelLoadError

if TYPE_CHECKING:
    from ldraw.model import Model
    from ldraw.parts import Parts


class SourceState(Enum):
    """Startup classification of the configured LDraw data."""

    READY = "ready"
    LIBRARY_MISSING = "library-missing"
    INDEX_MISSING = "index-missing"
    INDEX_STALE = "index-stale"


@dataclass(slots=True)
class CatalogSource:
    """Load the parts catalog and model files for one configuration."""

    config: Config
    config_file: Path | None = field(default=None, kw_only=True)

    @classmethod
    def from_default_config(cls, config_file: Path | None = None) -> Self:
        """Build a source from the user's pyldraw3 configuration."""
        return cls(config=Config.load(config_file), config_file=config_file)

    @property
    def session(self) -> LDrawSession:
        """Session handle for the configured LDraw library."""
        return LDrawSession(self.config)

    @property
    def parts_lst_path(self) -> Path:
        """Path to the library's ``parts.lst``."""
        return self.session.paths.parts_lst

    @property
    def catalog_db(self) -> Path:
        """Path to the persistent catalog index."""
        return self.session.paths.catalog_db

    def classify(self) -> SourceState:
        """Classify the data so the app can pick a startup path.

        ``INDEX_MISSING`` and ``INDEX_STALE`` both still load fine — the
        index is rebuilt on the fly — but the first load runs the slow
        categorization pass, so the app shows progress instead of hanging.
        """
        state = self.session.state()
        if not state.library_available:
            return SourceState.LIBRARY_MISSING
        if LDrawStateReason.INDEX_MISSING in state.reasons:
            return SourceState.INDEX_MISSING
        if {
            LDrawStateReason.INDEX_STALE,
            LDrawStateReason.INDEX_UNREADABLE,
        } & set(state.reasons):
            return SourceState.INDEX_STALE
        return SourceState.READY

    def load(self) -> Parts:
        """Load the catalog, building and persisting the index as needed.

        Blocking (file I/O over the whole library on a cold index) — run
        it in a worker thread.
        """
        return self.session.load()

    def open_model(self, path: Path | str) -> Model:
        """Read a ``.ldr``/``.mpd`` file, wrapping failures for the UI."""
        model_path = Path(path)
        try:
            return self.session.open_model(model_path)
        except OSError as error:
            reason = error.strerror or str(error)
            raise ModelLoadError(path=model_path, reason=reason) from error
        except (UnicodeDecodeError, PartError) as error:
            raise ModelLoadError(path=model_path, reason=str(error)) from error
