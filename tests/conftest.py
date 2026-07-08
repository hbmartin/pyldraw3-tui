"""Shared fixtures: a tiny LDraw library and sample models."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from ldraw.catalog import load_parts
from ldraw.config import Config

from pyldraw3_tui.app import PyldrawTuiApp
from pyldraw3_tui.data.source import CatalogSource

if TYPE_CHECKING:
    from collections.abc import Callable

    from ldraw.parts import Parts

FIXTURES = Path(__file__).parent / "fixtures"
LIBRARY = FIXTURES / "library"
MODELS = FIXTURES / "models"


@pytest.fixture
def fixture_config(tmp_path: Path) -> Config:
    """Return a config pointing at the fixture library and a tmp index."""
    return Config(
        ldraw_library_path=str(LIBRARY),
        generated_path=str(tmp_path / "generated"),
    )


@pytest.fixture
def parts(fixture_config: Config) -> Parts:
    """Return a fully categorized Parts over the fixture library."""
    parts_lst = Path(fixture_config.ldraw_library_path) / "ldraw" / "parts.lst"
    generated = Path(fixture_config.generated_path)
    generated.mkdir(parents=True, exist_ok=True)
    return load_parts(parts_lst, generated, build_index=True)


@pytest.fixture
def make_app(fixture_config: Config) -> Callable[..., PyldrawTuiApp]:
    """Return a factory building the app against the fixture library."""

    def factory(model_path: Path | None = None) -> PyldrawTuiApp:
        app = PyldrawTuiApp(
            source=CatalogSource(config=fixture_config),
            model_path=model_path,
        )
        # Deterministic frames for snapshots (no sliding tab underline).
        app.animation_level = "none"
        return app

    return factory


@pytest.fixture
def car_ldr() -> Path:
    """Path to the single-model fixture."""
    return MODELS / "car.ldr"


@pytest.fixture
def spaceship_mpd() -> Path:
    """Path to the multi-model MPD fixture."""
    return MODELS / "spaceship.mpd"


@pytest.fixture
def broken_ldr() -> Path:
    """Path to a fixture model with an invalid line."""
    return MODELS / "broken.ldr"
