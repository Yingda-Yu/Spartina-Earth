"""National EO metadata census design and pure summarizers (section 37-40).

Execution rule inherited from the #13 finding (sections 38-39):

* the *only* server-side traffic is a small number of **batch aggregate**
  calls over the dissolved national corridor geometry (one per sensor,
  never one ``getInfo`` per cell or scene);
* nominal WRS/MGRS frames are a cheap prefilter -- production
  eligibility must use actual contributing source geometry (the
  Sentinel-1 geometry cache in particular).

The GEE-touching executor lives in ``scripts/data/national/eo_census.py``
behind the ``gee_integration`` pytest marker so offline runs need no
credentials.  This module holds sensor specs, the batch contract and the
local frame-join summarizers that are unit-testable without GEE.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class Sensor(str, Enum):
    L5 = "L5"
    L7 = "L7"
    L8 = "L8"
    L9 = "L9"
    S1 = "S1"
    S2 = "S2"


@dataclass(frozen=True)
class SensorSpec:
    """Batch census contract for one sensor family."""

    sensor: Sensor
    gee_collection: str
    start_year: int
    end_year: int
    nominal_frame_system: str
    nominal_frame_key_property: str
    batch_aggregated_properties: tuple[str, ...]
    actual_geometry_required: bool
    notes: str


# Collection IDs are the same verified interfaces used by the Zhejiang
# pilots; nominal keys identify the prefilter frame only.
SENSOR_SPECS: Final[tuple[SensorSpec, ...]] = (
    SensorSpec(
        Sensor.L5,
        "LANDSAT/LT05/C02/T1_L2",
        1984,
        2012,
        "WRS2_DESCENDING",
        "WRS_PATH+WRS_ROW",
        ("LANDSAT_SCENE_ID", "DATE_ACQUIRED", "WRS_PATH", "WRS_ROW"),
        False,
        "Level-2 Collection 2; path/row footprints via WRS-2 index",
    ),
    SensorSpec(
        Sensor.L7,
        "LANDSAT/LE07/C02/T1_L2",
        1999,
        2026,
        "WRS2_DESCENDING",
        "WRS_PATH+WRS_ROW",
        ("LANDSAT_SCENE_ID", "DATE_ACQUIRED", "WRS_PATH", "WRS_ROW"),
        False,
        "SLC-off after May 2003 must be flagged as a quality status",
    ),
    SensorSpec(
        Sensor.L8,
        "LANDSAT/LC08/C02/T1_L2",
        2013,
        2026,
        "WRS2_DESCENDING",
        "WRS_PATH+WRS_ROW",
        ("LANDSAT_SCENE_ID", "DATE_ACQUIRED", "WRS_PATH", "WRS_ROW"),
        False,
        "Collection 2 Tier 1 Level-2",
    ),
    SensorSpec(
        Sensor.L9,
        "LANDSAT/LC09/C02/T1_L2",
        2022,
        2026,
        "WRS2_DESCENDING",
        "WRS_PATH+WRS_ROW",
        ("LANDSAT_SCENE_ID", "DATE_ACQUIRED", "WRS_PATH", "WRS_ROW"),
        False,
        "Operational from late 2021; national coverage from 2022",
    ),
    SensorSpec(
        Sensor.S1,
        "COPERNICUS/S1_GRD",
        2014,
        2026,
        "S1_NOMINAL_FRAME",
        "relativeOrbitNumber_start",
        (
            "system:index",
            "relativeOrbitNumber_start",
            "orbitProperties_pass",
        ),
        True,
        (
            "No MGRS/WRS equivalent; nominal frames biased (the #13 "
            "171/105 finding). Per-frame actual footprint cache required "
            "before per-cell eligibility."
        ),
    ),
    SensorSpec(
        Sensor.S2,
        "COPERNICUS/S2_SR_HARMONIZED",
        2015,
        2026,
        "MGRS_TILE",
        "MGRS_TILE",
        ("PRODUCT_ID", "DATATAKE_IDENTIFIER", "MGRS_TILE", "GENERATION_TIME"),
        True,
        "MGRS tile is a prefilter; multi-tile datatakes join on "
        "DATATAKE_IDENTIFIER (the #13 3-datatake finding); actual "
        "contributing tile geometry required for eligibility",
    ),
)


def summarize_frame_rows(
    rows: tuple[tuple[int, str], ...],
) -> dict[int, dict[str, object]]:
    """Summarise ``(year, nominal_frame_id)`` batch rows locally.

    Output per year: total scenes, distinct nominal frames, sorted frame
    list.  This is the local spatial-index join half of the census and
    never touches GEE.
    """
    per_year: dict[int, list[str]] = {}
    for year, frame in rows:
        per_year.setdefault(year, []).append(frame)
    summary: dict[int, dict[str, object]] = {}
    for year in sorted(per_year):
        frames = per_year[year]
        summary[year] = {
            "total_scenes": len(frames),
            "distinct_nominal_frames": len(set(frames)),
            "frames": sorted(set(frames)),
        }
    return summary


def cell_year_sensor_records(
    frame_year_counts: dict[str, dict[int, int]],
) -> dict[str, dict[str, int]]:
    """Join frame-index coverage into a cell x year x sensor count table.

    ``frame_year_counts`` maps nominal frame id to {year: scene_count};
    cells are joined to frame ids via the static WRS/MGRS indexes.  The
    output is the metadata-only Tier 0 census; quality-status levels
    (season candidates, cloud/VALID gate, actual geometry) are applied
    downstream, never inferred here.
    """
    out: dict[str, dict[str, int]] = {}
    for frame, year_counts in frame_year_counts.items():
        for year, count in year_counts.items():
            out.setdefault(str(year), {})
            out[str(year)][frame] = (
                out[str(year)].get(frame, 0) + count
            )
    return out


def assert_batch_contract(spec: SensorSpec) -> None:
    """Guard the executor against per-scene getInfo growth."""
    if not spec.batch_aggregated_properties:
        raise ValueError("batch census requires aggregated properties")
    if spec.sensor is Sensor.S1 and not spec.actual_geometry_required:
        raise ValueError("Sentinel-1 census must flag actual geometry")
