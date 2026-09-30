"""Real GEE integration smoke tests.

Auto-skip unless genuine credentials AND SPARTINA_GEE_PROJECT are present.
Never runs under the default test selection; execute manually with:

    pytest -m gee_integration

Catalog tests are metadata-only and stay tiny. The export-gate test
additionally requires SPARTINA_GEE_SMOKE_EXPORT=1, but under the fixed
2020-09-01..2020-11-01 Hangzhou-bay window the three real Landsat 8 scenes
ALL exceed the predeclared 0.30 ROI cloud threshold, so even with the
opt-in flag the driver must refuse with NO_ELIGIBLE_LANDSAT8_SCENE. That
refusal is the honest acceptance result for this window -- the test
asserts the gate CLOSES, it never fabricates a successful export.
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
# The end date is exclusive in EE filterDate; the driver uses the ISO
# instant 2020-11-01T00:00:00Z, this client-level query uses the same day.
WINDOW = ("2020-09-01", "2020-11-01")

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts" / "data" / "gee"

S1_SELECTED = (
    "S1A_IW_GRDH_1SDV_20201002T100300_20201002T100325_034616_0407DA_822F")
S2_SELECTED = "20200905T023549_20200905T024731_T51RUP"


def _load_driver(stem: str) -> object:
    """Load a scripts/data/gee driver once by its file stem."""
    if stem in sys.modules:
        return sys.modules[stem]
    spec = importlib.util.spec_from_file_location(stem, SCRIPTS / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[stem] = module
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

    Note: GEE really returns a null ``productIdentifier`` on the Sentinel-1
    GRD ingestion pipeline for these scenes. That null is recorded as
    MISSING evidence (system:index still identifies the scene); it must
    never be replaced with a fabricated product id.
    """
    client = EarthEngineCatalogClient()  # pragma: no cover
    query = SceneQuery(
        sensor_name=sensor, start_date=WINDOW[0], end_date=WINDOW[1],
        region=HZ_SMALL_ROI, max_cloud_cover=1.0,
    )
    scenes = client.query(query)  # pragma: no cover
    assert scenes, f"no {sensor} scenes returned for the small ROI"  # pragma: no cover
    for scene in scenes:  # pragma: no cover
        assert scene.scene_id
        assert scene.acquisition_time.endswith("+00:00")
        assert scene.extra.get(id_field) is not None
        product_id = scene.extra.get("product_id")
        if sensor == "sentinel1":
            # Null is a real, documented ingestion response (-> MISSING).
            assert product_id is None or isinstance(product_id, str)
        else:
            assert isinstance(product_id, str) and product_id

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


