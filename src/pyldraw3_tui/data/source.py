"""Resolve configuration, classify data freshness, and load catalog/models.

This is the only module that touches ``pyldraw3`` configuration and the
persistent catalog index. The app asks :meth:`CatalogSource.classify`
once at startup to decide between the setup screen, a build-progress
overlay, or an instant load.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Self

from ldraw.catalog import (
    CATALOG_SCHEMA_VERSION,
    catalog_db_path,
    load_parts,
    parts_lst_md5,
)
from ldraw.config import Config
from ldraw.errors import PartError
from ldraw.model import read_model

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

    @classmethod
    def from_default_config(cls) -> Self:
        """Build a source from the user's pyldraw3 configuration."""
        return cls(config=Config.load())

    @property
    def parts_lst_path(self) -> Path:
        """Path to the library's ``parts.lst``."""
        return Path(self.config.ldraw_library_path) / "ldraw" / "parts.lst"

    @property
    def catalog_db(self) -> Path:
        """Path to the persistent catalog index."""
        return catalog_db_path(self.config.generated_path)

    def classify(self) -> SourceState:
        """Classify the data so the app can pick a startup path.

        ``INDEX_MISSING`` and ``INDEX_STALE`` both still load fine — the
        index is rebuilt on the fly — but the first load runs the slow
        categorization pass, so the app shows progress instead of hanging.
        """
        if not self.parts_lst_path.is_file():
            return SourceState.LIBRARY_MISSING
        if not self.catalog_db.is_file():
            return SourceState.INDEX_MISSING
        if not self._index_fresh():
            return SourceState.INDEX_STALE
        return SourceState.READY

    def _index_fresh(self) -> bool:
        """Mirror the freshness rule ``ldraw.catalog.load_parts`` applies."""
        try:
            connection = sqlite3.connect(f"file:{self.catalog_db}?mode=ro", uri=True)
        except sqlite3.Error:
            return False
        try:
            (version,) = connection.execute("PRAGMA user_version").fetchone()
            if version != CATALOG_SCHEMA_VERSION:
                return False
            row = connection.execute(
                "SELECT value FROM meta WHERE key = 'parts_lst_md5'",
            ).fetchone()
        except sqlite3.Error:
            return False
        finally:
            connection.close()
        return row is not None and row[0] == parts_lst_md5(self.parts_lst_path)

    def load(self) -> Parts:
        """Load the catalog, building and persisting the index as needed.

        Blocking (file I/O over the whole library on a cold index) — run
        it in a worker thread.
        """
        Path(self.config.generated_path).mkdir(parents=True, exist_ok=True)
        return load_parts(
            self.parts_lst_path,
            self.config.generated_path,
            build_index=True,
        )

    def open_model(self, path: Path | str) -> Model:
        """Read a ``.ldr``/``.mpd`` file, wrapping failures for the UI."""
        model_path = Path(path)
        try:
            return read_model(model_path)
        except OSError as error:
            reason = error.strerror or str(error)
            raise ModelLoadError(path=model_path, reason=reason) from error
        except UnicodeDecodeError as error:
            raise ModelLoadError(path=model_path, reason=str(error)) from error
        except PartError as error:
            raise ModelLoadError(path=model_path, reason=str(error)) from error
