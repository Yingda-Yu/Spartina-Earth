#!/usr/bin/env python3
"""Label x analysis-cell overlap (M2.1a2, Issue #12, sections 30-34).

Offline, read-only over ``old datasets/``. Quantifies SILVER / WEAK label
coverage per fixed cell on every candidate grid, plus the HZB 2015
SILVER-vs-WEAK disagreement layer. Nothing is re-adjudicated; absence of
a label is recorded UNLABELED, never as a negative.

GoldSet handling stops at targets:
    GOLD_EVIDENCE_TARGET  - evidence target rationale (Issue #11 owns it)
    RESERVED_FOR_GOLDSET  - small deterministic pre-registration of future
                            field/UAV/expert sites; forbidden for training
No row is promoted to GOLD here.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyproj  # noqa: E402
import rasterio  # noqa: E402
from numpy.typing import NDArray  # noqa: E402
from rasterio.mask import raster_geometry_mask  # noqa: E402
from rasterio.transform import from_bounds  # noqa: E402
from rasterio.warp import Resampling, reproject  # noqa: E402
from shapely.geometry import box  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402
from shapely.ops import transform as shp_transform  # noqa: E402

TO_32651 = pyproj.Transformer.from_crs(4326, 32651, always_xy=True).transform

OVERLAP_COLUMNS = (
    "cell_id",
    "cell_size_m",
    "bay_id",
    "asset_id",
    "nominal_year",
    "label_tier",
    "positive_pixels",
    "positive_area_km2",
    "overlap_fraction_of_cell",
    "cell_label_status",
    "gold_target_flag",
    "gold_target_reason",
    "reserved_for_goldset",
)

DISAGREEMENT_COLUMNS = (
    "cell_id",
    "cell_size_m",
    "l1_silver_positive_px_common30m",
    "l3_weak_positive_px_common30m",
    "agreement_px",
    "silver_only_px",
    "weak_only_px",
    "union_px",
    "jaccard",
    "method",
)


def load_inventory_assets() -> tuple[Path, list[dict[str, Any]]]:
    spec = importlib.util.spec_from_file_location(
        "build_label_inventory",
        REPO_ROOT / "scripts/data/zhejiang/build_label_inventory.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.OLD, list(mod.ASSETS)


def cell_polys(cells_csv: Path) -> dict[str, dict[str, Any]]:
    df = pd.read_csv(cells_csv)
    out: dict[str, dict[str, Any]] = {}
    for r in df.to_dict("records"):
        poly = box(float(r["westx_easting_m"]), float(r["southy_northing_m"]),
                   float(r["eastx_easting_m"]), float(r["northy_northing_m"]))
        out[r["cell_id"]] = {"row": r, "poly32651": poly}
    return out


def raster_positive_in_cell(
    ds: rasterio.DatasetReader,
    cell_poly_32651: BaseGeometry,
) -> tuple[int, float, float]:
    """Windowed positive-pixel count; returns (px, area_km2, px_area_m2)."""
    to_raster = pyproj.Transformer.from_crs(
        32651, ds.crs, always_xy=True).transform
    geom_r = shp_transform(to_raster, cell_poly_32651)
    try:
        mask, transform, window = raster_geometry_mask(
            ds, [geom_r], crop=True, invert=True)
    except ValueError:
        return 0, 0.0, 900.0
    data = ds.read(1, window=window)
    if ds.nodata is not None:
        mask &= data != ds.nodata
    n = int(np.count_nonzero(mask & (data > 0)))
    px_area = abs(transform.a * transform.e)
    return n, round(n * px_area / 1e6, 4), float(abs(transform.a * transform.e))


def common_grid_labels(
    path: Path,
    cell_poly: BaseGeometry,
    dst_shape: tuple[int, int],
    dst_transform: Any,
) -> NDArray[Any] | None:
    """Reproject a binary label raster onto the cell's 32651 30 m grid."""
    with rasterio.open(path) as ds:
        to_raster = pyproj.Transformer.from_crs(
            32651, ds.crs, always_xy=True).transform
        geom_r = shp_transform(to_raster, cell_poly)
        try:
            _mask, src_transform, window = raster_geometry_mask(
                ds, [geom_r], crop=True, invert=True)
        except ValueError:
            return None
        src = ds.read(1, window=window).astype("float32")
        if ds.nodata is not None:
            src[src == ds.nodata] = 0
        dst = np.zeros(dst_shape, dtype="uint8")
        reproject(
            source=(src > 0).astype("uint8"),
            destination=dst,
            src_transform=src_transform,
            src_crs=ds.crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:32651",
            resampling=Resampling.nearest,
        )
        return dst.astype(bool)


