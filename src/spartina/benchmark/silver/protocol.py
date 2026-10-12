"""Phase B frozen protocol logic for SpartinaShift-Silver v0.1.

Everything in this module is decided BEFORE any model runs: cell roles,
witness isolation, sampling/normalisation rules, model ladder configs,
metrics and uncertainty. No baseline performance is inspected to set
any value here.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass
from typing import Any, Final

from spartina.data.national.grid import (
    CHINA_ALBERS_PROJ4,
    GridKind,
    GridSpec,
    parse_cell_id,
)
from spartina.evaluation.splits import SpatialUnit, find_cross_split_overlaps

PROTOCOL_NAME: Final[str] = "SPARTINASHIFT_SILVER_V0_1_PROTOCOL"
PROTOCOL_VERSION: Final[str] = "v0.1-frozen"
SEEDS: Final[tuple[int, ...]] = (17, 42, 2026)
LEAKAGE_BUFFER_M: Final[float] = 250.0
PATCH_PX: Final[int] = 128
PATCH_STRIDE_TRAIN: Final[int] = 64
PATCH_STRIDE_INFER: Final[int] = 128
PATCH_RES_M: Final[int] = 30
TRAIN_PATCHES_PER_CELL: Final[int] = 128
POSITIVE_PATCH_FRACTION: Final[float] = 0.5
BATCH_SIZE: Final[int] = 16
UNET_DEEPLAB_MAX_EPOCHS: Final[int] = 40
SEGFORMER_MAX_EPOCHS: Final[int] = 30
EARLY_STOP_PATIENCE: Final[int] = 10
WARMUP_EPOCHS: Final[int] = 3
POS_WEIGHT_CAP: Final[float] = 20.0
P_NORM_LOW: Final[float] = 0.005
P_NORM_HIGH: Final[float] = 0.995
RF_N_ESTIMATORS: Final[int] = 300
RF_PIXEL_CAP_PER_CELL: Final[int] = 20_000
GAP_SEASON_MATCH_DAYS: Final[int] = 30
GAP_NEAR_DATE_DAYS: Final[int] = 7
BLOCK_BOOTSTRAP_M: Final[int] = 1000
BLOCK_BOOTSTRAP_REPS: Final[int] = 1000
CI_LEVEL: Final[float] = 0.95

TRAIN_ROLE: Final[str] = "train"
VAL_ROLE: Final[str] = "val"
TEST_ROLE: Final[str] = "test"

#: 30 m fraction thresholds carried from the frozen label adapter.
FRAC_POSITIVE: Final[float] = 0.90
FRAC_MIXED_LO: Final[float] = 0.10

L8_BANDS: Final[tuple[str, ...]] = (
    "SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7")
S2_BANDS: Final[tuple[str, ...]] = ("B2", "B3", "B4", "B8")
S1_BANDS: Final[tuple[str, ...]] = ("VV", "VH")

MODEL_CONFIGS: Final[dict[str, dict[str, Any]]] = {
    "rf_pixel": {
        "family": "random_forest_pixel",
        "n_estimators": RF_N_ESTIMATORS,
        "class_weight": "balanced_subsample",
        "max_features": "sqrt",
        "min_samples_leaf": 2,
        "pixel_cap_per_train_cell": RF_PIXEL_CAP_PER_CELL,
        "features": (
            "EO bands + NDVI; S1 arm adds VV, VH and VV-VH log-ratio"),
    },
    "unet": {
        "family": "smp.Unet",
        "encoder": "resnet18",
        "encoder_weights": "ImageNet",
        "max_epochs": UNET_DEEPLAB_MAX_EPOCHS,
        "base_lr": 1e-3,
        "weight_decay": 1e-4,
        "batch_size": BATCH_SIZE,
    },
    "deeplabv3plus": {
        "family": "smp.DeepLabV3Plus",
        "encoder": "resnet18",
        "encoder_weights": "ImageNet",
        "max_epochs": UNET_DEEPLAB_MAX_EPOCHS,
        "base_lr": 1e-3,
        "weight_decay": 1e-4,
        "batch_size": BATCH_SIZE,
    },
    "segformer_b0": {
        "family": "huggingface.Segformer-B0",
        "pretrained": "nvidia/segformer-b0-finetuned-ade-512-512",
        "max_epochs": SEGFORMER_MAX_EPOCHS,
        "base_lr": 6e-4,
        "weight_decay": 1e-4,
        "batch_size": BATCH_SIZE,
        "head_replaced": True,
        "logits_upsampled_to_input": True,
    },
}


@dataclass(frozen=True)
class SplitRules:
    """Predeclared support-only constraints on a cell role split.

    ``positive_source_keys`` lists the label source keys in which a cell
    must carry pure-positive pixels (fraction >= 0.90) to count as a
    positive cell for that task. Background-only cells may fill roles up
    to the total counts; the per-role positive minimums guarantee the
    split can train, select and evaluate a binary segmenter at all.
    """

    n_test: int
    n_val: int
    positive_source_keys: tuple[str, ...]
    n_positive_train: int
    n_positive_val: int
    n_positive_test: int
    positive_test_min_provinces: int
    positive_test_require_north_south: bool
    min_val_provinces: int
    n_witness: int


def _hash_rank(namespace: str, cell_id: str) -> str:
    return hashlib.sha256(
        f"{PROTOCOL_NAME}|{namespace}|{cell_id}".encode()).hexdigest()


def cell_albers_unit(cell_id: str) -> SpatialUnit:
    ref = parse_cell_id(cell_id)
    if ref.kind is not GridKind.CHINA_ALBERS:
        raise ValueError(f"{cell_id} is not an Albers W10 cell")
    xmin, ymin, xmax, ymax = GridSpec(
        GridKind.CHINA_ALBERS).cell_bounds_projected(ref.row, ref.col)
    return SpatialUnit(cell_id, xmin, ymin, xmax, ymax)


def verify_buffer(roles: dict[str, str]) -> dict[str, Any]:
    """Canonical >=250 m cross-role buffer check on cell AABBs (Albers)."""
    units = {c: cell_albers_unit(c) for c in roles}
    overlaps = find_cross_split_overlaps(
        roles, units, buffer_m=LEAKAGE_BUFFER_M)
    gaps = []
    ids = list(units)
    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1:]:
            if roles[id_a] == roles[id_b]:
                continue
            a, b = units[id_a], units[id_b]
            gx = max(0.0, max(a.xmin, b.xmin) - min(a.xmax, b.xmax))
            gy = max(0.0, max(a.ymin, b.ymin) - min(a.ymax, b.ymax))
            gaps.append(max(gx, gy))
    return {
        "buffer_m": LEAKAGE_BUFFER_M,
        "n_cross_role_pairs_closer_than_buffer": len(overlaps),
        "min_cross_role_gap_m": round(min(gaps), 1) if gaps else None,
        "overlaps": [
            {"cell_a": a, "cell_b": b, "min_gap_m": round(g, 3)}
            for a, b, g in overlaps],
        "crs_proj4": CHINA_ALBERS_PROJ4,
    }


def _positive_cells(
    records: list[dict[str, Any]], source_keys: tuple[str, ...],
) -> set[str]:
    """Cells with pure-positive pixels in EVERY required label source."""
    by_key: dict[str, set[str]] = {k: set() for k in source_keys}
    for rec in records:
        key = rec["label_source_key"]
        if key in by_key and int(rec["n_pure_positive_px"]) > 0:
            by_key[key].add(rec["cell_id"])
    out = set(by_key[source_keys[0]])
    for key in source_keys[1:]:
        out &= by_key[key]
    return out


def assign_roles(
    namespace: str,
    cells: list[str],
    province_of: dict[str, str],
    records: list[dict[str, Any]],
    rules: SplitRules,
) -> dict[str, Any]:
    """Deterministically assign train/val/test (+witness) cell roles.

    Cells are hash-ranked and candidate (test, val) combinations are
    scanned in lexicographic order; the FIRST combination satisfying the
    predeclared support-only rules is frozen. No model output exists
    when this runs.
    """
    ordered = sorted(cells, key=lambda c: _hash_rank(namespace, c))
    index = {c: i for i, c in enumerate(ordered)}
    positive = _positive_cells(records, rules.positive_source_keys)
    north = {"Liaoning", "Shandong", "Jiangsu", "Shanghai", "Hebei",
             "Tianjin"}
    south = {"Fujian", "Zhejiang", "Guangdong", "Guangxi", "Hainan"}
    del index

    def valid_test(test: tuple[str, ...]) -> bool:
        pos = [c for c in test if c in positive]
        if len(pos) < rules.n_positive_test:
            return False
        provs = {province_of[c] for c in pos}
        if len(provs) < rules.positive_test_min_provinces:
            return False
        if not rules.positive_test_require_north_south:
            return True
        return bool(provs & north and provs & south)

    def valid_val(val: tuple[str, ...], test: tuple[str, ...]) -> bool:
        if sum(c in positive for c in val) < rules.n_positive_val:
            return False
        if len({province_of[c] for c in val}) < rules.min_val_provinces:
            return False
        remaining_pos = positive - set(test) - set(val)
        return len(remaining_pos) >= rules.n_positive_train

    chosen: tuple[tuple[str, ...], tuple[str, ...]] | None = None
    for test in itertools.combinations(ordered, rules.n_test):
        if not valid_test(test):
            continue
        rest = [c for c in ordered if c not in test]
        for val in itertools.combinations(rest, rules.n_val):
            if valid_val(val, test):
                chosen = (test, val)
                break
        if chosen is not None:
            break
    if chosen is None:
        raise ValueError(f"no admissible split found under {namespace}")

    test_cells, val_cells = chosen
    val_set, test_set = set(val_cells), set(test_cells)
    train_cells = tuple(c for c in ordered
                        if c not in val_set and c not in test_set)
    pos_test = [c for c in test_cells if c in positive]
    bg_test = [c for c in test_cells if c not in positive]
    witness_pos = sorted(
        pos_test, key=lambda c: _hash_rank(
            namespace + "|witness-positive", c))[:1]
    witness_prov = {province_of[c] for c in witness_pos}
    witness_bg = [
        c for c in sorted(
            bg_test,
            key=lambda c: _hash_rank(namespace + "|witness-background", c))
        if province_of[c] not in witness_prov][:max(
            0, rules.n_witness - len(witness_pos))]
    witness = tuple(witness_pos + witness_bg)
    if len(witness) != rules.n_witness:
        raise ValueError(
            f"could not assemble {rules.n_witness} witness cells: "
            f"{witness}")
    roles = {c: TRAIN_ROLE for c in train_cells}
    roles.update({c: VAL_ROLE for c in val_cells})
    roles.update({c: TEST_ROLE for c in test_cells})
    buffer_report = verify_buffer(roles)
    if buffer_report["n_cross_role_pairs_closer_than_buffer"] != 0:
        raise ValueError(
            "split violates the >=250 m cell buffer: "
            f"{buffer_report['overlaps']}")
    return {
        "split_id": namespace,
        "role_of": roles,
        "train": list(train_cells),
        "val": list(val_cells),
        "test": list(test_cells),
        "positive_cells": sorted(positive),
        "positive_by_role": {
            "train": sorted(c for c in train_cells if c in positive),
            "val": sorted(c for c in val_cells if c in positive),
            "test": sorted(c for c in test_cells if c in positive)},
        "witness_2020": list(witness),
        "province_of": {c: province_of[c] for c in ordered},
        "hash_ranks": {c: _hash_rank(namespace, c) for c in ordered},
        "buffer_check": buffer_report,
        "rules": {
            "n_train": len(train_cells), "n_val": len(val_cells),
            "n_test": len(test_cells), "n_witness": len(witness),
            "n_positive_train": rules.n_positive_train,
            "n_positive_val": rules.n_positive_val,
            "n_positive_test": rules.n_positive_test},
    }


def protocol_checksum(protocol: dict[str, Any]) -> str:
    """SHA-256 over the frozen content, excluding the checksum fields."""
    body = {k: v for k, v in protocol.items()
            if k not in {"checksum", "git_commit", "generated_utc"}}
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
