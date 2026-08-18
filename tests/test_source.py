"""Tests for CatalogSource freshness classification and loading."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from ldraw import Diagnostic, DiagnosticCode, Severity
from ldraw.config import Config
from ldraw.session import LDrawSession

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
    parts = source.load().parts
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
    first = source.load().parts
    mtime = source.catalog_db.stat().st_mtime_ns
    second = source.load().parts
    assert source.catalog_db.stat().st_mtime_ns == mtime
    assert sorted(second.catalog.by_code) == sorted(first.catalog.by_code)


def test_load_retains_catalog_preparation_diagnostics(
    source: CatalogSource,
    parts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning = Diagnostic(
        message="catalog index could not be persisted",
        severity=Severity.WARNING,
        code=DiagnosticCode.CATALOG_PERSIST_FAILED,
    )
    result = SimpleNamespace(parts=parts, diagnostics=(warning,))
    monkeypatch.setattr(
        LDrawSession,
        "prepare_catalog",
        lambda _session, **_kwargs: result,
    )

    loaded = source.load()

    assert loaded.parts is parts
    assert loaded.diagnostics == (warning,)


def test_load_uses_error_diagnostic_and_preserves_parts_path(
    source: CatalogSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning = Diagnostic(
        message="catalog index could not be persisted",
        severity=Severity.WARNING,
        code=DiagnosticCode.CATALOG_PERSIST_FAILED,
    )
    error = Diagnostic(message="catalog unavailable", severity=Severity.ERROR)
    result = SimpleNamespace(parts=None, diagnostics=(warning, error))
    monkeypatch.setattr(
        LDrawSession,
        "prepare_catalog",
        lambda _session, **_kwargs: result,
    )

    with pytest.raises(FileNotFoundError) as excinfo:
        source.load()

    reason = str(excinfo.value)
    assert "catalog unavailable" in reason
    assert warning.message not in reason
    assert str(source.parts_lst_path) in reason


def test_load_without_error_diagnostic_reports_parts_path(
    source: CatalogSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning = Diagnostic(
        message="catalog index could not be persisted",
        severity=Severity.WARNING,
        code=DiagnosticCode.CATALOG_PERSIST_FAILED,
    )
    result = SimpleNamespace(parts=None, diagnostics=(warning,))
    monkeypatch.setattr(
        LDrawSession,
        "prepare_catalog",
        lambda _session, **_kwargs: result,
    )

    with pytest.raises(FileNotFoundError) as excinfo:
        source.load()

    reason = str(excinfo.value)
    assert reason == str(source.parts_lst_path)
    assert warning.message not in reason


def test_default_config_factory_preserves_connection_sources(
    fixture_config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.yml"
    shadow = tmp_path / "shadow"
    studio = tmp_path / "studio.json"
    monkeypatch.setattr(
        Config,
        "load",
        staticmethod(lambda _config_file=None: fixture_config),
    )

    source = CatalogSource.from_default_config(
        config_file=config_file,
        connection_shadows=(shadow,),
        studio_metadata=(studio,),
    )

    assert source.config is fixture_config
    assert source.config_file == config_file
    assert source.connection_shadows == (shadow,)
    assert source.studio_metadata == (studio,)


def test_load_registers_connection_metadata_sources(
    fixture_config: Config,
    tmp_path: Path,
):
    shadow = tmp_path / "shadow"
    shadow_part = shadow / "parts" / "3901.dat"
    shadow_part.parent.mkdir(parents=True)
    shadow_part.write_text("0 !LDCAD SNAP_CLEAR\n")
    studio = tmp_path / "studio.json"
    studio.write_text(
        """{
          "parts": [{
            "part_id": "3901",
            "connections": [{
              "id": "studio-bar",
              "type": "bar",
              "position": [0, 0, 0],
              "axis": [0, 1, 0],
              "gender": "male",
              "radius": 3.2,
              "length": 10
            }]
          }]
        }"""
    )

    parts = (
        CatalogSource(
            config=fixture_config,
            connection_shadows=(shadow,),
            studio_metadata=(studio,),
        )
        .load()
        .parts
    )
    report = parts.connection_metadata("3901")

    assert report.coverage.value == "complete"
    assert report.source_count == 2
    assert [
        (feature.feature_id, feature.source.value) for feature in report.features
    ] == [("studio-bar", "studio")]


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
