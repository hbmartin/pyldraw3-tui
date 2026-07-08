# Contributing

Thanks for your interest in improving `pyldraw3-tui`! By participating in this project you agree to
abide by our [Code of Conduct](.github/CODE_OF_CONDUCT.md).

## Development setup

This project uses [`uv`](https://docs.astral.sh/uv/) for dependency management and packaging, and
targets **Python 3.12+**.

```sh
git clone https://github.com/hbmartin/pyldraw3-tui
cd pyldraw3-tui
uv sync --all-groups
```

## Checks

Please run the full suite before opening a pull request:

```sh
uv run pytest                    # tests
uv run ruff check .              # lint
uv run ruff format --check .     # formatting
uv run ty check src tests        # type check (ty)
uv run pyrefly check src tests   # type check (pyrefly)
```

## Snapshot tests

Snapshot tests compare SVG screenshots of the TUI under `tests/__snapshots__/`. After an
intentional visual change, regenerate them and review the diff before committing:

```sh
SNAPSHOT_UPDATE=1 uv run pytest tests/test_snapshots.py
```
