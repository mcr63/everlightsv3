"""Enable custom integration fixtures when HA is installed."""

from __future__ import annotations

import importlib.util

import pytest

HAS_HA = importlib.util.find_spec("pytest_homeassistant_custom_component") is not None
if HAS_HA:
    pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def custom_integration(request, monkeypatch):
    if HAS_HA:
        request.getfixturevalue("enable_custom_integrations")
        from pathlib import Path

        import custom_components

        monkeypatch.setattr(
            custom_components,
            "__path__",
            [str(Path(__file__).parents[1] / "custom_components")],
        )
