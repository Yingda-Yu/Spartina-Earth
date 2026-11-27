"""Shared loading helpers for Pilot-0 baseline CLI scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml

from spartina.data.dataset import prepare_grid
from spartina.data.normalization import (
    load_normalization,
    payload_checksum,
)
from spartina.data.pilot0 import load_sources
from spartina.experiments.embargo import EmbargoGate


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_yaml(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any],
                yaml.safe_load(path.read_text(encoding="utf-8")))


def load_common(repo: Path) -> dict[str, Any]:
    return load_yaml(repo / "configs/experiment/pilot0/common.yaml")


def split_registry(repo: Path, common: dict[str, Any]) -> dict[str, Any]:
    with open(repo / common["paths"]["split_registry"],
              encoding="utf-8") as fh:
        return cast(dict[str, Any], json.load(fh))


def split_fingerprint_of(registry: dict[str, Any]) -> str:
    return str(registry["window_manifest"][
        "logical_manifest_fingerprint_sha256"])


def load_all(
    repo: Path, allow_test: bool = False,
) -> dict[str, Any]:
    common = load_common(repo)
    registry = split_registry(repo, common)
    sources = load_sources(repo, common)
    norm_path = repo / common["paths"]["normalization"]
    stats, norm_payload = load_normalization(norm_path)
    norm_checksum = str(norm_payload.get("checksum")
                        or payload_checksum(norm_payload))
    grid = prepare_grid(sources, stats)
    sfp = split_fingerprint_of(registry)
    gate = EmbargoGate(
        lock_path=repo / common["paths"]["lock_file"],
        expected_split_fingerprint=sfp,
        expected_normalization_checksum=norm_checksum)
    return {"common": common, "split_registry": registry,
            "sources": sources, "stats": stats,
            "norm_payload": norm_payload, "norm_checksum": norm_checksum,
            "grid": grid, "split_fingerprint": sfp, "gate": gate,
            "model_cfgs": {
                name: load_yaml(
                    repo / f"configs/experiment/pilot0/{name}.yaml")
                for name in ("unet", "deeplabv3plus", "segformer_b0",
                             "random_forest", "spectral")}}
