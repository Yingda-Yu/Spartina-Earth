"""Train-only percentile normalization (M1.5, frozen statistics).

Statistics are computed from unique TRAIN source pixels only (the union
of active train windows); no val/test statistic enters preprocessing.

Per band: p005 / p995 (train) -> clip -> mean/std after clipping.
Invalid (NaN) pixels are excluded from statistics and filled with
normalized zero at application time.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

BAND_NAMES = ("B1", "B2", "B3", "B4", "B5", "B6", "B7",
              "NDVI", "SAI", "VV", "VH")
FILL_VALUE = 0.0


@dataclass(frozen=True)
class BandStats:
    name: str
    p005: float
    p995: float
    mean: float
    std: float

    def to_dict(self) -> dict[str, float | str]:
        return {"band": self.name, "p005": self.p005, "p995": self.p995,
                "mean": self.mean, "std": self.std}


def compute_band_stats(
    stack: np.ndarray[Any, Any],
    train_mask: np.ndarray[Any, Any],
    low_pct: float = 0.005,
    high_pct: float = 0.995,
) -> list[BandStats]:
    out: list[BandStats] = []
    for b in range(stack.shape[0]):
        values = stack[b][train_mask]
        values = values[np.isfinite(values)]
        if values.size == 0:
            raise RuntimeError(f"no finite TRAIN pixels for band {b}")
        lo = float(np.quantile(values, low_pct))
        hi = float(np.quantile(values, high_pct))
        clipped = np.clip(values, lo, hi)
        mean = float(clipped.mean())
        std = float(clipped.std())
        if not np.isfinite(std) or std <= 0.0:
            raise RuntimeError(f"degenerate TRAIN std for band {b}")
        out.append(BandStats(BAND_NAMES[b], lo, hi, mean, std))
    return out


def apply_normalization(
    stack: np.ndarray[Any, Any], stats: list[BandStats],
) -> np.ndarray[Any, Any]:
    """Clip/scale/fill on any split; statistics stay train-only."""
    out = np.empty_like(stack, dtype=np.float32)
    for b, st in enumerate(stats):
        x = stack[b].astype(np.float32)
        x = np.clip(x, st.p005, st.p995)
        out[b] = (x - st.mean) / st.std
    invalid = ~np.isfinite(stack)
    if invalid.any():
        out[invalid] = FILL_VALUE
    return out


def normalization_payload(
    stats: list[BandStats], stack_checksum: str, split_fingerprint: str,
    train_pixel_count: int, cfg: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "dataset_id": cfg.get("dataset_id", "hangzhou2015_pilot0"),
        "computed_from": "unique TRAIN source pixels (union of active "
                         "train windows); val/test excluded",
        "source_stack_checksum": stack_checksum,
        "split_logical_fingerprint": split_fingerprint,
        "train_unique_pixel_count": int(train_pixel_count),
        "low_pct": float(cfg["normalization"]["low_pct"]),
        "high_pct": float(cfg["normalization"]["high_pct"]),
        "fill_value": FILL_VALUE,
        "bands": [s.to_dict() for s in stats],
    }


def write_normalization(payload: dict[str, Any], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, sort_keys=True, indent=2,
                      ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_checksum(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_normalization(path: Path) -> tuple[list[BandStats], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stats = [BandStats(str(b["band"]), float(b["p005"]), float(b["p995"]),
                       float(b["mean"]), float(b["std"]))
             for b in payload["bands"]]
    return stats, payload
