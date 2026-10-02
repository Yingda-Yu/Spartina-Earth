#!/usr/bin/env python3
"""Label x analysis-cell overlap, BAY-CLIP corrected (M2.1a2-R1).

Supersedes ``zhejiang_label_cell_overlap_v0`` (kept on disk, never
overwritten). Two defects are corrected, both proven with evidence:

1. CELL_EDGE_BLEED_CONFIRMED: v0 counted label area over the FULL fixed
   10 km square. A square assigned to a bay extends outside
   PROVISIONAL_BAY_ENVELOPE_V0, so label pixels on neighbouring coast
   were attributed to the bay. v0_1 reports full-square area AND
   bay-clip area (cell_geometry n envelope) separately; authoritative
   bay-scoped status uses the clip. cell_id / cell_geometry are
   permanent -- clipping never regenerates an id.

2. M21A_SMB_ZERO_WAS_MASK_FAILURE: the M2.1a direct overlap
   ``overlap_zj_smb=0`` for L1 came from masking an invalid
   GeometryCollection (rasterio ValueError silently caught as 0).
   Masking the polygonal part yields 46,305 px / 41.6745 km2, equal to
   the envelope intersection. The M2.1a inventory row itself is NOT
   modified; this audit documents CONTRADICTED status.

Metadata/geometry/offline only. UNLABELED != NEGATIVE. No GOLD
promotion (Issue #11 owns that).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
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
import yaml  # noqa: E402
from rasterio.transform import from_bounds  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402

# reuse every measurement primitive from the v0 builder -- no duplicated
# raster/vector logic that could drift between versions
_v0_spec = importlib.util.spec_from_file_location(
    "label_overlap_v0",
    REPO_ROOT / "scripts/data/zhejiang/build_label_cell_overlap.py")
_v0 = importlib.util.module_from_spec(_v0_spec)  # type: ignore[arg-type]
_v0_spec.loader.exec_module(_v0)  # type: ignore[union-attr]

_bcells_spec = importlib.util.spec_from_file_location(
    "build_analysis_cells",
    REPO_ROOT / "scripts/data/zhejiang/build_analysis_cells.py")
_bcells = importlib.util.module_from_spec(_bcells_spec)  # type: ignore[arg-type]
_bcells_spec.loader.exec_module(_bcells)  # type: ignore[union-attr]

OVERLAP_V01_COLUMNS = (
    "cell_id",
    "cell_size_m",
    "bay_id",
    "asset_id",
    "nominal_year",
    "label_tier",
    "bay_clip_area_km2",
    "positive_pixels_full_cell",
    "positive_area_km2_full_cell",
    "positive_pixels_bay_clip",
    "positive_area_km2_bay_clip",
    "positive_pixels_outside_bay_in_cell",
    "positive_area_km2_outside_bay_in_cell",
    "overlap_fraction_of_cell",
    "overlap_fraction_of_bay_clip",
    "cell_label_status_full_geometry_v0",
    "cell_label_status_bay_scoped",
    "gold_target_flag",
    "gold_target_reason",
    "reserved_for_goldset",
)

RECON_COLUMNS = (
    "cell_size_m",
    "bay_id",
    "asset_id",
    "label_tier",
    "direct_envelope_positive_pixels",
    "direct_envelope_area_km2",
    "sum_clipped_cell_pixels",
    "sum_clipped_cell_area_km2",
    "absolute_area_difference_km2",
    "relative_difference",
    "units",
    "reconciliation_note",
)

DISAGREEMENT_V01_COLUMNS = (
    "cell_id",
    "cell_size_m",
    "l1_silver_positive_px_common30m_bayclip",
    "l3_weak_positive_px_common30m_bayclip",
    "agreement_px",
    "silver_only_px",
    "weak_only_px",
    "union_px",
    "jaccard",
    "geometry_scope",
    "method",
)

CELL_EDGE_BLEED = "CELL_EDGE_BLEED_CONFIRMED"
SMB_MASK_FAILURE = "M21A_SMB_ZERO_WAS_MASK_FAILURE"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_envelopes(config_path: Path) -> dict[str, BaseGeometry]:
    """Rebuild PROVISIONAL_BAY_ENVELOPE_V0 exactly as the cell builder."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    base = config["base_coastline"]
    shp_path = REPO_ROOT / base["local_path"]
    if not shp_path.exists():
        raise FileNotFoundError(shp_path)
    if hashlib.sha256(shp_path.read_bytes()).hexdigest() != base["shp_sha256"]:
        raise ValueError("coastline sha256 mismatch")
    margin = 0.12
    pts = [(a["lon"], a["lat"]) for b in config["rois"]
           for a in b["anchors"]]
    bbox = (min(x for x, _ in pts) - margin,
            min(y for _, y in pts) - margin,
            max(x for x, _ in pts) + margin,
            max(y for _, y in pts) + margin)
    coast = gpd.read_file(shp_path, bbox=bbox)
    land = coast.geometry.union_all()
    to_p = pyproj.Transformer.from_crs(
        4326, config["analysis_crs"], always_xy=True).transform
    envelopes: dict[str, BaseGeometry] = {}
    for spec in _bcells.parse_bay_specs(config):
        geom = _bcells.construct_bay(
            spec, land, _bcells.polygon_rings(list(coast.geometry)),
            config["analysis_crs"])
        envelopes[spec.roi_id] = _bcells.shp_transform(to_p, geom.envelope)
    return envelopes


