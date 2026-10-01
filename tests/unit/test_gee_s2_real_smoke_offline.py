"""Offline unit tests for the M1.6c Sentinel-2 real-byte smoke driver.

Nothing here contacts Earth Engine: ROI determinism, the frozen SCL QA
policy, task-store state history, and the rasterio audit helpers
(valid_mask_info / reflectance_sanity_masked) are all exercised on
synthetic in-memory data. The REAL end-to-end byte pipeline lives in
tests/integration/test_gee_integration.py and additionally requires
SPARTINA_GEE_SMOKE_EXPORT=1.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from spartina.data.gee.provenance import ProvenanceError
from spartina.data.gee.sentinel2 import (
    S2_SCL_QA_POLICY_VERSION,
    S2_VALID_SCL_CLASSES,
)
from spartina.data.gee.tasks import TaskStore

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "data" / "gee"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load_driver() -> object:
    if "real_s2_export_smoke" in sys.modules:
        return sys.modules["real_s2_export_smoke"]
    spec = importlib.util.spec_from_file_location(
        "real_s2_export_smoke", SCRIPTS / "real_s2_export_smoke.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["real_s2_export_smoke"] = module
    spec.loader.exec_module(module)
    return module


driver = _load_driver()


def test_export_roi_is_deterministic_10m_500m() -> None:
    """ROI = projected technical centroid + fixed metric width; 10 m grid."""
    grid_a, region_a, rule = driver.build_export_roi()
    grid_b, region_b, _ = driver.build_export_roi()

    assert grid_a == grid_b  # frozen dataclass equality
    assert region_a == region_b
    assert pytest.approx(rule["technical_roi_centroid_lonlat"], abs=1e-9) \
        == [121.11, 30.31]
    assert grid_a.crs == "EPSG:32651"
    assert grid_a.pixel_x_m == 10.0
    assert grid_a.pixel_y_m == 10.0
    # +-250 m box snapped outward to the lattice: 51 x 51 px / 510 m.
    assert (grid_a.width, grid_a.height) == (51, 51)
    assert grid_a.transform == (
        10.0, 0.0, 318010.0, 0.0, -10.0, 3354900.0)
    assert rule["grid_width_m"] == 510.0
    assert rule["grid_height_m"] == 510.0
    ring = region_a["coordinates"][0]
    assert len(ring) == 5 and ring[0] == ring[-1]
    # The region polygon is a closed WGS84 polygon around the UTM grid.
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    assert min(lons) > 121.10 and max(lons) < 121.12
    assert min(lats) > 30.30 and max(lats) < 30.32


def test_scl_valid_policy_matches_frozen_catalog_code() -> None:
    policy = driver.SCL_QA_POLICY
    valid = {int(k) for k in policy["valid_classes"]}
    # M1.6d corrected contract s2_scl_qa_v1_1: valid = {4,5,6}.
    assert valid == set(S2_VALID_SCL_CLASSES) == {4, 5, 6}
    assert policy["version"] == S2_SCL_QA_POLICY_VERSION == "s2_scl_qa_v1_1"
    assert policy["water_remains_valid"] is True
    categories = policy["category_mapping"]
    assert categories["cloud_family_classes"] == [8, 9, 10]
    assert categories["cloud_shadow_classes"] == [3]
    assert categories["cirrus_classes"] == [10]
    assert categories["snow_ice_classes"] == [11]
    assert categories["sensor_invalid_classes"] == [0, 1]
    assert categories["dark_area_classes"] == [2]
    assert categories["unclassified_classes"] == [7]
    # Snow/ice (11), dark area (2) and unclassified (7) are explicitly
    # NOT valid; snow/ice is reported via the separate snow statistic.
    assert policy["snow_or_ice_remains_valid"] is False
    assert policy["dark_area_class_2_decision"] == (
        "NOT_VALID_EXPLICIT_POLICY_DECISION")
    assert policy["unclassified_class_7_decision"] == (
        "NOT_VALID_EXPLICIT_POLICY_DECISION")
    assert policy["supersedes"] == "s2_scl_qa_v1"
    assert policy["superseded_valid_classes"] == [4, 5, 6, 11]


def test_task_store_persists_every_poll_state(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "task_store.json")
    record = store.create("smoke-s2-x")
    store.mark_enqueued(record.task_id, "backend-1")
    store.record_poll_state(record.task_id, "READY")
    store.record_poll_state(record.task_id, "RUNNING")
    store.record_poll_state(record.task_id, "RUNNING")
    store.record_poll_state(record.task_id, "COMPLETED")
    store.mark_completed(record.task_id, result={"state": "COMPLETED"})

    reloaded = TaskStore(tmp_path / "task_store.json")
    rec = reloaded.get(record.task_id)
    assert [h["state"] for h in rec.state_history] == [
        "READY", "RUNNING", "RUNNING", "COMPLETED"]
    assert all("utc" in h for h in rec.state_history)


def test_task_record_backward_compatible_without_state_history() -> None:
    """Pre-M1.6c store JSON (no state_history) must still load."""
    from spartina.data.gee.tasks import TaskRecord

    legacy = {
        "task_id": "task-old", "request_id": "req-old",
        "state": "COMPLETED", "backend_task_id": "b",
        "attempts": 1, "max_attempts": 3, "errors": [],
        "result": {}, "enqueue_spec": {},
        "created_utc": "2026-09-01T00:00:00+00:00",
        "updated_utc": "2026-09-01T00:01:00+00:00"}
    rec = TaskRecord.from_dict(legacy)
    assert rec.state_history == []


def _write_rasters(tmp_path: Path, sr_values, mask_values):
    pytest.importorskip("numpy")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    transform = from_origin(318010.0, 3354900.0, 10.0, 10.0)
    sr_path = tmp_path / "sr.tif"
    mask_path = tmp_path / "valid.tif"
    with rasterio.open(
            sr_path, "w", driver="GTiff", width=4, height=3, count=4,
            dtype="float32", crs="EPSG:32651",
            transform=transform,
            nodata=None) as dst:
        for band in range(4):
            dst.write(sr_values[band].astype("float32"), band + 1)
    with rasterio.open(
            mask_path, "w", driver="GTiff", width=4, height=3, count=1,
            dtype="uint8", crs="EPSG:32651",
            transform=transform) as dst:
        dst.write(mask_values.astype("uint8"), 1)
    return sr_path, mask_path


def test_valid_mask_and_masked_reflectance_audits(tmp_path: Path) -> None:
    from spartina.data.gee.provenance import (
        reflectance_sanity_masked,
        valid_mask_info,
    )

    np = pytest.importorskip("numpy")
    # 4x3 window; one 0 pixel in the mask; reflectance around 0.02..0.6
    base = np.array(
        [0.02, 0.08, 0.25, 0.60, -0.001, 1.01, 0.3, 0.1,
         0.05, 0.07, 0.4, 0.5], dtype="float32")
    layers = (base, base * 1.01, base * 0.99, base * 1.05)
    sr = np.stack([layer.reshape(3, 4) for layer in layers])
    mask = np.ones((3, 4), dtype="uint8")
    mask[0, 0] = 0
    sr_path, mask_path = _write_rasters(tmp_path, sr, mask)

    info = valid_mask_info(mask_path)
    assert info["dtypes"] == ["uint8"]
    assert info["unique_values"] == [0, 1]
    assert info["valid_pixel_count"] == 11
    assert info["total_pixel_count"] == 12
    assert info["valid_fraction"] == pytest.approx(11 / 12)

    stats = reflectance_sanity_masked(
        sr_path, mask_path, ("B2", "B3", "B4", "B8"))
    assert stats["scaling_check_pass"] is True
    b2 = stats["bands"]["B2"]
    assert b2["valid_pixel_count"] == 11
    assert 0.0 < b2["median"] < 0.3
    assert b2["negative_fraction"] == pytest.approx(1 / 11)
    assert b2["over_one_fraction"] == pytest.approx(1 / 11)
    assert set(b2) >= {
        "min", "p01", "p05", "median", "p95", "p99", "max",
        "mean", "std", "negative_fraction", "over_one_fraction"}


def test_valid_mask_rejects_non_binary(tmp_path: Path) -> None:
    from spartina.data.gee.provenance import valid_mask_info

    np = pytest.importorskip("numpy")
    sr = np.zeros((4, 3, 4), dtype="float32")
    mask = np.ones((3, 4), dtype="uint8")
    mask[1, 1] = 2
    _, mask_path = _write_rasters(tmp_path, sr, mask)
    with pytest.raises(ProvenanceError, match="subset of"):
        valid_mask_info(mask_path)


def test_masked_reflectance_rejects_dn_scale(tmp_path: Path) -> None:
    from spartina.data.gee.provenance import reflectance_sanity_masked

    np = pytest.importorskip("numpy")
    dn = np.full((3, 4), 2000.0, dtype="float32")  # raw DN, scale missed
    sr = np.stack([dn, dn, dn, dn])
    mask = np.ones((3, 4), dtype="uint8")
    sr_path, mask_path = _write_rasters(tmp_path, sr, mask)
    with pytest.raises(ProvenanceError, match="scaling sanity"):
        reflectance_sanity_masked(
            sr_path, mask_path, ("B2", "B3", "B4", "B8"))


def test_pipeline_refuses_without_opt_in_env(monkeypatch: pytest.MonkeyPatch,
                                             tmp_path: Path) -> None:
    monkeypatch.delenv("SPARTINA_GEE_SMOKE_EXPORT", raising=False)
    with pytest.raises(SystemExit):
        driver.run_pipeline(
            out_dir=tmp_path, tasks_path=tmp_path / "t.json",
            tracked_manifest=tmp_path / "m.json")
