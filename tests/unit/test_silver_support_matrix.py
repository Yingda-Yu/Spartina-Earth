"""Unit tests for the SpartinaShift-Silver v0.1 Phase A support matrix."""

from __future__ import annotations

import pandas as pd

from spartina.benchmark.silver.support import (
    ACTUAL_MASK_GATE,
    ANALYSIS_GRID_M,
    REGION_HOLDOUT_MIN_CELLS,
    REGION_TRAIN_MIN_CELLS,
    RIGHTS_BY_SOURCE_KEY,
    build_support_matrix,
    task_support_summary,
)

CELL_A = "CNA10K-R00001-C00001"
CELL_B = "CNA10K-R00002-C00002"

LABEL_COLS = [
    "cell_id", "family", "year", "support_m", "n_pure_positive",
    "n_mixed", "n_pure_negative", "n_unknown", "n_total",
    "positive_area_km2_in_cell", "tif_sha256"]


def _label_row(cell: str, family: str, year: int, support_m: int) -> dict:
    return {
        "cell_id": cell, "family": family, "year": year,
        "support_m": support_m, "n_pure_positive": 10, "n_mixed": 2,
        "n_pure_negative": 100 if family == "GEODATA" else 0,
        "n_unknown": 50, "n_total": 162,
        "positive_area_km2_in_cell": 0.01,
        "tif_sha256": f"sha-{family}-{year}-{support_m}"}


def _labels() -> pd.DataFrame:
    rows = []
    for cell in (CELL_A, CELL_B):
        for year in (2015, 2020):
            rows.append(_label_row(cell, "GEODATA", year, 30))
        for year in (2020, 2021):
            rows.append(_label_row(cell, "CMSA", year, 30))
        rows.append(_label_row(cell, "CM-SSM", 2020, 30))
        rows.append(_label_row(cell, "CM-SSM", 2020, 10))
    return pd.DataFrame(rows)


def _panel() -> pd.DataFrame:
    return pd.DataFrame([
        {"cell_id": CELL_A, "region_province": "Shandong",
         "coastal_segment": "BOHAI"},
        {"cell_id": CELL_B, "region_province": "Fujian",
         "coastal_segment": "EAST_CHINA_SEA"}])


PLAN_COLS = ["product_id", "cell_id", "sensor", "year", "variant",
             "status", "event_id", "event_utc"]


def _plan(**kw: object) -> dict:
    row = {"variant": "DEFAULT", "event_id": "EVT",
           "event_utc": "2020-10-12T00:00:00+00:00", "status": "SELECTED"}
    row.update(kw)
    return row


def _landed(**kw: object) -> dict:
    row = {"variant": "DEFAULT", "verdict": "PASS",
           "actual_observed_fraction": 1.0,
           "event_id": "EVT",
           "event_utc": "2020-10-12T00:00:00+00:00"}
    row.update(kw)
    return row


