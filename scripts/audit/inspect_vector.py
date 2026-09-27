"""Read-only forensic inspection of vector datasets (shp/gpkg/geojson).

Reports: driver, CRS, schema, feature count, geometry types, bounds,
invalid / empty / duplicate / sliver geometry diagnostics, and a forensic
test of any numeric area-like field (unit never asserted without evidence).

Originals are NEVER opened for writing; no repair is ever written back.
Writes <slug>.json + <slug>.md per vector into --outdir.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SLIVER_M2 = 100.0  # diagnostic thresholds, not a deletion rule


def _crs_label(crs: Any) -> str:
    try:
        code = crs.to_epsg()
    except Exception:  # noqa: BLE001
        code = None
    if code:
        return f"EPSG:{code}"
    return "CRS_WKT_PRESENT_EPSG_UNKNOWN" if crs else "NONE"


def area_square_meters(gdf: Any) -> Any:
    """Planar area for projected CRS; geodetic per-feature area for geographic.

    Geographic branch deliberately avoids treating degree^2 as m^2.
    """
    import pyproj
    from shapely.geometry.base import BaseGeometry

    crs = gdf.crs
    if crs is None:
        return None
    if crs.is_projected:
        return gdf.geometry.area
    if not crs.is_geographic:
        return None
    geod = pyproj.Geod(ellps="WGS84")

    def geod_area(geom: BaseGeometry) -> float:
        if geom is None or geom.is_empty:
            return 0.0
        area, _ = geod.geometry_area_perimeter(geom)
        return abs(float(area))

    return gdf.geometry.map(geod_area)


def area_field_forensics(gdf: Any, areas_m2: Any) -> dict[str, Any]:
    """Compare numeric fields with computed m^2 areas to resolve their unit."""
    import pandas as pd

    results: dict[str, Any] = {}
    if areas_m2 is None:
        return {"note": "no area comparison: CRS missing"}
    numeric = gdf.select_dtypes(include="number")
    for field in numeric.columns:
        name = field.lower()
        if not any(token in name for token in ("area", "area_ha", "_ha", "km2")):
            continue
        field_vals = pd.to_numeric(gdf[field], errors="coerce")
        ratio = areas_m2 / field_vals.replace(0, pd.NA)
        ratio = ratio.dropna()
        if ratio.empty:
            results[field] = {"note": "all zero/non-comparable"}
            continue
        median_ratio = float(statistics.median(ratio.tolist()))
        unit = "AMBIGUOUS"
        if 0.5 <= median_ratio <= 2.0:
            unit = "m^2 if ratio~1"
        elif 5_000 <= median_ratio <= 20_000:
            unit = "hectare if ratio~10000"
        elif 500_000 <= median_ratio <= 2_000_000:
            unit = "km^2 if ratio~1e6"
        results[field] = {
            "field_sum": float(field_vals.sum()),
            "field_min": float(field_vals.min()),
            "field_max": float(field_vals.max()),
            "computed_area_m2_sum": float(areas_m2.sum()),
            "median_ratio_computed_m2_over_field": median_ratio,
            "unit_hypothesis": unit,
            "warning": (
                "hypothesis only; confirm against official field definition / "
                "metadata before quoting hectares"
            ),
        }
    return results


def inspect(path: Path) -> dict[str, Any]:
    import fiona
    import geopandas as gpd

    with fiona.open(path) as collection:
        crs = collection.crs
        schema = dict(collection.schema)
        driver = collection.driver
        bounds = list(collection.bounds)
        crs_label = _crs_label(crs)
        geom_types_header = schema.get("geometry")

    frame = gpd.read_file(path)
    n = len(frame)
    geom_types = Counter(
        g.geom_type for g in frame.geometry if g is not None and not g.is_empty
    )
    empty = int(sum(g is None or g.is_empty for g in frame.geometry))
    is_valid = frame.geometry.is_valid
    invalid = int((~is_valid).sum())
    from shapely import is_valid_reason

    # Collapse coordinate-bearing reasons to their type label, e.g.
    # "Ring Self-intersection[524573..., ...]" -> "Ring Self-intersection".
    invalid_reasons: dict[str, int] = Counter(
        str(reason).split("[", 1)[0].strip()
        for reason in is_valid_reason(list(frame.geometry[~is_valid]))
    )
    wkb_hashes = [
        hashlib.sha256(g.wkb).hexdigest()
        for g in frame.geometry
        if g is not None and not g.is_empty
    ]
    dup_counter = Counter(wkb_hashes)
    duplicate_geometries = int(sum(c for c in dup_counter.values() if c > 1))

    areas_m2 = area_square_meters(frame)
    sliver_count: int | None = None
    area_summary: dict[str, Any] | None = None
    if areas_m2 is not None:
        sliver_count = int((areas_m2 < SLIVER_M2).sum())
        area_summary = {
            "crs_used_for_area": crs_label,
            "computed_total_area_m2": float(areas_m2.sum()),
            "computed_total_area_km2": float(areas_m2.sum()) / 1e6,
            "computed_min_area_m2": float(areas_m2.min()),
            "computed_max_area_m2": float(areas_m2.max()),
            "geometries_smaller_than_100m2": sliver_count,
        }
    field_forensics = area_field_forensics(frame, areas_m2)

    province_breakdown = None
    for col in frame.columns:
        if col.lower() in {"name", "province", "prov", "省"}:
            province_breakdown = {
                "field": col,
                "counts": {
                    str(k): int(v)
                    for k, v in frame[col].value_counts(dropna=False).items()
                },
            }
            break

    return {
        "path": str(path),
        "driver": driver,
        "crs": crs_label,
        "schema": schema,
        "geometry_types_header": geom_types_header,
        "geometry_types_observed": dict(geom_types),
        "feature_count": n,
        "bounds": bounds,
        "empty_geometries": empty,
        "invalid_geometries": invalid,
        "invalid_reasons": dict(invalid_reasons),
        "duplicate_geometry_features": duplicate_geometries,
        "area_summary": area_summary,
        "area_field_forensics": field_forensics,
        "categorical_breakdown": province_breakdown,
        "repair_policy": "originals untouched; any repair copy lives only under work/",
    }


def render_md(report: dict[str, Any]) -> str:
    lines = [
        f"# Vector report: {Path(report['path']).name}",
        "",
        f"- Driver `{report['driver']}`; CRS **{report['crs']}**; "
        f"features **{report['feature_count']}**",
        f"- Geometry: header `{report['geometry_types_header']}`, "
        f"observed `{report['geometry_types_observed']}`",
        f"- Bounds: {[round(v, 6) for v in report['bounds']]}",
        f"- Invalid: **{report['invalid_geometries']}** "
        f"({report['invalid_reasons']}); empty: {report['empty_geometries']}; "
        f"duplicate-geometry feature rows: {report['duplicate_geometry_features']}",
        "",
        "## Schema",
        "",
        "```json",
        json.dumps(report["schema"], indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    if report["area_summary"]:
        a = report["area_summary"]
        lines += [
            "## Area (computed, not from the attribute field)",
            "",
            f"- total **{a['computed_total_area_km2']:.4f} km^2** "
            f"(CRS {a['crs_used_for_area']})",
            f"- min {a['computed_min_area_m2']:.4f} m^2, "
            f"max {a['computed_max_area_m2']:.1f} m^2",
            f"- geometries < {SLIVER_M2} m^2 (sliver diagnostics): "
            f"**{a['geometries_smaller_than_100m2']}**",
            "",
        ]
    if report["area_field_forensics"]:
        lines += ["## Area-like attribute fields", ""]
        for field, info in report["area_field_forensics"].items():
            lines.append(f"- `{field}`: {json.dumps(info, ensure_ascii=False)}")
        lines.append("")
    if report["categorical_breakdown"]:
        lines += [
            f"## Breakdown by `{report['categorical_breakdown']['field']}`",
            "",
            json.dumps(report["categorical_breakdown"]["counts"], indent=2, ensure_ascii=False),
            "",
        ]
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
    args = parser.parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=True)
    for path in args.input:
        report = inspect(path)
        slug = slugify(path, args.root)
        (args.outdir / f"{slug}.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (args.outdir / f"{slug}.md").write_text(render_md(report), encoding="utf-8")
        print(f"{path} -> {slug}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
