"""Patch-size study for Pilot-0 (Issue #4 Step 2).

Chosen BEFORE model work and ONLY from geometry/data statistics:
component area / bbox / equivalent-diameter quantiles, containable
fraction with a declared context margin, usable-window counts, edge
truncation, area utilisation and spatially independent block counts.

Writes artifacts/audit/pilot0/patch_size_study.json. Read-only inputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import rasterio
from scipy import ndimage

CANDIDATES_PX = [64, 96, 128, 192, 256]
PIXEL_M = 30.0
# Context margin declared from benchmarks/spartinashift/SPEC.md:
# buffer >= 250 m -> ceil(250/30) = 9 px on every side of an object.
CONTEXT_MARGIN_PX = 9
# Materiality for WEAK-only candidate components is inspected at
# several thresholds and fixed in the config, never from model results.
MATERIAL_THRESHOLDS_PX = [10, 50, 100]
STRIDE_FRACTION = 0.5  # candidate stride = P/2 (decided in the config later)
QUANTILES = [50, 75, 90, 95, 99]


def component_table(
    mask: np.ndarray[Any, Any],
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any],
           np.ndarray[Any, Any], np.ndarray[Any, Any],
           np.ndarray[Any, Any]]:
    lab, n = ndimage.label(mask, structure=np.ones((3, 3), dtype="uint8"))
    sizes = np.bincount(lab.ravel())[1:]
    if n == 0:
        z = np.zeros(0)
        return z, z, z, z, z
    objs = ndimage.find_objects(lab)
    bw = np.array([o[1].stop - o[1].start for o in objs], dtype="float64")
    bh = np.array([o[0].stop - o[0].start for o in objs], dtype="float64")
    eqd = 2.0 * np.sqrt(sizes / np.pi)
    return sizes, bw, bh, eqd, bw * 0


def quantile_block(sizes: np.ndarray[Any, Any], bw: np.ndarray[Any, Any],
                   bh: np.ndarray[Any, Any],
                   eqd: np.ndarray[Any, Any]) -> dict[str, Any]:
    def q(v: np.ndarray[Any, Any]) -> dict[str, float]:
        out = {f"p{qq}": float(np.percentile(v, qq)) for qq in QUANTILES}
        out["max"] = float(v.max())
        return out

    return {
        "component_count": int(sizes.size),
        "area_pixels": q(sizes),
        "area_ha": q(sizes * PIXEL_M * PIXEL_M / 1e4),
        "bbox_width_px": q(bw),
        "bbox_height_px": q(bh),
        "equivalent_diameter_px": q(eqd),
        "equivalent_diameter_m": q(eqd * PIXEL_M),
    }


def window_starts(extent: int, patch: int, stride: int) -> list[int]:
    """Deterministic anchored windows fully inside the extent."""
    starts = list(range(0, extent - patch - stride + 1, stride))
    last = extent - patch
    if not starts or starts[-1] != last:
        starts.append(last)
    return starts


def evaluate_candidate(
    patch: int, silver: np.ndarray[Any, Any],
    weak_only: np.ndarray[Any, Any],
    s_bw: np.ndarray[Any, Any], s_bh: np.ndarray[Any, Any],
    w_bw: dict[int, np.ndarray[Any, Any]],
    w_bh: dict[int, np.ndarray[Any, Any]],
    opt: np.ndarray[Any, Any],
) -> dict[str, Any]:
    h, w = silver.shape
    stride = int(round(patch * STRIDE_FRACTION))

    def containable(bw: np.ndarray[Any, Any],
                     bh: np.ndarray[Any, Any]) -> float:
        need = 2 * CONTEXT_MARGIN_PX
        fits = (bw + need <= patch) & (bh + need <= patch)
        return float(fits.mean()) if bw.size else float("nan")

    rows = window_starts(h, patch, stride)
    cols = window_starts(w, patch, stride)
    n_win = len(rows) * len(cols)

    # coverage/label statistics over the sliding windows
    cov_bins = [0.0, 0.10, 0.25, 0.50, 0.75, 1.01]
    cov_hist = [0] * (len(cov_bins) - 1)
    silver_windows = 0
    covered = np.zeros_like(silver, dtype="uint8")
    silver_bbox_seen = np.zeros(s_bw.size, dtype=bool)
    lab_s, n_s = ndimage.label(silver,
                               structure=np.ones((3, 3), dtype="uint8"))
    for r0 in rows:
        for c0 in cols:
            win = opt[r0:r0 + patch, c0:c0 + patch]
            frac = float(win.mean())
            for i in range(len(cov_bins) - 1):
                if cov_bins[i] <= frac < cov_bins[i + 1]:
                    cov_hist[i] += 1
                    break
            sw = silver[r0:r0 + patch, c0:c0 + patch]
            if sw.any():
                silver_windows += 1
            covered[r0:r0 + patch, c0:c0 + patch] = 1
            ids = np.unique(lab_s[r0:r0 + patch, c0:c0 + patch])
            silver_bbox_seen[ids[ids > 0] - 1] = True

    # edge-truncated objects: SILVER components whose bbox is cut by at
    # least one window border even though they fit the canvas
    trunc = int(((s_bw > patch) | (s_bh > patch)).sum())

    # non-overlapping P x P blocks (independent-unit proxy) on the
    # anchored lattice that carry SILVER pixels or >=50% optical cover
    n_blocks = silver_blocks = valid_blocks = 0
    for r0 in range(0, h - patch + 1, patch):
        for c0 in range(0, w - patch + 1, patch):
            n_blocks += 1
            win = silver[r0:r0 + patch, c0:c0 + patch]
            if win.any():
                silver_blocks += 1
            if opt[r0:r0 + patch, c0:c0 + patch].mean() >= 0.5:
                valid_blocks += 1

    return {
        "patch_px": patch,
        "patch_km": patch * PIXEL_M / 1000.0,
        "stride_px": stride,
        "silver_components_fully_containable_with_context_fraction":
            containable(s_bw, s_bh),
        "silver_components_bbox_too_large_count": trunc,
        "weak_only_material_containable_fraction": {
            str(t): (containable(w_bw[t], w_bh[t]) if w_bw[t].size
                     else None)
            for t in MATERIAL_THRESHOLDS_PX
        },
        "sliding_windows_total": n_win,
        "windows_with_silver": silver_windows,
        "optical_coverage_histogram_fraction": {
            f"{cov_bins[i]:.2f}-{cov_bins[i+1]:.2f}": cov_hist[i]
            for i in range(len(cov_hist))
        },
        "grid_area_covered_by_windows_fraction": float(covered.mean()),
        "disjoint_patch_blocks_total": n_blocks,
        "disjoint_blocks_with_silver": silver_blocks,
        "disjoint_blocks_ge50pct_optical": valid_blocks,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", type=Path,
                    default=Path("work/hangzhou2015/v1"))
    ap.add_argument("--out", type=Path,
                    default=Path("artifacts/audit/pilot0/patch_size_study.json"))
    args = ap.parse_args()

    silver = rasterio.open(args.work_dir / "silver_2015_30m.tif").read(1) == 1
    weak = rasterio.open(args.work_dir / "label_mask_30m.tif").read(1) == 1
    weak_only = weak & ~silver
    stack_path = args.work_dir / "pilot0_stack_30m.tif"
    with rasterio.open(stack_path) as ds:
        sr = ds.read(range(1, 8))
    opt = np.all(np.isfinite(sr), axis=0)

    s_sizes, s_bw, s_bh, s_eqd, _ = component_table(silver)
    w_sizes, w_bw_all, w_bh_all, w_eqd, _ = component_table(weak_only)
    w_bw, w_bh = {}, {}
    for t in MATERIAL_THRESHOLDS_PX:
        m = w_sizes >= t
        w_bw[t], w_bh[t] = w_bw_all[m], w_bh_all[m]

    report = {
        "context_margin_px": CONTEXT_MARGIN_PX,
        "context_margin_m": CONTEXT_MARGIN_PX * PIXEL_M,
        "context_margin_basis": "benchmarks/spartinashift/SPEC.md >=250 m buffer",
        "stride_policy_evaluated": "P/2 sliding windows",
        "silver_components": quantile_block(s_sizes, s_bw, s_bh, s_eqd),
        "weak_only_all_components": quantile_block(
            w_sizes, w_bw_all, w_bh_all, w_eqd),
        "weak_only_material_components": {
            str(t): quantile_block(w_sizes[w_sizes >= t],
                                   w_bw_all[w_sizes >= t],
                                   w_bh_all[w_sizes >= t],
                                   w_eqd[w_sizes >= t])
            for t in MATERIAL_THRESHOLDS_PX
        },
        "candidates": [
            evaluate_candidate(p, silver, weak_only, s_bw, s_bh, w_bw, w_bh,
                               opt)
            for p in CANDIDATES_PX
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False)
                        + "\n", encoding="utf-8")
    for c in cast(list[dict[str, Any]], report["candidates"]):
        csf = c['silver_components_fully_containable_with_context_fraction']
        print(f"P={c['patch_px']:3d} containSilver={csf:.2f} "
              f"tooLarge={c['silver_components_bbox_too_large_count']} "
              f"win={c['sliding_windows_total']:4d} winSilver={c['windows_with_silver']:4d} "
              f"blocksSilver={c['disjoint_blocks_with_silver']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
