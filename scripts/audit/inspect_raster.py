"""Read-only forensic inspection of GeoTIFF/rasters.

Extracts metadata and, for single-band integer rasters, windowed class
statistics (unique values, positive pixel count, nodata count). Large
rasters are scanned in fixed 1024 px windows; the full raster is never
loaded into memory.

Area rule (binding):
* projected CRS -> area = positive_pixels * |pixel_width * pixel_height|
* geographic CRS -> degree^2 is NEVER reported as m^2; only the geodetic
  area of the full rectangular footprint is reported (clearly labelled),
  and per-class area is null with a guard flag.

Writes <slug>.json plus <slug>.md per raster into --outdir.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

WINDOW = 1024
MAX_UNIQUE = 10_000  # bail out of unique tracking if data is not thematic


def _epsg(ds_crs: Any) -> str:
    try:
        code = ds_crs.to_epsg()
    except Exception:  # noqa: BLE001
        code = None
    if code:
        return f"EPSG:{code}"
    return "CRS_WKT_PRESENT_EPSG_UNKNOWN" if ds_crs else "NONE"


def _window_iter(width: int, height: int) -> Any:
    from rasterio.windows import Window

    for row in range(0, height, WINDOW):
        for col in range(0, width, WINDOW):
            yield Window(
                col_off=col,
                row_off=row,
                width=min(WINDOW, width - col),
                height=min(WINDOW, height - row),
            )


def windowed_class_stats(ds: Any, band: int = 1) -> dict[str, Any]:
    import numpy as np

    nodata = ds.nodata
    counts: Counter[int] = Counter()
    nodata_count = 0
    total_valid = 0
    overflow = False
    for win in _window_iter(ds.width, ds.height):
        raw = ds.read(band, window=win, masked=False)
        if nodata is not None:
            nodata_count += int((raw == nodata).sum())
            mask = raw == nodata
            valid = raw[~mask]
        else:
            valid = raw.reshape(-1)
        total_valid += int(valid.size)
        if not overflow:
            uniq, cnt = np.unique(valid, return_counts=True)
            for value, n in zip(uniq.tolist(), cnt.tolist(), strict=True):
                counts[int(value)] += int(n)
            if len(counts) > MAX_UNIQUE:
                overflow = True
    positive = sum(n for value, n in counts.items() if value > 0)
    return {
        "unique_values": sorted(counts) if not overflow else None,
        "value_counts": {str(k): v for k, v in sorted(counts.items())} if not overflow else None,
        "unique_tracking_abandoned_above_MAX_UNIQUE": overflow,
        "positive_pixel_count": positive if not overflow else None,
        "nodata_pixel_count": int(nodata_count),
        "valid_pixel_count": int(total_valid),
    }


def footprint_geodetic_area_km2(bounds: tuple[float, float, float, float]) -> float | None:
    try:
        from pyproj import Geod
    except ImportError:
        return None
    west, south, east, north = bounds
    geod = Geod(ellps="WGS84")
    lon = [west, east, east, west, west]
    lat = [north, north, south, south, north]
    area, _ = geod.polygon_area_perimeter(lon, lat)
    return abs(area) / 1e6


def inspect(path: Path, classify_mode: str) -> dict[str, Any]:
    import rasterio
    from rasterio.crs import CRS

    with rasterio.open(path) as ds:
        is_projected = bool(ds.crs and ds.crs.is_projected)
        is_geographic = bool(ds.crs and ds.crs.is_geographic)
        bands = []
        for idx in range(1, ds.count + 1):
            bands.append(
                {
                    "index": idx,
                    "dtype": ds.dtypes[idx - 1],
                    "description": ds.descriptions[idx - 1] or None,
                    "block_shape": list(ds.block_shapes[idx - 1]),
                    "overviews": list(ds.overviews(idx)),
                    "nodata": ds.nodata,
                }
            )
        profile = ds.profile
        report: dict[str, Any] = {
            "path": str(path),
            "driver": ds.driver,
            "width": ds.width,
            "height": ds.height,
            "band_count": ds.count,
            "dtypes": sorted(set(ds.dtypes)),
            "crs": _epsg(ds.crs),
            "crs_is_projected": is_projected,
            "crs_is_geographic": is_geographic,
            "transform": [float(v) for v in list(ds.transform)[:6]],
            "bounds": [float(v) for v in ds.bounds],
            "resolution_x": float(ds.transform.a),
            "resolution_y": float(abs(ds.transform.e)),
            "nodata": ds.nodata,
            "compression": profile.get("compress", None),
            "tiled": bool(profile.get("tiled", False)),
            "block_shapes": [list(b) for b in ds.block_shapes],
            "bands": bands,
            "dataset_tags": {k: v for k, v in ds.tags().items()},
        }
        auto_classify = (
            classify_mode == "always"
            or (classify_mode == "auto" and ds.count == 1 and ds.dtypes[0].startswith(("u", "i")))
        )
        area: dict[str, Any] = {
            "method": None,
            "positive_area_km2": None,
            "guards": [],
        }
        if auto_classify:
            stats = windowed_class_stats(ds, band=1)
            report["class_statistics_band_1"] = stats
            pos = stats["positive_pixel_count"]
            if pos is not None and is_projected:
                pixel_area = abs(float(ds.transform.a) * float(ds.transform.e))
                area = {
                    "method": "pixel_count_x_transform_pixel_area(projected CRS)",
                    "pixel_area_m2": pixel_area,
                    "positive_area_m2": pos * pixel_area,
                    "positive_area_km2": pos * pixel_area / 1e6,
                    "positive_pixel_count": pos,
                    "guards": [],
                }
            elif pos is not None and is_geographic:
                area = {
                    "method": None,
                    "positive_area_m2": None,
                    "positive_area_km2": None,
                    "positive_pixel_count": pos,
                    "footprint_geodetic_area_km2": footprint_geodetic_area_km2(
                        tuple(ds.bounds)
                    ),
                    "guards": [
                        "GEOGRAPHIC_CRS: per-pixel degree^2 is NOT an area; "
                        "positive-class m^2 area not computed from degree grid"
                    ],
                }
        report["area"] = area
        _ = CRS  # imported for type familiarity; no reproject performed
    return report


def render_md(report: dict[str, Any]) -> str:
    lines = [
        f"# Raster report: {Path(report['path']).name}",
        "",
        f"- Driver: `{report['driver']}`; size **{report['width']} x {report['height']}**; "
        f"bands: {report['band_count']} ({', '.join(report['dtypes'])})",
        f"- CRS: **{report['crs']}** (projected={report['crs_is_projected']}, "
        f"geographic={report['crs_is_geographic']})",
        f"- Pixel size: {report['resolution_x']} x {report['resolution_y']} "
        "(CRS units; not metres when geographic)",
        f"- Bounds: {[round(v, 6) for v in report['bounds']]}",
        f"- Compression: {report['compression']}; tiled: {report['tiled']}; "
        f"nodata: {report['nodata']}",
        "",
    ]
    stats = report.get("class_statistics_band_1")
    if stats:
        lines += [
            "## Band-1 class statistics (windowed full scan)",
            "",
            f"- unique values: `{stats['unique_values']}`",
            f"- positive pixel count: **{stats['positive_pixel_count']}**",
            f"- nodata pixels: {stats['nodata_pixel_count']}; "
            f"valid pixels: {stats['valid_pixel_count']}",
            "",
        ]
    area = report.get("area", {})
    lines += [
        "## Area",
        "",
        f"- method: `{area.get('method')}`",
        f"- positive area km^2: **{area.get('positive_area_km2')}**",
    ]
    for guard in area.get("guards", []):
        lines.append(f"- GUARD: {guard}")
    if area.get("footprint_geodetic_area_km2") is not None:
        lines.append(
            f"- footprint geodetic area km^2 (whole rectangle, not class area): "
            f"{area['footprint_geodetic_area_km2']:.4f}"
        )
    lines.append("")
    return "\n".join(lines)


def slugify(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            rel = path.resolve().relative_to(root.resolve())
            stem = "__".join(rel.with_suffix("").parts)
        except ValueError:
            stem = path.stem
    else:
        stem = path.stem
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)[:120]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument(
        "--classify",
        choices=["auto", "always", "never"],
        default="auto",
        help="auto = single-band integer rasters only",
    )
    args = parser.parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=True)
    for path in args.input:
        report = inspect(path, args.classify)
        slug = slugify(path, args.root)
        json_path = args.outdir / f"{slug}.json"
        md_path = args.outdir / f"{slug}.md"
        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        md_path.write_text(render_md(report), encoding="utf-8")
        print(f"{path} -> {json_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
