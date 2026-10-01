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

QA contract (single source of truth, versioned):
``S2_SCL_QA_POLICY`` / :data:`S2_SCL_QA_POLICY_VERSION`.

* ``s2_scl_qa_v1`` (implicit, pre-M1.6d): valid classes were
  ``{4, 5, 6, 11}`` -- SCL 11 (snow/ice) was incorrectly treated as a
  valid coastal surface. Retained only as :data:`S2_LEGACY_V1_VALID_SCL_CLASSES`
  for auditing historical artifacts; never use it for new products.
* ``s2_scl_qa_v1_1`` (current): valid surface classes are exactly
  ``{4, 5, 6}`` (vegetation, bare soils, water). Water stays valid
  (coastal constraint). SCL 11 is invalid and is reported separately via
  the snow statistics. SCL 2 (dark area) and SCL 7 (unclassified) are
  invalid by an explicit project policy decision, not by omission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

#: Every SCL class with a fixed meaning (used by the candidate audit).
SCL_CLASS_NAMES: Final[dict[int, str]] = {
    0: "no_data", 1: "saturated_or_defective", 2: "dark_area",
    3: "cloud_shadow", 4: "vegetation", 5: "bare_soils", 6: "water",
    7: "unclassified", 8: "cloud_medium_probability",
    9: "cloud_high_probability", 10: "thin_cirrus", 11: "snow_or_ice",
}

# ---------------------------------------------------------------------------
# Versioned SCL QA contract -- the ONLY place class membership is decided.
# Catalog QA counts, export VALID masks, tests and manifests must derive
# from S2_SCL_QA_POLICY; class numbers must never be re-hardcoded.
# ---------------------------------------------------------------------------

#: Historical (incorrect) valid set used before the M1.6d correction.
#: Audit-only constant: SCL 11 = snow/ice is NOT a valid coastal surface.
S2_LEGACY_V1_VALID_SCL_CLASSES: Final[frozenset[int]] = frozenset(
    {4, 5, 6, 11})

#: Version of the implicit, unversioned pre-correction policy.
S2_LEGACY_V1_QA_POLICY_VERSION: Final[str] = "s2_scl_qa_v1"

#: Current QA policy version.
S2_SCL_QA_POLICY_VERSION: Final[str] = "s2_scl_qa_v1_1"

#: Valid coastal surface: vegetation / bare soils / water.
S2_VALID_SCL_CLASSES: Final[frozenset[int]] = frozenset({4, 5, 6})
#: Cloud family used by the catalog cloud statistic (8/9/10).
S2_CLOUD_FAMILY_CLASSES: Final[frozenset[int]] = frozenset({8, 9, 10})
#: Cloud shadow statistic.
S2_CLOUD_SHADOW_CLASSES: Final[frozenset[int]] = frozenset({3})
#: Thin-cirrus statistic (also part of the cloud family).
S2_CIRRUS_CLASSES: Final[frozenset[int]] = frozenset({10})
#: Snow / ice statistic; invalid as surface, reported separately.
S2_SNOW_ICE_CLASSES: Final[frozenset[int]] = frozenset({11})
#: Sensor-side invalidity: no data / saturated or defective.
S2_SENSOR_INVALID_CLASSES: Final[frozenset[int]] = frozenset({0, 1})
#: Explicit project decision: dark-area pixels are NOT valid.
S2_DARK_AREA_CLASSES: Final[frozenset[int]] = frozenset({2})
#: Explicit project decision: unclassified pixels are NOT valid.
S2_UNCLASSIFIED_CLASSES: Final[frozenset[int]] = frozenset({7})

#: Stable correction reason code stored in superseded-product manifests.
S2_SCL_11_CORRECTION_REASON: Final[str] = (
    "S2_SCL_CLASS_11_SNOW_ICE_WAS_INCORRECTLY_INCLUDED_IN_VALID_SET")

#: Human-readable rationale recorded per explicitly-decided class.
_DARK_AREA_NOTE: Final[str] = (
    "NOT_VALID_EXPLICIT_POLICY_DECISION: SCL 2 (dark area pixels) is not "
    "an official clear-surface class; it stays invalid under "
    "s2_scl_qa_v1_1 and is never silently treated as valid")
