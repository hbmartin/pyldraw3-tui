# pyldraw3-tui

[![CI](https://github.com/hbmartin/pyldraw3-tui/actions/workflows/lint-test.yml/badge.svg)](https://github.com/hbmartin/pyldraw3-tui/actions/workflows/lint-test.yml)
[![PyPI](https://img.shields.io/pypi/v/pyldraw3-tui.svg)](https://pypi.org/project/pyldraw3-tui/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE.txt)

A terminal user interface for **browsing the LDraw parts catalog** and **inspecting LDraw model
files** — built on [Textual](https://textual.textualize.io/) and
[pyldraw3](https://github.com/hbmartin/pyldraw3).

[LDraw](https://ldraw.org) is the open standard for describing LEGO® models as plain-text
`.ldr`/`.mpd` files. `pyldraw3-tui` is the read-only companion to the `pyldraw3` library: it never
creates, edits, or exports model or geometry files — it just lets you explore parts and models
fast, without leaving your terminal.

## Contents

- [Installation](#installation)
- [Usage](#usage)
- [Features](#features)
- [First run](#first-run)
- [Key bindings](#key-bindings)
- [Contributing](#contributing)
- [License](#license)

## Installation

Requires **Python 3.12+** and a terminal.

Run it without installing anything (recommended):

```sh
uvx pyldraw3-tui
```

Or install it as a persistent command-line tool:

```sh
uv tool install pyldraw3-tui   # via uv
pipx install pyldraw3-tui      # or via pipx
```

Want the latest unreleased build? Install straight from source:

```sh
uvx --from git+https://github.com/hbmartin/pyldraw3-tui pyldraw3-tui
uv tool install git+https://github.com/hbmartin/pyldraw3-tui
```

## Usage

```sh
pyldraw3-tui [FILE]
```

With no argument it opens on the **Catalog**; given a `.ldr`/`.mpd` path it opens on the **Model**
view for that file. Switch modes in-app via the two top tabs: **Catalog** and **Model**.

## Features

1. **Look up part codes** — find a part's code/description fast to paste into scripts or `.ldr` files.
2. **Explore the catalog** — browse categories and minifig sections to discover parts.
3. **Inspect a part** — metadata, palette swatches, and a drillable sub-part reference tree.
4. **Browse a model file** — open a `.ldr`/`.mpd` and read its pieces, summary stats, and bill of materials.

## First run

On launch the app reads your [pyldraw3](https://github.com/hbmartin/pyldraw3) configuration. If no
LDraw library is found on disk, a guided setup screen offers to download the library (~80 MB),
point your configuration at it, and generate the parts index. If the index is missing or stale it
is rebuilt automatically with a progress indicator — the first build takes a few seconds; later
launches are instant.

Everything lives under your platform's standard directories (resolved by
[platformdirs](https://pypi.org/project/platformdirs/)):

| What                          | macOS                                                | Linux                              |
| ----------------------------- | ---------------------------------------------------- | ---------------------------------- |
| Config file (`config.yml`)    | `~/Library/Application Support/pyldraw3/`            | `~/.config/pyldraw3/`              |
| LDraw library (download)      | `~/Library/Caches/pyldraw3/`                         | `~/.cache/pyldraw3/`               |
| Generated parts index         | `~/Library/Application Support/pyldraw3/generated/`  | `~/.local/share/pyldraw3/generated/` |

The exact library and index paths are recorded in `config.yml`; the values above are the defaults.
Windows uses the equivalent `%LOCALAPPDATA%` locations.

## Key bindings

**Navigation**

| Key                 | Action                              |
| ------------------- | ----------------------------------- |
| `↑`/`↓`, `k`/`j`    | Move within the focused list/tree   |
| `h`/`l`             | Collapse/expand tree nodes          |
| `Tab` / `Shift+Tab` | Cycle focusable panes               |
| `Enter`             | Open/drill selection                |
| `/`                 | Focus the live filter box           |

**Actions**

| Key       | Action                                                    |
| --------- | -------------------------------------------------------- |
| `y` / `Y` | Yank code / chooser (description, import path)           |
| `o`       | Open selected part on ldraw.org                          |
| `e`       | Export Python snippet (import / `Piece(...)` / bare code) |

**Global**

| Key            | Action                                                  |
| -------------- | ------------------------------------------------------ |
| `1` / `2`      | Switch to Catalog / Model tab                          |
| `:`            | Command palette (jump to part, open model, copy BOM, …) |
| `Ctrl+T`       | Toggle light/dark theme                                |
| `?`            | Help (full key reference)                              |
| `q` / `Ctrl+C` | Quit                                                   |

Full mouse support comes for free with Textual.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, the check
suite, and the snapshot-testing workflow. Please also review our
[Code of Conduct](.github/CODE_OF_CONDUCT.md).

## License

Distributed under the **GPL-3.0-or-later** license. See [LICENSE.txt](LICENSE.txt) for details.

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize, or endorse this project.
LDraw™ is a trademark of the Estate of James Jessiman.
