"""Pure helpers for building EverLights sequence payloads (no HA imports)."""

from __future__ import annotations

import re
from typing import Any

EFFECT_TYPES = (
    "fade",
    "blink",
    "strobe",
    "chase",
    "reverseChase",
    "wipe",
    "random",
    "twinkle",
    "lightning",
    "bars",
    "gradient",
    "melt",
    "pingPong",
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


def build_sequence(
    colors: list[Any], effects: list[dict] | None = None
) -> dict[str, Any]:
    """Build the POST /v1/zones/{serial}/sequence body."""
    if not colors:
        raise ValueError("At least one color is required")
    fx = []
    for eff in effects or []:
        etype = eff.get("type", eff.get("effectType"))
        if etype not in EFFECT_TYPES:
            raise ValueError(f"Unknown effect type: {etype!r}")
        speed = int(eff.get("speed", eff.get("value", 128)))
        speed = max(0, min(255, speed))
        fx.append({"effectType": etype, "value": speed})
    return {"pattern": [normalize_color(c) for c in colors], "effects": fx}


def scale_pattern(pattern: list[str], brightness: int) -> list[str]:
    """Scale an unmodified base pattern, without cumulative rounding loss."""
    factor = max(0, min(255, brightness)) / 255
    return [
        "".join(f"{round(int(c[i : i + 2], 16) * factor):02X}" for i in (0, 2, 4))
        for c in pattern
    ]


def pattern_brightness(pattern: list[str]) -> int:
    """Find the brightest channel."""
    return max((int(c[i : i + 2], 16) for c in pattern for i in (0, 2, 4)), default=255)


def is_builtin(preset: dict) -> bool:
    """Recognize factory presets."""
    return preset.get("colorMode") == "none" or str(preset.get("id", "")).startswith(
        "00000000-"
    )
