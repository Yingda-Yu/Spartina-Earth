#!/usr/bin/env python3
"""Issue #19 measured storage revision (post real-pixel pilot).

Replaces every planning-era byte assumption that the landed Issue #19
pilot can now measure:

* pilot bytes are MEASURED from the 194 product manifests (component
  files, sizes, width/height, dtype), including real L5/L7 float32 LZW
  ratios (the v1 study borrowed an L8 factor, tagged
  ESTIMATE_FLOAT32_LZW_RATIO_BORROWED_FROM_L8_TODO_MEASURE_AT_PHASE_D);
* MINIMAL/STANDARD national figures are EXTRAPOLATED by replaying the
  exact v1 per-scenario grid-pixel decomposition with the pilot-measured
  per-component bytes-per-pixel (national stays EXTRAPOLATED, never
  MEASURED; landsat 9 has no pilot sample and stays TODO_VERIFY).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402

from spartina.data.gee.landsat import sr_bands  # noqa: E402
from spartina.data.gee.provenance import git_context  # noqa: E402

MANIFEST_DIR = REPO_ROOT / "work/national/pilot19/manifests"
V1_JSON = (
    REPO_ROOT / "datasets/manifests/national_pilot19_storage_study_v1.json")
V1_CSV = (
    REPO_ROOT / "datasets/manifests/national_pilot19_storage_study_v1.csv")
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_storage_study_v2.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_storage_study_v2.csv"

#: pilot19 role -> v1 component vocabulary.
ROLE_TO_COMP = {"sr": "sr", "valid": "valid", "qapixel": "qapixel",
                "vvvh": "s1_vvvh"}
DTYPE_BYTES = {"float32": 4.0, "uint16": 2.0, "uint8": 1.0}
TOKEN_MEASURED = "MEASURED_PILOT19_LANDED_BYTES"
TOKEN_EXTRAPOLATED = "EXTRAPOLATED_PILOT19_MEASURED_FACTORS_V1_GRIDS"
TOKEN_L9 = "EXTRAPOLATED_L8_FACTOR_LANDSAT9_TODO_VERIFY"


def load_manifests(expected: int) -> list[dict[str, Any]]:
    mfs = [json.loads(p.read_text())
           for p in sorted(MANIFEST_DIR.glob("*.json"))]
    if len(mfs) != expected:
        print(f"WARNING: {len(mfs)} manifests, expected {expected}; "
              "pilot bytes will be partial", file=sys.stderr)
    return mfs


def component_factor(records: list[dict[str, Any]]) -> dict[str, Any]:
    """bytes-per-pixel and LZW ratio stats for one sensor-component."""
    ratios = np.array([r["lzw_ratio"] for r in records], dtype="float64")
    bpp = np.array([r["actual_bytes"] / r["grid_pixels"]
                    for r in records], dtype="float64")
    return {
        "n_samples": len(records),
        "raw_bytes_per_pixel": records[0]["raw_bytes_per_pixel"],
        "lzw_ratio_mean": float(ratios.mean()),
        "lzw_ratio_min": float(ratios.min()),
        "lzw_ratio_max": float(ratios.max()),
        "bytes_per_pixel_mean": float(bpp.mean()),
        "bytes_per_pixel_min": float(bpp.min()),
        "bytes_per_pixel_max": float(bpp.max()),
        "evidence_token": TOKEN_MEASURED}


def measured_factors(
    mfs: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Per (sensor, role) measured compression + total pilot bytes."""
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_sensor_bytes: dict[str, int] = {}
    total = 0
    excluded: list[dict[str, Any]] = []
    for mf in mfs:
        sensor = str(mf["sensor"])
        by_sensor_bytes[sensor] = by_sensor_bytes.get(sensor, 0) \
            + int(mf["n_bytes"])
        total += int(mf["n_bytes"])
        g = mf["grid_spec"]
        grid_px = int(g["width"]) * int(g["height"])
        paths = {str(f["role"]): f["local_uri"] for f
                 in mf["landed_files"]}
        obs_role = "vvvh" if sensor == "sentinel1" else "sr"
        with rasterio.open(paths[obs_role]) as ds:
            finite = np.isfinite(ds.read()).all(axis=0)
            finite_frac = float(finite.mean())
        for f in mf["landed_files"]:
            role = str(f["role"])
            # Information-free windows (S2 datatake-edge empties, partial
            # S1 footprints) compress anomalously and must not set national
            # factors; they stay counted in landed bytes and are reported.
            if finite_frac < 0.5:
                excluded.append({
                    "product_id": mf["product_id"], "sensor": sensor,
                    "role": role, "finite_fraction": finite_frac,
                    "reason": "observation coverage below 0.5; excluded "
                              "from compression factor estimation"})
                continue
            # band count for raw bytes: sr role has sensor SR bands,
            # qapixel/valid/vvvh declare their own band count implicitly.
            if role == "sr" and sensor.startswith("landsat"):
                n_bands = len(sr_bands(sensor))
            elif role == "sr":  # sentinel-2 four native 10 m bands
                n_bands = 4
            else:
                n_bands = 2 if role == "vvvh" else 1
            dtype = ("float32" if role in ("sr", "vvvh")
                     else "uint16" if role == "qapixel" else "uint8")
            raw_bpp = n_bands * DTYPE_BYTES[dtype]
            buckets.setdefault((sensor, role), []).append({
                "product_id": mf["product_id"],
                "grid_pixels": grid_px,
                "actual_bytes": int(f["size_bytes"]),
                "raw_bytes_per_pixel": raw_bpp,
                "lzw_ratio": grid_px * raw_bpp / int(f["size_bytes"])})
    factors = {f"{s}:{r}": component_factor(recs)
               for (s, r), recs in sorted(buckets.items())}
    totals = {"n_products": len(mfs), "bytes_measured": total,
              "bytes_by_sensor": dict(sorted(by_sensor_bytes.items())),
              "coverage_excluded_components": excluded}
    return factors, totals


