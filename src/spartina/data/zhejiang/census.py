"""Metadata-only multi-year EO observational census (M2.1a, Issue #7).

Two QA stages exist by contract:

* ``SCENE_METADATA``  - cheap: IDs, dates, tiles, orbit, scene-level cloud
  and a server-side *footprint* coverage fraction. This is what M2.1a runs.
* ``ROI_PIXEL_QA``    - per-scene reduceRegion ROI pixel statistics
  (S2 SCL policy ``s2_scl_qa_v1_1`` etc.). NOT run at M2.1a: the workload
  is reported and the stage waits for explicit approval.

Hard rule: this module must never call ``ee.batch.Export`` in any form.
The public runner installs :func:`install_export_guard` which replaces the
Export namespace with a raising object for the duration of the census;
tests inject a sentinel and fail if an export path is touched.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from spartina.data.gee.selection import canonical_fingerprint
from spartina.data.zhejiang.contracts import (
    CENSUS_SUMMARY_COLUMNS,
    GAP_NO_QUALITY,
    GAP_NO_SCENES,
    GAP_NONE,
    GAP_NOT_OPERATIONAL,
    QA_SCENE_METADATA,
    SLC_NA,
    SLC_POST_FAILURE,
    SLC_PRE_FAILURE,
)

SLC_FAILURE_DATE: str = "2003-05-31"


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------
def parse_utc(iso_utc: str) -> datetime | None:
    if not iso_utc:
        return None
    text = iso_utc.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None  # tz-aware is mandatory in this pipeline
    return dt.astimezone(UTC)


def is_operational(year: int, span: tuple[int, int]) -> bool:
    return span[0] <= year <= span[1]


def doy_in_window(doy: int | None, start: int, end: int) -> bool:
    if doy is None:
        return False
    return start <= doy <= end


def slc_status_for_date(iso_utc: str) -> str:
    dt = parse_utc(iso_utc)
    if dt is None:
        return SLC_NA
    failure = datetime.fromisoformat(SLC_FAILURE_DATE).replace(
        tzinfo=UTC)
    return SLC_POST_FAILURE if dt.date() >= failure.date() else SLC_PRE_FAILURE


def _sorted_join(values: Iterable[Any]) -> str:
    out = sorted({str(v) for v in values if v not in (None, "")})
    return "|".join(out)


def summarize_group(
    *,
    roi_id: str,
    year: int,
    sensor: str,
    collection_id: str,
    operational: bool,
    scenes: list[dict[str, Any]],
    retrieval_ts: str,
    season_windows: list[dict[str, Any]],
    scene_cloud_max: float,
    footprint_coverage_min: float,
    qa_level: str = QA_SCENE_METADATA,
) -> dict[str, Any]:
    """Aggregate one (roi, year, sensor) scene list into a summary row."""
    if not operational:
        row = _empty_summary(
            roi_id, year, sensor, collection_id, retrieval_ts)
        row["operational"] = False
        row["slc_status"] = (
            slc_year_label(year) if sensor == "landsat7" else SLC_NA)
        row["gap_status"] = GAP_NOT_OPERATIONAL
        row["query_status"] = "NOT_QUERIED_OUTSIDE_OPERATIONAL_YEARS"
        row["summary_fingerprint"] = _fingerprint(row)
        return row

    dates = {s.get("acquisition_utc", "")[:10]
             for s in scenes if s.get("acquisition_utc")}
    coverages = [s["footprint_coverage_fraction"] for s in scenes
                 if isinstance(s.get("footprint_coverage_fraction"), int | float)]
    cloud_ok = [
        s for s in scenes
        if sensor != "sentinel1"
        and isinstance(s.get("scene_cloud_fraction"), int | float)
        and s["scene_cloud_fraction"] <= scene_cloud_max
    ]
    coverage_ok = [
        s for s in scenes
        if isinstance(s.get("footprint_coverage_fraction"), int | float)
        and s["footprint_coverage_fraction"] >= footprint_coverage_min
    ]
    season_hits: set[str] = set()
    season_scenes = 0
    if sensor == "sentinel1":
        quality_ok = coverage_ok
    else:
        quality_ok = [s for s in scenes if s in coverage_ok and s in cloud_ok]
    for s in quality_ok:
        window_ids = [
            w["id"] for w in season_windows
            if doy_in_window(s.get("day_of_year"),
                             int(w["doy_start"]), int(w["doy_end"]))
        ]
        if window_ids:
            season_scenes += 1
            season_hits.update(window_ids)

    total = len(scenes)
    if total == 0:
        gap = GAP_NO_SCENES
    elif not quality_ok:
        # optical: need the SAME scene to be both full-coverage and clear;
        # SAR: coverage_ok alone (cloud_ok is empty/irrelevant)
        gap = GAP_NO_QUALITY
    else:
        gap = GAP_NONE

    slc = SLC_NA
    if sensor == "landsat7":
        statuses = {slc_status_for_date(s.get("acquisition_utc", ""))
                    for s in scenes if s.get("acquisition_utc")}
        statuses.discard(SLC_NA)
        slc = (next(iter(statuses)) if len(statuses) == 1
               else "|".join(sorted(statuses)) if statuses else SLC_NA)

    row = {
        "roi_id": roi_id,
        "year": year,
        "sensor": sensor,
        "collection_id": collection_id,
        "operational": True,
        "slc_status": slc,
        "qa_level": qa_level,
        "total_scenes": total,
        "distinct_acquisition_dates": len(dates),
        "scenes_ascending": sum(1 for s in scenes
                                if s.get("orbit_direction") == "ASCENDING"),
        "scenes_descending": sum(1 for s in scenes
                                 if s.get("orbit_direction") == "DESCENDING"),
        "tile_refs": _sorted_join(s.get("tile_ref") for s in scenes),
        "spacecraft_names": _sorted_join(s.get("spacecraft") for s in scenes),
        "processing_baselines": _sorted_join(
            s.get("processing_baseline") for s in scenes),
        "scene_cloud_eligible_scenes": (
            len(cloud_ok) if sensor != "sentinel1" else None),
        "footprint_coverage_eligible_scenes": len(coverage_ok),
        "season_candidate_scenes": season_scenes,
        "season_candidate_window_ids": "|".join(sorted(season_hits)),
        # ROI pixel QA is deliberately not executed at M2.1a.
        "quality_candidate_scenes": None,
        "best_footprint_coverage": (
            round(max(coverages), 6) if coverages else None),
        "gap_status": gap,
        "query_status": "QUERIED",
        "metadata_retrieval_timestamp": retrieval_ts,
        "summary_fingerprint": "",
    }
    row["summary_fingerprint"] = _fingerprint(row)
    return row


def slc_year_label(year: int) -> str:
    if year < 2003:
        return SLC_PRE_FAILURE
    if year > 2003:
        return SLC_POST_FAILURE
    return "MIXED_2003_SLC_FAILURE_YEAR"


def _empty_summary(roi_id: str, year: int, sensor: str,
                   collection_id: str, retrieval_ts: str) -> dict[str, Any]:
    return {
        "roi_id": roi_id, "year": year, "sensor": sensor,
        "collection_id": collection_id,
        "operational": False, "slc_status": SLC_NA,
        "qa_level": QA_SCENE_METADATA, "total_scenes": 0,
        "distinct_acquisition_dates": 0,
        "scenes_ascending": 0, "scenes_descending": 0,
        "tile_refs": "", "spacecraft_names": "",
        "processing_baselines": "",
        "scene_cloud_eligible_scenes": None,
        "footprint_coverage_eligible_scenes": 0,
        "season_candidate_scenes": 0,
        "season_candidate_window_ids": "",
        "quality_candidate_scenes": None,
        "best_footprint_coverage": None,
        "gap_status": GAP_NOT_OPERATIONAL,
        "query_status": "",
        "metadata_retrieval_timestamp": retrieval_ts,
        "summary_fingerprint": "",
    }


def _fingerprint(row: dict[str, Any]) -> str:
    return canonical_fingerprint(
        {k: v for k, v in row.items() if k != "summary_fingerprint"}
    )


# --------------------------------------------------------------------------
# EE interaction (metadata only) + export guard
# --------------------------------------------------------------------------
class ExportAttempted(RuntimeError):
    """Raised if any code path touches ee.batch.Export during the census."""


class _BlockedExport:
    def __getattr__(self, name: str) -> Any:
        raise ExportAttempted(
            f"ee.batch.Export.{name} is forbidden in M2.1a metadata census")


def install_export_guard(ee: Any) -> Any:
    """Replace ``ee.batch.Export`` with a raising sentinel; return restorer."""
    batch = ee.batch
    original = getattr(batch, "Export", None)
    batch.Export = _BlockedExport()

    def restore() -> None:
        batch.Export = original

    return restore


@dataclass(frozen=True)
class GroupQuery:
    roi_id: str
    year: int
    sensor: str
    collection_id: str


def _ee_geometry(ee: Any, geometry: Any, scale_m: float) -> Any:
    return ee.Geometry(_as_geojson(geometry))


def _as_geojson(geometry: Any) -> dict[str, Any]:
    from shapely.geometry import mapping
    return dict(mapping(geometry))


def query_group_scenes(
    ee: Any,
    *,
    geometry: Any,
    query: GroupQuery,
    coverage_scale_m: float,
) -> list[dict[str, Any]]:
    """One getInfo per group: scene metadata + ROI footprint coverage."""
    roi = _ee_geometry(ee, geometry, coverage_scale_m)
    roi_area = roi.area(coverage_scale_m)
    collection = (
        ee.ImageCollection(query.collection_id)
        .filterBounds(roi)
        .filterDate(f"{query.year}-01-01", f"{query.year + 1}-01-01")
    )

    def annotate(image: Any) -> Any:
        props = {
            "t": image.date().format("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"),
            "id": image.id(),
            "cov": (image.geometry(coverage_scale_m)
                    .intersection(roi, coverage_scale_m)
                    .area(coverage_scale_m).divide(roi_area)),
        }
        sensor = query.sensor
        if sensor.startswith("landsat"):
            props.update({
                "cld": image.get("CLOUD_COVER"),
                "tile": (ee.String(
                    image.get("WRS_PATH")).cat("/")
                    .cat(ee.String(image.get("WRS_ROW")))),
                "sc": image.get("SPACECRAFT_ID"),
            })
        elif sensor == "sentinel2":
            props.update({
                "cld": image.get("CLOUDY_PIXEL_PERCENTAGE"),
                "tile": image.get("MGRS_TILE"),
                "sc": image.get("SPACECRAFT_NAME"),
                "bl": image.get("PROCESSING_BASELINE"),
                "orbit": image.get("orbitProperties_pass"),
            })
        else:  # sentinel1
            props.update({
                "orbit": image.get("orbitProperties_pass"),
                "rel": image.get("relativeOrbitNumber_start"),
                "mode": image.get("instrumentMode"),
                "pol": image.get("transmitterReceiverPolarisation"),
                "sc": image.get("platform_number"),
            })
        return ee.Feature(None, props)

    payload = collection.map(annotate).getInfo()
    return [_scene_row(query, f) for f in payload.get("features", [])]


def _scene_row(query: GroupQuery, feature: dict[str, Any]) -> dict[str, Any]:
    p = feature.get("properties", {}) or {}
    iso_utc = p.get("t") or ""
    dt = parse_utc(iso_utc)
    cov = p.get("cov")
    cld = p.get("cld")
    return {
        "roi_id": query.roi_id,
        "year": query.year,
        "sensor": query.sensor,
        "collection_id": query.collection_id,
        "scene_id": p.get("id"),
        "acquisition_utc": iso_utc,
        "day_of_year": int(dt.timetuple().tm_yday) if dt else None,
        "tile_ref": _normalize_tile_ref(p.get("tile"), query.sensor),
        "orbit_direction": p.get("orbit"),
        "relative_orbit_number": p.get("rel"),
        "instrument_mode": p.get("mode"),
        "polarizations": (
            "|".join(p["pol"]) if isinstance(p.get("pol"), list)
            else p.get("pol")),
        "spacecraft": p.get("sc"),
        "processing_baseline": p.get("bl"),
        "slc_status": (
            slc_status_for_date(iso_utc)
            if query.sensor == "landsat7" else SLC_NA),
        "scene_cloud_fraction": (
            round(float(cld) / 100.0, 6)
            if isinstance(cld, int | float) else None),
        "footprint_coverage_fraction": (
            round(float(cov), 6) if isinstance(cov, int | float) else None),
        "metadata_retrieval_timestamp": "",
    }


_FLOAT_PATH_ROW = re.compile(r"^(\d+)\.0/(\d+)\.0$")


def _normalize_tile_ref(value: Any, sensor: str) -> Any:
    if isinstance(value, str) and sensor.startswith("landsat"):
        m = _FLOAT_PATH_ROW.match(value)
        if m:
            return f"{int(m.group(1)):03d}/{int(m.group(2)):03d}"
    return value


SUMMARY_COLUMN_ORDER: tuple[str, ...] = tuple(CENSUS_SUMMARY_COLUMNS)
