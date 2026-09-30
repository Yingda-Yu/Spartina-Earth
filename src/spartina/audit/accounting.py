"""Hard-fail reconciliation of run artifacts, lock and registry."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from spartina.audit.paths import (
    OFFICIAL_COUNTS,
    RunArtifact,
    official_completed,
)


class ReconciliationError(RuntimeError):
    """A frozen-run invariant is broken."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconcile(
    runs: list[RunArtifact], lock_path: Path,
    registry_csv: Path,
) -> dict[str, Any]:
    """Validate every official invariant. Raises on first violation."""
    findings: list[str] = []

    official = official_completed(runs)
    counts = Counter(r.model for r in official)
    if dict(counts) != OFFICIAL_COUNTS:
        raise ReconciliationError(
            f"official matrix mismatch: {dict(counts)} != {OFFICIAL_COUNTS}")

    keys = Counter((r.model, r.variant, r.seed) for r in official)
    dupes = [k for k, v in keys.items() if v > 1]
    if dupes:
        raise ReconciliationError(f"duplicate official run keys: {dupes}")

    # non-official runs must be explicitly labelled and never carry TEST
    extras = [r for r in runs if not (
        r.phase == "official" and r.status == "COMPLETED")]
    for r in extras:
        if r.phase != "smoke":
            raise ReconciliationError(
                f"unexpected non-official phase: {r.run_id} {r.phase}")
        if r.test_metrics is not None:
            raise ReconciliationError(
                f"non-official run carries TEST metrics: {r.run_id}")

    # every official run has val + frozen checkpoint metadata
    for r in official:
        if r.val_metrics is None:
            raise ReconciliationError(f"missing val metrics: {r.run_id}")
        for k in ("checkpoint_sha256", "val_threshold", "config_sha256",
                  "git_commit", "split_logical_fingerprint",
                  "normalization_sha256"):
            if r.manifest.get(k) is None:
                raise ReconciliationError(f"{r.run_id}: missing {k}")

    # lock maps 1:1
    lock = json.loads(lock_path.read_text("utf-8"))
    if lock.get("status") != "FROZEN":
        raise ReconciliationError("lock is not FROZEN")
    lock_ids = {e["run_id"] for e in lock["runs"]}
    off_ids = {r.run_id for r in official}
    if lock_ids != off_ids:
        raise ReconciliationError(
            f"lock/official mismatch: only-lock="
            f"{lock_ids - off_ids} only-disk={off_ids - lock_ids}")

    # checkpoint bytes match lock for every run
    for entry in lock["runs"]:
        ra = next(r for r in official if r.run_id == entry["run_id"])
        kind = entry["artifact_kind"]
        fn = {"torch_checkpoint": "best.pt",
              "random_forest_joblib": "rf.joblib",
              "spectral_rule": "rule.json"}[kind]
        p = ra.dir / fn
        if not p.exists():
            raise ReconciliationError(f"missing artifact {p}")
        if sha256_file(p) != entry["checkpoint_sha256"]:
            raise ReconciliationError(
                f"checksum mismatch: {ra.run_id}")
        if ra.manifest["val_threshold"] != entry["val_threshold"]:
            raise ReconciliationError(f"threshold mismatch: {ra.run_id}")
        if ra.manifest["config_sha256"] != entry["config_sha256"]:
            raise ReconciliationError(f"config hash mismatch: {ra.run_id}")

    # registry maps 1:1 (contains official + labelled smoke)
    reg = pd.read_csv(registry_csv)
    reg_off = set(reg[(reg.phase == "official")
                      & (reg.status == "COMPLETED")].run_id)
    if reg_off != off_ids:
        raise ReconciliationError("registry/official mismatch")
    if reg.run_id.duplicated().any():
        raise ReconciliationError("duplicate registry rows")

    # exactly one stored TEST record per official run, none elsewhere
    test_runs = [r for r in runs if r.test_metrics is not None]
    if {r.run_id for r in test_runs} != off_ids:
        raise ReconciliationError(
            f"TEST records {len(test_runs)} != official {len(official)}")

    findings.append(f"{len(official)} official runs reconciled with lock, "
                    f"registry and stored TEST metrics")
    return {"n_official": len(official),
            "n_non_official": len(extras),
            "counts": dict(counts),
            "lock_sha256": lock["lock_sha256"],
            "findings": findings}


def run_accounting_table(runs: list[RunArtifact]) -> pd.DataFrame:
    rows = []
    for r in runs:
        rows.append({
            "run_id": r.run_id, "model": r.model, "variant": r.variant,
            "seed": r.seed, "phase": r.phase, "status": r.status,
            "in_official_means": r.phase == "official"
            and r.status == "COMPLETED",
            "val_threshold": r.manifest.get("val_threshold"),
            "val_core_iou": r.manifest.get("val_core_iou"),
            "has_test_metrics": r.test_metrics is not None,
            "run_dir": r.manifest.get("run_dir"),
        })
    return pd.DataFrame(rows).sort_values(
        ["model", "variant", "seed", "phase"]).reset_index(drop=True)
