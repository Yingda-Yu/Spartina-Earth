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
    with pytest.raises(ValueError, match="not SELECTED"):
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


def test_deterministic_naming() -> None:
    row = {"product_id": "NP19_R00226-C00080_L5_1990",
           "event_utc": "1990-10-29T00:00:00+00:00"}
    assert (m.prefix_for(row, "sr")
            == "spartina_pilot19_NP19_R00226-C00080_L5_1990_sr_19901029_r1")
    assert m.request_for(row, "qapixel") == (
        "NP19_R00226-C00080_L5_1990:qapixel:r1")
    assert m.date_tag(row) == "19901029"


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
    assert detail["bands"]["VV"]["outside_bulk_envelope_pixels"] == 1
    assert detail["bands"]["VH"]["outside_bulk_envelope_pixels"] == 1
    assert detail["checks"]["VV_no_pixels_beyond_hard_envelope"]


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