def vector_area_in_cell(
    path: Path, cell_poly: BaseGeometry
) -> tuple[int, float]:
    minx, miny, maxx, maxy = shp_transform(
        pyproj.Transformer.from_crs(32651, 4326, always_xy=True).transform,
        cell_poly).bounds
    try:
        gdf = gpd.read_file(path, bbox=(minx, miny, maxx, maxy))
    except Exception:  # noqa: BLE001 - record MISSING never fabricate
        return -1, 0.0
    if len(gdf) == 0:
        return 0, 0.0
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    geog_cell = shp_transform(
        pyproj.Transformer.from_crs(32651, 4326, always_xy=True).transform,
        cell_poly)
    hits = gdf.geometry[gdf.geometry.intersects(geog_cell)]
    if len(hits) == 0:
        return 0, 0.0
    area = sum(float(shp_transform(TO_32651, g).area)
               for g in hits.intersection(geog_cell) if not g.is_empty)
    return int(len(hits)), round(area / 1e6, 4)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-dir",
                        default=str(REPO_ROOT / "datasets/manifests"))
    args = parser.parse_args()
    mdir = Path(args.manifest_dir)

    old_dir, assets = load_inventory_assets()
    label_assets = [
        a for a in assets if a["asset_kind"] in
        ("RASTER_LABEL", "VECTOR_LABEL")]
    paths = {a["asset_id"]: old_dir / a["relpath"] for a in label_assets}

    cells = cell_polys(mdir / "zhejiang_analysis_cells_v0.csv")
    rows: list[dict[str, Any]] = []
    # positive area lookup cell -> {asset_id: km2}
    pos: dict[str, dict[str, float]] = defaultdict(dict)

    for cid, bundle in sorted(cells.items()):
        r = bundle["row"]
        poly = bundle["poly32651"]
        cell_area = float(poly.area) / 1e6
        for asset in label_assets:
            aid = asset["asset_id"]
            path = paths[aid]
            px = 0
            area = 0.0
            if path.exists():
                if asset["asset_kind"] == "RASTER_LABEL":
                    with rasterio.open(path) as ds:
                        px, area, _ = raster_positive_in_cell(ds, poly)
                else:
                    _feats, area = vector_area_in_cell(path, poly)
                    px = _feats if _feats >= 0 else -1
            pos[cid][aid] = area
            tier = asset["label_tier"]
            rows.append({
                "cell_id": cid,
                "cell_size_m": int(r["cell_size_m"]),
                "bay_id": r["bay_id"],
                "asset_id": aid,
                "nominal_year": int(asset["nominal_year"]),
                "label_tier": tier,
                "positive_pixels": px,
                "positive_area_km2": area,
                "overlap_fraction_of_cell": (
                    round(area / cell_area, 6) if area else 0.0),
                "cell_label_status": "",
                "gold_target_flag": "",
                "gold_target_reason": "",
                "reserved_for_goldset": "",
            })

    df = pd.DataFrame(rows)
    # cell status: any SILVER / any WEAK / UNLABELED (never NEGATIVE)
    cell_tier = (
        df[df.positive_area_km2 > 0]
        .groupby("cell_id")["label_tier"]
        .agg(lambda s: "SILVER+WEAK" if set(s) >= {"SILVER", "WEAK"}
             else next(iter(set(s)))))
    df["cell_label_status"] = df["cell_id"].map(
        lambda c: cell_tier.get(c, "UNLABELED"))

    # ---- GoldSet targets on the recommended 10 km grid only --------------
    # Flags are cell-level decisions broadcast to every asset row of the
    # cell; no label is promoted to GOLD (Issue #11 owns promotion).
    ten = df[df.cell_size_m == 10_000]
    silver_cells = set(ten[(ten.label_tier == "SILVER")
                           & (ten.positive_area_km2 > 0)].cell_id)
    weak_cells = set(ten[(ten.label_tier == "WEAK")
                         & (ten.positive_area_km2 > 0)].cell_id)
    yqb_ids = {c for c, b in cells.items()
               if b["row"]["cell_size_m"] == 10_000
               and b["row"]["bay_id"] == "ZJ-YQB"}
    hzb_ids = {c for c, b in cells.items()
               if b["row"]["cell_size_m"] == 10_000
               and b["row"]["bay_id"] == "ZJ-HZB"}
    smb_ids = {c for c, b in cells.items()
               if b["row"]["cell_size_m"] == 10_000
               and b["row"]["bay_id"] == "ZJ-SMB"}
    disagreement = (silver_cells & weak_cells) & hzb_ids
    temporal = (silver_cells & weak_cells) & yqb_ids
    reasons: dict[str, str] = {}
    for c in sorted(disagreement):
        reasons[c] = "DISAGREEMENT_SILVER_2015_VS_WEAK_2015_HZB"
    for c in sorted(temporal):
        reasons[c] = "TEMPORAL_SILVER_2015_VS_WEAK_CMSA_2019_2021_YQB"
    # SILVER-only cells stay SILVER (usable but not promoted); they do
    # not demand new evidence, so they are not GoldSet targets.
    for c in sorted(weak_cells - silver_cells):
        reasons.setdefault(c, "WEAK_ONLY_EVIDENCE_UPGRADE_TARGET")
    # SMB: zero label anywhere inside the cell square (note this differs
    # from the envelope, whose L1 area is 0 by construction)
    smb_gap = smb_ids - (silver_cells | weak_cells)
    for c in sorted(smb_gap):
        reasons[c] = "CROSS_BAY_LABEL_GAP_SMB_NO_LABEL_IN_CELL"

    # deterministic RESERVED set: one HZB disagreement cell (max union
    # area), one YQB temporal cell (max CMSA area), one SMB gap cell
    reserved: dict[str, str] = {}
    if disagreement:
        area_rank = (
            ten[ten.cell_id.isin(disagreement)]
            .groupby("cell_id").positive_area_km2.sum()
            .sort_values(ascending=False))
        reserved[area_rank.index[0]] = (
            "PRE_REGISTERED_FIELD_UAV_TARGET_HZB_DISAGREEMENT")
    if temporal:
        cmsa = ten[ten.cell_id.isin(temporal)
                   & ten.asset_id.str.startswith(("L4", "L5", "L6"))]
        area_rank = (cmsa.groupby("cell_id").positive_area_km2.sum()
                     .sort_values(ascending=False))
        reserved[area_rank.index[0]] = (
            "PRE_REGISTERED_FIELD_UAV_TARGET_YQB_TEMPORAL")
    if smb_gap:
        reserved[min(smb_gap)] = (
            "PRE_REGISTERED_FIELD_UAV_TARGET_SMB_GAP")

    cell_reason = dict(reasons)
    for cid, why in reserved.items():
        prev = cell_reason.get(cid, "")
        cell_reason[cid] = f"{prev}|{why}" if prev else why

    ten_mask = df.cell_size_m == 10_000
    df.loc[ten_mask, "gold_target_flag"] = df.loc[
        ten_mask, "cell_id"].map(
            lambda c: "GOLD_EVIDENCE_TARGET" if c in cell_reason else "")
    df.loc[ten_mask, "gold_target_reason"] = df.loc[
        ten_mask, "cell_id"].map(lambda c: cell_reason.get(c, ""))
    df.loc[ten_mask, "reserved_for_goldset"] = df.loc[
        ten_mask, "cell_id"].map(
            lambda c: "RESERVED_FOR_GOLDSET" if c in reserved else "")

    df = df.sort_values(["cell_size_m", "cell_id", "asset_id"])
    df.to_csv(mdir / "zhejiang_label_cell_overlap_v0.csv", index=False)

    # ---- HZB disagreement on a common 30 m 32651 grid -------------------
    l1 = paths["L1-china2015-raster30m"]
    l3 = paths["L3-hangzhou-mask-2015"]
    drows: list[dict[str, Any]] = []
    hzb_candidates = sorted(
        c for c, b in cells.items()
        if b["row"]["cell_size_m"] == 10_000
        and b["row"]["bay_id"] == "ZJ-HZB"
        and (pos[c].get("L1-china2015-raster30m", 0) > 0
             or pos[c].get("L3-hangzhou-mask-2015", 0) > 0))
    for cid in hzb_candidates:
        poly = cells[cid]["poly32651"]
        size = 10_000 // 30
        tf = from_bounds(*poly.bounds, size, size)
        a = common_grid_labels(l1, poly, (size, size), tf)
        b = common_grid_labels(l3, poly, (size, size), tf)
        if a is None or b is None:
            continue
        agree = int(np.count_nonzero(a & b))
        only_a = int(np.count_nonzero(a & ~b))
        only_b = int(np.count_nonzero(b & ~a))
        union = agree + only_a + only_b
        drows.append({
            "cell_id": cid,
            "cell_size_m": 10000,
            "l1_silver_positive_px_common30m": int(np.count_nonzero(a)),
            "l3_weak_positive_px_common30m": int(np.count_nonzero(b)),
            "agreement_px": agree,
            "silver_only_px": only_a,
            "weak_only_px": only_b,
            "union_px": union,
            "jaccard": round(agree / union, 4) if union else None,
            "method": ("nearest-neighbour warp to common EPSG:32651 30m "
                       "grid; ~1 px positional tolerance; diagnostic"),
        })
    pd.DataFrame(drows, columns=list(DISAGREEMENT_COLUMNS)).to_csv(
        mdir / "zhejiang_hzb_label_disagreement_v0.csv", index=False)

    # ---- console summary ------------------------------------------------
    for size in sorted(df.cell_size_m.unique()):
        status = (df[df.cell_size_m == size][["cell_id", "cell_label_status"]]
                  .drop_duplicates().cell_label_status.value_counts())
        print(f"{size} m: {dict(status)}")
    print(f"disagreement cells: {len(drows)}; RESERVED cells: "
          f"{sorted(reserved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
