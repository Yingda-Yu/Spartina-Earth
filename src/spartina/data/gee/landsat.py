"""Landsat Collection 2 Level-2 adapter (Landsat 5/7/8/9).

All Earth Engine usage is lazy (``ee`` imported inside functions) so that
importing this module never requires credentials or ``earthengine-api``.
Pure helpers (QA bit decoding, property mapping) are unit-tested offline
on integer values and plain dictionaries.

References (USGS Landsat Collection 2 Level-2 product guides; the QA bit
layout is part of the product specification):
* ``QA_PIXEL``: bit 0 Fill, 1 Dilated Cloud, 2 Cirrus, 3 Cloud,
  4 Cloud Shadow, 5 Snow, 6 Clear, 7 Water, 8-9 cloud confidence,
  10-11 shadow confidence, 12-13 snow confidence, 14 cirrus confidence.
* Surface reflectance: DN * 2.75e-5 - 0.2.
* Surface temperature (ST_B6 / ST_B10): DN * 0.00341802 + 149.0 K.
"""

from __future__ import annotations

from typing import Any, Final

from spartina.data.gee.collections import (
    LANDSAT_C2_SR_ADD,
    LANDSAT_C2_SR_MULTIPLY,
)

#: sensor -> (surface reflectance bands, thermal band, platform prefix)
SENSOR_CONFIG: Final[dict[str, tuple[tuple[str, ...], str | None, str]]] = {
    "landsat5": (
        ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"),
        "ST_B6", "LT05"),
    "landsat7": (
        ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"),
        "ST_B6", "LE07"),
    "landsat8": (
        ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"),
        "ST_B10", "LC08"),
    "landsat9": (
        ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"),
        "ST_B10", "LC09"),
}

# QA_PIXEL bit positions
QA_FILL: Final = 0
QA_DILATED_CLOUD: Final = 1
QA_CIRRUS: Final = 2
QA_CLOUD: Final = 3
QA_CLOUD_SHADOW: Final = 4
QA_SNOW: Final = 5
QA_CLEAR: Final = 6

LANDSAT_ST_MULTIPLY: Final[float] = 0.00341802
LANDSAT_ST_ADD: Final[float] = 149.0


def supported_sensors() -> tuple[str, ...]:
    return tuple(SENSOR_CONFIG)


def sr_bands(sensor_name: str) -> tuple[str, ...]:
    return SENSOR_CONFIG[sensor_name][0]


def thermal_band(sensor_name: str) -> str | None:
    return SENSOR_CONFIG[sensor_name][1]


def export_bands(sensor_name: str, *, include_thermal: bool = False) -> tuple[str, ...]:
    """Bands to request for an export, in registry order."""
    bands = sr_bands(sensor_name)
    thermal = thermal_band(sensor_name)
    if include_thermal and thermal is not None:
        bands = (*bands, thermal)
    return (*bands, "QA_PIXEL", "QA_RADSAT")


def qa_pixel_is_clear(value: int) -> bool:
    """Pure pixel-level clear-sky decision from one ``QA_PIXEL`` DN.

    Clear requires: not fill, no dilated cloud / cirrus / cloud / shadow /
    snow, and the product's explicit Clear bit set. Water is allowed
    (coastal ROI) — it is a surface type, not a quality defect.
    """
    blocked = (QA_FILL, QA_DILATED_CLOUD, QA_CIRRUS, QA_CLOUD,
               QA_CLOUD_SHADOW, QA_SNOW)
    if any((int(value) >> bit) & 1 for bit in blocked):
        return False
    return bool((int(value) >> QA_CLEAR) & 1)


def qa_radsat_ok(value: int) -> bool:
    """True when no radiometric saturation flag is set (QA_RADSAT == 0)."""
    return int(value) == 0


# ---------------------------------------------------------------------------
# Earth Engine expressions (lazy import; exercised by gee_integration only)
# ---------------------------------------------------------------------------

