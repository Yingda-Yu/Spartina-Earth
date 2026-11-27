"""Run directories, manifests and the tracked Pilot-0 run registry.

Checkpoints and prediction rasters live under the gitignored
``runs/pilot0``; only metadata and hashes are summarized into the
tracked CSV under ``docs/experiments/registries/``.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

REGISTRY_COLUMNS = [
    "run_id", "model", "variant", "seed", "phase", "status",
    "git_commit", "dirty_tree", "best_epoch", "val_threshold",
    "val_core_iou", "checkpoint_sha256", "checkpoint_size_bytes",
    "gpu_id", "gpu_model", "gpu_vram_mib", "driver_version",
    "runtime_s", "run_dir",
]


def utc_now_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def git_commit(repo: Path) -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def git_dirty(repo: Path) -> bool:
    out = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                         capture_output=True, text=True, check=True)
    return bool(out.stdout.strip())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def environment_fingerprint() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "cuda": str(torch.version.cuda),
        "hostname": platform.node(),
    }


@dataclass
class RunContext:
    repo: Path
    runs_root: Path
    registry_dir: Path
    model: str
    variant: str
    seed: int | None
    phase: str = "official"

    run_id: str = ""
    run_dir: Path = field(default_factory=Path)
    manifest: dict[str, Any] = field(default_factory=dict)

    def initialize(self) -> RunContext:
        seed_part = f"seed-{self.seed}" if self.seed is not None \
            else "deterministic"
        rid = f"{self.model}_{self.variant}_{seed_part}_{utc_now_compact()}"
        rdir = (self.runs_root / self.model / self.variant / seed_part / rid)
        rdir.mkdir(parents=True, exist_ok=False)
        self.run_id = rid
        self.run_dir = rdir
        self.manifest = {
            "run_id": rid, "model": self.model, "variant": self.variant,
            "seed": self.seed, "phase": self.phase,
            "run_dir": str(rdir.relative_to(self.repo)),
            "created_utc": datetime.now(UTC).isoformat(),
            "environment": environment_fingerprint(),
        }
        return self

    def path(self, name: str) -> Path:
        return self.run_dir / name

    def write_json(self, name: str, payload: dict[str, Any]) -> Path:
        p = self.path(name)
        p.write_text(json.dumps(payload, sort_keys=True, indent=2,
                                ensure_ascii=False) + "\n",
                     encoding="utf-8")
        return p

    def save_checkpoint(self, state: dict[str, Any],
                        name: str = "best.pt") -> dict[str, Any]:
        p = self.path(name)
        torch.save(state, p)
        return {"checkpoint": name,
                "checkpoint_sha256": sha256_file(p),
                "checkpoint_size_bytes": p.stat().st_size}

    def finalize(self, status: str = "COMPLETED") -> dict[str, Any]:
        self.manifest["status"] = status
        self.manifest["finalized_utc"] = datetime.now(UTC).isoformat()
        self.write_json("run_manifest.json", self.manifest)
        return self.manifest

    def fail(self, reason: str) -> dict[str, Any]:
        self.manifest["failure_reason"] = reason
        return self.finalize("FAILED")


def append_registry_row(repo: Path, registry_dir: Path,
                        manifest: dict[str, Any]) -> None:
    import csv
    registry_dir.mkdir(parents=True, exist_ok=True)
    csv_path = registry_dir / "pilot0_registry.csv"
    exists = csv_path.exists()
    gpu = manifest.get("gpu", {}) or {}
    row = {
        "run_id": manifest.get("run_id"),
        "model": manifest.get("model"),
        "variant": manifest.get("variant"),
        "seed": manifest.get("seed"),
        "phase": manifest.get("phase"),
        "status": manifest.get("status"),
        "git_commit": manifest.get("git_commit"),
        "dirty_tree": manifest.get("dirty_tree"),
        "best_epoch": (manifest.get("training", {}) or {}).get("best_epoch"),
        "val_threshold": manifest.get("val_threshold"),
        "val_core_iou": manifest.get("val_core_iou"),
        "checkpoint_sha256": manifest.get("checkpoint_sha256"),
        "checkpoint_size_bytes": manifest.get("checkpoint_size_bytes"),
        "gpu_id": gpu.get("id"),
        "gpu_model": gpu.get("model"),
        "gpu_vram_mib": gpu.get("vram_mib"),
        "driver_version": gpu.get("driver"),
        "runtime_s": (manifest.get("efficiency", {}) or {}).get(
            "train_wall_s"),
        "run_dir": manifest.get("run_dir"),
    }
    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=REGISTRY_COLUMNS)
        if not exists:
            w.writeheader()
        w.writerow(row)
