"""Unit tests for Issue #21 Phase B deterministic, model-free selection."""

from __future__ import annotations

import pandas as pd
import pytest

from spartina.benchmark.v02 import selection as S

FEATURE_COLUMNS = [
    "cell_id", "membership_v1_1", "production_eligible", "center_lon",
    "center_lat", "province", "province_rule", "exclusive_stratum",
    "silver_2015_positive", "silver_2015_nearby", "cmsa_positive_history",
    "cmssm_2020_positive", "geodata_2015_pos_px", "geodata_2020_pos_px",
    "geodata_2020_issue18_g_px", "cmsa_2020_area_m2",
    "cmsa_2020_issue18_c_px", "cmsa_2021_area_m2",
    "cmsa_2020_gridcode0_area_m2", "cmsa_2021_gridcode0_area_m2",
    "cmssm_2020_issue18_m_px", "s2_autumn_full_2020",
    "s2_autumn_full_2021", "s1_autumn_full_2020", "s1_autumn_full_2021",
    "landsat_autumn_full_2015", "landsat_autumn_full_2020",
    "old_stage1_panel"]


def _row(i: int, province: str, kind: str, old: bool = False) -> dict:
    row = {c: 0 for c in FEATURE_COLUMNS}
    row.update({
        "cell_id": f"CNA10K-R{i:05d}-C00100",
        "membership_v1_1": "KEEP_MAINLAND_COASTAL",
        "production_eligible": True,
        "province": province,
        "province_rule": "CENTROID_WITHIN_PROVINCE",
        "exclusive_stratum": "UNLABELED_COASTAL",
        "old_stage1_panel": old,
        "s2_autumn_full_2020": 1, "s2_autumn_full_2021": 1,
        "s1_autumn_full_2020": 1, "s1_autumn_full_2021": 1,
        "landsat_autumn_full_2015": 1, "landsat_autumn_full_2020": 1,
    })
    if kind == "geo":  # GEODATA-positive both years
        row["geodata_2015_pos_px"] = 500
        row["geodata_2020_pos_px"] = 600
    elif kind == "cmsa":  # CMSA-positive both years
        row["cmsa_2020_area_m2"] = 200_000
        row["cmsa_2021_area_m2"] = 250_000
    elif kind == "trace":
        row["geodata_2015_pos_px"] = 2
        row["geodata_2020_pos_px"] = 2
    elif kind == "unknown":
        row["cmsa_2020_gridcode0_area_m2"] = 5_000
    return row


@pytest.fixture
def rich_universe() -> pd.DataFrame:
    rows = []
    i = 1
    provinces = ["Liaoning", "Shandong", "Jiangsu", "Zhejiang",
                 "Fujian", "Guangdong"]
    for p in provinces:
        for _ in range(3):
            rows.append(_row(i, p, "geo"))
            i += 1
        for _ in range(5):
            rows.append(_row(i, p, "cmsa"))
            i += 1
        rows.append(_row(i, p, "trace"))
        i += 1
        for _ in range(4):
            rows.append(_row(i, p, "bg"))
            i += 1
    rows.append(_row(9001, "Zhejiang", "geo", old=True))
    rows.append(_row(9002, "Zhejiang", "bg", old=True))
    return pd.DataFrame(rows)


def test_area_class() -> None:
    assert S.area_class(0) == "NONE"
    assert S.area_class(0.01) == "TRACE"
    assert S.area_class(0.2) == "SMALL"
    assert S.area_class(2.0) == "MEDIUM"
    assert S.area_class(99.0) == "LARGE"


def test_annotate_flags() -> None:
    df = S.annotate(pd.DataFrame([
        _row(1, "A", "geo"), _row(2, "A", "cmsa"), _row(3, "A", "bg"),
        _row(4, "A", "unknown")]))
    assert bool(df.loc[0, "geo_both"]) and bool(df.loc[0, "pair_capable"])
    assert bool(df.loc[1, "cmsa_both"])
    assert bool(df.loc[2, "clean_background"])
    assert not bool(df.loc[3, "clean_background"])
    assert df.loc[3, "gridcode0_unknown_overlap"]


def test_rich_universe_meets_goals_and_excludes_old(
        rich_universe: pd.DataFrame) -> None:
    result = S.select_panel(rich_universe)
    g = result["goals"]
    assert g["goals_met"] is True
    assert g["n_geo_both"] >= 12
    assert g["n_cmsa_both"] >= 24
    assert g["n_clean_background"] >= 24
    assert g["n_pair_capable"] >= 24
    assert g["n_pair_capable_positive"] >= 12
    assert len(result["holdout_provinces"]) >= 4
    for report in g["holdouts"].values():
        assert report["holds"]
    assert g["n_cells"] <= 96
    selected = set(result["panel"]["cell_id"])
    assert "CNA10K-R09001-C00100" not in selected
    assert "CNA10K-R09002-C00100" not in selected
    assert result["deficits"] == []


def test_determinism_and_model_column_ignored(
        rich_universe: pd.DataFrame) -> None:
    r1 = S.select_panel(rich_universe)
    shuffled = rich_universe.sample(frac=1.0, random_state=7)
    r2 = S.select_panel(shuffled)
    assert r1["checksum"] == r2["checksum"]
    with_extra = rich_universe.copy()
    with_extra["model_uncertainty"] = range(len(with_extra))
    with_extra["model_prediction"] = 9.99
    r3 = S.select_panel(with_extra)
    assert r3["checksum"] == r1["checksum"]


def test_poor_support_records_deficits() -> None:
    rows = [_row(1, "Liaoning", "geo"), _row(2, "Liaoning", "cmsa"),
            _row(3, "Liaoning", "bg"), _row(4, "Shandong", "bg")]
    result = S.select_panel(pd.DataFrame(rows))
    assert result["goals"]["goals_met"] is False
    assert result["deficits"]
    joined = " ".join(result["deficits"])
    assert "geodata" in joined or "cmsa" in joined


def test_checksum_semantics() -> None:
    a = S.panel_checksum(["C1", "C2"], ["P1"])
    b = S.panel_checksum(["C1", "C2"], ["P1"])
    c = S.panel_checksum(["C1", "C3"], ["P1"])
    d = S.panel_checksum(["C1", "C2"], ["P2"])
    assert a == b and a != c and a != d
