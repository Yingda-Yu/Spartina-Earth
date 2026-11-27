"""Step 4/11/13: the committed Pilot-0 window manifest and split registry
must be internally consistent and pass the full leakage audit."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from spartina.benchmark.splits.leakage import AuditInputs, run_audit

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "datasets/manifests/hangzhou2015_tiles_v1.csv"
PARQUET_PATH = ROOT / "datasets/manifests/hangzhou2015_tiles_v1.parquet"
JSON_PATH = ROOT / "benchmarks/spartinashift/pilot0_splits_v1.json"

REQUIRED_COLUMNS = {
    "tile_id", "source_stack_version", "source_stack_checksum",
    "row_off", "col_off", "height", "width", "bounds_utm",
    "bounds_wgs84", "split", "silver_positive_pixels", "silver_fraction",
    "weak_positive_pixels", "weak_fraction", "ignore_pixels",
    "ignore_fraction", "weak_only_candidate_pixels",
    "weak_only_candidate_fraction", "optical_valid_fraction",
    "sar_valid_fraction", "vv_valid_fraction", "vh_valid_fraction",
    "indices_valid_fraction", "optical_available", "sar_available",
    "indices_available", "silver_component_ids",
    "weak_candidate_component_ids", "eligible_for_train",
    "eligible_for_eval", "exclusion_reason",
}

LIST_FIELDS = ("bounds_utm", "bounds_wgs84", "silver_component_ids",
               "weak_candidate_component_ids", "source_transform")
INT_FIELDS = ("row_off", "col_off", "height", "width",
              "silver_positive_pixels", "silver_eval_pixels",
              "weak_positive_pixels", "weak_eval_pixels",
              "ignore_pixels", "weak_only_candidate_pixels")
FLOAT_FIELDS = ("silver_fraction", "weak_fraction", "ignore_fraction",
                "weak_only_candidate_fraction", "optical_valid_fraction",
                "sar_valid_fraction", "vv_valid_fraction",
                "vh_valid_fraction", "indices_valid_fraction")
BOOL_FIELDS = ("eligible_for_train", "eligible_for_eval",
               "optical_available", "sar_available", "indices_available")


@pytest.fixture(scope="module")
def records() -> list[dict]:
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in LIST_FIELDS:
            r[k] = json.loads(r[k])
        for k in INT_FIELDS:
            r[k] = int(r[k])
        for k in FLOAT_FIELDS:
            r[k] = float(r[k])
        for k in BOOL_FIELDS:
            r[k] = r[k].lower() == "true"
    return rows


@pytest.fixture(scope="module")
def registry() -> dict:
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_manifest_schema_complete(records: list[dict]) -> None:
    assert REQUIRED_COLUMNS.issubset(records[0].keys())
    assert len(records) >= 200


def test_split_registry_records_pass_audit(
    records: list[dict], registry: dict,
) -> None:
    regions = {
        k: tuple(v["usable"])
        for k, v in registry["splits"]["regions"].items()
    }
    guard = int(registry["splits"]["guard_px"])
    first = records[0]
    violations = run_audit(AuditInputs(
        records=records, regions=regions, guard_px=guard,
        expected_stack_checksum=first["source_stack_checksum"],
        expected_crs=first["source_crs"],
        expected_transform=tuple(first["source_transform"]),
        patch=first["width"],
    ))
    assert violations == [], [
        (v.code, v.detail) for v in violations]
    assert registry["audit"]["pass"] is True
    assert registry["audit"]["n_violations"] == 0


def test_tile_and_window_identity_unique(records: list[dict]) -> None:
    ids = [r["tile_id"] for r in records]
    geoms = [(r["row_off"], r["col_off"], r["height"], r["width"])
             for r in records]
    assert len(ids) == len(set(ids))
    assert len(geoms) == len(set(geoms))


def test_blocked_windows_excluded_and_documented(
    records: list[dict],
) -> None:
    for r in records:
        if r["split"] in {"train", "val", "test"}:
            assert r["exclusion_reason"] == ""
        else:
            assert r["exclusion_reason"]
            assert r["silver_component_ids"] == []
            assert r["weak_candidate_component_ids"] == []
            assert not r["eligible_for_train"]
            assert not r["eligible_for_eval"]


def test_eval_windows_only_in_val_and_test(records: list[dict]) -> None:
    for r in records:
        if r["eligible_for_eval"]:
            assert r["split"] in {"val", "test"}
            assert r["silver_eval_pixels"] >= 1


def test_fingerprints_present(registry: dict) -> None:
    wm = registry["window_manifest"]
    assert len(wm["logical_manifest_fingerprint_sha256"]) == 64
    assert len(wm["parquet_container_sha256"]) == 64
    assert len(registry["config_fingerprint_sha256"]) == 64
    assert registry["config"]["labels"]["gold_available"] is False


def test_parquet_artifact_matches_csv_schema(
    records: list[dict],
) -> None:
    pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq
    table = pq.read_table(PARQUET_PATH)
    assert table.num_rows == len(records)
    assert set(table.column_names) == set(records[0].keys())
