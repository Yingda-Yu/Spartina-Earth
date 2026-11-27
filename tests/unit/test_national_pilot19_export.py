"""Unit tests for the Issue #19 Phase D/E national pilot export driver.

Only offline, deterministic pieces are tested: frozen-plan scope gating,
component/band accounting, the shared UTM grid rule (checked against the
frozen Phase F/G label-support manifest), deterministic task naming and
the state rollup. Live GEE/Drive paths live behind gee_integration.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts/data/national" / "pilot19_export_products.py"
_LABEL_SUPPORTS = (
    REPO_ROOT / "datasets/manifests"
    / "national_pilot19_label_supports_v1.csv")

FROZEN_PLAN_CSV_SHA256 = (
    "ebc36a5a3b5e5f97ff603526e8e66a10e96a2344158748436d0b4aedb6f80769")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "pilot19_export_products", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load_module()


def test_frozen_plan_checksum() -> None:
    assert m.plan_csv_sha256() == FROZEN_PLAN_CSV_SHA256


def test_full_scope_is_frozen_194_products_402_tasks() -> None:
    scope = m.load_scope(canary=False, only_sensor=None)
    assert len(scope) == 194
    assert all(r["status"] == "SELECTED" for r in scope)
    n_tasks = sum(len(m.COMPONENTS[str(r["sensor"])]) for r in scope)
    assert n_tasks == 402


def test_canary_scope_is_five_named_products() -> None:
    scope = m.load_scope(canary=True, only_sensor=None)
    by_sensor = {str(r["sensor"]): str(r["product_id"]) for r in scope}
    assert by_sensor == {
        "landsat5": "NP19_R00226-C00080_L5_1990",
        "landsat7": "NP19_R00264-C00132_L7_2000",
        "landsat8": "NP19_R00311-C00156_L8_2021",
        "sentinel1": "NP19_R00347-C00151_S1_2015_A",
        "sentinel2": "NP19_R00388-C00129_S2_2020",
    }
    # 3 + 3 + 3 + 1 + 2 = 12 canary component tasks.
    assert sum(len(m.COMPONENTS[str(r["sensor"])]) for r in scope) == 12


def test_scope_filters() -> None:
    l5 = m.load_scope(canary=False, only_sensor="landsat5")
    assert {str(r["sensor"]) for r in l5} == {"landsat5"}
    one = m.load_scope(
        canary=False, only_sensor=None,
        products_filter=("NP19_R00311-C00156_L8_2021",))
    assert len(one) == 1
    with pytest.raises(ValueError, match="not eligible in frozen v1 plan"):
        m.load_scope(
            canary=False, only_sensor=None,
            products_filter=("NP19_DOES_NOT_EXIST",))


def test_component_accounting() -> None:
    assert m.COMPONENTS["landsat5"] == ("sr", "valid", "qapixel")
    assert m.COMPONENTS["landsat7"] == ("sr", "valid", "qapixel")
    assert m.COMPONENTS["landsat8"] == ("sr", "valid", "qapixel")
    assert m.COMPONENTS["sentinel2"] == ("sr", "valid")
    assert m.COMPONENTS["sentinel1"] == ("vvvh",)


def test_landsat_scaling_audit_band_accounting() -> None:
    def stats(n: int) -> dict[str, float]:
        out: dict[str, float] = {}
        for i in range(1, n + 1):
            out.update({
                f"sr_b{i}_min": 0.0, f"sr_b{i}_p01": 0.01,
                f"sr_b{i}_p50": 0.1, f"sr_b{i}_p99": 0.5,
                f"sr_b{i}_max": 0.8})
        return out

    a5 = m.landsat_scaling_audit("landsat5", stats(6))
    a7 = m.landsat_scaling_audit("landsat8", stats(7))
    assert a5["n_sr_bands"] == 6 and a5["pass"]
    assert a7["n_sr_bands"] == 7 and a7["pass"]
    assert len(a5["checks"]) == 12 and len(a7["checks"]) == 14
    bad = dict(stats(6))
    bad["sr_b1_p99"] = 2.0  # unphysical
    assert not m.landsat_scaling_audit("landsat5", bad)["pass"]


def test_role_revision_table() -> None:
    # r2 landsat VALID (all-SR-bands-observed); every other component r1.
    assert m.role_revision("landsat5", "valid") == "r2"
    assert m.role_revision("landsat7", "valid") == "r2"
    assert m.role_revision("landsat8", "valid") == "r2"
    assert m.role_revision("landsat8", "sr") == "r1"
    assert m.role_revision("landsat8", "qapixel") == "r1"
    assert m.role_revision("sentinel2", "valid") == "r1"
    assert m.role_revision("sentinel1", "vvvh") == "r1"


def test_deterministic_naming() -> None:
    row = {"product_id": "NP19_R00226-C00080_L5_1990",
           "sensor": "landsat5",
           "event_utc": "1990-10-29T00:00:00+00:00"}
    assert (m.prefix_for(row, "sr")
            == "spartina_pilot19_NP19_R00226-C00080_L5_1990_sr_19901029_r1")
    assert m.request_for(row, "qapixel") == (
        "NP19_R00226-C00080_L5_1990:qapixel:r1")
    # Landsat VALID moved to r2 after the pilot D1 per-band nodata finding.
    assert (m.prefix_for(row, "valid")
            == "spartina_pilot19_NP19_R00226-C00080_L5_1990_valid_"
               "19901029_r2")
    assert m.request_for(row, "valid") == (
        "NP19_R00226-C00080_L5_1990:valid:r2")
    assert m.date_tag(row) == "19901029"
    # Non-landsat components keep r1.
    s2 = {"product_id": "NP19_P_S2_2020", "sensor": "sentinel2",
          "event_utc": "2020-09-18T02:45:49+00:00"}
    assert m.request_for(s2, "valid") == "NP19_P_S2_2020:valid:r1"
    assert (m.prefix_for(s2, "valid")
            == "spartina_pilot19_NP19_P_S2_2020_valid_20200918_r1")


def test_summarize_states_priority_and_counts() -> None:
    pids = ["a", "b", "c", "d", "e"]
    summary = m.summarize_states(
        pids, landed={"a"}, failed={"b", "c"},
        active={"b": "RUNNING", "d": "SUBMITTED"})
    # LANDED beats a stale failure ledger entry; active beats failure.
    assert summary["by_product"] == {
        "a": "LANDED", "b": "RUNNING", "c": "EXPORT_FAILED",
        "d": "SUBMITTED", "e": "SELECTED"}
    assert summary["states"] == {
        "SELECTED": 1, "SUBMITTED": 1, "RUNNING": 1,
        "LANDED": 1, "EXPORT_FAILED": 1}


def test_export_grids_match_frozen_label_supports_for_all_cells() -> None:
    panel = m.load_panel()
    supports = pd.read_csv(_LABEL_SUPPORTS)
    scope = m.load_scope(canary=False, only_sensor=None)
    cells = sorted({str(r["cell_id"]) for r in scope})
    assert len(cells) == 20
    checked = 0
    for cell in cells:
        for sensor in ("landsat8", "sentinel2"):
            pixel_m = 30 if sensor.startswith("landsat") else 10
            row = next(r for r in scope
                       if str(r["cell_id"]) == cell
                       and str(r["sensor"]) == sensor)
            grid, _region, zone = m.product_grid(row, panel)
            label_rows = supports[
                (supports.cell_id == cell)
                & (supports.support_m == pixel_m)]
            assert not label_rows.empty
            for lab in label_rows.itertuples():
                assert int(lab.crs_epsg) == grid.crs_epsg
                assert int(lab.utm_zone) == zone
                assert int(lab.width) == grid.width
                assert int(lab.height) == grid.height
                assert zone in (49, 50, 51, 52)
                checked += 1
    # 10 support rows at 30 m (GEODATA x4, CMSA 2017-2021 x5, CM-SSM 30 m)
    # plus 1 at 10 m (CM-SSM 10 m) for each of the 20 cells = 220.
    assert checked == 220


def test_task_adoption_rule_prevents_duplicate_resume_submission() -> None:
    from spartina.data.gee.tasks import (
        STATE_ENQUEUED,
        STATE_PENDING,
        STATE_RUNNING,
        TaskRecord,
    )

    def rec(state: str, backend: str | None) -> TaskRecord:
        return TaskRecord(task_id="task-x", request_id="pid:sr:r1",
                          state=state, backend_task_id=backend)

    assert m.task_is_adoptable(rec(STATE_ENQUEUED, "GEE1"))
    assert m.task_is_adoptable(rec(STATE_RUNNING, "GEE1"))
    assert m.task_is_adoptable(rec("COMPLETED", "GEE1"))
    # PENDING = a recorded failed attempt that still owes a retry.
    assert not m.task_is_adoptable(rec(STATE_PENDING, "GEE1"))
    # Never created / never started.
    assert not m.task_is_adoptable(rec(STATE_PENDING, None))


def _write_float_geotiff(path: Path, arrs: list, crs: str = "EPSG:32651") -> None:
    import rasterio
    from rasterio.transform import from_origin

    profile = {
        "driver": "GTiff", "height": arrs[0].shape[0],
        "width": arrs[0].shape[1], "count": len(arrs),
        "dtype": "float32", "crs": crs,
        "transform": from_origin(500000.0, 3400000.0, 30.0, 30.0)}
    with rasterio.open(path, "w", **profile) as dst:
        for i, arr in enumerate(arrs, start=1):
            dst.write(arr.astype("float32"), i)


def _write_valid_byte(path: Path, valid) -> None:
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(
            path, "w", driver="GTiff", height=valid.shape[0],
            width=valid.shape[1], count=1, dtype="uint8",
            crs="EPSG:32651",
            transform=from_origin(500000.0, 3400000.0, 30.0, 30.0)) as dst:
        dst.write(valid.astype("uint8"), 1)


def test_landsat_physical_audit_clean_passes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import numpy as np

    band = np.full((4, 4), 0.1, dtype="float32")
    sr = tmp_path / "sr.tif"
    valid = tmp_path / "valid.tif"
    _write_float_geotiff(sr, [band] * 6)
    _write_valid_byte(valid, np.ones((4, 4), dtype="uint8"))
    detail, _ = m.landsat_physical_audit("landsat5", str(sr), str(valid))
    assert detail["pass"]


def test_landsat_physical_audit_nonfinite_in_valid_fails(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import numpy as np

    band = np.full((4, 4), 0.1, dtype="float32")
    band[0, 0] = np.nan
    sr = tmp_path / "sr.tif"
    valid = tmp_path / "valid.tif"
    _write_float_geotiff(sr, [band] * 7)
    _write_valid_byte(valid, np.ones((4, 4), dtype="uint8"))
    detail, _ = m.landsat_physical_audit("landsat8", str(sr), str(valid))
    assert not detail["checks"]["sr_b1_no_nonfinite_in_valid"]
    assert not detail["pass"]


def test_landsat_physical_audit_zero_valid_warns_but_passes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import numpy as np

    band = np.full((4, 4), 0.1, dtype="float32")
    sr = tmp_path / "sr.tif"
    valid = tmp_path / "valid.tif"
    _write_float_geotiff(sr, [band] * 6)
    _write_valid_byte(valid, np.zeros((4, 4), dtype="uint8"))
    detail, stats = m.landsat_physical_audit(
        "landsat5", str(sr), str(valid))
    # Zero QA-valid surface pixels is source-scene quality, not an export
    # defect: the product lands with an explicit warning.
    assert detail["zero_valid_pixels"]
    assert detail["warnings"]
    assert detail["pass"]
    assert stats["sr_b1_valid_px"] == 0
    assert stats["sr_b1_valid_p50"] is None


def test_landsat_physical_audit_saturation_rules(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import numpy as np

    cap = m.SR_SATURATION_CAP

    # Saturation OUTSIDE the valid mask is physical and allowed.
    band = np.full((4, 4), 0.1, dtype="float32")
    band[:, 2:] = cap
    valid_arr = np.ones((4, 4), dtype="uint8")
    valid_arr[:, 2:] = 0
    sr = tmp_path / "sr_out.tif"
    vd = tmp_path / "valid_out.tif"
    _write_float_geotiff(sr, [band] * 6)
    _write_valid_byte(vd, valid_arr)
    detail, _ = m.landsat_physical_audit("landsat7", str(sr), str(vd))
    assert detail["pass"]

    # Saturation INSIDE valid above the 0.1% hard fraction fails.
    saturated = np.full((4, 4), cap, dtype="float32")
    sr2 = tmp_path / "sr_in.tif"
    vd2 = tmp_path / "valid_in.tif"
    _write_float_geotiff(sr2, [saturated] * 6)
    _write_valid_byte(vd2, np.ones((4, 4), dtype="uint8"))
    detail2, _ = m.landsat_physical_audit("landsat7", str(sr2), str(vd2))
    assert not detail2["checks"][
        "sr_b1_saturation_in_valid_below_hard_fraction"]
    assert not detail2["pass"]


def _write_vvvh_geotiff(path: Path, vv, vh) -> None:
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(
            path, "w", driver="GTiff", height=vv.shape[0],
            width=vv.shape[1], count=2, dtype="float32",
            crs="EPSG:32651",
            transform=from_origin(330020.0, 3502310.0, 10.0, 10.0)) as dst:
        dst.write(vv.astype("float32"), 1)
        dst.write(vh.astype("float32"), 2)
        dst.set_band_description(1, "VV")
        dst.set_band_description(2, "VH")


def test_s1_physical_audit_clean_and_point_target_tail(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import numpy as np

    rng = np.random.default_rng(0)
    vv = rng.normal(-12.0, 4.0, (32, 32)).astype("float32")
    vh = rng.normal(-22.0, 5.0, (32, 32)).astype("float32")
    # One harbour point target at +34 dB and one dark-water null at -53 dB:
    # 1/1024 = 9.8e-4 is within the 1e-3 sparse-tail allowance.
    vv[0, 0] = 34.0
    vh[1, 1] = -53.0
    p = tmp_path / "s1.tif"
    _write_vvvh_geotiff(p, vv, vh)
    detail = m.s1_physical_audit(str(p))
    assert detail["pass"]
    assert detail["bands"]["VV"]["physical_tail_pixels"] == 1
    assert detail["bands"]["VH"]["physical_tail_pixels"] == 1
    assert detail["checks"]["VV_no_pixels_beyond_hard_envelope"]


def test_s1_physical_audit_extreme_floor_is_not_a_raw_reject(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """F3: <= -70 dB floor pixels are counted, never rejected on raw bytes."""
    import numpy as np

    vv = np.full((32, 32), -12.0, dtype="float32")
    vh = np.full((32, 32), -22.0, dtype="float32")
    vv[0, 0] = -80.031   # discrete GEE frame-border floor
    vh[0, 0] = -80.031
    vv[1, 1] = -71.0     # at/below floor but not the discrete value
    p = tmp_path / "s1_floor.tif"
    _write_vvvh_geotiff(p, vv, vh)
    detail = m.s1_physical_audit(str(p))
    # Raw identity raster passes: floor is an observation-validity matter.
    assert detail["pass"]
    assert detail["bands"]["VV"]["at_or_below_extreme_floor_pixels"] == 2
    assert detail["bands"]["VH"]["at_or_below_extreme_floor_pixels"] == 1
    # Floor pixels are excluded from the physical sparse-tail gate.
    assert detail["bands"]["VV"]["physical_tail_pixels"] == 0
    assert detail["extreme_floor_rule_db"] == -70.0


def test_s1_physical_audit_tail_above_fraction_fails(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import numpy as np

    vv = np.full((32, 32), -12.0, dtype="float32")
    vh = np.full((32, 32), -22.0, dtype="float32")
    vv.flat[:5] = 35.0  # 5/1024 ~ 4.9e-3 point targets: systematic, fails
    p = tmp_path / "s1_tail.tif"
    _write_vvvh_geotiff(p, vv, vh)
    detail = m.s1_physical_audit(str(p))
    assert not detail["checks"]["VV_tail_below_hard_fraction"]
    assert not detail["pass"]


def test_v2_plan_checksum_and_scope_is_187_eligible() -> None:
    checksum = m.plan_csv_sha256("v2")
    assert checksum  # the frozen V2 plan gates on its embedded sha256
    scope = m.load_scope(
        canary=False, only_sensor=None, plan_version="v2")
    assert len(scope) == 187
    by_sensor: dict[str, int] = {}
    for row in scope:
        by_sensor[str(row["sensor"])] = by_sensor.get(str(row["sensor"]), 0) + 1
        if str(row["sensor"]).startswith("landsat"):
            assert row["status"] == "SELECTED"
            assert row["v2_change"] == m.CHANGE_LANDSAT
        else:
            assert row["status"] == m.STATUS_V2_ELIGIBLE
            assert row["v2_change"] in (
                m.CHANGE_KEPT, m.CHANGE_REPLACED)
    assert by_sensor == {
        "landsat5": 27, "landsat7": 6, "landsat8": 50,
        "sentinel1": 67, "sentinel2": 37}
    # The seven honest drops are excluded, never padded to 194.
    assert len(scope) < 194
    # GEE export tasks: 83 landsat x 3 + 37 S2 x 2 + 67 S1 x 1 = 390;
    # the 67 s1_dualpol_valid_v2 tokens are local derivations, not tasks.
    n_gee = sum(len(m.COMPONENTS[str(r["sensor"])]) for r in scope)
    n_derived = sum(
        len(m.DERIVED_COMPONENTS_V2[str(r["sensor"])]) for r in scope)
    assert n_gee == 390
    assert n_derived == 67


def test_v2_canary_is_four_required_case_types() -> None:
    scope = m.load_scope(canary=True, only_sensor=None, plan_version="v2")
    pids = {str(r["product_id"]) for r in scope}
    assert pids == {
        "NP19_R00260-C00128_S2_2020",       # previously empty S2
        "NP19_R00264-C00132_S1_2020_A",     # previously partial S1
        "NP19_R00226-C00080_S2_2020",       # normal kept S2
        "NP19_R00226-C00080_S1_2020_A"}     # normal kept S1
    allow = pd.read_csv(m.CANARY_V2_CSV).set_index("product_id")
    assert set(allow["canary_case"]) == {
        "previously_empty_s2", "previously_partial_s1",
        "normal_kept_s2", "normal_kept_s1"}
    # Two replacement exports (S2 2 raw tasks, S1 1), two retained rows.
    repl = [r for r in scope if r["v2_change"] == m.CHANGE_REPLACED]
    kept = [r for r in scope if r["v2_change"] == m.CHANGE_KEPT]
    assert len(repl) == 2 and len(kept) == 2


def test_v2_component_revisions_keep_r1_and_bump_replacements_to_r2() -> None:
    kept_s1 = {"product_id": "NP19_KEEP_S1_2020_A", "sensor": "sentinel1",
               "event_utc": "2020-10-10T10:33:32+00:00",
               "v2_change": m.CHANGE_KEPT}
    repl_s1 = {"product_id": "NP19_REPL_S1_2020_A", "sensor": "sentinel1",
               "event_utc": "2020-10-12T10:17:35+00:00",
               "v2_change": m.CHANGE_REPLACED}
    kept_s2 = {"product_id": "NP19_KEEP_S2_2020", "sensor": "sentinel2",
               "event_utc": "2020-10-26T03:12:11+00:00",
               "v2_change": m.CHANGE_KEPT}
    repl_s2 = {"product_id": "NP19_REPL_S2_2020", "sensor": "sentinel2",
               "event_utc": "2020-10-10T02:51:19+00:00",
               "v2_change": m.CHANGE_REPLACED}
    # Retained raw bytes keep r1 and their V1 request ids.
    assert m.component_revision(kept_s1, "vvvh", "v2") == "r1"
    assert m.component_revision(kept_s2, "sr", "v2") == "r1"
    assert m.request_for(kept_s1, "vvvh", plan_version="v2") == (
        "NP19_KEEP_S1_2020_A:vvvh:r1")
    # Replaced events export under r2 so the old r1 task is never adopted.
    assert m.component_revision(repl_s1, "vvvh", "v2") == "r2"
    assert m.component_revision(repl_s2, "sr", "v2") == "r2"
    assert m.component_revision(repl_s2, "valid", "v2") == "r2"
    assert m.request_for(repl_s1, "vvvh", plan_version="v2") == (
        "NP19_REPL_S1_2020_A:vvvh:r2")
    assert (m.prefix_for(repl_s1, "vvvh", plan_version="v2")
            == "spartina_pilot19_NP19_REPL_S1_2020_A_vvvh_20201012_r2")
    # Derived token naming is revision v2 and never a GEE request id.
    assert (m.prefix_for(repl_s1, m.S1_VALID_V2_ROLE,
                         revision=m.S1_VALID_V2_REVISION)
            == "spartina_pilot19_NP19_REPL_S1_2020_A_dualpol_valid_v2_"
               "20201012_v2")
    # Landsat revisions are untouched by V2.
    l8 = {"product_id": "NP19_X_L8_2020", "sensor": "landsat8",
          "event_utc": "2020-10-02T00:00:00+00:00",
          "v2_change": m.CHANGE_LANDSAT}
    assert m.component_revision(l8, "sr", "v2") == "r1"
    assert m.component_revision(l8, "valid", "v2") == "r2"
    # Default plan version stays V1 even for rows carrying V2 columns.
    assert m.component_revision(repl_s2, "sr", "v1") == "r1"


def test_v2_eligibility_filter_excludes_honest_drops() -> None:
    frame = pd.DataFrame([
        {"sensor": "sentinel2", "status": "V2_ELIGIBLE",
         "v2_change": m.CHANGE_KEPT},
        {"sensor": "sentinel1", "status": "NO_ELIGIBLE_EVENT_ACTUAL_MASK",
         "v2_change": "V1_SELECTED_BUT_NO_ELIGIBLE_ACTUAL_MASK"},
        {"sensor": "sentinel2", "status": "NO_SCENE", "v2_change": None},
        {"sensor": "landsat8", "status": "SELECTED",
         "v2_change": m.CHANGE_LANDSAT},
        {"sensor": "landsat5", "status": "NO_ELIGIBLE_EVENT",
         "v2_change": m.CHANGE_LANDSAT},
    ])
    out = m._v2_eligible(frame)
    assert len(out) == 2
    assert set(out["sensor"]) == {"sentinel2", "landsat8"}


def test_s1_dualpol_valid_v2_token_rules(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import numpy as np

    vv = np.full((4, 4), -12.0, dtype="float32")
    vh = np.full((4, 4), -20.0, dtype="float32")
    vv[0, 0] = np.nan          # source non-observation
    vv[0, 1] = -80.031         # discrete floor in VV
    vh[0, 1] = -80.031
    vv[0, 2] = -69.5           # above the floor: stays observed
    raw = tmp_path / "raw_vvvh.tif"
    _write_vvvh_geotiff(raw, vv, vh)
    stats = m.s1_dualpol_valid_v2_stats(str(raw))
    assert stats["grid_pixels"] == 16
    # 1 NaN + 1 floor pixel excluded: 14 of 16 valid; 15 dual-finite.
    assert stats["valid_pixels"] == 14
    assert stats["actual_observed_fraction"] == 14 / 16
    assert stats["dualpol_finite_fraction"] == 15 / 16
    assert stats["floor_pixels_either_band"] == 1
    token = tmp_path / "token.tif"
    out = m.write_s1_valid_v2_token(str(raw), token)
    assert out["actual_observed_fraction"] == 14 / 16
    import rasterio
    with rasterio.open(token) as ds:
        assert ds.count == 1 and ds.dtypes[0] == "uint8"
        assert ds.descriptions[0] == "S1_DUALPOL_VALID_V2"
        tok = ds.read(1)
        with rasterio.open(raw) as rs:
            assert ds.crs == rs.crs
            assert ds.transform == rs.transform
            assert ds.width == rs.width and ds.height == rs.height
    assert tok[0, 0] == 0 and tok[0, 1] == 0 and tok[0, 2] == 1
    assert tok[1, 0] == 1
    # The raw raster is untouched (float32 representation of -80.031).
    with rasterio.open(raw) as ds:
        assert float(ds.read(1)[0, 1]) == pytest.approx(-80.031, abs=1e-5)


def test_s2_sr_actual_mask_requires_all_four_bands(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    bands = [np.full((4, 4), 0.1, dtype="float32") for _ in range(4)]
    bands[0][0, 0] = np.nan  # one band missing at one pixel -> unobserved
    sr = tmp_path / "sr.tif"
    with rasterio.open(
            sr, "w", driver="GTiff", height=4, width=4, count=4,
            dtype="float32", crs="EPSG:32650",
            transform=from_origin(500000.0, 3400000.0, 10.0, 10.0)) as dst:
        for i, arr in enumerate(bands, start=1):
            dst.write(arr, i)
            dst.set_band_description(i, ("B2", "B3", "B4", "B8")[i - 1])
    stats = m.s2_sr_actual_mask(str(sr))
    assert stats["actual_observed_fraction"] == 15 / 16
    assert stats["per_band_finite_fraction"]["B2"] == 15 / 16


def test_landsat_inherited_gate_rules() -> None:
    # Eligibility follows the in-W10-cell joint fraction (owner F1);
    # the grid fraction is evidence and may fall below 0.95 while the
    # cell passes.
    grid = {"actual_observed_fraction": 0.94}
    cell_ok = {"actual_observed_fraction_in_w10_cell": 0.98}
    gate = m.landsat_inherited_gate(grid, cell_ok)
    assert gate["gate_pass"] and gate["pass"]
    assert gate["grid_fraction_below_gate"]
    assert gate["plan_v2_fraction"] is None
    # Cell below 0.95 fails even when the full grid passes.
    fail = m.landsat_inherited_gate(
        {"actual_observed_fraction": 0.96},
        {"actual_observed_fraction_in_w10_cell": 0.949})
    assert not fail["gate_pass"] and not fail["pass"]


def test_landsat_inherited_block_joint_not_min_per_band(
        tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import numpy as np
    import pytest
    import rasterio
    from rasterio.transform import from_origin

    bands = [np.full((10, 10), 0.1, dtype="float32") for _ in range(7)]
    # Disjoint fill populations: min(per-band)=0.95 overstates the joint
    # intersection 0.90 -- the Issue #19 V2 bug.
    bands[0].ravel()[0:5] = np.nan
    bands[1].ravel()[5:10] = np.nan
    sr = tmp_path / "sr.tif"
    with rasterio.open(
            sr, "w", driver="GTiff", height=10, width=10, count=7,
            dtype="float32", crs="EPSG:32650",
            transform=from_origin(500000.0, 3400000.0, 30.0, 30.0)) as dst:
        for i, arr in enumerate(bands, start=1):
            dst.write(arr, i)
            dst.set_band_description(i, f"SR_B{i}")
    assert m.s2_sr_actual_mask(str(sr))["actual_observed_fraction"] == 0.90
    row = {"product_id": "NP19_X_L8_2015", "sensor": "landsat8"}
    doc = {"cell_id": "CNA10K-R00000-C00000", "utm_zone": 50}

    def fake_cell(path: str, cell_id: str, zone: int,  # noqa: ARG001
                  pixel_m: float) -> dict[str, float]:  # noqa: ARG001
        return {"cell_pixels": 100, "observed_in_cell_pixels": 90,
                "actual_observed_fraction_in_w10_cell": 0.90}

    monkeypatch.setattr(m, "sr_in_w10_cell_fraction", fake_cell)
    with pytest.raises(m.ProvenanceError):
        m._v2_gate_from_landed(
            "landsat8", doc, row, {"sr": sr})  # noqa: SLF001

    def fake_cell_ok(path: str, cell_id: str, zone: int,  # noqa: ARG001
                     pixel_m: float) -> dict[str, float]:  # noqa: ARG001
        return {"cell_pixels": 100, "observed_in_cell_pixels": 98,
                "actual_observed_fraction_in_w10_cell": 0.98}

    monkeypatch.setattr(m, "sr_in_w10_cell_fraction", fake_cell_ok)
    block, new_files = m._v2_gate_from_landed(
        "landsat8", doc, row, {"sr": sr})  # noqa: SLF001
    assert new_files == []
    assert block["coverage_basis"] == m.BASIS_LANDSAT_INHERITED
    assert block["actual_observed_fraction"] == 0.90
    assert block["actual_observed_fraction_in_w10_cell"] == 0.98
    assert block["observed_pixels"] == 90
    assert block["gate"]["gate_pass"] and block["gate"]["pass"]
    assert block["gate"]["grid_fraction_below_gate"]


def test_actual_mask_gate_check_rules() -> None:
    ok = m.actual_mask_gate_check(1.0, 1.0, "LANDED_BYTES")
    assert ok["pass"]
    # Gate failure dominates.
    below = m.actual_mask_gate_check(0.91, 0.91, "LIVE_GEE_EXPORT_GRID")
    assert not below["gate_pass"] and not below["pass"]
    # Live evidence gets the resampling margin; landed bytes must agree
    # exactly.
    live = m.actual_mask_gate_check(0.999, 1.0, "LIVE_GEE_EXPORT_GRID")
    assert live["pass"]
    landed = m.actual_mask_gate_check(0.999, 1.0, "LANDED_BYTES")
    assert not landed["plan_agreement_pass"]


def test_v2_replay_gate_both_pass_proxy_delta_is_warn_not_fail() -> None:
    # R00445-C00159 S2: bytes cover the W10 cell fully (1.0) while the
    # plan-time live reduceRegion proxy measured 0.9603 (fractional
    # edge-mask resampling at the two-granule mosaic edge). Both sides
    # pass 0.95 -> eligible, disagreement recorded as a WARN only.
    gate = m.v2_replay_actual_mask_gate(
        1.0, 1.0, 0.9602704987320372, "LIVE_GEE_EXPORT_GRID")
    assert gate["gate_pass"] and gate["pass"]
    assert not gate["gate_status_conflict"]
    assert not gate["plan_agreement_pass"]
    assert [w["code"] for w in gate["crosscheck_warnings"]] == [
        m.PROXY_CROSSCHECK_WARN]


def test_v2_replay_gate_gate_flip_is_hard_failure() -> None:
    # Bytes pass but the plan proxy failed (or vice versa): the two
    # evidence streams disagree ON the gate -> conflict, never eligible.
    bytes_pass_plan_fail = m.v2_replay_actual_mask_gate(
        0.99, 0.99, 0.90, "LIVE_GEE_EXPORT_GRID")
    assert bytes_pass_plan_fail["gate_pass"]
    assert bytes_pass_plan_fail["gate_status_conflict"]
    assert not bytes_pass_plan_fail["pass"]
    bytes_fail_plan_pass = m.v2_replay_actual_mask_gate(
        0.90, 0.90, 0.99, "LIVE_GEE_EXPORT_GRID")
    assert not bytes_fail_plan_pass["gate_pass"]
    assert bytes_fail_plan_pass["gate_status_conflict"]
    assert not bytes_fail_plan_pass["pass"]
    assert bytes_fail_plan_pass["crosscheck_warnings"] == []


def test_v2_replay_gate_both_fail_is_failure_without_conflict() -> None:
    gate = m.v2_replay_actual_mask_gate(
        0.80, 0.80, 0.85, "LIVE_GEE_EXPORT_GRID")
    assert not gate["gate_pass"] and not gate["pass"]
    assert not gate["gate_status_conflict"]


def test_v2_replay_gate_exact_landed_evidence_agrees() -> None:
    gate = m.v2_replay_actual_mask_gate(
        0.971, 0.971, 0.971, "LANDED_BYTES")
    assert gate["pass"] and gate["plan_agreement_pass"]
    assert gate["crosscheck_warnings"] == []


def test_old_event_orphan_predicate() -> None:
    pid = "NP19_R00264-C00132_S1_2020_A"
    assert m.is_old_event_orphan(
        "spartina_pilot19_NP19_R00264-C00132_S1_2020_A_vvvh_20201019_r1.tif",
        pid, "20201012")
    # Current V2 event r2 export is never an orphan.
    assert not m.is_old_event_orphan(
        "spartina_pilot19_NP19_R00264-C00132_S1_2020_A_vvvh_20201012_r2.tif",
        pid, "20201012")
    # Derived v2 token is never an orphan.
    assert not m.is_old_event_orphan(
        "spartina_pilot19_NP19_R00264-C00132_S1_2020_A_dualpol_valid_v2_"
        "20201012_v2.tif", pid, "20201012")
    # A different slot's file is never touched.
    assert not m.is_old_event_orphan(
        "spartina_pilot19_NP19_R00264-C00132_S1_2021_A_vvvh_20211019_r1.tif",
        pid, "20201012")


def test_event_selection_block_contents() -> None:
    row = {"sensor": "sentinel1", "status": "V2_ELIGIBLE",
           "v2_change": m.CHANGE_REPLACED,
           "v2_actual_observed_fraction": 1.0,
           "v2_candidates_evaluated": 2,
           "v2_evidence_source": "LIVE_GEE_EXPORT_GRID"}
    block = m.event_selection_block(row, "deadbeef")
    assert block["revision"] == m.SELECTION_V2
    assert block["plan_csv"] == "national_pilot_event_plan_v2.csv"
    assert block["supersedes_plan_csv"] == "national_pilot_event_plan_v1.csv"
    assert block["plan_csv_sha256"] == "deadbeef"
    assert block["actual_mask_gate"] == 0.95
    assert block["label_independent"]
    landsat = dict(row, sensor="landsat8", status="SELECTED",
                   v2_change=m.CHANGE_LANDSAT)
    assert (m.event_selection_block(landsat, "deadbeef")["revision"]
            == m.SELECTION_V1_LANDSAT_INHERITED)


def test_s1_physical_audit_corruption_and_inversion_fail(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import numpy as np

    # Double-log / corruption produces values hundreds of dB outside hard.
    vv = np.full((16, 16), -12.0, dtype="float32")
    vh = np.full((16, 16), -22.0, dtype="float32")
    vv[0, 0] = 120.0
    p = tmp_path / "s1_bad.tif"
    _write_vvvh_geotiff(p, vv, vh)
    detail = m.s1_physical_audit(str(p))
    assert not detail["checks"]["VV_no_pixels_beyond_hard_envelope"]
    assert not detail["pass"]

    # Co-pol/cross-pol median inversion is a band-order/identity symptom.
    vv2 = np.full((16, 16), -25.0, dtype="float32")
    vh2 = np.full((16, 16), -10.0, dtype="float32")
    p2 = tmp_path / "s1_inv.tif"
    _write_vvvh_geotiff(p2, vv2, vh2)
    detail2 = m.s1_physical_audit(str(p2))
    assert not detail2["checks"]["VV_median_above_VH"]
    assert not detail2["pass"]
