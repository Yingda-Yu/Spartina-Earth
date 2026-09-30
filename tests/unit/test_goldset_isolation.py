"""Unit tests for the GoldSet isolation freeze gate (Issue #11)."""

from __future__ import annotations

import pytest

from spartina.evaluation.goldset_isolation import (
    Envelope,
    GoldsetIsolationError,
    assert_gold_isolated,
    envelopes_from_records,
    find_gold_overlaps,
)


def _env(site_id: str, bounds: tuple[float, float, float, float],
         crs: int = 32651) -> Envelope:
    return Envelope(site_id=site_id, bounds=bounds, crs_epsg=crs)


def test_disjoint_units_pass_and_overlaps_fail() -> None:
    gold = [_env("GOLD-A", (0.0, 0.0, 10.0, 10.0))]
    far = [_env("TRAIN-T1", (100.0, 100.0, 110.0, 110.0))]
    assert_gold_isolated(gold, far, buffer_m=5.0)

    touching = [_env("VAL-V1", (9.0, 9.0, 20.0, 20.0))]
    events = find_gold_overlaps(gold, touching, buffer_m=0.0)
    assert len(events) == 1 and events[0].blocked_unit_id == "VAL-V1"
    with pytest.raises(GoldsetIsolationError, match="GOLD-A"):
        assert_gold_isolated(gold, touching)


def test_buffer_expands_the_exclusion_zone() -> None:
    gold = [_env("GOLD-B", (0.0, 0.0, 10.0, 10.0))]
    # 4 m away on x: disjoint without buffer, overlapping with 5 m buffer
    near = [_env("TRAIN-T2", (14.0, 0.0, 24.0, 10.0))]
    assert_gold_isolated(gold, near, buffer_m=0.0)
    with pytest.raises(GoldsetIsolationError):
        assert_gold_isolated(gold, near, buffer_m=5.0)


def test_cross_crs_check_is_refused() -> None:
    gold = [_env("GOLD-C", (0.0, 0.0, 10.0, 10.0), crs=32651)]
    other_crs = [_env("TRAIN-T3", (5.0, 5.0, 15.0, 15.0), crs=32650)]
    with pytest.raises(GoldsetIsolationError, match="across CRS"):
        assert_gold_isolated(gold, other_crs)


def test_records_parse_and_invalid_geometry_rejected() -> None:
    parsed = envelopes_from_records([
        {"site_id": "GOLD-D", "bounds": [0, 0, 10, 10], "crs_epsg": 32651}])
    assert parsed[0].site_id == "GOLD-D"
    with pytest.raises(ValueError):
        Envelope("bad", (10.0, 10.0, 0.0, 20.0), crs_epsg=32651)
    with pytest.raises(ValueError):
        envelopes_from_records(
            [{"site_id": "x", "bounds": [0, 0, 10], "crs_epsg": 32651}])
