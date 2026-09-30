#!/usr/bin/env python
"""Issue #10 audit driver: accounting, forensics, RF/index audits, tables.

Read-only with respect to TEST: only stored test_metrics.json are read;
frozen checkpoints are scored on VALIDATION mosaics only. Outputs:

* docs/experiments/pilot0_run_accounting.csv
* docs/experiments/pilot0_collapse_forensics.csv
* docs/experiments/pilot0_rf_audit.csv
* docs/experiments/pilot0_index_distributions.csv
* docs/experiments/pilot0_index_probes.csv
* docs/experiments/pilot0_metrics_audit.csv
* docs/experiments/pilot0_variant_deltas.csv
* docs/experiments/pilot0_model_means.csv
* docs/experiments/pilot0_stress_audit.csv
* docs/experiments/pilot0_component_sensitivity.csv
* docs/experiments/PILOT0_BASELINE_FREEZE_V1.json  (only if gates pass)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from spartina.audit.accounting import (  # noqa: E402
    reconcile,
    run_accounting_table,
)
from spartina.audit.forensics import build_forensics  # noqa: E402
from spartina.audit.freeze import build_freeze_payload, write_freeze  # noqa: E402
from spartina.audit.index_probe import build_index_probe  # noqa: E402
from spartina.audit.paths import discover  # noqa: E402
from spartina.audit.rf_audit import build_rf_audit  # noqa: E402
from spartina.audit.tables import build_audit_tables  # noqa: E402
from spartina.experiments.registry import git_commit  # noqa: E402
from spartina.experiments.runner import load_all, repo_root  # noqa: E402

COMPARE_COLS = [
    "arbitrated_core_iou", "arbitrated_core_f1", "arbitrated_core_auprc",
    "arbitrated_core_brier", "arbitrated_core_ece",
    "arbitrated_core_signed_area_bias", "arbitrated_core_precision",
    "arbitrated_core_recall", "silver_strict_iou", "silver_strict_f1",
    "silver_strict_auprc"]


def cross_check_issue5_tables(out: Path, rebuilt: pd.DataFrame) -> None:
    """Every machine-generated Issue #5 number must match the rebuild."""
    old = pd.read_csv(out / "pilot0_metrics.csv")
    key = ["run_id", "split"]
    merged = old.merge(rebuilt, on=key, suffixes=("_old", "_new"),
                       how="outer", indicator=True)
    if (merged["_merge"] != "both").any():
        missing = merged.loc[merged["_merge"] != "both", key]
        raise RuntimeError(f"row-set mismatch vs pilot0_metrics.csv: "
                           f"{missing.to_dict('records')}")
    for col in COMPARE_COLS:
        a = merged[f"{col}_old"].to_numpy(dtype=float)
        b = merged[f"{col}_new"].to_numpy(dtype=float)
        if not np.allclose(a, b, rtol=0, atol=1e-12, equal_nan=True):
            bad = np.flatnonzero(~np.isclose(a, b, atol=1e-12))
            raise RuntimeError(
                f"{col} mismatch vs Issue #5 table at rows "
                f"{merged.iloc[bad][key].to_dict('records')}")
    print(f"cross-check: {len(merged)} rows match pilot0_metrics.csv")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=repo_root())
    args = ap.parse_args()
    repo = args.repo
    env = load_all(repo)
    common = env["common"]
    runs_root = repo / common["paths"]["runs_root"]
    out_dir = repo / "docs/experiments"
    runs = discover(runs_root)

    # A1 — accounting + lock/registry/test-record reconciliation
    rec = reconcile(
        runs, repo / common["paths"]["lock_file"],
        repo / common["paths"]["registry_dir"] / "pilot0_registry.csv")
    run_accounting_table(runs).to_csv(
        out_dir / "pilot0_run_accounting.csv", index=False)
    print(json.dumps(rec, indent=1))

    # A2 — SegFormer forensics (TRAIN/VAL only)
    fore = build_forensics(runs, env)
    fore.to_csv(out_dir / "pilot0_collapse_forensics.csv", index=False)
    print(fore[["variant", "seed", "best_epoch",
                "val_iou_best_over_epochs", "val_threshold",
                "val_target_positive_px", "val_mean_prob_positive_ref",
                "inflation_init_max_abs_err", "state_dict_missing_keys",
                "state_dict_unexpected_keys", "head_is_single_class",
                "test_recall", "classification"]].to_string(index=False))
    if (fore.classification == "IMPLEMENTATION_DEFECT").any():
        raise SystemExit(
            "IMPLEMENTATION_DEFECT classified — freeze aborted; report to "
            "user before any further TEST evaluation version")

    # A3 — RF low-threshold audit (VAL only)
    rf_df = build_rf_audit(runs, env)
    rf_df.to_csv(out_dir / "pilot0_rf_audit.csv", index=False)
    print(rf_df[["variant", "seed", "rf_classes", "positive_column_index",
                 "class_index_inversion", "stored_val_threshold",
                 "threshold_matches_stored", "val_auprc", "val_auroc",
                 "brier", "subsample_cap_binds", "fitted_pixels_manifest",
                 "train_domain_positive_fraction"]].to_string(index=False))

    # A4 — NDVI/SAI association diagnostics (TRAIN/VAL only)
    index_dist, index_probe = build_index_probe(env)
    index_dist.to_csv(out_dir / "pilot0_index_distributions.csv",
                      index=False)
    index_probe.to_csv(out_dir / "pilot0_index_probes.csv", index=False)
    print(index_probe[["probe", "val_auprc", "val_threshold_iou",
                       "mi_bits_train", "pearson_r_train"]].to_string(
                           index=False))

    # A4/A5/A6/A7/A8 — strict tables rebuilt from frozen artifacts
    classifications = dict(zip(fore.run_id, fore.classification, strict=False))
    tables = build_audit_tables(
        runs, sources=env["sources"], grid=env["grid"],
        classifications=classifications)
    tables.metrics.to_csv(out_dir / "pilot0_metrics_audit.csv",
                          index=False)
    tables.deltas.to_csv(out_dir / "pilot0_variant_deltas.csv",
                         index=False)
    tables.means.to_csv(out_dir / "pilot0_model_means.csv", index=False)
    tables.stress.to_csv(out_dir / "pilot0_stress_audit.csv",
                         index=False)
    tables.sensitivity.to_csv(
        out_dir / "pilot0_component_sensitivity.csv", index=False)
    cross_check_issue5_tables(out_dir, tables.metrics)
    print(tables.means[["model", "variant", "split", "iou_mean",
                        "iou_std", "collapsed_seeds",
                        "n_seeds_in_denominator"]].to_string(index=False))

    # A9 — freeze (raises if any gate fails)
    payload = build_freeze_payload(
        repo, env, tables, fore, rec,
        str(Path(common["paths"]["registry_dir"])
            / "pilot0_registry.csv"),
        git_commit(repo))
    write_freeze(payload, out_dir / "PILOT0_BASELINE_FREEZE_V1.json")
    print(f"FREEZE OK: {payload['freeze_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
