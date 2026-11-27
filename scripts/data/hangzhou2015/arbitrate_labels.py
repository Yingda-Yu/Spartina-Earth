"""Pilot-0 label arbitration: SILVER 2015 national product vs WEAK local mask.

Both labels are treated as *distinct label sources*. This script:

1. warps a windowed read of the national 2015 SILVER raster (read-only)
   to the 30 m analysis grid with nearest neighbour;
2. builds the agreement/disagreement map;
3. quantifies intersection/union/omission/commission, connected-component
   size distributions, boundary distance bands and centroid vectors;
4. profiles the spectral/SAR context of each disagreement stratum with
   explicitly-labelled PROXY class conventions (water/mudflat/vegetation);
5. tests whether the WEAK mask can be reproduced by a simple SAI or NDVI
   threshold (and a conjunction), reporting the best achievable agreement;
6. emits a deterministic stratified point sample for OWNER visual
   inspection in QGIS/ArcGIS (the agent cannot perform visual adjudication);
7. proposes an IGNORE mask for validation use.

Writes only to work/ and artifacts/. Source files are never modified.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import rasterio.warp  # noqa: F401
from rasterio.enums import Resampling
from scipy import ndimage

ANALYSIS_CRS = "EPSG:32651"
PIX_M = 30.0
PIX_AREA_KM2 = PIX_M * PIX_M / 1e6
SILVER_NODATA = 255
IGNORE_BOUNDARY_M = 60.0  # <=2 L8 pixels around either label's boundary

# Context PROXY conventions (analytical, NOT ground truth)
WATER_NDWI = 0.10
VEG_NDVI = 0.25
SPARSE_NDVI = 0.10

# Plausibility gates for the threshold-generation hypothesis
PLAUSIBLE_JACCARD = 0.90
WEAK_PLAUSIBLE_JACCARD = 0.75


def find_silver_raster(root: Path) -> Path:
    hits = list(root.glob("30mSpartinaChina/**/*.tif"))
    hits = [p for p in hits if "数据实体" in str(p) or len(hits) == 1]
    if not hits:
        raise FileNotFoundError("national 2015 raster not found under old datasets/")
    return sorted(hits)[0]


def component_table(binary: np.ndarray[Any, Any], pixel_m: float) -> dict[str, Any]:
    structure = np.ones((3, 3), dtype="uint8")  # 8-connectivity
    lab, n = ndimage.label(binary, structure=structure)
    if n == 0:
        return {"component_count": 0}
    sizes = np.bincount(lab.ravel())[1:]  # pixels per component
    bins = {"1-9_small": (1, 9), "10-100": (10, 100), "101-1000": (101, 1000),
            ">1000_large": (1001, None)}
    dist: dict[str, Any] = {}
    for name, (lo, hi) in bins.items():
        sel = sizes >= lo if hi is None else (sizes >= lo) & (sizes <= hi)
        dist[name] = {
            "component_count": int(sel.sum()),
            "pixel_count": int(sizes[sel].sum()),
            "area_km2": float(sizes[sel].sum()) * PIX_AREA_KM2,
        }
    return {
        "component_count": int(n),
        "largest_component_pixels": int(sizes.max()),
        "largest_component_area_km2": float(sizes.max()) * PIX_AREA_KM2,
        "median_component_pixels": float(np.median(sizes)),
        "size_distribution": dist,
        "total_pixels": int(sizes.sum()),
    }


def boundary_distance_bands(
    region: np.ndarray[Any, Any], other_label: np.ndarray[Any, Any], pixel_m: float
) -> dict[str, Any]:
    """Distance of disagreement pixels to the OTHER label's nearest edge."""
    other_edge = other_label & ~ndimage.binary_erosion(other_label)
    # Distance from every pixel to the nearest edge pixel of other_label
    dist = ndimage.distance_transform_edt(~other_edge) * pixel_m
    vals = dist[region]
    bins = [0, 30, 90, 300, math.inf]
    names = ["0-30m_boundary", "30-90m", "90-300m", ">300m_interior"]
    out: dict[str, Any] = {}
    for name, lo, hi in zip(names, bins[:-1], bins[1:], strict=True):
        sel = (vals >= lo) & (vals < hi)
        out[name] = {"pixel_count": int(sel.sum()),
                     "area_km2": float(sel.sum()) * PIX_AREA_KM2,
                     "fraction": float(sel.mean()) if region.sum() else None}
    out["median_distance_m"] = float(np.median(vals)) if vals.size else None
    return out


