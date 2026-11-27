"""M2.1a2-R1 unit tests: bay-clip semantics, funnel gate fix, S1 sampler.

Markers covered:
  CELL_EDGE_BLEED_CONFIRMED
  M21A_SMB_ZERO_WAS_MASK_FAILURE
  S2_2022_ZERO_WAS_GROUPWIDE_CLOUD_BUG
  S1_REPRESENTATIVE_FOOTPRINT_NOT_PRODUCTION_GEOMETRY
"""

from __future__ import annotations

import importlib.util
import json
import types
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from shapely.geometry import box

from spartina.data.zhejiang import acquisition as acq
from spartina.data.zhejiang.cells import cell_id, grid_spec

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = REPO_ROOT / "datasets/manifests"
WINDOWS = [
    {"id": "autumn_primary_v1", "doy_start": 260, "doy_end": 320,
     "layer": "biological_target_phase"},
]


def _s2(sid: str, tile: str, cloud: float | None, datatake: str = "DT_X",
        date: str = "2022-09-20") -> dict:
    return {
        "scene_id": sid, "sensor": "sentinel2",
        "acquisition_utc": f"{date}T02:30:00Z", "tile_ref": tile,
        "spacecraft": "Sentinel-2A", "relative_orbit_number": 121,
        "orbit_direction": "DESCENDING", "instrument_mode": "",
        "polarizations": "", "processing_baseline": "",
        "datatake_identifier": datatake, "scene_cloud_fraction": cloud,
    }


def _s1(sid: str, direction: str = "ASCENDING", rel: int = 171) -> dict:
    return {
        "scene_id": sid, "sensor": "sentinel1",
        "acquisition_utc": "2022-09-20T22:00:00Z",
        "tile_ref": f"S1:{direction}:{rel}",
        "spacecraft": "Sentinel-1A", "relative_orbit_number": rel,
        "orbit_direction": direction, "instrument_mode": "IW",
        "polarizations": "VV|VH", "processing_baseline": "",
        "datatake_identifier": None, "scene_cloud_fraction": None,
    }


def _one_cell():
    return [SimpleNamespace(
        cell_id=cell_id(grid_spec(10_000), 0, 0),
        bay_id="ZJ-A", cell_size_m=10_000,
        index_east=0, index_north=0)]


def _run(scenes, frames):
    groups = acq.group_scenes(scenes)
    return acq.simulate_cell_observations(
        _one_cell(), groups, frames, {s["scene_id"]: s for s in scenes},
        WINDOWS, coverage_min=0.99, scene_cloud_max=0.30)


# ---------------------------------------------------------------------------
# Blocker #2 regression: contributing-scene cloud gate
# ---------------------------------------------------------------------------
def test_cloudy_adjacent_tile_does_not_poison_covered_cell() -> None:
    frames = {
        "MGRS:TILEA": box(-1000, -1000, 11_000, 11_000),
        "MGRS:TILEB": box(40_000, 40_000, 50_000, 50_000),
    }
    scenes = [_s2("A", "TILEA", 0.10), _s2("B", "TILEB", 0.90)]
    rows = _run(scenes, frames)
    assert len(rows) == 1
    r = rows[0]
    assert r["contributing_scene_ids"] == "A"
    assert r["contributing_n_scenes"] == 1
    assert r["cloud_gate"] == acq.CLOUD_GATE_PASS
    assert r["groupwide_cloud_gate"] == acq.CLOUD_GATE_FAIL
    assert r["quality_pass"]
    assert r["cloud_gate_basis"] == acq.CLOUD_GATE_BASIS_CONTRIBUTING
    assert set(r) == set(acq.CELL_OBSERVATION_COLUMNS)


def test_cloudy_covering_tile_still_fails() -> None:
    frames = {
        "MGRS:TILEA": box(-1000, -1000, 11_000, 11_000),
        "MGRS:TILEB": box(-1000, -1000, 11_000, 11_000),
    }
    rows = _run([_s2("A", "TILEA", 0.10), _s2("B", "TILEB", 0.90)], frames)
    assert rows[0]["cloud_gate"] == acq.CLOUD_GATE_FAIL
    assert not rows[0]["quality_pass"]


def test_covering_scene_missing_cloud_cannot_be_rescued() -> None:
    frames = {
        "MGRS:TILEA": box(-1000, -1000, 11_000, 11_000),
        "MGRS:TILEB": box(40_000, 40_000, 50_000, 50_000),
    }
    rows = _run([_s2("A", "TILEA", None), _s2("B", "TILEB", 0.10)], frames)
    assert rows[0]["cloud_gate"] == acq.CLOUD_GATE_MISSING
    assert not rows[0]["quality_pass"]


