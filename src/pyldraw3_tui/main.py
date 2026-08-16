"""Command-line entry point: ``pyldraw3-tui [FILE]``."""

from __future__ import annotations

import sys
import zipfile
from argparse import ArgumentParser
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Never

from ldraw.config import Config
from ldraw.errors import ConfigLoadError

from pyldraw3_tui.app import PyldrawTuiApp
from pyldraw3_tui.data.source import CatalogSource

if TYPE_CHECKING:
    from collections.abc import Iterable


class _ConnectionSourceError(ValueError):
    """Invalid startup connection metadata source."""

    def __init__(self, kind: str, path: Path, reason: str) -> None:
        message = f"{kind} {path}: {reason}"
        super().__init__(message)


def _normalized_source(source: Path, *, kind: str) -> Path:
    """Expand a connection source path and require it to exist."""
    path = source.expanduser()
    if not path.exists():
        raise _ConnectionSourceError(kind, path, "path does not exist")
    return path


def _require_file(path: Path, *, kind: str, expected: str) -> None:
    """Require an existing connection source to be a regular file."""
    if not path.is_file():
        raise _ConnectionSourceError(kind, path, expected)


def _raise_source_error(kind: str, path: Path, error: BaseException) -> Never:
    """Raise an I/O or archive error with connection-source context."""
    reason = str(error) or type(error).__name__
    raise _ConnectionSourceError(kind, path, reason) from error


def _package_version() -> str:
    try:
        return version("pyldraw3-tui")
    except PackageNotFoundError:
        return "unknown"


def build_parser() -> ArgumentParser:
    """Build the argument parser for the console script."""
    parser = ArgumentParser(
        prog="pyldraw3-tui",
        description=(
            "Browse the LDraw and Rebrickable catalogs and inspect LDraw "
            "model files. With no FILE the app opens on the Catalog tab; "
            "with a .ldr/.mpd FILE it opens on the Model tab."
        ),
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        metavar="FILE",
        help="optional .ldr/.mpd model file to open",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="alternate pyldraw3 config.yml",
    )
    parser.add_argument(
        "--ldcad-shadow",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help="LDCad shadow directory or ZIP/CSL archive (repeatable)",
    )
    parser.add_argument(
        "--studio-metadata",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help="Studio connectivity JSON export (repeatable)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_package_version()}",
    )
    return parser


def _validated_shadow_sources(sources: Iterable[Path]) -> tuple[Path, ...]:
    """Return normalized, readable LDCad shadow sources in registration order."""
    validated: list[Path] = []
    for source in sources:
        path = _normalized_source(source, kind="LDCad shadow")
        if path.is_dir():
            try:
                next(path.iterdir(), None)
            except OSError as error:
                _raise_source_error("LDCad shadow", path, error)
            validated.append(path)
            continue
        _require_file(
            path,
            kind="LDCad shadow",
            expected="expected a directory or ZIP/CSL archive",
        )
        try:
            with zipfile.ZipFile(path) as archive:
                archive.infolist()
        except (OSError, zipfile.BadZipFile) as error:
            _raise_source_error("LDCad shadow", path, error)
        validated.append(path)
    return tuple(validated)


def _validated_studio_sources(sources: Iterable[Path]) -> tuple[Path, ...]:
    """Return normalized, readable Studio JSON files for pyldraw3 to parse."""
    validated: list[Path] = []
    for source in sources:
        path = _normalized_source(source, kind="Studio metadata")
        _require_file(
            path,
            kind="Studio metadata",
            expected="expected a JSON file",
        )
        try:
            with path.open("rb") as source_file:
                source_file.read(1)
        except OSError as error:
            _raise_source_error("Studio metadata", path, error)
        validated.append(path)
    return tuple(validated)


def main(argv: list[str] | None = None) -> None:
    """Run the pyldraw3-tui application."""
    args = build_parser().parse_args(argv)
    try:
        config = Config.load(args.config) if args.config is not None else Config.load()
        connection_shadows = _validated_shadow_sources(args.ldcad_shadow)
        studio_metadata = _validated_studio_sources(args.studio_metadata)
    except (ConfigLoadError, _ConnectionSourceError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    app = PyldrawTuiApp(
        source=CatalogSource(
            config=config,
            config_file=args.config,
            connection_shadows=connection_shadows,
            studio_metadata=studio_metadata,
        ),
        model_path=args.file,
    )
    app.run()
