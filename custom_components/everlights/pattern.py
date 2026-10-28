"""Pure helpers for building EverLights sequence payloads (no HA imports)."""
from __future__ import annotations

import re
from typing import Any

EFFECT_TYPES = (
    "fade", "blink", "strobe", "chase", "reverseChase",
    "wipe", "random", "twinkle", "lightning",
)
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def normalize_color(color: Any) -> str:
    """Return 'RRGGBB' from '#rrggbb', 'rrggbb' or [r, g, b]."""
    if isinstance(color, str):
        m = _HEX.match(color.strip())
        if not m:
            raise ValueError(f"Invalid hex color: {color!r}")
        return m.group(1).upper()
    if isinstance(color, (list, tuple)) and len(color) == 3:
        rgb = [int(c) for c in color]
        if any(c < 0 or c > 255 for c in rgb):
            raise ValueError(f"RGB out of range: {color!r}")
        return "".join(f"{c:02X}" for c in rgb)
    raise ValueError(f"Unsupported color: {color!r}")


def build_sequence(colors: list[Any], effects: list[dict] | None = None) -> dict[str, Any]:
    """Build the POST /v1/zones/{serial}/sequence body."""
    if not colors:
        raise ValueError("At least one color is required")
    fx = []
    for eff in effects or []:
        etype = eff.get("type", eff.get("effectType"))
        if etype not in EFFECT_TYPES:
            raise ValueError(f"Unknown effect type: {etype!r}")
        speed = int(eff.get("speed", eff.get("value", 50)))
        if not 0 <= speed <= 255:
            raise ValueError(f"Speed out of range: {speed}")
        fx.append({"effectType": etype, "value": speed})
    return {"pattern": [normalize_color(c) for c in colors], "effects": fx}
