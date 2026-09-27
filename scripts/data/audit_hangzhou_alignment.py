"""Read-only alignment audit of the Hangzhou Bay 2015 asset bundle.

Compares the georeferencing grids of the mask, Landsat stack, NDVI/SAI
indices and Sentinel-1 images WITHOUT resampling any pixel. Reprojection
is applied only to bounds/center points for comparison.

Outputs a single JSON describing per-file grids, ground pixel sizes in
metres, and pairwise footprint overlap in the analysis CRS.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ANALYSIS_CRS = "EPSG:32651"  # WGS 84 / UTM zone 51N (Hangzhou ~121E)


def ground_pixel_meters(
    src_crs: Any,
    transform: Any,
    center_lonlat: tuple[float, float],
) -> tuple[float | None, float | None]:
    """Measure one-pixel ground span in metres near the raster center."""
    from pyproj import Transformer

    if src_crs is None:
        return None, None
    if src_crs.is_projected:
        return abs(float(transform.a)), abs(float(transform.e))
    if not src_crs.is_geographic:
        return None, None
    to_utm = Transformer.from_crs(src_crs, ANALYSIS_CRS, always_xy=True)
    lon0, lat0 = center_lonlat
    x0, y0 = to_utm.transform(lon0, lat0)
    x1, y1 = to_utm.transform(lon0 + abs(float(transform.a)), lat0)
    x2, y2 = to_utm.transform(lon0, lat0 + abs(float(transform.e)))
    return abs(x1 - x0), abs(y2 - y0)


def inspect(path: Path) -> dict[str, Any]:
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(path) as ds:
        crs = ds.crs
        crs_label = "NONE"
        if crs is not None:
            code = crs.to_epsg()
            crs_label = f"EPSG:{code}" if code else "CRS_WKT_PRESENT_EPSG_UNKNOWN"
        bounds = list(ds.bounds)
        center_lonlat: tuple[float, float]
        if crs is not None and crs.is_geographic:
            center_lonlat = (
                (bounds[0] + bounds[2]) / 2,
                (bounds[1] + bounds[3]) / 2,
            )
            analysis_bounds = list(
                transform_bounds(crs, ANALYSIS_CRS, *bounds, densify_pts=21)
            )
        elif crs is not None and crs.to_epsg() == 32651:
            center_lonlat = (0.0, 0.0)  # unused for projected input
            analysis_bounds = bounds[:]
        else:
            center_lonlat = (0.0, 0.0)
            analysis_bounds = list(
                transform_bounds(crs, ANALYSIS_CRS, *bounds, densify_pts=21)
            ) if crs is not None else [None] * 4
        gx, gy = ground_pixel_meters(crs, ds.transform, center_lonlat)
        return {
            "path": str(path),
            "crs": crs_label,
            "width": ds.width,
            "height": ds.height,
            "band_count": ds.count,
            "dtypes": sorted(set(ds.dtypes)),
            "native_bounds": [round(v, 8) for v in bounds],
            "analysis_crs": ANALYSIS_CRS,
            "bounds_in_analysis_crs": (
                [round(v, 3) if v is not None else None for v in analysis_bounds]
                if analysis_bounds[0] is not None
                else None
            ),
            "native_pixel_size": [float(ds.transform.a), float(ds.transform.e)],
            "ground_pixel_meters_at_center": (
                [round(gx, 3), round(gy, 3)]
                if gx is not None and gy is not None
                else None
            ),
            "band_descriptions": [d for d in ds.descriptions],
            "tags": dict(ds.tags()),
        }


def pairwise_overlap(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    boxes = {
        item["path"]: item["bounds_in_analysis_crs"]
        for item in items
    }
    names = list(boxes)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = boxes[names[i]], boxes[names[j]]
            if a is None or b is None:
                rows.append({"a": names[i], "b": names[j], "overlap_km2": None})
                continue
            ax0, ay0, ax1, ay1 = a
            bx0, by0, bx1, by1 = b
            ix0, iy0 = max(ax0, bx0), max(ay0, by0)
            ix1, iy1 = min(ax1, bx1), min(ay1, by1)
            area = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0) / 1e6
            area_a = (ax1 - ax0) * (ay1 - ay0) / 1e6
            rows.append(
                {
                    "a": Path(names[i]).name,
                    "b": Path(names[j]).name,
                    "intersection_km2": round(area, 4),
                    "fraction_of_a": round(area / area_a, 4) if area_a else None,
                }
            )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    items = [inspect(p) for p in args.input]
    payload = {
        "analysis_crs": ANALYSIS_CRS,
        "resampling_performed": False,
        "items": items,
        "pairwise_overlap": pairwise_overlap(items),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"-> {args.out}")
    for item in items:
        print(
            f"{Path(item['path']).name}: {item['crs']} {item['width']}x{item['height']} "
            f"pixel_m={item['ground_pixel_meters_at_center']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
