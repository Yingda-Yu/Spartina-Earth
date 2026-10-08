#!/usr/bin/env python3
"""Issue #18 — 2020 multi-resolution label disagreement and scale audit.

Quantifies how resolution, boundary position, patch size, region and
mapping protocol structure *disagreement* among three 2020 Spartina
external-reference products. No product is treated as truth; no
artificial 5 m national lattice is created; native geometry is preserved
and only documented comparison supports are built:

* 30 m support  - the native GEODATA grid (Krasovsky Albers), used as a
                  comparison lattice only. Fine products contribute
                  EXACT fractional Spartina cover per 30 m pixel via
                  polygon/grid intersection on reprojected derived copies.
* 10 m support  - a documented project comparison lattice in China Albers
                  (origin 0,0), used only for CMSA vs CM-SSM. GEODATA is
                  never rasterised onto it.

Inputs never move: source shapes are immutable; repair and reprojection
operate on derived copies under work/issue18/ (gitignored). Tracked
outputs are aggregate tables/manifests under datasets/manifests plus
docs/analysis/2020_LABEL_DISAGREEMENT_AUDIT.md.

Usage::

    PYTHONPATH=src python3 scripts/analysis/labels/run_2020_scale_audit.py
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio import features
from rasterio.enums import MergeAlg, Resampling
from rasterio.transform import Affine
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from spartina.data.national.geometry import CHINA_ALBERS_CRS
from spartina.labels import scale_agreement as sa

REPO_ROOT = Path(__file__).resolve().parents[3]
GEODATA_TIF = REPO_ROOT / (
    "work/intake/staging/2020年中国滨海30 m分辨率互花米草空间分布动态数据集"
    "-数据实体/2020年中国滨海30 m分辨率互花米草空间分布动态数据集"
    "-数据实体.tif"
)
CMSA_SHP = REPO_ROOT / (
    "work/intake/staging/中国大陆2017-2021互花米草CMSA/CMSA_2020.shp"
)
CMSSM_SHP = REPO_ROOT / "old datasets/30mSpartinaChina/2020/CM-SSM/CM-SSM.shp"
CELLS_CSV = REPO_ROOT / "work/national/domain/cells_china_albers_W10000.csv"
WORK = REPO_ROOT / "work/issue18"
DERIVED = WORK / "derived"
FIG_WORK = WORK / "figures"
MANIFEST_DIR = REPO_ROOT / "datasets/manifests"
DOCS_ANALYSIS = REPO_ROOT / "docs/analysis"

GRIDCODE_POSITIVE = 2
BLOCK_PIXELS = 2048
HALO_30M = 16  # 480 m halo > 300 m deepest boundary band
HALO_10M = 40  # 400 m
BOUNDARY_MAX_M = 300.0
PURE_LO = 0.1
PURE_HI = 0.9
SEED = 20201018
N_BOOT = 500

# Independent (source-independent) region attribution parameters,
# Issue #18 R1. Provinces are Natural Earth 10 m admin-1 polygons
# (independent of every audited label product). Pixel centroids inside
# a province polygon are attributed directly; labelled pixels whose
# centroid falls on water beyond the polygon coastline receive the
# nearest province, subject to a reach cap and a border-tie rule.
ADMIN1_SHP = REPO_ROOT / (
    "work/external/naturalearth_10m_admin1/extracted/"
    "ne_10m_admin_1_states_provinces.shp"
)
INDEP_REGION_REACH_M = 25_000.0   # matches the project 25 km island reach
INDEP_REGION_AMBIG_M = 300.0      # <=300 m between two provinces => UNKNOWN

SUM_FIELDS_30 = (
    "n", "g", "c", "m", "gc", "gm", "cm", "bc", "bm", "cmb",
    "dgc", "dgm", "dcm",
    "g0mix_c", "g0mix_m", "g1mix_c", "g1mix_m",
)
SUM_FIELDS_10 = ("n", "c", "m", "cm", "bc", "bm", "cmb", "dcm")


# ---------------------------------------------------------------------------
# Provenance / geometry repair
# ---------------------------------------------------------------------------

def git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class RepairAudit:
    product: str
    features_before: int
    invalid_before: int
    self_intersecting_before: int
    slivers_lt_100m2_before: int
    total_area_km2_before: float
    parts_after: int
    invalid_after: int
    empty_or_nonpolygon_dropped: int
    total_area_km2_after: float
    area_change_pct: float
    repair_method: str
    note: str


def make_valid_copy(product: str, gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, RepairAudit]:
    """Repair invalid geometries on a derived copy; audit every change."""
    n_before = len(gdf)
    invalid_before = int((~gdf.geometry.is_valid).sum())
    nonsimple_before = int((~gdf.geometry.is_simple).sum())
    area_before = float(gdf.geometry.area.sum())
    slivers = int((gdf.geometry.area < 100.0).sum())

    fixed = gpd.GeoDataFrame(
        gdf.drop(columns="geometry"),
        geometry=gdf.make_valid(),
        crs=gdf.crs,
    )
    exploded = fixed.explode(ignore_index=True)
    is_polygonal = exploded.geometry.geom_type.isin(
        ["Polygon", "MultiPolygon"]
    )
    dropped = int((exploded.geometry.is_empty | ~is_polygonal).sum())
    exploded = exploded[~exploded.geometry.is_empty & is_polygonal].copy()
    invalid_after = int((~exploded.geometry.is_valid).sum())
    area_after = float(exploded.geometry.area.sum())
    change_pct = 100.0 * (area_after - area_before) / area_before
    audit = RepairAudit(
        product=product,
        features_before=n_before,
        invalid_before=invalid_before,
        self_intersecting_before=nonsimple_before,
        slivers_lt_100m2_before=slivers,
        total_area_km2_before=round(area_before / 1e6, 4),
        parts_after=len(exploded),
        invalid_after=invalid_after,
        empty_or_nonpolygon_dropped=dropped,
        total_area_km2_after=round(area_after / 1e6, 4),
        area_change_pct=round(change_pct, 5),
        repair_method=(
            "GeoDataFrame.make_valid() (shapely 2 / GEOS MakeValid) on a "
            "derived copy; explode(ignore_index=True) to single parts; "
            "empty and non-polygonal parts dropped; source file untouched"
        ),
        note=(
            "STOP CONDITION |area_change_pct| < 1% asserted in code; "
            "CMSA gridcode=0 features excluded upstream, never relabelled."
        ),
    )
    assert abs(change_pct) < 1.0, f"material repair area change for {product}"
    assert invalid_after == 0, f"{product} still has invalid parts"
    return exploded, audit


# ---------------------------------------------------------------------------
# Region layer (CM-SSM native province `name`)
# ---------------------------------------------------------------------------

def region_code_map() -> dict[str, int]:
    provinces = [p for p in sa.PROVINCE_ORDER if p != "UNATTRIBUTED"]
    return {abbr: i + 1 for i, (abbr, _) in enumerate(sa.PROVINCE_CODES.items())
            if sa.PROVINCE_CODES[abbr] in provinces}


def region_name(code: int) -> str:
    provinces = [p for p in sa.PROVINCE_ORDER if p != "UNATTRIBUTED"]
    return provinces[int(code) - 1] if code > 0 else "UNATTRIBUTED"


# ---------------------------------------------------------------------------
# Raster machinery
# ---------------------------------------------------------------------------

def exact_cover_block(
    block_box_geom: BaseGeometry,
    polys: gpd.GeoDataFrame,
    value_col: str,
    origin_x: float,
    origin_y_north: float,
    pixel_m: float,
    n_rows: int,
    n_cols: int,
) -> tuple[np.ndarray[Any, Any], pd.DataFrame]:
    """Exact union polygon area (m^2) per touched pixel in a block halo.

    The selected source polygons are clipped to the halo and dissolved
    (``union_all``): per-pixel cover is then an exact *union* fraction,
    so intra-product overlaps / duplicate vectorisation seams cannot
    double-count area, and every geometry used in pixel predicates is
    local, keeping un-prepared GEOS predicates cheap. Patch identity per
    pixel comes from a separate all-touched GDAL burn of the original
    source IDs (GDAL replacement order breaks ties, which arise only
    where source polygons of the same product overlap).
    """
    transform = Affine(pixel_m, 0.0, origin_x, 0.0, -pixel_m, origin_y_north)
    # Persistent national STRtree (materialised once by the caller):
    # a gpd.sjoin against a column-projected frame would rebuild it on
    # every block.
    hit_idx = np.asarray(
        polys.sindex.query(block_box_geom, predicate="intersects")
    )
    cover = np.zeros((n_rows, n_cols), dtype=np.float64)
    if hit_idx.size == 0:
        return cover, pd.DataFrame(columns=["row", "col", value_col, "area_m2"])
    sel = polys.iloc[hit_idx]
    owner = cast(
        np.ndarray[Any, Any],
        features.rasterize(
            [(geom, int(val)) for geom, val in
             zip(sel.geometry, sel[value_col], strict=True)],
            out_shape=(n_rows, n_cols),
            transform=transform,
            fill=-1,
            dtype="int32",
            all_touched=True,
            merge_alg=MergeAlg.replace,
        ),
    )
    clipped = shapely.intersection(sel.geometry.to_numpy(), block_box_geom)
    clipped = clipped[~shapely.is_empty(clipped)]
    # Exact union semantics without a nationwide-per-block dissolve:
    # union only the connected components whose members overlap with
    # positive area (duplicate vectorisation seams, sliver overlaps).
    # Edge-touching neighbours share zero area and are kept as separate
    # parts; disjoint patches pass through untouched. The resulting
    # parts are pairwise area-disjoint, so per-(part,pixel) intersection
    # areas sum to the exact union cover.
    parts_geom = _union_overlapping_components(clipped)
    touched = features.rasterize(
        [(geom, 1) for geom in parts_geom],
        out_shape=(n_rows, n_cols),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=True,
        merge_alg=MergeAlg.replace,
    )
    rr, cc = np.nonzero(touched)
    minx = origin_x + cc * pixel_m
    maxy = origin_y_north - rr * pixel_m
    box_geoms = shapely.box(
        minx, maxy - pixel_m, minx + pixel_m, maxy
    )
    # Vectorised bulk STRtree query replaces a gpd.sjoin (which would
    # build a fresh index for the parts of every block).
    part_tree = shapely.STRtree(parts_geom)
    qb, qp = part_tree.query(box_geoms, predicate="intersects")
    left_boxes = box_geoms[qb]
    pixel_area = float(pixel_m) * float(pixel_m)
    areas = np.zeros(qb.size, dtype=np.float64)
    if qb.size:
        # Per part: a PREPARED covers() test flags fully covered pixel
        # boxes cheaply even for high-vertex meadow polygons; the
        # remaining boundary boxes are unioned and intersected with the
        # part once, then pair areas are taken from that local edge
        # geometry. Parts are area-disjoint and pixel boxes are
        # area-disjoint, so the pair areas partition both unions exactly.
        order = np.argsort(qp, kind="stable")
        qb_s, qp_s = qb[order], qp[order]
        uniq_parts, starts = np.unique(qp_s, return_index=True)
        for loop_i, part_pos in enumerate(uniq_parts):
            lo = int(starts[loop_i])
            hi = int(starts[loop_i + 1]) if loop_i + 1 < len(
                uniq_parts
            ) else qb_s.size
            pair_pos = order[lo:hi]
            boxes_p = left_boxes[pair_pos]
            part = parts_geom[int(part_pos)]
            prepared = shapely.prepared.prep(part)
            full_k: list[int] = []
            bnd_boxes: list[Any] = []
            bnd_k: list[int] = []
            for k, box_geom in zip(pair_pos, boxes_p, strict=True):
                if prepared.covers(box_geom):
                    full_k.append(int(k))
                else:
                    bnd_boxes.append(box_geom)
                    bnd_k.append(int(k))
            if full_k:
                areas[np.asarray(full_k, dtype=np.int64)] = pixel_area
            if bnd_boxes:
                edge = shapely.intersection(
                    part,
                    shapely.union_all(np.asarray(bnd_boxes), grid_size=0.001),
                )
                bnd_idx = np.asarray(bnd_k, dtype=np.int64)
                areas[bnd_idx] = shapely.area(
                    shapely.intersection(
                        np.repeat(np.asarray([edge]), len(bnd_idx)),
                        left_boxes[bnd_idx],
                    )
                )
    # Drop point/line-only touches (zero area): they must not attach a
    # patch identity to a pixel they only graze.
    nz = areas > 0.0
    rows_k = rr[qb[nz]]
    cols_k = cc[qb[nz]]
    areas_k = areas[nz]
    np.add.at(cover, (rows_k, cols_k), areas_k)
    detail = pd.DataFrame({
        "row": rows_k,
        "col": cols_k,
        value_col: owner[rows_k, cols_k].astype(np.int64),
        "area_m2": areas_k,
    })
    return cover, detail


def _union_overlapping_components(
    geoms: np.ndarray[Any, Any],
) -> np.ndarray[Any, Any]:
    """Union only the components of geometries overlapping with area >0.

    Disjoint or edge-touching geometries pass through individually; this
    keeps the common case of thousands of disjoint mapped patches free
    of a costly cascaded union while preserving exact union semantics.
    """
    n = int(geoms.size)
    if n == 0:
        return geoms
    parent = np.arange(n, dtype=np.int64)

    def find(i: int) -> int:
        root = i
        while int(parent[root]) != root:
            root = int(parent[root])
        while int(parent[i]) != root:
            parent[i], i = root, int(parent[i])
        return root

    tree = shapely.STRtree(geoms)
    ai, bi = tree.query(geoms, predicate="intersects")
    keep = ai < bi
    if keep.any():
        # Positive-area overlap iff the interiors intersect in 2D;
        # edge-only neighbours (II='F') must NOT be unioned. A relate
        # predicate avoids materialising the intersection geometries.
        overlap = shapely.relate_pattern(
            geoms[ai[keep]], geoms[bi[keep]], "2********"
        )
        for a0, b0 in zip(ai[keep][overlap], bi[keep][overlap], strict=True):
            ra, rb = find(int(a0)), find(int(b0))
            if ra != rb:
                parent[rb] = ra

    def find_all() -> np.ndarray[Any, Any]:
        return np.fromiter((find(i) for i in range(n)), dtype=np.int64,
                           count=n)

    roots = find_all()
    out: list[Any] = []
    for root in np.unique(roots):
        members = geoms[roots == root]
        if members.size == 1:
            out.append(members[0])
        else:
            # 1 mm grid snap; area impact at 10/30 m supports is << 1e-6.
            merged = shapely.get_parts(
                shapely.union_all(members, grid_size=0.001)
            )
            out.extend(list(merged))
    return np.asarray(out, dtype=object)


def selected_rasterize(
    polys: gpd.GeoDataFrame,
    value_col: str,
    halo: BaseGeometry,
    origin_x: float,
    origin_y_north: float,
    pixel_m: float,
    n_rows: int,
    n_cols: int,
    fill: int,
    all_touched: bool = False,
) -> np.ndarray[Any, Any]:
    """Burn only the halo-intersecting simple polygons.

    Selecting simple source polygons via the persistent STRtree (never
    clipping, never dissolving) keeps per-block GDAL work proportional
    to local geometry while giving identical core-pixel values to a
    nationwide burn. Polygons overlapping across labels tie on GDAL
    replacement order (the overlap case is absent for W10 cells and
    negligible between adjacent provinces).
    """
    transform = Affine(pixel_m, 0.0, origin_x, 0.0, -pixel_m, origin_y_north)
    hits = np.asarray(polys.sindex.query(halo, predicate="intersects"))
    if hits.size == 0:
        return np.full((n_rows, n_cols), fill, dtype=np.int32)
    sub = polys.iloc[hits]
    return cast(
        np.ndarray[Any, Any],
        features.rasterize(
            [(geom, int(val)) for geom, val in
             zip(sub.geometry, sub[value_col], strict=True)],
            out_shape=(n_rows, n_cols),
            transform=transform,
            fill=fill,
            dtype="int32",
            all_touched=all_touched,
            merge_alg=MergeAlg.replace,
        ),
    )


def patch_region_lookup(frame: gpd.GeoDataFrame, id_col: str) -> np.ndarray[Any, Any]:
    """Patch-id -> province code lookup table for one product."""
    first = (
        frame[[id_col, "region_code"]]
        .drop_duplicates(id_col)
        .sort_values(id_col)
    )
    ids = first[id_col].to_numpy().astype(np.int64)
    lut = np.zeros(int(ids.max()) + 1, dtype=np.int32)
    lut[ids] = first["region_code"].to_numpy().astype(np.int32)
    return lut


def region_label_block(
    cmsa_frame: gpd.GeoDataFrame,
    cmssm_frame: gpd.GeoDataFrame,
    id_col_c: str,
    id_col_m: str,
    lut_c: np.ndarray[Any, Any],
    lut_m: np.ndarray[Any, Any],
    halo: BaseGeometry,
    origin_x: float,
    origin_y_north: float,
    pixel_m: float,
    n_rows: int,
    n_cols: int,
) -> np.ndarray[Any, Any]:
    """Per-pixel province labels from the OWNING mapped patch.

    All-touched patch-id burns (GDAL replacement ties overlapping
    patches) are mapped to province codes via each product's own
    patch->region table: native CM-SSM province name takes priority;
    pixels covered only by CMSA receive CMSA's representative-point
    province. Pixels with no fine-product patch stay 0 (UNATTRIBUTED);
    a centre-sampled province burn would otherwise drop thin /
    partial-cover pixels into UNATTRIBUTED at the 10/30 m supports.
    """
    rid_c = selected_rasterize(
        cmsa_frame, id_col_c, halo, origin_x, origin_y_north,
        pixel_m, n_rows, n_cols, fill=-1, all_touched=True,
    )
    rid_m = selected_rasterize(
        cmssm_frame, id_col_m, halo, origin_x, origin_y_north,
        pixel_m, n_rows, n_cols, fill=-1, all_touched=True,
    )
    region_m = np.where(rid_m >= 0, lut_m[np.maximum(rid_m, 0)], 0)
    region_c = np.where(rid_c >= 0, lut_c[np.maximum(rid_c, 0)], 0)
    out = region_m.astype(np.int32, copy=True)
    out[out == 0] = region_c[out == 0]
    return out


def signed_distance(mask: np.ndarray[Any, Any], pixel_m: float) -> np.ndarray[Any, Any]:
    """Backward-compatible local alias for ``sa.signed_distance``."""
    return sa.signed_distance(mask, pixel_m)


# ---------------------------------------------------------------------------
# Source-independent region attribution (Issue #18 R1, Part A)
# ---------------------------------------------------------------------------

# method codes in the independent attribution audit tables
INDEP_METHOD_CENTROID = 1
INDEP_METHOD_NEAREST = 2
INDEP_METHOD_UNKNOWN = 0


def load_coastal_provinces(crs: Any) -> gpd.GeoDataFrame:
    """Natural Earth 10 m admin-1 coastal provinces, one geom per code.

    The admin-1 polygons are independent of every audited label product
    (CMSA / CM-SSM / GEODATA).  Names map to the project region codes by
    position in ``sa.PROVINCE_ORDER`` (1..10; 0 stays UNKNOWN).
    """
    name_to_code = {
        name: i + 1
        for i, name in enumerate(sa.PROVINCE_ORDER)
        if name != "UNATTRIBUTED"
    }
    prov = gpd.read_file(ADMIN1_SHP, columns=["name"], engine="pyogrio")
    prov = prov[prov["name"].isin(name_to_code)][["name", "geometry"]].copy()
    prov["code"] = (
        prov["name"].map(name_to_code).astype("int32")
    )
    prov = prov.to_crs(crs)
    prov = prov.dissolve(
        by="code", aggfunc={"name": "first"}, as_index=False
    )
    prov["geometry"] = prov.geometry.buffer(0.0)
    prov = gpd.GeoDataFrame(prov, geometry="geometry", crs=crs)
    _ = prov.sindex
    return prov[["code", "name", "geometry"]]


def independent_region_block(
    prov: gpd.GeoDataFrame,
    halo: BaseGeometry,
    origin_x: float,
    origin_y_north: float,
    pixel_m: float,
    n_rows: int,
    n_cols: int,
    need: np.ndarray[Any, Any],
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Source-independent per-pixel region codes for one raster block.

    Deterministic, product-independent rule:

    1. pixel **centroid inside** exactly one admin-1 province polygon
       -> that province (``method=1``);
    2. centroid outside (coastline-generalised polygons leave seaward
       tidal-flat pixels on water) -> nearest province polygon if its
       distance is <= ``INDEP_REGION_REACH_M`` AND the second-nearest
       province is farther by more than ``INDEP_REGION_AMBIG_M``
       (``method=2``);
    3. otherwise the pixel stays ``0`` / ``method=0`` (UNKNOWN): beyond
       reach, or a border tie too close to force.  Ambiguous border
       pixels are never assigned.

    Only pixels where ``need`` is True receive a code.  Returns
    ``(code int32, method int8)`` arrays shaped ``(n_rows, n_cols)``.
    """
    base = selected_rasterize(
        prov, "code", halo, origin_x, origin_y_north, pixel_m,
        n_rows, n_cols, fill=0, all_touched=False,
    )
    code = base.astype(np.int32, copy=True)
    method = np.where(base > 0, INDEP_METHOD_CENTROID, 0).astype(np.int8)
    unresolved = (base == 0) & need
    ys, xs = np.nonzero(unresolved)
    if ys.size and not prov.empty:
        px = origin_x + (xs + 0.5) * pixel_m
        py = origin_y_north - (ys + 0.5) * pixel_m
        pts = shapely.points(px, py)
        # Only provinces within reach of the halo can serve a core
        # pixel; the STRtree query is per-block but geometries are
        # process-global via the fork-inherited province frame.
        reach_box = halo.buffer(INDEP_REGION_REACH_M + 2.0 * pixel_m)
        cand_pos = prov.sindex.query(reach_box, predicate="intersects")
        if cand_pos.size:
            cand = prov.iloc[cand_pos]
            geoms = cand.geometry.to_numpy()
            codes = cand["code"].to_numpy().astype(np.int32)
            dist_all = np.column_stack(
                [shapely.distance(pts, g) for g in geoms]
            )
            nearest_col = dist_all.argmin(axis=1)
            d1 = dist_all[np.arange(ys.size), nearest_col]
            if dist_all.shape[1] > 1:
                tmp = dist_all.copy()
                tmp[np.arange(ys.size), nearest_col] = np.inf
                d2 = tmp.min(axis=1)
            else:
                d2 = np.full(ys.size, np.inf)
            ok = (d1 <= INDEP_REGION_REACH_M) & (
                np.isinf(d2) | (d2 - d1 > INDEP_REGION_AMBIG_M)
            )
            code[ys[ok], xs[ok]] = codes[nearest_col[ok]]
            method[ys[ok], xs[ok]] = INDEP_METHOD_NEAREST
    code[~need] = 0
    method[~need] = 0
    return code, method


