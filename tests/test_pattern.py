import importlib.util
import pathlib

import pytest

spec = importlib.util.spec_from_file_location("pattern", pathlib.Path(__file__).parents[1] / "custom_components/everlights/pattern.py")
pattern = importlib.util.module_from_spec(spec); spec.loader.exec_module(pattern)

def test_build():
    assert pattern.build_sequence(["#ff6a00", [109, 4, 255]], [{"type": "chase", "speed": 60}]) == {
        "pattern": ["FF6A00", "6D04FF"], "effects": [{"effectType": "chase", "value": 60}]}

def test_static():
    assert pattern.build_sequence(["FF0000"])["effects"] == []

@pytest.mark.parametrize("colors,effects", [([], None), (["XYZ"], None), ([[300, 0, 0]], None), (["FF0000"], [{"type": "spin"}]), (["FF0000"], [{"type": "fade", "speed": 999}])])
def test_invalid(colors, effects):
    with pytest.raises(ValueError):
        pattern.build_sequence(colors, effects)
