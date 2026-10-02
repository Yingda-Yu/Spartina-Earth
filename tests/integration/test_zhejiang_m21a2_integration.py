"""Live but metadata-only M2.1a2 smoke: verify the DATATAKE property.

Run with:  pytest -m gee_integration -k m21a2 -v

Guarantees for the M2.1a2 boundary:
* exactly one getInfo (one representative S2 SR scene over Zhejiang);
* only scene METADATA is read - no pixels, no export, no download;
* the export guard blocks ee.batch.Export for the duration.

The assertion underpins the S2 grouping rule: if GEE ever stops exposing
``DATATAKE_IDENTIFIER`` on the C2 harmonized SR collection, grouping must
fall back to the flagged FALLBACK rule rather than silently mis-grouping.
"""

from __future__ import annotations

import pytest

from spartina.data.gee import auth
from spartina.data.zhejiang.census import (
    ExportAttempted,
    install_export_guard,
)

pytestmark = [
    pytest.mark.gee_integration,
    pytest.mark.skipif(not auth.credentials_available(),
                       reason="GEE credentials not configured."),
    pytest.mark.skipif(not auth.configured_project(),
                       reason="SPARTINA_GEE_PROJECT is unset."),
]


def test_s2_datatake_identifier_present_metadata_only() -> None:
    import ee  # local import: package must import without ee installed

    auth.initialize()
    restore = install_export_guard(ee)
    try:
        col = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(ee.Geometry.Rectangle(
                [121.2, 29.0, 121.6, 29.4]))
            .filterDate("2023-10-01", "2023-10-31")
            .limit(1))
        info = col.first().getInfo()  # ONE metadata getInfo, no pixels
        props = info["properties"]
        assert "DATATAKE_IDENTIFIER" in props
        datatake = props["DATATAKE_IDENTIFIER"]
        assert isinstance(datatake, str) and datatake.startswith("GS2")
        assert props["MGRS_TILE"]  # tile property needed by frame keys

        with pytest.raises(ExportAttempted):
            ee.batch.Export.image.toDrive(image=col.first(),
                                          description="guard-check")
    finally:
        restore()
