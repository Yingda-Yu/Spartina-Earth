"""Deterministic scene/event rows for the national metadata census.

The national census caches one row per *scene/granule* returned by GEE:

* Landsat: WRS-2 path/row scene (Tier 1 L2 Collection 2);
* Sentinel-2: one granule (``system:index``/PRODUCT_ID). Granules are
  never grouped across dates; datatake composition happens only in the
  local cell-event join, where every ObservationEvent keeps the member
  granules and their distinct UTC datetimes;
* Sentinel-1: one GRD scene with pass/relative orbit and the hash of its
  actual GEE footprint geometry.

All timestamps are timezone-aware UTC. Event identifiers are
content-deterministic from sensor + source scene id.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime

from spartina.data.national.footprints import l7_era

AUTUMN_PRIMARY_V1_DOY_START = 260
AUTUMN_PRIMARY_V1_DOY_END = 320
AUTUMN_PRIMARY_V1 = "AUTUMN_PRIMARY_V1_CANDIDATE"
OTHER_SEASON = "OTHER_SEASON_FULL_YEAR"

LANDSAT_SENSORS = ("landsat5", "landsat7", "landsat8", "landsat9")


def event_id(sensor: str, source_scene_id: str) -> str:
    digest = hashlib.sha256(f"{sensor}|{source_scene_id}".encode()).hexdigest()
    prefix = "EVT-S2" if sensor == "sentinel2" else "EVT-S1" if sensor == "sentinel1" else "EVT-L"
    return f"{prefix}-{digest[:16]}"


def utc_from_epoch_ms(value: object) -> datetime | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, int | float | str):
        return None
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def utc_from_scene_center(value: object, date_only: object = None) -> datetime | None:
    """Parse C02 SCENE_CENTRE_TIME (ISO Z) with DATE_ACQUIRED fallback."""
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = None
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    if isinstance(date_only, str) and len(date_only) >= 10:
        try:
            day = date.fromisoformat(date_only[:10])
        except ValueError:
            return None
        return datetime(day.year, day.month, day.day, tzinfo=UTC)
    return None


def season_tag(when: datetime | date) -> str:
    day = when.date() if isinstance(when, datetime) else when
    doy = day.timetuple().tm_yday
    if AUTUMN_PRIMARY_V1_DOY_START <= doy <= AUTUMN_PRIMARY_V1_DOY_END:
        return AUTUMN_PRIMARY_V1
    return OTHER_SEASON


@dataclass(frozen=True)
class LandsatScene:
    sensor: str
    scene_id: str  # LANDSAT_SCENE_ID
    product_id: str | None
    utc: datetime
    utc_precision: str  # SECOND | DAY_FALLBACK
    path: int
    row: int
    cloud_cover: float | None
    cloud_cover_land: float | None
    l7_era: str | None
    season_tag: str
    doy: int

    def to_row(self) -> dict[str, object]:
        return {
            "event_id": event_id(self.sensor, self.scene_id),
            "sensor": self.sensor,
            "scene_id": self.scene_id,
            "product_id": self.product_id,
            "utc": self.utc.isoformat(),
            "utc_precision": self.utc_precision,
            "year": self.utc.year,
            "doy": self.doy,
            "season_tag": self.season_tag,
            "wrs_path": self.path,
            "wrs_row": self.row,
            "frame_id": f"WRS2-D-P{self.path:03d}-R{self.row:03d}",
            "cloud_cover": self.cloud_cover,
            "cloud_cover_land": self.cloud_cover_land,
            "l7_era": self.l7_era,
        }


def landsat_scene_from_props(sensor: str, props: dict[str, object]) -> LandsatScene | None:
    scene_id = props.get("LANDSAT_SCENE_ID") or props.get("system:index")
    if not isinstance(scene_id, str) or not scene_id:
        return None
    path, row = props.get("WRS_PATH"), props.get("WRS_ROW")
    if not isinstance(path, int) or not isinstance(row, int):
        return None
    utc = utc_from_scene_center(
        props.get("SCENE_CENTER_TIME"), props.get("DATE_ACQUIRED")
    )
    if utc is None:
        return None
    precision = (
        "SECOND" if isinstance(props.get("SCENE_CENTER_TIME"), str) else "DAY_FALLBACK"
    )

    def _num(key: str) -> float | None:
        val = props.get(key)
        return float(val) if isinstance(val, int | float) else None

    return LandsatScene(
        sensor=sensor,
        scene_id=scene_id,
        product_id=(
            landsat_pid
            if isinstance(landsat_pid := props.get("LANDSAT_PRODUCT_ID"), str)
            else None
        ),
        utc=utc,
        utc_precision=precision,
        path=path,
        row=row,
        cloud_cover=_num("CLOUD_COVER"),
        cloud_cover_land=_num("CLOUD_COVER_LAND"),
        l7_era=l7_era(utc) if sensor == "landsat7" else None,
        season_tag=season_tag(utc),
        doy=utc.timetuple().tm_yday,
    )


@dataclass(frozen=True)
class Sentinel2Granule:
    system_index: str
    product_id: str | None
    datatake_identifier: str
    mgrs_tile: str
    spacecraft: str | None
    utc: datetime
    cloudy_pixel_percent: float | None
    cloudy_over_land_percent: float | None
    season_tag: str
    doy: int

    def to_row(self) -> dict[str, object]:
        return {
            "event_id": event_id("sentinel2", self.system_index),
            "sensor": "sentinel2",
            "system_index": self.system_index,
            "product_id": self.product_id,
            "datatake_identifier": self.datatake_identifier,
            "mgrs_tile": self.mgrs_tile,
            "spacecraft_name": self.spacecraft,
            "utc": self.utc.isoformat(),
            "year": self.utc.year,
            "doy": self.doy,
            "season_tag": self.season_tag,
            "cloudy_pixel_percent": self.cloudy_pixel_percent,
            "cloudy_over_land_percent": self.cloudy_over_land_percent,
            "geometry_basis": "NOMINAL_MGRS_PREFILTER",
            "actual_scene_geometry": "NOT_FETCHED_NATIONAL_SEE_PIXEL_PILOT",
        }


def s2_granule_from_props(props: dict[str, object]) -> Sentinel2Granule | None:
    system_index = props.get("system:index")
    datatake = props.get("DATATAKE_IDENTIFIER")
    tile = props.get("MGRS_TILE")
    if not all(isinstance(v, str) and v for v in (system_index, datatake, tile)):
        return None
    assert isinstance(system_index, str) and isinstance(datatake, str)
    assert isinstance(tile, str)
    utc = utc_from_epoch_ms(props.get("system:time_start"))
    if utc is None:
        return None

    def _num(key: str) -> float | None:
        val = props.get(key)
        return float(val) if isinstance(val, int | float) else None

    product_id = props.get("PRODUCT_ID")
    spacecraft = props.get("SPACECRAFT_NAME")
    return Sentinel2Granule(
        system_index=system_index,
        product_id=product_id if isinstance(product_id, str) else None,
        datatake_identifier=datatake,
        mgrs_tile=tile,
        spacecraft=spacecraft if isinstance(spacecraft, str) else None,
        utc=utc,
        cloudy_pixel_percent=_num("CLOUDY_PIXEL_PERCENTAGE"),
        cloudy_over_land_percent=_num("CLOUDY_PIXEL_OVER_LAND_PERCENTAGE"),
        season_tag=season_tag(utc),
        doy=utc.timetuple().tm_yday,
    )


@dataclass(frozen=True)
class Sentinel1Scene:
    scene_id: str  # system:index
    utc: datetime
    pass_name: str  # ASC | DESC
    relative_orbit: int
    orbit_start: int
    platform: str  # Sentinel-1A / Sentinel-1B
    polarization: str  # VV|VH sorted join
    instrument_mode: str | None
    footprint_sha256: str
    season_tag: str
    doy: int

    def to_manifest_row(self) -> dict[str, object]:
        """Tracked manifest row: identity + bounds/hash only, no geometry."""
        return {
            "event_id": event_id("sentinel1", self.scene_id),
            "sensor": "sentinel1",
            "scene_id": self.scene_id,
            "utc": self.utc.isoformat(),
            "year": self.utc.year,
            "doy": self.doy,
            "season_tag": self.season_tag,
            "pass": self.pass_name,
            "relative_orbit": self.relative_orbit,
            "orbit_start": self.orbit_start,
            "platform": self.platform,
            "polarization": self.polarization,
            "instrument_mode": self.instrument_mode,
            "footprint_sha256": self.footprint_sha256,
        }


def _platform_s1(platform_number: object) -> str | None:
    if platform_number == "A":
        return "Sentinel-1A"
    if platform_number == "B":
        return "Sentinel-1B"
    if platform_number == "C":
        return "Sentinel-1C"
    if isinstance(platform_number, str) and platform_number.startswith("Sentinel-1"):
        return platform_number
    return None


def s1_scene_from_props(
    props: dict[str, object], footprint_sha256: str
) -> Sentinel1Scene | None:
    """Parse one S1 feature produced by the batched geometry census.

    ``props`` mirrors GEE S1_GRD metadata plus our injected footprint hash.
    """
    scene_id = props.get("system:index")
    if not isinstance(scene_id, str) or not scene_id:
        return None
    utc = utc_from_epoch_ms(props.get("system:time_start"))
    if utc is None:
        return None
    relative_orbit = props.get("relativeOrbitNumber_start")
    orbit_start = props.get("orbitNumber_start")
    if not isinstance(relative_orbit, int) or isinstance(relative_orbit, bool):
        return None
    if not isinstance(orbit_start, int) or isinstance(orbit_start, bool):
        return None
    pass_value = props.get("orbitProperties_pass")
    pass_name = (
        "ASC" if pass_value == "ASCENDING"
        else "DESC" if pass_value == "DESCENDING"
        else None
    )
    platform = _platform_s1(props.get("platform_number"))
    if pass_name is None or platform is None:
        return None
    pol = props.get("transmitterReceiverPolarisation")
    if not isinstance(pol, list) or not all(isinstance(v, str) for v in pol):
        return None
    polarization = "|".join(sorted(pol))
    mode = props.get("instrumentMode")
    return Sentinel1Scene(
        scene_id=scene_id,
        utc=utc,
        pass_name=pass_name,
        relative_orbit=relative_orbit,
        orbit_start=orbit_start,
        platform=platform,
        polarization=polarization,
        instrument_mode=mode if isinstance(mode, str) else None,
        footprint_sha256=footprint_sha256,
        season_tag=season_tag(utc.date()),
        doy=utc.timetuple().tm_yday,
    )