def add_keyed2_fast(
    acc: KeyedSums,
    key_codes: tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]],
    arrays: tuple[np.ndarray[Any, Any], ...],
    valid: np.ndarray[Any, Any] | None = None,
) -> None:
    """Two-integer-key version of :func:`add_keyed_fast`."""
    k1 = key_codes[0].ravel().astype(np.int64)
    k2 = key_codes[1].ravel().astype(np.int64)
    flattened = tuple(a.ravel() for a in arrays)
    if valid is not None:
        mask = valid.ravel()
        k1, k2 = k1[mask], k2[mask]
        flattened = tuple(a[mask] for a in flattened)
    packed = k1 * 64 + k2
    uniq, inv = np.unique(packed, return_inverse=True)
    k = int(uniq.size)
    sums = np.empty((k, len(flattened)), dtype=np.float64)
    for j, arr in enumerate(flattened):
        sums[:, j] = np.bincount(
            inv, weights=arr.astype(np.float64), minlength=k
        )
    for j, val in enumerate(uniq):
        key = (int(val // 64), int(val % 64))
        if key in acc.store:
            acc.store[key] = acc.store[key] + sums[j]
        else:
            acc.store[key] = sums[j].copy()



def patch_bins(area: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    edges = np.array(sa.PATCH_BIN_EDGES[:-1])
    idx = np.digitize(area, edges[1:], right=False)
    labels = np.array(sa.PATCH_BIN_LABELS + ("none",))
    out = labels[idx]
    out[area <= 0] = "none"
    return out


# ---------------------------------------------------------------------------
# Keyed accumulation
# ---------------------------------------------------------------------------

class KeyedSums:
    """Group rows by key columns; hold a sum vector per key."""

    def __init__(self, key_names: tuple[str, ...],
                 value_names: tuple[str, ...]) -> None:
        self.key_names = key_names
        self.value_names = value_names
        self.store: dict[tuple[Any, ...], np.ndarray[Any, Any]] = {}

    def add(self, keys: pd.DataFrame, values: pd.DataFrame) -> None:
        frame = pd.concat([keys.reset_index(drop=True), values.reset_index(drop=True)],
                          axis=1)
        grouped = frame.groupby(list(self.key_names), sort=False, observed=True)
        for key, sub in grouped:
            if not isinstance(key, tuple):
                key = (key,)
            vec = sub[list(self.value_names)].sum().to_numpy(dtype=np.float64)
            if key in self.store:
                self.store[key] += vec
            else:
                self.store[key] = vec

    def frame(self) -> pd.DataFrame:
        rows = [
            {**dict(zip(self.key_names, key, strict=True)),
             **dict(zip(self.value_names, vec, strict=True))}
            for key, vec in self.store.items()
        ]
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Pixel-tally core
# ---------------------------------------------------------------------------

DIST_LABELS = np.array(sa.DISTANCE_BIN_LABELS)
def distance_labels(abs_dist: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    # Right-inclusive edges: the first lattice ring (30 m on the 30 m
    # support, 10/20/30 m on the 10 m support) belongs to "0-30m",
    # otherwise the pre-registered near band is structurally empty.
    idx = np.digitize(abs_dist, sa.DISTANCE_BIN_EDGES[1:], right=True)
    return DIST_LABELS[idx]


def pixel_vectors_30(
    g: np.ndarray[Any, Any], fc_c: np.ndarray[Any, Any], fc_m: np.ndarray[Any, Any],
    dgc: np.ndarray[Any, Any], dgm: np.ndarray[Any, Any], dcm: np.ndarray[Any, Any],
) -> pd.DataFrame:
    g_b = g.astype(bool)
    b_c = fc_c >= 0.5
    b_m = fc_m >= 0.5
    return pd.DataFrame({
        "n": np.ones(g.size, dtype=np.float64),
        "g": g.ravel().astype(np.float64),
        "c": fc_c.ravel(),
        "m": fc_m.ravel(),
        "gc": (g_b & b_c).ravel().astype(np.float64),
        "gm": (g_b & b_m).ravel().astype(np.float64),
        "cm": np.minimum(fc_c, fc_m).ravel(),
        "bc": b_c.ravel().astype(np.float64),
        "bm": b_m.ravel().astype(np.float64),
        "cmb": (b_c & b_m).ravel().astype(np.float64),
        "dgc": dgc.ravel().astype(np.float64),
        "dgm": dgm.ravel().astype(np.float64),
        "dcm": dcm.ravel().astype(np.float64),
        "g0mix_c": ((~g_b) & (fc_c > PURE_LO) & (fc_c < PURE_HI)).ravel().astype(float),
        "g0mix_m": ((~g_b) & (fc_m > PURE_LO) & (fc_m < PURE_HI)).ravel().astype(float),
        "g1mix_c": (g_b & (fc_c > PURE_LO) & (fc_c < PURE_HI)).ravel().astype(float),
        "g1mix_m": (g_b & (fc_m > PURE_LO) & (fc_m < PURE_HI)).ravel().astype(float),
    })


def pixel_vectors_10(fc_c: np.ndarray[Any, Any], fc_m: np.ndarray[Any, Any],
                     dcm: np.ndarray[Any, Any]) -> pd.DataFrame:
    b_c = fc_c >= 0.5
    b_m = fc_m >= 0.5
    return pd.DataFrame({
        "n": np.ones(fc_c.size, dtype=np.float64),
        "c": fc_c.ravel(),
        "m": fc_m.ravel(),
        "cm": np.minimum(fc_c, fc_m).ravel(),
        "bc": b_c.ravel().astype(np.float64),
        "bm": b_m.ravel().astype(np.float64),
        "cmb": (b_c & b_m).ravel().astype(np.float64),
        "dcm": dcm.ravel().astype(np.float64),
    })


def add_keyed_fast(
    acc: KeyedSums,
    codes: np.ndarray[Any, Any],
    arrays: tuple[np.ndarray[Any, Any], ...],
    valid: np.ndarray[Any, Any] | None = None,
) -> None:
    """Full-core keyed sums via np.unique + bincount (no per-pixel pandas).

    Unlike the boundary-band accumulators, the regional/national area
    ledgers and the per-cell block-bootstrap inputs must include patch
    INTERIORS (pixels >300 m from any mapped edge), so this runs over
    every core pixel (optionally restricted by ``valid``). Column order
    must match ``acc.value_names``; ``acc`` must have a single key.
    """
    flat = codes.ravel()
    flattened = tuple(a.ravel() for a in arrays)
    if valid is not None:
        mask = valid.ravel()
        flat = flat[mask]
        flattened = tuple(a[mask] for a in flattened)
    uniq, inv = np.unique(flat, return_inverse=True)
    k = int(uniq.size)
    sums = np.empty((k, len(flattened)), dtype=np.float64)
    for j, arr in enumerate(flattened):
        sums[:, j] = np.bincount(
            inv, weights=arr.astype(np.float64), minlength=k
        )
    for j, code in enumerate(uniq):
        key = (int(code),)
        if key in acc.store:
            acc.store[key] = acc.store[key] + sums[j]
        else:
            acc.store[key] = sums[j].copy()


def add_contingency_30_fast(
    store: dict[int, int],
    region: np.ndarray[Any, Any],
    g: np.ndarray[Any, Any],
    fc_c: np.ndarray[Any, Any],
    fc_m: np.ndarray[Any, Any],
    cell: np.ndarray[Any, Any],
) -> None:
    """Full-core (region, GEO class, CMSA cover, CM-SSM cover) counts.

    Integer-encoded keys + np.unique keep millions of core pixels out
    of per-block pandas; restricted to W10-domain cell pixels. H6 needs
    patch INTERIORS, so this must not be limited to the 300 m band.
    """
    valid = cell >= 0
    if not bool(valid.any()):
        return
    rg = region[valid].astype(np.int64)
    gg = g[valid].astype(bool).astype(np.int64)
    cb = sa.fine_coverage_bins(fc_c[valid]).astype(np.int64)
    mb = sa.fine_coverage_bins(fc_m[valid]).astype(np.int64)
    keys = ((rg * 2 + gg) * 5 + cb) * 5 + mb
    uniq, counts = np.unique(keys, return_counts=True)
    for key, cnt in zip(uniq.tolist(), counts.tolist(), strict=True):
        store[int(key)] = store.get(int(key), 0) + int(cnt)


def add_contingency_10_fast(
    store: dict[int, int],
    fc_c: np.ndarray[Any, Any],
    fc_m: np.ndarray[Any, Any],
    cell: np.ndarray[Any, Any],
) -> None:
    valid = cell >= 0
    if not bool(valid.any()):
        return
    cb = sa.fine_coverage_bins(fc_c[valid]).astype(np.int64)
    mb = sa.fine_coverage_bins(fc_m[valid]).astype(np.int64)
    keys = cb * 5 + mb
    uniq, counts = np.unique(keys, return_counts=True)
    for key, cnt in zip(uniq.tolist(), counts.tolist(), strict=True):
        store[int(key)] = store.get(int(key), 0) + int(cnt)


def decode_contingency_30(store: dict[int, int]) -> pd.DataFrame:
    rows = []
    labels = sa.COVER_BIN_LABELS
    for key, n in store.items():
        mb_i = key % 5
        cb_i = (key // 5) % 5
        g_i = (key // 25) % 2
        region = key // 50
        rows.append({
            "region": region, "g_class": g_i,
            "cover_c_bin": labels[cb_i], "cover_m_bin": labels[mb_i],
            "n": n,
        })
    return pd.DataFrame(rows)


def decode_contingency_10(store: dict[int, int]) -> pd.DataFrame:
    rows = []
    labels = sa.COVER_BIN_LABELS
    for key, n in store.items():
        rows.append({
            "cover_c_bin": labels[key // 5],
            "cover_m_bin": labels[key % 5],
            "n": n,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 30 m support
# ---------------------------------------------------------------------------

@dataclass
class SupportResult:
    region_table: pd.DataFrame
    distance_table: pd.DataFrame
    patch_class_table: pd.DataFrame
    contingency: pd.DataFrame
    patch_cover: pd.DataFrame
    cell_table: pd.DataFrame
    metadata: dict[str, Any]
    # Issue #18 R1: None unless --independent-regions was used.
    region_independent_table: pd.DataFrame | None = None
    region_attribution_table: pd.DataFrame | None = None
    region_validation_table: pd.DataFrame | None = None


DOMAIN_STATUSES = (
    "KEEP_MAINLAND_COASTAL",
    "KEEP_ISLAND_COASTAL",
    "PROVISIONAL_UNRESOLVED",
)


def load_w10_cells() -> gpd.GeoDataFrame:
    """W10 domain cells from the frozen v1 candidate manifest.

    EXCLUDE_DOMAIN_ARTIFACT cells are dropped from the analysis domain;
    PROVISIONAL_UNRESOLVED cells (Issue #17, owner sign-off pending) are
    retained and flagged so downstream tables can separate them.
    """
    frame = pd.read_csv(CELLS_CSV)
    membership = pd.read_csv(
        MANIFEST_DIR / "china_coastal_cells_v1_candidate.csv"
    )[["cell_id", "membership_v1_candidate"]]
    frame = frame.merge(membership, on="cell_id", how="left")
    frame = frame[
        frame["membership_v1_candidate"].isin(DOMAIN_STATUSES)
    ].copy()
    frame["cell_idx"] = np.arange(len(frame))
    frame["is_provisional"] = (
        frame["membership_v1_candidate"] == "PROVISIONAL_UNRESOLVED"
    ).astype("int32")
    return gpd.GeoDataFrame(
        frame,
        geometry=[
            box(int(r.col) * 10000, int(r.row) * 10000,
                (int(r.col) + 1) * 10000, (int(r.row) + 1) * 10000)
            for r in frame.itertuples()
        ],
        crs=CHINA_ALBERS_CRS,
    )


def run_30m_support(
    cmsa_a: gpd.GeoDataFrame,
    cmssm_a: gpd.GeoDataFrame,
    cells_a: gpd.GeoDataFrame,
    stripe: tuple[int, int] | None = None,
    prov_a: gpd.GeoDataFrame | None = None,
) -> SupportResult:
    with rasterio.open(GEODATA_TIF) as ds:
        return _run_30m_support(
            ds, cmsa_a, cmssm_a, cells_a, stripe, prov_a
        )


def _run_30m_support(
    ds: rasterio.io.DatasetReader,
    cmsa_a: gpd.GeoDataFrame,
    cmssm_a: gpd.GeoDataFrame,
    cells_a: gpd.GeoDataFrame,
    stripe: tuple[int, int] | None,
    prov_a: gpd.GeoDataFrame | None = None,
) -> SupportResult:
    x0_g, ytop_g = ds.transform.c, ds.transform.f
    overview = ds.overviews(1)[-1]
    # NEAREST (not the default average): the overview is only a cheap
    # block-hit mask; averaging can round an isolated positive pixel to
    # zero and silently drop GEODATA-only meadows.
    small = ds.read(
        1, out_shape=(ds.height // overview, ds.width // overview),
        resampling=Resampling.nearest,
    )
    rows = np.flatnonzero(small.any(axis=1))
    cols = np.flatnonzero(small.any(axis=0))
    g_r0, g_r1 = int(rows[0]) * overview, min(
        ds.height, (int(rows[-1]) + 1) * overview
    )
    g_c0, g_c1 = int(cols[0]) * overview, min(
        ds.width, (int(cols[-1]) + 1) * overview
    )
    g_bounds = (
        x0_g + g_c0 * 30.0, ytop_g - g_r1 * 30.0,
        x0_g + g_c1 * 30.0, ytop_g - g_r0 * 30.0,
    )
    fb = gpd.GeoSeries(
        list(cmsa_a.geometry) + list(cmssm_a.geometry), crs=cmsa_a.crs
    ).total_bounds
    u_minx = min(g_bounds[0], fb[0]) - 480.0
    u_miny = min(g_bounds[1], fb[1]) - 480.0
    u_maxx = max(g_bounds[2], fb[2]) + 480.0
    u_maxy = max(g_bounds[3], fb[3]) + 480.0
    # Snap to the native GEODATA lattice.
    s_col = int(np.floor((u_minx - x0_g) / 30.0))
    s_row = int(np.floor((ytop_g - u_maxy) / 30.0))
    e_col = int(np.ceil((u_maxx - x0_g) / 30.0))
    e_row = int(np.ceil((ytop_g - u_miny) / 30.0))
    n_cols, n_rows = e_col - s_col, e_row - s_row
    metadata = {
        "support": "30m GEODATA native grid (Krasovsky Albers); comparison support only",
        "global_start_col": s_col, "global_start_row": s_row,
        "n_cols": n_cols, "n_rows": n_rows, "pixel_m": 30,
        "pixel_area_m2": 900.0,
    }

    acc_region = KeyedSums(("region",), SUM_FIELDS_30)
    acc_dist = KeyedSums(("region", "dist_bin"), SUM_FIELDS_30)
    acc_patch = KeyedSums(("region", "patch_c_bin", "patch_m_bin"), SUM_FIELDS_30)
    cont_store: dict[int, int] = {}
    acc_cell = KeyedSums(("cell_idx",), SUM_FIELDS_30)
    # Independent attribution accumulators (Issue #18 R1).
    acc_region_indep = KeyedSums(("region",), SUM_FIELDS_30)
    acc_attr_indep = KeyedSums(
        ("method", "region"), ("pixels", "g", "bc", "bm")
    )
    acc_valid_indep = KeyedSums(
        ("prod_region", "indep_region"),
        ("pixels", "g", "bc", "bm", "fine_pixels", "fine_agree"),
    )
    patch_store: dict[tuple[str, int], dict[str, float]] = {}
    patch_area_c = cmsa_a.groupby("patch_id_c").geometry.apply(
        lambda s: s.area.sum()
    )
    patch_area_m = cmssm_a.groupby("patch_id_m").geometry.apply(
        lambda s: s.area.sum()
    )
    tree_c, tree_m = cmsa_a.sindex, cmssm_a.sindex
    lut_c = patch_region_lookup(cmsa_a, "patch_id_c")
    lut_m = patch_region_lookup(cmssm_a, "patch_id_m")
    row_starts: Any = range(s_row, e_row, BLOCK_PIXELS)
    if stripe is not None:
        row_starts = [
            br for br in range(s_row, e_row, BLOCK_PIXELS)
            if stripe[0] <= br < stripe[1]
        ]

    for br in row_starts:
        for bc in range(s_col, e_col, BLOCK_PIXELS):
            bh = min(BLOCK_PIXELS, e_row - br)
            bw = min(BLOCK_PIXELS, e_col - bc)
            hr0, hc0 = br - HALO_30M, bc - HALO_30M
            hh, hw = bh + 2 * HALO_30M, bw + 2 * HALO_30M
            ox = x0_g + hc0 * 30.0
            oyn = ytop_g - hr0 * 30.0
            halo_bounds = (
                ox, oyn - hh * 30.0, ox + hw * 30.0, oyn
            )
            halo_box = box(*halo_bounds)

            # Cheap STRtree + overview pre-filter so empty blocks never
            # pay for an sjoin or a GEODATA read.
            ov = overview
            or0 = max(hr0 // ov, 0)
            oc0 = max(hc0 // ov, 0)
            or1 = min(small.shape[0], (hr0 + hh) // ov + 1)
            oc1 = min(small.shape[1], (hc0 + hw) // ov + 1)
            g_hit = bool(small[or0:or1, oc0:oc1].any())
            c_hit = bool(len(tree_c.intersection(halo_bounds)))
            m_hit = bool(len(tree_m.intersection(halo_bounds)))
            if not (g_hit or c_hit or m_hit):
                continue
            g_arr = np.zeros((hh, hw), dtype="uint8")
            if g_hit:
                wr0, wc0 = max(hr0, 0), max(hc0, 0)
                wr1, wc1 = min(hr0 + hh, ds.height), min(hc0 + hw, ds.width)
                if wr1 > wr0 and wc1 > wc0:
                    win = rasterio.windows.Window(wc0, wr0, wc1 - wc0, wr1 - wr0)
                    part = ds.read(1, window=win) == 1
                    g_arr[wr0 - hr0:wr1 - hr0, wc0 - hc0:wc1 - hc0] = part

            if c_hit:
                cov_c, det_c = exact_cover_block(
                    halo_box, cmsa_a, "patch_id_c", ox, oyn, 30.0, hh, hw
                )
            else:
                cov_c = np.zeros((hh, hw), dtype=np.float64)
                det_c = pd.DataFrame(
                    columns=["row", "col", "patch_id_c", "area_m2"]
                )
            if m_hit:
                cov_m, det_m = exact_cover_block(
                    halo_box, cmssm_a, "patch_id_m", ox, oyn, 30.0, hh, hw
                )
            else:
                cov_m = np.zeros((hh, hw), dtype=np.float64)
                det_m = pd.DataFrame(
                    columns=["row", "col", "patch_id_m", "area_m2"]
                )
            if g_arr.max() == 0 and cov_c.max() == 0 and cov_m.max() == 0:
                continue
            fc_c, fc_m = cov_c / 900.0, cov_m / 900.0
            b_c, b_m = fc_c >= 0.5, fc_m >= 0.5
            d_any = signed_distance(
                g_arr.astype(bool) | b_c | b_m, 30.0
            )
            dgc = (g_arr.astype(bool) != b_c)
            dgm = (g_arr.astype(bool) != b_m)
            dcm = b_c != b_m

            # Largest source-patch area touching each pixel.
            pa_c = _max_patch_area(det_c, patch_area_c, "patch_id_c", (hh, hw))
            pa_m = _max_patch_area(det_m, patch_area_m, "patch_id_m", (hh, hw))

            sl = (slice(HALO_30M, HALO_30M + bh),
                  slice(HALO_30M, HALO_30M + bw))
            keep = np.abs(d_any[sl]) <= BOUNDARY_MAX_M
            # Region labels from the *individual simple* CM-SSM polygons
            # (province code carried per feature): exact union semantics
            # inside the halo at a fraction of the dissolve/sjoin cost.
            region_arr = region_label_block(
                cmsa_a, cmssm_a, "patch_id_c", "patch_id_m",
                lut_c, lut_m, halo_box, ox, oyn, 30.0, hh, hw,
            )
            indep_arr = None
            indep_method = None
            if prov_a is not None:
                indep_arr, indep_method = independent_region_block(
                    prov_a, halo_box, ox, oyn, 30.0, hh, hw,
                    g_arr.astype(bool) | b_c | b_m,
                )
            cell_arr = selected_rasterize(
                cells_a, "cell_idx", halo_box, ox, oyn, 30.0, hh, hw,
                fill=-1,
            )
            # Regional/national ledger over the FULL core (interiors
            # included); boundary/patch tables use the 300 m band only.
            g_full = g_arr[sl]
            fc_c_full, fc_m_full = fc_c[sl], fc_m[sl]
            bc_full, bm_full = fc_c_full >= 0.5, fc_m_full >= 0.5
            gb_full = g_full.astype(bool)
            full_arrays = (
                np.ones(g_full.shape, dtype=np.float64),
                g_full.astype(np.float64),
                fc_c_full, fc_m_full,
                (gb_full & bc_full).astype(np.float64),
                (gb_full & bm_full).astype(np.float64),
                np.minimum(fc_c_full, fc_m_full),
                bc_full.astype(np.float64),
                bm_full.astype(np.float64),
                (bc_full & bm_full).astype(np.float64),
                dgc[sl].astype(np.float64),
                dgm[sl].astype(np.float64),
                dcm[sl].astype(np.float64),
                ((~gb_full) & (fc_c_full > PURE_LO)
                 & (fc_c_full < PURE_HI)).astype(np.float64),
                ((~gb_full) & (fc_m_full > PURE_LO)
                 & (fc_m_full < PURE_HI)).astype(np.float64),
                (gb_full & (fc_c_full > PURE_LO)
                 & (fc_c_full < PURE_HI)).astype(np.float64),
                (gb_full & (fc_m_full > PURE_LO)
                 & (fc_m_full < PURE_HI)).astype(np.float64),
            )
            add_keyed_fast(acc_region, region_arr[sl], full_arrays)
            if indep_arr is not None and indep_method is not None:
                add_keyed_fast(
                    acc_region_indep, indep_arr[sl], full_arrays
                )
                labeled30 = gb_full | bc_full | bm_full
                add_keyed2_fast(
                    acc_attr_indep,
                    (indep_method[sl], indep_arr[sl]),
                    (
                        np.ones(gb_full.shape, dtype=np.float64),
                        gb_full.astype(np.float64),
                        bc_full.astype(np.float64),
                        bm_full.astype(np.float64),
                    ),
                    valid=labeled30,
                )
                prod_core = region_arr[sl]
                fine30 = bc_full | bm_full
                agree30 = (
                    fine30
                    & (prod_core > 0)
                    & (indep_arr[sl] > 0)
                    & (prod_core == indep_arr[sl])
                )
                add_keyed2_fast(
                    acc_valid_indep,
                    (prod_core, indep_arr[sl]),
                    (
                        np.ones(gb_full.shape, dtype=np.float64),
                        gb_full.astype(np.float64),
                        bc_full.astype(np.float64),
                        bm_full.astype(np.float64),
                        fine30.astype(np.float64),
                        agree30.astype(np.float64),
                    ),
                    valid=labeled30,
                )
                # Independent region keys for all block-keyed tables.
                region_key_core = indep_arr[sl]
            else:
                region_key_core = region_arr[sl]
            # Per-W10-cell full-core ledger for spatial block bootstrap.
            add_keyed_fast(
                acc_cell, cell_arr[sl], full_arrays,
                valid=cell_arr[sl] >= 0,
            )
            region_core = region_key_core[keep]
            gk, ck, mk = g_arr[sl][keep], fc_c[sl][keep], fc_m[sl][keep]
            dgck, dgmk, dcmk = dgc[sl][keep], dgm[sl][keep], dcm[sl][keep]
            dist_k = np.abs(d_any[sl][keep])
            vals = pixel_vectors_30(gk, ck, mk, dgck, dgmk, dcmk)
            key_dist = pd.DataFrame({
                "region": region_core,
                "dist_bin": distance_labels(dist_k),
            })
            key_patch = pd.DataFrame({
                "region": region_core,
                "patch_c_bin": patch_bins(pa_c[sl][keep]),
                "patch_m_bin": patch_bins(pa_m[sl][keep]),
            })
            acc_dist.add(key_dist, vals)
            acc_patch.add(key_patch, vals)
            # H6 contingency over the FULL core within W10 cells
            # (patch interiors included; the band tables stay band-only).
            add_contingency_30_fast(
                cont_store,
                region_key_core, g_arr[sl], fc_c[sl], fc_m[sl],
                cell_arr[sl],
            )
            _accumulate_patch_cover(
                "cmsa", det_c, g_arr, fc_m, cmsa_a, (hh, hw), sl, patch_store
            )
            _accumulate_patch_cover(
                "cmssm", det_m, g_arr, fc_c, cmssm_a, (hh, hw), sl, patch_store
            )

    patch_cover = _patch_cover_frame(patch_store, cmsa_a, cmssm_a)
    cell_table = acc_cell.frame()
    return SupportResult(
        region_table=acc_region.frame(),
        distance_table=acc_dist.frame(),
        patch_class_table=acc_patch.frame(),
        contingency=decode_contingency_30(cont_store),
        patch_cover=patch_cover,
        cell_table=cell_table,
        metadata=metadata,
        region_independent_table=(
            acc_region_indep.frame() if prov_a is not None else None
        ),
        region_attribution_table=(
            acc_attr_indep.frame() if prov_a is not None else None
        ),
        region_validation_table=(
            acc_valid_indep.frame() if prov_a is not None else None
        ),
    )


def _max_patch_area(detail: pd.DataFrame, patch_area: pd.Series,
                    value_col: str, shape: tuple[int, int]) -> np.ndarray[Any, Any]:
    arr = np.zeros(shape, dtype=np.float64)
    if detail.empty:
        return arr
    tmp = detail[["row", "col", value_col]].copy()
    tmp["area"] = tmp[value_col].map(patch_area).to_numpy()
    grouped = tmp.groupby(["row", "col"], sort=False)["area"].max()
    coords = np.array(grouped.index.tolist(), dtype=np.int64).T
    arr[coords[0], coords[1]] = grouped.to_numpy()
    return arr


def _accumulate_patch_cover(
    which: str, detail: pd.DataFrame, g_arr: np.ndarray[Any, Any], other_fc: np.ndarray[Any, Any],
    polys: gpd.GeoDataFrame, halo_shape: tuple[int, int],
    sl: tuple[slice, slice],
    store: dict[tuple[str, int], dict[str, float]],
) -> None:
    if detail.empty:
        return
    bh = sl[0].stop - sl[0].start
    bw = sl[1].stop - sl[1].start
    in_core = (
        (detail["row"] >= HALO_30M) & (detail["row"] < HALO_30M + bh)
        & (detail["col"] >= HALO_30M) & (detail["col"] < HALO_30M + bw)
    )
    detail = detail.loc[in_core]
    if detail.empty:
        return
    pid_col = "patch_id_c" if which == "cmsa" else "patch_id_m"
    gvals = g_arr[detail["row"], detail["col"]]
    ovals = other_fc[detail["row"], detail["col"]]
    grouped = detail.assign(gv=gvals, ov=ovals).groupby(pid_col, sort=False)
    for pid, sub in grouped:
        bucket = store.setdefault(
            (which, int(pid)), {"own_m2": 0.0, "g_m2": 0.0, "other_m2": 0.0}
        )
        bucket["own_m2"] += float(sub["area_m2"].sum())
        bucket["g_m2"] += float((sub["area_m2"] * sub["gv"]).sum())
        bucket["other_m2"] += float((sub["area_m2"] * sub["ov"]).sum())


def _patch_cover_frame(
    store: dict[tuple[str, int], dict[str, float]],
    cmsa_a: gpd.GeoDataFrame, cmssm_a: gpd.GeoDataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    region_c = cmsa_a.groupby("patch_id_c")["region_code"].first()
    region_m = cmssm_a.groupby("patch_id_m")["region_code"].first()
    area_c = cmsa_a.groupby("patch_id_c").geometry.apply(lambda s: s.area.sum())
    area_m = cmssm_a.groupby("patch_id_m").geometry.apply(lambda s: s.area.sum())
    for (which, pid), v in store.items():
        reg = region_c if which == "cmsa" else region_m
        area = area_c if which == "cmsa" else area_m
        reg_code = int(reg.loc[pid]) if pid in reg.index else 0
        patch_area = float(area.loc[pid]) if pid in area.index else np.nan
        rows.append({
            "support": "30m",
            "product": which,
            "patch_id": pid,
            "region": region_name(reg_code),
            "patch_area_m2": patch_area,
            "own_intersect_m2": v["own_m2"],
            "geodata_cover_m2": v["g_m2"],
            "other_fine_fractional_m2": v["other_m2"],
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 10 m support (CMSA vs CM-SSM only)
# ---------------------------------------------------------------------------

def run_10m_support(
    cmsa_b: gpd.GeoDataFrame,
    cmssm_b: gpd.GeoDataFrame,
    cells_b: gpd.GeoDataFrame,
    stripe: tuple[int, int] | None = None,
    prov_b: gpd.GeoDataFrame | None = None,
) -> SupportResult:
    fb = gpd.GeoSeries(
        list(cmsa_b.geometry) + list(cmssm_b.geometry), crs=cmsa_b.crs
    ).total_bounds
    ox = np.floor((fb[0] - 400.0) / 10.0) * 10.0
    oyn = np.ceil((fb[3] + 400.0) / 10.0) * 10.0
    n_cols = int(round((np.ceil((fb[2] + 400.0) / 10.0) * 10.0 - ox) / 10.0))
    n_rows = int(round((oyn - np.floor((fb[1] - 400.0) / 10.0) * 10.0) / 10.0))
    metadata = {
        "support": (
            "10m PROJECT comparison lattice (China Albers, origin 0,0); "
            "not the CMSA native pixel grid; CMSA vs CM-SSM only"
        ),
        "origin_x": float(ox), "origin_y_north": float(oyn),
        "n_cols": n_cols, "n_rows": n_rows, "pixel_m": 10,
        "pixel_area_m2": 100.0,
    }
    acc_region = KeyedSums(("region",), SUM_FIELDS_10)
    acc_dist = KeyedSums(("region", "dist_bin"), SUM_FIELDS_10)
    acc_patch = KeyedSums(("region", "patch_c_bin", "patch_m_bin"), SUM_FIELDS_10)
    cont_store: dict[int, int] = {}
    acc_cell = KeyedSums(("cell_idx",), SUM_FIELDS_10)
    acc_region_indep = KeyedSums(("region",), SUM_FIELDS_10)
    acc_attr_indep = KeyedSums(
        ("method", "region"), ("pixels", "bc", "bm")
    )
    acc_valid_indep = KeyedSums(
        ("prod_region", "indep_region"),
        ("pixels", "fine_pixels", "fine_agree"),
    )
    patch_store: dict[tuple[str, int], dict[str, float]] = {}
    patch_area_c = cmsa_b.groupby("patch_id_c").geometry.apply(
        lambda s: s.area.sum()
    )
    patch_area_m = cmssm_b.groupby("patch_id_m").geometry.apply(
        lambda s: s.area.sum()
    )
    tree_c, tree_m = cmsa_b.sindex, cmssm_b.sindex
    lut_c = patch_region_lookup(cmsa_b, "patch_id_c")
    lut_m = patch_region_lookup(cmssm_b, "patch_id_m")
    row_starts: Any = range(0, n_rows, BLOCK_PIXELS)
    if stripe is not None:
        row_starts = [
            br for br in range(0, n_rows, BLOCK_PIXELS)
            if stripe[0] <= br < stripe[1]
        ]

    for br in row_starts:
        for bc in range(0, n_cols, BLOCK_PIXELS):
            bh = min(BLOCK_PIXELS, n_rows - br)
            bw = min(BLOCK_PIXELS, n_cols - bc)
            hr0, hc0 = br - HALO_10M, bc - HALO_10M
            hh, hw = bh + 2 * HALO_10M, bw + 2 * HALO_10M
            hx = float(ox + hc0 * 10.0)
            hyn = float(oyn - hr0 * 10.0)
            halo_bounds = (hx, hyn - hh * 10.0, hx + hw * 10.0, hyn)
            halo_box = box(*halo_bounds)

            c_hit = bool(len(tree_c.intersection(halo_bounds)))
            m_hit = bool(len(tree_m.intersection(halo_bounds)))
            if not (c_hit or m_hit):
                continue
            if c_hit:
                cov_c, det_c = exact_cover_block(
                    halo_box, cmsa_b, "patch_id_c", hx, hyn, 10.0, hh, hw
                )
            else:
                cov_c = np.zeros((hh, hw), dtype=np.float64)
                det_c = pd.DataFrame(
                    columns=["row", "col", "patch_id_c", "area_m2"]
                )
            if m_hit:
                cov_m, det_m = exact_cover_block(
                    halo_box, cmssm_b, "patch_id_m", hx, hyn, 10.0, hh, hw
                )
            else:
                cov_m = np.zeros((hh, hw), dtype=np.float64)
                det_m = pd.DataFrame(
                    columns=["row", "col", "patch_id_m", "area_m2"]
                )
            if cov_c.max() == 0 and cov_m.max() == 0:
                continue
            fc_c, fc_m = cov_c / 100.0, cov_m / 100.0
            b_c, b_m = fc_c >= 0.5, fc_m >= 0.5
            d_any = signed_distance(b_c | b_m, 10.0)
            dcm = b_c != b_m
            pa_c = _max_patch_area(det_c, patch_area_c, "patch_id_c", (hh, hw))
            pa_m = _max_patch_area(det_m, patch_area_m, "patch_id_m", (hh, hw))

            sl = (slice(HALO_10M, HALO_10M + bh),
                  slice(HALO_10M, HALO_10M + bw))
            keep = np.abs(d_any[sl]) <= BOUNDARY_MAX_M
            region_arr = region_label_block(
                cmsa_b, cmssm_b, "patch_id_c", "patch_id_m",
                lut_c, lut_m, halo_box, hx, hyn, 10.0, hh, hw,
            )
            indep_arr = None
            indep_method = None
            if prov_b is not None:
                indep_arr, indep_method = independent_region_block(
                    prov_b, halo_box, hx, hyn, 10.0, hh, hw, b_c | b_m,
                )
            cell_arr = selected_rasterize(
                cells_b, "cell_idx", halo_box, hx, hyn, 10.0, hh, hw,
                fill=-1,
            )
            # Regional/national ledger over the FULL core (interiors
            # included); boundary/patch tables use the 300 m band only.
            fc_c_full, fc_m_full = fc_c[sl], fc_m[sl]
            bc_full, bm_full = fc_c_full >= 0.5, fc_m_full >= 0.5
            full_arrays = (
                np.ones(bc_full.shape, dtype=np.float64),
                fc_c_full, fc_m_full,
                np.minimum(fc_c_full, fc_m_full),
                bc_full.astype(np.float64),
                bm_full.astype(np.float64),
                (bc_full & bm_full).astype(np.float64),
                dcm[sl].astype(np.float64),
            )
            add_keyed_fast(acc_region, region_arr[sl], full_arrays)
            if indep_arr is not None and indep_method is not None:
                add_keyed_fast(
                    acc_region_indep, indep_arr[sl], full_arrays
                )
                labeled10 = bc_full | bm_full
                add_keyed2_fast(
                    acc_attr_indep,
                    (indep_method[sl], indep_arr[sl]),
                    (
                        np.ones(bc_full.shape, dtype=np.float64),
                        bc_full.astype(np.float64),
                        bm_full.astype(np.float64),
                    ),
                    valid=labeled10,
                )
                prod_core = region_arr[sl]
                agree10 = (
                    labeled10
                    & (prod_core > 0)
                    & (indep_arr[sl] > 0)
                    & (prod_core == indep_arr[sl])
                )
                add_keyed2_fast(
                    acc_valid_indep,
                    (prod_core, indep_arr[sl]),
                    (
                        np.ones(bc_full.shape, dtype=np.float64),
                        labeled10.astype(np.float64),
                        agree10.astype(np.float64),
                    ),
                    valid=labeled10,
                )
                region_key_core = indep_arr[sl]
            else:
                region_key_core = region_arr[sl]
            add_keyed_fast(
                acc_cell, cell_arr[sl], full_arrays,
                valid=cell_arr[sl] >= 0,
            )
            region_core = region_key_core[keep]
            ck, mk = fc_c[sl][keep], fc_m[sl][keep]
            dcmk = dcm[sl][keep]
            vals = pixel_vectors_10(ck, mk, dcmk)
            acc_dist.add(
                pd.DataFrame({
                    "region": region_core,
                    "dist_bin": distance_labels(np.abs(d_any[sl][keep])),
                }),
                vals,
            )
            acc_patch.add(
                pd.DataFrame({
                    "region": region_core,
                    "patch_c_bin": patch_bins(pa_c[sl][keep]),
                    "patch_m_bin": patch_bins(pa_m[sl][keep]),
                }),
                vals,
            )
            # Full-core CMSA vs CM-SSM cover contingency within cells.
            add_contingency_10_fast(
                cont_store, fc_c[sl], fc_m[sl], cell_arr[sl]
            )

            _accumulate_patch_cover_10(
                "cmsa", det_c, fc_m, (hh, hw), sl, patch_store
            )
            _accumulate_patch_cover_10(
                "cmssm", det_m, fc_c, (hh, hw), sl, patch_store
            )

    patch_rows: list[dict[str, Any]] = []
    region_c = cmsa_b.groupby("patch_id_c")["region_code"].first()
    region_m = cmssm_b.groupby("patch_id_m")["region_code"].first()
    area_c = cmsa_b.groupby("patch_id_c").geometry.apply(lambda s: s.area.sum())
    area_m = cmssm_b.groupby("patch_id_m").geometry.apply(lambda s: s.area.sum())
    for (which, pid), v in patch_store.items():
        reg: pd.Series[Any] = region_c if which == "cmsa" else region_m
        area: pd.Series[Any] = area_c if which == "cmsa" else area_m
        reg_code = int(reg.loc[pid]) if pid in reg.index else 0
        patch_area = float(area.loc[pid]) if pid in area.index else np.nan
        patch_rows.append({
            "support": "10m",
            "product": which,
            "patch_id": pid,
            "region": region_name(reg_code),
            "patch_area_m2": patch_area,
            "own_intersect_m2": v["own_m2"],
            "other_fine_fractional_m2": v["other_m2"],
            "geodata_cover_m2": np.nan,
        })
    cell_table = acc_cell.frame()
    return SupportResult(
        region_table=acc_region.frame(),
        distance_table=acc_dist.frame(),
        patch_class_table=acc_patch.frame(),
        contingency=decode_contingency_10(cont_store),
        patch_cover=pd.DataFrame(patch_rows),
        cell_table=cell_table,
        metadata=metadata,
        region_independent_table=(
            acc_region_indep.frame() if prov_b is not None else None
        ),
        region_attribution_table=(
            acc_attr_indep.frame() if prov_b is not None else None
        ),
        region_validation_table=(
            acc_valid_indep.frame() if prov_b is not None else None
        ),
    )


def _accumulate_patch_cover_10(
    which: str, detail: pd.DataFrame, other_fc: np.ndarray[Any, Any],
    halo_shape: tuple[int, int], sl: tuple[slice, slice],
    store: dict[tuple[str, int], dict[str, float]],
) -> None:
    bh = sl[0].stop - sl[0].start
    bw = sl[1].stop - sl[1].start
    in_core = (
        (detail["row"] >= HALO_10M) & (detail["row"] < HALO_10M + bh)
        & (detail["col"] >= HALO_10M) & (detail["col"] < HALO_10M + bw)
    )
    detail = detail.loc[in_core]
    if detail.empty:
        return
    pid_col = "patch_id_c" if which == "cmsa" else "patch_id_m"
    ovals = other_fc[detail["row"], detail["col"]]
    grouped = detail.assign(ov=ovals).groupby(pid_col, sort=False)
    for pid, sub in grouped:
        bucket = store.setdefault(
            (which, pid), {"own_m2": 0.0, "other_m2": 0.0, "g_m2": 0.0}
        )
        bucket["own_m2"] += float(sub["area_m2"].sum())
        bucket["other_m2"] += float((sub["area_m2"] * sub["ov"]).sum())


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Parallel (fork) stripe execution
# ---------------------------------------------------------------------------

N_WORKERS = int(os.environ.get("SPARTINA_AUDIT_WORKERS", "8"))

# Per-call worker context populated in the parent and inherited via fork
# (never sent through pickle: national frames and STRtrees are large).
_W30: dict[str, Any] = {}
_W10: dict[str, Any] = {}


def _30m_block_rows(
    cmsa_a: gpd.GeoDataFrame, cmssm_a: gpd.GeoDataFrame
) -> list[int]:
    with rasterio.open(GEODATA_TIF) as ds:
        x0_g, ytop_g = ds.transform.c, ds.transform.f
        overview = ds.overviews(1)[-1]
        small = ds.read(
            1, out_shape=(ds.height // overview, ds.width // overview),
            resampling=Resampling.nearest,
        )
        rows = np.flatnonzero(small.any(axis=1))
        cols = np.flatnonzero(small.any(axis=0))
        g_r0 = int(rows[0]) * overview
        g_r1 = min(ds.height, (int(rows[-1]) + 1) * overview)
        g_c0 = int(cols[0]) * overview
        g_c1 = min(ds.width, (int(cols[-1]) + 1) * overview)
        g_bounds = (
            x0_g + g_c0 * 30.0, ytop_g - g_r1 * 30.0,
            x0_g + g_c1 * 30.0, ytop_g - g_r0 * 30.0,
        )
    fb = gpd.GeoSeries(
        list(cmsa_a.geometry) + list(cmssm_a.geometry), crs=cmsa_a.crs
    ).total_bounds
    u_maxy = max(g_bounds[3], fb[3]) + 480.0
    u_miny = min(g_bounds[1], fb[1]) - 480.0
    s_row = int(np.floor((ytop_g - u_maxy) / 30.0))
    e_row = int(np.ceil((ytop_g - u_miny) / 30.0))
    return list(range(s_row, e_row, BLOCK_PIXELS))


def _10m_block_rows(
    cmsa_b: gpd.GeoDataFrame, cmssm_b: gpd.GeoDataFrame
) -> tuple[list[int], int]:
    fb = gpd.GeoSeries(
        list(cmsa_b.geometry) + list(cmssm_b.geometry), crs=cmsa_b.crs
    ).total_bounds
    oyn = np.ceil((fb[3] + 400.0) / 10.0) * 10.0
    n_rows = int(round(
        (oyn - np.floor((fb[1] - 400.0) / 10.0) * 10.0) / 10.0
    ))
    return list(range(0, n_rows, BLOCK_PIXELS)), n_rows


def _make_stripes(row_starts: list[int]) -> list[tuple[int, int]]:
    n_workers = max(1, min(N_WORKERS, len(row_starts)))
    # ~4 chunks per worker balances dense/sparse row bands.
    n_chunks = min(len(row_starts), n_workers * 4)
    bounds = np.linspace(0, len(row_starts), n_chunks + 1, dtype=int)
    stripes: list[tuple[int, int]] = []
    for i in range(n_chunks):
        lo = int(row_starts[bounds[i]])
        hi = (
            int(row_starts[bounds[i + 1]])
            if i + 1 < n_chunks else int(row_starts[-1]) + BLOCK_PIXELS
        )
        stripes.append((lo, hi))
    return stripes


def _worker_30(stripe: tuple[int, int]) -> SupportResult:
    return run_30m_support(
        _W30["cmsa"], _W30["cmssm"], _W30["cells"], stripe=stripe,
        prov_a=_W30.get("prov"),
    )


def _worker_10(stripe: tuple[int, int]) -> SupportResult:
    return run_10m_support(
        _W10["cmsa"], _W10["cmssm"], _W10["cells"], stripe=stripe,
        prov_b=_W10.get("prov"),
    )


def _merge_results(results: list[SupportResult]) -> SupportResult:
    region = pd.concat(
        [r.region_table for r in results], ignore_index=True
    )
    distance = pd.concat(
        [r.distance_table for r in results], ignore_index=True
    )
    patch_class = pd.concat(
        [r.patch_class_table for r in results], ignore_index=True
    )
    contingency = pd.concat(
        [r.contingency for r in results], ignore_index=True
    )
    cells = pd.concat(
        [r.cell_table for r in results], ignore_index=True
    )
    patch_cover = pd.concat(
        [r.patch_cover for r in results], ignore_index=True
    )

    def sum_by(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        return frame.groupby(keys, as_index=False, sort=False).sum(
            numeric_only=True
        )

    region_k = ["region"]
    distance_k = ["region", "dist_bin"]
    patch_k = ["region", "patch_c_bin", "patch_m_bin"]
    cont_k = [c for c in ("region", "g_class", "cover_c_bin", "cover_m_bin")
              if c in contingency.columns]
    region_f = sum_by(region, region_k)
    distance_f = sum_by(distance, distance_k)
    patch_f = sum_by(patch_class, patch_k)
    cont_f = sum_by(contingency, cont_k)
    cells_f = sum_by(cells, ["cell_idx"])
    pc_keys = ["support", "product", "patch_id"]
    pc_sum = patch_cover.groupby(pc_keys, as_index=False, sort=False).sum(
        numeric_only=True
    )
    pc_first = patch_cover[
        pc_keys + ["region", "patch_area_m2"]
    ].drop_duplicates(pc_keys)
    patch_cover_f = pc_first.merge(
        pc_sum[pc_keys + [
            c for c in pc_sum.columns
            if c.endswith("_m2") and c != "patch_area_m2"
        ]],
        on=pc_keys, how="outer",
    )
    def optional_sum(field: str, keys: list[str]) -> pd.DataFrame | None:
        frames = [
            getattr(r, field) for r in results
            if getattr(r, field) is not None
        ]
        if not frames:
            return None
        return sum_by(
            pd.concat(frames, ignore_index=True), keys
        )

    return SupportResult(
        region_table=region_f,
        distance_table=distance_f,
        patch_class_table=patch_f,
        contingency=cont_f,
        patch_cover=patch_cover_f,
        cell_table=cells_f,
        metadata=results[0].metadata,
        region_independent_table=optional_sum(
            "region_independent_table", ["region"]
        ),
        region_attribution_table=optional_sum(
            "region_attribution_table", ["method", "region"]
        ),
        region_validation_table=optional_sum(
            "region_validation_table", ["prod_region", "indep_region"]
        ),
    )


def parallel_30(
    cmsa_a: gpd.GeoDataFrame,
    cmssm_a: gpd.GeoDataFrame,
    cells_a: gpd.GeoDataFrame,
    prov_a: gpd.GeoDataFrame | None = None,
) -> SupportResult:
    if N_WORKERS <= 1:
        return run_30m_support(
            cmsa_a, cmssm_a, cells_a, prov_a=prov_a
        )
    row_starts = _30m_block_rows(cmsa_a, cmssm_a)
    stripes = _make_stripes(row_starts)
    _W30.update(cmsa=cmsa_a, cmssm=cmssm_a, cells=cells_a, prov=prov_a)
    ctx = mp.get_context("fork")
    with ctx.Pool(N_WORKERS) as pool:
        results = pool.map(_worker_30, stripes)
    out = _merge_results(results)
    print(
        f"30m support merged from {len(results)} stripes "
        f"({N_WORKERS} workers)", flush=True,
    )
    return out


def parallel_10(
    cmsa_b: gpd.GeoDataFrame,
    cmssm_b: gpd.GeoDataFrame,
    cells_b: gpd.GeoDataFrame,
    prov_b: gpd.GeoDataFrame | None = None,
) -> SupportResult:
    if N_WORKERS <= 1:
        return run_10m_support(
            cmsa_b, cmssm_b, cells_b, prov_b=prov_b
        )
    row_starts, _ = _10m_block_rows(cmsa_b, cmssm_b)
    stripes = _make_stripes(row_starts)
    _W10.update(cmsa=cmsa_b, cmssm=cmssm_b, cells=cells_b, prov=prov_b)
    ctx = mp.get_context("fork")
    with ctx.Pool(N_WORKERS) as pool:
        results = pool.map(_worker_10, stripes)
    out = _merge_results(results)
    print(
        f"10m support merged from {len(results)} stripes "
        f"({N_WORKERS} workers)", flush=True,
    )
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--independent-regions", action="store_true",
        help=(
            "Issue #18 R1: additionally produce source-independent "
            "(Natural Earth admin-1) region attribution and key all "
            "regional tables on it; product-derived region tables are "
            "retained separately for before/after comparison."
        ),
    )
    args = parser.parse_args(argv)
    DERIVED.mkdir(parents=True, exist_ok=True)
    FIG_WORK.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_ANALYSIS.mkdir(parents=True, exist_ok=True)

    cmsa_raw = gpd.read_file(CMSA_SHP, engine="pyogrio")
    cmsa_gc0 = int((cmsa_raw["gridcode"] == 0).sum())
    cmsa = cmsa_raw[cmsa_raw["gridcode"] == GRIDCODE_POSITIVE].copy()
    cmssm = gpd.read_file(CMSSM_SHP, engine="pyogrio")

    cmsa_fix, cmsa_audit = make_valid_copy("CMSA_2020_gridcode2", cmsa)
    cmssm_fix, cmssm_audit = make_valid_copy("CM_SSM_2020", cmssm)

    # Patch identity.
    cmsa_fix["patch_id_c"] = cmsa_fix.groupby("Id", sort=True).ngroup().astype("int64")
    cmssm_fix["patch_id_m"] = np.arange(len(cmssm_fix), dtype=np.int64)

    # Region codes: native for CM-SSM; nearest CM-SSM province for CMSA.
    cmap = region_code_map()
    cmssm_fix["region_code"] = cmssm_fix["name"].map(cmap).astype(int)
    cmssm_albers = cmssm_fix.to_crs(CHINA_ALBERS_CRS)
    cmsa_rep = gpd.GeoDataFrame(
        geometry=cmsa_fix.geometry.representative_point(), crs=cmsa_fix.crs
    ).to_crs(CHINA_ALBERS_CRS)
    # Point-in-province via the *individual simple* CM-SSM polygons
    # (prepared-geometry bulk join): equivalent to intersecting the
    # dissolved provinces but orders of magnitude faster.
    inside = gpd.sjoin(
        cmsa_rep,
        cmssm_albers[["region_code", "geometry"]],
        how="left", predicate="intersects",
    )
    inside = inside[~inside.index.duplicated(keep="first")]
    region_code = pd.to_numeric(
        inside["region_code"], errors="coerce"
    ).fillna(0).astype("int64")
    region_dist = pd.Series(
        np.where(region_code.to_numpy() > 0, 0.0, np.nan),
        index=cmsa_rep.index, dtype="float64",
    )
    missing_idx = region_code.index[region_code == 0]
    if len(missing_idx) > 0:
        # Points outside every province: nearest province = province of
        # the nearest individual CM-SSM polygon; distance to that
        # polygon equals distance to the province union.
        ref_geoms = cmssm_albers.geometry.to_numpy()
        ref_codes = cmssm_albers["region_code"].to_numpy()
        rtree = shapely.STRtree(ref_geoms)
        pts = cmsa_rep.loc[missing_idx].geometry.to_numpy()
        near_idx = np.asarray(rtree.nearest(pts))
        region_code.loc[missing_idx] = ref_codes[near_idx].astype("int64")
        region_dist.loc[missing_idx] = [
            float(pt.distance(ref_geoms[int(j)]))
            for pt, j in zip(pts, near_idx, strict=True)
        ]
    cmsa_fix["region_code"] = region_code.to_numpy()
    cmsa_fix["region_nearest_m"] = region_dist.to_numpy()

    cells = load_w10_cells()

    with rasterio.open(GEODATA_TIF) as ds:
        crs_a = ds.crs
        crs_a_wkt = ds.crs.to_wkt()
        cmsa_a = cmsa_fix.to_crs(crs_a)
        cmssm_a = cmssm_fix.to_crs(crs_a)
        cells_a = cells.to_crs(crs_a)
        # Materialize every nationwide STRtree exactly once; the
        # fork-based stripe workers inherit these frames and indexes.
        for frame in (cmsa_a, cmssm_a, cells_a):
            _ = frame.sindex

    cmsa_b = cmsa_fix.to_crs(CHINA_ALBERS_CRS)
    for frame in (cmsa_b, cmssm_albers, cells):
        _ = frame.sindex

    prov_a = prov_b = None
    if args.independent_regions:
        print("loading Natural Earth admin-1 provinces ...", flush=True)
        with rasterio.open(GEODATA_TIF) as ds_prov:
            prov_a = load_coastal_provinces(ds_prov.crs)
        prov_b = load_coastal_provinces(CHINA_ALBERS_CRS)
        for frame in (prov_a, prov_b):
            _ = frame.sindex

    r30 = parallel_30(cmsa_a, cmssm_a, cells_a, prov_a=prov_a)
    r10 = parallel_10(cmsa_b, cmssm_albers, cells, prov_b=prov_b)

    for name, frame in (
        ("s30_region", r30.region_table),
        ("s30_distance", r30.distance_table),
        ("s30_patch_class", r30.patch_class_table),
        ("s30_contingency", r30.contingency),
        ("s30_patch_cover", r30.patch_cover),
        ("s30_cells", r30.cell_table),
        ("s10_region", r10.region_table),
        ("s10_distance", r10.distance_table),
        ("s10_patch_class", r10.patch_class_table),
        ("s10_contingency", r10.contingency),
        ("s10_patch_cover", r10.patch_cover),
        ("s10_cells", r10.cell_table),
    ):
        frame.to_csv(DERIVED / f"{name}.csv", index=False)

    for name, frame in (
        ("s30_region_independent", r30.region_independent_table),
        ("s30_region_attribution", r30.region_attribution_table),
        ("s30_region_validation", r30.region_validation_table),
        ("s10_region_independent", r10.region_independent_table),
        ("s10_region_attribution", r10.region_attribution_table),
        ("s10_region_validation", r10.region_validation_table),
    ):
        if frame is not None:
            frame.to_csv(DERIVED / f"{name}.csv", index=False)

    manifest = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "issue": 18,
        "inputs": {
            "geodata_2020_tif": str(GEODATA_TIF.relative_to(REPO_ROOT)),
            "geodata_sha256": sha256_file(GEODATA_TIF),
            "cmsa_2020_shp": str(CMSA_SHP.relative_to(REPO_ROOT)),
            "cmssm_2020_shp": str(CMSSM_SHP.relative_to(REPO_ROOT)),
            "cmsa_gridcode0_features_excluded": cmsa_gc0,
            "cmsa_gridcode0_policy": "UNKNOWN/TODO_VERIFY; never relabelled negative",
        },
        "supports": {"support_30m": r30.metadata, "support_10m": r10.metadata},
        "crs_30m_wkt": crs_a_wkt,
        "crs_10m": str(CHINA_ALBERS_CRS),
        "repair_audit": [vars(a) for a in (cmsa_audit, cmssm_audit)],
        "native_area_km2": {
            "geodata": 519.8913,
            "cmsa_gridcode2_utm_repaired": round(
                float(cmsa_fix.geometry.area.sum()) / 1e6, 4
            ),
            "cmssm_utm_repaired": round(
                float(cmssm_fix.geometry.area.sum()) / 1e6, 4
            ),
        },
        "analysis_universe": (
            "pixels within 300 m of any product positive on each support; "
            "pairwise metrics state their denominators explicitly"
        ),
        "bootstrap": {
            "method": "W10-cell spatial block bootstrap, percentile CI",
            "n_boot": N_BOOT, "seed": SEED,
        },
        "independent_region_attribution": (
            {
                "enabled": True,
                "source": "Natural Earth 10m admin-1 states/provinces "
                          "(ne_10m_admin_1_states_provinces, v5.1.1); "
                          "independent of CMSA, CM-SSM and GEODATA",
                "source_shp": str(ADMIN1_SHP.relative_to(REPO_ROOT)),
                "rule": (
                    "centroid inside province -> province; else nearest "
                    "province if distance <= reach_m and the "
                    "second-nearest province is farther by more than "
                    "ambiguity_m; else UNKNOWN (never forced)"
                ),
                "reach_m": INDEP_REGION_REACH_M,
                "ambiguity_m": INDEP_REGION_AMBIG_M,
                "supports": ["30m", "10m"],
                "note": (
                    "independent labels key all regional tables in the "
                    "v2 report; product-derived region tables remain "
                    "available as s{30,10}_region.csv for the "
                    "before/after attribution comparison"
                ),
            }
            if args.independent_regions else {"enabled": False}
        ),
    }
    (WORK / "transform_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(manifest["repair_audit"], indent=2))
    print(json.dumps(manifest["native_area_km2"], indent=2))
    print("30m region rows:", len(r30.region_table),
          "| 10m region rows:", len(r10.region_table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
