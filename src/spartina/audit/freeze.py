"""Issue #10 result-freeze payload (PILOT0_BASELINE_FREEZE_V1).

Emitted only when every integrity gate passes: exact 49-run accounting,
no implementation defect, strict table reconciliation. The freeze marks
the ladder ENGINEERING_VERIFIED / SCIENTIFICALLY_LIMITED and pins every
provenance hash needed to regenerate the tables.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from spartina.audit.paths import OFFICIAL_COUNTS
from spartina.audit.tables import AuditTables, canonical_hash

FREEZE_NAME = "PILOT0_BASELINE_FREEZE_V1"


# Fields that record *when/where the document was emitted* rather than
# evidence content. They stay in the document but are excluded from its
# self-hash so re-running the audit on unchanged artifacts reproduces the
# same freeze hash.
_NON_EVIDENCE_FIELDS: tuple[str, ...] = ("freeze_sha256", "created_utc")


def _hash_json(payload: dict[str, Any]) -> str:
    body = dict(payload)
    for key in _NON_EVIDENCE_FIELDS:
        body.pop(key, None)
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()


def _official_registry_hash(repo: Path, rel_path: str) -> str:
    df = pd.read_csv(repo / rel_path)
    df = df[(df.phase == "official") & (df.status == "COMPLETED")]
    df = df.sort_values("run_id").reset_index(drop=True)
    return canonical_hash(df)


def build_freeze_payload(
    repo: Path,
    env: dict[str, Any],
    tables: AuditTables,
    forensics: pd.DataFrame,
    reconciliation: dict[str, Any],
    registry_rel_path: str,
    git_commit: str,
) -> dict[str, Any]:
    """Assemble the freeze document (caller writes it)."""
    class_counts = forensics["classification"].value_counts().to_dict()
    defect_runs = forensics.loc[
        forensics.classification == "IMPLEMENTATION_DEFECT", "run_id"]
    if len(defect_runs):
        raise RuntimeError(
            f"refusing to freeze; IMPLEMENTATION_DEFECT runs: "
            f"{sorted(defect_runs)}")

    collapsed = forensics.loc[
        forensics.classification != "NO_COLLAPSE",
        ["run_id", "variant", "seed", "classification"]]
    metrics_sorted = tables.metrics.sort_values(
        ["run_id", "split"]).reset_index(drop=True)
    means_sorted = tables.means.sort_values(
        ["model", "variant", "split"]).reset_index(drop=True)
    deltas_sorted = tables.deltas.sort_values(
        ["model", "seed", "split", "contrast"]).reset_index(drop=True)

    payload: dict[str, Any] = {
        "freeze_id": FREEZE_NAME,
        "created_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "git_commit": git_commit,
        "engineering_status": "ENGINEERING_VERIFIED",
        "scientific_status": "SCIENTIFICALLY_LIMITED",
        "n_official_runs": int(sum(OFFICIAL_COUNTS.values())),
        "official_counts": dict(sorted(OFFICIAL_COUNTS.items())),
        "segformer_classification_counts": {
            str(k): int(v) for k, v in sorted(class_counts.items())},
        "collapsed_runs_retained_in_means": collapsed.to_dict(
            orient="records"),
        "fingerprints": {
            "split_logical_fingerprint_sha256":
                env["split_fingerprint"],
            "normalization_sha256": env["norm_checksum"],
            "final_eval_lock_sha256":
                reconciliation["lock_sha256"],
            "official_registry_sha256":
                _official_registry_hash(repo, registry_rel_path),
            "metrics_table_sha256": canonical_hash(metrics_sorted),
            "model_means_table_sha256": canonical_hash(means_sorted),
            "variant_deltas_table_sha256": canonical_hash(deltas_sorted),
        },
        "integrity_gates_passed": [
            "exact 49-run official matrix (SAI 1, RF 12, U-Net 12, "
            "DeepLabV3+ 12, SegFormer 12)",
            "run manifests == FINAL_EVAL_LOCK == registry == stored "
            "TEST metrics (checksums verified)",
            "no diagnostic/smoke run carries TEST metrics",
            "SegFormer inflation/head/state-dict/target-entry checks "
            "pass; zero IMPLEMENTATION_DEFECT",
            "RF positive-class column verified (classes_==1); no class "
            "or label inversion",
            "mean/SD denominators include all three seeds, collapsed "
            "runs retained",
            "tables rebuilt from raw artifacts with hard-fail validation",
        ],
        "known_report_corrections": [
            "Issue #5 report phrase 'RF 14/14 thresholds at 0.05 (all "
            "Random Forest)' mislabels two neural runs: the 14 runs are "
            "12 RF + U-Net optical_sar seed 2026 + DeepLabV3+ "
            "optical_sar seed 2026.",
        ],
        "scientific_limitations": [
            "NO GOLD labels: all targets are SILVER (government/peer "
            "product, not field/UAV verified)",
            "single region (Hangzhou Bay pilot), single nominal year 2015",
            "exact S1/L8 acquisition dates of the legacy composite are "
            "UNKNOWN — SAR/index effects reported only 'under the current "
            "legacy composite', never as sensor-intrinsic conclusions",
            "TEST geography: 7 windows; 5 full-grid SILVER ecological "
            "patches (12 coverage-fragmented reference pieces, 8 >= 10 "
            "px, 4 small); one large patch dominates the pixel support",
            "no spatial confidence interval is claimed at n=5 patches",
            "missing-modality stress is deployment-robustness evidence, "
            "not causal feature importance",
        ],
        "evidence_not_persisted_in_issue5_engine": [
            "TEST stitched probability rasters (per-component/LOCO "
            "analysis therefore NOT_PERSISTED; required for eval v1.1)",
            "per-component SILVER match lists",
            "per-step gradient norms",
            "AMP GradScaler events",
            "per-batch losses and per-epoch validation loss",
        ],
        "evaluation_v1_1_recommendations": [
            "persist stitched TEST probability + hard prediction rasters",
            "persist per-component match table with component IDs",
            "log gradient norms, AMP scaler events, per-batch loss",
            "expand test geography across spatially disjoint patches",
        ],
    }
    payload["freeze_sha256"] = _hash_json(payload)
    return payload


def write_freeze(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    return path
