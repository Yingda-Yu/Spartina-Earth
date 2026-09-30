"""Sentinel-2 Surface Reflectance Harmonized adapter.

Collection ``COPERNICUS/S2_SR_HARMONIZED``. Reflectance bands are scaled
by 1e-4 in GEE (DN/10000, harmonized baseline offset already applied by
the collection). Quality uses the Scene Classification Layer (``SCL``)
and, optionally, the cloud probability band ``MSK_CLDPRB`` (20 m).

``ee`` is imported lazily; the SCL decoder is a pure integer function so
unit tests need no Earth Engine.

SCL classes (S2MSI product specification):
0 no data, 1 saturated/defective, 2 dark area, 3 cloud shadow,
4 vegetation, 5 bare soils, 6 water, 7 unclassified,
8 cloud medium prob, 9 cloud high prob, 10 thin cirrus, 11 snow/ice.
"""

from __future__ import annotations

from typing import Any, Final

#: SCL classes treated as valid surface observations.
SCL_CLEAR_CLASSES: Final[frozenset[int]] = frozenset({4, 5, 6, 11})

#: Every SCL class with a fixed meaning (used by the candidate audit).
SCL_CLASS_NAMES: Final[dict[int, str]] = {
    0: "no_data", 1: "saturated_or_defective", 2: "dark_area",
    3: "cloud_shadow", 4: "vegetation", 5: "bare_soils", 6: "water",
    7: "unclassified", 8: "cloud_medium_probability",
    9: "cloud_high_probability", 10: "thin_cirrus", 11: "snow_or_ice",
}

REFLECTANCE_BANDS: Final[tuple[str, ...]] = (
    "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9",
    "B11", "B12")
#: 10 m science-stream bands only (native 10 m — never resampled 20/60 m
#: bands presented as 10 m).
TEN_M_BANDS: Final[tuple[str, ...]] = ("B2", "B3", "B4", "B8")
REFLECTANCE_SCALE: Final[float] = 10000.0
DEFAULT_CLDPRB_THRESHOLD: Final[int] = 60  # percent


def scl_is_clear(value: int) -> bool:
    """Pure SCL pixel decision: valid surface class."""
    return int(value) in SCL_CLEAR_CLASSES


def export_bands(*, include_scl: bool = True,
                 include_cloudprob: bool = False) -> tuple[str, ...]:
    bands = tuple(REFLECTANCE_BANDS)
    if include_scl:
        bands = (*bands, "SCL")
    if include_cloudprob:
        bands = (*bands, "MSK_CLDPRB")
    return bands


def load_collection(ee: Any, region_geometry: Any, start_date: str,
                    end_date: str,
                    max_cloud_cover: float | None = None) -> Any:
    """Filtered S2 SR Harmonized collection (still in DN)."""
    from spartina.data.gee.collections import collection_for

    col = (ee.ImageCollection(collection_for("sentinel2"))
           .filterBounds(region_geometry)
           .filterDate(start_date, end_date))
    if max_cloud_cover is not None:
        col = col.filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE",
                                       float(max_cloud_cover) * 100.0))
    return col


def scl_clear_mask(ee: Any, image: Any) -> Any:
    """Mask to SCL clear-surface pixels."""
    scl = image.select("SCL")
    mask = ee.Image(0)
    for cls in sorted(SCL_CLEAR_CLASSES):
        mask = mask.Or(scl.eq(cls))
    return image.updateMask(mask)


def cloudprob_mask(ee: Any, image: Any,
                   threshold_percent: int = DEFAULT_CLDPRB_THRESHOLD) -> Any:
    """Mask out cloudy pixels via MSK_CLDPRB (nearest-neighbour kept)."""
    prob = image.select("MSK_CLDPRB")
    return image.updateMask(prob.lt(int(threshold_percent)))


def scale_to_physical(ee: Any, image: Any) -> Any:
    """Divide reflectance bands by 10000."""
    return image.select(list(REFLECTANCE_BANDS)).divide(REFLECTANCE_SCALE)


def record_from_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Map raw GEE S2 scene properties to a provenance record (pure)."""
    return {
        "scene_id": properties.get("system:index"),
        "product_id": (properties.get("PRODUCT_ID")
                       or properties.get("DATATAKE_IDENTIFIER")),
        "datatake_identifier": properties.get("DATATAKE_IDENTIFIER"),
        "acquisition_epoch_ms": properties.get("system:time_start"),
        "mgrs_tile": properties.get("MGRS_TILE"),
        "cloudy_pixel_fraction": (
            float(properties["CLOUDY_PIXEL_PERCENTAGE"]) / 100.0
            if properties.get("CLOUDY_PIXEL_PERCENTAGE") is not None
            else None),
        "generation_time_epoch_ms": properties.get("GENERATION_TIME"),
        "spacecraft": properties.get("SPACECRAFT_NAME"),
        "processing_baseline": properties.get("PROCESSING_BASELINE"),
        "sensing_orbit_number": properties.get("SENSING_ORBIT_NUMBER"),
        "orbit_direction": properties.get(
            "orbitProperties_pass"),
    }


__all__ = [
    "DEFAULT_CLDPRB_THRESHOLD",
    "REFLECTANCE_BANDS",
    "REFLECTANCE_SCALE",
    "SCL_CLASS_NAMES",
    "SCL_CLEAR_CLASSES",
    "TEN_M_BANDS",
    "cloudprob_mask",
    "export_bands",
    "load_collection",
    "record_from_properties",
    "scale_to_physical",
    "scl_clear_mask",
    "scl_is_clear",
]
