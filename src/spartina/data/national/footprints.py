"""Static acquisition-footprint indices and sensor-era rules (Issue #16).

Two *nominal* grid systems are indexed as cheap spatial prefilters:

* WRS-2 descending path/row polygons for Landsat 5/7/8/9 (USGS public
  domain shapefile);
* MGRS 100 km tile squares for Sentinel-1/2 (computed from the MGRS
  standard via the ``mgrs`` package).

Nominal frames are never the final eligibility gate. Sentinel-1 uses
actual per-scene geometry, and Landsat 7 scenes from the Extended
Science Mission (2022-05-05 onward) drift off the WRS-2 grid and must be
joined with their own scene geometry (see :data:`L7_ERAS`).

Era boundaries are taken from USGS mission documentation
(https://www.usgs.gov/landsat-missions/landsat-7-extended-science-mission
and https://www.usgs.gov/landsat-missions/landsat-7).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Final

from shapely import to_wkb
from shapely.geometry.base import BaseGeometry

# --- sensor keys (consistent with gee.collections) -----------------------

LANDSAT5: Final[str] = "landsat5"
LANDSAT7: Final[str] = "landsat7"
LANDSAT8: Final[str] = "landsat8"
LANDSAT9: Final[str] = "landsat9"
SENTINEL1: Final[str] = "sentinel1"
SENTINEL2: Final[str] = "sentinel2"

LANDSAT_SENSORS: Final[tuple[str, ...]] = (
    LANDSAT5,
    LANDSAT7,
    LANDSAT8,
    LANDSAT9,
)


@dataclass(frozen=True)
class NominalWindow:
    """Nominal operational window (observed coverage comes from census)."""

    start: date
    end: date | None
    note: str


# Nominal mission windows (coarse, UTC dates); per-path/row observed
# coverage years are filled by the executed census, never assumed.
NOMINAL_WINDOWS: Final[dict[str, NominalWindow]] = {
    LANDSAT5: NominalWindow(
        date(1984, 3, 1),
        date(2013, 6, 5),
        "Landsat 5 TM: launch 1984-03-01; decommissioned 2013-06-05; "
        "acquisition gap ~2011-11-18 to 2012-05-10 (X-band transmitter)",
    ),
    LANDSAT7: NominalWindow(
        date(1999, 4, 15),
        date(2024, 1, 19),
        "Landsat 7 ETM+: launch 1999-04-15; WRS-2 nominal science until "
        "2022-04-05; Extended Science Mission from 2022-05-05; imaging "
        "suspended 2024-01-19; decommissioned 2025-06-04",
    ),
    LANDSAT8: NominalWindow(
        date(2013, 2, 11),
        None,
        "Landsat 8 OLI: launch/first light 2013-02-11; operational",
    ),
    LANDSAT9: NominalWindow(
        date(2021, 9, 27),
        None,
        "Landsat 9 OLI-2: launch 2021-09-27; public products from 2022-02",
    ),
    SENTINEL1: NominalWindow(
        date(2014, 10, 3),
        None,
        "Sentinel-1A IW GRD on GEE from ~2014-10; 1B 2016-2021",
    ),
    SENTINEL2: NominalWindow(
        date(2015, 6, 27),
        None,
        "Sentinel-2A from 2015-06-27; 2B from 2017-07; L1C/L2A on GEE",
    ),
}

# --- Landsat 7 era taxonomy (UTC dates, inclusive as documented) ---------

L7_SLC_FAILURE: Final[date] = date(2003, 5, 31)
L7_NOMINAL_END: Final[date] = date(2022, 4, 5)
L7_EXTENDED_RESUME: Final[date] = date(2022, 5, 5)

L7_PRE_SLC_FAILURE: Final[str] = "L7_PRE_SLC_FAILURE"
L7_POST_SLC_FAILURE: Final[str] = "L7_POST_SLC_FAILURE"
L7_STANDBY_ORBIT_LOWERING: Final[str] = "L7_STANDBY_ORBIT_LOWERING"
L7_EXTENDED_SCIENCE_MISSION: Final[str] = "L7_EXTENDED_SCIENCE_MISSION"

#: Eras during which the nominal WRS-2 polygon is the correct frame.
L7_NOMINAL_WRS2_ERAS: Final[frozenset[str]] = frozenset(
    {L7_PRE_SLC_FAILURE, L7_POST_SLC_FAILURE}
)


def l7_era(when: datetime | date) -> str:
    """Classify a Landsat 7 acquisition date into its mission era."""
    day = when.date() if isinstance(when, datetime) else when
    if day < L7_SLC_FAILURE:
        return L7_PRE_SLC_FAILURE
    if day <= L7_NOMINAL_END:
        return L7_POST_SLC_FAILURE
    if day < L7_EXTENDED_RESUME:
        return L7_STANDBY_ORBIT_LOWERING
    return L7_EXTENDED_SCIENCE_MISSION


def l7_footprint_is_nominal_wrs2(when: datetime | date) -> bool:
    """True only when the scene is guaranteed on the WRS-2 nominal frame.

    Extended Science Mission scenes drift relative to WRS-2; callers must
    join them using the scene's own geometry.
    """
    return l7_era(when) in L7_NOMINAL_WRS2_ERAS


# --- sensor-era status for cell x year x sensor census -------------------

SENSOR_NOT_OPERATIONAL: Final[str] = "SENSOR_NOT_OPERATIONAL"
NO_SCENES_FOUND: Final[str] = "NO_SCENES_FOUND"
NO_CELL_INTERSECTION: Final[str] = "NO_CELL_INTERSECTION"
METADATA_AVAILABLE: Final[str] = "METADATA_AVAILABLE"
QUERY_FAILED: Final[str] = "QUERY_FAILED"

CELL_YEAR_STATUS: Final[tuple[str, ...]] = (
    SENSOR_NOT_OPERATIONAL,
    NO_SCENES_FOUND,
    NO_CELL_INTERSECTION,
    METADATA_AVAILABLE,
    QUERY_FAILED,
)


def sensor_operational(sensor: str, year: int) -> bool:
    """Whether ``sensor`` was nominally operational at any point in year."""
    window = NOMINAL_WINDOWS[sensor]
    if year < window.start.year:
        return False
    return not (
        year < window.start.year
        or (window.end is not None and year > window.end.year)
    )


# --- deterministic geometry fingerprints ---------------------------------

def geometry_fingerprint(geometry: BaseGeometry) -> str:
    """SHA-256 of canonical big-endian 2D WKB (no SRID)."""
    wkb = to_wkb(geometry, hex=False, output_dimension=2, byte_order=0, include_srid=False)
    return hashlib.sha256(bytes(wkb)).hexdigest()


def wrs2_frame_id(path: int, row: int) -> str:
    """Deterministic nominal-frame identifier, e.g. ``WRS2-D-P118-R039``."""
    if not 1 <= path <= 233:
        raise ValueError(f"WRS-2 path out of range: {path}")
    if not 1 <= row <= 248:
        raise ValueError(f"WRS-2 row out of range: {row}")
    return f"WRS2-D-P{path:03d}-R{row:03d}"


def utc_now_iso() -> str:
    """UTC timestamp helper (kept here so callers stay timezone-aware)."""
    return datetime.now(UTC).isoformat(timespec="seconds")
