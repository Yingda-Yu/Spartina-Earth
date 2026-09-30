"""Real GEE integration smoke tests.

Auto-skip unless genuine credentials are present. Never runs under the
default M0 test selection in CI; execute manually in M1+ with:

    pytest -m gee_integration

Even then, these stay tiny catalog/export smokes on one small ROI —
never nationwide downloads.
"""

from __future__ import annotations

import os

import pytest

from spartina.data.gee import auth
from spartina.data.gee.catalog import (
    EarthEngineCatalogClient,
    Region,
    SceneQuery,
)
from spartina.data.gee.quality import (
    CloudCoverFilter,
    apply_filters,
    build_candidate_table,
    candidate_records,
)

pytestmark = [
    pytest.mark.gee_integration,
    pytest.mark.skipif(
        not auth.credentials_available(),
        reason="GEE credentials not configured; integration test skipped.",
    ),
]

# Small Hangzhou Bay pilot ROI (~0.02 deg box), UTM 51N. Query one sensor
# over one month — the minimum needed to verify real scene provenance.
HZ_SMALL_ROI = Region(
    geometry={
        "type": "Polygon",
        "coordinates": [[
            [121.10, 30.30], [121.12, 30.30], [121.12, 30.32],
            [121.10, 30.32], [121.10, 30.30]]],
    },
    crs_epsg=4326,
)


def test_ee_initialize_smoke() -> None:
    """Initialize and perform one tiny catalog-level operation."""
    auth.initialize()  # pragma: no cover - requires real credentials
    import ee  # type: ignore[import-not-found]  # pragma: no cover

    result = ee.Number(1).getInfo()  # pragma: no cover
    assert result == 1  # pragma: no cover


def test_landsat8_candidate_provenance_small_roi() -> None:
    """Real L8 scenes must carry scene id, product id and exact UTC time.

    Regression guard for the Issue #6 requirement: no composite may ever
    again be recorded as '2015 with source scenes UNKNOWN'.
    """
    client = EarthEngineCatalogClient()  # pragma: no cover
    query = SceneQuery(
        sensor_name="landsat8",
        start_date="2015-06-01", end_date="2015-07-31",
        region=HZ_SMALL_ROI, max_cloud_cover=1.0,
    )
    scenes = client.query(query)  # pragma: no cover
    assert scenes, "no L8 scenes returned for the small ROI"  # pragma: no cover
    for scene in scenes:  # pragma: no cover
        assert scene.scene_id and scene.extra.get("product_id")
        assert scene.acquisition_time.endswith("+00:00")
        assert scene.extra.get("wrs_path") is not None

    accepted = apply_filters(scenes, [CloudCoverFilter(0.8)])
    table = build_candidate_table(
        scenes, frozenset(s.scene_id for s in accepted))
    records = candidate_records(table)
    assert len(records) == len(scenes)  # pragma: no cover
    assert all("acquisition_utc" in row for row in records)


@pytest.mark.skipif(
    os.environ.get("SPARTINA_GEE_SMOKE_EXPORT") != "1",
    reason="operator must opt in (SPARTINA_GEE_SMOKE_EXPORT=1) for even a "
           "tiny real export; default integration run is catalog-only",
)
def test_tiny_direct_export_smoke() -> None:
    """Operator-enabled, single-tile export smoke (never bulk).

    Left as an explicit opt-in checkpoint: when credentials exist and the
    operator sets the env var, run one tiny getDownloadURL landing +
    checksum/manifest round trip on HZ_SMALL_ROI.
    """
    raise pytest.skip(  # pragma: no cover
        "direct export smoke orchestration is driven manually via the "
        "factory pipeline; this guard prevents accidental exports")