def _minimal_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cell A lands L8/S2/S1 in every task year; cell B lands nothing."""
    plan_rows = []
    landed_rows = []
    for cell in (CELL_A, CELL_B):
        plan_rows.append(_plan(
            product_id=f"P-{cell}-L8-2015", cell_id=cell,
            sensor="landsat8", year=2015))
        plan_rows.append(_plan(
            product_id=f"P-{cell}-L8-2020", cell_id=cell,
            sensor="landsat8", year=2020))
        plan_rows.append(_plan(
            product_id=f"P-{cell}-S2-2020", cell_id=cell,
            sensor="sentinel2", year=2020))
        plan_rows.append(_plan(
            product_id=f"P-{cell}-S2-2021", cell_id=cell,
            sensor="sentinel2", year=2021))
        plan_rows.append(_plan(
            product_id=f"P-{cell}-S1-2020-A", cell_id=cell,
            sensor="sentinel1", year=2020, variant="A"))
    for pid, sensor, year, variant in [
            ("L8-2015", "landsat8", 2015, "DEFAULT"),
            ("L8-2020", "landsat8", 2020, "DEFAULT"),
            ("S2-2020", "sentinel2", 2020, "DEFAULT"),
            ("S2-2021", "sentinel2", 2021, "DEFAULT"),
            ("S1-2020-A", "sentinel1", 2020, "A")]:
        landed_rows.append(_landed(
            product_id=f"P-{CELL_A}-{pid}", cell_id=CELL_A,
            sensor=sensor, year=year, variant=variant))
    return pd.DataFrame(plan_rows, columns=PLAN_COLS), pd.DataFrame(
        landed_rows)


def test_rights_table_owner_policy() -> None:
    for year in (1990, 2000, 2015, 2020):
        r = RIGHTS_BY_SOURCE_KEY[f"GEODATA_{year}"]
        assert r.training_eligible and r.evaluation_eligible
        assert not r.external_reference_only
        assert "INTERNAL_RESEARCH_ONLY" in r.rights_status
    for year in range(2017, 2022):
        r = RIGHTS_BY_SOURCE_KEY[f"CMSA_{year}"]
        assert r.training_eligible and "NONCOMMERCIAL" in r.rights_status
    cmssm = RIGHTS_BY_SOURCE_KEY["CM-SSM_2020"]
    assert not cmssm.training_eligible
    assert cmssm.evaluation_eligible
    assert cmssm.external_reference_only
    assert "CONFLICT" in cmssm.rights_status


def test_landed_pairing_and_unlanded_inventory() -> None:
    plan, landed = _minimal_fixture()
    matrix = build_support_matrix(plan, landed, _labels(), _panel())
    # 5 landed products in cell A x label families at the year:
    # 2015 GEODATA; 2020 GEODATA+CMSA+CM-SSM(30+10m); 2021 CMSA.
    a = matrix[matrix.cell_id == CELL_A]
    assert (a.pairing_state == "PAIRED_LANDED").sum() == (
        # L8-2015 x GEODATA 30m
        1
        # L8-2020 x GEODATA, CMSA, CM-SSM 30m
        + 3
        # S2-2020 x GEODATA, CMSA, CM-SSM 30m + CM-SSM 10m
        + 4
        # S1-2020A x GEODATA, CMSA, CM-SSM 30m + CM-SSM 10m
        + 4
        # S2-2021 x CMSA 30m
        + 1)
    # Every unlanded planned product in cell B is retained per label.
    b = matrix[matrix.cell_id == CELL_B]
    assert (b.pairing_state == "EO_PLANNED_NOT_LANDED").sum() == (
        # L8-2015 x1; L8-2020 x3; S2-2020 x3 30m + x1 10m CM-SSM;
        # S1-A x3 + x1; S2-2021 x1
        1 + 3 + 4 + 4 + 1)
    # CMSA 2017-2019 have no EO plan anywhere.
    plan_extra = pd.concat([plan, pd.DataFrame([_plan(
        product_id="X", cell_id=CELL_A, sensor="landsat8", year=2017,
        status="NO_SCENE")], columns=PLAN_COLS)], ignore_index=True)
    labels = pd.concat([_labels(), pd.DataFrame([_label_row(
        CELL_A, "CMSA", 2017, 30)])], ignore_index=True)
    matrix2 = build_support_matrix(plan_extra, landed, labels, _panel())
    cmsa17 = matrix2[
        (matrix2.label_source_key == "CMSA_2017")
        & (matrix2.cell_id == CELL_A)].iloc[0]
    assert cmsa17.pairing_state == "EO_PLANNED_NOT_LANDED"
    assert cmsa17.unlanded_reason == "NO_SCENE"


def test_unplanned_label_only_rows_are_kept() -> None:
    plan, landed = _minimal_fixture()
    labels = pd.concat([_labels(), pd.DataFrame([_label_row(
        CELL_A, "CMSA", 2018, 30)])], ignore_index=True)
    matrix = build_support_matrix(plan, landed, labels, _panel())
    row = matrix[
        (matrix.label_source_key == "CMSA_2018")
        & (matrix.cell_id == CELL_A)].iloc[0]
    assert row.pairing_state == "EO_UNPLANNED"
    assert row.sensor == "MISSING_EO"


def test_confirmed_actual_mask_rejection_overrides_plan_status() -> None:
    plan, landed = _minimal_fixture()
    rejected = {f"P-{CELL_B}-L8-2020"}
    matrix = build_support_matrix(
        plan, landed, _labels(), _panel(),
        rejected_product_ids=rejected)
    rows = matrix[
        (matrix.cell_id == CELL_B)
        & (matrix.product_id == f"P-{CELL_B}-L8-2020")]
    assert len(rows) == 3  # GEODATA, CMSA, CM-SSM 30 m
    assert set(rows.unlanded_reason) == {"CONFIRMED_ACTUAL_MASK_REJECTION"}
    assert rows.actual_mask_gate_pass.eq(False).all()


def test_landed_product_without_plan_raises() -> None:
    plan, _ = _minimal_fixture()
    ghost = pd.DataFrame([_landed(
        product_id="GHOST", cell_id=CELL_A, sensor="landsat8", year=2020)])
    try:
        build_support_matrix(plan, ghost, _labels(), _panel())
    except ValueError as exc:
        assert "absent from V2 plan" in str(exc)
    else:
        raise AssertionError("expected ValueError for orphan landing")


def test_landsat_never_pairs_with_10m_support() -> None:
    plan, landed = _minimal_fixture()
    matrix = build_support_matrix(plan, landed, _labels(), _panel())
    cmssm10 = matrix[
        (matrix.label_family == "CM-SSM")
        & (matrix.label_support_m == 10)]
    assert set(cmssm10.sensor) <= {"sentinel1", "sentinel2", "MISSING_EO"}
    assert (cmssm10.eo_native_res_m != 30).all()


def test_actual_mask_gate_and_resampling_tokens() -> None:
    plan, landed = _minimal_fixture()
    matrix = build_support_matrix(plan, landed, _labels(), _panel())
    paired = matrix[matrix.pairing_state == "PAIRED_LANDED"]
    assert paired.actual_mask_gate_pass.all()
    assert (paired.actual_mask_gate == ACTUAL_MASK_GATE).all()
    assert (paired.analysis_grid_m == ANALYSIS_GRID_M).sum() > 0
    agg = paired[
        paired.sensor.isin(["sentinel1", "sentinel2"])
        & (paired.analysis_grid_m == ANALYSIS_GRID_M)]
    assert agg.eo_to_analysis_grid.str.startswith("VALID_PIXEL_AGGREGATE_") \
        .all()
    native = paired[paired.sensor.str.startswith("landsat")]
    assert (native.eo_to_analysis_grid == "NATIVE_30M").all()


def test_gold_zero_and_cmssm_never_training() -> None:
    plan, landed = _minimal_fixture()
    matrix = build_support_matrix(plan, landed, _labels(), _panel())
    assert (matrix.gold_available == 0).all()
    cmssm = matrix[matrix.label_family == "CM-SSM"]
    assert not cmssm.training_eligible.any()
    assert cmssm.evaluation_eligible.all()
    assert cmssm.external_reference_only.all()


def test_task_summary_intersections_and_regions() -> None:
    plan, landed = _minimal_fixture()
    matrix = build_support_matrix(plan, landed, _labels(), _panel())
    summary = task_support_summary(matrix)
    tasks = summary["tasks"]
    # Cell A lands everything; cell B lands nothing.
    assert tasks["C1_cross_year_geodata_l8"]["eligible_cells_both_years"] \
        == [CELL_A]
    assert tasks["C2_cross_year_cmsa_s2"]["eligible_cells_both_years"] \
        == [CELL_A]
    assert tasks["C4_cross_source_2020"]["eligible_union_cells"] == [CELL_A]
    assert tasks["C5_modality_ablation_2020"]["eligible_cells"] == [CELL_A]
    # Only one supported cell -> no province meets the holdout rule.
    regions = tasks["C3_cross_region_province_holdout"]["regions"]
    assert all(not v["adequate_holdout_under"] for v in regions.values())
    assert REGION_HOLDOUT_MIN_CELLS >= 4
    assert REGION_TRAIN_MIN_CELLS >= 8
    # C5 acquisition gap is one day (same date in the fixture), not zero
    # language about simultaneity is forbidden.
    c5 = tasks["C5_modality_ablation_2020"]
    assert c5["s2_s1a_acquisition_gap_days"] == {CELL_A: 0}
    assert c5["gap_stats_primary_variant_a"][
        "observations_are_never_simultaneous"]
