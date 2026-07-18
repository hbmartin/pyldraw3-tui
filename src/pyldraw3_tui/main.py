"""Command-line entry point: ``pyldraw3-tui [FILE]``."""

from __future__ import annotations

import sys
from argparse import ArgumentParser
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from ldraw.config import Config
from ldraw.errors import ConfigLoadError

from pyldraw3_tui.app import PyldrawTuiApp
from pyldraw3_tui.data.source import CatalogSource


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
            "Browse the LDraw parts catalog and inspect LDraw model files. "
            "With no FILE the app opens on the Catalog tab; with a "
            ".ldr/.mpd FILE it opens on the Model tab."
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
        "--version",
        action="version",
        version=f"%(prog)s {_package_version()}",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the pyldraw3-tui application."""
    args = build_parser().parse_args(argv)
    try:
        config = Config.load(args.config) if args.config is not None else Config.load()
    except ConfigLoadError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    app = PyldrawTuiApp(
        source=CatalogSource(config=config, config_file=args.config),
        model_path=args.file,
    )
    app.run()
