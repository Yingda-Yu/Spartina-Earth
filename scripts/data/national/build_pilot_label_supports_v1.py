#!/usr/bin/env python3
"""Issue #19 Phase F/G -- derived pilot label supports (offline).

For each of the 20 frozen panel cells, builds fractional-occupancy label
supports on the SAME grids the Phase D exporter will land EO pixels on
(``spartina.data.gee.grid.covering_grid``; per-cell native UTM zone from
the cell centroid; 30 m for Landsat-era sources, 10 m for CM-SSM):

* GEODATA 1990/2000/2015/2020 -- binary 30 m rasters, nearest-neighbour
  warp, in-window background is a WEAK negative only;
* CMSA 2017-2021 -- gridcode 2 polygon union fractions at 30 m;
  gridcode 0 stays UNKNOWN/TODO_VERIFY (never negative);
* CM-SSM 2020 -- polygon union fractions at 10 m and 30 m.

Source archives are opened read-only and never modified; vector repair
runs on derived copies with a |area change| < 1% STOP guard. GeoTIFF
bytes land under work/ (out of Git); a checksummed CSV/JSON manifest is
written under datasets/manifests/.

Fractions are SILVER occupancy summaries, never ground truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402
from affine import Affine  # noqa: E402
from pyproj import CRS, Transformer  # noqa: E402
from rasterio.errors import WindowError  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.warp import Resampling, reproject, transform_bounds  # noqa: E402
from rasterio.windows import Window, from_bounds  # noqa: E402
from shapely import box  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402

from spartina.data.gee.grid import covering_grid  # noqa: E402
from spartina.data.national.grid import (  # noqa: E402
    CHINA_ALBERS_PROJ4,
    GridKind,
    parse_cell_id,
    utm_epsg,
)
from spartina.data.national.grid import (  # noqa: E402
    GridSpec as LatticeSpec,
)
from spartina.data.national.pilot_labels import (  # noqa: E402
    ADAPTER_VERSION,
    LABEL_SOURCES,
    POLICY_DOC,
    UNKNOWN_GRIDCODE_ZERO,
    LabelKind,
    OccupancyClass,
    assert_repair_area_change,
    class_counts,
    classify_fractions,
    classify_positive_only_fractions,
    positive_area_km2,
)

PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
PLAN_JSON = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.json"
WORK_DIR = REPO_ROOT / "work/national/pilot19/labels"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_label_supports_v1.csv"
OUT_JSON = (
    REPO_ROOT
    / "datasets/manifests/national_pilot19_label_supports_v1.json")
STAGING = REPO_ROOT / "work/intake/staging"
OLD = REPO_ROOT / "old datasets"

SOURCE_FILES: dict[str, Path] = {
    "GEODATA_1990": STAGING / (
        "1990年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体/"
        "1990年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif"),
    "GEODATA_2000": STAGING / (
        "2000年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体/"
        "2000年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif"),
    "GEODATA_2015": STAGING / (
        "30m分辨率中国互花米草空间分布数据集(2015年)-数据实体/"
        "30m中国互花米草空间分布数据集(2015年)-数据实体.tif"),
    "GEODATA_2020": STAGING / (
        "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体/"
        "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif"),
    "CMSA_2017": STAGING / "中国大陆2017-2021互花米草CMSA/CMSA_2017.shp",
    "CMSA_2018": STAGING / "中国大陆2017-2021互花米草CMSA/CMSA_2018.shp",
    "CMSA_2019": STAGING / "中国大陆2017-2021互花米草CMSA/CMSA_2019.shp",
    "CMSA_2020": STAGING / "中国大陆2017-2021互花米草CMSA/CMSA_2020.shp",
    "CMSA_2021": STAGING / "中国大陆2017-2021互花米草CMSA/CMSA_2021.shp",
    "CM-SSM_2020": OLD / "30mSpartinaChina/2020/CM-SSM/CM-SSM.shp",
}

ALBERS = CRS.from_proj4(CHINA_ALBERS_PROJ4)
SOURCE_BY_KEY_POLICIES = {s.key: s for s in LABEL_SOURCES}
GRID_VALUE_POSITIVE = 1
GRID_NODATA = 255
REPAIR_TOLERANCE = 0.01
#: Fraction values above this indicate a geometry/grid error, not coverage.
FRACTION_SANITY_MAX = 1.01
#: Points sampled per cell edge when projecting Albers corners into UTM
#: (projected edges can bow beyond the four-corner bounding box).
BOUNDS_DENSIFY_PER_EDGE = 21


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def shapefile_component_hashes(shp: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        side = shp.with_suffix(ext)
        if side.exists():
            out[ext] = _sha256(side)
    return out


def cell_utm_bounds(
    cell_id: str, zone: int,
) -> tuple[int, tuple[float, float, float, float]]:
    """Projected UTM bounding box of one Albers cell.

    Cell edges are densified before projection: the reprojected square is
    not axis-aligned in UTM, so a four-corner bbox could clip the edges.
    This is the single shared bounds rule the Phase D EO exporter must use
    so label supports and EO pixels share one grid.
    """
    ref = parse_cell_id(cell_id)
    lattice = LatticeSpec(GridKind.CHINA_ALBERS)
    xmin, ymin, xmax, ymax = lattice.cell_bounds_projected(ref.row, ref.col)
    transformer = Transformer.from_crs(
        ALBERS, CRS.from_epsg(utm_epsg(zone)), always_xy=True)
    edge = np.linspace(0.0, 1.0, BOUNDS_DENSIFY_PER_EDGE)
    pts: list[tuple[float, float]] = []
    for t in edge:
        pts.extend([
            (xmin + t * (xmax - xmin), ymin),
            (xmin + t * (xmax - xmin), ymax),
            (xmin, ymin + t * (ymax - ymin)),
            (xmax, ymin + t * (ymax - ymin)),
        ])
    px, py = transformer.transform([p[0] for p in pts], [p[1] for p in pts])
    return utm_epsg(zone), (float(min(px)), float(min(py)),
                           float(max(px)), float(max(py)))


def cell_polygon_utm(cell_id: str, zone: int) -> Polygon:
    """Exact Albers 10 km cell square projected into the cell UTM zone
    (edges densified, matching :func:`cell_utm_bounds`)."""
    ref = parse_cell_id(cell_id)
    lattice = LatticeSpec(GridKind.CHINA_ALBERS)
    xmin, ymin, xmax, ymax = lattice.cell_bounds_projected(ref.row, ref.col)
    edge = np.linspace(0.0, 1.0, BOUNDS_DENSIFY_PER_EDGE)
    pts: list[tuple[float, float]] = []
    # Ordered ring: bottom edge -> right edge -> top edge -> left edge.
    pts.extend((xmin + t * (xmax - xmin), ymin) for t in edge)
    pts.extend((xmax, ymin + t * (ymax - ymin)) for t in edge[1:])
    pts.extend((xmin + t * (xmax - xmin), ymax)
               for t in edge[-2::-1])
    pts.extend((xmin, ymin + t * (ymax - ymin))
               for t in edge[-2:0:-1])
    transformer = Transformer.from_crs(
        ALBERS, CRS.from_epsg(utm_epsg(zone)), always_xy=True)
    px, py = transformer.transform([p[0] for p in pts], [p[1] for p in pts])
    return Polygon(list(zip(px, py, strict=True)))


def pixel_centres_in_cell(
    cell_poly: BaseGeometry, transform: Affine,
    height: int, width: int, pixel_m: int,
) -> np.ndarray[Any, Any]:
    """Boolean mask: pixel CENTRE inside the exact Albers cell.

    Same centre-in-cell assignment rule Issue #18 used (selected_rasterize
    GDAL centre rule). The export grid covers the larger UTM bbox; only
    these pixels belong to the cell for cell-level statistics.
    """
    cols, rows = np.meshgrid(np.arange(width), np.arange(height))
    xs = transform.c + (cols.ravel() + 0.5) * pixel_m
    ys = transform.f - (rows.ravel() + 0.5) * pixel_m
    inside = shapely.contains(cell_poly, shapely.points(xs, ys))
    return np.asarray(inside, dtype=bool).reshape(height, width)


def raster_support(
    tif_path: Path,
    bounds_utm: tuple[float, float, float, float],
    epsg: int, pixel_m: int,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], dict[str, Any]]:
    """Warp a binary GEODATA raster onto one cell UTM grid.

    Returns (fraction float32 [NaN outside source window], class uint8,
    provenance).
    """
    grid = covering_grid(bounds_utm, epsg, float(pixel_m))
    dst_transform = Affine(*grid.transform)
    destination = np.full((grid.height, grid.width), GRID_NODATA,
                          dtype=np.float32)
    coverage = np.zeros((grid.height, grid.width), dtype=np.uint8)
    meta: dict[str, Any] = {"grid": grid, "overlaps_source_window": False,
                           "src_window_px": [0, 0], "src_crs": ""}
    with rasterio.open(tif_path) as src:
        src_bounds = transform_bounds(
            f"EPSG:{epsg}", src.crs, *bounds_utm, densify_pts=21)
        window = from_bounds(*src_bounds, src.transform)
        window = window.round_offsets().round_lengths()
        try:
            window = window.intersection(
                Window(0, 0, src.width, src.height))
        except WindowError:
            # Projected cell falls wholly outside the source data window
            # (e.g. northern cells beyond the 1990 product extent).
            window = Window(0, 0, 0, 0)
        meta["src_crs"] = str(src.crs)
        meta["src_window_px"] = [int(window.width), int(window.height)]
        if window.width > 0 and window.height > 0:
            meta["overlaps_source_window"] = True
            labels = src.read(1, window=window)
            win_transform = src.window_transform(window)
            reproject(
                source=labels.astype(np.float32),
                destination=destination,
                src_transform=win_transform, src_crs=src.crs,
                dst_transform=dst_transform, dst_crs=f"EPSG:{epsg}",
                src_nodata=GRID_NODATA, dst_nodata=GRID_NODATA,
                resampling=Resampling.nearest)
            # Coverage band: which destination pixels fall inside the
            # source data window (every source sample equals 1 here; the
            # window itself is the mapped extent).
            ones = np.ones(labels.shape, dtype=np.uint8)
            reproject(
                source=ones, destination=coverage,
                src_transform=win_transform, src_crs=src.crs,
                dst_transform=dst_transform, dst_crs=f"EPSG:{epsg}",
                src_nodata=0, dst_nodata=0,
                resampling=Resampling.nearest)
    inside = coverage > 0
    fraction = np.full(destination.shape, np.nan, dtype=np.float32)
    fraction[inside] = (
        destination[inside] == GRID_VALUE_POSITIVE).astype(np.float32)
    # In-window background pixels are weak negatives, not UNKNOWN: the
    # unknown mask is reserved for out-of-window coverage.
    classes = classify_fractions(fraction)
    return fraction, classes, meta


def repaired(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """make_valid on a derived copy with the <1% area STOP guard."""
    gdf = gdf[gdf.geometry.notna()].copy()
    before_km2 = float(gdf.geometry.area.sum()) / 1e6
    n_before = len(gdf)
    repaired_geom = gdf.geometry.make_valid()
    gdf = gpd.GeoDataFrame(gdf, geometry=repaired_geom, crs=gdf.crs)
    gdf = gdf.explode(ignore_index=True, index_parts=False)
    gdf = gdf[gdf.geometry.geom_type.isin({"Polygon", "MultiPolygon"})]
    after_km2 = float(gdf.geometry.area.sum()) / 1e6
    if before_km2 > 0:
        assert_repair_area_change(before_km2, after_km2, REPAIR_TOLERANCE)
    info = {
        "area_km2_before": round(before_km2, 6),
        "area_km2_after": round(after_km2, 6),
        "features_before": int(n_before),
        "parts_after": int(len(gdf)),
        "area_change_fraction": (
            round(abs(after_km2 - before_km2) / before_km2, 8)
            if before_km2 > 0 else 0.0),
    }
    return gdf, info


@dataclass
class VectorEntry:
    """Repaired positive/unknown frames held in the vector NATIVE CRS."""

    pos: gpd.GeoDataFrame
    gridcode_zero: gpd.GeoDataFrame | None
    native_epsg: int
    repair: dict[str, Any]


def load_vector_entry(key: str, shp: Path) -> VectorEntry:
    """Load + split + repair one vector source in its native CRS."""
    policy = SOURCE_BY_KEY_POLICIES[key]
    loaded = gpd.read_file(shp)
    native_epsg = loaded.crs.to_epsg()
    if native_epsg is None:
        raise ValueError(f"{key}: source CRS has no EPSG code; STOP")
    repair: dict[str, Any] = {
        "native_crs_epsg": int(native_epsg),
        "n_features": int(len(loaded)),
    }
    gz: gpd.GeoDataFrame | None = None
    if policy.family == "CMSA":
        codes = {int(v) for v in pd.unique(loaded["gridcode"]).tolist()}
        repair["gridcodes_present"] = sorted(codes)
        unexpected = codes - {0, 2}
        if unexpected:
            raise ValueError(
                f"{key}: unexpected gridcode values {sorted(unexpected)}; "
                "STOP (semantics not predeclared)")
        pos_frame = loaded[loaded["gridcode"] == 2].copy()
        gz_frame = loaded[loaded["gridcode"] == 0].copy()
        gz, gz_info = repaired(gz_frame)
        repair["gridcode0"] = gz_info
    else:
        pos_frame = loaded
    pos, pos_info = repaired(pos_frame)
    repair["positive"] = pos_info
    return VectorEntry(pos, gz, int(native_epsg), repair)


def _polygon_parts(geoms: gpd.GeoSeries) -> list[BaseGeometry]:
    """Atomic polygon parts of the union (parts are mutually disjoint)."""
    if geoms.empty:
        return []
    union = geoms.union_all()
    if union.is_empty:
        return []
    return [
        g for g in shapely.get_parts(union)
        if not g.is_empty and g.geom_type in ("Polygon", "MultiPolygon")]


def _cell_subset(
    frame: gpd.GeoDataFrame, native_epsg: int,
    cell_box_utm: BaseGeometry, cell_epsg: int, buffer_m: float,
) -> gpd.GeoDataFrame:
    """Repair-frame features intersecting one cell (prefilter native CRS,
    then reproject to the cell UTM zone)."""
    cell_native = gpd.GeoSeries(
        [cell_box_utm], crs=cell_epsg).to_crs(native_epsg).iloc[0]
    region = gpd.GeoDataFrame(
        geometry=[cell_native.buffer(buffer_m)], crs=native_epsg)
    hit = gpd.sjoin(
        frame, region, how="inner", predicate="intersects")
    subset = frame.loc[hit.index.drop_duplicates()]
    return subset.to_crs(cell_epsg)


def exact_pixel_fractions(
    geometries: list[BaseGeometry], dst_transform: Affine,
    height: int, width: int, pixel_m: int,
) -> tuple[np.ndarray[Any, Any], int]:
    """Exact union polygon area / pixel area per touched pixel.

    ``geometries`` must be mutually disjoint (union parts), so per-part
    intersection areas sum to the exact covered fraction. Returns
    (fractions float64, n_touched_pixels).
    """
    cover = np.zeros((height, width), dtype=np.float64)
    if not geometries:
        return cover, 0
    burned = rasterize(
        [(g, 1) for g in geometries],
        out_shape=(height, width), transform=dst_transform,
        fill=0, dtype="uint8", all_touched=True)
    rows, cols = np.nonzero(burned)
    if rows.size == 0:
        return cover, 0
    minx = dst_transform.c + cols * pixel_m
    maxy = dst_transform.f - rows * pixel_m
    pixel_boxes = box(minx, maxy - pixel_m, minx + pixel_m, maxy)
    tree = gpd.GeoSeries(geometries).sindex
    qb, qg = tree.query(pixel_boxes, predicate="intersects")
    if qb.size:
        areas = shapely.area(
            shapely.intersection(pixel_boxes[qb], np.asarray(geometries)[qg]))
        np.add.at(cover, (rows[qb], cols[qb]), areas)
    fractions = cover / float(pixel_m) ** 2
    return fractions, int(rows.size)


def parts_support(
    pos_parts: list[BaseGeometry], gz_parts: list[BaseGeometry],
    dst_transform: Affine, height: int, width: int, pixel_m: int,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], dict[str, Any]]:
    """Fraction/classes from disjoint union parts on one cell grid."""
    pos_frac, n_touched = exact_pixel_fractions(
        pos_parts, dst_transform, height, width, pixel_m)
    gz_frac, _ = exact_pixel_fractions(
        gz_parts, dst_transform, height, width, pixel_m)
    if float(pos_frac.max(initial=0.0)) > FRACTION_SANITY_MAX:
        raise ValueError(
            f"positive fraction {pos_frac.max():.4f} > sanity bound; "
            "STOP (geometry/grid error)")
    unknown_gc0 = gz_frac > 0
    fraction = pos_frac.astype(np.float32)
    # Positive-only products never carry PURE_NEGATIVE: partial cover is
    # MIXED, uncovered pixels stay UNKNOWN (no verified negative envelope).
    classes = classify_positive_only_fractions(fraction, unknown=unknown_gc0)
    meta = {
        "positive_parts": len(pos_parts),
        "gridcode0_parts": len(gz_parts),
        "positive_touched_pixels": n_touched,
        "gridcode0_pixels": int(unknown_gc0.sum()),
        "gridcode0_token": UNKNOWN_GRIDCODE_ZERO,
        "max_fraction": round(float(pos_frac.max(initial=0.0)), 6),
    }
    return fraction, classes, meta


def write_support_tif(
    path: Path, fraction: np.ndarray[Any, Any],
    classes: np.ndarray[Any, Any],
    epsg: int, transform: Affine, source_id: str, support_m: int,
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff", "dtype": "float32", "count": 2,
        "width": fraction.shape[1], "height": fraction.shape[0],
        "crs": f"EPSG:{epsg}", "transform": transform,
        "compress": "lzw", "tiled": True}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(fraction.astype(np.float32), 1)
        dst.write(classes.astype(np.uint8), 2)
        dst.set_band_description(
            1, f"fractional_occupancy_{support_m}m (NaN=unknown)")
        dst.set_band_description(2, "occupancy_class_uint8")
        dst.update_tags(
            adapter=ADAPTER_VERSION, source=source_id,
            support_m=str(support_m),
            fractions_are="SILVER occupancy summary, not ground truth")
    return _sha256(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", default="",
                        help="comma-separated cell ids (default: all 20)")
    parser.add_argument("--out-csv", default=str(OUT_CSV))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    args = parser.parse_args()

    panel = pd.read_csv(PANEL_CSV)
    if args.cells:
        wanted = {c.strip() for c in args.cells.split(",") if c.strip()}
        panel = panel[panel.cell_id.isin(wanted)]
        missing = wanted - set(panel.cell_id)
        if missing:
            raise SystemExit(f"requested cells not in frozen panel: {missing}")
    panel = panel.copy()
    panel["utm_zone"] = ((panel.center_lon + 180) // 6 + 1).astype(int)

    for policy in LABEL_SOURCES:
        if not SOURCE_FILES[policy.key].exists():
            raise FileNotFoundError(
                f"missing label source {SOURCE_FILES[policy.key]}")

    vector_cache: dict[str, VectorEntry] = {}
    vector_repair: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []

    for cell in panel.itertuples(index=False):
        cell_id = str(cell.cell_id)
        zone = int(cell.utm_zone)
        epsg, bounds = cell_utm_bounds(cell_id, zone)
        short = cell_id.removeprefix("CNA10K-")
        cell_dir = WORK_DIR / short
        cell_box_utm = box(*bounds)
        cell_poly = cell_polygon_utm(cell_id, zone)

        for policy in LABEL_SOURCES:
            src_path = SOURCE_FILES[policy.key]
            for support_m in policy.supports_m:
                grid = covering_grid(bounds, epsg, float(support_m))
                transform = Affine(*grid.transform)
                repair_record: dict[str, Any] = {}
                if policy.kind is LabelKind.BINARY_RASTER:
                    fraction, classes, meta = raster_support(
                        src_path, bounds, epsg, support_m)
                    components = {".tif": _sha256(src_path)}
                    cell_meta = {
                        "source_window_overlap":
                            meta["overlaps_source_window"],
                        "src_window_px": meta["src_window_px"],
                        "positive_parts": "",
                        "gridcode0_parts": "",
                        "positive_touched_pixels": "",
                        "gridcode0_pixels": "",
                        "max_fraction": "",
                    }
                else:
                    components = shapefile_component_hashes(src_path)
                    if policy.key not in vector_cache:
                        entry = load_vector_entry(policy.key, src_path)
                        vector_cache[policy.key] = entry
                        vector_repair[policy.key] = entry.repair
                    entry = vector_cache[policy.key]
                    pos_subset = _cell_subset(
                        entry.pos, entry.native_epsg, cell_box_utm, epsg,
                        float(support_m))
                    gz_subset = (
                        _cell_subset(
                            entry.gridcode_zero, entry.native_epsg,
                            cell_box_utm, epsg, float(support_m))
                        if entry.gridcode_zero is not None else None)
                    pos_parts = _polygon_parts(pos_subset.geometry)
                    gz_parts = (
                        _polygon_parts(gz_subset.geometry)
                        if gz_subset is not None else [])
                    fraction, classes, vmeta = parts_support(
                        pos_parts, gz_parts, transform,
                        grid.height, grid.width, support_m)
                    repair_record = entry.repair
                    cell_meta = {
                        "source_window_overlap": "",
                        "src_window_px": "",
                        **vmeta,
                    }

                out_tif = cell_dir / f"{policy.key}_{support_m}m.tif"
                tif_sha = write_support_tif(
                    out_tif, fraction, classes, epsg, transform,
                    policy.source_id, support_m)
                counts = class_counts(classes)
                unknown_mask = classes == OccupancyClass.UNKNOWN
                in_cell = pixel_centres_in_cell(
                    cell_poly, transform, grid.height, grid.width,
                    support_m)
                area_in_cell = positive_area_km2(
                    fraction[in_cell], float(support_m) ** 2,
                    unknown_mask[in_cell])
                rows.append({
                    "cell_id": cell_id,
                    "source": policy.source_id,
                    "family": policy.family,
                    "year": policy.year,
                    "support_m": support_m,
                    "crs_epsg": epsg,
                    "utm_zone": zone,
                    "width": grid.width,
                    "height": grid.height,
                    "n_pixels_in_cell": int(in_cell.sum()),
                    "positive_area_km2": positive_area_km2(
                        fraction, float(support_m) ** 2, unknown_mask),
                    "positive_area_km2_in_cell": area_in_cell,
                    **counts,
                    **cell_meta,
                    "fraction_tif":
                        str(out_tif.relative_to(REPO_ROOT)),
                    "tif_sha256": tif_sha,
                    "source_components_sha256":
                        json.dumps(components, sort_keys=True),
                    "repair_record":
                        json.dumps(repair_record, sort_keys=True,
                                   ensure_ascii=False)
                        if repair_record else "",
                    "adapter_version": ADAPTER_VERSION,
                    "grid_alignment": (
                        "spartina.data.gee.grid.covering_grid on densified "
                        "cell UTM bounds (identical to the Phase D EO export "
                        "grid)"),
                })

    summary = pd.DataFrame(rows)
    out_csv = Path(args.out_csv)
    summary.to_csv(out_csv, index=False)

    manifest = {
        "product": "national_pilot19_label_supports_v1",
        "issue": 19,
        "adapter_version": ADAPTER_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "git_commit": _git_commit(),
        "panel_manifest": PANEL_CSV.name,
        "event_plan": PLAN_JSON.name,
        "policy": POLICY_DOC,
        "sources": [
            {"key": s.key, "registry_product_id": s.registry_product_id,
             "kind": s.kind.name, "supports_m": list(s.supports_m),
             "path": str(SOURCE_FILES[s.key].relative_to(REPO_ROOT)),
             "positive_rule": s.positive_rule,
             "unknown_rule": s.unknown_rule,
             "negative_semantics": s.negative_semantics}
            for s in LABEL_SOURCES],
        "vector_repair": vector_repair,
        "bounds_rule": (
            "Albers 10 km cell edges densified at "
            f"{BOUNDS_DENSIFY_PER_EDGE} points/edge, projected to the UTM "
            "north zone of the WGS84 cell centroid "
            "floor((lon+180)/6)+1; same grid used for Phase D EO exports"),
        "cell_assignment_rule": (
            "export grids cover the UTM bbox (larger than the rotated "
            "cell); cell-level statistics use pixel CENTRES inside the "
            "exact (densified, projected) Albers cell polygon -- the same "
            "centre-in-cell rule Issue #18 used (selected_rasterize GDAL "
            "centre rule); positive_area_km2 covers the full export grid, "
            "positive_area_km2_in_cell covers assigned pixels only"),
        "repair_tolerance_max_area_change": REPAIR_TOLERANCE,
        "n_rows": len(summary),
        "n_cells": int(summary.cell_id.nunique()) if not summary.empty else 0,
        "rows": rows,
        "checksums": {
            "panel_csv_sha256": _sha256(PANEL_CSV),
            "supports_csv_sha256":
                hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        },
    }
    out_json = Path(args.out_json)
    out_json.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    grouped = summary.groupby(
        ["family", "year", "support_m"]).positive_area_km2.sum().round(3)
    print(json.dumps({
        "rows": len(summary),
        "cells": int(summary.cell_id.nunique()) if not summary.empty else 0,
        "positive_area_km2_by_source": {
            f"{family}_{year}_{support_m}m": area
            for (family, year, support_m), area in grouped.items()},
        "unknown_pixels": int(summary.n_unknown.sum())}, indent=2,
        default=str))


if __name__ == "__main__":
    main()
