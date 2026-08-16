"""Tests for the command-line entry point."""

from __future__ import annotations

import zipfile
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

import pyldraw3_tui.main as main_module
from pyldraw3_tui.main import main

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from ldraw.config import Config

    from pyldraw3_tui.data.source import CatalogSource


def test_malformed_config_exits_with_message(tmp_path: Path, capsys):
    bad_config = tmp_path / "config.yml"
    bad_config.write_text("- not\n- a\n- mapping\n")
    with pytest.raises(SystemExit) as excinfo:
        main(["--config", str(bad_config)])
    assert excinfo.value.code == 1
    stderr = capsys.readouterr().err
    assert "config.yml" in stderr
    assert "mapping" in stderr


def _stub_main(
    monkeypatch: pytest.MonkeyPatch,
    fixture_config: Config,
) -> dict[str, object]:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        main_module.Config,
        "load",
        staticmethod(lambda _path=None: fixture_config),
    )

    def app_factory(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(run=lambda: captured.setdefault("ran", True))

    monkeypatch.setattr(main_module, "PyldrawTuiApp", app_factory)
    return captured


def test_connection_source_flags_preserve_order(
    fixture_config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _stub_main(monkeypatch, fixture_config)
    shadow_a = tmp_path / "shadow-a"
    shadow_b = tmp_path / "shadow-b.csl"
    shadow_a.mkdir()
    with zipfile.ZipFile(shadow_b, "w") as archive:
        archive.writestr("parts/3001.dat", "0 !LDCAD SNAP_CLEAR\n")
    studio_a = tmp_path / "studio-a.json"
    studio_b = tmp_path / "studio-b.json"
    studio_a.write_text('{"parts": []}')
    studio_b.write_text('{"parts": [{"part_id": "3001"}]}')

    main(
        [
            "--ldcad-shadow",
            str(shadow_a),
            "--studio-metadata",
            str(studio_a),
            "--ldcad-shadow",
            str(shadow_b),
            "--studio-metadata",
            str(studio_b),
        ]
    )

    source = cast("CatalogSource", captured["source"])
    assert source.connection_shadows == (shadow_a, shadow_b)
    assert source.studio_metadata == (studio_a, studio_b)
    assert captured["ran"] is True


@pytest.mark.parametrize(
    "case",
    [
        ("--ldcad-shadow", "missing.csl", None, "path does not exist"),
        ("--ldcad-shadow", "bad.csl", "not a zip", "File is not a zip file"),
        ("--studio-metadata", "missing.json", None, "path does not exist"),
    ],
)
def test_invalid_connection_source_exits_before_app(
    fixture_config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: tuple[str, str, str | None, str],
) -> None:
    option, filename, contents, message = case
    captured = _stub_main(monkeypatch, fixture_config)
    source = tmp_path / filename
    if contents is not None:
        source.write_text(contents)

    with pytest.raises(SystemExit) as excinfo:
        main([option, str(source)])

    assert excinfo.value.code == 1
    assert message in capsys.readouterr().err
    assert "ran" not in captured


def test_unreadable_shadow_directory_exits_before_app(
    fixture_config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured = _stub_main(monkeypatch, fixture_config)
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    path_type = type(shadow)
    original_iterdir = path_type.iterdir

    def deny_listing(path: Path) -> Iterator[Path]:
        if path == shadow:
            message = "permission denied"
            raise PermissionError(message)
        return original_iterdir(path)

    monkeypatch.setattr(path_type, "iterdir", deny_listing)

    with pytest.raises(SystemExit) as excinfo:
        main(["--ldcad-shadow", str(shadow)])

    assert excinfo.value.code == 1
    assert "permission denied" in capsys.readouterr().err
    assert "ran" not in captured


def test_shadow_directory_validation_reads_only_one_entry(
    fixture_config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _stub_main(monkeypatch, fixture_config)
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    first = shadow / "parts"
    path_type = type(shadow)

    def one_then_fail(_path: Path) -> Iterator[Path]:
        yield first
        message = "validation enumerated more than one entry"
        raise AssertionError(message)

    monkeypatch.setattr(path_type, "iterdir", one_then_fail)

    main(["--ldcad-shadow", str(shadow)])

    assert captured["ran"] is True


def test_studio_source_must_be_a_file(
    fixture_config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured = _stub_main(monkeypatch, fixture_config)
    studio = tmp_path / "studio"
    studio.mkdir()

    with pytest.raises(SystemExit):
        main(["--studio-metadata", str(studio)])

    assert "expected a JSON file" in capsys.readouterr().err
    assert "ran" not in captured


@pytest.mark.parametrize("contents", ["not json", "{}"])
def test_studio_document_parsing_is_deferred_to_pyldraw(
    fixture_config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    contents: str,
) -> None:
    captured = _stub_main(monkeypatch, fixture_config)
    studio = tmp_path / "studio.json"
    studio.write_text(contents)

    main(["--studio-metadata", str(studio)])

    source = cast("CatalogSource", captured["source"])
    assert source.studio_metadata == (studio,)
    assert captured["ran"] is True


def test_unsupported_studio_row_is_not_a_startup_error(
    fixture_config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _stub_main(monkeypatch, fixture_config)
    studio = tmp_path / "studio.json"
    studio.write_text(
        '{"parts": [{"part_id": "3001", "connections": '
        '[{"type": "future-connector"}]}]}'
    )

    main(["--studio-metadata", str(studio)])

    assert captured["ran"] is True
