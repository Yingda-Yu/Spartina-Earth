"""Unit tests for Issue #21 Phase C fresh-test reserve declaration."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from spartina.benchmark.v02 import reserve as R

REPO_ROOT = Path(__file__).resolve().parents[2]
V02 = REPO_ROOT / "benchmarks/spartinashift/v0_2"
RESERVE_JSON = V02 / "V0_2_FRESH_TEST_RESERVE.json"
RESERVE_CSV = V02 / "v02_fresh_test_reserve.csv"
PANEL_CSV = V02 / "v02_cell_panel.csv"


def _panel_row(cell: str, prov: str, positive: bool) -> dict:
    return {"cell_id": cell, "province": prov,
            "any_positive": positive,
            "clean_background": not positive}


def test_reserve_deterministic_and_stratified() -> None:
    rows = []
    for prov in "ABCDEFGHIJ":
        for k in range(3):
            rows.append(_panel_row(f"{prov}-p{k}", prov, True))
        rows.append(_panel_row(f"{prov}-b0", prov, False))
    panel = pd.DataFrame(rows)
    d1 = R.declare_reserve(panel)
    d2 = R.declare_reserve(panel.sample(frac=1.0, random_state=3))
    assert d1["checksum"] == d2["checksum"]
    assert d1["n_cells"] == 24
    assert d1["n_positive"] == 16
    assert d1["n_background"] == 8
    assert d1["n_provinces"] == 8
    assert d1["final_roles_status"] == R.FINAL_ROLES
    ids = [m["cell_id"] for m in d1["members"]]
    assert len(ids) == len(set(ids))
    # top-8 provinces by positive count; counts are tied -> name order
    assert d1["selection_rule"]["provinces_used"] == list("ABCDEFGH")


def test_reserve_reports_max_attainable() -> None:
    rows = [_panel_row("A-p0", "A", True), _panel_row("A-p1", "A", True),
            _panel_row("A-b0", "A", False),
            _panel_row("B-p0", "B", True), _panel_row("B-b0", "B", False)]
    d = R.declare_reserve(pd.DataFrame(rows))
    assert d["n_provinces"] == 1
    assert d["deficits_max_attainable"]


@pytest.fixture(scope="module")
def freeze() -> dict:
    return json.loads(RESERVE_JSON.read_text())


def test_committed_reserve(freeze: dict) -> None:
    panel = pd.read_csv(PANEL_CSV)
    reserve_csv = pd.read_csv(RESERVE_CSV)
    assert freeze["reserve_name"] == R.RESERVE_NAME
    assert freeze["final_roles_status"] == R.FINAL_ROLES
    assert freeze["model_output_influence"] is False
    assert freeze["stage1_test_witness_eligible"] is False
    member_ids = [m["cell_id"] for m in freeze["members"]]
    assert len(member_ids) == freeze["n_cells"]
    assert set(member_ids) <= set(panel["cell_id"])
    assert set(reserve_csv["cell_id"]) == set(member_ids)
    assert freeze["n_provinces"] >= 4
    assert freeze["n_positive"] >= 8
    # every inspected Stage-1 cell is explicitly outside the reserve
    stage1 = set(freeze["stage1_inspected_test_witness"])
    assert not (stage1 & set(member_ids))
    recomputed = R.reserve_checksum(freeze)
    assert recomputed == freeze["checksum"]