_UNCLASSIFIED_NOTE: Final[str] = (
    "NOT_VALID_EXPLICIT_POLICY_DECISION: SCL 7 (unclassified / low-"
    "probability cloud) is not a confident surface class; it stays "
    "invalid under s2_scl_qa_v1_1")
_SNOW_ICE_NOTE: Final[str] = (
    "NOT_VALID_QA_SEMANTICS_CORRECTION: SCL 11 is snow/ice per the S2MSI "
    "specification; it is counted in the separate snow statistic and must "
    "never be silently included in the valid coastal-surface set")


@dataclass(frozen=True)
class S2SclQaPolicy:
    """Typed Sentinel-2 SCL QA contract (one version, one instance)."""

    version: str
    valid_classes: frozenset[int]
    cloud_family_classes: frozenset[int]
    cloud_shadow_classes: frozenset[int]
    cirrus_classes: frozenset[int]
    snow_ice_classes: frozenset[int]
    sensor_invalid_classes: frozenset[int]
    dark_area_classes: frozenset[int]
    unclassified_classes: frozenset[int]
    class_names: dict[int, str]
    water_class: int = 6

    def __post_init__(self) -> None:
        decided = (
            self.valid_classes | self.cloud_family_classes
            | self.cloud_shadow_classes | self.snow_ice_classes
            | self.sensor_invalid_classes | self.dark_area_classes
            | self.unclassified_classes)
        if decided != frozenset(range(12)):
            missing = sorted(frozenset(range(12)) - decided)
            raise ValueError(f"SCL QA policy leaves classes {missing} "
                             "without an explicit decision")
        if self.water_class not in self.valid_classes:
            raise ValueError("water (SCL 6) must remain a valid class")

    def category_of(self, value: int) -> str:
        """Stable category name for an SCL class (audit/histograms)."""
        cls = int(value)
        if cls in self.valid_classes:
            return "valid_surface"
        if cls in self.snow_ice_classes:
            return "snow_or_ice"
        if cls in self.cloud_family_classes:
            return "cloud"
        if cls in self.cloud_shadow_classes:
            return "cloud_shadow"
        if cls in self.sensor_invalid_classes:
            return "sensor_invalid"
        if cls in self.dark_area_classes:
            return "dark_area"
        if cls in self.unclassified_classes:
            return "unclassified"
        return "undecided"  # pragma: no cover - guarded by __post_init__

    def is_valid(self, value: int) -> bool:
        """Pure SCL pixel decision: valid coastal surface class."""
        return int(value) in self.valid_classes

    def class_decision_table(self) -> list[dict[str, object]]:
        """Every class 0..11 with semantic name + explicit valid decision."""
        notes = {
            2: _DARK_AREA_NOTE, 7: _UNCLASSIFIED_NOTE, 11: _SNOW_ICE_NOTE}
        return [{
            "class": cls,
            "semantic_name": self.class_names[cls],
            "category": self.category_of(cls),
            "valid": cls in self.valid_classes,
            "policy_note": notes.get(cls, ""),
        } for cls in range(12)]

    def ee_any_classes(self, ee: Any, scl: Any,
                       classes: frozenset[int]) -> Any:
        """Earth Engine image: 1 where SCL equals any of ``classes``.

        The OR chain is generated from the contract so callers cannot
        hardcode a divergent class list.
        """
        mask = ee.Image(0)
        for cls in sorted(classes):
            mask = mask.Or(scl.eq(cls))
        return mask

    def ee_valid_surface(self, ee: Any, scl: Any) -> Any:
        """Earth Engine 0/1 image of the valid-surface decision."""
        return self.ee_any_classes(ee, scl, self.valid_classes)

    def to_manifest_dict(self) -> dict[str, Any]:
        """Deterministic contract record embedded in locks/manifests."""
        invalid = frozenset(range(12)) - self.valid_classes
        return {
            "version": self.version,
            "source_band": "SCL",
            "valid_classes": {
                str(cls): self.class_names[cls]
                for cls in sorted(self.valid_classes)},
            "not_valid_classes": {
                str(cls): self.class_names[cls]
                for cls in sorted(invalid)},
            "category_mapping": {
                "cloud_family_classes": sorted(self.cloud_family_classes),
                "cloud_shadow_classes": sorted(self.cloud_shadow_classes),
                "cirrus_classes": sorted(self.cirrus_classes),
                "snow_ice_classes": sorted(self.snow_ice_classes),
                "water_class": self.water_class,
                "sensor_invalid_classes": sorted(self.sensor_invalid_classes),
                "dark_area_classes": sorted(self.dark_area_classes),
                "unclassified_classes": sorted(self.unclassified_classes),
            },
            "water_remains_valid": True,
            "snow_or_ice_remains_valid": False,
            "dark_area_class_2_decision": "NOT_VALID_EXPLICIT_POLICY_DECISION",
            "unclassified_class_7_decision":
                "NOT_VALID_EXPLICIT_POLICY_DECISION",
            "class_decision_table": self.class_decision_table(),
            "byte_encoding": (
                "1 = VALID (SCL in {4,5,6}); 0 = not valid; masked "
                "footprint unmasked to 0"),
            "supersedes": S2_LEGACY_V1_QA_POLICY_VERSION,
            "superseded_valid_classes": sorted(
                S2_LEGACY_V1_VALID_SCL_CLASSES),
            "correction_reason": S2_SCL_11_CORRECTION_REASON,
            "identity_with_catalog": (
                "VALID == CLEAR_PIXELS rule in "
                "spartina.data.gee.pixelqa.sentinel2_qa_count_bands; the "
                "catalog clear_pixel_fraction and the export VALID mask "
                "share this single SCL contract"),
        }


