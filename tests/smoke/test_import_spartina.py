"""Smoke test: the package imports and exposes its M0 surface."""

from __future__ import annotations

import spartina
from spartina.data.sensors import default_registry
from spartina.labels import LabelQuality


def test_package_version() -> None:
    assert isinstance(spartina.__version__, str)
    assert spartina.__version__.count(".") == 2


def test_default_registry_contains_six_sensors() -> None:
    registry = default_registry()
    assert len(registry) == 6
    assert set(registry.names()) == {
        "landsat5",
        "landsat7",
        "landsat8",
        "landsat9",
        "sentinel1",
        "sentinel2",
    }


def test_label_quality_tiers() -> None:
    assert set(LabelQuality.values()) == {"GOLD", "SILVER", "WEAK", "UNLABELED"}
