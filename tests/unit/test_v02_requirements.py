"""Unit tests for the Issue #21 Phase A frozen support requirements."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from spartina.benchmark.v02 import requirements as R

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEZE_JSON = (REPO_ROOT / "benchmarks/spartinashift/v0_2"
               / "SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS.json")
PANEL_JSON = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.json"
SPLITS_JSON = (REPO_ROOT / "benchmarks/spartinashift/silver_v0_1"
               / "splits_v0_1.json")


@pytest.fixture(scope="module")
def document() -> dict:
    doc = json.loads(FREEZE_JSON.read_text())
    R.validate_requirements(doc)
    return doc


def test_freeze_file_valid(document: dict) -> None:
    assert document["requirements_name"] == R.REQUIREMENTS_NAME
    assert document["status"] == "FROZEN_PRE_SELECTION"
    assert document["issue"] == 21


def test_checksum_stable_and_excludes_bookkeeping(document: dict) -> None:
    embedded = document["checksum"]
    assert R.requirements_checksum(document) == embedded
    tampered = copy.deepcopy(document)
    tampered["git_commit"] = "0" * 40
    tampered["generated_utc"] = "1999-01-01T00:00:00+00:00"
    assert R.requirements_checksum(tampered) == embedded
    tampered["hard_scope_caps"]["max_new_cells"] = 95
    assert R.requirements_checksum(tampered) != embedded


def test_support_goals_match_directive(document: dict) -> None:
    goals = document["support_goals"]
    geo, cmsa = goals["geodata_temporal"], goals["cmsa_temporal"]
    xr, pair = goals["cross_region"], goals["near_synchronous"]
    assert (geo["positive_cells_usable_both_years_min"],
            geo["regions_min"], geo["background_cells_min"]) == (12, 3, 12)
    assert geo["anchor_years"] == [2015, 2020]
    assert (cmsa["positive_cells_usable_both_years_min"],
            cmsa["regions_min"], cmsa["background_cells_min"]) == (24, 4, 24)
    assert cmsa["anchor_years"] == [2020, 2021]
    assert (xr["defensible_region_holdouts_min"],
            xr["held_region_cells_min"],
            xr["held_region_positive_cells_min"]) == (4, 4, 2)
    assert (xr["outside_pool_cells_min"],
            xr["outside_pool_positive_cells_min"]) == (12, 4)
    assert (pair["paired_cells_min"], pair["paired_positive_cells_min"],
            pair["primary_pairing_gap_days_max"]) == (24, 12, 7)


def test_hard_caps(document: dict) -> None:
    caps = document["hard_scope_caps"]
    assert caps["max_new_cells"] == 96
    assert caps["max_landed_eo_gib"] == 40
    assert caps["max_gee_component_tasks"] == 10_000
    assert caps["no_national_batch"] is True


def test_selection_inputs_disjoint_and_model_free(document: dict) -> None:
    legal = set(document["selection_inputs"]["legal"])
    forbidden = set(document["selection_inputs"]["forbidden"])
    assert not (legal & forbidden)
    joined = " ".join(forbidden).lower()
    for needle in ("model prediction", "failure map", "uncertainty",
                   "performance", "imagery"):
        assert needle in joined


def test_acquisition_rules(document: dict) -> None:
    rules = document["acquisition_rules"]
    phen = rules["phenology"]
    assert (phen["autumn_doy_start"], phen["autumn_doy_end"],
            phen["target_doy"]) == (260, 320, 290)
    s2 = rules["sentinel2"]
    assert s2["max_datatakes_per_cell_year"] == 3
    assert s2["cell_years"] == [2020, 2021]
    assert s2["qa_policy"] == "s2_scl_qa_v1_1"
    assert s2["postexport_actual_mask_valid_min"] == 0.95
    l8 = rules["landsat"]
    assert l8["cell_years"] == [2015, 2020]
    assert l8["observations_per_cell_year_desired"] == [2, 3]
    assert "no silent spectral harmonization" in l8["harmonization"]
    views = rules["views"]["views"]
    assert views == ["SINGLE_EVENT_CANONICAL", "MULTI_DATE_SEASONAL"]
    s1 = rules["sentinel1"]
    assert s1["instrument_mode"] == "IW"
    assert s1["polarizations"] == ["VV", "VH"]
    assert s1["validity_token"] == "s1_dualpol_valid_v2"
    assert s1["primary_pairing_gap_days_max"] == 7
    assert "simultaneous" in document["support_goals"]["near_synchronous"][
        "simultaneous_rule"]


def test_stage1_panel_exclusion(document: dict) -> None:
    panel = json.loads(PANEL_JSON.read_text())
    expected = sorted(c["cell_id"] for c in panel["cells"])
    assert document["stage1_panel"]["cell_ids"] == expected
    assert len(expected) == 20
    splits = json.loads(SPLITS_JSON.read_text())
    inspected: set[str] = set()
    for split in splits["splits"].values():
        inspected.update(split["test"])
        inspected.update(split["witness_2020"])
    assert set(document["stage1_panel"]["inspected_test_witness_cell_ids"]) \
        == inspected
    assert document["stage1_panel"]["status"] == \
        "DEVELOPMENT_INSTRUMENTATION_ONLY"
    assert document["stage1_panel"]["eligible_as_primary_v02_test"] is False


def test_fresh_reserve_predeclared(document: dict) -> None:
    reserve = document["fresh_test_reserve"]
    assert reserve["old_test_witness_eligible_as_primary_test"] is False
    assert reserve["model_output_influence"] is False
    assert reserve["final_roles_assigned_now"] is False


def test_input_artifacts_checksums(document: dict) -> None:
    assert len(document["input_artifacts"]) == len(R.INPUT_ARTIFACTS)
    for entry in document["input_artifacts"]:
        path = REPO_ROOT / entry["path"]
        assert path.exists(), entry["path"]
        assert len(entry["sha256"]) == 64


def test_validate_detects_corruption(document: dict) -> None:
    bad = copy.deepcopy(document)
    bad["hard_scope_caps"]["max_new_cells"] = 120
    with pytest.raises(ValueError, match="new-cell cap"):
        R.validate_requirements(bad)
    bad2 = copy.deepcopy(document)
    bad2["stage1_panel"]["cell_ids"] = bad2["stage1_panel"]["cell_ids"][:-1]
    with pytest.raises(ValueError, match="20 cells"):
        R.validate_requirements(bad2)


def test_selection_hash_rank_deterministic() -> None:
    a = R.selection_hash_rank("ns", "CNA10K-R00001-C00001")
    b = R.selection_hash_rank("ns", "CNA10K-R00001-C00001")
    c = R.selection_hash_rank("other", "CNA10K-R00001-C00001")
    assert a == b and a != c and len(a) == 64
