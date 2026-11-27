"""Freeze train/val decisions into FINAL_EVAL_LOCK.json (one-shot)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXPECTED_RUNS = {
    "sai": 1,
    "random_forest": 12,
    "unet": 12,
    "deeplabv3plus": 12,
    "segformer_b0": 12,
}


def discover_official_runs(runs_root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for mf in sorted(runs_root.rglob("run_manifest.json")):
        payload = json.loads(mf.read_text(encoding="utf-8"))
        if payload.get("phase") != "official":
            continue
        if payload.get("status") != "COMPLETED":
            continue
        runs.append(payload)
    return runs


def validate_matrix(runs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    keys: set[tuple[str, str, int | None]] = set()
    for r in runs:
        model = str(r["model"])
        counts[model] = counts.get(model, 0) + 1
        keys.add((model, str(r["variant"]),
                  r["seed"] if r["seed"] is not None else -1))
    if counts != EXPECTED_RUNS:
        raise RuntimeError(
            f"official run matrix mismatch: {counts} != {EXPECTED_RUNS}")
    if len(keys) != sum(EXPECTED_RUNS.values()):
        raise RuntimeError("duplicate (model,variant,seed) runs found")
    return counts


def build_lock(
    runs: list[dict[str, Any]], split_fingerprint: str,
    normalization_checksum: str, git_commit: str, dirty_tree: bool,
    plan: dict[str, Any],
) -> dict[str, Any]:
    entries = []
    for r in runs:
        if not r.get("checkpoint_sha256") or r.get("val_threshold") \
                is None or not r.get("config_sha256"):
            raise RuntimeError(f"run {r.get('run_id')} missing frozen "
                               "checkpoint/threshold/config hash")
        entries.append({
            "run_id": r["run_id"], "model": r["model"],
            "variant": r["variant"], "seed": r["seed"],
            "run_dir": r["run_dir"],
            "checkpoint_sha256": r["checkpoint_sha256"],
            "val_threshold": r["val_threshold"],
            "config_sha256": r["config_sha256"],
            "artifact_kind": r.get("artifact_kind", "torch_checkpoint"),
        })
    entries.sort(key=lambda e: (str(e["model"]), str(e["variant"]),
                                -1 if e["seed"] is None else int(e["seed"])))
    payload: dict[str, Any] = {
        "status": "FROZEN",
        "frozen_utc": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "dirty_tree": dirty_tree,
        "split_logical_fingerprint": split_fingerprint,
        "normalization_sha256": normalization_checksum,
        "plan": plan,
        "runs": entries,
    }
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    payload["lock_sha256"] = hashlib.sha256(body).hexdigest()
    return payload