def _asset_measure(
    asset: dict[str, Any], path: Path, geom: BaseGeometry
) -> tuple[int, float]:
    """Return (positive_pixels_or_feature_count, area_km2) for one geom."""
    import rasterio

    if geom.is_empty:
        return 0, 0.0
    if not path.exists():
        return 0, 0.0
    if asset["asset_kind"] == "RASTER_LABEL":
        with rasterio.open(path) as ds:
            px, area_km2, _cov = _v0.raster_positive_in_cell(ds, geom)
            return int(px), float(area_km2)
    n, area = _v0.vector_area_in_cell(path, geom)
    return (int(max(n, 0)), float(area))


def status_from(pos: dict[str, dict[str, dict[str, Any]]], area_key: str,
                cell_ids: set[str]) -> dict[str, str]:
    tiers: dict[str, set[str]] = defaultdict(set)
    for cid, by_asset in pos.items():
        if cid not in cell_ids:
            continue
        for areas in by_asset.values():
            tier = areas.get("tier")
            if isinstance(tier, str) and areas[area_key] > 0:
                tiers[cid].add(tier)
    out: dict[str, str] = {}
    for cid in cell_ids:
        t = tiers.get(cid, set())
        if not t:
            out[cid] = "UNLABELED"
        elif t >= {"SILVER", "WEAK"}:
            out[cid] = "SILVER+WEAK"
        else:
            out[cid] = next(iter(t))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",
                        default=str(REPO_ROOT
                                    / "configs/data/zhejiang_multibay_m21a.yaml"))
    parser.add_argument("--manifest-dir",
                        default=str(REPO_ROOT / "datasets/manifests"))
    args = parser.parse_args()
    mdir = Path(args.manifest_dir)
    config_path = Path(args.config)
    envelopes = load_envelopes(config_path)

    old_dir, assets = _v0.load_inventory_assets()
    label_assets = [a for a in assets if a["asset_kind"] in
                    ("RASTER_LABEL", "VECTOR_LABEL")]
    paths = {a["asset_id"]: old_dir / a["relpath"] for a in label_assets}

    cells = _v0.cell_polys(mdir / "zhejiang_analysis_cells_v0.csv")
    rows: list[dict[str, Any]] = []
    pos: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    for cid, bundle in sorted(cells.items()):
        r = bundle["row"]
        bay_id = str(r["bay_id"])
        square: BaseGeometry = bundle["poly32651"]
        clip = square.intersection(envelopes[bay_id])
        outside = square.difference(envelopes[bay_id])
        cell_area = float(square.area) / 1e6
        clip_area = round(float(clip.area) / 1e6, 6)
        for asset in label_assets:
            aid = asset["asset_id"]
            path = paths[aid]
            px_f, a_full = _asset_measure(asset, path, square)
            px_c, a_clip = _asset_measure(asset, path, clip)
            px_o, a_out = _asset_measure(asset, path, outside)
            pos[cid][aid] = {
                "tier": asset["label_tier"],
                "full": a_full, "clip": a_clip, "out": a_out,
            }
            rows.append({
                "cell_id": cid,
                "cell_size_m": int(r["cell_size_m"]),
                "bay_id": bay_id,
                "asset_id": aid,
                "nominal_year": int(asset["nominal_year"]),
                "label_tier": asset["label_tier"],
                "bay_clip_area_km2": clip_area,
                "positive_pixels_full_cell": px_f,
                "positive_area_km2_full_cell": a_full,
                "positive_pixels_bay_clip": px_c,
                "positive_area_km2_bay_clip": a_clip,
                "positive_pixels_outside_bay_in_cell": px_o,
                "positive_area_km2_outside_bay_in_cell": a_out,
                "overlap_fraction_of_cell": (
                    round(a_full / cell_area, 6) if a_full else 0.0),
                "overlap_fraction_of_bay_clip": (
                    round(a_clip / clip_area, 6)
                    if a_clip and clip_area else 0.0),
                "cell_label_status_full_geometry_v0": "",
                "cell_label_status_bay_scoped": "",
                "gold_target_flag": "",
                "gold_target_reason": "",
                "reserved_for_goldset": "",
            })

    df = pd.DataFrame(rows)
    all_ids = set(cells)
    full_status = status_from(pos, "full", all_ids)
    clip_status = status_from(pos, "clip", all_ids)
    df["cell_label_status_full_geometry_v0"] = df["cell_id"].map(
        lambda c: full_status.get(c, "UNLABELED"))
    df["cell_label_status_bay_scoped"] = df["cell_id"].map(
        lambda c: clip_status.get(c, "UNLABELED"))

    # ---- GoldSet flags on 10 km, bay-scoped (clip) semantics ------------
    ten = df[df.cell_size_m == 10_000]
    silver = {r.cell_id for r in ten.itertuples()
              if r.label_tier == "SILVER"
              and r.positive_area_km2_bay_clip > 0}
    weak = {r.cell_id for r in ten.itertuples()
            if r.label_tier == "WEAK"
            and r.positive_area_km2_bay_clip > 0}
    ids10 = {bid: {c for c, b in cells.items()
                   if b["row"]["cell_size_m"] == 10_000
                   and b["row"]["bay_id"] == bid}
             for bid in ("ZJ-HZB", "ZJ-SMB", "ZJ-YQB")}
    disagreement = (silver & weak) & ids10["ZJ-HZB"]
    temporal = (silver & weak) & ids10["ZJ-YQB"]
    reasons: dict[str, str] = {}
    for c in sorted(disagreement):
        reasons[c] = "DISAGREEMENT_SILVER_2015_VS_WEAK_2015_HZB"
    for c in sorted(temporal):
        reasons[c] = "TEMPORAL_SILVER_2015_VS_WEAK_CMSA_2019_2021_YQB"
    for c in sorted(weak - silver):
        reasons.setdefault(c, "WEAK_ONLY_EVIDENCE_UPGRADE_TARGET")
    smb_gap = ids10["ZJ-SMB"] - (silver | weak)
    for c in sorted(smb_gap):
        reasons[c] = "CROSS_BAY_LABEL_GAP_SMB_NO_LABEL_IN_BAY_CLIP"

    reserved: dict[str, str] = {}
    if disagreement:
        rank = (ten[ten.cell_id.isin(disagreement)]
                .groupby("cell_id").positive_area_km2_bay_clip.sum()
                .sort_values(ascending=False))
        reserved[rank.index[0]] = (
            "PRE_REGISTERED_FIELD_UAV_TARGET_HZB_DISAGREEMENT")
    if temporal:
        cmsa = ten[ten.cell_id.isin(temporal)
                   & ten.asset_id.str.startswith(("L4", "L5", "L6"))]
        rank = (cmsa.groupby("cell_id").positive_area_km2_bay_clip.sum()
                .sort_values(ascending=False))
        reserved[rank.index[0]] = (
            "PRE_REGISTERED_FIELD_UAV_TARGET_YQB_TEMPORAL")
    if smb_gap:
        reserved[min(smb_gap)] = (
            "PRE_REGISTERED_FIELD_UAV_TARGET_SMB_GAP")
    cell_reason = dict(reasons)
    for cid, why in reserved.items():
        prev = cell_reason.get(cid, "")
        cell_reason[cid] = f"{prev}|{why}" if prev else why

    ten_mask = df.cell_size_m == 10_000
    df.loc[ten_mask, "gold_target_flag"] = df.loc[ten_mask, "cell_id"].map(
        lambda c: "GOLD_EVIDENCE_TARGET" if c in cell_reason else "")
    df.loc[ten_mask, "gold_target_reason"] = df.loc[ten_mask, "cell_id"].map(
        lambda c: cell_reason.get(c, ""))
    df.loc[ten_mask, "reserved_for_goldset"] = df.loc[
        ten_mask, "cell_id"].map(
            lambda c: "RESERVED_FOR_GOLDSET" if c in reserved else "")

    df = df.sort_values(["cell_size_m", "cell_id", "asset_id"])
    csv_path = mdir / "zhejiang_label_cell_overlap_v0_1.csv"
    pq_path = mdir / "zhejiang_label_cell_overlap_v0_1.parquet"
    df.to_csv(csv_path, index=False)
    df.to_parquet(pq_path, index=False)

    # ---- direct-envelope reconciliation ---------------------------------
    recon_rows: list[dict[str, Any]] = []
    # each candidate grid tiles the envelope independently; reconcile
    # per grid size (summing across sizes would triple-count)
    direct_cache: dict[tuple[str, str], tuple[int, float]] = {}
    for size in sorted(df.cell_size_m.unique()):
        for bay_id in sorted(envelopes):
            env = envelopes[bay_id]
            for asset in label_assets:
                aid = asset["asset_id"]
                dpx, darea = direct_cache.setdefault(
                    (bay_id, aid),
                    _asset_measure(asset, paths[aid], env))
                sub = df[(df.cell_size_m == size)
                         & (df.bay_id == bay_id) & (df.asset_id == aid)]
                spx = int(sub.positive_pixels_bay_clip.sum())
                sarea = round(
                    float(sub.positive_area_km2_bay_clip.sum()), 4)
                units = ("POSITIVE_PIXELS"
                         if asset["asset_kind"] == "RASTER_LABEL"
                         else "FEATURES_AREA")
                diff = round(abs(sarea - darea), 4)
                rel = (round(diff / darea, 6) if darea > 0 else
                       (0.0 if sarea == 0 else float("inf")))
                note = ("MATCH_WITHIN_RASTERIZATION_TOLERANCE" if rel < 0.01
                        else "MISMATCH_REQUIRES_REVIEW")
                recon_rows.append({
                    "cell_size_m": int(size),
                    "bay_id": bay_id,
                    "asset_id": aid,
                    "label_tier": asset["label_tier"],
                    "direct_envelope_positive_pixels": dpx,
                    "direct_envelope_area_km2": darea,
                    "sum_clipped_cell_pixels": spx,
                    "sum_clipped_cell_area_km2": sarea,
                    "absolute_area_difference_km2": diff,
                    "relative_difference": rel,
                    "units": units,
                    "reconciliation_note": note,
                })
    pd.DataFrame(recon_rows, columns=list(RECON_COLUMNS)).to_csv(
        mdir / "zhejiang_label_bay_reconciliation_v0_1.csv", index=False)

    # ---- HZB disagreement on bay-clip common 30 m grid ------------------
    l1 = paths["L1-china2015-raster30m"]
    l3 = paths["L3-hangzhou-mask-2015"]
    drows: list[dict[str, Any]] = []
    for cid in sorted(c for c in disagreement):
        square = cells[cid]["poly32651"]
        clip = square.intersection(envelopes["ZJ-HZB"])
        size = 10_000 // 30
        tf = from_bounds(*square.bounds, size, size)
        a = _v0.common_grid_labels(l1, clip, (size, size), tf)
        b = _v0.common_grid_labels(l3, clip, (size, size), tf)
        if a is None or b is None:
            continue
        agree = int(np.count_nonzero(a & b))
        only_a = int(np.count_nonzero(a & ~b))
        only_b = int(np.count_nonzero(b & ~a))
        union = agree + only_a + only_b
        drows.append({
            "cell_id": cid,
            "cell_size_m": 10000,
            "l1_silver_positive_px_common30m_bayclip": int(np.count_nonzero(a)),
            "l3_weak_positive_px_common30m_bayclip": int(np.count_nonzero(b)),
            "agreement_px": agree,
            "silver_only_px": only_a,
            "weak_only_px": only_b,
            "union_px": union,
            "jaccard": round(agree / union, 4) if union else None,
            "geometry_scope": "cell_geometry n HZB envelope (bay clip)",
            "method": ("nearest-neighbour warp to common EPSG:32651 30m "
                       "grid; ~1 px positional tolerance; diagnostic"),
        })
    pd.DataFrame(drows, columns=list(DISAGREEMENT_V01_COLUMNS)).to_csv(
        mdir / "zhejiang_hzb_label_disagreement_v0_1.csv", index=False)

    # ---- supersession sidecar (v0 bytes stay untouched) -----------------
    old_csv = mdir / "zhejiang_label_cell_overlap_v0.csv"
    sidecar = {
        "manifest": "zhejiang_label_cell_overlap_v0_1",
        "supersedes": "zhejiang_label_cell_overlap_v0.csv",
        "supersedes_sha256": sha256_file(old_csv),
        "superseded_sha256": sha256_file(csv_path),
        "correction_status": "SUPERSEDED_BY_BAY_CLIP_CORRECTION",
        "defects": [
            {
                "marker": CELL_EDGE_BLEED,
                "detail": ("v0 attributed label area in the full fixed "
                           "square to the cell's bay; v0_1 separates "
                           "bay-clip and outside-bay area."),
            },
            {
                "marker": SMB_MASK_FAILURE,
                "detail": ("M2.1a overlap_zj_smb L1=0 was a swallowed "
                           "rasterio ValueError on an invalid "
                           "GeometryCollection; polygonal-part mask gives "
                           "46,305 px / 41.6745 km2. M2.1a inventory file "
                           "is preserved unchanged; status CONTRADICTED."),
            },
        ],
        "geometry_semantics": {
            "cell_geometry": "full fixed square; stable id/archive/split unit",
            "bay_clip_geometry":
                "cell_geometry n PROVISIONAL_BAY_ENVELOPE_V0",
            "authoritative_bay_scoped_status": "cell_label_status_bay_scoped",
        },
    }
    (mdir / "zhejiang_label_cell_overlap_v0_1.supersedes.json").write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n")

    # ---- console summary ------------------------------------------------
    for size in sorted(df.cell_size_m.unique()):
        sub = df[df.cell_size_m == size][
            ["cell_id", "cell_label_status_bay_scoped", "bay_id"]] \
            .drop_duplicates()
        print(f"{size} m (bay-clip):")
        print(sub.groupby(["bay_id", "cell_label_status_bay_scoped"])
              .size().unstack(fill_value=0))
    bleed = df[(df.cell_size_m == 10_000)
               & (df.positive_area_km2_outside_bay_in_cell > 0)]
    print("10 km rows with outside-bay label area: "
          f"{len(bleed)} asset-rows, "
          f"{bleed.positive_area_km2_outside_bay_in_cell.sum():.4f} km2 total")
    print("disagreement cells (clip):", len(drows),
          "; RESERVED:", sorted(reserved))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
