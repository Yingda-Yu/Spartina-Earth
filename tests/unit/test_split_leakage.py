"""Tests for the spatial-leakage split utility."""

from __future__ import annotations

import pytest

from spartina.evaluation.splits import (
    SpatialUnit,
    assert_spatially_disjoint,
    check_date_table_grouping,
    find_cross_split_overlaps,
)


def _units() -> dict[str, SpatialUnit]:
    # Two 1 km tiles 500 m apart (A ends at x=1000, B starts at x=1500).
    return {
        "A": SpatialUnit("A", 0.0, 0.0, 1000.0, 1000.0),
        "B": SpatialUnit("B", 1500.0, 0.0, 2500.0, 1000.0),
    }


def test_disjoint_units_pass_without_buffer() -> None:
    units = _units()
    split_of = {"A": "train", "B": "test"}
    assert find_cross_split_overlaps(split_of, units, buffer_m=0.0) == []
    assert_spatially_disjoint(split_of, units, buffer_m=0.0)


def test_buffer_catches_nearby_train_test_tiles() -> None:
    units = _units()
    split_of = {"A": "train", "B": "test"}
    # 500 m gap < default 250 m? No — 500 > 250, so default passes...
    assert find_cross_split_overlaps(split_of, units, buffer_m=250.0) == []
    # ...but a 750 m buffer exceeds the 500 m gap and must be flagged.
    violations = find_cross_split_overlaps(split_of, units, buffer_m=750.0)
    assert len(violations) == 1
    assert violations[0][:2] == ("A", "B")
    with pytest.raises(ValueError, match="Spatial leakage"):
        assert_spatially_disjoint(split_of, units, buffer_m=750.0)


def test_same_split_neighbors_are_not_flagged() -> None:
    units = _units()
    split_of = {"A": "train", "B": "train"}
    assert find_cross_split_overlaps(split_of, units, buffer_m=1000.0) == []


def test_random_patch_like_overlap_is_rejected() -> None:
    # Two tiles literally overlapping (adjacent random patches).
    units = {
        "P1": SpatialUnit("P1", 0.0, 0.0, 100.0, 100.0),
        "P2": SpatialUnit("P2", 50.0, 0.0, 150.0, 100.0),
    }
    split_of = {"P1": "train", "P2": "test"}
    with pytest.raises(ValueError, match="Spatial leakage"):
        assert_spatially_disjoint(split_of, units, buffer_m=0.0)


def test_temporal_grouping_violation_detected() -> None:
    # Same unit appearing in train at one date and test at another.
    rows = [("A", "train"), ("A", "test"), ("B", "train")]
    offenders = check_date_table_grouping(rows)
    assert offenders == {"A": ["test", "train"]}
    assert check_date_table_grouping([("A", "train"), ("B", "test")]) == {}


def test_invalid_unit_extent_rejected() -> None:
    with pytest.raises(ValueError, match="non-positive extent"):
        SpatialUnit("bad", 10.0, 0.0, 0.0, 10.0)
