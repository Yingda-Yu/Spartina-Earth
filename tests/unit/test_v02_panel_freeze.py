"""Guards on the committed Issue #21 Phase B frozen panel artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from spartina.benchmark.v02 import selection as S

REPO_ROOT = Path(__file__).resolve().parents[2]
V02 = REPO_ROOT / "benchmarks/spartinashift/v0_2"
PANEL_JSON = V02 / "SPARTINASHIFT_V0_2_CELL_PANEL.json"
PANEL_CSV = V02 / "v02_cell_panel.csv"
FEATURES_CSV = REPO_ROOT / "work/issue21/derived/v02_cell_features.csv"
LEDGER_CSV = REPO_ROOT / "work/issue21/derived/v02_domain_exclusion_ledger.csv"
REGISTRY_CSV = (
    REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_1_core_frozen.csv")


@pytest.fixture(scope="module")
def freeze() -> dict:
    return json.loads(PANEL_JSON.read_text())


def test_freeze_structure(freeze: dict) -> None:
    assert freeze["panel_name"] == "SPARTINASHIFT_V0_2_CELL_PANEL"
    assert freeze["status"] == "FROZEN_PRE_EXPORT"
    assert freeze["requirements_name"] == \
        "SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS"
    assert len(freeze["requirements_checksum"]) == 64
    assert freeze["n_new_cells"] <= 96
    assert freeze["goal_attainment"]["goals_met"] is True
    assert freeze["deficits_max_attainable"] == []


def test_panel_csv_matches_freeze(freeze: dict) -> None:
    panel = pd.read_csv(PANEL_CSV)
    assert sorted(panel["cell_id"]) == freeze["selected_cell_ids"]
    assert panel["cell_id"].is_unique
    assert len(panel) == freeze["n_new_cells"]
    recomputed = S.panel_checksum(
        sorted(panel["cell_id"]), freeze["holdout_provinces"])
    assert recomputed == freeze["selection_checksum"]


def test_no_stage1_cells_and_goals(freeze: dict) -> None:
    panel = pd.read_csv(PANEL_CSV)
    features = pd.read_csv(FEATURES_CSV)
    old = set(features.loc[features["old_stage1_panel"], "cell_id"])
    assert not (set(panel["cell_id"]) & old)
    g = freeze["goal_attainment"]
    assert g["n_geo_both"] >= 12 and g["n_geo_both_regions"] >= 3
    assert g["n_cmsa_both"] >= 24 and g["n_cmsa_both_regions"] >= 4
    assert g["n_clean_background"] >= 24
    assert g["n_pair_capable"] >= 24
    assert g["n_pair_capable_positive"] >= 12
    for report in g["holdouts"].values():
        assert report["holds"]


def test_exclusion_ledger_covers_all_registry_cells(freeze: dict) -> None:
    ledger = pd.read_csv(LEDGER_CSV)
    registry = pd.read_csv(REGISTRY_CSV)
    assert len(ledger) == len(registry) == 3319
    assert set(ledger["cell_id"]) == set(registry["cell_id"])
    selected = set(ledger.loc[ledger["selected"], "cell_id"])
    assert selected == set(freeze["selected_cell_ids"])
    assert (ledger.loc[ledger["selected"], "reason"] == "SELECTED").all()
    stage1 = ledger[ledger["reason"] == S.REASON_OLD_PANEL]
    assert len(stage1) == 20
    assert not stage1["selected"].any()


def test_freeze_reproducible_from_features(freeze: dict) -> None:
    result = S.select_panel(pd.read_csv(FEATURES_CSV))
    assert result["checksum"] == freeze["selection_checksum"]
    assert result["holdout_provinces"] == freeze["holdout_provinces"]