def load_collection(ee: Any, sensor_name: str, region_geometry: Any,
                    start_date: str, end_date: str,
                    max_cloud_cover: float | None = None) -> Any:
    """Return the filtered C2 L2 ImageCollection (scenes still in DN)."""
    from spartina.data.gee.collections import collection_for

    col = (ee.ImageCollection(collection_for(sensor_name))
           .filterBounds(region_geometry)
           .filterDate(start_date, end_date))
    if max_cloud_cover is not None:
        col = col.filter(ee.Filter.lte("CLOUD_COVER",
                                       float(max_cloud_cover) * 100.0))
    return col


def clear_mask(ee: Any, image: Any) -> Any:
    """Apply the pure QA decision as an Earth Engine pixel mask."""
    qa = image.select("QA_PIXEL")
    radsat = image.select("QA_RADSAT")
    conditions = [
        qa.bitwiseAnd(1 << QA_FILL).eq(0),
        qa.bitwiseAnd(1 << QA_DILATED_CLOUD).eq(0),
        qa.bitwiseAnd(1 << QA_CIRRUS).eq(0),
        qa.bitwiseAnd(1 << QA_CLOUD).eq(0),
        qa.bitwiseAnd(1 << QA_CLOUD_SHADOW).eq(0),
        qa.bitwiseAnd(1 << QA_SNOW).eq(0),
        qa.bitwiseAnd(1 << QA_CLEAR).neq(0),
        radsat.eq(0),
    ]
    mask = conditions[0]
    for extra in conditions[1:]:
        mask = mask.And(extra)
    return image.updateMask(mask)


def scale_to_physical(ee: Any, image: Any, sensor_name: str) -> Any:
    """Apply per-family scales: SR reflectance (unitless) and ST (K)."""
    sr = list(sr_bands(sensor_name))
    out = image.select(sr).multiply(LANDSAT_C2_SR_MULTIPLY).add(
        LANDSAT_C2_SR_ADD)
    thermal = thermal_band(sensor_name)
    if thermal is not None:
        st = image.select(thermal).multiply(LANDSAT_ST_MULTIPLY).add(
            LANDSAT_ST_ADD).rename(thermal)
        out = ee.Image.cat([out, st])
    return out


def record_from_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Map raw GEE scene properties to a provenance record (pure).

    Keys not present are recorded as ``None`` — never guessed. Times are
    kept as GEE epoch milliseconds; the caller converts to UTC ISO.
    """
    index = properties.get("system:index")
    product_id = properties.get("LANDSAT_PRODUCT_ID") or (
        f"LANDSAT/{index}" if index else None)
    return {
        "scene_id": index,
        "product_id": product_id,
        "acquisition_epoch_ms": properties.get("system:time_start"),
        "wrs_path": properties.get("WRS_PATH"),
        "wrs_row": properties.get("WRS_ROW"),
        "cloud_cover_fraction": (
            float(properties["CLOUD_COVER"]) / 100.0
            if properties.get("CLOUD_COVER") is not None else None),
        "cloud_cover_land_fraction": (
            float(properties["CLOUD_COVER_LAND"]) / 100.0
            if properties.get("CLOUD_COVER_LAND") is not None else None),
        "sun_azimuth_deg": properties.get("SUN_AZIMUTH"),
        "sun_elevation_deg": properties.get("SUN_ELEVATION"),
        "spacecraft_id": properties.get("SPACECRAFT_ID"),
        "processing_level": properties.get("PROCESSING_LEVEL"),
        "collection_category": properties.get("COLLECTION_CATEGORY"),
    }


__all__ = [
    "LANDSAT_ST_ADD",
    "LANDSAT_ST_MULTIPLY",
    "SENSOR_CONFIG",
    "clear_mask",
    "export_bands",
    "load_collection",
    "qa_pixel_is_clear",
    "qa_radsat_ok",
    "record_from_properties",
    "scale_to_physical",
    "sr_bands",
    "supported_sensors",
    "thermal_band",
]
