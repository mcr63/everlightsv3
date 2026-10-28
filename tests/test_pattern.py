"""Pure helpers work without importing Home Assistant."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "pattern", Path(__file__).parents[1] / "custom_components/everlights_v3/pattern.py"
)
pattern = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pattern)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("#ff9a3c", "FF9A3C"), ("abcdef", "ABCDEF"), ([0, 128, 255], "0080FF")],
)
def test_color(value, expected):
    assert pattern.normalize_color(value) == expected


@pytest.mark.parametrize("value", ["12345", "GGGGGG", [-1, 0, 0], [1, 2]])
def test_bad_color(value):
    with pytest.raises(ValueError):
        pattern.normalize_color(value)


def test_scaling():
    base = ["FF8040"]
    assert pattern.scale_pattern(base, 128) == ["804020"]
    assert pattern.scale_pattern(base, 255) == base
    assert base == ["FF8040"]
    assert pattern.pattern_brightness(["204080"]) == 128


def test_effects():
    assert len(pattern.EFFECT_TYPES) == 13
    body = pattern.build_sequence(
        ["#ff0000"],
        [
            {"type": "bars", "value": 999},
            {"type": "fade", "value": -2},
            {"type": "blink"},
        ],
    )
    assert body == {
        "pattern": ["FF0000"],
        "effects": [
            {"effectType": "bars", "value": 255},
            {"effectType": "fade", "value": 0},
            {"effectType": "blink", "value": 128},
        ],
    }
    with pytest.raises(ValueError):
        pattern.build_sequence(["FFFFFF"], [{"type": "invalid"}])
    with pytest.raises(ValueError):
        pattern.build_sequence([])


def test_builtin():
    assert pattern.is_builtin({"id": "00000000-example"})
    assert pattern.is_builtin({"colorMode": "none"})
    assert not pattern.is_builtin({"id": "user-preset", "colorMode": "rgb"})
