"""Live but metadata-only census smoke for one (bay, year, sensor) group.

Run with:  pytest -m gee_integration -k zhejiang -v

Guarantees for the M2.1a boundary:
* one getInfo only, scene metadata + footprint coverage fraction;
* the export guard blocks ee.batch.Export for the duration of the call;
* all timestamps are timezone-aware UTC.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import shape

from spartina.data.gee import auth
from spartina.data.zhejiang.census import (
    ExportAttempted,
    GroupQuery,
    _BlockedExport,
    install_export_guard,
    parse_utc,
    query_group_scenes,
)

pytestmark = [
    pytest.mark.gee_integration,
    pytest.mark.skipif(not auth.credentials_available(),
                       reason="GEE credentials not configured."),
    pytest.mark.skipif(not auth.configured_project(),
                       reason="SPARTINA_GEE_PROJECT is unset."),
]

ROIS = (Path(__file__).resolve().parents[2]
        / "datasets/rois/zhejiang_bays_v0.geojson")


def test_yqb_2020_landsat8_metadata_group():
    import ee  # imported only when the marker is selected

    auth.initialize()
    fc = json.loads(ROIS.read_text(encoding="utf-8"))
    geom = shape(next(f["geometry"] for f in fc["features"]
                      if f["properties"]["roi_id"] == "ZJ-YQB"))

    restore = install_export_guard(ee)
    try:
        assert isinstance(ee.batch.Export, _BlockedExport)
        scenes = query_group_scenes(
            ee, geometry=geom,
            query=GroupQuery("ZJ-YQB", 2020, "landsat8",
                             "LANDSAT/LC08/C02/T1_L2"),
            coverage_scale_m=30)
        with pytest.raises(ExportAttempted):
            ee.batch.Export.image.toDrive(image=None)
    finally:
        restore()

    assert len(scenes) > 0  # 2020 L8 coverage of Yueqing Bay is observed
    ids = [s["scene_id"] for s in scenes]
    assert len(ids) == len(set(ids))
    for s in scenes:
        dt = parse_utc(s["acquisition_utc"])
        assert dt is not None and dt.tzinfo is not None
        assert s["day_of_year"] == dt.timetuple().tm_yday
        cov = s["footprint_coverage_fraction"]
        assert cov is None or 0.0 <= cov <= 1.0
        assert s["slc_status"] == "NOT_APPLICABLE"