def _bundle_bpp(sensor: str, factors: dict[str, dict[str, Any]],
                bound: str) -> float:
    """Sum of component bytes-per-pixel for one sensor bundle."""
    if sensor == "sentinel2":
        roles = ["sr", "valid"]
    elif sensor == "sentinel1":
        roles = ["vvvh"]
    else:  # landsat 5/7/8/9
        roles = ["sr", "qapixel", "valid"]
    # Landsat 9 has no pilot sample: carry the L8 factor explicitly.
    factor_sensor = "landsat8" if sensor == "landsat9" else sensor
    total = 0.0
    for role in roles:
        total += float(factors[f"{factor_sensor}:{role}"][
            "bytes_per_pixel_mean" if bound == "mean"
            else f"bytes_per_pixel_{bound}"])
    return total


def extrapolate_national(
    factors: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    v1 = pd.read_csv(V1_CSV)
    out_rows = []
    totals: dict[str, dict[str, float]] = {}
    for row in v1.to_dict("records"):
        sensor = str(row["sensor"])
        px = float(row["grid_pixels_sum"])
        tokens = {TOKEN_EXTRAPOLATED}
        if sensor == "landsat9":
            tokens.add(TOKEN_L9)
        vals = {}
        for bound in ("min", "mean", "max"):
            try:
                vals[bound] = px * _bundle_bpp(sensor, factors, bound)
            except KeyError:
                vals[bound] = float("nan")
        rec = dict(row)
        rec.update({"bytes_v2_low": vals["min"],
                    "bytes_v2_base": vals["mean"],
                    "bytes_v2_high": vals["max"],
                    "v2_tokens": sorted(tokens)})
        out_rows.append(rec)
        scen = str(row["scenario"])
        d = totals.setdefault(scen, {"low": 0.0, "base": 0.0,
                                     "high": 0.0, "products": 0.0,
                                     "tasks": 0.0})
        d["low"] += vals["min"]
        d["base"] += vals["mean"]
        d["high"] += vals["max"]
        d["products"] += float(row["n_products"])
        d["tasks"] += float(row["n_gee_tasks"])
    pd.DataFrame(out_rows).to_csv(OUT_CSV, index=False)
    return {scen: {"n_products": int(v["products"]),
                   "n_gee_tasks": int(v["tasks"]),
                   "bytes_low": int(round(v["low"])),
                   "bytes_base": int(round(v["base"])),
                   "bytes_high": int(round(v["high"])),
                   "evidence_token": TOKEN_EXTRAPOLATED}
            for scen, v in sorted(totals.items())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expected-products", type=int, default=194)
    args = ap.parse_args()
    mfs = load_manifests(args.expected_products)
    factors, pilot = measured_factors(mfs)
    national = extrapolate_national(factors)
    v1 = json.loads(V1_JSON.read_text())
    revision = {
        "product": "national_pilot19_storage_study_v2",
        "issue": "#19",
        "phase": "D/H measured revision",
        "created_utc": datetime.now(UTC).isoformat(),
        "git": git_context(str(REPO_ROOT)),
        "status": ("MEASURED pilot factors; national figures EXTRAPOLATED"
                   if len(mfs) == args.expected_products
                   else "PARTIAL: fewer than expected manifests"),
        "pilot_measured": pilot,
        "pilot_v1_estimate_bytes_base": (
            v1["pilot_scenario"]["bytes_base"]),
        "pilot_measured_minus_v1_base_bytes": (
            pilot["bytes_measured"]
            - int(v1["pilot_scenario"]["bytes_base"])),
        "measured_component_factors": factors,
        "replaced_assumptions": [{
            "token": "ESTIMATE_FLOAT32_LZW_RATIO_BORROWED_FROM_L8_"
                     "TODO_MEASURE_AT_PHASE_D",
            "replacement": "landsat5:sr and landsat7:sr measured factors",
            "l5_sr_lzw_ratio_mean": factors.get(
                "landsat5:sr", {}).get("lzw_ratio_mean"),
            "l7_sr_lzw_ratio_mean": factors.get(
                "landsat7:sr", {}).get("lzw_ratio_mean"),
            "l8_sr_lzw_ratio_mean": factors.get(
                "landsat8:sr", {}).get("lzw_ratio_mean")}],
        "national_scenarios_recomputed": national,
        "national_v1_comparison": {
            "v1_minimal_base": (
                v1["national_minimal_scenario"]["bytes_base"]),
            "v2_minimal_base": national.get(
                "national_minimal_anchors", {}).get("bytes_base"),
            "v1_standard_note": "v1 standard scenario is narrative-only "
                                "in JSON; pixel decomposition is in CSV",
            "v2_standard_base": national.get(
                "national_standard_annual", {}).get("bytes_base")},
        "evidence_tokens": {
            TOKEN_MEASURED: "real landed pilot component bytes",
            TOKEN_EXTRAPOLATED: "v1 national grid pixels times pilot "
                                "measured per-component bytes-per-pixel",
            TOKEN_L9: "no Landsat-9 pilot product; L8 factor carried "
                      "forward as TODO_VERIFY"}}
    OUT_JSON.write_text(json.dumps(revision, indent=2, ensure_ascii=False))
    print(json.dumps({
        "pilot_measured_bytes": pilot["bytes_measured"],
        "n_products": pilot["n_products"],
        "l5_sr_ratio": factors.get("landsat5:sr", {}).get("lzw_ratio_mean"),
        "l7_sr_ratio": factors.get("landsat7:sr", {}).get("lzw_ratio_mean"),
        "national": national}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
