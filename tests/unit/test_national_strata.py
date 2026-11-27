"""Unit tests for the two-layer national cell strata taxonomy (Issue #16)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from spartina.data.national.strata import (
    CMSSM_2020_POSITIVE_ONLY,
    GOLD_EVIDENCE,
    MULTI_PRODUCT_SILVER_POSITIVE,
    NEAR_SILVER_UNLABELED,
    SILVER_2015_POSITIVE_ONLY,
    UNLABELED_COASTAL,
    assert_partition,
    assign_priority_stratum,
    stratum_counts,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STRATA_DIR = REPO_ROOT / "work" / "national" / "strata"


def _assign(row: dict[str, bool]) -> str:
    return assign_priority_stratum(
        silver_2015_positive=row.get("s", False),
        cmssm_2020_positive=row.get("c", False),
        silver_2015_nearby=row.get("n", False),
        gold_evidence=row.get("g", False),
    )


def test_priority_ladder_all_combinations() -> None:
    assert _assign({"g": True, "s": True, "c": True, "n": True}) is GOLD_EVIDENCE
    assert _assign({"s": True, "c": True, "n": True}) is MULTI_PRODUCT_SILVER_POSITIVE
    assert _assign({"s": True, "n": True}) is SILVER_2015_POSITIVE_ONLY
    assert _assign({"c": True, "n": True}) is CMSSM_2020_POSITIVE_ONLY
    assert _assign({"n": True}) is NEAR_SILVER_UNLABELED
    assert _assign({}) is UNLABELED_COASTAL


def test_nearby_never_overrides_positive() -> None:
    # nearby flag orthogonal: a positive cell stays in its positive stratum
    assert _assign({"s": True, "c": False, "n": True}) is SILVER_2015_POSITIVE_ONLY
    assert _assign({"s": False, "c": True, "n": True}) is CMSSM_2020_POSITIVE_ONLY


def test_stratum_counts_zero_filled_and_unknown_rejected() -> None:
    counts = stratum_counts([UNLABELED_COASTAL, GOLD_EVIDENCE])
    assert counts[GOLD_EVIDENCE] == 1
    assert counts[MULTI_PRODUCT_SILVER_POSITIVE] == 0
    assert sum(counts.values()) == 2
    with pytest.raises(ValueError, match="unknown strata"):
        stratum_counts(["NONSENSE"])


def _rows(labels: list[tuple[bool, bool, bool]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for s, c, n in labels:
        rows.append(
            {
                "gold_evidence": 0,
                "silver_2015_positive": int(s),
                "cmssm_2020_positive": int(c),
                "silver_2015_nearby": int(n and not s),
                "multi_product_positive": int(s and c),
                "cmsa_positive_history": 0,
                "management_evidence_available": 0,
                "exclusive_stratum": assign_priority_stratum(
                    silver_2015_positive=s,
                    cmssm_2020_positive=c,
                    silver_2015_nearby=n and not s,
                ),
            }
        )
    return rows


def test_assert_partition_sums_and_consistency() -> None:
    rows = _rows(
        [
            (True, True, False),
            (True, False, True),
            (False, True, False),
            (False, False, True),
            (False, False, False),
        ]
    )
    counts = assert_partition(rows, expected_cells=5)
    assert tuple(counts.values()) == (0, 1, 1, 1, 1, 1)


def test_assert_partition_rejects_inconsistent_label() -> None:
    rows = _rows([(False, False, False)])
    rows[0]["exclusive_stratum"] = GOLD_EVIDENCE
    with pytest.raises(ValueError, match="inconsistent"):
        assert_partition(rows)


def test_assert_partition_rejects_size_mismatch() -> None:
    rows = _rows([(False, False, False), (False, False, False)])
    with pytest.raises(ValueError, match="partition size"):
        assert_partition(rows, expected_cells=3)


@pytest.mark.parametrize(
    ("width", "expected_cells"),
    [("W5000", 8192), ("W10000", 3319), ("W20000", 1383)],
)
def test_built_strata_artifacts_partition_domain(width: str, expected_cells: int) -> None:
    csv_path = STRATA_DIR / f"strata_china_albers_{width}.csv"
    if not csv_path.exists():
        pytest.skip(f"strata artifact not built: {csv_path}")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    assert len(records) == expected_cells
    rows: list[dict[str, object]] = []
    for record in records:
        row: dict[str, object] = {
            key: int(value)
            for key, value in record.items()
            if key not in ("cell_id", "exclusive_stratum")
        }
        row["exclusive_stratum"] = record["exclusive_stratum"]
        rows.append(row)
    counts = assert_partition(rows, expected_cells=expected_cells)
    assert sum(counts.values()) == expected_cells


def test_w10_stratum_counts_are_canonical() -> None:
    csv_path = STRATA_DIR / "strata_china_albers_W10000.csv"
    if not csv_path.exists():
        pytest.skip("W10 strata artifact not built")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    counts = stratum_counts([r["exclusive_stratum"] for r in records])
    assert counts == {
        GOLD_EVIDENCE: 0,
        MULTI_PRODUCT_SILVER_POSITIVE: 309,
        SILVER_2015_POSITIVE_ONLY: 97,
        CMSSM_2020_POSITIVE_ONLY: 76,
        NEAR_SILVER_UNLABELED: 742,
        UNLABELED_COASTAL: 2095,
    }
    flags = {
        "silver_2015_positive": sum(int(r["silver_2015_positive"]) for r in records),
        "cmssm_2020_positive": sum(int(r["cmssm_2020_positive"]) for r in records),
        "silver_2015_nearby": sum(int(r["silver_2015_nearby"]) for r in records),
        "multi_product_positive": sum(int(r["multi_product_positive"]) for r in records),
    }
    assert flags == {
        "silver_2015_positive": 406,
        "cmssm_2020_positive": 385,
        "silver_2015_nearby": 812,
        "multi_product_positive": 309,
    }
