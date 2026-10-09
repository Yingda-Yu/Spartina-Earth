#!/usr/bin/env python3
"""Issue #19 F3 -- evidence audit for the S1 extreme-floor validity token.

Owner decision (Issue #19, 2026-10-09): keep raw GEE Sentinel-1 GRD
values exactly; classify values <= -70 dB in either required
polarization as NON_OBSERVATION_EXTREME_FLOOR in a DERIVED validity
token ``s1_dualpol_valid_v2`` only. Before the token is frozen the owner
requires evidence that:

1. minima/quantiles and <= -70 dB fractions are recorded per product;
2. <= -70 dB pixels are spatially associated with partial / frame-edge
   coverage and are not a meaningful interior signal population;
3. masked-area fractions are reported per product.

This script audits every LANDED S1 product manifest plus any vvvh raster
downloaded but rejected at landing validation (quarantined raw evidence
of the F3 finding). It performs no GEE calls and writes no pixels:

* datasets/manifests/national_pilot19_s1_floor_audit_v2.json
* datasets/manifests/national_pilot19_s1_floor_audit_v2.csv

A diagnostic figure for the quarantined floor rasters goes to
work/national/pilot19/qa/ (outside Git). If the rule removes a
substantial or clearly meaningful interior population the verdict is
STOP_OWNER_REVIEW; the threshold is never silently changed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import matplotlib  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from scipy import ndimage  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from spartina.data.gee.provenance import git_context  # noqa: E402

WORK_DIR = REPO_ROOT / "work" / "national" / "pilot19"
MANIFEST_DIR = WORK_DIR / "manifests"
PRODUCT_DIR = WORK_DIR / "products"
QA_DIR = WORK_DIR / "qa"
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_s1_floor_audit_v2.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_s1_floor_audit_v2.csv"

POLICY_TOKEN = "s1_dualpol_valid_v2"
FLOOR_DB: float = -70.0
INTERIOR_MARGINS_M: tuple[int, ...] = (50, 500, 1000)
#: Interior-removal stop rule: beyond the 50 m eroded interior no more
#: than this share of observed pixels may be floor-masked, and no LANDED
#: product with >= 0.95 dual-pol coverage may lose any interior region.
INTERIOR_REMOVAL_HARD_FRACTION = 1e-4
EDGE_LIST_DB = -65.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _band_record(name: str, arr: np.ndarray[Any, Any]) -> dict[str, Any]:
    finite = np.isfinite(arr)
    vals = arr[finite]
    rec: dict[str, Any] = {
        "band": name,
        "finite_fraction": float(finite.mean()),
        "n_finite": int(finite.sum()),
        "n_grid_pixels": int(finite.size),
        "min_db": None,
        "p001_db": None,
        "p01_db": None,
        "p50_db": None,
        "p99_db": None,
        "max_db": None,
        "n_at_or_below_floor": int((finite & (arr <= FLOOR_DB)).sum()),
        "fraction_at_or_below_floor_of_finite": (
            float((finite & (arr <= FLOOR_DB)).sum())
            / max(int(finite.sum()), 1)),
        "discrete_values_at_or_below_minus65_db": [],
    }
    if vals.size:
        pct = np.percentile(vals, [0, 0.1, 1, 50, 99, 100])
        rec.update({
            "min_db": float(pct[0]), "p001_db": float(pct[1]),
            "p01_db": float(pct[2]), "p50_db": float(pct[3]),
            "p99_db": float(pct[4]), "max_db": float(pct[5])})
        low = vals[vals <= EDGE_LIST_DB]
        values, counts = np.unique(np.round(low, 3), return_counts=True)
        rec["discrete_values_at_or_below_minus65_db"] = [
            {"value_db": float(v), "pixels": int(c)}
            for v, c in sorted(
                zip(values, counts, strict=True),
                key=lambda t: int(t[1]), reverse=True)]
    return rec


def _edge_localization(
    observed: np.ndarray[Any, Any],
    floor: np.ndarray[Any, Any],
    resolution_m: float,
) -> dict[str, Any]:
    n_floor = int(floor.sum())
    rec: dict[str, Any] = {
        "n_floor_pixels": n_floor,
        "fraction_of_grid": float(n_floor / floor.size),
        "fraction_of_observed": float(n_floor / max(int(observed.sum()), 1)),
        "beyond_interior_margins_m": {},
        "touching_nonobserved_2px_fraction": None,
        "distance_to_nonobserved_edge_m": {
            "max": None, "p95": None, "p99": None},
    }
    if not observed.any() or n_floor == 0:
        for margin in INTERIOR_MARGINS_M:
            iters = max(1, int(round(margin / resolution_m)))
            interior_size = int(
                ndimage.binary_erosion(observed, iterations=iters).sum())
            rec["beyond_interior_margins_m"][str(margin)] = {
                "pixels": 0,
                "fraction_of_floor": 0.0,
                "fraction_of_observed_interior": (
                    0.0 / max(interior_size, 1)),
            }
        rec["touching_nonobserved_2px_fraction"] = 0.0
        return rec
    for margin in INTERIOR_MARGINS_M:
        iters = max(1, int(round(margin / resolution_m)))
        interior = ndimage.binary_erosion(observed, iterations=iters)
        deep = int((floor & interior).sum())
        rec["beyond_interior_margins_m"][str(margin)] = {
            "pixels": deep,
            "fraction_of_floor": float(deep / n_floor),
            "fraction_of_observed_interior": (
                float(deep / max(int(interior.sum()), 1))),
        }
    outside_dilated = ndimage.binary_dilation(
        ~observed, iterations=2)
    rec["touching_nonobserved_2px_fraction"] = float(
        int((floor & outside_dilated).sum()) / n_floor)
    distance = ndimage.distance_transform_edt(observed) * resolution_m
    rec["distance_to_nonobserved_edge_m"] = {
        "max": float(distance[floor].max()),
        "p95": float(np.percentile(distance[floor], 95)),
        "p99": float(np.percentile(distance[floor], 99))}
    return rec


def audit_raster(path: Path) -> dict[str, Any]:
    with rasterio.open(path) as ds:
        vv = ds.read(1).astype("float64")
        vh = ds.read(2).astype("float64")
        resolution_m = float(ds.res[0])
    finite_vv = np.isfinite(vv)
    finite_vh = np.isfinite(vh)
    observed = finite_vv & finite_vh
    floor = observed & ((vv <= FLOOR_DB) | (vh <= FLOOR_DB))
    valid_v2 = observed & ~floor
    band_records = [
        _band_record("VV", vv), _band_record("VH", vh)]
    edge = _edge_localization(observed, floor, resolution_m)
    # Also record the band-asymmetric frame edge (one polarization
    # present, the other masked): dual-pol observation requires both.
    asymmetric = {
        "vv_present_vh_missing_pixels": int((finite_vv & ~finite_vh).sum()),
        "vh_present_vv_missing_pixels": int((finite_vh & ~finite_vv).sum()),
    }
    return {
        "raster": str(path),
        "resolution_m": resolution_m,
        "grid_height": int(vv.shape[0]),
        "grid_width": int(vv.shape[1]),
        "bands": band_records,
        "dualpol_observed_fraction": float(observed.mean()),
        "s1_dualpol_valid_v2_fraction_of_grid": float(valid_v2.mean()),
        "floor_masked_pixels": int(floor.sum()),
        "floor_masked_fraction_of_observed": (
            float(floor.sum()) / max(int(observed.sum()), 1)),
        "band_asymmetric_frame_edge": asymmetric,
        "floor_edge_localization": edge,
    }


def _policy_decision(records: list[dict[str, Any]]) -> dict[str, Any]:
    violations: list[str] = []
    for r in records:
        deep = r["floor_edge_localization"]["beyond_interior_margins_m"]["50"]
        if (r["evidence_class"] == "LANDED"
                and r["dualpol_observed_fraction"] >= 0.95
                and deep["pixels"] > 0):
            violations.append(
                f"{r['product_id']}: {deep['pixels']} floor pixels beyond "
                "50 m interior in a >=0.95 coverage product")
        if (deep["fraction_of_observed_interior"]
                > INTERIOR_REMOVAL_HARD_FRACTION):
            violations.append(
                f"{r['product_id']}: interior floor fraction "
                f"{deep['fraction_of_observed_interior']:.6f} exceeds "
                f"{INTERIOR_REMOVAL_HARD_FRACTION}")
    return {
        "rule": (
            "s1_dualpol_valid_v2 pixel observed iff VV source mask "
            "present AND VH source mask present AND finite(VV) AND "
            "finite(VH) AND VV > -70 dB AND VH > -70 dB"),
        "semantics": (
            "OBSERVATION_VALIDITY_RULE_ONLY: <= -70 dB is classified "
            "NON_OBSERVATION_EXTREME_FLOOR; not a claim that all values "
            "below -70 dB are physically impossible"),
        "raw_raster_policy": "RAW GEE VALUES PRESERVED EXACTLY; no clipping, "
                            "no replacement, no rewrite; mask is derived",
        "threshold_db": FLOOR_DB,
        "threshold_origin": (
            "owner decision 2026-10-09; provisional conservative value in "
            "the empirical gap between normal bulk minima and the discrete "
            "GEE frame-border floor"),
        "interior_margin_m": 50,
        "interior_removal_hard_fraction": INTERIOR_REMOVAL_HARD_FRACTION,
        "violations": violations,
        "verdict": ("STOP_OWNER_REVIEW" if violations
                    else "POLICY_CONFIRMED_S1_DUALPOL_VALID_V2"),
    }


def _diagnostic_figure(records: list[dict[str, Any]]) -> str | None:
    quarantined = [r for r in records
                   if r["evidence_class"] == "QUARANTINED_UNLANDED"]
    if not quarantined:
        return None
    QA_DIR.mkdir(parents=True, exist_ok=True)
    out = QA_DIR / "s1_extreme_floor_edge_localization.png"
    fig, axes = plt.subplots(
        len(quarantined), 3, figsize=(12, 4 * len(quarantined)))
    if len(quarantined) == 1:
        axes = np.array([axes])
    for row, rec in zip(axes, quarantined, strict=True):
        with rasterio.open(rec["raster"]) as ds:
            vv = ds.read(1).astype("float64")
            vh = ds.read(2).astype("float64")
        obs = np.isfinite(vv) & np.isfinite(vh)
        floor = obs & ((vv <= FLOOR_DB) | (vh <= FLOOR_DB))
        with np.errstate(invalid="ignore"):
            row[0].imshow(np.where(obs, vv, np.nan), cmap="gray",
                          vmin=-25, vmax=0)
            row[0].set_title(f"{rec['product_id']} VV dB")
            row[1].imshow(np.where(obs, vh, np.nan), cmap="gray",
                          vmin=-35, vmax=-10)
            row[1].set_title("VH dB")
            overlay = np.zeros((*obs.shape, 3), dtype="float64")
            overlay[..., 0] = obs
            overlay[..., 2] = floor
            row[2].imshow(overlay)
            row[2].set_title(
                f"observed(red) + floor<=-70(blue): {int(floor.sum())} px")
        for ax in row:
            ax.set_xticks([])
            ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return str(out)


def main() -> int:
    records: list[dict[str, Any]] = []
    landed_pids: set[str] = set()
    for mp in sorted(MANIFEST_DIR.glob("*.json")):
        mf = json.loads(mp.read_text("utf-8"))
        if mf.get("sensor") != "sentinel1":
            continue
        pid = str(mf["product_id"])
        landed_pids.add(pid)
        vvvh = next((f for f in mf["landed_files"]
                     if f["role"] == "vvvh"), None)
        if vvvh is None:
            continue
        rec = audit_raster(Path(vvvh["local_uri"]))
        rec["product_id"] = pid
        rec["evidence_class"] = "LANDED"
        rec["manifest"] = str(mp.relative_to(REPO_ROOT))
        records.append(rec)

    # Quarantined raw rasters (downloaded before landing validation failed
    # on the pre-v2 hard envelope; no manifest/SHA ledger entry).
    for tif in sorted(PRODUCT_DIR.glob("*_S1_*_vvvh_*.tif")):
        pid = tif.name.removeprefix(
            "spartina_pilot19_").split("_vvvh_")[0]
        if pid in landed_pids:
            continue
        rec = audit_raster(tif)
        rec["product_id"] = pid
        rec["evidence_class"] = "QUARANTINED_UNLANDED"
        rec["manifest"] = None
        records.append(rec)

    decision = _policy_decision(records)
    figure = _diagnostic_figure(records)

    csv_rows = []
    for r in records:
        for b in r["bands"]:
            csv_rows.append({
                "product_id": r["product_id"],
                "evidence_class": r["evidence_class"],
                "band": b["band"],
                "dualpol_observed_fraction": r["dualpol_observed_fraction"],
                "s1_dualpol_valid_v2_fraction_of_grid":
                    r["s1_dualpol_valid_v2_fraction_of_grid"],
                "finite_fraction": b["finite_fraction"],
                "min_db": b["min_db"], "p01_db": b["p01_db"],
                "p50_db": b["p50_db"], "p99_db": b["p99_db"],
                "max_db": b["max_db"],
                "n_at_or_below_floor": b["n_at_or_below_floor"],
                "fraction_at_or_below_floor_of_finite":
                    b["fraction_at_or_below_floor_of_finite"],
                "floor_pixels": r["floor_masked_pixels"],
                "floor_fraction_of_observed":
                    r["floor_masked_fraction_of_observed"],
                "floor_beyond_50m_interior_pixels":
                    r["floor_edge_localization"]
                    ["beyond_interior_margins_m"]["50"]["pixels"],
                "floor_touching_nonobserved_fraction":
                    r["floor_edge_localization"]
                    ["touching_nonobserved_2px_fraction"],
            })

    import csv as csv_mod
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv_mod.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

    doc = {
        "product": "national_pilot19_s1_floor_audit_v2",
        "issue": 19,
        "created_utc": _now(),
        "policy_token": POLICY_TOKEN,
        "policy_decision": decision,
        "n_landed_products": int(
            sum(r["evidence_class"] == "LANDED" for r in records)),
        "n_quarantined_unlanded_rasters": int(
            sum(r["evidence_class"] == "QUARANTINED_UNLANDED"
                for r in records)),
        "diagnostic_figure": figure,
        "products": records,
        "git": git_context(REPO_ROOT),
    }
    OUT_JSON.write_text(
        json.dumps(doc, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "verdict": decision["verdict"],
        "landed": doc["n_landed_products"],
        "quarantined": doc["n_quarantined_unlanded_rasters"],
        "violations": decision["violations"],
        "csv": str(OUT_CSV.relative_to(REPO_ROOT)),
        "figure": figure}, indent=2))
    return 0 if decision["verdict"].startswith("POLICY_CONFIRMED") else 3


if __name__ == "__main__":
    raise SystemExit(main())
