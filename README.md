# pyldraw3-tui

`pyldraw3-tui` is a terminal user interface, built on [Textual](https://textual.textualize.io/)
and [pyldraw3](https://github.com/hbmartin/pyldraw3), for **browsing the LDraw parts catalog** and
**inspecting LDraw model files**. It is strictly read-only: it never creates, edits, or exports
model or geometry files.

A single command launches it:

```sh
pyldraw3-tui [FILE]
```

With no argument it opens on the **Catalog**; given a `.ldr`/`.mpd` path it opens on the **Model**
view for that file. Mode switching happens in-app via two top tabs: **Catalog** and **Model**.

### Features

1. **Look up part codes** — find a part's code/description fast to paste into scripts or `.ldr` files.
2. **Explore the catalog** — browse categories and minifig sections to discover parts.
3. **Inspect a part** — metadata, palette swatches, and a drillable sub-part reference tree.
4. **Browse a model file** — open a `.ldr`/`.mpd` and read its pieces, summary stats, and bill of materials.

## First run

The app reads your [pyldraw3](https://github.com/hbmartin/pyldraw3) configuration. If no LDraw
library is on disk yet, a guided setup screen offers to download the library and generate the
parts index. If the index is missing or stale, it is rebuilt automatically with a progress
indicator (the first build takes a few seconds; later launches are instant).

## Key bindings

| Key                 | Action                                                       |
| ------------------- | ------------------------------------------------------------ |
| `↑`/`↓`, `k`/`j`    | Move within the focused list/tree                            |
| `h`/`l`             | Collapse/expand tree nodes                                   |
| `Tab` / `Shift+Tab` | Cycle focusable panes                                        |
| `Enter`             | Open/drill selection                                         |
| `/`                 | Focus the live filter box                                    |
| `:`                 | Command palette (jump to part, open model, copy BOM, …)      |
| `y` / `Y`           | Yank code / chooser (description, import path)               |
| `o`                 | Open selected part on ldraw.org                              |
| `e`                 | Export Python snippet (import / `Piece(...)` / bare code)    |
| `1` / `2`           | Switch to Catalog / Model tab                                |
| `?`                 | Help (full key reference)                                    |
| `q` / `Ctrl+C`      | Quit                                                         |

Full mouse support comes for free with Textual.

## Development

This project uses `uv` for dependency management.

```sh
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ty check src tests
uv run pyrefly check src tests
```

Snapshot tests compare SVG screenshots under `tests/__snapshots__/`. After an intentional
visual change, regenerate them with:

```sh
SNAPSHOT_UPDATE=1 uv run pytest tests/test_snapshots.py
```
