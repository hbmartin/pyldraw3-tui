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

**What you get:**

- 🔎 Look up a part code or description in seconds — no browser, no 3D viewer.
- 📖 Read any `.ldr`/`.mpd` model's pieces, bounding box, and bill of materials as plain text.
- 🎨 Preview the full LDraw colour palette with swatches and finish metadata.
- 📋 Yank codes or export ready-to-paste Python snippets straight into your scripts.
- ⌨️ Fully keyboard-driven (with mouse support), running entirely in your terminal.

> **Status:** Beta (v0.1.0). Usable day-to-day; interfaces and key bindings may still change
> between releases. Bug reports and feedback are very welcome.

## Contents

- [Installation](#installation)
- [Usage](#usage)
- [Features](#features)
- [First run](#first-run)
- [Key bindings](#key-bindings)
- [Troubleshooting](#troubleshooting)
- [pyldraw3-tui vs. pyldraw3](#pyldraw3-tui-vs-pyldraw3)
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

Or grab it with the standalone [uvx.sh](https://uvx.sh) installer script (no Python toolchain
required up front — it bootstraps `uv` for you):

```sh
curl -LsSf uvx.sh/pyldraw3-tui/install.sh | sh
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

The app is organised around its two top tabs.

**Catalog** — browse and look up parts:

- **Look up part codes** — find a part's code/description fast to paste into scripts or `.ldr` files.
- **Explore the catalog** — browse categories and minifig sections to discover parts.
- **Inspect a part** — metadata, palette swatches, and a drillable sub-part reference tree.

**Model** — read a model file:

- **Browse a model file** — open a `.ldr`/`.mpd` and read its pieces, summary stats, and bill of materials.
- **See real geometry** — per-piece bounding boxes and stud counts, plus an overall model bounding box in LDU/mm.
- **Follow building steps** — pieces are grouped by their `0 STEP` markers where the model defines them.

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

## Troubleshooting

**"No LDraw library found" on first launch.**
The app needs the LDraw parts library on disk. Let the guided setup screen download it (~80 MB,
needs network access), or if you already have an LDraw install, point `config.yml` at it (see
[First run](#first-run) for the path) and relaunch.

**The parts index rebuild is slow or seems stuck.**
The first index build scans the whole library and takes a few seconds; a progress indicator shows
its status. Subsequent launches reuse the cached index and start instantly. If it never completes,
delete the `generated/` directory (see the paths table above) and relaunch to force a clean rebuild.

**Colours or swatches look wrong / boxes render as garbage.**
The UI expects a modern terminal with truecolor and Unicode support. Make sure `TERM` advertises
256+ colours (e.g. `xterm-256color`) and that your terminal font includes box-drawing glyphs.
Try a different terminal emulator if artifacts persist.

**Can I use my existing LDraw installation instead of downloading?**
Yes — set the library path in `config.yml` to your existing LDraw directory. The paths are shared
with `pyldraw3`, so any configuration that library already uses is picked up automatically.

**Where does it store things / how do I reset?**
Everything lives under the platform directories listed in [First run](#first-run). Deleting the
config and `generated/` directories resets the app to a first-run state.

## pyldraw3-tui vs. pyldraw3

[`pyldraw3`](https://github.com/hbmartin/pyldraw3) is the Python **library** for parsing, resolving,
and computing geometry from LDraw files. `pyldraw3-tui` is an interactive, **read-only** front end
built on top of it.

- Reach for **`pyldraw3`** when you're scripting: loading models, transforming geometry, generating
  BOMs programmatically, or building your own tools.
- Reach for **`pyldraw3-tui`** when you want to *explore* interactively — look up a part code, skim a
  model's pieces, or grab a snippet — without writing any code.

Both read the same configuration and library on disk, so they coexist happily. The TUI never writes
to your model or geometry files.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, the check
suite, and the snapshot-testing workflow. Please also review our
[Code of Conduct](.github/CODE_OF_CONDUCT.md).

## License

Distributed under the **GPL-3.0-or-later** license. See [LICENSE.txt](LICENSE.txt) for details.

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize, or endorse this project.
LDraw™ is a trademark of the Estate of James Jessiman.