def test_sar_pair_is_na_regardless_of_frames() -> None:
    frames = {"S1:ASCENDING:171": box(-1000, -1000, 11_000, 11_000)}
    rows = _run([_s1("R")], frames)
    assert rows[0]["cloud_gate"] == acq.CLOUD_GATE_NA
    assert rows[0]["cloud_gate_basis"] == acq.CLOUD_GATE_BASIS_NA
    assert rows[0]["quality_pass"]
    assert rows[0]["contributing_cloud_max"] is None


# ---------------------------------------------------------------------------
# Blocker #2 artifact: 2022 funnel manifest locks + bucket reconciliation
# ---------------------------------------------------------------------------
FUNNEL = MANIFESTS / "zhejiang_s2_2022_funnel_audit_v0.csv"
REJECT = MANIFESTS / "zhejiang_s2_2022_funnel_rejections_v0.csv"


@pytest.mark.skipif(not FUNNEL.exists(), reason="funnel manifest absent")
def test_funnel_stage_counts_locked() -> None:
    f = pd.read_csv(FUNNEL)
    expected = {
        "ZJ-HZB": dict(A=373, C=63, D=25, E=573, G=399, J_v0=0, J_r1=51),
        "ZJ-SMB": dict(A=147, C=26, D=25, E=750, G=750, J_v0=0, J_r1=150),
        "ZJ-YQB": dict(A=584, C=100, D=25, E=400, G=375, J_v0=0, J_r1=89),
    }
    for bay, exp in expected.items():
        b = f[f.bay_id == bay].set_index("stage_id")
        assert int(b.loc["A_raw_census_rows", "count"]) == exp["A"]
        assert int(b.loc["C_autumn_scenes", "count"]) == exp["C"]
        assert int(b.loc[
            "D_autumn_datatake_groups_intersecting_bay", "count"]) == exp["D"]
        assert int(b.loc["E_cell_group_candidate_pairs", "count"]) == exp["E"]
        assert int(b.loc["G_coverage_pass_pairs_ge_0.99", "count"]) == exp["G"]
        assert int(b.loc["J_v0_final_quality_pairs", "count"]) == exp["J_v0"]
        assert int(b.loc["J_R1_final_quality_pairs", "count"]) == exp["J_r1"]


@pytest.mark.skipif(not (FUNNEL.exists() and REJECT.exists()),
                    reason="funnel artifacts absent")
def test_funnel_rejection_buckets_reconcile_and_verdict() -> None:
    f = pd.read_csv(FUNNEL)
    r = pd.read_csv(REJECT)
    for bay in ("ZJ-HZB", "ZJ-SMB", "ZJ-YQB"):
        b = f[f.bay_id == bay].set_index("stage_id")
        n_e = int(b.loc["E_cell_group_candidate_pairs", "count"])
        n_g = int(b.loc["G_coverage_pass_pairs_ge_0.99", "count"])
        rr = r[r.bay_id == bay].set_index("category")["n_pairs"]
        assert int(rr["LOW_COVERAGE_lt_0.99"]) == n_e - n_g
        # every coverage-passing pair is genuinely cloudy under both gates
        # or a final R1 pass (metadata-missing counts are zero in 2022)
        assert (int(rr["FAIL_CLOUD_BOTH_V0_AND_R1"])
                + int(rr["FINAL_QUALITY_PASS_R1"]) == n_g)
        assert int(rr["RECOVERED_R1_GROUPWIDE_POISONED_ONLY"]) == int(
            b.loc["J_R1_final_quality_pairs", "count"])
        assert int(rr["CLOUD_METADATA_MISSING_V0_GROUPWIDE"]) == 0
        assert int(rr["CLOUD_METADATA_MISSING_R1_CONTRIBUTING"]) == 0
    verdict = json.loads((MANIFESTS
        / "zhejiang_s2_2022_funnel_audit_v0.verdict.json").read_text())
    assert verdict["verdict_marker"] == "ZERO_WAS_PIPELINE_BUG"
    assert verdict["thresholds_unchanged"] == {
        "coverage_min": 0.99, "scene_cloud_max": 0.3}
    assert verdict["datatake_verification"][
        "all_groups_real_datatake"] is True
    assert verdict["datatake_verification"][
        "groups_spanning_multiple_utc_dates"] == 0


# ---------------------------------------------------------------------------
# Blocker #1: bay-clip semantics + v0_1 artifact invariants
# ---------------------------------------------------------------------------
def test_bay_clip_geometry_semantics_synthetic() -> None:
    cell = box(0, 0, 10_000, 10_000)
    envelope = box(0, 0, 10_000, 5_000)  # bay covers northern? half
    inside = box(0, 4_000, 5_000, 5_000)
    outside = box(0, 8_000, 5_000, 9_000)
    clip = cell.intersection(envelope)
    assert clip.area <= cell.area
    assert clip.intersection(inside).area == inside.area
    assert clip.intersection(outside).area == 0.0
    # clipping never moves identity: same bounds basis
    assert cell.bounds[:2] == (0.0, 0.0)


