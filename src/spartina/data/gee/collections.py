"""Collection identifiers and sensor-name mapping for GEE.

M0: constant mapping only. Exact collection IDs and band availability must
be re-verified against provider documentation before M1 exports
(``TODO_VERIFY``); the map is centralized so corrections touch one place.
"""

from __future__ import annotations

from typing import Final

#: Maps registry sensor names to the nominal GEE collection ID.
COLLECTIONS: Final[dict[str, str]] = {
    "landsat5": "LANDSAT/LT05/C02/T1_L2",
    "landsat7": "LANDSAT/LE07/C02/T1_L2",
    "landsat8": "LANDSAT/LC08/C02/T1_L2",
    "landsat9": "LANDSAT/LC09/C02/T1_L2",
    "sentinel1": "COPERNICUS/S1_GRD",
    "sentinel2": "COPERNICUS/S2_SR_HARMONIZED",
}

#: Sentinel-2 GEE reflectance integer scale (physical = DN/10000).
SENTINEL2_REFLECTANCE_SCALE: Final[int] = 10000

#: Landsat Collection 2 Level-2 surface-reflectance transform.
LANDSAT_C2_SR_MULTIPLY: Final[float] = 2.75e-5
LANDSAT_C2_SR_ADD: Final[float] = -0.2


def collection_for(sensor_name: str) -> str:
    """Return the GEE collection ID for a registered sensor name."""
    try:
        return COLLECTIONS[sensor_name]
    except KeyError:
        raise KeyError(f"No GEE collection mapping for sensor {sensor_name!r}") from None


__all__ = [
    "COLLECTIONS",
    "SENTINEL2_REFLECTANCE_SCALE",
    "LANDSAT_C2_SR_MULTIPLY",
    "LANDSAT_C2_SR_ADD",
    "collection_for",
]
