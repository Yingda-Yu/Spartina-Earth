"""M2.1a2 (Issue #12) pure-logic unit tests.

Covers the fixed cell grid, acquisition-event grouping, cell x event QA,
the rights matrix, and the metadata-only / no-export invariants. Nothing
here touches GEE or the large data files.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from shapely.geometry import box

from spartina.data.gee.sentinel2 import (
    S2_LEGACY_V1_VALID_SCL_CLASSES,
    S2_SCL_11_CORRECTION_REASON,
    S2_SCL_QA_POLICY_VERSION,
    S2_VALID_SCL_CLASSES,
)
from spartina.data.zhejiang import acquisition as acq
from spartina.data.zhejiang.cells import (
    CANDIDATE_CELL_SIZES_M,
    GRID_ID,
    RELEVANT,
    _bay_assignment,
    cell_bounds,
    cell_id,
    cell_polygon,
    cells_are_interior_disjoint,
    grid_spec,
    parse_cell_id,
    registry_fingerprint,
)
from spartina.data.zhejiang.rights import (
    NO,
    NO_LICENSE,
    RIGHTS_VALUES,
    UNKNOWN,
    YES,
    label_rights_records,
    rights_registry_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "configs/data/zhejiang_multibay_m21a.yaml"


# ---------------------------------------------------------------------------
# Fixed analysis cells
# ---------------------------------------------------------------------------
def test_cell_id_roundtrip_all_sizes():
    for size in CANDIDATE_CELL_SIZES_M:
        spec = grid_spec(size)
        cid = cell_id(spec, 32, 313)
        parsed_size, ix, iy = parse_cell_id(cid)
        assert (parsed_size, ix, iy) == (size, 32, 313)
        assert cid.startswith("ZJ_U51_")


@pytest.mark.parametrize("bad", [
    "ZJ_U51_10K_E032", "ZJ_U52_10K_E032_N313", "ZJ_U51_1K_E032_N313",
    "U51_10K_E032_N313", "ZJ_U51_10K_X032_N313", "ZJ_U51_10K_E032_X313",
])
def test_parse_cell_id_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_cell_id(bad)


def test_grid_spec_rejects_unknown_size():
    with pytest.raises(ValueError):
        grid_spec(3000)


def test_cell_bounds_exact_and_deterministic():
    spec = grid_spec(10_000)
    assert cell_bounds(spec, 0, 0) == (0.0, 0.0, 10_000.0, 10_000.0)
    assert cell_bounds(spec, 32, 313) == (
        320_000.0, 3_130_000.0, 330_000.0, 3_140_000.0)
    assert cell_bounds(grid_spec(10_000), 1, 1) == cell_bounds(
        grid_spec(10_000), 1, 1)


def test_grids_nest_four_5k_cells_tile_one_10k_cell():
    big = cell_polygon(grid_spec(10_000), 4, 7)
    children = [
        cell_polygon(grid_spec(5_000), 2 * 4 + dx, 2 * 7 + dy)
        for dx in (0, 1) for dy in (0, 1)]
    union = children[0]
    for c in children[1:]:
        union = union.union(c)
    assert union.equals(big)
    # 20 km nests four 10 km cells
    huge = cell_polygon(grid_spec(20_000), 2, 3)
    tens = [
        cell_polygon(grid_spec(10_000), 2 * 2 + dx, 2 * 3 + dy)
        for dx in (0, 1) for dy in (0, 1)]
    u = tens[0]
    for c in tens[1:]:
        u = u.union(c)
    assert u.equals(huge)


def _cell_ns(size, ix, iy, bay="ZJ-X"):
    return SimpleNamespace(
        cell_id=cell_id(grid_spec(size), ix, iy), cell_size_m=size,
        index_east=ix, index_north=iy, bay_id=bay,
        coastal_relevance=RELEVANT)


def test_interior_disjoint_invariant_true_and_false():
    adjacent = [_cell_ns(10_000, 0, 0), _cell_ns(10_000, 1, 0),
                _cell_ns(10_000, 0, 1), _cell_ns(10_000, 1, 1)]
    assert cells_are_interior_disjoint(adjacent)
    overlapping = adjacent + [_cell_ns(5_000, 0, 0)]
    assert not cells_are_interior_disjoint(overlapping)


def test_registry_fingerprint_order_independent_and_stable():
    rows = [
        SimpleNamespace(
            cell_id=_cell_ns(10_000, ix, iy).cell_id,
            cell_size_m=10_000,
            as_row=lambda ix=ix, iy=iy: {
                "cell_id": _cell_ns(10_000, ix, iy).cell_id,
                "cell_size_m": 10_000})
        for ix in range(3) for iy in range(3)]
    a = registry_fingerprint(list(rows))
    b = registry_fingerprint(list(reversed(rows)))
    assert a == b and len(a) == 64


def test_bay_assignment_max_intersection():
    envelopes = {
        "A": box(0, 0, 60, 60),
        "B": box(60, 0, 120, 60),
    }
    bay, area = _bay_assignment(box(10, 0, 70, 60), envelopes)
    assert bay == "A"
    assert area == 3000.0  # intersection area (m^2 in these units)


def test_bay_assignment_ties_and_misses_raise():
    envelopes = {
        "A": box(0, 0, 60, 60),
        "B": box(60, 0, 120, 60),
    }
    with pytest.raises(ValueError):
        _bay_assignment(box(55, 0, 65, 10), envelopes)  # 5 vs 5 tie
    with pytest.raises(ValueError):
        _bay_assignment(box(100, 100, 110, 110), envelopes)  # no overlap


# ---------------------------------------------------------------------------
# Acquisition groups
# ---------------------------------------------------------------------------
def _s2_scene(sid, date, tile, datatake, spacecraft="Sentinel-2A",
              relorbit=121, cloud=0.05):
    return {
        "scene_id": sid, "sensor": "sentinel2",
        "acquisition_utc": f"{date}T02:30:00Z", "tile_ref": tile,
        "spacecraft": spacecraft, "relative_orbit_number": relorbit,
        "orbit_direction": "DESCENDING", "instrument_mode": "",
        "polarizations": "", "processing_baseline": "",
        "datatake_identifier": datatake, "scene_cloud_fraction": cloud,
    }


def _landsat_scene(sid, date, ref, sensor="landsat8", cloud=0.05,
                   slc="PRE_SLC_FAILURE"):
    p, r = ref.split("/")
    return {
        "scene_id": sid, "sensor": sensor,
        "acquisition_utc": f"{date}T02:30:00Z", "tile_ref": ref,
        "spacecraft": sensor.upper().replace("LANDSAT", "LANDSAT_"),
        "relative_orbit_number": None, "orbit_direction": "",
        "instrument_mode": "", "polarizations": "",
        "processing_baseline": "", "datatake_identifier": None,
        "scene_cloud_fraction": cloud, "slc_status": slc,
        "wrs_path": int(p), "wrs_row": int(r),
    }


def _s1_scene(sid, date, direction, relorbit, pol="VV|VH"):
    return {
        "scene_id": sid, "sensor": "sentinel1",
        "acquisition_utc": f"{date}T22:00:00Z",
        "tile_ref": f"S1:{direction}:{relorbit}",
        "spacecraft": "Sentinel-1A", "relative_orbit_number": relorbit,
        "orbit_direction": direction, "instrument_mode": "IW",
        "polarizations": pol, "processing_baseline": "",
        "datatake_identifier": None, "scene_cloud_fraction": None,
    }


def test_s2_groups_by_real_datatake_across_tiles():
    scenes = [
        _s2_scene("S1", "2021-09-20", "51RUP", "DT_X"),
        _s2_scene("S2", "2021-09-20", "51RUQ", "DT_X"),
        _s2_scene("S3", "2021-09-20", "51RTP", "DT_Y"),
    ]
    groups = acq.group_scenes(scenes)
    assert len(groups) == 2
    by_members = {tuple(sorted(g.member_scene_ids)): g for g in groups}
    gx = by_members[("S1", "S2")]
    assert gx.n_scenes == 2
    assert gx.datatake_status == acq.DATATAKE_PRESENT
    assert gx.grouping_rule == acq.S2_GROUP_RULE
    assert set(gx.footprint_frame_keys) == {"MGRS:51RUP", "MGRS:51RUQ"}
    assert by_members[("S3",)].datatake_identifiers == "DT_Y"


def test_s2_different_datatake_same_date_not_merged():
    scenes = [
        _s2_scene("A", "2021-09-20", "51RUP", "DT_1", relorbit=121),
        _s2_scene("B", "2021-09-20", "51RUQ", "DT_2", relorbit=121),
    ]
    groups = acq.group_scenes(scenes)
    assert len(groups) == 2


def test_s2_missing_datatake_uses_flagged_fallback():
    scenes = [
        _s2_scene("A", "2021-09-20", "51RUP", "", relorbit=121),
        _s2_scene("B", "2021-09-20", "51RUQ", "", relorbit=121),
    ]
    groups = acq.group_scenes(scenes)
    assert len(groups) == 1
    assert groups[0].datatake_status == acq.DATATAKE_FALLBACK
    assert groups[0].grouping_rule == acq.S2_FALLBACK_RULE


def test_s2_cross_date_grouping_is_impossible():
    # same datatake string cannot occur across dates in reality; even if
    # faked, dates are part of assertions only for the landsat path.
    # S2 bucket key uses the datatake, so two dates with the same fake
    # datatake must trigger the cross-date assertion.
    scenes = [
        _s2_scene("A", "2021-09-20", "51RUP", "DT_BAD"),
        _s2_scene("B", "2021-09-21", "51RUQ", "DT_BAD"),
    ]
    with pytest.raises(AssertionError):
        acq.group_scenes(scenes)


def test_landsat_three_row_wrs_chain_groups_then_splits_disconnected():
    scenes = [
        _landsat_scene("L1", "2020-10-01", "118/039"),
        _landsat_scene("L2", "2020-10-01", "118/040"),
        _landsat_scene("L3", "2020-10-01", "118/041"),
        # Manhattan distance >= 2 from every chain member -> own event
        _landsat_scene("L4", "2020-10-01", "117/038"),
    ]
    groups = acq.group_scenes(scenes)
    assert len(groups) == 2
    multi = [g for g in groups if g.n_scenes == 3]
    assert len(multi) == 1
    assert set(multi[0].tile_refs.split("|")) == {
        "118/039", "118/040", "118/041"}


def test_landsat_different_sensors_same_date_separate():
    scenes = [
        _landsat_scene("A", "2020-10-01", "118/040", sensor="landsat7"),
        _landsat_scene("B", "2020-10-01", "118/040", sensor="landsat8"),
    ]
    groups = acq.group_scenes(scenes)
    assert {g.sensor for g in groups} == {"landsat7", "landsat8"}


def test_s1_ascending_descending_never_mix():
    scenes = [
        _s1_scene("A", "2021-09-20", "ASCENDING", 69),
        _s1_scene("B", "2021-09-20", "DESCENDING", 69),
        _s1_scene("C", "2021-09-20", "ASCENDING", 171),
    ]
    groups = acq.group_scenes(scenes)
    assert len(groups) == 3
    dirs = [g.orbit_direction for g in groups]
    assert dirs.count("ASCENDING") == 2 and dirs.count("DESCENDING") == 1


def test_group_id_deterministic_and_membership_preserved():
    scenes = [
        _s2_scene("A", "2021-09-20", "51RUP", "DT_X"),
        _s2_scene("B", "2021-09-20", "51RUQ", "DT_X"),
    ]
    g1 = acq.group_scenes(scenes)[0]
    g2 = acq.group_scenes(list(reversed(scenes)))[0]
    assert g1.group_id == g2.group_id
    assert g1.member_scene_ids == ["A", "B"]
    assert g1.footprint_frame_keys == ["MGRS:51RUP", "MGRS:51RUQ"]


def test_l7_extended_science_mission_regime_flag():
    nominal = acq.group_scenes(
        [_landsat_scene("N", "2022-03-30", "117/040", sensor="landsat7")])[0]
    extended = acq.group_scenes(
        [_landsat_scene("E", "2023-09-29", "117/040", sensor="landsat7",
                        slc="POST_SLC_FAILURE")])[0]
    assert nominal.geometry_regime == acq.GEOM_NOMINAL_WRS
    assert extended.geometry_regime == acq.GEOM_L7_EXTENDED
    assert extended.slc_statuses == "POST_SLC_FAILURE"
    # other sensors keep their regimes
    s2 = acq.group_scenes(
        [_s2_scene("S", "2023-09-29", "51RUP", "DT_Z")])[0]
    s1 = acq.group_scenes(
        [_s1_scene("R", "2023-09-29", "ASCENDING", 69)])[0]
    assert s2.geometry_regime == acq.GEOM_NOMINAL_MGRS
    assert s1.geometry_regime == acq.GEOM_S1_REPRESENTATIVE


# ---------------------------------------------------------------------------
# Cell x event QA on synthetic geometry
# ---------------------------------------------------------------------------
WINDOWS = [
    {"id": "autumn_v0", "doy_start": 260, "doy_end": 305},
    {"id": "autumn_primary_v1", "doy_start": 260, "doy_end": 320,
     "layer": "biological_target_phase"},
]


def _qa_cells():
    return [
        SimpleNamespace(
            cell_id=cell_id(grid_spec(10_000), 0, 0),
            bay_id="ZJ-A", cell_size_m=10_000, index_east=0, index_north=0),
        SimpleNamespace(
            cell_id=cell_id(grid_spec(10_000), 1, 0),
            bay_id="ZJ-A", cell_size_m=10_000, index_east=1, index_north=0),
    ]


def test_cell_coverage_gate_and_cloud_gate():
    cells = _qa_cells()[:1]
    frames = {"MGRS:51RUP": box(-1000, -1000, 11_000, 11_000)}
    scenes = {
        "A": _s2_scene("A", "2021-09-20", "51RUP", "DT_Q", cloud=0.10),
    }
    groups = acq.group_scenes(list(scenes.values()))
    rows = acq.simulate_cell_observations(
        cells, groups, frames, scenes, WINDOWS,
        coverage_min=0.99, scene_cloud_max=0.30)
    assert len(rows) == 1
    r = rows[0]
    assert r["coverage_fraction"] >= 0.99 and r["quality_pass"]
    assert r["cloud_gate"] == acq.CLOUD_GATE_PASS
    assert "autumn_primary_v1" in r["window_ids"]
    assert r["geometry_regime"] == acq.GEOM_NOMINAL_MGRS


def test_partial_coverage_fails_gate_but_pair_kept():
    cells = _qa_cells()[:1]
    # half of cell 0 covered
    frames = {"MGRS:51RUP": box(0, 0, 10_000, 5_000)}
    scenes = {"A": _s2_scene("A", "2021-09-20", "51RUP", "DT_Q")}
    groups = acq.group_scenes(list(scenes.values()))
    rows = acq.simulate_cell_observations(
        cells, groups, frames, scenes, WINDOWS,
        coverage_min=0.99, scene_cloud_max=0.30)
    assert len(rows) == 1
    assert 0.49 < rows[0]["coverage_fraction"] < 0.51
    assert not rows[0]["coverage_gate"] and not rows[0]["quality_pass"]
    # NO_QUALITY-like outcome still records the data (pair retained)


def test_cloud_failure_and_sar_na():
    cells = _qa_cells()[:1]
    geom = box(-1000, -1000, 11_000, 11_000)
    frames = {"MGRS:51RUP": geom, "S1:ASCENDING:69": geom}
    scenes = {
        "A": _s2_scene("A", "2021-09-20", "51RUP", "DT_Q", cloud=0.80),
        "R": _s1_scene("R", "2021-09-20", "ASCENDING", 69),
    }
    groups = acq.group_scenes(list(scenes.values()))
    rows = acq.simulate_cell_observations(
        cells, groups, frames, scenes, WINDOWS,
        coverage_min=0.99, scene_cloud_max=0.30)
    by_sensor = {r["sensor"]: r for r in rows}
    assert by_sensor["sentinel2"]["cloud_gate"] == acq.CLOUD_GATE_FAIL
    assert not by_sensor["sentinel2"]["quality_pass"]
    assert by_sensor["sentinel1"]["cloud_gate"] == acq.CLOUD_GATE_NA
    assert by_sensor["sentinel1"]["quality_pass"]


def test_qa_thresholds_are_unchanged_and_scl_policy_pinned():
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    qa = config["m21a2"]["cell_qa"]
    assert qa["coverage_min"] == 0.99
    assert qa["scene_cloud_max"] == 0.30
    assert qa["threshold_status"] == "UNCHANGED_NOT_RELAXED"
    assert qa["s2_scl_qa_policy"] == "s2_scl_qa_v1_1"
    assert S2_SCL_QA_POLICY_VERSION == "s2_scl_qa_v1_1"
    # water (6) / vegetation (4,5) valid under v1.1; snow (11) was
    # removed from the valid set and remains only in the legacy audit set
    assert {4, 5, 6} <= set(S2_VALID_SCL_CLASSES)
    assert 11 not in S2_VALID_SCL_CLASSES
    assert 11 in S2_LEGACY_V1_VALID_SCL_CLASSES
    assert "11" in S2_SCL_11_CORRECTION_REASON


# ---------------------------------------------------------------------------
# Rights matrix
# ---------------------------------------------------------------------------
def test_rights_matrix_structure_and_l1_distinction():
    rows = label_rights_records()
    assert len(rows) == 20
    for r in rows:
        for field in (
                "scientific_analysis_allowed",
                "internal_training_allowed",
                "validation_use_allowed",
                "public_redistribution_allowed",
                "derived_model_release_status",
                "citation_required"):
            assert r[field] in RIGHTS_VALUES
    l1 = next(r for r in rows if r["asset_id"] == "L1-china2015-raster30m")
    assert l1["scientific_analysis_allowed"] == YES
    assert l1["internal_training_allowed"] == UNKNOWN  # not NO
    assert l1["public_redistribution_allowed"] == NO
    assert l1["derived_model_release_status"] == UNKNOWN
    assert l1["citation_required"] == YES
    # no-license assets are all UNKNOWN, never silent NO
    for aid in ("L2-cmssm2020-polygons", "L3-hangzhou-mask-2015",
                "U6-zj-featurestack-A", "U7-zj-featurestack-B"):
        r = next(x for x in rows if x["asset_id"] == aid)
        assert r["rights_status"] == NO_LICENSE
        assert r["scientific_analysis_allowed"] == UNKNOWN
        assert r["public_redistribution_allowed"] == UNKNOWN


def test_open_upstream_local_derivatives_keep_redistribution_unknown():
    rows = label_rights_records()
    u8 = [r for r in rows if r["asset_id"].startswith("U8-")]
    assert len(u8) == 7
    for r in u8:
        assert r["internal_training_allowed"] == YES
        assert r["public_redistribution_allowed"] == UNKNOWN
        assert r["derived_model_release_status"] == UNKNOWN


def test_rights_fingerprint_stable():
    rows = label_rights_records()
    assert rights_registry_fingerprint(rows) == (
        rights_registry_fingerprint(list(reversed(rows))))


# ---------------------------------------------------------------------------
# No-export / metadata-only invariants
# ---------------------------------------------------------------------------
def test_acquisition_module_never_imports_ee():
    src = (Path(acq.__file__)).read_text(encoding="utf-8")
    assert "import ee" not in src
    assert "ee.batch" not in src
    assert GRID_ID == "ZJ_U51_FIXED_V0"


def test_export_guard_blocks_batch_export():
    # The same guard the census runner installs must raise on any
    # ee.batch.Export.* invocation.
    import types

    from spartina.data.zhejiang.census import ExportAttempted, install_export_guard

    class _Batch:
        class Export:
            @staticmethod
            def image(**_kwargs):
                return ("would-export", _kwargs)

            table = image
            map = image

    fake_ee = types.SimpleNamespace(batch=_Batch())
    restore = install_export_guard(fake_ee)
    try:
        with pytest.raises(ExportAttempted):
            fake_ee.batch.Export.image(**{"x": 1})
    finally:
        restore()
    # restored after the context
    assert fake_ee.batch.Export.image(x=1)[0] == "would-export"