OVERLAP = MANIFESTS / "zhejiang_label_cell_overlap_v0_1.csv"
RECON = MANIFESTS / "zhejiang_label_bay_reconciliation_v0_1.csv"
OVERLAP_V0 = MANIFESTS / "zhejiang_label_cell_overlap_v0.csv"


@pytest.mark.skipif(not OVERLAP.exists(), reason="overlap v0_1 absent")
def test_overlap_v01_required_columns_and_statuses() -> None:
    d = pd.read_csv(OVERLAP)
    required = {"cell_id", "cell_size_m", "bay_id",
                "cell_label_status_full_geometry_v0",
                "cell_label_status_bay_scoped",
                "positive_pixels_bay_clip", "positive_area_km2_bay_clip",
                "positive_area_km2_outside_bay_in_cell"}
    assert required <= set(d.columns)
    statuses = set(d.cell_label_status_bay_scoped.unique()) | set(
        d.cell_label_status_full_geometry_v0.unique())
    assert "NEGATIVE" not in statuses  # UNLABELED never becomes NEGATIVE


@pytest.mark.skipif(not (OVERLAP.exists() and OVERLAP_V0.exists()),
                    reason="overlap artifacts absent")
def test_cell_identity_stable_and_smb_silver17() -> None:
    d = pd.read_csv(OVERLAP)
    v0 = pd.read_csv(OVERLAP_V0)
    for size in (5_000, 10_000, 20_000):
        assert (set(d[d.cell_size_m == size].cell_id)
                == set(v0[v0.cell_size_m == size].cell_id))
    t = d[(d.cell_size_m == 10_000)
          & (d.asset_id == "L1-china2015-raster30m")]
    n_smb = t[(t.bay_id == "ZJ-SMB")
              & (t.cell_label_status_bay_scoped.isin(
                  ["SILVER", "SILVER+WEAK"]))].cell_id.nunique()
    n_hzb = t[(t.bay_id == "ZJ-HZB")
              & (t.cell_label_status_bay_scoped.isin(
                  ["SILVER", "SILVER+WEAK"]))].cell_id.nunique()
    n_yqb = t[(t.bay_id == "ZJ-YQB")
              & (t.cell_label_status_bay_scoped.isin(
                  ["SILVER", "SILVER+WEAK"]))].cell_id.nunique()
    assert (n_hzb, n_smb, n_yqb) == (13, 17, 11)


@pytest.mark.skipif(not RECON.exists(), reason="reconciliation absent")
def test_reconciliation_closes_per_grid_size() -> None:
    r = pd.read_csv(RECON)
    assert (r.reconciliation_note
            == "MATCH_WITHIN_RASTERIZATION_TOLERANCE").all()
    pos = r[r.direct_envelope_area_km2 > 0]
    assert (pos.relative_difference < 0.01).all()


# ---------------------------------------------------------------------------
# Blocker #3: deterministic S1 sample selection + audit artifact flags
# ---------------------------------------------------------------------------
def _load(path_name: str, mod_name: str):
    path = REPO_ROOT / path_name
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic_s1_census() -> pd.DataFrame:
    rows = []
    bays = ("ZJ-HZB", "ZJ-SMB", "ZJ-YQB")
    tracks = {
        ("ASCENDING", 69), ("ASCENDING", 171), ("DESCENDING", 105)}
    for bay in bays:
        for direction, rel in tracks:
            for year in range(2017, 2025):
                for k in range(24):
                    rows.append({
                        "scene_id": f"{bay[3:]}_{direction[:3]}_{rel}_"
                                    f"{year}_{k}",
                        "sensor": "sentinel1", "roi_id": bay,
                        "orbit_direction": direction,
                        "relative_orbit_number": float(rel),
                        "instrument_mode": "IW",
                        "year": year,
                        "acquisition_utc": f"{year}-06-{(k%28)+1:02d}T22:00:00Z",
                    })
    # a few EW open-ocean scenes that must never be selected
    for year in (2018, 2022):
        rows.append({"scene_id": f"EW_{year}", "sensor": "sentinel1",
                     "roi_id": "ZJ-HZB", "orbit_direction": "ASCENDING",
                     "relative_orbit_number": 98.0, "instrument_mode": "EW",
                     "year": year,
                     "acquisition_utc": f"{year}-01-01T00:00:00Z"})
    return pd.DataFrame(rows)


