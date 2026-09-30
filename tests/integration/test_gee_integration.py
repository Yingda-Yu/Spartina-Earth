"""Real GEE integration smoke tests.

Auto-skip unless genuine credentials AND SPARTINA_GEE_PROJECT are present.
Never runs under the default test selection; execute manually with:

    pytest -m gee_integration

Catalog tests are metadata-only and stay tiny. The end-to-end export test
additionally requires SPARTINA_GEE_SMOKE_EXPORT=1 (one ~500 m Landsat tile
exported to Google Drive and downloaded) -- never bulk, never nationwide.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from spartina.data.gee import auth
from spartina.data.gee.catalog import (
    EarthEngineCatalogClient,
    Region,
    SceneQuery,
)
from spartina.data.gee.quality import (
    CloudCoverFilter,
    apply_filters,
    build_candidate_table,
    candidate_records,
)

PROJECT_READY = bool(auth.configured_project())

pytestmark = [
    pytest.mark.gee_integration,
    pytest.mark.skipif(
        not auth.credentials_available(),
        reason="GEE credentials not configured; integration test skipped.",
    ),
    pytest.mark.skipif(
        not PROJECT_READY,
        reason="SPARTINA_GEE_PROJECT is unset; real Initialize needs a "
               "Cloud project with Earth Engine enabled.",
    ),
]

# Small technical smoke box on the northern Hangzhou Bay coast (EPSG:4326).
# This is NOT an authoritative bay boundary -- see ZHEJIANG_DATA_PREPARATION_V0.
HZ_SMALL_ROI = Region(
    geometry={
        "type": "Polygon",
        "coordinates": [[
            [121.10, 30.30], [121.12, 30.30], [121.12, 30.32],
            [121.10, 30.32], [121.10, 30.30]]],
    },
    crs_epsg=4326,
)
# Narrow, data-rich autumn window (season policy v0 target: early October).
WINDOW = ("2020-09-01", "2020-10-31")

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts" / "data" / "gee"


def _load_driver(name: str) -> object:
    spec = importlib.util.spec_from_file_location(
        name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_ee_initialize_smoke() -> None:
    """Initialize with the env-provided project and touch the API."""
    auth.initialize()  # pragma: no cover - requires real credentials
    import ee  # type: ignore[import-not-found]  # pragma: no cover

    result = ee.Number(1).getInfo()  # pragma: no cover
    assert result == 1  # pragma: no cover


@pytest.mark.parametrize(
    ("sensor", "id_field"),
    [("landsat8", "wrs_path"),
     ("sentinel2", "mgrs_tile"),
     ("sentinel1", "orbit_direction")],
)
def test_real_candidate_provenance_small_roi(
    sensor: str, id_field: str,
) -> None:
    """Real scenes must carry ids, exact UTC times and sensor provenance.

    Regression guard for the Issue #6 requirement: no product may ever
    again be recorded as '2015 composite, source scenes UNKNOWN'.
    """
    client = EarthEngineCatalogClient()  # pragma: no cover
    query = SceneQuery(
        sensor_name=sensor, start_date=WINDOW[0], end_date=WINDOW[1],
        region=HZ_SMALL_ROI, max_cloud_cover=1.0,
    )
    scenes = client.query(query)  # pragma: no cover
    assert scenes, f"no {sensor} scenes returned for the small ROI"  # pragma: no cover
    for scene in scenes:  # pragma: no cover
        assert scene.scene_id and scene.extra.get("product_id")
        assert scene.acquisition_time.endswith("+00:00")
        assert scene.extra.get(id_field) is not None

    if sensor != "sentinel1":  # pragma: no cover
        accepted = apply_filters(scenes, [CloudCoverFilter(0.8)])
    else:
        accepted = list(scenes)
    table = build_candidate_table(
        scenes, frozenset(s.scene_id for s in accepted))
    records = candidate_records(table)
    assert len(records) == len(scenes)  # pragma: no cover
    assert all(row["acquisition_utc"] for row in records)  # pragma: no cover
    assert all(not row["selected"] for row in records)  # pragma: no cover


@pytest.mark.skipif(
    os.environ.get("SPARTINA_GEE_SMOKE_EXPORT") != "1",
    reason="operator must opt in (SPARTINA_GEE_SMOKE_EXPORT=1) for the "
           "real Drive export + download smoke; default run is metadata-only",
)
def test_real_single_scene_export_roundtrip(tmp_path: Path) -> None:
    """Full acceptance chain: query -> select -> ee.batch task -> GeoTIFF.

    One selected Landsat 8 scene over the ~500 m technical box is exported
    through a real pollable Earth Engine batch task to Google Drive,
    downloaded, verified against the fixed 30 m GridSpec, checksummed and
    manifested (GEE_DATA_FACTORY_V1).
    """
    catalog_driver = _load_driver("real_catalog_smoke")
    summary = catalog_driver.run_smoke(  # type: ignore[attr-defined]
        ("landsat8",), WINDOW[0], WINDOW[1], tmp_path, 275)
    candidates = Path(summary["candidate_json"])
    assert candidates.is_file()  # pragma: no cover
    rows = json.loads(candidates.read_text(encoding="utf-8"))
    assert any(row["selected"] for row in rows)  # pragma: no cover

    export_driver = _load_driver("real_export_smoke")
    old_argv = sys.argv
    sys.argv = [
        "real_export_smoke.py", "--candidates", str(candidates),
        "--sensor", "landsat8", "--mode", "batch",
        "--out-dir", str(tmp_path), "--tasks",
        str(tmp_path / "task_store.json"),
    ]
    try:
        export_driver.main()  # type: ignore[attr-defined]  # pragma: no cover
    finally:
        sys.argv = old_argv

    manifests = list(tmp_path.glob("manifest_*.json"))  # pragma: no cover
    assert len(manifests) == 1  # pragma: no cover
    manifest = json.loads(manifests[0].read_text())  # pragma: no cover
    landed = manifest["landed_files"][0]  # pragma: no cover
    assert Path(landed["local_uri"]).is_file()  # pragma: no cover
    assert len(landed["sha256"]) == 64  # pragma: no cover
    assert manifest["selected_scene_ids"][0] in {  # pragma: no cover
        row["scene_id"] for row in manifest["candidate_scenes"]}
    assert manifest["grid"]["pixel_size_m"] == [30.0, 30.0]  # pragma: no cover
