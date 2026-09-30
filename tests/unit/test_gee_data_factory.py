"""Issue #6 GEE EO Data Factory v1 — offline unit tests.

Standard library only: every real Earth Engine call is lazy and lives
behind the ``gee_integration`` marker. These tests cover fixed grids,
QA decoders, candidate tables, PROXY tide metadata, resumable tasks,
checksum landing and v1 manifests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spartina.data.gee import landsat, sentinel1, sentinel2
from spartina.data.gee.catalog import (
    EarthEngineCatalogClient,
    MockCatalogClient,
    Region,
    SceneMetadata,
    SceneQuery,
    epoch_ms_to_iso,
)
from spartina.data.gee.export import ExportRequest, ExportTask, land_bytes
from spartina.data.gee.grid import (
    GridError,
    assert_no_forced_upsampling,
    covering_grid,
    grid_for_stream,
)
from spartina.data.gee.manifest import build_data_factory_manifest
from spartina.data.gee.quality import (
    CoverageFilter,
    build_candidate_table,
    candidate_records,
)
from spartina.data.gee.tasks import (
    STATE_COMPLETED,
    STATE_ENQUEUED,
    STATE_FAILED,
    STATE_RUNNING,
    TaskError,
    TaskRunner,
    TaskStore,
)
from spartina.data.gee.tide import PROXY_METHOD, TideProxyRecord, no_tide_metadata

GEE_PKG = Path(__file__).resolve().parents[2] / "src/spartina/data/gee"


# --------------------------------------------------------------------------
# Fixed grids
# --------------------------------------------------------------------------

def test_covering_grid_aligns_and_covers_bounds() -> None:
    grid = covering_grid((500_015.0, 3_300_025.0, 500_615.0, 3_300_625.0),
                         32651, 30.0)
    assert (grid.west % 30.0, grid.north % 30.0) == (0.0, 0.0)
    assert grid.west <= 500_015.0 and grid.east >= 500_615.0
    assert grid.south <= 3_300_025.0 and grid.north >= 3_300_625.0
    assert grid.pixel_x_m == grid.pixel_y_m == 30.0
    assert grid.crs == "EPSG:32651"
    assert grid.width == grid.height == 21  # ~600 m span, snapped outward


def test_science_streams_keep_separate_pixel_sizes() -> None:
    bounds = (500_000.0, 3_300_000.0, 500_100.0, 3_300_100.0)
    assert grid_for_stream("landsat_30m", bounds, 32651).pixel_x_m == 30.0
    assert grid_for_stream("sentinel_10m", bounds, 32651).pixel_x_m == 10.0
    with pytest.raises(GridError):
        grid_for_stream("landsat_10m_fake", bounds, 32651)


def test_forced_upsampling_is_rejected_but_downsampling_allowed() -> None:
    assert_no_forced_upsampling(30.0, 30.0)
    assert_no_forced_upsampling(10.0, 30.0)
    with pytest.raises(GridError, match="forced upsampling"):
        assert_no_forced_upsampling(30.0, 10.0)
    with pytest.raises(GridError):
        covering_grid((0, 0, 1, 0), 32651, 30.0)


# --------------------------------------------------------------------------
# Per-sensor QA decoders (pure, integer level)
# --------------------------------------------------------------------------

def test_landsat_qa_pixel_decoder() -> None:
    clear = 1 << landsat.QA_CLEAR  # explicit clear bit only
    assert landsat.qa_pixel_is_clear(clear)
    for bit in (landsat.QA_FILL, landsat.QA_DILATED_CLOUD, landsat.QA_CIRRUS,
                landsat.QA_CLOUD, landsat.QA_CLOUD_SHADOW, landsat.QA_SNOW):
        assert not landsat.qa_pixel_is_clear(clear | (1 << bit))
    assert landsat.qa_radsat_ok(0)
    assert not landsat.qa_radsat_ok(1)


def test_landsat_sensor_config_and_export_bands() -> None:
    assert landsat.supported_sensors() == (
        "landsat5", "landsat7", "landsat8", "landsat9")
    assert landsat.thermal_band("landsat5") == "ST_B6"
    assert landsat.thermal_band("landsat8") == "ST_B10"
    bands = landsat.export_bands("landsat8", include_thermal=True)
    assert bands[-3:] == ("ST_B10", "QA_PIXEL", "QA_RADSAT")
    assert "SR_B6" in landsat.sr_bands("landsat9")
    assert "SR_B6" not in landsat.sr_bands("landsat5")


def test_sentinel2_scl_decoder_and_bands() -> None:
    for cls in (4, 5, 6, 11):
        assert sentinel2.scl_is_clear(cls)
    for cls in (0, 1, 2, 3, 7, 8, 9, 10):
        assert not sentinel2.scl_is_clear(cls)
    assert sentinel2.TEN_M_BANDS == ("B2", "B3", "B4", "B8")
    assert sentinel2.export_bands(include_cloudprob=True)[-2:] == (
        "SCL", "MSK_CLDPRB")


def test_sentinel1_orbit_and_record_mapping() -> None:
    # invalid orbit is rejected before any Earth Engine object is touched
    with pytest.raises(ValueError):
        sentinel1.load_collection(None, object(), "2020-01-01",
                                  "2020-02-01", orbit_direction="SIDEWAYS")
    record = sentinel1.record_from_properties({
        "system:index": "s1-scene",
        "orbitProperties_pass": "ASCENDING",
        "relativeOrbitNumber_start": 142,
        "transmitterReceiverPolarisation": ["VV", "VH"],
        "instrumentMode": "IW", "resolution_meters": 10})
    assert record["orbit_direction"] == "ASCENDING"
    assert record["relative_orbit_number"] == 142
    assert record["polarizations"] == ("VV", "VH")


# --------------------------------------------------------------------------
# Candidate table: every candidate retained, selection explicit
# --------------------------------------------------------------------------

def _scenes() -> list[SceneMetadata]:
    return [
        SceneMetadata("good", "landsat8", "2020-06-01T02:30:00+00:00", 0.1,
                      (0, 0, 1, 1), "EPSG:32651",
                      {"product_id": "LC08_GOOD", "wrs_path": 118}),
        SceneMetadata("cloudy", "landsat8", "2020-06-17T02:30:00+00:00", 0.85,
                      (0, 0, 1, 1), "EPSG:32651",
                      {"product_id": "LC08_CLOUDY"}),
        SceneMetadata("partial", "landsat8", "2020-07-03T02:30:00+00:00", 0.05,
                      (0, 0, 1, 1), "EPSG:32651",
                      {"product_id": "LC08_PART"}),
    ]


def test_candidate_table_keeps_rejections_and_marks_selection() -> None:
    table = build_candidate_table(
        _scenes(), frozenset({"good", "partial"}),
        coverage_by_scene={"partial": 0.4},
        pixel_quality_by_scene={"good": {"valid_pixel_fraction": 0.97}},
        selected_scene_id="good")
    records = candidate_records(table)
    by_id = {row["scene_id"]: row for row in records}
    assert len(records) == 3
    assert by_id["cloudy"]["accepted"] is False
    assert "failed_qa_or_metadata_filter" in by_id["cloudy"][
        "rejection_reasons"]
    assert by_id["good"]["selected"] is True
    assert by_id["good"]["valid_pixel_fraction"] == 0.97
    assert "partial_footprint_coverage" in by_id["partial"][
        "rejection_reasons"]
    with pytest.raises(KeyError):
        build_candidate_table(_scenes(), frozenset({"ghost_scene"}))
    with pytest.raises(ValueError):
        build_candidate_table(_scenes(), frozenset({"good"}),
                              selected_scene_id="cloudy")


def test_coverage_filter_unknown_does_not_autopass() -> None:
    rule = CoverageFilter(0.9)
    assert rule.accept(0.95)
    assert not rule.accept(0.5)
    assert not rule.accept(None)


# --------------------------------------------------------------------------
# Tide proxy is PROXY only
# --------------------------------------------------------------------------

def test_tide_records_are_explicitly_proxy() -> None:
    rec = no_tide_metadata("scene-1", "2020-06-01T02:30:00+00:00")
    payload = rec.to_record()
    assert payload["method"] == PROXY_METHOD
    assert payload["gauge_observed"] is False
    with pytest.raises(ValueError):
        TideProxyRecord("s", None, proxy_basis="x", proxy_value=None,
                        method="GAUGE_OBSERVED")
    with pytest.raises(ValueError):
        TideProxyRecord("s", None, proxy_basis="x", proxy_value=None,
                        gauge_observed=True)
    with pytest.raises(ValueError):
        TideProxyRecord("s", None, proxy_basis="", proxy_value=None)


# --------------------------------------------------------------------------
# Resumable task store
# --------------------------------------------------------------------------

class _FakeBackend:
    def __init__(self, fail_enqueue: int = 0, poll_states: tuple = ()) -> None:
        self.fail_enqueue = fail_enqueue
        self.poll_states = list(poll_states)
        self.enqueued: list[dict] = []
        self.polls: list[str] = []

    def enqueue(self, spec: dict) -> str:
        if self.fail_enqueue > 0:
            self.fail_enqueue -= 1
            raise RuntimeError("transient GEE outage")
        self.enqueued.append(spec)
        return f"bee-{len(self.enqueued)}"

    def poll(self, backend_task_id: str) -> dict:
        self.polls.append(backend_task_id)
        state = self.poll_states.pop(0)
        if state == STATE_FAILED:
            return {"state": state, "error": "backend boom"}
        return {"state": state, "result": {"ok": True}}


def test_task_store_retry_resume_and_persistence(tmp_path: Path) -> None:
    store_path = tmp_path / "tasks.json"
    backend = _FakeBackend(fail_enqueue=1,
                           poll_states=(STATE_ENQUEUED, STATE_COMPLETED))
    runner = TaskRunner(TaskStore(store_path), backend)
    rec = runner.submit("req-1", {"image": "x"}, max_attempts=3)
    assert rec.attempts == 1 and rec.state == STATE_ENQUEUED
    rec = runner.poll_once(rec.task_id)
    assert rec.state == STATE_ENQUEUED
    rec = runner.poll_once(rec.task_id)
    assert rec.state == STATE_COMPLETED and rec.result == {"ok": True}
    assert len(backend.enqueued) == 1  # first enqueue failed, retried once

    # crash simulation: reload store from disk and resume
    reloaded = TaskStore(store_path)
    assert reloaded.get(rec.task_id).state == STATE_COMPLETED
    assert reloaded.list_non_terminal() == []


def test_task_store_fails_after_max_attempts(tmp_path: Path) -> None:
    backend = _FakeBackend(fail_enqueue=5)
    runner = TaskRunner(TaskStore(tmp_path / "t.json"), backend)
    rec = runner.submit("req-x", {}, max_attempts=2)
    assert rec.state == STATE_FAILED
    assert len(rec.errors) == 2
    assert "transient GEE outage" in rec.errors[0]["message"]
    assert runner.store.counts() == {STATE_FAILED: 1}


def test_poll_failure_re_enqueues_then_completes(tmp_path: Path) -> None:
    backend = _FakeBackend(poll_states=(STATE_FAILED, STATE_RUNNING,
                                        STATE_COMPLETED))
    runner = TaskRunner(TaskStore(tmp_path / "t.json"), backend)
    rec = runner.submit("req-r", {"bands": ["B4"]})
    rec = runner.poll_once(rec.task_id)  # backend fails once -> re-enqueue
    assert rec.state == STATE_ENQUEUED and rec.backend_task_id == "bee-2"
    runner.poll_once(rec.task_id)
    final = runner.poll_once(rec.task_id)
    assert final.state == STATE_COMPLETED


def test_task_ids_are_deterministic_and_unique(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "t.json")
    first = store.create("same-request")
    second = store.create("other-request")
    assert first.task_id != second.task_id
    with pytest.raises(TaskError):
        store.create("same-request")


# --------------------------------------------------------------------------
# Checksum landing + v1 manifest
# --------------------------------------------------------------------------

def test_land_bytes_checksums_and_rejects_mismatch(tmp_path: Path) -> None:
    dest = tmp_path / "scene.tif"
    info = land_bytes(dest, b"payload-bytes")
    assert info["size_bytes"] == 13
    assert dest.read_bytes() == b"payload-bytes"
    assert not (tmp_path / "scene.tif.part").exists()
    with pytest.raises(ValueError, match="checksum mismatch"):
        land_bytes(dest, b"payload-bytes", expected_sha256="deadbeef")


def _export_request() -> ExportRequest:
    grid = grid_for_stream(
        "landsat_30m",
        (500_000.0, 3_300_000.0, 500_300.0, 3_300_300.0), 32651)
    return ExportRequest(
        request_id="req-hz-1", sensor_name="landsat8", tile_id="hz-pilot-1",
        start_date="2015-06-01", end_date="2015-08-31",
        destination_uri="datasets/raw/hz-pilot-1/",
        bands=("SR_B2", "SR_B3", "SR_B4", "SR_B5"), crs_epsg=32651,
        resolution_m=30.0, grid_spec=grid.to_dict(),
        source_scene_ids=("good",), science_stream="landsat_30m")


def test_data_factory_manifest_chain_and_guards(tmp_path: Path) -> None:
    table = build_candidate_table(_scenes(), frozenset({"good"}),
                                  selected_scene_id="good")
    info = land_bytes(tmp_path / "scene.tif", b"bytes")
    task = ExportTask(task_id="task-1", request_id="req-hz-1",
                      state=STATE_COMPLETED)
    tide = no_tide_metadata("good").to_record()
    payload = build_data_factory_manifest(
        _export_request(), task,
        candidate_scenes=candidate_records(table),
        selected_scene_ids=["good"],
        grid_spec=grid_for_stream(
            "landsat_30m", (500_000.0, 3_300_000.0, 500_300.0, 3_300_300.0),
            32651).to_dict(),
        processing_config={"qa": "QA_PIXEL clear + QA_RADSAT == 0",
                           "scale": "C2 L2 2.75e-5 - 0.2"},
        landed_files=[info], tide_records=[tide],
        roi={"type": "Polygon", "name": "hangzhou-pilot-small"})
    assert payload["manifest_version"] == "GEE_DATA_FACTORY_V1"
    assert payload["selected_scene_ids"] == ["good"]
    assert len(payload["candidate_scenes"]) == 3
    assert payload["tide_inundation"][0]["method"] == "PROXY"
    assert payload["landed_files"][0]["sha256"]
    json.dumps(payload)  # fully serializable

    with pytest.raises(ValueError, match="candidate table"):
        build_data_factory_manifest(
            _export_request(), task,
            candidate_scenes=candidate_records(table),
            selected_scene_ids=["ghost"], grid_spec={},
            processing_config={}, landed_files=[info])
    with pytest.raises(ValueError, match="grid_spec missing"):
        build_data_factory_manifest(
            _export_request(), task,
            candidate_scenes=candidate_records(table),
            selected_scene_ids=["good"], grid_spec={"crs": "X"},
            processing_config={}, landed_files=[info])
    with pytest.raises(ValueError, match="checksum"):
        bad_info = dict(info)
        bad_info["sha256"] = None
        build_data_factory_manifest(
            _export_request(), task,
            candidate_scenes=candidate_records(table),
            selected_scene_ids=["good"],
            grid_spec=_export_request().grid_spec or {},
            processing_config={}, landed_files=[bad_info])


# --------------------------------------------------------------------------
# Lazy EE / no-network guarantees
# --------------------------------------------------------------------------

def test_no_gee_module_imports_earth_engine_at_top_level() -> None:
    for path in sorted(GEE_PKG.glob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            # only column-0 imports count as module-level; function-local
            # lazy imports are indented and are exactly what we require
            assert not (line.startswith("import ee")
                        or line.startswith("from ee")), (
                f"{path.name}:{lineno} imports ee at module level")


def test_real_catalog_client_is_blocked_without_auth() -> None:
    client = EarthEngineCatalogClient()
    query = SceneQuery(
        sensor_name="landsat8", start_date="2015-06-01",
        end_date="2015-08-31",
        region=Region({"type": "Polygon"}, 32651))
    with pytest.raises(RuntimeError, match="BLOCKED_BY_AUTH"):
        client.query(query)


def test_epoch_ms_to_iso() -> None:
    iso = epoch_ms_to_iso(1_433_116_800_000)  # 2015-06-01T00:00:00Z
    assert iso is not None and iso.endswith("+00:00")
    assert iso.startswith("2015-06-01")
    assert epoch_ms_to_iso(None) is None


def test_mock_catalog_still_works_after_v1_extensions() -> None:
    client = MockCatalogClient(tuple(_scenes()))
    result = client.query(SceneQuery(
        sensor_name="landsat8", start_date="2015-01-01",
        end_date="2015-12-31", region=Region({"type": "Polygon"}, 32651),
        max_cloud_cover=0.5))
    assert {s.scene_id for s in result} == {"good", "partial"}


# --------------------------------------------------------------------------
# Best-single-scene selection policy (Issue #6 real integration)
# --------------------------------------------------------------------------

def _candidate(
    scene_id: str, *, coverage: float | None = 1.0,
    valid: float | None = 1.0, cloud: float | None = 0.05,
    accepted: bool = True, when: str = "2020-09-15T02:00:00+00:00",
) -> dict[str, object]:
    return {
        "scene_id": scene_id,
        "sensor": "landsat8",
        "acquisition_utc": when,
        "accepted": accepted,
        "footprint_coverage_fraction": coverage,
        "valid_pixel_fraction": valid,
        "cloud_cover_fraction": cloud,
        "quality_extras": {},
        "rejection_reasons": [],
    }


def test_policy_rejects_unknown_low_coverage_and_cloud() -> None:
    from spartina.data.gee.selection import (
        REASON_HIGH_CLOUD,
        REASON_LOW_COVERAGE,
        REASON_LOW_VALID,
        REASON_UNKNOWN_COVERAGE,
        SingleScenePolicy,
        rejection_reasons,
    )

    policy = SingleScenePolicy(target_doy=275)
    assert rejection_reasons(_candidate("a", coverage=None), policy) == (
        REASON_UNKNOWN_COVERAGE,)
    assert REASON_LOW_COVERAGE in rejection_reasons(
        _candidate("b", coverage=0.8), policy)
    assert REASON_LOW_VALID in rejection_reasons(
        _candidate("c", valid=0.5), policy)
    assert REASON_HIGH_CLOUD in rejection_reasons(
        _candidate("d", cloud=0.9), policy)


def test_best_scene_is_deterministic_on_coverage_valid_cloud_season() -> None:
    from spartina.data.gee.selection import (
        SingleScenePolicy,
        best_single_scene,
    )

    policy = SingleScenePolicy(target_doy=275)
    rows = [
        _candidate("far_season", when="2020-09-20T00:00:00+00:00"),
        _candidate("more_valid", valid=0.99,
                   when="2020-10-05T00:00:00+00:00"),
        _candidate("fully_valid", valid=1.0, cloud=0.02,
                   when="2020-10-10T00:00:00+00:00"),
        _candidate("not_accepted", accepted=False),
    ]
    chosen = best_single_scene(rows, policy)
    assert chosen is not None and chosen["scene_id"] == "fully_valid"
    # deterministic under reordering
    import random
    for seed in range(5):
        shuffled = rows[:]
        random.Random(seed).shuffle(shuffled)
        again = best_single_scene(shuffled, policy)
        assert again is not None and again["scene_id"] == "fully_valid"


def test_sar_scene_without_cloud_metadata_is_selectable() -> None:
    from spartina.data.gee.selection import (
        SingleScenePolicy,
        best_single_scene,
        circular_doy_distance,
    )

    policy = SingleScenePolicy(target_doy=275)
    sar = _candidate("S1A_IW", cloud=None)
    assert best_single_scene([sar], policy)["scene_id"] == "S1A_IW"
    assert circular_doy_distance(360, 10) == 15
    assert best_single_scene([], policy) is None


def test_candidate_record_carries_polarizations() -> None:
    scene = SceneMetadata(
        scene_id="s1", sensor_name="sentinel1",
        acquisition_time="2020-09-15T00:00:00+00:00",
        cloud_cover=None, bbox=(0.0, 0.0, 1.0, 1.0), crs="EPSG:4326",
        extra={"polarizations": ["VV", "VH"]})
    table = build_candidate_table([scene], frozenset({"s1"}))
    row = table[0].to_record()
    assert row["polarizations"] == ["VV", "VH"]


def test_project_env_var_is_required_by_initialize(monkeypatch: pytest.MonkeyPatch) -> None:
    from spartina.data.gee import auth

    monkeypatch.setattr(auth, "credentials_available", lambda: True)
    monkeypatch.delenv("SPARTINA_GEE_PROJECT", raising=False)
    assert auth.configured_project() is None
    with pytest.raises(RuntimeError, match="SPARTINA_GEE_PROJECT"):
        auth.initialize()