def test_s1_sample_deterministic_stratified_years() -> None:
    mod = _load("scripts/data/zhejiang/audit_s1_footprints.py",
                "audit_s1_footprints")
    census = _synthetic_s1_census()
    a = mod.select_s1_sample(census)
    b = mod.select_s1_sample(census)
    assert [s["scene_id"] for s in a] == [s["scene_id"] for s in b]
    ids = [s["scene_id"] for s in a]
    assert len(ids) == len(set(ids)) == mod.MAX_SCENES
    df = pd.DataFrame(a)
    assert set(df.roi_id) == {"ZJ-HZB", "ZJ-SMB", "ZJ-YQB"}
    assert set(df.orbit_direction) == {"ASCENDING", "DESCENDING"}
    assert set(df.relative_orbit_number) == {69.0, 171.0, 105.0}
    assert df.year.nunique() >= 5
    assert not any(s.startswith("EW_") for s in ids)


def test_spread_positions_bounds_and_order() -> None:
    mod = _load("scripts/data/zhejiang/audit_s1_footprints.py",
                "audit_s1_footprints2")
    pos = mod._spread_positions(100, 5)
    assert pos[0] == 0 and pos[-1] == 99
    assert len(pos) == len(set(pos)) == 5


S1_AUDIT = MANIFESTS / "zhejiang_s1_footprint_audit_v0.csv"


@pytest.mark.skipif(not S1_AUDIT.exists(), reason="s1 audit absent")
def test_s1_audit_flags_consistent_and_sample_adequate() -> None:
    d = pd.read_csv(S1_AUDIT)
    n = d.scene_id.nunique()
    assert 24 <= n <= 60
    assert set(d.bay_id) == {"ZJ-HZB", "ZJ-SMB", "ZJ-YQB"}
    assert d.orbit_direction.nunique() == 2
    fe = (d["eligible_approx_ge_0.99"]
          & ~d["eligible_actual_ge_0.99"])
    fr = (d["eligible_actual_ge_0.99"]
          & ~d["eligible_approx_ge_0.99"])
    assert fe.tolist() == d["false_eligible_approx_only"].tolist()
    assert fr.tolist() == d["false_rejected_actual_only"].tolist()
    assert d.abs_error.min() >= 0.0
    assert (d.abs_error <= 1.0 + 1e-9).all()
    policy = json.loads((MANIFESTS
        / "zhejiang_s1_footprint_audit_v0.policy.json").read_text())
    assert policy["approx_status"] == "PLANNING_PREFILTER_ONLY"
    assert policy["actual_status"] == "PRODUCTION_ELIGIBILITY_AND_QA"
    assert (policy["overall"]["false_eligible_approx_only"]
            + policy["overall"]["false_rejected_actual_only"]) > 0


# ---------------------------------------------------------------------------
# Export guard (no ee installation required: works on a fake module)
# ---------------------------------------------------------------------------
def test_export_guard_blocks_fake_ee_and_restores() -> None:
    from spartina.data.zhejiang.census import ExportAttempted, install_export_guard

    class _Batch:
        class Export:  # noqa: N801 - mimics ee.batch.Export namespace
            @staticmethod
            def toDrive(**_: object) -> str:  # noqa: N802
                return "would-export"

    fake_ee = types.SimpleNamespace(batch=_Batch)
    restore = install_export_guard(fake_ee)
    with pytest.raises(ExportAttempted):
        fake_ee.batch.Export.toDrive(image="x", description="y")
    restore()
    assert fake_ee.batch.Export.toDrive() == "would-export"


PAIRS_V01 = REPO_ROOT / "work/derived/zhejiang_cell_observations_v0_1.parquet"


@pytest.mark.skipif(not PAIRS_V01.exists(), reason="work pairs absent")
def test_pairs_v01_schema_and_2022_s2_recovery() -> None:
    p = pd.read_parquet(PAIRS_V01)
    assert set(acq.CELL_OBSERVATION_COLUMNS) <= set(p.columns)
    s2 = p[(p.sensor == "sentinel2") & (p.year == 2022)
           & (p.cell_size_m == 10_000)
           & (p.day_of_year.between(260, 320))]
    got = {b: int(s2[(s2.bay_id == b)].quality_pass.sum())
           for b in ("ZJ-HZB", "ZJ-SMB", "ZJ-YQB")}
    assert got == {"ZJ-HZB": 51, "ZJ-SMB": 150, "ZJ-YQB": 89}
    # S1 cloud columns are NA, never FAIL/PASS
    s1 = p[p.sensor == "sentinel1"]
    assert (s1.cloud_gate == acq.CLOUD_GATE_NA).all()