#: The project-wide current Sentinel-2 SCL QA contract.
S2_SCL_QA_POLICY: Final[S2SclQaPolicy] = S2SclQaPolicy(
    version=S2_SCL_QA_POLICY_VERSION,
    valid_classes=S2_VALID_SCL_CLASSES,
    cloud_family_classes=S2_CLOUD_FAMILY_CLASSES,
    cloud_shadow_classes=S2_CLOUD_SHADOW_CLASSES,
    cirrus_classes=S2_CIRRUS_CLASSES,
    snow_ice_classes=S2_SNOW_ICE_CLASSES,
    sensor_invalid_classes=S2_SENSOR_INVALID_CLASSES,
    dark_area_classes=S2_DARK_AREA_CLASSES,
    unclassified_classes=S2_UNCLASSIFIED_CLASSES,
    class_names=SCL_CLASS_NAMES,
)

#: Manifest-ready record of the current contract (frozen on import).
S2_SCL_QA_POLICY_RECORD: Final[dict[str, Any]] = (
    S2_SCL_QA_POLICY.to_manifest_dict())

REFLECTANCE_BANDS: Final[tuple[str, ...]] = (
    "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9",
    "B11", "B12")
#: 10 m science-stream bands only (native 10 m — never resampled 20/60 m
#: bands presented as 10 m).
TEN_M_BANDS: Final[tuple[str, ...]] = ("B2", "B3", "B4", "B8")
REFLECTANCE_SCALE: Final[float] = 10000.0
DEFAULT_CLDPRB_THRESHOLD: Final[int] = 60  # percent


def scl_is_valid(value: int) -> bool:
    """Pure SCL pixel decision: valid coastal surface class."""
    return S2_SCL_QA_POLICY.is_valid(value)


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


def scl_valid_surface_mask(ee: Any, image: Any) -> Any:
    """Mask an image to the contract valid-surface pixels."""
    scl = image.select("SCL")
    mask = S2_SCL_QA_POLICY.ee_valid_surface(ee, scl)
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
    "S2SclQaPolicy",
    "S2_CIRRUS_CLASSES",
    "S2_CLOUD_FAMILY_CLASSES",
    "S2_CLOUD_SHADOW_CLASSES",
    "S2_DARK_AREA_CLASSES",
    "S2_LEGACY_V1_QA_POLICY_VERSION",
    "S2_LEGACY_V1_VALID_SCL_CLASSES",
    "S2_SCL_11_CORRECTION_REASON",
    "S2_SCL_QA_POLICY",
    "S2_SCL_QA_POLICY_RECORD",
    "S2_SCL_QA_POLICY_VERSION",
    "S2_SENSOR_INVALID_CLASSES",
    "S2_SNOW_ICE_CLASSES",
    "S2_UNCLASSIFIED_CLASSES",
    "S2_VALID_SCL_CLASSES",
    "SCL_CLASS_NAMES",
    "TEN_M_BANDS",
    "cloudprob_mask",
    "export_bands",
    "load_collection",
    "record_from_properties",
    "scale_to_physical",
    "scl_is_valid",
    "scl_valid_surface_mask",
]