def confusion(weak: np.ndarray[Any, Any], silver: np.ndarray[Any, Any], valid: np.ndarray[Any, Any],
              ) -> dict[str, Any]:
    w = weak.astype(bool) & valid
    s = silver.astype(bool) & valid
    tp = int((w & s).sum())
    fp = int((w & ~s).sum())
    fn = int((~w & s).sum())
    tn = int((~w & ~s).sum())
    inter, union = tp, tp + fp + fn
    jaccard = inter / union if union else None
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None
    return {
        "both_tp_pixels": tp,
        "weak_only_fp_pixels": fp,
        "silver_only_fn_pixels": fn,
        "neither_tn_pixels": tn,
        "jaccard": jaccard,
        "precision_of_weak_vs_silver": precision,
        "recall_of_weak_vs_silver": recall,
        "f1": f1,
        "areas_km2": {
            "intersection": tp * PIX_AREA_KM2,
            "weak_only": fp * PIX_AREA_KM2,
            "silver_only": fn * PIX_AREA_KM2,
            "union": union * PIX_AREA_KM2,
            "weak_total": (tp + fp) * PIX_AREA_KM2,
            "silver_total": (tp + fn) * PIX_AREA_KM2,
        },
    }


def best_threshold(
    values: np.ndarray[Any, Any], target: np.ndarray[Any, Any], valid: np.ndarray[Any, Any],
    direction: str, n_steps: int = 200,
) -> dict[str, Any]:
    """Best 1-D threshold; direction='less' or 'greater' predicts positive."""
    v = values[valid]
    t = target[valid]
    grid = np.quantile(v, np.linspace(0.01, 0.99, n_steps))
    best: dict[str, Any] = {"jaccard": -1.0}
    for thr in grid:
        pred = v < thr if direction == "less" else v > thr
        inter = float((pred & t).sum())
        union = float((pred | t).sum())
        j = inter / union if union else 0.0
        if j > best["jaccard"]:
            tp = inter
            fp = float((pred & ~t).sum())
            fn = float((~pred & t).sum())
            best = {
                "threshold": float(thr),
                "jaccard": j,
                "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None,
                "positive_pixels": int(pred.sum()),
            }
    return best


def context_profile(
    strata: dict[str, np.ndarray[Any, Any]],
    ndvi: np.ndarray[Any, Any], ndwi: np.ndarray[Any, Any], sai: np.ndarray[Any, Any],
    vv: np.ndarray[Any, Any], vh: np.ndarray[Any, Any], valid: np.ndarray[Any, Any],
) -> dict[str, Any]:
    def proxy_class(mask: np.ndarray[Any, Any]) -> dict[str, float]:
        m = mask & valid & np.isfinite(ndvi) & np.isfinite(ndwi)
        n = int(m.sum())
        if n == 0:
            return {"pixels": 0}
        water = (ndwi[m] > WATER_NDWI)
        green = (ndvi[m] >= VEG_NDVI)
        sparse = (ndvi[m] >= SPARSE_NDVI) & (ndvi[m] < VEG_NDVI)
        mud = (~water) & (ndvi[m] < SPARSE_NDVI)
        return {
            "pixels": n,
            "water_proxy_fraction": float(water.mean()),
            "mudflat_wetsoil_proxy_fraction": float(mud.mean()),
            "sparse_veg_proxy_fraction": float(sparse.mean()),
            "green_veg_proxy_fraction": float(green.mean()),
            "ndvi_mean": float(np.nanmean(ndvi[m])),
            "ndwi_mean": float(np.nanmean(ndwi[m])),
            "sai_mean": float(np.nanmean(sai[m])),
            "vv_db_mean": float(np.nanmean(vv[m])),
            "vh_db_mean": float(np.nanmean(vh[m])),
        }

    return {name: proxy_class(mask) for name, mask in strata.items()}


