#!/usr/bin/env python3
"""Run manifest generator (EXPERIMENT_EXECUTION_PLAN.md §4.2).

Builds the provenance manifest for a training/evaluation run and REFUSES
runs missing any mandatory provenance field. Manifest + SHA-256 go to
Git-adjacent storage; run outputs stay outside Git.

Mandatory fields (reject if missing):
  run_id, git_sha, dataset_manifest_sha256, split_id, config_path,
  config_sha256, seeds, environment (conda env name or pip-freeze hash),
  gpu_ids, qa_ledger_ref.

Also enforces resource policy: never GPU 0; at most 3 GPUs.

Usage:
  python generate_run_manifest.py --config runs/r001/config.yaml \
      --dataset-manifest-sha <sha> --split-id SPLIT_V1_x --seeds 42,17,2026 \
      --gpu-ids 5,8 --out work/experiments/r001/run_manifest.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys

MANDATORY = [
    "run_id",
    "git_sha",
    "dataset_manifest_sha256",
    "split_id",
    "config_path",
    "config_sha256",
    "seeds",
    "environment",
    "gpu_ids",
    "qa_ledger_ref",
]

MAX_GPUS = 3


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_sha(repo: str = ".") -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def build_manifest(args) -> dict:
    seeds = [int(s) for s in str(args.seeds).split(",") if s.strip()]
    gpu_ids = sorted(int(g) for g in str(args.gpu_ids).split(",") if g.strip())
    manifest = {
        "run_id": args.run_id,
        "git_sha": args.git_sha or git_sha(),
        "dataset_manifest_sha256": args.dataset_manifest_sha,
        "split_id": args.split_id,
        "config_path": args.config,
        "config_sha256": sha256_file(args.config) if os.path.exists(args.config) else None,
        "seeds": seeds,
        "environment": args.environment,
        "gpu_ids": gpu_ids,
        "qa_ledger_ref": args.qa_ledger_ref,
        "checkpoint_sha256": args.checkpoint_sha,
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    return manifest


def validate_manifest(m: dict) -> list[str]:
    errors = []
    for key in MANDATORY:
        v = m.get(key)
        if v is None or v == "" or (isinstance(v, list) and not v):
            errors.append(f"missing mandatory field: {key}")
    gpus = m.get("gpu_ids") or []
    if 0 in gpus:
        errors.append("resource policy violation: GPU 0 is reserved and must never be used")
    if len(gpus) > MAX_GPUS:
        errors.append(f"resource policy violation: {len(gpus)} GPUs requested > {MAX_GPUS}")
    if not m.get("seeds"):
        errors.append("seeds list empty (protocol requires 42,17,2026)")
    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--dataset-manifest-sha", required=True)
    ap.add_argument("--split-id", required=True)
    ap.add_argument("--seeds", default="42,17,2026")
    ap.add_argument("--environment", required=True)
    ap.add_argument("--gpu-ids", required=True)
    ap.add_argument("--qa-ledger-ref", required=True)
    ap.add_argument("--git-sha", default=None)
    ap.add_argument("--checkpoint-sha", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if not os.path.exists(args.config):
        print(f"ERROR: config not found: {args.config}", file=sys.stderr)
        return 2

    manifest = build_manifest(args)
    errors = validate_manifest(manifest)
    if errors:
        print("RUN MANIFEST REJECTED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    payload = json.dumps(manifest, indent=1, sort_keys=True).encode()
    manifest["manifest_sha256"] = hashlib.sha256(payload).hexdigest()

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(manifest, f, indent=1, sort_keys=True)
        print(f"manifest written: {args.out}")
    print(json.dumps({k: manifest[k] for k in
                      ("run_id", "git_sha", "split_id", "seeds", "gpu_ids",
                       "manifest_sha256")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
