"""Manifest construction for GEE export batches (M0).

Produces plain dictionaries aligned with the asset manifest schema
(``datasets/manifests/schema.json``); bytes/checksums are filled in by M1
code after real exports land on disk. Unknown values are explicitly
``None`` / ``"UNKNOWN"`` rather than guessed.
"""

from __future__ import annotations

import json
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


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    """Serialize a manifest to JSON (parent dirs created). Returns path."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output


__all__ = ["build_export_record", "build_scene_manifest", "write_json"]