def shift_jaccard_scan(weak: np.ndarray[Any, Any], silver: np.ndarray[Any, Any],
                         max_shift: int = 5) -> dict[str, Any]:
    """Jaccard under integer translations of SILVER; a peak off-zero
    would indicate a residual systematic misregistration."""
    w = weak.astype(bool)
    table = {}
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            s2 = np.zeros_like(silver, dtype=bool)
            ys0 = max(0, dy)
            ys1 = min(silver.shape[0], silver.shape[0] + dy)
            xs0 = max(0, dx)
            xs1 = min(silver.shape[1], silver.shape[1] + dx)
            sy0 = max(0, -dy)
            sy1 = sy0 + (ys1 - ys0)
            sx0 = max(0, -dx)
            sx1 = sx0 + (xs1 - xs0)
            s2[ys0:ys1, xs0:xs1] = silver[sy0:sy1, sx0:sx1]
            inter = float((w & s2).sum())
            union = float((w | s2).sum())
            table[f"{dy},{dx}"] = inter / union if union else None
    best = max(table.items(), key=lambda kv: kv[1] or -1)
    by_, bx_ = (int(v) for v in best[0].split(","))
    return {
        "max_shift_px": max_shift,
        "jaccard_at_zero": table["0,0"],
        "best_shift_row_col_px": [by_, bx_],
        "best_jaccard": best[1],
        "peak_at_zero": (by_, bx_) == (0, 0),
        "note": "positive dx = SILVER shifted east; 30 m per pixel",
    }


