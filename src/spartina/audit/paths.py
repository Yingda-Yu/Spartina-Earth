"""Artifact discovery for the Pilot-0 integrity audit (read-only)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OFFICIAL_COUNTS = {
    "sai": 1,
    "random_forest": 12,
    "unet": 12,
    "deeplabv3plus": 12,
    "segformer_b0": 12,
}
SEEDS = (17, 42, 2026)
VARIANTS = ("optical", "optical_indices", "optical_sar", "full")


@dataclass(frozen=True)
class RunArtifact:
    run_id: str
    model: str
    variant: str
    seed: int | None
    phase: str
    status: str
    dir: Path
    manifest: dict[str, Any]

    @property
    def val_metrics(self) -> dict[str, Any] | None:
        p = self.dir / "val_metrics.json"
        return json.loads(p.read_text("utf-8")) if p.exists() else None

    @property
    def test_metrics(self) -> dict[str, Any] | None:
        p = self.dir / "test_metrics.json"
        return json.loads(p.read_text("utf-8")) if p.exists() else None

    @property
    def history(self) -> list[dict[str, Any]] | None:
        p = self.dir / "history.json"
        if not p.exists():
            return None
        return list(json.loads(p.read_text("utf-8")).get("history", []))


def discover(runs_root: Path) -> list[RunArtifact]:
    out: list[RunArtifact] = []
    for mf in sorted(runs_root.rglob("run_manifest.json")):
        m = json.loads(mf.read_text("utf-8"))
        out.append(RunArtifact(
            run_id=str(m["run_id"]), model=str(m["model"]),
            variant=str(m["variant"]),
            seed=(None if m.get("seed") is None else int(m["seed"])),
            phase=str(m["phase"]), status=str(m["status"]),
            dir=mf.parent, manifest=m))
    return out


def official_completed(runs: list[RunArtifact]) -> list[RunArtifact]:
    return [r for r in runs if r.phase == "official"
            and r.status == "COMPLETED"]
