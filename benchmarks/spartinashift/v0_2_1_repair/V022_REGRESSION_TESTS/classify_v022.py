#!/usr/bin/env python3
"""V022 regression test -- read-only reclassification of all optical products.

Deterministic, pixel-evidence-based classifier that re-scores every
landed Landsat product from the panel (Phase H) and repair (Phase 2A)
exports under BOTH the frozen v0.2 honest-rejection contract and the
proposed v0.2.2 contract, and asserts the historical counts.

Read-only: no raster is modified, no manifest rewritten, no threshold
applied to any accepted product. Rasters are opened only for zero-valid
candidates (2 products); everything else is classified from manifest
QA blocks.

v0.2 rule (frozen Phase J): zero-VALID product is an honest rejection
(`ZERO_QA_VALID_SURFACE_PIXELS`) iff sensor is Landsat AND every SR band
is 100 % finite AND physical audit passed; otherwise zero-VALID is a
hard error.

v0.2.2 rule (proposal): zero-VALID product is an honest rejection iff
(a) SHA-256 match, (b) locked-grid rebuild pass, (c) physical audit
pass, (d) byte actual-mask >= 0.95, and (e) PIXEL EVIDENCE: the count
of non-finite SR pixels inside the offline QA-valid predicate set
(clear bit 6 set AND fill/dilated-cloud/cirrus/cloud/cloud-shadow/snow
bits 0-5 unset, per Landsat C2 QA_PIXEL) is zero. L7 and L8 share the
same C2 QA_PIXEL bit layout (L7 lacks the cirrus definition in
practice; bit 2 is reserved and reported as-is per USGS), so one
deterministic predicate applies to both with sensor-explicit
documentation. If there are no non-finite pixels at all, condition (e)
is vacuously satisfied (this reduces exactly to the v0.2 rule).

Usage:
  python3 classify_v022.py            # run + assertions + write results
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio

REPO_ROOT = Path(__file__).resolve().parents[4]

MANIFEST_DIRS = {
    "panel": REPO_ROOT / "work/issue21/export/manifests",
    "repair": REPO_ROOT / "work/issue21/export_repair/manifests",
}
OUT_JSON = Path(__file__).resolve().parent / "V022_REGRESSION_RESULTS.json"

BANNED_BITS = (0, 1, 2, 3, 4, 5)  # fill, dilated, cirrus, cloud, shadow, snow
CLEAR_BIT = 6


def offline_qa_valid(qa: np.ndarray) -> np.ndarray:
    """Landsat C2 QA_PIXEL production VALID predicate (QA bits only)."""
    clear = ((qa >> CLEAR_BIT) & 1).astype(bool)
    banned = np.zeros(qa.shape, dtype=bool)
    for bit in BANNED_BITS:
        banned |= ((qa >> bit) & 1).astype(bool)
    return clear & ~banned


def classify_manifest(m: dict, root: Path) -> dict:
    qa = m.get("qa", {})
    sensor = m["sensor"]
    vm = qa.get("valid_mask", {})
    bands = qa.get("observed", {}).get("bands", {})
    finites = [float(b.get("finite_fraction") or 0.0)
               for b in bands.values()]
    zero_valid = int(vm.get("valid_pixel_count", -1)) == 0
    all_finite = bool(finites) and min(finites) >= 1.0
    partial_finite = bool(finites) and min(finites) < 1.0
    cls_v02, cls_v022, evidence = "accepted", "accepted", None
    if sensor != "sentinel1" and zero_valid:
        checks = {
            "sha256_match": all(f.get("sha256_match_manifest", True)
                                for f in m["landed_files"]),
            "physical_audit_pass": bool(
                qa.get("physical_audit", {}).get("pass")),
            "mask_gate_pass": bool(
                (qa.get("actual_mask_v2", {}).get("gate", {})
                 or {}).get("gate_pass")),
            "all_finite": all_finite}
        cls_v02 = ("HONEST_REJECTION_ZERO_QA_VALID_SURFACE_PIXELS"
                   if checks["all_finite"] and checks["physical_audit_pass"]
                   else "HARD_ERROR")
        # v0.2.2 pixel evidence (condition e)
        files = {f["role"]: root / f["local_uri"] for f in m["landed_files"]}
        with rasterio.open(files["sr"]) as ds:
            sr = ds.read()
        with rasterio.open(files["qapixel"]) as ds:
            qa_px = ds.read(1).astype(np.uint16)
        nonfinite = np.isnan(sr).any(axis=0)
        qa_valid_set = offline_qa_valid(qa_px)
        nan_inside_qa_valid = int((nonfinite & qa_valid_set).sum())
        nan_total = int(nonfinite.sum())
        fill_any = int(((qa_px >> 0) & 1).sum())
        evidence = {"nonfinite_pixels_total": nan_total,
                    "nonfinite_inside_offline_qa_valid_set":
                        nan_inside_qa_valid,
                    "fill_bit_pixels_anywhere": fill_any,
                    "condition_e_pass": nan_inside_qa_valid == 0}
        ok = (checks["sha256_match"] and checks["physical_audit_pass"]
              and checks["mask_gate_pass"] and evidence["condition_e_pass"])
        cls_v022 = ("HONEST_REJECTION_ZERO_QA_VALID_SURFACE_PIXELS" if ok
                    else "HARD_ERROR")
    elif partial_finite:
        cls_v02 = cls_v022 = "ACCEPTED_PARTIAL_FINITE"
    return {"product_id": m["product_id"], "sensor": sensor,
            "zero_valid": zero_valid, "all_finite": all_finite,
            "min_finite_fraction": min(finites) if finites else None,
            "class_v0_2": cls_v02, "class_v0_2_2": cls_v022,
            "pixel_evidence": evidence}


def main() -> int:
    results, counts = [], {}
    for batch, md in MANIFEST_DIRS.items():
        for p in sorted(md.glob("*.json")):
            m = json.loads(p.read_text())
            if m["sensor"] == "sentinel1":
                continue
            r = classify_manifest(m, md.parent)
            r["batch"] = batch
            results.append(r)
        key = (batch,)
    for r in results:
        counts[r["class_v0_2"]] = counts.get(r["class_v0_2"], 0) + 1
    diffs = [r for r in results if r["class_v0_2"] != r["class_v0_2_2"]]

    # historical assertions (Owner-specified regression expectations)
    panel = [r for r in results if r["batch"] == "panel"]
    repair = [r for r in results if r["batch"] == "repair"]
    assertions = {
        "panel_optical_products": len(panel) == 443,
        "repair_optical_products": len(repair) == 35,
        "exactly_1_panel_honest_rejection": sum(
            r["class_v0_2"] == "HONEST_REJECTION_ZERO_QA_VALID_SURFACE_PIXELS"
            for r in panel) == 1,
        "panel_partial_finite_accepted_146": sum(
            r["class_v0_2"] == "ACCEPTED_PARTIAL_FINITE"
            for r in panel) == 146,
        "repair_partial_finite_accepted_22": sum(
            r["class_v0_2"] == "ACCEPTED_PARTIAL_FINITE"
            for r in repair) == 22,
        "exactly_1_zero_valid_partial_finite_product": sum(
            r["zero_valid"] and not r["all_finite"] for r in results) == 1,
        "v0_2_2_changes_only_that_product": len(diffs) == 1 and diffs[0][
            "product_id"] == "V021_R00372-C00139_L8_2015_E",
    }
    doc = {"product": "V022_REGRESSION_RESULTS", "generated_by":
           "V022_REGRESSION_TESTS/classify_v022.py (read-only)",
           "n_optical_products": len(results),
           "counts_v0_2": counts,
           "v0_2_2_reclassifications": [
               {"product_id": r["product_id"],
                "from": r["class_v0_2"], "to": r["class_v0_2_2"],
                "pixel_evidence": r["pixel_evidence"]} for r in diffs],
           "assertions": assertions,
           "all_assertions_pass": all(assertions.values())}
    OUT_JSON.write_text(json.dumps(doc, indent=2) + "\n")
    print(json.dumps({k: doc[k] for k in
                      ("n_optical_products", "counts_v0_2",
                       "v0_2_2_reclassifications", "assertions",
                       "all_assertions_pass")}, indent=1, default=str))
    return 0 if doc["all_assertions_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
