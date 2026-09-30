"""Manifest construction for GEE export batches (M0).

Produces plain dictionaries aligned with the asset manifest schema
(``datasets/manifests/schema.json``); bytes/checksums are filled in by M1
code after real exports land on disk. Unknown values are explicitly
``None`` / ``"UNKNOWN"`` rather than guessed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spartina.data.gee.catalog import SceneMetadata
from spartina.data.gee.export import ExportRequest, ExportTask


def build_scene_manifest(scene: SceneMetadata) -> dict[str, Any]:
    """Build one schema-aligned asset record for a catalog scene."""
    year: int | None
    try:
        year = int(scene.acquisition_time[:4])
    except (ValueError, IndexError):
        year = None
    return {
        "asset_id": f"scene-{scene.scene_id}",
        "source": "google_earth_engine",
        "provider": "USGS/ESA via GEE (exact provider set in M1 per collection)",
        "sensor": scene.sensor_name,
        "product": None,
        "acquisition_time": scene.acquisition_time,
        "year": year,
        "region": None,
        "bbox": list(scene.bbox),
        "crs": scene.crs,
        "resolution": None,
        "bands": [],
        "label_type": None,
        "label_quality": "UNLABELED",
        "license": "UNKNOWN",
        "permission": "unknown",
        "local_uri": None,
        "remote_uri": None,
        "checksum": None,
        "provenance": {
            "scene_id": scene.scene_id,
            "catalog": "GEE",
            "extra": scene.extra,
        },
        "status": "cataloged",
        "notes": "M0 mock/record; not exported.",
    }


def build_export_record(
    request: ExportRequest, task: ExportTask, scenes: list[SceneMetadata]
) -> dict[str, Any]:
    """Build the export-batch provenance record."""
    return {
        "export_request": {
            "request_id": request.request_id,
            "sensor": request.sensor_name,
            "tile_id": request.tile_id,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "bands": list(request.bands),
            "crs_epsg": request.crs_epsg,
            "resolution_m": request.resolution_m,
            "destination_uri": request.destination_uri,
        },
        "task": {
            "task_id": task.task_id,
            "state": task.state,
            "messages": list(task.messages),
        },
        "scene_ids": [scene.scene_id for scene in scenes],
        "status": task.state,
    }


def build_data_factory_manifest(
    request: ExportRequest,
    task: ExportTask,
    *,
    candidate_scenes: list[dict[str, Any]],
    selected_scene_ids: list[str],
    grid_spec: dict[str, Any],
    processing_config: dict[str, Any],
    landed_files: list[dict[str, Any]],
    tide_records: list[dict[str, Any]] | None = None,
    roi: dict[str, Any] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Build the v1 EO Data Factory provenance manifest.

    Provenance chain (AGENTS.md rule 8):
    source scenes -> QA/candidate table -> fixed grid -> processing config
    -> export task -> landed files + checksums. Every selected scene must
    be present in the candidate table. Unknown fields are explicit
    ``None`` / ``"UNKNOWN"``; nothing is inferred.
    """
    candidate_ids = {row["scene_id"] for row in candidate_scenes}
    missing = [sid for sid in selected_scene_ids
               if sid not in candidate_ids]
    if missing:
        raise ValueError(
            f"selected scenes absent from candidate table: {missing}")
    required_grid = {"crs", "transform", "width", "height",
                     "pixel_size_m", "bounds"}
    if not required_grid <= set(grid_spec):
        raise ValueError(
            f"grid_spec missing keys: {sorted(required_grid - set(grid_spec))}")
    for record in landed_files:
        for key in ("local_uri", "sha256", "size_bytes"):
            if record.get(key) is None:
                raise ValueError(
                    f"landed file record missing {key!r}; a factory asset "
                    "cannot be manifest without checksum provenance")
    return {
        "manifest_version": "GEE_DATA_FACTORY_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "status": task.state,
        "roi": roi or None,
        "science_stream": request.science_stream or "UNKNOWN",
        "grid": dict(grid_spec),
        "export_request": {
            "request_id": request.request_id,
            "sensor": request.sensor_name,
            "tile_id": request.tile_id,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "bands": list(request.bands),
            "crs_epsg": request.crs_epsg,
            "resolution_m": request.resolution_m,
            "destination_uri": request.destination_uri,
            "source_scene_ids": list(request.source_scene_ids),
        },
        "selected_scene_ids": list(selected_scene_ids),
        "candidate_scenes": list(candidate_scenes),
        "tide_inundation": list(tide_records or []),
        "processing_config": dict(processing_config),
        "export_task": {
            "task_id": task.task_id,
            "state": task.state,
            "messages": list(task.messages),
        },
        "landed_files": list(landed_files),
        "label_quality": "UNLABELED",
        "license": "UNKNOWN",
        "notes": notes,
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    """Serialize a manifest to JSON (parent dirs created). Returns path."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output


__all__ = [
    "build_data_factory_manifest",
    "build_export_record",
    "build_scene_manifest",
    "write_json",
]