def test_real_catalog_smoke_driver_evidence(tmp_path: Path) -> None:
    """Run the real metadata driver twice and verify deterministic evidence.

    Real EE retrieval over HZB_TECH_SMOKE_V1: every candidate is retained,
    ROI-level pixel QA counts are computed server-side, and the second
    independent retrieval must reproduce both fingerprints and the scene
    id sets.
    """
    driver = _load_driver("real_catalog_smoke")
    summary = driver.run_smoke(  # type: ignore[attr-defined]
        ("landsat8", "sentinel1", "sentinel2"), tmp_path)

    assert summary["rerun_identical"] is True  # pragma: no cover
    assert summary["rerun_scene_id_sets_equal"] is True  # pragma: no cover
    assert summary["roi"]["roi_id"] == "HZB_TECH_SMOKE_V1"  # pragma: no cover

    counts = summary["counts"]  # pragma: no cover
    assert counts["landsat8"] == {  # pragma: no cover
        "candidate_count": 3, "eligible_count": 0, "selected_count": 0}
    assert counts["sentinel1"] == {  # pragma: no cover
        "candidate_count": 15, "eligible_count": 15, "selected_count": 1}
    assert counts["sentinel2"] == {  # pragma: no cover
        "candidate_count": 12, "eligible_count": 5, "selected_count": 1}

    passes = summary["s1_pass_breakdown"]  # pragma: no cover
    assert passes["ASCENDING"]["selected_scene_id"] == S1_SELECTED  # pragma: no cover
    assert passes["DESCENDING"]["selected_scene_id"] is None  # pragma: no cover
    assert passes["DESCENDING"]["candidate_count"] == 0  # pragma: no cover

    s2_pick = summary["selected_scenes"]["sentinel2"][0]  # pragma: no cover
    assert s2_pick["scene_id"] == S2_SELECTED  # pragma: no cover
    assert s2_pick["mgrs_tile"] == "51RUP"  # pragma: no cover
    s1_pick = summary["selected_scenes"]["sentinel1"][0]  # pragma: no cover
    assert s1_pick["scene_id"] == S1_SELECTED  # pragma: no cover
    assert s1_pick["relative_orbit_number"] == 69  # pragma: no cover
    assert s1_pick["selected_orbit"] == "ASCENDING"  # pragma: no cover
    assert summary["selected_scenes"]["landsat8"] == []  # pragma: no cover

    # Fingerprints must be 64-char hex and stable across the two retrievals.
    for key in ("catalog_fingerprint_sha256",  # pragma: no cover
                "selection_fingerprint_sha256"):
        fp_a = summary[f"{key}_run_1"]  # pragma: no cover
        fp_b = summary[f"{key}_run_2"]  # pragma: no cover
        assert len(fp_a) == 64 and fp_a == fp_b  # pragma: no cover

    for kind in ("json", "csv", "parquet"):  # pragma: no cover
        assert Path(summary["candidate_files"][kind]).is_file()  # pragma: no cover
    assert Path(summary["summary_path"]).is_file()  # pragma: no cover


@pytest.mark.skipif(
    os.environ.get("SPARTINA_GEE_SMOKE_EXPORT") != "1",
    reason="operator must opt in (SPARTINA_GEE_SMOKE_EXPORT=1); default run "
           "is metadata-only and the export path stays untouched",
)
def test_real_export_gate_blocks_zero_eligible_l8(tmp_path: Path) -> None:
    """Predeclared gate must CLOSE when no L8 scene is policy-eligible.

    Fixed window real result: 3 L8 candidates, ROI cloud fractions
    0.783 / 1.0 / 1.0, all above max_cloud_fraction=0.30. Even with the
    operator opt-in flag, the driver exits NO_ELIGIBLE_LANDSAT8_SCENE
    instead of widening the window or relaxing the policy. No Drive task,
    no GeoTIFF, no manifest claiming a COMPLETED export may be produced.
    """
    catalog_driver = _load_driver("real_catalog_smoke")
    summary = catalog_driver.run_smoke(  # type: ignore[attr-defined]
        ("landsat8", "sentinel1", "sentinel2"), tmp_path)
    candidates = Path(summary["candidate_files"]["json"])
    assert candidates.is_file()  # pragma: no cover
    rows = json.loads(candidates.read_text(encoding="utf-8"))  # pragma: no cover
    l8 = [r for r in rows if r["sensor"] == "landsat8"]  # pragma: no cover
    assert len(l8) == 3  # pragma: no cover
    assert not any(r["selected"] for r in l8)  # pragma: no cover

    export_driver = _load_driver("real_export_smoke")
    old_argv = sys.argv
    sys.argv = [
        "real_export_smoke.py", "--candidates", str(candidates),
        "--out-dir", str(tmp_path), "--tasks",
        str(tmp_path / "task_store.json"),
    ]
    try:
        with pytest.raises(SystemExit) as exc_info:  # pragma: no cover
            export_driver.main()  # type: ignore[attr-defined]  # pragma: no cover
    finally:
        sys.argv = old_argv
    message = str(exc_info.value.code)  # pragma: no cover
    assert "NO_ELIGIBLE_LANDSAT8_SCENE" in message  # pragma: no cover

    # Nothing export-shaped must have landed: no tracked-style manifest,
    # no GeoTIFF, no task store.
    assert not list(tmp_path.glob("*.tif"))  # pragma: no cover
    assert not list(tmp_path.glob("*.manifest.json"))  # pragma: no cover
    assert not (tmp_path / "task_store.json").exists()  # pragma: no cover
