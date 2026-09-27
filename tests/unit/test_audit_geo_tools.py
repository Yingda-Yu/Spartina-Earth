"""Tests for raster/vector forensic tools (require the spartina-earth env)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

rasterio = pytest.importorskip("rasterio")
fiona = pytest.importorskip("fiona")

import inspect_raster as ir  # noqa: E402
import inspect_vector as iv  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402


def _write_mask_raster(path: Path, crs: str, geotransform, value_grid) -> Path:
    import numpy as np

    arr = np.array(value_grid, dtype="uint8")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=arr.shape[1],
        height=arr.shape[0],
        count=1,
        dtype="uint8",
        crs=crs,
        transform=geotransform,
    ) as dst:
        dst.write(arr, 1)
    return path


def test_raster_projected_area_is_count_times_pixel_area(tmp_path: Path) -> None:
    # 30 m pixels in UTM 51N; two positive pixels -> 2 * 900 m^2
    path = _write_mask_raster(
        tmp_path / "m.tif",
        "EPSG:32651",
        from_origin(300000, 3400000, 30.0, 30.0),
        [[1, 0], [0, 1]],
    )
    report = ir.inspect(path, classify_mode="auto")
    stats = report["class_statistics_band_1"]
    assert stats["positive_pixel_count"] == 2
    assert report["area"]["positive_area_km2"] == pytest.approx(0.0018)
    assert report["area"]["method"].startswith("pixel_count_x_transform")


def test_raster_geographic_area_guard_never_degrees_squared(tmp_path: Path) -> None:
    path = _write_mask_raster(
        tmp_path / "g.tif",
        "EPSG:4326",
        from_origin(121.0, 30.5, 0.001, 0.001),
        [[1, 0], [0, 1]],
    )
    report = ir.inspect(path, classify_mode="auto")
    assert report["crs_is_geographic"] is True
    assert report["area"]["positive_area_km2"] is None
    assert any("GEOGRAPHIC_CRS" in g for g in report["area"]["guards"])
    assert report["area"]["footprint_geodetic_area_km2"] > 0


def test_raster_metadata_bands_and_compression(tmp_path: Path) -> None:
    import numpy as np

    path = tmp_path / "multi.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=4, height=3, count=2,
        dtype="uint16", crs="EPSG:32651",
        transform=from_origin(300000, 3400000, 10, 10),
    ) as dst:
        dst.write(np.zeros((3, 4), dtype="uint16"), 1)
        dst.write(np.ones((3, 4), dtype="uint16"), 2)
        dst.set_band_description(1, "B4")
        dst.set_band_description(2, "B3")
    report = ir.inspect(path, classify_mode="auto")
    assert report["band_count"] == 2
    assert report["bands"][0]["description"] == "B4"
    assert report["width"] == 4 and report["height"] == 3


def test_vector_reports_invalid_and_sliver_and_hectare_field(tmp_path: Path) -> None:
    from shapely.geometry import Polygon, mapping

    # A 100 m x 100 m valid square (1 ha), plus a tiny sliver, plus a
    # bowtie (self-intersecting) polygon.
    valid = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    sliver = Polygon([(200, 0), (205, 0), (205, 5), (200, 5)])  # 25 m^2
    bowtie = Polygon([(300, 0), (320, 20), (300, 20), (320, 0)])
    schema = {"geometry": "Polygon", "properties": {"area": "float", "Id": "int"}}
    records = [
        {"geometry": mapping(valid), "properties": {"area": 1.0, "Id": 1}},
        {"geometry": mapping(sliver), "properties": {"area": 0.0025, "Id": 2}},
        {"geometry": mapping(bowtie), "properties": {"area": 0.01, "Id": 3}},
    ]
    path = tmp_path / "v.geojson"
    with fiona.open(path, "w", driver="GeoJSON", crs="EPSG:32651", schema=schema) as col:
        col.writerecords(records)

    report = iv.inspect(path)
    assert report["feature_count"] == 3
    assert report["invalid_geometries"] >= 1
    assert any("intersection" in r.lower() for r in report["invalid_reasons"])
    assert report["area_summary"]["geometries_smaller_than_100m2"] >= 1
    # the area field is in hectares (ratio ~10000 m^2 per field unit)
    fr = report["area_field_forensics"]["area"]
    assert fr["median_ratio_computed_m2_over_field"] == pytest.approx(10000.0, rel=1e-3)


def test_vector_geographic_crs_uses_geodetic_area(tmp_path: Path) -> None:
    from shapely.geometry import Polygon, mapping

    # ~100 m square near the Fujian site
    poly = Polygon([
        (121.20, 28.35), (121.2011, 28.35),
        (121.2011, 28.3509), (121.20, 28.3509),
    ])
    schema = {"geometry": "Polygon", "properties": {"Area_ha": "float"}}
    path = tmp_path / "geo.geojson"
    with fiona.open(path, "w", driver="GeoJSON", crs="EPSG:4326", schema=schema) as col:
        col.write({"geometry": mapping(poly), "properties": {"Area_ha": 0.01}})
    report = iv.inspect(path)
    area_km2 = report["area_summary"]["computed_total_area_km2"]
    assert 0.005 < area_km2 < 0.02  # geodetic, never degree^2


def test_raster_report_is_json_serializable(tmp_path: Path) -> None:
    path = _write_mask_raster(
        tmp_path / "m.tif", "EPSG:32651", from_origin(0, 0, 30, 30), [[1]]
    )
    report = ir.inspect(path, classify_mode="auto")
    json.dumps(report)  # no numpy scalars leak
