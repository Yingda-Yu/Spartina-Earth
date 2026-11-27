#!/usr/bin/env python3
"""Executable failure analysis for frozen C2 (evidence, not narrative).

Recomputes, from frozen Issue #19 V2 bytes only:

1. pure-positive support and its EO-valid overlap per positive cell;
2. within-scene spectral separability of CMSA positives (NDVI/bands);
3. RF same-scene overfit ceiling (best threshold on the SAME grid);
4. RF cross-scene transfer between the two spectrally separable sites;
5. RF same-scene 2020 -> 2021 temporal transfer;
6. single-date acquisition gaps from the frozen event plan.

All RF fits use the frozen model config (300 trees, min_samples_leaf=2,
balanced_subsample). The point is to localise why the held-out ladders
fail: pipeline defect vs. pilot support ceiling.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
import sys  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "src"))
from spartina.benchmark.silver.data import load_cell_arrays, target_masks  # noqa: E402

BENCH = REPO_ROOT / "benchmarks" / "spartinashift" / "silver_v0_1"
POSITIVE_CELLS = (
    "CNA10K-R00311-C00156", "CNA10K-R00349-C00154",
    "CNA10K-R00236-C00083", "CNA10K-R00334-C00163",
    "CNA10K-R00413-C00121")
GRID = np.round(np.arange(0.05, 0.9501, 0.01), 2)
SAMPLE = 40_000


def _arrays(cell: str, year: int) -> Any:
    return load_cell_arrays(
        cell, f"NP19_{cell[7:]}_S2_{year}", f"CMSA_{year}")


def _view(cell: str, year: int) -> tuple[Any, Any, np.ndarray[Any, Any]]:
    a = _arrays(cell, year)
    m = target_masks(a.fraction, a.occ_class, "CMSA", year)
    finite = np.isfinite(a.features).all(axis=0)
    return a, m, finite


def _best_iou(
    prob: np.ndarray[Any, Any], y: np.ndarray[Any, Any],
    bv: np.ndarray[Any, Any],
) -> float:
    best = 0.0
    pp = np.nan_to_num(prob)
    for t in GRID:
        pr = (pp >= t) & bv
        tp = int((pr & y).sum())
        fp = int((pr & ~y & bv).sum())
        fn = int((~pr & y & bv).sum())
        if tp + fp + fn:
            best = max(best, tp / (tp + fp + fn))
    return float(best)


def _rf_proba(
    f_train: np.ndarray[Any, Any],
    bv_train: np.ndarray[Any, Any],
    y_train: np.ndarray[Any, Any],
    f_test: np.ndarray[Any, Any],
    bv_test: np.ndarray[Any, Any], seed: int = 0,
) -> tuple[np.ndarray[Any, Any], Any]:
    from sklearn.ensemble import RandomForestClassifier
    rng = np.random.default_rng(seed)
    sel = rng.choice(np.flatnonzero(bv_train),
                     size=min(SAMPLE, int(bv_train.sum())), replace=False)
    rf = RandomForestClassifier(
        n_estimators=300, min_samples_leaf=2,
        class_weight="balanced_subsample", max_features="sqrt",
        n_jobs=8, random_state=seed)
    rf.fit(f_train.reshape(f_train.shape[0], -1)[:, sel].T,
           y_train.ravel()[sel].astype(np.int8))
    pos = int(np.flatnonzero(rf.classes_ == 1)[0])
    idx = np.flatnonzero(bv_test)
    out = np.zeros(bv_test.shape, dtype=np.float32).ravel()
    if idx.size:
        out[idx] = rf.predict_proba(
            f_test.reshape(f_test.shape[0], -1)[:, idx].T)[:, pos]
    return out.reshape(bv_test.shape), rf


def main() -> int:
    findings: dict[str, Any] = {"diagnostic": "C2_failure_analysis"}

    # 1-2. support, EO validity, separability
    support = []
    for cell in POSITIVE_CELLS:
        a, m, finite = _view(cell, 2020)
        bv = m["binary_valid"] & finite
        pos = m["y"] & finite
        bg = ~m["y"] & m["binary_valid"] & finite
        ndvi = (a.features[3] - a.features[2]) / (
            a.features[3] + a.features[2])
        row: dict[str, Any] = {
            "cell_id": cell,
            "n_pure_positive_2020": int(m["y"].sum()),
            "n_pure_positive_eo_valid_2020": int(pos.sum()),
            "eo_valid_fraction_of_positive_2020": (
                float(pos.sum() / m["y"].sum()) if m["y"].sum() else None),
            "n_background_binary_valid_2020": int(bg.sum()),
            "ndvi_mean_positive": (
                float(ndvi[pos].mean()) if pos.any() else None),
            "ndvi_mean_background": (
                float(ndvi[bg].mean()) if bg.any() else None),
            "ndvi_gap": None}
        if row["ndvi_mean_positive"] is not None and row["ndvi_mean_background"] is not None:
            row["ndvi_gap"] = (row["ndvi_mean_positive"]
                               - row["ndvi_mean_background"])
        support.append(row)
    findings["positive_support_2020"] = support

    # 3. same-scene overfit ceilings (train and evaluate on one scene)
    ceilings: dict[str, Any] = {}
    for cell in POSITIVE_CELLS:
        a, m, finite = _view(cell, 2020)
        bv = m["binary_valid"] & finite
        if int((m["y"] & bv).sum()) < 10:
            ceilings[cell] = {
                "same_scene_overfit_iou_2020": None,
                "reason": "fewer than 10 EO-valid positive pixels"}
            continue
        prob, _ = _rf_proba(a.features, bv, m["y"], a.features, bv)
        ceilings[cell] = {
            "same_scene_overfit_iou_2020": _best_iou(prob, m["y"], bv),
            "n_train_pixels": int(bv.sum())}
    findings["same_scene_overfit_ceiling"] = ceilings

    # 4. cross-scene transfer (two spectrally separable, well-covered sites)
    aA, mA, fA = _view("CNA10K-R00349-C00154", 2020)
    aB, mB, fB = _view("CNA10K-R00413-C00121", 2020)
    bvA = mA["binary_valid"] & fA
    bvB = mB["binary_valid"] & fB
    pAB, _ = _rf_proba(aA.features, bvA, mA["y"], aB.features, bvB)
    pBA, _ = _rf_proba(aB.features, bvB, mB["y"], aA.features, bvA)
    findings["cross_scene_transfer_2020"] = {
        "train_R00349_eval_R00413_iou": _best_iou(pAB, mB["y"], bvB),
        "train_R00413_eval_R00349_iou": _best_iou(pBA, mA["y"], bvA),
        "note": "both scenes have strong within-scene NDVI separation"}

    # 5. same-scene temporal transfer 2020 -> 2021
    temporal: dict[str, Any] = {}
    for cell in ("CNA10K-R00349-C00154", "CNA10K-R00413-C00121"):
        a20, m20, f20 = _view(cell, 2020)
        a21, m21, f21 = _view(cell, 2021)
        bv20 = m20["binary_valid"] & f20
        bv21 = m21["binary_valid"] & f21
        p, _ = _rf_proba(a20.features, bv20, m20["y"],
                         a21.features, bv21)
        temporal[cell] = {
            "same_scene_2020_to_2021_iou": _best_iou(p, m21["y"], bv21),
            "n_positive_2021_eo_valid": int((m21["y"] & f21).sum())}
    findings["same_scene_temporal_transfer"] = temporal

    # 6. acquisition dates/qa from the frozen matrix
    with (BENCH / "support_matrix_v0_1.csv").open(newline="") as fh:
        matrix = list(csv.DictReader(fh))
    dates = {}
    for cell in POSITIVE_CELLS:
        rows = [r for r in matrix if r["cell_id"] == cell
                and r["sensor"] == "sentinel2"
                and r["label_source_key"].startswith("CMSA")
                and r["label_support_m"] == "30"
                and r["pairing_state"] == "PAIRED_LANDED"]
        dates[cell] = {
            f"{r['year']}": {
                "event_utc": r["event_utc"],
                "eo_qa_verdict": r["eo_qa_verdict"]}
            for r in rows}
    d20 = dates["CNA10K-R00413-C00121"]["2020"]["event_utc"][:10]
    d21 = dates["CNA10K-R00413-C00121"]["2021"]["event_utc"][:10]
    gap = abs((np.datetime64(d21) - np.datetime64(d20)).astype(int))
    findings["acquisition_dates"] = dates
    findings["R00413_2020_vs_2021_date_gap_days"] = int(gap)

    findings["created_utc"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    findings["git_commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True).stdout.strip()
    findings["support_matrix_sha256"] = hashlib.sha256(
        (BENCH / "support_matrix_v0_1.csv").read_bytes()).hexdigest()

    out = BENCH / "results" / "C2" / "failure_analysis_C2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(findings, sort_keys=True, indent=2,
                              ensure_ascii=False) + "\n")
    print(f"wrote {out.relative_to(REPO_ROOT)}")
    print(json.dumps({
        "support": [(r["cell_id"][-9:],
                     r["n_pure_positive_eo_valid_2020"],
                     round(r["ndvi_gap"], 3) if r["ndvi_gap"] is not None
                     else None)
                    for r in support],
        "ceilings": {k[-9:]: v["same_scene_overfit_iou_2020"]
                     for k, v in ceilings.items()},
        "cross": findings["cross_scene_transfer_2020"],
        "temporal": {k[-9:]: v["same_scene_2020_to_2021_iou"]
                     for k, v in temporal.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
