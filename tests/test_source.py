"""Tests for CatalogSource freshness classification and loading."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from ldraw.config import Config

from pyldraw3_tui.data.source import CatalogSource, SourceState
from pyldraw3_tui.errors import ModelLoadError

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def source(fixture_config: Config) -> CatalogSource:
    return CatalogSource(config=fixture_config)


def test_library_missing(tmp_path: Path):
    config = Config(
        ldraw_library_path=str(tmp_path / "nowhere"),
        generated_path=str(tmp_path / "generated"),
    )
    assert CatalogSource(config=config).classify() is SourceState.LIBRARY_MISSING


def test_index_missing_then_ready(source: CatalogSource):
    assert source.classify() is SourceState.INDEX_MISSING
    parts = source.load()
    assert len(parts.catalog.by_code) == 5
    assert source.catalog_db.is_file()
    assert source.classify() is SourceState.READY


def test_index_stale_on_garbage_db(source: CatalogSource):
    source.catalog_db.parent.mkdir(parents=True, exist_ok=True)
    source.catalog_db.write_bytes(b"not a sqlite database")
    assert source.classify() is SourceState.INDEX_STALE


def test_index_stale_on_md5_mismatch(source: CatalogSource, tmp_path: Path):
    source.load()
    assert source.classify() is SourceState.READY
    # Point the same generated index at a different library.
    other_library = tmp_path / "other-library" / "ldraw"
    other_library.mkdir(parents=True)
    (other_library / "parts.lst").write_text("9999.dat Different Part\n")
    stale = CatalogSource(
        config=Config(
            ldraw_library_path=str(other_library.parent),
            generated_path=source.config.generated_path,
        ),
    )
    assert stale.classify() is SourceState.INDEX_STALE


def test_load_reuses_fresh_index(source: CatalogSource):
    first = source.load()
    mtime = source.catalog_db.stat().st_mtime_ns
    second = source.load()
    assert source.catalog_db.stat().st_mtime_ns == mtime
    assert sorted(second.catalog.by_code) == sorted(first.catalog.by_code)


def test_open_model(source: CatalogSource, car_ldr: Path):
    model = source.open_model(car_ldr)
    assert [piece.part for piece in model.iter_pieces()] == ["3001", "3022", "6157"]


def test_open_model_missing_file(source: CatalogSource, tmp_path: Path):
    with pytest.raises(ModelLoadError) as excinfo:
        source.open_model(tmp_path / "missing.ldr")
    assert "missing.ldr" in str(excinfo.value)


def test_open_model_parse_error(source: CatalogSource, broken_ldr: Path):
    with pytest.raises(ModelLoadError) as excinfo:
        source.open_model(broken_ldr)
    error = excinfo.value
    assert error.line_number == 2
    assert "broken.ldr:2" in str(error)
    # The location comes from the structured attributes, not the message.
    assert "at line 2" not in str(error)
