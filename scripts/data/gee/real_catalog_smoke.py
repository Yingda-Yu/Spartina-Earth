#!/usr/bin/env python
"""Real Earth Engine catalog smoke for the Hangzhou Bay technical ROI.

Issue #6 integration gate (metadata only -- this script NEVER exports
pixels). It runs real L8 / S1 / S2 queries over the fixed historical
window 2020-09-01..2020-11-01 (target DOY 275), computes ROI-level raster
quality COUNTS inside EE, retains EVERY candidate scene (the selected
scene is explicit), ranks deterministically, and runs the whole query a
second time to produce catalog/selection fingerprints.

Outputs (gitignored bytes/JSON; tracked evidence lives in
docs/data/GEE_REAL_QUERY_SMOKE.md and tests/fixtures/gee/):

    artifacts/gee/real_smoke/candidate_scenes_real_smoke_v1.parquet
    artifacts/gee/real_smoke/candidate_scenes_real_smoke_v1.csv
    artifacts/gee/real_smoke/candidate_scenes_real_smoke_v1.json
    artifacts/gee/real_smoke/run_summary_real_smoke_v1.json

The 0.02-degree box HZB_TECH_SMOKE_V1 is a *technical smoke ROI* near the
northern Hangzhou Bay coast. It is NOT the Hangzhou Bay authoritative /
administrative / ecological boundary (see
docs/data/ZHEJIANG_DATA_PREPARATION_V0.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.data.gee import landsat, pixelqa, sentinel1, sentinel2  # noqa: E402
from spartina.data.gee.auth import PROJECT_ENV_VAR, configured_project, initialize  # noqa: E402
from spartina.data.gee.catalog import _bbox_from_feature, epoch_ms_to_iso  # noqa: E402
from spartina.data.gee.collections import COLLECTIONS  # noqa: E402
from spartina.data.gee.selection import (  # noqa: E402
    REASON_SAR_MISSING_POLS,
    REASON_SAR_NOT_IW,
    SingleScenePolicy,
    best_per_sar_pass,
    canonical_fingerprint,
    rank_eligibles,
    rejection_reasons,
)

# ---------------------------------------------------------------------------
# Fixed, predeclared smoke configuration (do not widen after seeing results)
# ---------------------------------------------------------------------------

ROI_ID = "HZB_TECH_SMOKE_V1"
ROI_GEOMETRY: dict[str, object] = {
    "type": "Polygon",
    "coordinates": [[
        [121.10, 30.30], [121.12, 30.30], [121.12, 30.32],
        [121.10, 30.32], [121.10, 30.30]]],
}
ROI_CRS_EPSG = 4326
ROI_NOTE = (
    "technical verification box near the northern Hangzhou Bay coast; "
    "NOT the Hangzhou Bay authoritative/administrative/ecological "
    "boundary; formal Issue #7 ROIs require separate provenance")

DEFAULT_START = "2020-09-01T00:00:00Z"
DEFAULT_END = "2020-11-01T00:00:00Z"
DEFAULT_TARGET_DOY = 275  # 1 October, autumn Spartina window (planning v0)
SMOKE_VERSION = "real_smoke_v1"

NOT_APPLICABLE = "NOT_APPLICABLE"
MISSING = "MISSING"

SENSOR_SPEC: dict[str, dict[str, Any]] = {
    "landsat8": {
        "native_resolution_m": 30.0, "grid": "landsat_30m",
        "scale_m": 30.0,
    },
    "sentinel2": {
        "native_resolution_m": 10.0, "grid": "sentinel_10m",
        "scale_m": 10.0,
    },
    "sentinel1": {
        "native_resolution_m": 10.0, "grid": "sentinel_10m",
        "scale_m": 10.0,
    },
}

CANDIDATE_COLUMNS: tuple[str, ...] = (
    "query_id", "sensor", "collection_id",
    "scene_id", "system_index", "product_id",
    "acquisition_utc", "acquisition_date", "day_of_year",
    "roi_id", "scene_bounds",
    "roi_intersection_fraction", "roi_coverage_fraction",
    "native_resolution_m", "grid",
    "cloud_cover_fraction", "cloud_cover_land_fraction",
    "wrs_path", "wrs_row", "mgrs_tile",
    "processing_baseline", "spacecraft",
    "instrument_mode", "orbit_direction", "relative_orbit_number",
    "polarizations", "platform_number",
    "vv_available", "vh_available", "hh_available", "hv_available",
    "angle_available", "cloud_probability_available",
    "roi_total_pixels", "roi_valid_pixels", "roi_cloud_pixels",
    "roi_cloud_shadow_pixels", "roi_cirrus_pixels", "roi_snow_pixels",
    "roi_saturated_pixels", "roi_clear_pixels",
    "valid_pixel_fraction", "roi_cloud_fraction", "roi_shadow_fraction",
    "roi_cirrus_fraction", "roi_snow_fraction", "roi_saturated_fraction",
    "clear_pixel_fraction",
    "accepted", "policy_eligible", "selected", "selected_orbit",
    "selection_rank", "selection_score", "selection_reason",
    "rejection_reasons", "metadata_retrieval_timestamp",
)

# Fields that define the stable catalog fingerprint (timestamps of the
# retrieval itself and derived annotations are deliberately excluded).
FINGERPRINT_FIELDS: tuple[str, ...] = (
    "sensor", "collection_id", "scene_id", "product_id",
    "acquisition_utc", "wrs_path", "wrs_row", "mgrs_tile",
    "orbit_direction", "relative_orbit_number", "polarizations",
    "instrument_mode", "platform_number",
    "cloud_cover_fraction", "cloud_cover_land_fraction",
    "roi_coverage_fraction",
    "roi_total_pixels", "roi_valid_pixels", "roi_cloud_pixels",
    "roi_cloud_shadow_pixels", "roi_cirrus_pixels", "roi_snow_pixels",
    "roi_saturated_pixels", "roi_clear_pixels",
    "vv_available", "vh_available", "hh_available", "hv_available",
    "angle_available", "cloud_probability_available",
)

OPTICAL_QA_FRACTIONS: tuple[str, ...] = (
    "valid_pixel_fraction", "roi_cloud_fraction", "roi_shadow_fraction",
    "roi_cirrus_fraction", "roi_snow_fraction", "roi_saturated_fraction",
    "clear_pixel_fraction")
OPTICAL_QA_COUNTS: tuple[str, ...] = (
    "roi_total_pixels", "roi_valid_pixels", "roi_cloud_pixels",
    "roi_cloud_shadow_pixels", "roi_cirrus_pixels", "roi_snow_pixels",
    "roi_saturated_pixels", "roi_clear_pixels")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _ee_geometry(ee: Any) -> Any:
    return ee.Geometry(ROI_GEOMETRY, f"EPSG:{ROI_CRS_EPSG}", False)


def _doy(iso_utc: str) -> int | None:
    try:
        return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).timetuple().tm_yday
    except (ValueError, AttributeError):
        return None


def _raw_collection(ee: Any, sensor: str, roi: Any) -> Any:
    """Full candidate collection (no cloud prefilter; SAR unfiltered).

    Catalog cloud metadata is retained as a feature but never removes a
    candidate. Sentinel-1 is queried WITHOUT mode/polarisation filters so
    non-IW or non-VV/VH scenes remain visible as rejected candidates.
    """
    start, end = DEFAULT_START, DEFAULT_END
    if sensor == "landsat8":
        return (ee.ImageCollection(COLLECTIONS["landsat8"])
                .filterBounds(roi).filterDate(start, end))
    if sensor == "sentinel2":
        return (ee.ImageCollection(COLLECTIONS["sentinel2"])
                .filterBounds(roi).filterDate(start, end))
    if sensor == "sentinel1":
        return (ee.ImageCollection(COLLECTIONS["sentinel1"])
                .filterBounds(roi).filterDate(start, end))
    raise KeyError(f"unsupported smoke sensor {sensor!r}")


def _annotated_features(ee: Any, sensor: str, roi: Any) -> list[dict[str, Any]]:
    """One getInfo: raw scenes + server-side ROI footprint coverage."""
    collection = _raw_collection(ee, sensor, roi)
    roi_area = roi.area(30.0)

    def annotate(image: Any) -> Any:
        intersection = image.geometry(30.0).intersection(roi, 30.0)
        return image.set(
            "spartina_roi_coverage_fraction",
            intersection.area(30.0).divide(roi_area))

    return list(collection.map(annotate).getInfo().get("features", []))


def _value_or(value: object, sentinel: str) -> object:
    return value if value is not None else sentinel


def _base_row(sensor: str, query_id: str, feature: dict[str, Any],
              retrieval_ts: str) -> tuple[dict[str, Any], dict[str, Any]]:
    props = dict(feature.get("properties", {}))
    if sensor.startswith("landsat"):
        record = landsat.record_from_properties(props)
    elif sensor == "sentinel2":
        record = sentinel2.record_from_properties(props)
    else:
        record = sentinel1.record_from_properties(props)
    iso_utc = epoch_ms_to_iso(record.get("acquisition_epoch_ms")) or ""
    coverage = props.get("spartina_roi_coverage_fraction")
    coverage = float(coverage) if isinstance(coverage, int | float) else None
    row: dict[str, Any] = {
        "query_id": query_id,
        "sensor": sensor,
        "collection_id": COLLECTIONS[sensor],
        "scene_id": record.get("scene_id"),
        "system_index": props.get("system:index"),
        "product_id": record.get("product_id"),
        "acquisition_utc": iso_utc,
        "acquisition_date": iso_utc[:10] if iso_utc else MISSING,
        "day_of_year": _doy(iso_utc),
        "roi_id": ROI_ID,
        "scene_bounds": list(_bbox_from_feature(feature)),
        "roi_intersection_fraction": coverage,
        "roi_coverage_fraction": coverage,
        "native_resolution_m": SENSOR_SPEC[sensor]["native_resolution_m"],
        "grid": SENSOR_SPEC[sensor]["grid"],
        "accepted": True,
        "policy_eligible": False,
        "selected": False,
        "selected_orbit": NOT_APPLICABLE,
        "selection_rank": None,
        "selection_score": None,
        "selection_reason": None,
        "rejection_reasons": [],
        "metadata_retrieval_timestamp": retrieval_ts,
    }
    return row, record


def _optical_row(sensor: str, query_id: str, feature: dict[str, Any],
                 qa: dict[str, Any], retrieval_ts: str) -> dict[str, Any]:
    row, record = _base_row(sensor, query_id, feature, retrieval_ts)
    props = dict(feature.get("properties", {}))
    row.update({
        "cloud_cover_fraction": (
            record.get("cloud_cover_fraction")
            if sensor == "landsat8"
            else record.get("cloudy_pixel_fraction")),
        "cloud_cover_land_fraction": record.get(
            "cloud_cover_land_fraction"),
        "wrs_path": _value_or(record.get("wrs_path"), NOT_APPLICABLE),
        "wrs_row": _value_or(record.get("wrs_row"), NOT_APPLICABLE),
        "mgrs_tile": _value_or(record.get("mgrs_tile"), NOT_APPLICABLE),
        "processing_baseline": (
            record.get("processing_baseline")
            if sensor == "sentinel2" else NOT_APPLICABLE),
        "spacecraft": (
            props.get("SPACECRAFT_NAME") if sensor == "sentinel2"
            else props.get("SPACECRAFT_ID")),
        "instrument_mode": NOT_APPLICABLE,
        "orbit_direction": NOT_APPLICABLE,
        "relative_orbit_number": NOT_APPLICABLE,
        "polarizations": NOT_APPLICABLE,
        "platform_number": NOT_APPLICABLE,
        "vv_available": NOT_APPLICABLE, "vh_available": NOT_APPLICABLE,
        "hh_available": NOT_APPLICABLE, "hv_available": NOT_APPLICABLE,
        "angle_available": NOT_APPLICABLE,
        "cloud_probability_available": (
            bool(qa.get("cloud_probability_available"))
            if sensor == "sentinel2" else NOT_APPLICABLE),
    })
    for key in OPTICAL_QA_COUNTS:
        row[key] = qa.get(key)
    for key in OPTICAL_QA_FRACTIONS:
        row[key] = qa.get(key)
    return row


def _sentinel1_row(query_id: str, feature: dict[str, Any],
                   qa: dict[str, Any], retrieval_ts: str) -> dict[str, Any]:
    row, record = _base_row("sentinel1", query_id, feature, retrieval_ts)
    # S1 productIdentifier is the documented property; when the ingestion
    # pipeline returns null it must be recorded MISSING, not fabricated.
    product_id = record.get("product_id")
    polarizations = record.get("polarizations")
    mode = record.get("instrument_mode")
    row.update({
        "product_id": product_id if product_id else MISSING,
        "cloud_cover_fraction": NOT_APPLICABLE,
        "cloud_cover_land_fraction": NOT_APPLICABLE,
        "wrs_path": NOT_APPLICABLE, "wrs_row": NOT_APPLICABLE,
        "mgrs_tile": NOT_APPLICABLE,
        "processing_baseline": NOT_APPLICABLE,
        "spacecraft": record.get("platform"),
        "instrument_mode": mode or MISSING,
        "orbit_direction": record.get("orbit_direction") or MISSING,
        "relative_orbit_number": (
            record.get("relative_orbit_number") or MISSING),
        "polarizations": list(polarizations) if polarizations else MISSING,
        "platform_number": record.get("platform") or MISSING,
        "vv_available": bool(qa.get("vv_available")),
        "vh_available": bool(qa.get("vh_available")),
        "hh_available": bool(qa.get("hh_available")),
        "hv_available": bool(qa.get("hv_available")),
        "angle_available": bool(qa.get("angle_available")),
        "cloud_probability_available": NOT_APPLICABLE,
        "roi_total_pixels": qa.get("roi_total_pixels"),
        "roi_valid_pixels": qa.get("roi_valid_pixels"),
        "valid_pixel_fraction": qa.get("valid_pixel_fraction"),
    })
    for key in ("roi_cloud_pixels", "roi_cloud_shadow_pixels",
                "roi_cirrus_pixels", "roi_snow_pixels",
                "roi_saturated_pixels", "roi_clear_pixels"):
        row[key] = NOT_APPLICABLE
    for key in ("roi_cloud_fraction", "roi_shadow_fraction",
                "roi_cirrus_fraction", "roi_snow_fraction",
                "roi_saturated_fraction", "clear_pixel_fraction"):
        row[key] = NOT_APPLICABLE
    # Eligibility: IW mode with both VV and VH present.
    reasons = list(row["rejection_reasons"])
    if mode != sentinel1.INSTRUMENT_MODE_IW:
        reasons.append(REASON_SAR_NOT_IW)
    if not (row["vv_available"] and row["vh_available"]):
        reasons.append(REASON_SAR_MISSING_POLS)
    row["rejection_reasons"] = reasons
    row["accepted"] = not reasons
    return row


def _qa_counts(ee: Any, sensor: str, collection: Any,
               roi: Any) -> dict[str, dict[str, Any]]:
    scale = float(SENSOR_SPEC[sensor]["scale_m"])
    if sensor == "landsat8":
        return pixelqa.counts_landsat(ee, collection, roi, scale_m=scale)
    if sensor == "sentinel2":
        return pixelqa.counts_sentinel2(ee, collection, roi, scale_m=scale)
    return pixelqa.counts_sentinel1(ee, collection, roi, scale_m=scale)


def collect_sensor(
    ee: Any, sensor: str, policy: SingleScenePolicy,
    retrieval_ts: str,
) -> list[dict[str, Any]]:
    """One full real retrieval: every candidate row with QA + rank marks."""
    roi = _ee_geometry(ee)
    query_id = (
        f"{sensor}-{ROI_ID}-{DEFAULT_START[:10]}_{DEFAULT_END[:10]}"
        f"-doy{DEFAULT_TARGET_DOY}-{SMOKE_VERSION}")
    features = _annotated_features(ee, sensor, roi)
    if not features:
        raise RuntimeError(
            f"ZERO real scenes for {sensor} {DEFAULT_START}..{DEFAULT_END}; "
            "the date range must NOT be widened silently -- report this")
    raw = _raw_collection(ee, sensor, roi)
    qa_by_scene = _qa_counts(ee, sensor, raw, roi)

    rows: list[dict[str, Any]] = []
    for feature in features:
        scene_id = str(dict(feature.get("properties", {})).get("system:index"))
        qa = qa_by_scene.get(scene_id, {})
        if sensor == "sentinel1":
            row = _sentinel1_row(query_id, feature, qa, retrieval_ts)
        else:
            row = _optical_row(sensor, query_id, feature, qa, retrieval_ts)
        rows.append(row)

    if sensor == "sentinel1":
        _rank_sar(rows, policy)
    else:
        _rank_optical(rows, policy)
    return rows


def _rank_optical(rows: list[dict[str, Any]],
                  policy: SingleScenePolicy) -> None:
    for row in rows:
        reasons = list(rejection_reasons(row, policy))
        row["rejection_reasons"] = sorted({*row["rejection_reasons"],
                                           *reasons})
    ranked = rank_eligibles(rows, policy)
    by_id = {r["scene_id"]: r for r in ranked}
    for row in rows:
        chosen = by_id.get(row["scene_id"])
        row["policy_eligible"] = chosen is not None
        if chosen is not None:
            row["selection_rank"] = chosen["selection_rank"]
            row["selection_score"] = chosen["selection_score"]
            row["selection_reason"] = chosen["selection_reason"]
            row["selected"] = chosen["selection_rank"] == 1


def _rank_sar(rows: list[dict[str, Any]],
              policy: SingleScenePolicy) -> None:
    """SAR: rank ASCENDING and DESCENDING independently."""
    for row in rows:
        if not row["rejection_reasons"]:
            row["rejection_reasons"] = list(rejection_reasons(row, policy))
    best = best_per_sar_pass(rows, policy)
    eligible_ids: set[str] = set()
    for orbit, scene in best.items():
        if scene is None:
            continue
        ranked = rank_eligibles(rows, policy, orbit=orbit)
        by_id = {str(r["scene_id"]): r for r in ranked}
        eligible_ids.update(by_id.keys())
        for row in rows:
            chosen = by_id.get(row["scene_id"])
            if chosen is None:
                continue
            row["policy_eligible"] = True
            row["selection_rank"] = chosen["selection_rank"]
            row["selection_score"] = chosen["selection_score"]
            row["selection_reason"] = chosen["selection_reason"]
            row["selected_orbit"] = orbit
            row["selected"] = chosen["selection_rank"] == 1
    # explicit eligibility flags even without a ranked entry
    for row in rows:
        if row["accepted"] and not row["rejection_reasons"]:
            row["policy_eligible"] = True


def _fingerprint_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: row.get(k) for k in FINGERPRINT_FIELDS}
            for row in sorted(rows, key=lambda r: str(r.get("scene_id")))]


def _selection_payload(
    rows_by_sensor: dict[str, list[dict[str, Any]]],
    policy: SingleScenePolicy,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"policy": policy.to_record()}
    for sensor, rows in rows_by_sensor.items():
        payload[sensor] = {
            "eligible": sorted(
                [(r["scene_id"], r["selection_rank"])
                 for r in rows if r["policy_eligible"]],
                key=lambda item: (item[1] is None, item[1])),
            "selected_overall": [r["scene_id"] for r in rows
                                 if r["selected"]],
            "selected_by_orbit": (
                {orbit: next((r["scene_id"] for r in rows
                              if r["selected"] and r["selected_orbit"] == orbit),
                             None)
                 for orbit in ("ASCENDING", "DESCENDING")}
                if sensor == "sentinel1" else None),
        }
    return payload


def run_smoke(
    sensors: tuple[str, ...] = ("landsat8", "sentinel1", "sentinel2"),
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the real metadata-only smoke twice; return full evidence."""
    project = configured_project()
    if project is None:
        raise SystemExit(
            f"export {PROJECT_ENV_VAR}=<project-id> before the real smoke")
    initialize()
    import ee  # noqa: F401  (initialization side effect; module used below)

    policy = SingleScenePolicy(target_doy=DEFAULT_TARGET_DOY)
    out_dir = out_dir or (REPO_ROOT / "artifacts" / "gee" / "real_smoke")
    out_dir.mkdir(parents=True, exist_ok=True)

    # First retrieval.
    ts_a = _now_iso()
    rows_a: dict[str, list[dict[str, Any]]] = {
        sensor: collect_sensor(ee, sensor, policy, ts_a)
        for sensor in sensors}
    # Independent second retrieval (fresh EE calls) for determinism check.
    ts_b = _now_iso()
    rows_b: dict[str, list[dict[str, Any]]] = {
        sensor: collect_sensor(ee, sensor, policy, ts_b)
        for sensor in sensors}

    all_rows = [row for sensor in sensors for row in rows_a[sensor]]
    catalog_fp = canonical_fingerprint(_fingerprint_payload(
        [r for sensor in sensors for r in rows_a[sensor]]))
    catalog_fp_b = canonical_fingerprint(_fingerprint_payload(
        [r for sensor in sensors for r in rows_b[sensor]]))
    selection_fp = canonical_fingerprint(_selection_payload(rows_a, policy))
    selection_fp_b = canonical_fingerprint(_selection_payload(rows_b, policy))

    rerun_match = (
        catalog_fp == catalog_fp_b and selection_fp == selection_fp_b)
    id_sets_a = {s: sorted(r["scene_id"] for r in rows_a[s])
                 for s in sensors}
    id_sets_b = {s: sorted(r["scene_id"] for r in rows_b[s])
                 for s in sensors}

    counts = {sensor: {
        "candidate_count": len(rows_a[sensor]),
        "eligible_count": sum(1 for r in rows_a[sensor]
                              if r["policy_eligible"]),
        "selected_count": sum(1 for r in rows_a[sensor] if r["selected"]),
    } for sensor in sensors}
    s1_rows = rows_a.get("sentinel1", [])
    s1_passes = {orbit: {
        "candidate_count": sum(
            1 for r in s1_rows if r["orbit_direction"] == orbit),
        "eligible_count": sum(
            1 for r in s1_rows
            if r["policy_eligible"] and r["selected_orbit"] == orbit),
        "selected_scene_id": next(
            (r["scene_id"] for r in s1_rows
             if r["selected"] and r["selected_orbit"] == orbit), None),
    } for orbit in ("ASCENDING", "DESCENDING")}

    selected: dict[str, Any] = {}
    for sensor in sensors:
        picks = [r for r in rows_a[sensor] if r["selected"]]
        selected[sensor] = [{
            "scene_id": r["scene_id"],
            "product_id": r["product_id"],
            "acquisition_utc": r["acquisition_utc"],
            "selected_orbit": r["selected_orbit"],
            "selection_rank": r["selection_rank"],
            "wrs_path": r["wrs_path"], "wrs_row": r["wrs_row"],
            "mgrs_tile": r["mgrs_tile"],
            "relative_orbit_number": r["relative_orbit_number"],
            "roi_cloud_fraction": r["roi_cloud_fraction"],
            "valid_pixel_fraction": r["valid_pixel_fraction"],
        } for r in picks]

    json_path = out_dir / f"candidate_scenes_{SMOKE_VERSION}.json"
    csv_path = out_dir / f"candidate_scenes_{SMOKE_VERSION}.csv"
    parquet_path = out_dir / f"candidate_scenes_{SMOKE_VERSION}.parquet"
    json_path.write_text(
        json.dumps(all_rows, indent=2, sort_keys=True), encoding="utf-8")
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("pandas/pyarrow are required to write the table") from exc
    frame = pd.DataFrame(all_rows, columns=list(CANDIDATE_COLUMNS))
    frame.to_csv(csv_path, index=False)
    # Parquet disallows mixing numeric nulls with "NOT_APPLICABLE"/"MISSING"
    # strings in one column. Columns whose semantics differ per sensor are
    # written as explicit strings; the JSON table stays the canonical
    # richly-typed copy and documents every sentinel.
    _STRINGIFIED = (
        "cloud_cover_fraction", "cloud_cover_land_fraction",
        "wrs_path", "wrs_row", "relative_orbit_number",
        "vv_available", "vh_available", "hh_available", "hv_available",
        "angle_available", "cloud_probability_available",
        *OPTICAL_QA_COUNTS, *OPTICAL_QA_FRACTIONS,
    )

    def _stringify(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    pq_frame = frame.copy()
    for column in _STRINGIFIED:
        pq_frame[column] = pq_frame[column].map(_stringify)
    for column in ("polarizations", "selection_score"):
        pq_frame[column] = pq_frame[column].map(
            lambda v: json.dumps(v) if isinstance(v, list | tuple) else v)
    pq_frame.to_parquet(parquet_path, index=False)

    summary = {
        "smoke_version": SMOKE_VERSION,
        "retrieval_utc_run_1": ts_a,
        "retrieval_utc_run_2": ts_b,
        "project_env_var": PROJECT_ENV_VAR,
        "project_id": project,
        "roi": {
            "roi_id": ROI_ID, "crs_epsg": ROI_CRS_EPSG,
            "geometry": ROI_GEOMETRY,
            "geometry_sha256": canonical_fingerprint(ROI_GEOMETRY),
            "note": ROI_NOTE,
        },
        "window": {
            "start_utc": DEFAULT_START, "end_utc": DEFAULT_END,
            "target_doy": DEFAULT_TARGET_DOY},
        "collections": {s: COLLECTIONS[s] for s in sensors},
        "policy": policy.to_record(),
        "counts": counts,
        "s1_pass_breakdown": s1_passes,
        "selected_scenes": selected,
        "catalog_fingerprint_sha256_run_1": catalog_fp,
        "catalog_fingerprint_sha256_run_2": catalog_fp_b,
        "selection_fingerprint_sha256_run_1": selection_fp,
        "selection_fingerprint_sha256_run_2": selection_fp_b,
        "rerun_identical": rerun_match,
        "rerun_scene_id_sets_equal": id_sets_a == id_sets_b,
        "candidate_files": {
            "json": str(json_path), "csv": str(csv_path),
            "parquet": str(parquet_path)},
    }
    summary_path = out_dir / f"run_summary_{SMOKE_VERSION}.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return {**summary, "rows_run_1": rows_a, "rows_run_2": rows_b,
            "summary_path": str(summary_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensors", nargs="+",
                        default=["landsat8", "sentinel1", "sentinel2"])
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    result = run_smoke(
        tuple(args.sensors),
        Path(args.out_dir) if args.out_dir else None)
    printable = {k: v for k, v in result.items()
                 if not k.startswith("rows_run")}
    print(json.dumps(printable, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
