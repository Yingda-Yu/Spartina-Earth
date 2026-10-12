"""Unit tests for the SpartinaShift-Silver v0.1 Phase B frozen protocol."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spartina.benchmark.silver.protocol import (
    LEAKAGE_BUFFER_M,
    PROTOCOL_NAME,
    SEEDS,
    SplitRules,
    assign_roles,
    cell_albers_unit,
    protocol_checksum,
    verify_buffer,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
V01 = REPO_ROOT / "benchmarks/spartinashift/silver_v0_1"
PROTOCOL_JSON = V01 / "SPARTINASHIFT_SILVER_V0_1_PROTOCOL.json"
SPLITS_JSON = V01 / "splits_v0_1.json"
MATRIX_CSV = V01 / "support_matrix_v0_1.csv"

NORTH = "Shandong"
SOUTH = "Zhejiang"
BG1 = "CNA10K-R00445-C00159"  # Liaoning background cell
BG2 = "CNA10K-R00260-C00128"  # Fujian background cell
BG3 = "CNA10K-R00388-C00129"  # Shandong background cell
BG4 = "CNA10K-R00429-C00140"  # Liaoning background cell


def _record(cell: str, source: str, n_pos: int) -> dict:
    return {"cell_id": cell, "label_source_key": source,
            "label_support_m": 30, "n_pure_positive_px": n_pos}


@pytest.fixture(scope="module")
def fixture() -> dict:
    cells = [
        "CNA10K-R00311-C00156",  # positive, Zhejiang
        "CNA10K-R00349-C00154",  # positive, Jiangsu
        "CNA10K-R00236-C00083",  # positive, Guangdong
        "CNA10K-R00334-C00163",  # positive, Zhejiang
        "CNA10K-R00413-C00121",  # positive, Shandong
        BG1, BG2, BG3, BG4]
    prov = {
        "CNA10K-R00311-C00156": "Zhejiang",
        "CNA10K-R00349-C00154": "Jiangsu",
        "CNA10K-R00236-C00083": "Guangdong",
        "CNA10K-R00334-C00163": "Zhejiang",
        "CNA10K-R00413-C00121": "Shandong",
        BG1: "Liaoning", BG2: "Fujian", BG3: "Shandong",
        BG4: "Liaoning"}
    records = []
    for cell in cells[:5]:
        records.append(_record(cell, "CMSA_2020", 100))
        records.append(_record(cell, "CMSA_2021", 100))
    for cell in cells[5:]:
        records.append(_record(cell, "CMSA_2020", 0))
        records.append(_record(cell, "CMSA_2021", 0))
    return {"cells": cells, "prov": prov, "records": records}


RULES = SplitRules(
    n_test=4, n_val=3,
    positive_source_keys=("CMSA_2020", "CMSA_2021"),
    n_positive_train=2, n_positive_val=1, n_positive_test=2,
    positive_test_min_provinces=2,
    positive_test_require_north_south=True,
    min_val_provinces=2, n_witness=2)


def test_deterministic_assignment(fixture: dict) -> None:
    a = assign_roles(
        "TEST-DET", fixture["cells"], fixture["prov"],
        list(reversed(fixture["records"])), RULES)
    b = assign_roles(
        "TEST-DET", list(reversed(fixture["cells"])), fixture["prov"],
        fixture["records"], RULES)
    assert a["role_of"] == b["role_of"]
    assert a["witness_2020"] == b["witness_2020"]


def test_role_exclusivity_and_counts(fixture: dict) -> None:
    split = assign_roles(
        "TEST-ROLES", fixture["cells"], fixture["prov"],
        fixture["records"], RULES)
    train, val, test = split["train"], split["val"], split["test"]
    assert len(train) + len(val) + len(test) == len(fixture["cells"])
    assert not (set(train) & set(val) | set(train) & set(test)
                | set(val) & set(test))
    assert len(split["positive_by_role"]["train"]) >= 2
    assert len(split["positive_by_role"]["val"]) >= 1
    assert len(split["positive_by_role"]["test"]) >= 2
    pos_test = split["positive_by_role"]["test"]
    provs = {fixture["prov"][c] for c in pos_test}
    assert len(provs) >= 2
    assert provs & {"Shandong", "Liaoning", "Jiangsu"}
    assert provs & {"Zhejiang", "Fujian", "Guangdong"}


def test_witness_isolation(fixture: dict) -> None:
    split = assign_roles(
        "TEST-WIT", fixture["cells"], fixture["prov"],
        fixture["records"], RULES)
    witness = split["witness_2020"]
    assert len(witness) == 2
    assert all(c in split["test"] for c in witness)
    assert not any(c in split["train"] or c in split["val"]
                   for c in witness)
    assert len({fixture["prov"][c] for c in witness}) == 2
    assert len(split["positive_by_role"]["test"]) >= 1


def test_infeasible_positive_rule_raises(fixture: dict) -> None:
    # Only 3 positive cells cannot satisfy 2 train + 1 val + 2 test.
    records = [r for r in fixture["records"]
               if r["cell_id"] not in {
                   "CNA10K-R00236-C00083", "CNA10K-R00349-C00154"}]
    cells = [c for c in fixture["cells"]
             if c not in {"CNA10K-R00236-C00083",
                          "CNA10K-R00349-C00154"}]
    with pytest.raises(ValueError, match="no admissible split"):
        assign_roles("TEST-INFEAS", cells, fixture["prov"], records, RULES)


def test_buffer_check_flags_adjacent_cells() -> None:
    # Two edge-adjacent lattice cells in different roles must fail.
    a = "CNA10K-R00334-C00163"
    b = "CNA10K-R00334-C00164"
    assert cell_albers_unit(a) is not None
    report = verify_buffer({a: "train", b: "test"})
    assert report["n_cross_role_pairs_closer_than_buffer"] == 1
    assert report["overlaps"][0]["min_gap_m"] == 0.0


def test_seeds_and_buffer_constants() -> None:
    assert SEEDS == (17, 42, 2026)
    assert LEAKAGE_BUFFER_M == 250.0


def test_frozen_artifact_consistency() -> None:
    protocol = json.loads(PROTOCOL_JSON.read_text())
    splits = json.loads(SPLITS_JSON.read_text())
    assert protocol["protocol_name"] == PROTOCOL_NAME
    assert protocol["status"] == "FROZEN_PRE_TRAINING"
    assert protocol["gold_label_cells"] == 0
    assert protocol["checksum"] == protocol_checksum(protocol)
    assert splits["protocol_checksum"] == protocol["checksum"]
    split = protocol["splits"]["SPLIT-S2"]
    roles = split["train"] + split["val"] + split["test"]
    assert len(roles) == len(set(roles)) == 18
    assert split["buffer_check"][
        "n_cross_role_pairs_closer_than_buffer"] == 0
    # Frozen task verdicts reflect the measured support reality.
    assert protocol["tasks"]["C1_cross_year_geodata_l8"]["verdict"] \
        == "INSUFFICIENT_SUPPORT"
    assert protocol["tasks"]["C3_cross_region"][
        "verdict"] == "INSUFFICIENT_SUPPORT_ALL_REGIONS"
    c2 = protocol["tasks"]["C2_cross_year_cmsa_s2"]
    assert c2["verdict"] == "SUPPORTED"
    assert c2["runs_planned"] == 12
    # CM-SSM never trains; rights token frozen.
    assert "CONFLICT" in protocol["rights_policy"]["CM-SSM"]
    c4 = protocol["tasks"]["C4_cross_source_2020"]
    assert c4["no_new_training"] is True
    # Witness cells are all test cells; one positive.
    witness = split["witness_2020"]
    pos_test = set(split["positive_by_role"]["test"])
    assert sum(c in pos_test for c in witness) == 1
    assert all(c in split["test"] for c in witness)
    # Matrix the protocol was frozen from is present.
    assert MATRIX_CSV.exists()
