"""Build the Pilot-0 leakage-proof window manifest + split registry.

Issue #4. Deterministic: same config + source manifest + git commit must
reproduce tile IDs, assignments and fingerprints. No model work here.

Outputs:
  datasets/manifests/hangzhou2015_tiles_v1.{csv,parquet}
  benchmarks/spartinashift/pilot0_splits_v1.json
  work/hangzhou2015/v1/previews/*.png (human QA only, gitignored)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import yaml
from pyproj import Transformer

from spartina.benchmark.splits import (
    AuditInputs,
    choose_stripe_boundaries,
    crossing_component_ids,
    label_components,
    logical_manifest_fingerprint,
    make_regions,
    run_audit,
    violations_to_jsonable,
)
from spartina.benchmark.splits.blocks import SplitRegion
from spartina.benchmark.splits.components import ComponentInfo
from spartina.data.tiling import (
    WindowSpec,
    packed_region_starts,
    tile_id,
    window_bounds,
)

GRID_ID = "HB2015"
MANIFEST_COLUMNS = [
    "tile_id", "source_stack_version", "source_stack_checksum",
    "row_off", "col_off", "height", "width",
    "bounds_utm", "bounds_wgs84", "split",
    "silver_positive_pixels", "silver_eval_pixels", "silver_fraction",
    "weak_positive_pixels", "weak_eval_pixels", "weak_fraction",
    "ignore_pixels", "ignore_fraction",
    "weak_only_candidate_pixels", "weak_only_candidate_fraction",
    "optical_valid_fraction", "sar_valid_fraction",
    "vv_valid_fraction", "vh_valid_fraction", "indices_valid_fraction",
    "optical_available", "sar_available", "indices_available",
    "silver_component_ids", "weak_candidate_component_ids",
    "eligible_for_train", "eligible_for_eval", "exclusion_reason",
    "source_crs", "source_transform",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_inputs(cfg: dict[str, Any]) -> dict[str, str]:
    """Verify source stack/labels checksums against Pilot-0 manifest."""
    with open(cfg["source"]["manifest"], encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    checks = {}
    expected = {
        "stack": Path(cfg["source"]["stack"]),
        "labels": Path(cfg["source"]["labels"]),
    }
    by_name = {Path(r["local_uri"]).name: r["checksum"] for r in rows}
    for key, path in expected.items():
        actual = "sha256:" + sha256_file(path)
        want = by_name.get(path.name)
        if want != actual:
            raise SystemExit(
                f"INPUT CHECKSUM MISMATCH for {path}: {actual} != {want}")
        checks[key] = actual
    return checks


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "UNKNOWN"


def stats_window(mask: np.ndarray[Any, Any]) -> int:
    return int(mask.sum())


def build(records_ctx: dict[str, Any]) -> tuple[list[dict[str, Any]],
                                                dict[str, Any]]:
    cfg = records_ctx["cfg"]
    P = int(cfg["geometry"]["patch_px"])
    S = int(cfg["geometry"]["stride_px"])
    g = int(cfg["geometry"]["guard_band_px"])
    thr = cfg["thresholds"]
    H, W = records_ctx["H"], records_ctx["W"]
    silver = records_ctx["silver"]
    weak = records_ctx["weak"]
    ignore = records_ctx["ignore"]
    wonly_mask = records_ctx["wonly_mask"]
    opt = records_ctx["opt"]
    vv = records_ctx["vv"]
    vh = records_ctx["vh"]
    ind = records_ctx["ind"]

    # --- components --------------------------------------------------------
    s_lab, s_reg = label_components(silver, "silver")
    w_lab_all, _ = label_components(wonly_mask, "weakall")
    w_sizes_all = np.bincount(w_lab_all.ravel())
    material_idx = np.where(
        w_sizes_all[1:] >= int(thr["weak_only_material_min_pixels"]))[0] + 1
    material_mask = np.isin(w_lab_all, material_idx)
    # fresh contiguous labels + registry for the material-only subset
    w_lab, w_reg = label_components(material_mask, "weakcand")

    # column profiles and component spans
    col_silver = silver.sum(axis=0)
    col_valid = opt.sum(axis=0)

    def spans(
        reg: dict[int, ComponentInfo], n: int
    ) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        cmin = np.full(n + 1, W, dtype="int64")
        cmax = np.full(n + 1, -1, dtype="int64")
        for i, info in reg.items():
            cmin[i] = info.bbox_left
            cmax[i] = info.bbox_right - 1
        cmin[0], cmax[0] = 0, -1
        return cmin, cmax

    s_cmin, s_cmax = spans(s_reg, len(s_reg))
    w_cmin, w_cmax = spans(w_reg, len(w_reg))

    # Coverage-aware window viability for the boundary search (geometry +
    # fixed coverage thresholds only; never model accuracy).
    def _integral(
        a: np.ndarray[Any, Any]
    ) -> np.ndarray[Any, Any]:
        c = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
        c[1:, 1:] = a.astype(np.float64).cumsum(0).cumsum(1)
        return c

    ii_opt = _integral(opt)
    ii_vv = _integral(vv)
    ii_vh = _integral(vh)
    ii_ind = _integral(ind)
    ii_ig = _integral(ignore)
    ii_se = _integral(silver & ~ignore)

    def _component_integrals(
        lab: np.ndarray[Any, Any], n: int
    ) -> np.ndarray[Any, Any]:
        out = np.zeros((n + 1, H + 1, W + 1), dtype=np.int32)
        for i in range(1, n + 1):
            out[i, 1:, 1:] = np.cumsum(
                np.cumsum(lab == i, axis=0, dtype=np.int32), axis=1,
                dtype=np.int32)
        return out

    ii_scomp = _component_integrals(s_lab, len(s_reg))
    ii_wcomp = _component_integrals(w_lab, len(w_reg))

    def _box(c: np.ndarray[Any, Any], r0: int, c0: int) -> float:
        return float(c[r0 + P, c0 + P] - c[r0, c0 + P]
                     - c[r0 + P, c0] + c[r0, c0])

    row_starts = packed_region_starts(H, P, S, 0, H)

    def region_window_stats(
        lo: int, hi: int,
        blocked_s: set[int], blocked_w: set[int],
    ) -> tuple[int, int, int]:
        cols = packed_region_starts(W, P, S, lo, hi)
        n_viable = 0
        n_silver = 0
        nn = float(P * P)
        for c0 in cols:
            for r0 in row_starts:
                if (_box(ii_opt, r0, c0) / nn
                        < float(thr["min_optical_valid_fraction"])
                        or min(_box(ii_vv, r0, c0), _box(ii_vh, r0, c0))
                        / nn < float(thr["min_sar_valid_fraction"])
                        or _box(ii_ind, r0, c0) / nn
                        < float(thr["min_indices_valid_fraction"])
                        or _box(ii_ig, r0, c0) / nn
                        > float(thr["max_ignore_fraction"])):
                    continue
                quarantined = any(
                    int(ii_scomp[i, r0 + P, c0 + P]
                        - ii_scomp[i, r0, c0 + P] - ii_scomp[i, r0 + P, c0]
                        + ii_scomp[i, r0, c0]) > 0 for i in blocked_s) or any(
                    int(ii_wcomp[i, r0 + P, c0 + P]
                        - ii_wcomp[i, r0, c0 + P] - ii_wcomp[i, r0 + P, c0]
                        + ii_wcomp[i, r0, c0]) > 0 for i in blocked_w)
                if quarantined:
                    continue
                n_viable += 1
                if _box(ii_se, r0, c0) >= 1:
                    n_silver += 1
        return len(cols), n_viable, n_silver

    b1, b2, boundary_diag = choose_stripe_boundaries(
        W, col_silver, col_valid,
        s_cmin[1:], s_cmax[1:], w_cmin[1:], w_cmax[1:],
        P, g, region_window_stats,
        int(cfg["splits"].get("min_column_tracks", 2)),
        int(cfg["splits"].get("min_eval_windows", 5)),
    )
    regions = make_regions(W, b1, b2, g)

    quarantined_silver = (crossing_component_ids(s_lab, b1)
                          | crossing_component_ids(s_lab, b2))
    quarantined_weak = (crossing_component_ids(w_lab, b1)
                        | crossing_component_ids(w_lab, b2))

    # --- windows -----------------------------------------------------------
    to_wgs = Transformer.from_crs(cfg["source"]["crs"], "EPSG:4326",
                                  always_xy=True).transform
    gt = records_ctx["grid_transform"]
    records: list[dict[str, Any]] = []

    for split in ("train", "val", "test"):
        region = regions[split]
        col_starts = packed_region_starts(
            W, P, S, region.usable_start, region.usable_end)
        for r0 in row_starts:
            for c0 in col_starts:
                win = (slice(r0, r0 + P), slice(c0, c0 + P))
                n = P * P
                w_silver = silver[win]
                w_weak = weak[win]
                w_ignore = ignore[win]
                w_wonly = wonly_mask[win]
                w_opt = opt[win]
                w_vv = vv[win]
                w_vh = vh[win]
                w_ind = ind[win]
                n_s = stats_window(w_silver)
                n_w = stats_window(w_weak)
                n_ig = stats_window(w_ignore)
                n_wo = stats_window(w_wonly & material_mask[win])
                s_eval = int((w_silver & ~w_ignore).sum())
                wk_eval = int((w_weak & ~w_ignore).sum())
                of = float(w_opt.mean())
                vvf, vhf = float(w_vv.mean()), float(w_vh.mean())
                sf = min(vvf, vhf)
                inf = float(w_ind.mean())
                sids = {int(i) for i in np.unique(s_lab[win]) if i > 0}
                wids = {int(i) for i in np.unique(w_lab[win]) if i > 0}
                touched_q = bool(sids & quarantined_silver) or bool(
                    wids & quarantined_weak)

                reasons = []
                if of < float(thr["min_optical_valid_fraction"]):
                    reasons.append("insufficient_optical_coverage")
                if min(vvf, vhf) < float(thr["min_sar_valid_fraction"]):
                    reasons.append("insufficient_sar_coverage")
                if inf < float(thr["min_indices_valid_fraction"]):
                    reasons.append("insufficient_indices_coverage")
                if n_ig / n > float(thr["max_ignore_fraction"]):
                    reasons.append("too_much_ignore")
                if touched_q:
                    reasons.append("quarantined_component")
                blocked = bool(reasons)

                west, south, east, north = window_bounds(
                    gt, WindowSpec(r0, c0, P, P))
                lon0, lat0 = to_wgs(west, south)
                lon1, lat1 = to_wgs(east, north)

                rec_split = None if blocked else split
                records.append({
                    "candidate_split": split,
                    "tile_id": tile_id(GRID_ID, r0, c0, P),
                    "source_stack_version": cfg["source"]["stack_version"],
                    "source_stack_checksum":
                        records_ctx["checksums"]["stack"],
                    "row_off": r0, "col_off": c0, "height": P, "width": P,
                    "bounds_utm": [west, south, east, north],
                    "bounds_wgs84": [lon0, lat0, lon1, lat1],
                    "split": rec_split,
                    "silver_positive_pixels": n_s,
                    "silver_eval_pixels": s_eval,
                    "silver_fraction": n_s / n,
                    "weak_positive_pixels": n_w,
                    "weak_eval_pixels": wk_eval,
                    "weak_fraction": n_w / n,
                    "ignore_pixels": n_ig,
                    "ignore_fraction": n_ig / n,
                    "weak_only_candidate_pixels": n_wo,
                    "weak_only_candidate_fraction": n_wo / n,
                    "optical_valid_fraction": of,
                    "sar_valid_fraction": sf,
                    "vv_valid_fraction": vvf,
                    "vh_valid_fraction": vhf,
                    "indices_valid_fraction": inf,
                    "optical_available": of >= float(
                        thr["min_optical_valid_fraction"]),
                    "sar_available": sf >= float(
                        thr["min_sar_valid_fraction"]),
                    "indices_available": inf >= float(
                        thr["min_indices_valid_fraction"]),
                    "silver_component_ids": sorted(
                        s_reg[i].component_id for i in sids
                        if i not in quarantined_silver) if not blocked
                        else [],
                    "weak_candidate_component_ids": sorted(
                        w_reg[i].component_id for i in wids
                        if i in w_reg and i not in quarantined_weak)
                        if not blocked else [],
                    "eligible_for_train": (not blocked) and split == "train",
                    "eligible_for_eval": (
                        not blocked and split in {"val", "test"}
                        and s_eval >= int(
                            thr["min_silver_eval_pixels_for_metric"])),
                    "exclusion_reason": ";".join(reasons),
                    "source_crs": cfg["source"]["crs"],
                    "source_transform": [gt.a, gt.b, gt.c, gt.d, gt.e, gt.f],
                })

    diagnostics = collect_diagnostics(records, regions, s_reg, w_reg,
                                      s_lab, w_lab, quarantined_silver,
                                      quarantined_weak, b1, b2, g,
                                      boundary_diag, records_ctx)
    return records, diagnostics


def collect_diagnostics(
    records: list[dict[str, Any]],
    regions: dict[str, SplitRegion],
    s_reg: dict[int, ComponentInfo],
    w_reg: dict[int, ComponentInfo],
    s_lab: np.ndarray[Any, Any],
    w_lab: np.ndarray[Any, Any],
    q_silver: set[int], q_weak: set[int],
    b1: int, b2: int, g: int,
    boundary_diag: dict[str, Any], ctx: dict[str, Any],
) -> dict[str, Any]:
    """Per-split aggregate statistics and component registry."""
    splits = ("train", "val", "test")
    per: dict[str, Any] = {}
    for sp in splits:
        rs = [r for r in records if r["split"] == sp]
        n = sum(r["height"] * r["width"] for r in rs)
        per[sp] = {
            "windows_total_placed": len(rs),
            "eligible_train_windows": sum(r["eligible_for_train"] for r in rs),
            "eligible_eval_windows": sum(r["eligible_for_eval"] for r in rs),
            "silver_positive_pixels": sum(r["silver_positive_pixels"]
                                          for r in rs),
            "silver_eval_pixels": sum(r["silver_eval_pixels"] for r in rs),
            "weak_positive_pixels": sum(r["weak_positive_pixels"]
                                        for r in rs),
            "ignore_pixels": sum(r["ignore_pixels"] for r in rs),
            "weak_only_candidate_pixels": sum(
                r["weak_only_candidate_pixels"] for r in rs),
            "window_area_pixels": n,
            "mean_ignore_fraction": (sum(r["ignore_fraction"] for r in rs)
                                     / len(rs)) if rs else None,
            "mean_optical_valid_fraction": (
                sum(r["optical_valid_fraction"] for r in rs) / len(rs))
            if rs else None,
            "mean_sar_valid_fraction": (
                sum(r["sar_valid_fraction"] for r in rs) / len(rs))
            if rs else None,
            "excluded_window_reasons": exclusion_counts(records, sp),
        }

    # usable interior area profiles (region-level, not window-union)
    silver = ctx["silver"]
    opt = ctx["opt"]
    region_rows = {}
    for sp in splits:
        a, b = regions[sp].usable_start, regions[sp].usable_end
        region_rows[sp] = {
            "usable_columns": [a, b],
            "usable_area_pixels": (b - a) * ctx["H"],
            "optical_valid_pixels": int(opt[:, a:b].sum()),
            "silver_pixels": int(silver[:, a:b].sum()),
        }

    def comp_entries(
        reg: dict[int, ComponentInfo],
        lab: np.ndarray[Any, Any],
        qset: set[int],
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        covered: dict[int, list[str]] = {}
        split_of: dict[int, str | None] = {}
        for r in records:
            if r["split"] is None:
                continue
            ids = np.unique(lab[r["row_off"]:r["row_off"] + r["height"],
                               r["col_off"]:r["col_off"] + r["width"]])
            for i in ids:
                i = int(i)
                if i and i not in qset:
                    covered.setdefault(i, []).append(r["tile_id"])
                    if split_of.get(i) is None:
                        split_of[i] = r["split"]
        out = []
        for i, info in reg.items():
            out.append({
                "component_id": info.component_id,
                "pixel_count": info.pixel_count,
                "area_ha": round(info.area_ha, 4),
                "bbox_top_left_bottom_right_px": [
                    info.bbox_top, info.bbox_left,
                    info.bbox_bottom, info.bbox_right],
                "bbox_width_px": info.bbox_width_px,
                "bbox_height_px": info.bbox_height_px,
                "centroid_row_col": [round(info.centroid_row, 2),
                                     round(info.centroid_col, 2)],
                "assigned_split": ("QUARANTINED" if i in qset
                                   else split_of.get(i, "GUARD_ZONE_ONLY")),
                "quarantined": i in qset,
                "usable_in_eligible_windows": bool(covered.get(i)),
                "window_tile_ids": covered.get(i, []),
            })
        return out

    comps = {
        "silver": comp_entries(s_reg, s_lab, q_silver, records),
        "weak_only_material": comp_entries(w_reg, w_lab, q_weak, records),
    }
    return {
        "boundaries_columns": {"train_val": b1, "val_test": b2},
        "guard_px": g,
        "boundary_search": boundary_diag,
        "regions": {sp: {"owner": [regions[sp].owner_start,
                                   regions[sp].owner_end],
                         "usable": [regions[sp].usable_start,
                                    regions[sp].usable_end]}
                    for sp in splits},
        "per_split": per,
        "region_pixel_accounting": region_rows,
        "components": comps,
        "quarantined": {
            "silver_component_ids": sorted(s_reg[i].component_id
                                           for i in q_silver),
            "weak_component_ids": sorted(w_reg[i].component_id
                                        for i in q_weak if i in w_reg),
        },
    }


def exclusion_counts(
    records: list[dict[str, Any]], sp: str
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        if r.get("candidate_split") != sp or not r["exclusion_reason"]:
            continue
        for reason in r["exclusion_reason"].split(";"):
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def write_manifest(records: list[dict[str, Any]], csv_path: Path,
                   parquet_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS,
                           extrasaction="ignore")
        w.writeheader()
        for r in records:
            row = dict(r)
            row["bounds_utm"] = json.dumps(r["bounds_utm"])
            row["bounds_wgs84"] = json.dumps(r["bounds_wgs84"])
            row["silver_component_ids"] = json.dumps(r["silver_component_ids"])
            row["weak_candidate_component_ids"] = json.dumps(
                r["weak_candidate_component_ids"])
            row["source_transform"] = json.dumps(r["source_transform"])
            w.writerow(row)
    try:
        import pandas as pd

        pd.DataFrame([
            {k: (json.dumps(r[k]) if isinstance(r[k], list | dict)
                 else r[k]) for k in MANIFEST_COLUMNS}
            for r in records
        ], columns=MANIFEST_COLUMNS).to_parquet(parquet_path, index=False)
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path,
                    default=Path("configs/data/hangzhou2015_pilot0.yaml"))
    ap.add_argument("--tiles-csv", type=Path,
                    default=Path("datasets/manifests/hangzhou2015_tiles_v1.csv"))
    ap.add_argument("--tiles-parquet", type=Path,
                    default=Path(
                        "datasets/manifests/hangzhou2015_tiles_v1.parquet"))
    ap.add_argument("--split-json", type=Path,
                    default=Path(
                        "benchmarks/spartinashift/pilot0_splits_v1.json"))
    ap.add_argument("--no-previews", action="store_true")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    checks = verify_inputs(cfg)

    with rasterio.open(cfg["source"]["stack"]) as ds:
        stack = ds.read()
        gt = ds.transform
        H, W = ds.height, ds.width
        crs = str(ds.crs)
    silver = rasterio.open(cfg["source"]["silver"]).read(1) == 1
    with rasterio.open(cfg["source"]["labels"]) as ds:
        weak = ds.read(1) == 1
        ignore = ds.read(3) == 1
    disagreement = rasterio.open(cfg["source"]["disagreement"]).read(1)
    wonly_mask = disagreement == 3
    opt = np.all(np.isfinite(stack[0:7]), axis=0)
    vv = np.isfinite(stack[9])
    vh = np.isfinite(stack[10])
    ind = np.isfinite(stack[7]) & np.isfinite(stack[8])

    ctx = {"cfg": cfg, "H": H, "W": W, "silver": silver, "weak": weak,
           "ignore": ignore, "wonly_mask": wonly_mask, "opt": opt,
           "vv": vv, "vh": vh, "ind": ind, "grid_transform": gt,
           "checksums": checks}
    records, diag = build(ctx)

    # --- audit (hard fail) -------------------------------------------------
    usable_regions = {sp: tuple(diag["regions"][sp]["usable"])
                      for sp in ("train", "val", "test")}
    audit_in = AuditInputs(
        records=records, regions=usable_regions,
        guard_px=int(cfg["geometry"]["guard_band_px"]),
        expected_stack_checksum=checks["stack"],
        expected_crs=crs,
        expected_transform=tuple(
            [gt.a, gt.b, gt.c, gt.d, gt.e, gt.f]),
        patch=int(cfg["geometry"]["patch_px"]),
        label_arrays={"silver": silver, "weak": weak, "ignore": ignore},
    )
    violations = run_audit(audit_in)
    if violations:
        for v in violations:
            print("HARD FAIL", v.code, v.detail)
        return 2

    write_manifest(records, args.tiles_csv, args.tiles_parquet)
    container_hash = (sha256_file(args.tiles_parquet)
                      if args.tiles_parquet.exists() else None)

    fp_logical = logical_manifest_fingerprint(records)
    config_fp_input = json.loads(json.dumps(cfg))  # plain data
    from spartina.benchmark.splits import split_config_fingerprint
    fp_config = split_config_fingerprint(config_fp_input)

    split_doc = {
        "schema_version": "v1",
        "dataset_id": cfg["dataset_id"],
        "generated_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "git_commit": git_commit(),
        "config_path": str(args.config),
        "config": cfg,
        "config_fingerprint_sha256": fp_config,
        "source": {
            "stack": cfg["source"]["stack"],
            "stack_checksum": checks["stack"],
            "labels_checksum": checks["labels"],
            "crs": crs,
            "transform": [gt.a, gt.b, gt.c, gt.d, gt.e, gt.f],
            "width": W, "height": H, "stack_bands": 11,
        },
        "splits": diag,
        "window_manifest": {
            "csv": str(args.tiles_csv),
            "parquet": str(args.tiles_parquet),
            "parquet_container_sha256": container_hash,
            "logical_manifest_fingerprint_sha256": fp_logical,
            "n_records": len(records),
        },
        "audit": {
            "pass": True,
            "n_violations": 0,
            "violations": violations_to_jsonable(violations),
            "checks": [
                "shared_source_pixel", "cross_split_window_overlap",
                "window_crossing_split_boundary", "guard_distance",
                "silver_component_single_split",
                "weak_material_component_single_split",
                "duplicate_tile_id", "duplicate_source_window",
                "crs_consistency", "transform_consistency",
                "manifest_checksum", "valid_label_values",
                "ignore_handling", "temporal_identity_reserved"],
        },
        "label_policy": {
            "gold_available": False,
            "silver": "SILVER evaluation reference",
            "weak": "WEAK auxiliary only",
            "ignore": "excluded from loss / denominator / confusion",
            "weak_only_material": "tracked; never SILVER truth",
        },
    }
    args.split_json.parent.mkdir(parents=True, exist_ok=True)
    args.split_json.write_text(
        json.dumps(split_doc, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n", encoding="utf-8")

    if not args.no_previews:
        render_previews(records, diag, cfg, Path("work/hangzhou2015/v1"))

    print("boundaries:", diag["boundaries_columns"])
    for sp in ("train", "val", "test"):
        p = diag["per_split"][sp]
        print(sp, "windows", p["windows_total_placed"],
              "eligible_eval", p["eligible_eval_windows"],
              "silver_px", p["silver_positive_pixels"],
              "exclusions", p["excluded_window_reasons"])
    print("logical fingerprint:", fp_logical)
    print(f"-> {args.tiles_csv} / {args.split_json}")
    return 0


def render_previews(records: list[dict[str, Any]],
                    diag: dict[str, Any], cfg: dict[str, Any],
                    out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

    P = int(cfg["geometry"]["patch_px"])
    silver = rasterio.open(cfg["source"]["silver"]).read(1)
    weak = rasterio.open(cfg["source"]["labels"]).read(1)
    ndvi = rasterio.open(cfg["source"]["stack"]).read(8)
    b1 = diag["boundaries_columns"]["train_val"]
    b2 = diag["boundaries_columns"]["val_test"]
    g = diag["guard_px"]
    fig, ax = plt.subplots(figsize=(15, 7))
    ax.imshow(np.nan_to_num(ndvi, nan=0.0), cmap="gray", vmin=-0.2,
              vmax=0.5)
    ax.imshow(np.where(silver == 1, 1, np.nan), cmap="Greens", alpha=0.6)
    ax.imshow(np.where((weak == 1) & (silver == 0), 1, np.nan),
              cmap="Reds", alpha=0.6)
    colors = {"train": "tab:blue", "val": "tab:orange",
              "test": "tab:green"}
    for r in records:
        if r["split"] is None:
            continue
        ax.add_patch(patches.Rectangle(
            (r["col_off"], r["row_off"]), P, P, linewidth=0.6,
            edgecolor=colors[r["split"]], facecolor="none"))
    for x in (b1, b2):
        ax.axvline(x, color="white", linestyle="--", lw=1)
        ax.axvspan(x - g, x + g, color="yellow", alpha=0.15)
    ax.set_title("Pilot-0 split: train/val/test stripes + guard bands"
                 " (green=SILVER, red=WEAK-only)")
    fig.tight_layout()
    pv = out_dir / "previews"
    pv.mkdir(parents=True, exist_ok=True)
    fig.savefig(pv / "split_overview.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