def centroid(binary: np.ndarray[Any, Any], transform: Any) -> tuple[float, float]:
    ys, xs = np.where(binary)
    if len(ys) == 0:
        return (float("nan"), float("nan"))
    x = transform.c + (xs.mean() + 0.5) * transform.a
    y = transform.f + (ys.mean() + 0.5) * transform.e
    return float(x), float(y)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=Path("old datasets"))
    ap.add_argument("--work-dir", type=Path,
                    default=Path("work/hangzhou2015/v1"))
    ap.add_argument("--json-out", type=Path,
                    default=Path("artifacts/audit/pilot0/label_arbitration.json"))
    ap.add_argument("--sample-csv", type=Path,
                    default=Path("artifacts/audit/pilot0/label_arbitration_samples.csv"))
    args = ap.parse_args(argv)
    wd = args.work_dir

    grid = json.loads((wd / "grid_spec.json").read_text())["grid_30m"]
    from rasterio.transform import Affine

    g30 = Affine(*grid["transform"])
    w, h = grid["width"], grid["height"]

    with rasterio.open(wd / "label_mask_30m.tif") as ds:
        weak = ds.read(1)
    with rasterio.open(wd / "l8_sr_30m.tif") as ds:
        sr = ds.read().astype("float32")
    with rasterio.open(wd / "l8_valid_30m.tif") as ds:
        opt_valid = ds.read(1).astype(bool)
    ndvi = rasterio.open(wd / "ndvi_30m.tif").read(1).astype("float32")
    sai = rasterio.open(wd / "sai_30m.tif").read(1).astype("float32")
    vv = rasterio.open(wd / "s1_vv_30m.tif").read(1).astype("float32")
    vh = rasterio.open(wd / "s1_vh_30m.tif").read(1).astype("float32")

    # --- SILVER window: warp (NN) only the intersecting national region --
    silver_path = find_silver_raster(args.data_root)
    silver_raw = np.full((h, w), SILVER_NODATA, dtype="int16")
    with rasterio.open(silver_path) as src:
        rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=silver_raw,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=g30,
            dst_crs=ANALYSIS_CRS,
            src_nodata=SILVER_NODATA,
            dst_nodata=SILVER_NODATA,
            resampling=Resampling.nearest,
        )
    # Presence-only thematic product (VAT has a single class Value=1).
    # 255 is storage NoData; semantically read as "background" (not 1).
    # Whether background means "verified absence" or "outside mapped
    # domain" is NOT documented in the file -> MISSING_EVIDENCE recorded.
    bg_count = int((silver_raw == SILVER_NODATA).sum())
    silver = (silver_raw == 1).astype("uint8")
    with rasterio.open(
        wd / "silver_2015_30m.tif", "w", driver="GTiff", width=w, height=h,
        count=1, dtype="uint8", crs=ANALYSIS_CRS, transform=g30,
        compress="deflate",
    ) as dst:
        dst.write(silver, 1)

    valid_all = weak != 127          # full window: background treated negative
    valid = opt_valid & (weak != 127) & np.isfinite(ndvi)  # spectral domain
    wb = weak == 1
    sb = silver == 1

    # --- confusion ---------------------------------------------------------
    # Primary: full window; 255 read as background (presence-mask semantics).
    conf = confusion(weak, silver, valid_all)
    conf_optical = confusion(weak, silver, valid)

    # --- strata ------------------------------------------------------------
    both = wb & sb & valid_all
    silver_only = sb & ~wb & valid_all
    weak_only = wb & ~sb & valid_all
    neither = ~wb & ~sb & valid_all
    dmap = np.zeros((h, w), dtype="uint8")
    dmap[valid_all & ~wb & ~sb] = 0
    dmap[both] = 1
    dmap[silver_only] = 2
    dmap[weak_only] = 3
    with rasterio.open(
        wd / "label_disagreement_30m.tif", "w", driver="GTiff", width=w,
        height=h, count=1, dtype="uint8", crs=ANALYSIS_CRS, transform=g30,
        compress="deflate",
    ) as dst:
        dst.write(dmap, 1)
        dst.write_colormap(1, {0: (20, 20, 20, 255), 1: (0, 180, 0, 255),
                               2: (230, 160, 0, 255), 3: (220, 0, 0, 255)})

    # --- components --------------------------------------------------------
    comps = {
        "both": component_table(both, PIX_M),
        "silver_only": component_table(silver_only, PIX_M),
        "weak_only": component_table(weak_only, PIX_M),
        "weak_positive_total": component_table(wb & valid_all, PIX_M),
        "silver_positive_total": component_table(sb & valid_all, PIX_M),
    }

    # --- boundary bands ----------------------------------------------------
    bands = {
        "silver_only_distance_to_weak":
            boundary_distance_bands(silver_only, wb, PIX_M),
        "weak_only_distance_to_silver":
            boundary_distance_bands(weak_only, sb, PIX_M),
    }

    # --- centroid vectors (systematic translation?) -----------------------
    cw = centroid(wb & valid, g30)
    cs = centroid(sb & valid, g30)
    cb = centroid(both, g30)
    cso = centroid(silver_only, g30)
    cwo = centroid(weak_only, g30)
    centroids = {
        "weak_centroid_utm51n": cw,
        "silver_centroid_utm51n": cs,
        "intersection_centroid_utm51n": cb,
        "silver_only_centroid_utm51n": cso,
        "weak_only_centroid_utm51n": cwo,
        "weak_minus_silver_centroid_m": [cw[0] - cs[0], cw[1] - cs[1]],
    }

    # --- spectral/SAR context ---------------------------------------------
    b3 = sr[1]  # green (SR_B2)
    b5 = sr[4]  # NIR (SR_B5)
    denom = b3 + b5
    ndwi = np.where(denom != 0, (b3 - b5) / denom, np.nan).astype("float32")
    strata = {"both_positive": both, "silver_only": silver_only,
              "weak_only": weak_only, "neither_negative": neither}
    profiles = context_profile(strata, ndvi, ndwi, sai, vv, vh, valid)

    # --- threshold-generation hypotheses ----------------------------------
    finite = valid & np.isfinite(sai) & np.isfinite(ndvi)
    t_sai = best_threshold(sai, wb, finite, "less")
    t_ndvi = best_threshold(ndvi, wb, finite, "greater")

    # conjunction: SAI < t_s AND NDVI > t_n (coarse grid)
    best_conj: dict[str, Any] = {"jaccard": -1.0}
    grid_s = np.quantile(sai[finite], np.linspace(0.1, 0.9, 33))
    grid_n = np.quantile(ndvi[finite], np.linspace(0.1, 0.9, 33))
    tgt = wb[finite]
    sv, nv = sai[finite], ndvi[finite]
    for ts in grid_s:
        for tn in grid_n:
            pred = (sv < ts) & (nv > tn)
            inter = float((pred & tgt).sum())
            union = float((pred | tgt).sum())
            j = inter / union if union else 0.0
            if j > best_conj["jaccard"]:
                best_conj = {"sai_threshold": float(ts),
                             "ndvi_threshold": float(tn), "jaccard": j,
                             "positive_pixels": int(pred.sum())}

    def verdict(j: float | None) -> str:
        if j is None:
            return "UNTESTED"
        if j >= PLAUSIBLE_JACCARD:
            return "PLAUSIBLE (>=0.90)"
        if j >= WEAK_PLAUSIBLE_JACCARD:
            return "PARTIAL (0.75-0.90)"
        return "REJECTED (<0.75)"

    shift_scan = shift_jaccard_scan(wb, sb, max_shift=5)

    thresholds: dict[str, Any] = {
        "polarity": "weak mask positives are more negative in SAI "
                    "(consistent with SAI=(Red-NIR)/NIR)",
        "sai_threshold_best": t_sai,
        "ndvi_threshold_best": t_ndvi,
        "sai_and_ndvi_conjunction_best": best_conj,
        "verdicts": {
            "mask_is_sai_threshold": verdict(t_sai["jaccard"]),
            "mask_is_ndvi_threshold": verdict(t_ndvi["jaccard"]),
            "mask_is_sai_and_ndvi_rule": verdict(best_conj["jaccard"]),
        },
    }

    # --- proposed IGNORE mask ---------------------------------------------
    wb_edge = wb & ~ndimage.binary_erosion(wb)
    sb_edge = sb & ~ndimage.binary_erosion(sb)
    near_either = ndimage.binary_dilation(wb_edge | sb_edge,
                                          iterations=int(round(
                                              IGNORE_BOUNDARY_M / PIX_M)))
    ignore = (valid & near_either & (wb ^ sb)) | (~opt_valid)
    with rasterio.open(
        wd / "ignore_30m.tif", "w", driver="GTiff", width=w, height=h,
        count=1, dtype="uint8", crs=ANALYSIS_CRS, transform=g30,
        compress="deflate",
    ) as dst:
        dst.write(ignore.astype("uint8"), 1)
    usable_eval = valid_all & ~ignore
    conf_eval = confusion(weak, silver, usable_eval)
    conf_eval_optical = confusion(weak, silver, valid & ~ignore)

    # --- deterministic stratified sample for OWNER visual inspection ------
    rng = np.random.default_rng(0)
    sample_strata = {
        "both_interior": both & ~near_either,
        "silver_only_interior": silver_only & ~near_either,
        "weak_only_interior": weak_only & ~near_either,
        "disagreement_boundary": valid & near_either & (wb ^ sb),
    }
    rows = []
    for name, mask in sample_strata.items():
        ys, xs = np.where(mask)
        if len(ys) == 0:
            continue
        take = min(30, len(ys))
        sel = rng.choice(len(ys), size=take, replace=False)
        for i in sel:
            y, x = int(ys[i]), int(xs[i])
            from pyproj import Transformer

            lon, lat = Transformer.from_crs(
                ANALYSIS_CRS, "EPSG:4326", always_xy=True
            ).transform(g30.c + (x + 0.5) * g30.a,
                        g30.f + (y + 0.5) * g30.e)
            rows.append({
                "stratum": name, "row": y, "col": x,
                "easting": g30.c + (x + 0.5) * g30.a,
                "northing": g30.f + (y + 0.5) * g30.e,
                "lon": lon, "lat": lat,
                "weak_label": int(wb[y, x]), "silver_label": int(sb[y, x]),
                "ndvi": float(ndvi[y, x]), "ndwi_proxy": float(ndwi[y, x]),
                "sai": float(sai[y, x]),
                "vv_db": float(vv[y, x]), "vh_db": float(vh[y, x]),
                "sr_B2_green": float(sr[1, y, x]),
                "sr_B5_nir": float(sr[4, y, x]),
                "sr_B6_swir1": float(sr[5, y, x]),
            })
    args.sample_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.sample_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames: list[str] = [k for k in rows[0]]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "silver_source": str(silver_path),
        "silver_semantics": {
            "vat_classes": "single Value=1 (count 608287 in full national file)",
            "storage_nodata": 255,
            "interpretation_used": "presence mask: 1=Spartina, 255=background",
            "background_meaning": ("MISSING_EVIDENCE: file does not state whether "
                                   "background is verified absence or unmapped domain"),
            "background_pixels_in_window": bg_count,
        },
        "window_pixels": int(valid_all.sum()),
        "optical_valid_pixels": int(valid.sum()),
        "confusion_full_window_background_as_negative": conf,
        "confusion_optical_valid_only": conf_optical,
        "components": comps,
        "boundary_distance_bands": bands,
        "centroids": centroids,
        "context_proxy_conventions": {
            "water": f"NDWI(green,NIR) > {WATER_NDWI}",
            "mudflat_wetsoil": f"not water and NDVI < {SPARSE_NDVI}",
            "sparse_veg": f"{SPARSE_NDVI} <= NDVI < {VEG_NDVI}",
            "green_veg": f"NDVI >= {VEG_NDVI}",
            "warning": "these are analytical PROXY classes, not ground truth",
        },
        "context_profiles": profiles,
        "systematic_shift_scan": shift_scan,
        "threshold_hypotheses": thresholds,
        "ignore_mask": {
            "rule": (
                f"IGNORE = invalid optical pixels OR disagreement pixels "
                f"within {IGNORE_BOUNDARY_M:.0f} m of either label boundary"
            ),
            "ignore_pixels": int(ignore.sum()),
            "confusion_after_ignore_full_window": conf_eval,
            "confusion_after_ignore_optical_valid": conf_eval_optical,
            "arbitration_option": (
                "Option 1+3: SILVER 2015 product is the evaluation "
                "reference; WEAK local mask is auxiliary information; "
                "boundary disagreement is IGNORED at validation, not voted"
            ),
        },
        "owner_action_required": (
            "inspect label_arbitration_samples.csv over L8/S1 in QGIS/ArcGIS "
            "(120 deterministic points); agent visual adjudication is not "
            "possible and was not attempted"
        ),
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "jaccard_all": conf["jaccard"],
        "jaccard_after_ignore": conf_eval["jaccard"],
        "sai_threshold": thresholds["verdicts"]["mask_is_sai_threshold"],
        "conjunction": thresholds["verdicts"]["mask_is_sai_and_ndvi_rule"],
    }, indent=2))
    print(f"-> {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
