"""Command-line entry point: ``pyldraw3-tui [FILE]``."""

from __future__ import annotations

import json
import sys
import zipfile
from argparse import ArgumentParser
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING

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
        path = source.expanduser()
        if not path.exists():
            raise _ConnectionSourceError(
                kind="LDCad shadow",
                path=path,
                reason="path does not exist",
            )
        if path.is_dir():
            try:
                for _entry in path.iterdir():
                    pass
            except OSError as error:
                reason = str(error) or type(error).__name__
                raise _ConnectionSourceError(
                    kind="LDCad shadow",
                    path=path,
                    reason=reason,
                ) from error
            validated.append(path)
            continue
        if not path.is_file():
            raise _ConnectionSourceError(
                kind="LDCad shadow",
                path=path,
                reason="expected a directory or ZIP/CSL archive",
            )
        try:
            with zipfile.ZipFile(path) as archive:
                archive.infolist()
        except (OSError, zipfile.BadZipFile) as error:
            reason = str(error) or type(error).__name__
            raise _ConnectionSourceError(
                kind="LDCad shadow",
                path=path,
                reason=reason,
            ) from error
        validated.append(path)
    return tuple(validated)


def _validated_studio_sources(sources: Iterable[Path]) -> tuple[Path, ...]:
    """Return normalized Studio JSON sources with a valid document envelope."""
    validated: list[Path] = []
    for source in sources:
        path = source.expanduser()
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, RecursionError, UnicodeError, ValueError) as error:
            reason = str(error) or type(error).__name__
            raise _ConnectionSourceError(
                kind="Studio metadata",
                path=path,
                reason=reason,
            ) from error
        if not isinstance(document, dict) or not isinstance(
            document.get("parts"), list
        ):
            raise _ConnectionSourceError(
                kind="Studio metadata",
                path=path,
                reason="expected a JSON object containing a parts list",
            )
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
