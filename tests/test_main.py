"""Tests for the command-line entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyldraw3_tui.main import main

if TYPE_CHECKING:
    from pathlib import Path


def test_malformed_config_exits_with_message(tmp_path: Path, capsys):
    bad_config = tmp_path / "config.yml"
    bad_config.write_text("- not\n- a\n- mapping\n")
    with pytest.raises(SystemExit) as excinfo:
        main(["--config", str(bad_config)])
    assert excinfo.value.code == 1
    stderr = capsys.readouterr().err
    assert "config.yml" in stderr
    assert "mapping" in stderr
