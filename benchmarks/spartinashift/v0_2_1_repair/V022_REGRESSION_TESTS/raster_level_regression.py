#!/usr/bin/env python3
"""V022 raster-level regression -- recompute evidence from landed rasters.

Read-only pass over every optical product manifest (panel + repair):
opens the landed sr/valid/qapixel GeoTIFFs and recomputes readability,
per-band finite fractions, VALID pixel count, QA_PIXEL bit census,
nonfinite-inside-QA-valid count and the zero-valid classification.
Nothing is copied from historical manifests; missing files are recorded
with reasons. Output: V022_RASTER_LEVEL_REGRESSION.csv (+ JSON summary).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

REPO_ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
MANIFEST_DIRS = {
    "panel": REPO_ROOT / "work/issue21/export/manifests",
    "repair": REPO_ROOT / "work/issue21/export_repair/manifests",
}
OUT_CSV = HERE / "V022_RASTER_LEVEL_REGRESSION.csv"
OUT_JSON = HERE / "V022_RASTER_LEVEL_REGRESSION_SUMMARY.json"
BITS = ["fill", "dilated_cloud", "cirrus", "cloud",
        "cloud_shadow", "snow", "clear"]


def main() -> int:
    rows, missing, unreadable = [], [], []
    for batch, md in MANIFEST_DIRS.items():
        prod_root = md.parent / "products"
        for p in sorted(md.glob("*.json")):
            m = json.loads(p.read_text())
            pid = m["product_id"]
            if m["sensor"] == "sentinel1":
                continue
            files = {f["role"]: Path(f["local_uri"]) for f in m["landed_files"]}
            row = {"batch": batch, "product_id": pid,
                   "sensor": m["sensor"], "readable": False}
            for role in ("sr", "valid", "qapixel"):
                fp = files.get(role)
                if fp is None or not fp.exists():
                    missing.append({"product_id": pid, "role": role,
                                    "reason": "file not found" if fp is None
                                    else f"path missing: {fp}"})
                    row[f"{role}_missing"] = 1
                else:
                    row[f"{role}_missing"] = 0
            if any(row.get(f"{role}_missing") for role in
                   ("sr", "valid", "qapixel")):
                rows.append(row)
                continue
            try:
                with rasterio.open(files["qapixel"]) as ds:
                    q = ds.read(1).astype(np.uint16)
                with rasterio.open(files["valid"]) as ds:
                    v = ds.read(1)
                with rasterio.open(files["sr"]) as ds:
                    sr = ds.read()
                    n_bands = sr.shape[0]
                row["readable"] = True
                row["n_sr_bands"] = n_bands
                row["valid_pixel_count"] = int((v != 0).sum())
                row["zero_valid"] = int(row["valid_pixel_count"]) == 0
                for b, name in enumerate(BITS):
                    row[f"qabit_{name}"] = int(((q >> b) & 1).sum())
                clear = ((q >> 6) & 1).astype(bool)
                banned = np.zeros(q.shape, dtype=bool)
                for b in range(6):
                    banned |= ((q >> b) & 1).astype(bool)
                qa_valid_set = clear & ~banned
                nonfinite = np.isnan(sr).any(axis=0)
                row["nonfinite_total"] = int(nonfinite.sum())
                row["nonfinite_inside_qa_valid"] = int(
                    (nonfinite & qa_valid_set).sum())
                finite_per_band = [float((~np.isnan(sr[i])).mean())
                                   for i in range(sr.shape[0])]
                row["min_band_finite_fraction"] = min(finite_per_band)
                row["all_finite"] = min(finite_per_band) >= 1.0
                if row["zero_valid"]:
                    row["class_v0_2"] = (
                        "HONEST_REJECTION_ZERO_QA_VALID_SURFACE_PIXELS"
                        if row["all_finite"] else "HARD_ERROR")
                    row["class_v0_2_2"] = (
                        "HONEST_REJECTION_ZERO_QA_VALID_SURFACE_PIXELS"
                        if row["nonfinite_inside_qa_valid"] == 0
                        else "HARD_ERROR")
                else:
                    cls = "ACCEPTED_PARTIAL_FINITE" if not row["all_finite"] \
                        else "accepted"
                    row["class_v0_2"] = row["class_v0_2_2"] = cls
            except Exception as exc:  # noqa: BLE001 -- recorded verbatim
                unreadable.append({"product_id": pid,
                                   "error": f"{type(exc).__name__}: {exc}"})
                row["readable"] = False
                row["error"] = str(exc)[:200]
            rows.append(row)

    fields = sorted({k for r in rows for k in r})
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    summary = {
        "n_optical_products": len(rows),
        "n_readable": sum(1 for r in rows if r.get("readable")),
        "n_missing_files": len(missing),
        "missing_detail": missing,
        "n_unreadable": len(unreadable),
        "unreadable_detail": unreadable,
        "zero_valid_products": [
            r["product_id"] for r in rows if r.get("zero_valid")],
        "v0_2_2_reclassifications": [
            {"product_id": r["product_id"], "from": r["class_v0_2"],
             "to": r["class_v0_2_2"]} for r in rows
            if r.get("class_v0_2") != r.get("class_v0_2_2")],
        "qa_valid_intersection_max": max(
            (r.get("nonfinite_inside_qa_valid", 0) for r in rows),
            default=None)}
    OUT_JSON.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in
                      ("n_optical_products", "n_readable", "n_missing_files",
                       "n_unreadable", "zero_valid_products",
                       "v0_2_2_reclassifications",
                       "qa_valid_intersection_max")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
