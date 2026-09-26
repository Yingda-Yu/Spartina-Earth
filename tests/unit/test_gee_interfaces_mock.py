"""Offline tests for the GEE interface skeletons (no network, no creds)."""

from __future__ import annotations

import pytest

from spartina.data.gee import auth, manifest
from spartina.data.gee.catalog import (
    MockCatalogClient,
    Region,
    SceneMetadata,
    SceneQuery,
)
from spartina.data.gee.collections import collection_for
from spartina.data.gee.export import ExportRequest, NullExporter
from spartina.data.gee.quality import CloudCoverFilter, apply_filters


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("GOOGLE_APPLICATION_CREDENTIALS", "EE_SERVICE_ACCOUNT_JSON"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(auth, "_USER_CREDENTIAL_CANDIDATES", ("/nonexistent-spartina-creds",))


def test_credentials_absent_and_initialize_raises() -> None:
    assert auth.credentials_available() is False
    with pytest.raises(RuntimeError, match="No Earth Engine credentials"):
        auth.initialize()


def test_collection_mapping_covers_six_sensors() -> None:
    assert collection_for("landsat8") == "LANDSAT/LC08/C02/T1_L2"
    assert collection_for("sentinel2") == "COPERNICUS/S2_SR_HARMONIZED"
    with pytest.raises(KeyError):
        collection_for("unknown_sensor")


def test_mock_catalog_filters_by_sensor_and_cloud() -> None:
    scenes = (
        SceneMetadata("s1", "landsat8", "2020-06-01T02:30:00Z", 0.1, (0, 0, 1, 1), "EPSG:32651"),
        SceneMetadata("s2", "landsat8", "2020-07-01T02:30:00Z", 0.8, (0, 0, 1, 1), "EPSG:32651"),
        SceneMetadata("s3", "sentinel2", "2020-06-02T10:30:00Z", 0.05, (0, 0, 1, 1), "EPSG:32651"),
    )
    client = MockCatalogClient(scenes)
    query = SceneQuery(
        sensor_name="landsat8",
        start_date="2020-01-01",
        end_date="2020-12-31",
        region=Region({"type": "Polygon"}, 32651),
        max_cloud_cover=0.5,
    )
    result = client.query(query)
    assert [scene.scene_id for scene in result] == ["s1"]
    assert client.calls == [query]


def test_cloud_cover_filter_validation() -> None:
    with pytest.raises(ValueError):
        CloudCoverFilter(1.5)
    scene = SceneMetadata("s", "landsat8", "2020-06-01", 0.9, (0, 0, 1, 1), "EPSG:32651")
    assert CloudCoverFilter(0.5).accept(scene) is False


def test_null_exporter_and_manifest_build_are_offline() -> None:
    scenes = [
        SceneMetadata("s1", "landsat8", "2020-06-01T02:30:00Z", 0.1, (0, 0, 1, 1), "EPSG:32651")
    ]
    request = ExportRequest(
        request_id="req-1",
        sensor_name="landsat8",
        tile_id="tile-001",
        start_date="2020-06-01",
        end_date="2020-06-30",
        destination_uri="datasets/raw/tile-001/",
        bands=("SR_B2", "SR_B3", "SR_B4"),
        crs_epsg=32651,
        resolution_m=30.0,
    )
    exporter = NullExporter()
    task = exporter.submit(request)
    assert task.state == "MOCK_ENQUEUED"
    assert len(exporter.submitted) == 1

    record = manifest.build_export_record(request, task, scenes)
    assert record["scene_ids"] == ["s1"]
    assert record["export_request"]["tile_id"] == "tile-001"

    asset = manifest.build_scene_manifest(scenes[0])
    assert asset["year"] == 2020
    assert asset["label_quality"] == "UNLABELED"
    assert asset["status"] == "cataloged"


def test_apply_filters_chain() -> None:
    scenes = [
        SceneMetadata("a", "landsat8", "2020-06-01", 0.2, (0, 0, 1, 1), "EPSG:32651"),
        SceneMetadata("b", "landsat8", "2020-06-02", 0.6, (0, 0, 1, 1), "EPSG:32651"),
    ]
    kept = apply_filters(scenes, [CloudCoverFilter(0.3)])
    assert [s.scene_id for s in kept] == ["a"]
