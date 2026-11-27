"""Tests for the identity-aware sensor registry."""

from __future__ import annotations

import pytest

from spartina.data.sensors import (
    BandSpec,
    Modality,
    SensorRegistry,
    SensorSpec,
    default_registry,
)


def test_bands_are_identity_not_channel_index() -> None:
    registry = default_registry()
    # Landsat 8 red band is SR_B4 at ~655 nm; Sentinel-2 red is B4 at ~665 nm.
    # Both are "channel 4"-ish in legacy intuition but distinct identities.
    l8_red = registry.get_band("landsat8", "SR_B4")
    s2_red = registry.get_band("sentinel2", "B4")
    assert l8_red.name != s2_red.name
    assert l8_red.wavelength_nm == pytest.approx(655.0, abs=1.0)
    assert s2_red.wavelength_nm == pytest.approx(665.0, abs=1.0)


def test_sar_bands_have_no_optical_wavelength() -> None:
    registry = default_registry()
    assert registry.get("sentinel1").modality is Modality.SAR
    assert registry.get_band("sentinel1", "VV").wavelength_nm is None


def test_mixed_resolution_sentinel2_bands() -> None:
    registry = default_registry()
    assert registry.get_band("sentinel2", "B2").resolution_m == 10.0
    assert registry.get_band("sentinel2", "B5").resolution_m == 20.0
    assert registry.get_band("sentinel2", "B1").resolution_m == 60.0


def test_unknown_sensor_and_band_raise() -> None:
    registry = default_registry()
    with pytest.raises(KeyError):
        registry.get("modis")
    with pytest.raises(KeyError):
        registry.get_band("landsat8", "B_NOT_REAL")


def test_duplicate_sensor_registration_rejected() -> None:
    registry = SensorRegistry()
    spec = SensorSpec(
        sensor_name="x",
        platform="X",
        modality=Modality.OPTICAL,
        native_resolution_m=30.0,
        bands=(BandSpec("a", 1.0),),
    )
    registry.register(spec)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(spec)


def test_duplicate_band_name_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate band"):
        SensorSpec(
            sensor_name="y",
            platform="Y",
            modality=Modality.OPTICAL,
            native_resolution_m=30.0,
            bands=(BandSpec("a", 1.0), BandSpec("a", 2.0)),
        )
