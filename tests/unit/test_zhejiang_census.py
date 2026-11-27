"""Pure-logic tests for the metadata census: era gating, seasons, guard."""

from __future__ import annotations

import types
from datetime import UTC

import pytest

from spartina.data.zhejiang.census import (
    SLC_FAILURE_DATE,
    ExportAttempted,
    _BlockedExport,
    install_export_guard,
    is_operational,
    parse_utc,
    slc_status_for_date,
    summarize_group,
)
from spartina.data.zhejiang.contracts import (
    GAP_NO_QUALITY,
    GAP_NO_SCENES,
    GAP_NONE,
    GAP_NOT_OPERATIONAL,
    SLC_POST_FAILURE,
    SLC_PRE_FAILURE,
)

WINDOWS = [
    {"id": "autumn_v0", "doy_start": 260, "doy_end": 305},
    {"id": "summer_v0", "doy_start": 152, "doy_end": 212},
]


def _scene(doy, cov=1.0, cloud=0.1, orbit=None):
    from datetime import datetime, timedelta
    dt = datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=doy - 1)
    return {
        "acquisition_utc": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "day_of_year": doy,
        "footprint_coverage_fraction": cov,
        "scene_cloud_fraction": cloud,
        "orbit_direction": orbit,
    }


def _summarize(sensor, scenes, year=2020, operational=True):
    return summarize_group(
        roi_id="ZJ-X", year=year, sensor=sensor,
        collection_id="c/x", operational=operational, scenes=scenes,
        retrieval_ts="2026-10-01T00:00:00Z", season_windows=WINDOWS,
        scene_cloud_max=0.30, footprint_coverage_min=0.99)


def test_parse_utc_rejects_naive_and_empty():
    assert parse_utc("") is None
    assert parse_utc("2020-01-01T00:00:00") is None  # naive -> rejected
    dt = parse_utc("2020-01-01T12:00:00Z")
    assert dt is not None and dt.utcoffset().total_seconds() == 0


def test_slc_boundary_date():
    assert SLC_FAILURE_DATE == "2003-05-31"
    assert slc_status_for_date("2003-05-30T00:00:00Z") == SLC_PRE_FAILURE
    assert slc_status_for_date("2003-05-31T00:00:00Z") == SLC_POST_FAILURE
    assert slc_status_for_date("2024-01-01T00:00:00Z") == SLC_POST_FAILURE


def test_operational_span_inclusive():
    assert is_operational(1984, (1984, 2012))
    assert is_operational(2012, (1984, 2012))
    assert not is_operational(2013, (1984, 2012))


def test_pre_operational_group_is_not_zero_scenes_gap():
    row = _summarize("landsat9", [], year=2020, operational=False)
    assert row["gap_status"] == GAP_NOT_OPERATIONAL
    assert row["total_scenes"] == 0
    assert row["query_status"] == "NOT_QUERIED_OUTSIDE_OPERATIONAL_YEARS"
    assert row["quality_candidate_scenes"] is None  # pixel QA never run
    # fingerprint must be deterministic
    row2 = _summarize("landsat9", [], year=2020, operational=False)
    assert row["summary_fingerprint"] == row2["summary_fingerprint"]


def test_operational_empty_year_is_no_scenes_not_era():
    row = _summarize("sentinel2", [], year=2020)
    assert row["gap_status"] == GAP_NO_SCENES
    assert row["operational"] is True


def test_optical_gate_no_full_coverage_or_too_cloudy():
    scenes = [_scene(270, cov=0.98, cloud=0.1),
              _scene(280, cov=1.0, cloud=0.5)]
    row = _summarize("sentinel2", scenes)
    assert row["gap_status"] == GAP_NO_QUALITY
    assert row["season_candidate_scenes"] == 0


def test_optical_season_candidate_counts_windows():
    scenes = [_scene(270), _scene(300), _scene(180),
              _scene(10), _scene(150, cloud=0.9)]
    row = _summarize("landsat8", scenes)
    assert row["gap_status"] == GAP_NONE
    assert row["season_candidate_scenes"] == 3
    assert row["season_candidate_window_ids"] == "autumn_v0|summer_v0"


def test_sar_uses_coverage_only():
    row = _summarize("sentinel1",
                     [_scene(270, cov=0.5, cloud=None, orbit="ASCENDING")])
    assert row["gap_status"] == GAP_NO_QUALITY
    assert row["scene_cloud_eligible_scenes"] is None
    assert row["scenes_ascending"] == 1
    row2 = _summarize("sentinel1",
                      [_scene(270, cov=1.0, orbit="DESCENDING")])
    assert row2["gap_status"] == GAP_NONE
    assert row2["scenes_descending"] == 1
    assert row2["season_candidate_scenes"] == 1


def test_export_guard_blocks_and_restores():
    sentinel = object()
    fake_batch = types.SimpleNamespace(Export=sentinel)
    fake_ee = types.SimpleNamespace(batch=fake_batch)
    restore = install_export_guard(fake_ee)
    assert isinstance(fake_batch.Export, _BlockedExport)
    with pytest.raises(ExportAttempted, match="forbidden"):
        fake_batch.Export.toDrive(**{"x": 1})
    restore()
    assert fake_batch.Export is sentinel
