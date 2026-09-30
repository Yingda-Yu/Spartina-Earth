"""Sentinel-1 GRD (C-SAR, IW) adapter — ``COPERNICUS/S1_GRD``.

The GEE S1 GRD collection is already radiometrically terrain-corrected
and converted to sigma0 decibels by the ingestion pipeline, so no
reflectance scale is applied. Provenance captured per scene:

* orbit direction (``orbitProperties_pass``: ASCENDING/DESCENDING),
* relative orbit number (``relativeOrbitNumber_start``),
* platform (Sentinel-1A/1B), instrument mode, polarization,
* nominal resolution / pixel spacing and the ``angle`` band (incidence
  angle), used by the quality pipeline.

``ee`` is imported lazily; SAR scenes carry no cloud metadata.
"""

from __future__ import annotations

from typing import Any, Final

INSTRUMENT_MODE_IW: Final[str] = "IW"
POLARIZATIONS: Final[tuple[str, str]] = ("VV", "VH")
ORBIT_ASCENDING: Final[str] = "ASCENDING"
ORBIT_DESCENDING: Final[str] = "DESCENDING"
VALID_ORBITS: Final[frozenset[str]] = frozenset(
    {ORBIT_ASCENDING, ORBIT_DESCENDING})


def export_bands(*, include_angle: bool = False) -> tuple[str, ...]:
    bands: tuple[str, ...] = POLARIZATIONS
    if include_angle:
        bands = (*bands, "angle")
    return bands


def load_collection(
    ee: Any, region_geometry: Any, start_date: str, end_date: str,
    orbit_direction: str | None = None,
    polarizations: tuple[str, ...] = POLARIZATIONS,
) -> Any:
    """Filtered S1 GRD IW collection for the requested polarizations.

    ``orbit_direction`` must be ``ASCENDING``, ``DESCENDING`` or ``None``
    (both). Mixing directions in one composite without recording that
    choice is rejected at the pipeline layer, not here.
    """
    if orbit_direction is not None and orbit_direction not in VALID_ORBITS:
        raise ValueError(
            f"orbit_direction must be one of {sorted(VALID_ORBITS)}")
    from spartina.data.gee.collections import collection_for

    col = (ee.ImageCollection(collection_for("sentinel1"))
           .filterBounds(region_geometry)
           .filterDate(start_date, end_date)
           .filter(ee.Filter.eq("instrumentMode", INSTRUMENT_MODE_IW))
           .filter(ee.Filter.listContains(
               "transmitterReceiverPolarisation", polarizations[0])))
    for extra in polarizations[1:]:
        col = col.filter(ee.Filter.listContains(
            "transmitterReceiverPolarisation", extra))
    if orbit_direction is not None:
        col = col.filter(
            ee.Filter.eq("orbitProperties_pass", orbit_direction))
    return col


def record_from_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Map raw GEE S1 scene properties to a provenance record (pure)."""
    pol = properties.get("transmitterReceiverPolarisation")
    return {
        "scene_id": properties.get("system:index"),
        "product_id": properties.get("productIdentifier"),
        "acquisition_epoch_ms": properties.get("system:time_start"),
        "orbit_direction": properties.get("orbitProperties_pass"),
        "relative_orbit_number": properties.get(
            "relativeOrbitNumber_start"),
        "absolute_orbit_number": properties.get("orbitNumber_start"),
        "platform": properties.get("platform_number")
        or properties.get("SPACECRAFT_NAME"),
        "instrument_mode": properties.get("instrumentMode"),
        "polarizations": tuple(pol) if isinstance(pol, list | tuple)
        else None,
        "resolution_meters": properties.get("resolution_meters"),
        "product_type": properties.get("productType"),
        "slice_number": properties.get("sliceNumber"),
    }


__all__ = [
    "INSTRUMENT_MODE_IW",
    "ORBIT_ASCENDING",
    "ORBIT_DESCENDING",
    "POLARIZATIONS",
    "VALID_ORBITS",
    "export_bands",
    "load_collection",
    "record_from_properties",
]
