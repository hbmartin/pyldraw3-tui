"""Unit tests for summary size formatting and pyldraw3 bounds semantics."""

from __future__ import annotations

from ldraw import model_bounds, read_model

from pyldraw3_tui.widgets.stats_panel import size_label


def _components(vector) -> list[float]:
    return [vector.x, vector.y, vector.z]


def test_model_bounds_single_model(parts, car_ldr):
    bounds = model_bounds(read_model(car_ldr), parts)
    assert bounds is not None
    assert _components(bounds.min) == [-40, -36, -20]
    assert _components(bounds.max) == [60, 0, 20]


def test_model_bounds_uses_world_space_occurrences(parts, spaceship_mpd):
    bounds = model_bounds(read_model(spaceship_mpd), parts)
    assert bounds is not None
    assert _components(bounds.min) == [-80, -28, -20]
    assert _components(bounds.max) == [80, 0, 20]


def test_size_label_converts_to_mm():
    assert size_label([80, 28, 40]) == "80 x 28 x 40 LDU (32.0 x 11.2 x 16.0 mm)"
