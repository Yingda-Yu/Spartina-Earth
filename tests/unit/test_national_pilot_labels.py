"""Unit tests for the Issue #19 pilot label-support policy."""

from __future__ import annotations

import numpy as np
import pytest

from spartina.data.national.pilot_labels import (
    LABEL_SOURCES,
    PURE_HI,
    PURE_LO,
    SOURCE_BY_KEY,
    LabelKind,
    OccupancyClass,
    assert_repair_area_change,
    class_counts,
    classify_fractions,
    classify_positive_only_fractions,
    positive_area_km2,
)


def test_classify_fractions_thresholds_inclusive() -> None:
    frac = np.array([np.nan, 0.0, PURE_LO, 0.5, PURE_HI, 1.0])
    out = classify_fractions(frac)
    assert out.tolist() == [
        OccupancyClass.UNKNOWN,
        OccupancyClass.PURE_NEGATIVE,
        OccupancyClass.PURE_NEGATIVE,
        OccupancyClass.MIXED,
        OccupancyClass.PURE_POSITIVE,
        OccupancyClass.PURE_POSITIVE,
    ]


def test_classify_unknown_mask_overrides_everything() -> None:
    frac = np.array([0.0, 0.5, 1.0, np.nan])
    unknown = np.array([True, True, True, True])
    out = classify_fractions(frac, unknown=unknown)
    assert np.all(out == OccupancyClass.UNKNOWN)


def test_positive_only_never_negative() -> None:
    frac = np.array([np.nan, 0.0, 0.001, PURE_LO, 0.5,
                     PURE_HI - 1e-12, PURE_HI, 1.0])
    out = classify_positive_only_fractions(frac)
    assert out.tolist() == [
        OccupancyClass.UNKNOWN,        # NaN
        OccupancyClass.UNKNOWN,        # uncovered
        OccupancyClass.MIXED,          # sliver is partial, not negative
        OccupancyClass.MIXED,
        OccupancyClass.MIXED,
        OccupancyClass.MIXED,
        OccupancyClass.PURE_POSITIVE,
        OccupancyClass.PURE_POSITIVE,
    ]
    assert not np.any(out == OccupancyClass.PURE_NEGATIVE)


def test_positive_only_gridcode_zero_overrides_positive() -> None:
    frac = np.array([1.0, 0.5, 0.0])
    unknown = np.array([True, False, True])
    out = classify_positive_only_fractions(frac, unknown=unknown)
    assert out.tolist() == [
        OccupancyClass.UNKNOWN,
        OccupancyClass.MIXED,
        OccupancyClass.UNKNOWN,
    ]


def test_class_counts_and_total() -> None:
    classes = np.array([
        OccupancyClass.PURE_POSITIVE, OccupancyClass.PURE_POSITIVE,
        OccupancyClass.MIXED, OccupancyClass.PURE_NEGATIVE,
        OccupancyClass.UNKNOWN])
    counts = class_counts(classes)
    assert counts == {
        "n_pure_positive": 2, "n_mixed": 1, "n_pure_negative": 1,
        "n_unknown": 1, "n_total": 5}


def test_positive_area_km2_ignores_nan_and_unknown() -> None:
    # two fully covered 30 m pixels = 0.0018 km2; half pixel = 0.00045.
    frac = np.array([1.0, 1.0, 0.5, np.nan, 0.0])
    area = positive_area_km2(frac, 30.0 ** 2)
    assert area == pytest.approx(0.00225)
    unknown = np.array([False, True, False, True, False])
    area_u = positive_area_km2(frac, 30.0 ** 2, unknown)
    assert area_u == pytest.approx(0.00135)


def test_repair_guard() -> None:
    assert_repair_area_change(100.0, 100.5, tolerance=0.01)
    with pytest.raises(ValueError, match="STOP"):
        assert_repair_area_change(100.0, 101.0, tolerance=0.01)
    with pytest.raises(ValueError):
        assert_repair_area_change(0.0, 0.0)


def test_source_matrix_invariants() -> None:
    assert len(LABEL_SOURCES) == 10
    assert len(SOURCE_BY_KEY) == len(LABEL_SOURCES)
    keys = [s.key for s in LABEL_SOURCES]
    assert len(set(keys)) == len(keys)
    geodata = [s for s in LABEL_SOURCES if s.family == "GEODATA"]
    cmsa = [s for s in LABEL_SOURCES if s.family == "CMSA"]
    cmssm = [s for s in LABEL_SOURCES if s.family == "CM-SSM"]
    assert len(geodata) == 4 and len(cmsa) == 5 and len(cmssm) == 1
    # 30 m native products must never land on 10 m supports.
    for s in geodata + cmsa:
        assert s.supports_m == (30,)
        assert s.kind in (LabelKind.BINARY_RASTER, LabelKind.POSITIVE_POLYGONS)
    assert tuple(cmssm[0].supports_m) == (10, 30)
    # Positive-only products document no negative semantics.
    for s in cmsa + cmssm:
        assert "no PURE_NEGATIVE" in s.negative_semantics


def test_gridcode_zero_is_unknown_not_negative() -> None:
    cmsa = [s for s in LABEL_SOURCES if s.family == "CMSA"]
    assert all("gridcode == 0" in s.unknown_rule for s in cmsa)
    assert all("no PURE_NEGATIVE" in s.negative_semantics for s in cmsa)
