"""Derived label-support policy for the Issue #19 20-cell pilot.

The pilot NEVER trains on, reshapes, or re-distributes the frozen source
archives (GEODATA 1990/2000/2015/2020 rasters; CMSA 2017-2021 polygons;
CM-SSM 2020 polygons). This module defines the predeclared semantics of
*derived* fractional-occupancy supports aligned to the pilot EO grids:

* fractions are polygon-area / pixel-area (vectors) or binary mask
  presence (rasters, native 30 m, nearest-neighbour warp into a cell UTM
  grid); they are occupancy summaries of SILVER products, never ground
  truth, and must never be quoted as accuracy;
* 30 m sources are never written onto 10 m supports: GEODATA and CMSA
  support 30 m only; CM-SSM supports 10 m and 30 m (AGENTS.md rule 7);
* CMSA ``gridcode == 0`` features have UNKNOWN semantics
  (``UNKNOWN_GRIDCODE_ZERO_TODO_VERIFY``); they are never converted into
  negatives;
* no source ships a verified negative class: GEODATA value 255 is the
  declared raster nodata/background; vector products are positive-only.
  PURE_NEGATIVE is therefore only assigned to GEODATA in-window mapped
  background pixels (weak-negative semantics recorded on the product),
  while uncovered vector pixels and out-of-raster-window pixels stay
  UNKNOWN.

Pure numpy semantics live here; all file I/O is in the builder script.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Final

import numpy as np

ADAPTER_VERSION: Final[str] = "PILOT_LABEL_ADAPTER_V1"

#: Predeclared occupancy-class thresholds, identical to the values used
#: by the Issue #18 scale audit (fixed before any pilot pixel was read).
PURE_LO: Final[float] = 0.10
PURE_HI: Final[float] = 0.90


class OccupancyClass(IntEnum):
    """Per-pixel fractional-occupancy class on a derived support."""

    PURE_POSITIVE = 1
    MIXED = 2
    PURE_NEGATIVE = 3
    UNKNOWN = 0


#: Machine-readable UNKNOWN sub-reasons (never silently collapse).
UNKNOWN_OUTSIDE_SOURCE_WINDOW: Final[str] = "UNKNOWN_OUTSIDE_SOURCE_WINDOW"
UNKNOWN_GRIDCODE_ZERO: Final[str] = "UNKNOWN_GRIDCODE_ZERO_TODO_VERIFY"
UNKNOWN_NO_VERIFIED_NEGATIVE_ENVELOPE: Final[str] = (
    "UNKNOWN_NO_VERIFIED_NEGATIVE_ENVELOPE")
UNKNOWN_BACKGROUND_NODATA: Final[str] = "UNKNOWN_BACKGROUND_NODATA"

SUPPORT_30M: Final[int] = 30
SUPPORT_10M: Final[int] = 10


class LabelKind(IntEnum):
    """Source representation kind."""

    BINARY_RASTER = 1
    POSITIVE_POLYGONS = 2


@dataclass(frozen=True)
class LabelSourcePolicy:
    """Predeclared adapter semantics for one frozen label source."""

    source_id: str
    family: str
    year: int
    kind: LabelKind
    supports_m: tuple[int, ...]
    positive_rule: str
    unknown_rule: str
    negative_semantics: str
    resampling: str
    registry_product_id: str

    @property
    def key(self) -> str:
        return f"{self.family}_{self.year}"


#: The exact (family, year) matrix authorised for pilot supports.
LABEL_SOURCES: Final[tuple[LabelSourcePolicy, ...]] = (
    LabelSourcePolicy(
        "geodata-1990", "GEODATA", 1990, LabelKind.BINARY_RASTER,
        (SUPPORT_30M,),
        "raster value 1 (VAT class) = Spartina",
        "raster value 255 is the file nodata/background; outside the "
        "raster data window = UNKNOWN_OUTSIDE_SOURCE_WINDOW",
        "in-window non-positive pixels classed PURE_NEGATIVE but treated "
        "as WEAK negatives: the product documents no verified-negative "
        "class (background/nodata 255)",
        "nearest neighbour, native 30 m",
        "GEODATA-SPARTINA-1990"),
    LabelSourcePolicy(
        "geodata-2000", "GEODATA", 2000, LabelKind.BINARY_RASTER,
        (SUPPORT_30M,),
        "raster value 1 (VAT class) = Spartina",
        "raster value 255 is the file nodata/background; outside the "
        "raster data window = UNKNOWN_OUTSIDE_SOURCE_WINDOW",
        "in-window non-positive pixels classed PURE_NEGATIVE but treated "
        "as WEAK negatives: the product documents no verified-negative "
        "class (background/nodata 255)",
        "nearest neighbour, native 30 m",
        "GEODATA-SPARTINA-2000"),
    LabelSourcePolicy(
        "geodata-2015", "GEODATA", 2015, LabelKind.BINARY_RASTER,
        (SUPPORT_30M,),
        "raster value 1 (VAT class) = Spartina",
        "raster value 255 is the file nodata/background; outside the "
        "raster data window = UNKNOWN_OUTSIDE_SOURCE_WINDOW",
        "in-window non-positive pixels classed PURE_NEGATIVE but treated "
        "as WEAK negatives: the product documents no verified-negative "
        "class (background/nodata 255)",
        "nearest neighbour, native 30 m; source EPSG:32650",
        "GEODATA-SPARTINA-2015"),
    LabelSourcePolicy(
        "geodata-2020", "GEODATA", 2020, LabelKind.BINARY_RASTER,
        (SUPPORT_30M,),
        "raster value 1 (VAT class 互花米草) = Spartina",
        "raster value 255 is the file nodata/background; outside the "
        "raster data window = UNKNOWN_OUTSIDE_SOURCE_WINDOW",
        "in-window non-positive pixels classed PURE_NEGATIVE but treated "
        "as WEAK negatives: the product documents no verified-negative "
        "class (background/nodata 255)",
        "nearest neighbour, native 30 m",
        "GEODATA-SPARTINA-2020-30M"),
    LabelSourcePolicy(
        "cmsa-2017", "CMSA", 2017, LabelKind.POSITIVE_POLYGONS,
        (SUPPORT_30M,),
        "polygon attribute gridcode == 2",
        "gridcode == 0 features burn UNKNOWN ("
        "UNKNOWN_GRIDCODE_ZERO_TODO_VERIFY); uncovered pixels are "
        "UNKNOWN_NO_VERIFIED_NEGATIVE_ENVELOPE (positive-only product)",
        "no PURE_NEGATIVE: polygons encode positives and uncertain "
        "gridcode-0 only",
        "exact polygon union area per 30 m pixel (make_valid derived "
        "copy; source untouched)",
        "NESDC-CMSA-2017"),
    LabelSourcePolicy(
        "cmsa-2018", "CMSA", 2018, LabelKind.POSITIVE_POLYGONS,
        (SUPPORT_30M,),
        "polygon attribute gridcode == 2",
        "gridcode == 0 features burn UNKNOWN ("
        "UNKNOWN_GRIDCODE_ZERO_TODO_VERIFY); uncovered pixels are "
        "UNKNOWN_NO_VERIFIED_NEGATIVE_ENVELOPE (positive-only product)",
        "no PURE_NEGATIVE: polygons encode positives and uncertain "
        "gridcode-0 only",
        "exact polygon union area per 30 m pixel (make_valid derived "
        "copy; source untouched)",
        "NESDC-CMSA-2018"),
    LabelSourcePolicy(
        "cmsa-2019", "CMSA", 2019, LabelKind.POSITIVE_POLYGONS,
        (SUPPORT_30M,),
        "polygon attribute gridcode == 2",
        "gridcode == 0 features burn UNKNOWN ("
        "UNKNOWN_GRIDCODE_ZERO_TODO_VERIFY); uncovered pixels are "
        "UNKNOWN_NO_VERIFIED_NEGATIVE_ENVELOPE (positive-only product)",
        "no PURE_NEGATIVE: polygons encode positives and uncertain "
        "gridcode-0 only",
        "exact polygon union area per 30 m pixel (make_valid derived "
        "copy; source untouched)",
        "NESDC-CMSA-2019"),
    LabelSourcePolicy(
        "cmsa-2020", "CMSA", 2020, LabelKind.POSITIVE_POLYGONS,
        (SUPPORT_30M,),
        "polygon attribute gridcode == 2",
        "gridcode == 0 features burn UNKNOWN ("
        "UNKNOWN_GRIDCODE_ZERO_TODO_VERIFY); uncovered pixels are "
        "UNKNOWN_NO_VERIFIED_NEGATIVE_ENVELOPE (positive-only product)",
        "no PURE_NEGATIVE: polygons encode positives and uncertain "
        "gridcode-0 only",
        "exact polygon union area per 30 m pixel (make_valid derived "
        "copy; source untouched)",
        "NESDC-CMSA-2020"),
    LabelSourcePolicy(
        "cmsa-2021", "CMSA", 2021, LabelKind.POSITIVE_POLYGONS,
        (SUPPORT_30M,),
        "polygon attribute gridcode == 2",
        "gridcode == 0 features burn UNKNOWN ("
        "UNKNOWN_GRIDCODE_ZERO_TODO_VERIFY); uncovered pixels are "
        "UNKNOWN_NO_VERIFIED_NEGATIVE_ENVELOPE (positive-only product)",
        "no PURE_NEGATIVE: polygons encode positives and uncertain "
        "gridcode-0 only",
        "exact polygon union area per 30 m pixel (make_valid derived "
        "copy; source untouched)",
        "NESDC-CMSA-2021"),
    LabelSourcePolicy(
        "cmssm-2020", "CM-SSM", 2020, LabelKind.POSITIVE_POLYGONS,
        (SUPPORT_10M, SUPPORT_30M),
        "all mapped polygons are Spartina positive (no gridcode field)",
        "uncovered pixels are UNKNOWN_NO_VERIFIED_NEGATIVE_ENVELOPE "
        "(positive-only product)",
        "no PURE_NEGATIVE: polygons encode positives only",
        "exact polygon union area per pixel (make_valid derived copy; "
        "source untouched)",
        "ZENODO-CM-SSM-2020"),
)

SOURCE_BY_KEY: Final[dict[str, LabelSourcePolicy]] = {
    s.key: s for s in LABEL_SOURCES}


def classify_fractions(
    fraction: np.ndarray[Any, Any], unknown: np.ndarray[Any, Any] | None = None,
) -> np.ndarray[Any, Any]:
    """Apply the predeclared thresholds to a fraction array.

    ``fraction`` is in [0, 1] occupancy. Where ``unknown`` is True the
    result is :class:`OccupancyClass.UNKNOWN` regardless of fraction
    (e.g. gridcode-0 regions, out-of-window pixels).
    """
    frac = np.asarray(fraction, dtype=np.float64)
    classes = np.full(frac.shape, OccupancyClass.UNKNOWN, dtype=np.uint8)
    weak_neg = (~np.isnan(frac)) & (frac <= PURE_LO)
    mixed = (~np.isnan(frac)) & (frac > PURE_LO) & (frac < PURE_HI)
    pure_pos = (~np.isnan(frac)) & (frac >= PURE_HI)
    classes[weak_neg] = OccupancyClass.PURE_NEGATIVE
    classes[mixed] = OccupancyClass.MIXED
    classes[pure_pos] = OccupancyClass.PURE_POSITIVE
    if unknown is not None:
        classes[np.asarray(unknown, dtype=bool)] = OccupancyClass.UNKNOWN
    return classes


def classify_positive_only_fractions(
    fraction: np.ndarray[Any, Any], unknown: np.ndarray[Any, Any] | None = None,
) -> np.ndarray[Any, Any]:
    """Classify fractions from a positive-only polygon product.

    CMSA and CM-SSM encode mapped Spartina polygons with NO verified
    negative envelope, so a low fraction cannot be read as a negative:

    * ``fraction >= PURE_HI`` -> PURE_POSITIVE,
    * any ``0 < fraction < PURE_HI`` -> MIXED (partial mapped cover; the
      rest of the pixel is unmapped, not verified non-Spartina),
    * ``fraction <= 0`` or NaN -> UNKNOWN
      (UNKNOWN_NO_VERIFIED_NEGATIVE_ENVELOPE),
    * ``unknown`` mask (e.g. CMSA gridcode 0) -> UNKNOWN, overriding
      everything.
    """
    frac = np.asarray(fraction, dtype=np.float64)
    classes = np.full(frac.shape, OccupancyClass.UNKNOWN, dtype=np.uint8)
    mapped = (~np.isnan(frac)) & (frac > 0)
    partial = mapped & (frac < PURE_HI)
    pure_pos = mapped & (frac >= PURE_HI)
    classes[partial] = OccupancyClass.MIXED
    classes[pure_pos] = OccupancyClass.PURE_POSITIVE
    if unknown is not None:
        classes[np.asarray(unknown, dtype=bool)] = OccupancyClass.UNKNOWN
    return classes


def class_counts(classes: np.ndarray[Any, Any]) -> dict[str, int]:
    """Count occupancy classes for manifest provenance."""
    arr = np.asarray(classes)
    return {
        "n_pure_positive":
            int(np.count_nonzero(arr == OccupancyClass.PURE_POSITIVE)),
        "n_mixed": int(np.count_nonzero(arr == OccupancyClass.MIXED)),
        "n_pure_negative":
            int(np.count_nonzero(arr == OccupancyClass.PURE_NEGATIVE)),
        "n_unknown": int(np.count_nonzero(arr == OccupancyClass.UNKNOWN)),
        "n_total": int(arr.size),
    }


def positive_area_km2(fraction: np.ndarray[Any, Any], pixel_area_m2: float,
                      unknown: np.ndarray[Any, Any] | None = None) -> float:
    """Sum positive occupancy area; NaN/unknown pixels contribute zero."""
    frac = np.asarray(fraction, dtype=np.float64)
    valid = ~np.isnan(frac)
    if unknown is not None:
        valid &= ~np.asarray(unknown, dtype=bool)
    area_m2 = float(np.nansum(np.where(valid, frac, 0.0)) * pixel_area_m2)
    return area_m2 / 1e6


def assert_repair_area_change(before_km2: float, after_km2: float,
                              tolerance: float = 0.01) -> None:
    """STOP guard for derived geometry repair (|area change| < 1%)."""
    if before_km2 <= 0:
        raise ValueError("positive area before repair must be positive")
    change = abs(after_km2 - before_km2) / before_km2
    if change >= tolerance:
        raise ValueError(
            f"geometry repair changed positive area by {change:.4%} "
            f">= {tolerance:.0%}; STOP per pilot label policy")


POLICY_DOC: Final[dict[str, object]] = {
    "adapter_version": ADAPTER_VERSION,
    "class_thresholds": {"pure_lo": PURE_LO, "pure_hi": PURE_HI},
    "classes": [c.name for c in OccupancyClass],
    "fractions_are": (
        "SILVER product occupancy summaries, not ground truth; never "
        "cite as accuracy"),
    "no_30m_to_10m": (
        "GEODATA and CMSA are never rasterized onto 10 m supports; "
        "CM-SSM supports 10 m and 30 m; CMSA 30 m per Issue #19 policy"),
    "cmsa_gridcode0": UNKNOWN_GRIDCODE_ZERO,
    "negative_semantics": (
        "no source provides verified negatives; GEODATA in-window "
        "background is a WEAK negative only; vector backgrounds remain "
        "UNKNOWN"),
    "positive_only_classification": (
        "positive-only polygon products never assign PURE_NEGATIVE: "
        "0 < fraction < 0.9 = MIXED, fraction = 0/NaN = UNKNOWN"),
    "source_repair": (
        "GeoDataFrame.make_valid() on derived copies only; |area "
        "change| < 1% asserted; source archives never modified"),
}

__all__ = [
    "ADAPTER_VERSION",
    "LABEL_SOURCES",
    "LabelKind",
    "LabelSourcePolicy",
    "OccupancyClass",
    "POLICY_DOC",
    "PURE_HI",
    "PURE_LO",
    "SOURCE_BY_KEY",
    "SUPPORT_10M",
    "SUPPORT_30M",
    "UNKNOWN_BACKGROUND_NODATA",
    "UNKNOWN_GRIDCODE_ZERO",
    "UNKNOWN_NO_VERIFIED_NEGATIVE_ENVELOPE",
    "UNKNOWN_OUTSIDE_SOURCE_WINDOW",
    "assert_repair_area_change",
    "class_counts",
    "classify_fractions",
    "classify_positive_only_fractions",
    "positive_area_km2",
]
