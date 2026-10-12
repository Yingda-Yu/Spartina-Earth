"""Stage-1 experiment runner for the frozen SpartinaShift-Silver v0.1.

Honours ``SPARTINASHIFT_SILVER_V0_1_PROTOCOL`` exactly:

* W10 cells are the sole split unit; all patches/dates/modalities of a
  cell inherit the cell's frozen role;
* normalisation, pos-weight, threshold, early stopping and HPO use the
  TRAIN/VAL cells only -- TEST arrays are not opened until model
  selection is frozen;
* the threshold is selected once on VAL (training year) and applied
  unchanged to the held-out reference year and the temporal-shift year;
* metrics are reported per cell AND pooled, with patch and independent
  held-out cell counts, spatial block-bootstrap intervals (1000 m
  blocks, pixels are never bootstrapped), calibration and a separate
  descriptive MIXED/fraction-agreement view;
* every run persists config, seed, checkpoint, logs, predictions,
  environment and git commit, plus a small tracked summary JSON.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import torch
from scipy import ndimage
from torch.utils.data import DataLoader, Dataset

from spartina.benchmark.silver.data import (
    CellArrays,
    NormStats,
    apply_norm,
    geometric_transform,
    load_cell_arrays,
    sample_patch_origins,
    target_masks,
)
from spartina.benchmark.silver.protocol import (
    BATCH_SIZE,
    BLOCK_BOOTSTRAP_M,
    BLOCK_BOOTSTRAP_REPS,
    CI_LEVEL,
    EARLY_STOP_PATIENCE,
    MODEL_CONFIGS,
    P_NORM_HIGH,
    P_NORM_LOW,
    PATCH_PX,
    POS_WEIGHT_CAP,
    POSITIVE_PATCH_FRACTION,
    PROTOCOL_NAME,
    SEEDS,
    TRAIN_PATCHES_PER_CELL,
    WARMUP_EPOCHS,
    protocol_checksum,
)
from spartina.evaluation.metrics import (
    THRESHOLD_GRID_DEFAULT,
    _boundary,
    area_metrics,
    auprc,
    calibration,
    choose_threshold,
    confusion,
    evaluate_view,
    patch_matching,
    pixel_rates,
)
from spartina.training.losses import segmentation_loss
from spartina.training.schedule import lr_at_epoch, seed_everything

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[4]
BENCH_DIR: Final[Path] = REPO_ROOT / "benchmarks" / "spartinashift" / "silver_v0_1"
PROTOCOL_PATH: Final[Path] = BENCH_DIR / "SPARTINASHIFT_SILVER_V0_1_PROTOCOL.json"
SPLITS_PATH: Final[Path] = BENCH_DIR / "splits_v0_1.json"
MATRIX_PATH: Final[Path] = BENCH_DIR / "support_matrix_v0_1.csv"
RUNS_ROOT: Final[Path] = REPO_ROOT / "runs" / "silver_v0_1"
RESULTS_DIR: Final[Path] = BENCH_DIR / "results"

ANALYSIS_PIXEL_M: Final[int] = 30
BOOTSTRAP_SEED: Final[int] = 20261001

NEURAL_MODELS: Final[frozenset[str]] = frozenset(
    {"unet", "deeplabv3plus", "segformer_b0"})
ALL_MODELS: Final[tuple[str, ...]] = (
    "rf_pixel", "unet", "deeplabv3plus", "segformer_b0")

# ---------------------------------------------------------------------------
# Frozen-input loading and integrity checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellSpec:
    cell_id: str
    role: str
    province: str
    positive: bool
    product_by_year: dict[int, str]
    extra_product_by_year: dict[int, str]
    label_by_year: dict[int, str]


@dataclass(frozen=True)
class TaskSpec:
    task: str
    arm: str
    split_id: str
    label_family: str
    train_year: int
    eval_years: tuple[int, ...]
    in_channels: int
    cells: dict[str, CellSpec]

    def cells_of(self, role: str) -> list[CellSpec]:
        return [c for c in self.cells.values() if c.role == role]


def train_specs(task: TaskSpec, smoke: bool) -> list[CellSpec]:
    specs = task.cells_of("train")
    return specs[:2] if smoke else specs


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_inputs() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    protocol = json.loads(PROTOCOL_PATH.read_text())
    stored = protocol.get("checksum")
    recomputed = protocol_checksum(protocol)
    if stored != recomputed:
        raise ValueError(
            f"frozen protocol checksum mismatch: stored {stored} != "
            f"recomputed {recomputed}; refusing to run")
    splits = json.loads(SPLITS_PATH.read_text())["splits"]["SPLIT-S2"]
    with MATRIX_PATH.open(newline="") as fh:
        matrix = list(csv.DictReader(fh))
    return protocol, splits, matrix


def _resolve_product(
    matrix: list[dict[str, str]], cell_id: str, year: int, sensor: str,
    label_key: str, variant: str | None = None,
) -> str:
    rows = [r for r in matrix
            if r["cell_id"] == cell_id and int(r["year"]) == year
            and r["sensor"] == sensor and r["pairing_state"] == "PAIRED_LANDED"
            and r["label_source_key"] == label_key
            and int(r["label_support_m"]) == 30
            and (variant is None or r["eo_variant"] == variant)]
    if len(rows) != 1:
        raise ValueError(
            f"{cell_id} {year} {sensor} variant={variant}: expected exactly "
            f"1 PAIRED_LANDED row, found {len(rows)}")
    return rows[0]["product_id"]


def _build_s2_task_spec(
    task_name: str, matrix: list[dict[str, str]], splits: dict[str, Any],
    arm: str, allowed_cells: set[str] | None = None,
) -> TaskSpec:
    years = (2020, 2021)
    cells: dict[str, CellSpec] = {}
    positive = set(splits["positive_cells"])
    for role in ("train", "val", "test"):
        for cell_id in splits[role]:
            if allowed_cells is not None and cell_id not in allowed_cells:
                continue
            products: dict[int, str] = {}
            extra: dict[int, str] = {}
            labels: dict[int, str] = {}
            for year in years:
                label_key = f"CMSA_{year}"
                products[year] = _resolve_product(
                    matrix, cell_id, year, "sentinel2", label_key)
                labels[year] = label_key
                if arm == "s2_s1":
                    extra[year] = _resolve_product(
                        matrix, cell_id, year, "sentinel1", label_key,
                        variant="A")
            cells[cell_id] = CellSpec(
                cell_id=cell_id, role=role,
                province=splits["province_of"][cell_id],
                positive=cell_id in positive,
                product_by_year=products, extra_product_by_year=extra,
                label_by_year=labels)
    n_channels = 6 if arm == "s2_s1" else 4
    return TaskSpec(
        task=task_name, arm=arm, split_id="SPLIT-S2", label_family="CMSA",
        train_year=2020, eval_years=years, in_channels=n_channels,
        cells=cells)


def build_c2_spec(matrix: list[dict[str, str]], splits: dict[str, Any],
                  arm: str = "s2") -> TaskSpec:
    return _build_s2_task_spec("C2", matrix, splits, arm)


def build_c5_spec(
    protocol: dict[str, Any], matrix: list[dict[str, str]],
    splits: dict[str, Any],
) -> TaskSpec:
    eligible = set(protocol["tasks"]["C5_modality_ablation"]
                   ["optical_sar_arm"]["eligible_cells"])
    task = _build_s2_task_spec("C5", matrix, splits, "s2_s1",
                               allowed_cells=eligible)
    missing = eligible - set(task.cells)
    if missing:
        raise ValueError(f"C5 eligible cells missing from spec: {sorted(missing)}")
    if len(task.cells) != len(eligible):
        raise ValueError("C5 cell count mismatch")
    return task


# ---------------------------------------------------------------------------
# Cell arrays, train-only normalisation, patch sampling
# ---------------------------------------------------------------------------


def open_cell(spec: CellSpec, year: int) -> CellArrays:
    return load_cell_arrays(
        spec.cell_id, spec.product_by_year[year],
        spec.label_by_year[year],
        extra_product_id=spec.extra_product_by_year.get(year))


def cell_masks(arrays: Any, family: str, year: int) -> dict[str, Any]:
    return target_masks(arrays.fraction, arrays.occ_class, family, year)


def pooled_train_norm(
    task: TaskSpec, smoke: bool = False,
) -> tuple[NormStats, dict[str, Any]]:
    """Percentile/mean/std from VALID TRAIN-cell pixels of the train year."""
    train = train_specs(task, smoke)
    bands: list[list[np.ndarray[Any, Any]]] = [
        [] for _ in range(task.in_channels)]
    n_pixels = 0
    for spec in train:
        arrays = open_cell(spec, task.train_year)
        if arrays.features.shape[0] != task.in_channels:
            raise ValueError(
                f"{spec.cell_id}: expected {task.in_channels} bands for arm "
                f"{task.arm}, got {arrays.features.shape[0]}")
        for i in range(task.in_channels):
            finite = arrays.features[i][
                arrays.valid & np.isfinite(arrays.features[i])]
            bands[i].append(finite)
        n_pixels += int(arrays.valid.sum())
    per_band = [np.concatenate(parts) for parts in bands]
    lo = np.array([np.quantile(v, P_NORM_LOW) for v in per_band],
                  dtype=np.float32)
    hi = np.array([np.quantile(v, P_NORM_HIGH) for v in per_band],
                  dtype=np.float32)
    mean = np.empty(task.in_channels, dtype=np.float32)
    std = np.empty(task.in_channels, dtype=np.float32)
    for i, vals in enumerate(per_band):
        clipped = np.clip(vals, lo[i], hi[i])
        mean[i] = clipped.mean()
        std[i] = max(float(clipped.std()), 1e-8)
    stats = NormStats(lo, hi, mean, std)
    audit = {
        "source": "TRAIN cells only, train-year EO, valid pixels",
        "train_cells_used": [c.cell_id for c in train],
        "n_valid_pixels": n_pixels,
        "p_low": P_NORM_LOW, "p_high": P_NORM_HIGH,
        **stats.to_dict(),
    }
    return stats, audit


def _cell_seed(seed: int, cell_id: str) -> int:
    return int(hashlib.sha256(
        f"{seed}|{cell_id}".encode()).hexdigest()[:8], 16)


class CellPatchDataset(Dataset[tuple[torch.Tensor, torch.Tensor,
                                      torch.Tensor]]):
    def __init__(self, task: TaskSpec, norm: NormStats, seed: int,
                 n_patches: int = TRAIN_PATCHES_PER_CELL,
                 train_cells: list[CellSpec] | None = None) -> None:
        self.patch = PATCH_PX
        self.items: list[tuple[Any, np.ndarray[Any, Any],
                               np.ndarray[Any, Any],
                               list[tuple[int, int]]]] = []
        for spec in (train_cells if train_cells is not None
                     else task.cells_of("train")):
            arrays = open_cell(spec, task.train_year)
            masks = cell_masks(arrays, task.label_family, task.train_year)
            x = apply_norm(arrays.features, arrays.valid, norm)
            # Frozen C5 identity: the optical+SAR arm samples the SAME
            # patch geometry as the optical arm, so origins use the
            # Sentinel-2-only validity mask (labels are identical).
            sampling_valid = arrays.valid
            if task.arm == "s2_s1":
                optical = load_cell_arrays(
                    spec.cell_id, spec.product_by_year[task.train_year],
                    spec.label_by_year[task.train_year])
                sampling_valid = optical.valid
            origins = sample_patch_origins(
                sampling_valid, masks["y"], n_patches=n_patches,
                patch=self.patch, positive_fraction=POSITIVE_PATCH_FRACTION,
                seed=_cell_seed(seed, spec.cell_id))
            self.items.append((x, masks["y"], masks["binary_valid"], origins))
        self.index: list[tuple[int, int]] = [
            (j, k) for j, (_, _, _, origins) in enumerate(self.items)
            for k in range(len(origins))]
        self.kinds = np.zeros(len(self.index), dtype=np.int8)

    def set_epoch(self, epoch: int, seed: int) -> None:
        rng = np.random.default_rng(seed * 7919 + epoch)
        self.kinds = rng.integers(0, 6, size=len(self.index)).astype(np.int8)

    def __len__(self) -> int:
        return len(self.index)

    def __getitem__(
        self, idx: int,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        j, k = self.index[idx]
        x, y, valid, origins = self.items[j]
        r0, c0 = origins[k]
        p = self.patch
        ignore = np.zeros_like(valid)
        xt, yt, vt, _ = geometric_transform(
            x[:, r0:r0 + p, c0:c0 + p],
            y[r0:r0 + p, c0:c0 + p],
            valid[r0:r0 + p, c0:c0 + p],
            ignore[r0:r0 + p, c0:c0 + p], int(self.kinds[idx]))
        return (torch.from_numpy(np.ascontiguousarray(xt)).float(),
                torch.from_numpy(np.ascontiguousarray(yt)).float(),
                torch.from_numpy(np.ascontiguousarray(vt)))


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


@torch.no_grad()
def predict_neural(
    model: torch.nn.Module, features: np.ndarray[Any, Any],
    valid: np.ndarray[Any, Any], device: torch.device,
) -> np.ndarray[Any, Any]:
    """Non-overlapping PATCH_PX tiles; NaN outside EO-valid pixels."""
    model.eval()
    c, h, w = features.shape
    p = PATCH_PX
    h2 = max(int(np.ceil(h / p)) * p, p)
    w2 = max(int(np.ceil(w / p)) * p, p)
    canvas = np.zeros((c, h2, w2), dtype=np.float32)
    vcanvas = np.zeros((h2, w2), dtype=bool)
    canvas[:, :h, :w] = features
    vcanvas[:h, :w] = valid
    probs = np.full((h2, w2), np.nan, dtype=np.float32)
    tiles: list[tuple[int, int]] = [
        (r, cc) for r in range(0, h2, p) for cc in range(0, w2, p)
        if vcanvas[r:r + p, cc:cc + p].any()]
    batch = BATCH_SIZE
    for s in range(0, len(tiles), batch):
        chunk = tiles[s:s + batch]
        xt = torch.from_numpy(np.stack([
            canvas[:, r:r + p, cc:cc + p] for r, cc in chunk])).to(device)
        with torch.autocast(device_type="cuda", enabled=device.type == "cuda"):
            logits = model(xt)
        pr = torch.sigmoid(logits.float()).squeeze(1).cpu().numpy()
        for (r, cc), tile in zip(chunk, pr, strict=True):
            probs[r:r + p, cc:cc + p] = tile
    out = probs[:h, :w].copy()
    out[~valid] = np.nan
    return out


def ndvi_volume(raw: np.ndarray[Any, Any], band_names: tuple[str, ...]) -> np.ndarray[Any, Any]:
    i4 = band_names.index("B4")
    i8 = band_names.index("B8")
    denom = raw[i8] + raw[i4]
    ndvi: np.ndarray[Any, Any] = np.divide(raw[i8] - raw[i4], denom,
                     out=np.zeros_like(denom), where=np.abs(denom) > 1e-6)
    out = np.concatenate([raw, ndvi[None]], axis=0)
    return np.asarray(out, dtype=np.float32)


def rf_feature_volume(
    raw: np.ndarray[Any, Any], valid: np.ndarray[Any, Any],
    norm: NormStats, band_names: tuple[str, ...],
) -> np.ndarray[Any, Any]:
    normed = apply_norm(raw, valid, norm)
    extras: list[np.ndarray[Any, Any]] = []
    if "B8" in band_names:
        extras.append(ndvi_volume(raw, band_names)[-1])
    if "VV" in band_names and "VH" in band_names:
        # S1 GRD is stored in dB; the VV-VH log-ratio is their dB
        # difference (frozen rf_pixel feature spec).
        extras.append((raw[band_names.index("VV")]
                       - raw[band_names.index("VH")]).astype(np.float32))
    if extras:
        normed = np.concatenate(
            [normed, *[e[None] for e in extras]], axis=0)
    return normed.astype(np.float32)


def predict_rf(
    rf: Any, volume: np.ndarray[Any, Any], valid: np.ndarray[Any, Any],
) -> np.ndarray[Any, Any]:
    h, w = volume.shape[1:]
    out = np.full((h, w), np.nan, dtype=np.float32)
    idx = np.flatnonzero(valid & np.isfinite(volume).all(axis=0))
    if idx.size:
        probs = rf.predict_proba(volume.reshape(volume.shape[0], -1)[:, idx].T)
        pos = int(np.flatnonzero(rf.classes_ == 1)[0])
        out.reshape(-1)[idx] = probs[:, pos].astype(np.float32)
    return out


# ---------------------------------------------------------------------------
# Spatial block bootstrap and MIXED agreement
# ---------------------------------------------------------------------------


def block_bootstrap_ci(
    views: list[tuple[np.ndarray[Any, Any], np.ndarray[Any, Any],
                      np.ndarray[Any, Any]]],
    threshold: float, block_m: int = BLOCK_BOOTSTRAP_M,
    reps: int = BLOCK_BOOTSTRAP_REPS, seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """1000 m spatial blocks, resampled per independent held-out cell.

    Pixels are never individually resampled. Blocks never cross cell
    boundaries (cells are spatially disjoint W10 units). Per-block
    confusion counts are bootstrapped and IoU/F1/precision/recall are
    recomputed on each replicate.
    """
    bpx = max(1, int(round(block_m / ANALYSIS_PIXEL_M)))
    rows: list[np.ndarray[Any, Any]] = []
    for prob, y, valid in views:
        h, w = valid.shape
        bid = (np.arange(h)[:, None] // bpx).astype(np.int64) * 100000 \
            + (np.arange(w)[None, :] // bpx).astype(np.int64)
        pred = (prob >= threshold) & valid
        ref = y & valid
        keys = bid[valid]
        tp = pred[valid] & ref[valid]
        fp = pred[valid] & ~ref[valid]
        fn = ~pred[valid] & ref[valid]
        order = np.argsort(keys, kind="stable")
        ks = keys[order]
        uniq, starts = np.unique(ks, return_index=True)
        tpb = np.add.reduceat(tp[order], starts)
        fpb = np.add.reduceat(fp[order], starts)
        fnb = np.add.reduceat(fn[order], starts)
        block_rows = np.stack([tpb, fpb, fnb], axis=1).astype(np.int64)
        block_rows = block_rows[(block_rows.sum(axis=1) > 0)]
        rows.append(block_rows)
    all_blocks = np.concatenate(rows, axis=0) if rows else np.zeros(
        (0, 3), dtype=np.int64)
    n_blocks = int(all_blocks.shape[0])
    rng = np.random.default_rng(seed)
    out_iou = np.full(reps, np.nan)
    out_f1 = np.full(reps, np.nan)
    out_p = np.full(reps, np.nan)
    out_r = np.full(reps, np.nan)
    if n_blocks:
        for i in range(reps):
            draw = all_blocks[rng.integers(0, n_blocks, size=n_blocks)]
            tp, fp, fn = (int(v) for v in draw.sum(axis=0))
            if tp + fp + fn:
                out_iou[i] = tp / (tp + fp + fn)
            if 2 * tp + fp + fn:
                out_f1[i] = 2 * tp / (2 * tp + fp + fn)
            if tp + fp:
                out_p[i] = tp / (tp + fp)
            if tp + fn:
                out_r[i] = tp / (tp + fn)
    lo_q = (1 - CI_LEVEL) / 2

    def q(a: np.ndarray[Any, Any]) -> list[float | None]:
        if not np.isfinite(a).any():
            return [None, None]
        return [float(np.nanquantile(a, lo_q)),
                float(np.nanquantile(a, 1 - lo_q))]

    return {
        "block_m": block_m, "block_px": bpx, "n_blocks": n_blocks,
        "reps": reps, "ci_level": CI_LEVEL, "resample_unit": "spatial_block",
        "iou_ci95": q(out_iou), "f1_ci95": q(out_f1),
        "precision_ci95": q(out_p), "recall_ci95": q(out_r)}


def mixed_agreement(
    views: list[tuple[np.ndarray[Any, Any], np.ndarray[Any, Any],
                      np.ndarray[Any, Any], np.ndarray[Any, Any]]],
) -> dict[str, Any]:
    """Descriptive probability-vs-fraction agreement on MIXED pixels."""
    ps: list[np.ndarray[Any, Any]] = []
    fs: list[np.ndarray[Any, Any]] = []
    for prob, fraction, mixed, valid in views:
        sel = mixed & valid & np.isfinite(prob)
        if sel.any():
            ps.append(prob[sel])
            fs.append(fraction[sel])
    if not ps:
        return {"n_mixed_pixels": 0}
    p = np.concatenate(ps)
    f = np.concatenate(fs)
    if np.std(f) < 1e-12 or np.std(p) < 1e-12:
        rho = pearson = None
    else:
        from scipy.stats import spearmanr
        rho = float(spearmanr(p, f).statistic)
        pearson = float(np.corrcoef(p, f)[0, 1])
    return {
        "n_mixed_pixels": int(p.size),
        "spearman_prob_fraction": rho,
        "pearson_prob_fraction": pearson,
        "mae_prob_fraction": float(np.mean(np.abs(p - f))),
        "mean_prob_on_mixed": float(p.mean()),
        "mean_fraction_mixed": float(f.mean())}


# ---------------------------------------------------------------------------
# Evaluation assembly
# ---------------------------------------------------------------------------


def pooled_view(
    bin_views: list[tuple[np.ndarray[Any, Any], np.ndarray[Any, Any],
                          np.ndarray[Any, Any]]],
    threshold: float,
) -> dict[str, Any]:
    """Metrics pooled over independent cells.

    Confusion/AUPRC/calibration/area use pooled pixels; boundary and
    connected-patch statistics are computed inside each cell (they are
    spatial and must not cross cell boundaries) and aggregated from
    their raw counts.
    """
    pf = [np.nan_to_num(v[0]).ravel() for v in bin_views]
    yf = [v[1].ravel() for v in bin_views]
    vf = [v[2].ravel() for v in bin_views]
    p, y, v = np.concatenate(pf), np.concatenate(yf), np.concatenate(vf)
    c = confusion(p, y, v, threshold)
    rates = pixel_rates(c)
    area = area_metrics((p[v] >= threshold), y[v].astype(bool))
    out: dict[str, Any] = {
        "threshold": threshold,
        "n_valid_pixels": int(v.sum()),
        "n_positive_pixels": int(y.sum()),
        **rates,
        "auprc": auprc(p, y, v),
        **calibration(p, y, v),
        **area,
    }
    for tol, key in ((1, "bf1_30m"), (2, "bf1_60m")):
        bp_tot = br_tot = 0
        bp_match = br_match = 0
        for prob, yy, vv in bin_views:
            pred = (prob >= threshold) & vv
            ref = yy & vv
            bp, br = _boundary(pred), _boundary(ref)
            if bp.any():
                d = ndimage.distance_transform_edt(~br)
                bp_tot += int(bp.sum())
                bp_match += int((d[bp] <= tol).sum())
            if br.any():
                d = ndimage.distance_transform_edt(~bp)
                br_tot += int(br.sum())
                br_match += int((d[br] <= tol).sum())
        if bp_tot + br_tot == 0:
            out[key] = None
        elif bp_tot == 0 or br_tot == 0:
            out[key] = 0.0
        else:
            prec = bp_match / bp_tot
            rec = br_match / br_tot
            out[key] = (2 * prec * rec / (prec + rec)
                        if prec + rec else 0.0)
    for min_iou, key in ((0.25, "patch_025"), (0.50, "patch_050")):
        n_ref = n_pred = n_match = small_ref = small_match = 0
        for prob, yy, vv in bin_views:
            pred = (prob >= threshold) & vv
            ref = yy & vv
            m = patch_matching(pred, ref, min_iou)
            n_ref += int(m["n_ref"])
            n_pred += int(m["n_pred"])
            n_match += int(m["n_matches"])
            matched_ref = {x[0] for x in m["matches"]}
            rlab = ndimage.label(
                ref, structure=np.ones((3, 3), dtype="uint8"))[0]
            sizes = np.bincount(rlab.ravel())
            small_ids = {i for i in range(1, len(sizes))
                         if sizes[i] < 10}
            small_ref += len(small_ids)
            small_match += len(small_ids & matched_ref)
        out[key] = {
            "n_ref": n_ref, "n_pred": n_pred, "n_matches": n_match,
            "patch_precision": (n_match / n_pred) if n_pred else None,
            "patch_recall": (n_match / n_ref) if n_ref else None,
            "small_ref_count": small_ref,
            "small_patch_recall": (
                small_match / small_ref) if small_ref else None}
    return out


def evaluate_role(
    predict: Any, task: TaskSpec, role: str, year: int, threshold: float,
    bootstrap: bool = False,
) -> tuple[dict[str, Any], list[tuple[str, np.ndarray[Any, Any]]]]:
    per_cell: list[dict[str, Any]] = []
    bin_views: list[tuple[np.ndarray[Any, Any], np.ndarray[Any, Any],
                          np.ndarray[Any, Any]]] = []
    mix_views: list[tuple[np.ndarray[Any, Any], np.ndarray[Any, Any],
                          np.ndarray[Any, Any], np.ndarray[Any, Any]]] = []
    prob_store: list[tuple[str, np.ndarray[Any, Any]]] = []
    for spec in task.cells_of(role):
        arrays = open_cell(spec, year)
        masks = cell_masks(arrays, task.label_family, year)
        prob = predict(arrays)
        prob_store.append((spec.cell_id, prob))
        bv = masks["binary_valid"]
        metrics = evaluate_view(np.nan_to_num(prob), masks["y"], bv,
                                threshold)
        metrics.update({
            "cell_id": spec.cell_id, "province": spec.province,
            "positive_cell": spec.positive, "year": year,
            "n_mixed_pixels": int(masks["mixed"].sum()),
            "n_unknown_pixels": int(masks["unknown"].sum()),
            "eo_valid_fraction": float(arrays.valid.mean())})
        per_cell.append(metrics)
        bin_views.append((np.nan_to_num(prob), masks["y"], bv))
        mix_views.append((prob, arrays.fraction, masks["mixed"],
                          arrays.valid))

    def pooled(keep: list[bool]) -> dict[str, Any]:
        views = [v for v, k in zip(bin_views, keep, strict=True) if k]
        return pooled_view(views, threshold)

    cells = task.cells_of(role)
    keep_all = [True] * len(cells)
    out: dict[str, Any] = {
        "n_cells": len(cells),
        "n_positive_cells": sum(c.positive for c in cells),
        "pooled": pooled(keep_all),
        "per_cell": per_cell}
    if role == "test":
        out["strata"] = {
            "positive_cells": pooled([c.positive for c in cells]),
            "background_cells": pooled([not c.positive for c in cells])}
        if bootstrap:
            out["block_bootstrap"] = block_bootstrap_ci(bin_views, threshold)
        out["mixed_agreement"] = mixed_agreement(mix_views)
    return out, prob_store


def pooled_val_threshold(
    predict: Any, task: TaskSpec,
) -> tuple[float, float, dict[str, Any]]:
    probs: list[np.ndarray[Any, Any]] = []
    ys: list[np.ndarray[Any, Any]] = []
    vs: list[np.ndarray[Any, Any]] = []
    per_cell: list[dict[str, Any]] = []
    for spec in task.cells_of("val"):
        arrays = open_cell(spec, task.train_year)
        masks = cell_masks(arrays, task.label_family, task.train_year)
        prob = predict(arrays)
        bv = masks["binary_valid"]
        probs.append(np.nan_to_num(prob).ravel())
        ys.append(masks["y"].ravel())
        vs.append(bv.ravel())
        per_cell.append({
            "cell_id": spec.cell_id, "positive_cell": spec.positive,
            "n_positive_pixels": int(masks["y"].sum())})
    p = np.concatenate(probs)
    y = np.concatenate(ys)
    v = np.concatenate(vs)
    threshold, iou = choose_threshold(p, y, v, THRESHOLD_GRID_DEFAULT)
    return threshold, iou, {"per_cell": per_cell,
                            "n_val_positive_pixels": int(y.sum())}


# ---------------------------------------------------------------------------
# Environment / manifest helpers
# ---------------------------------------------------------------------------


def gpu_info(gpu_index: int) -> dict[str, Any]:
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits", "-i", str(gpu_index)],
            capture_output=True, text=True, check=True)
        name, vram, driver = (
            x.strip() for x in out.stdout.splitlines()[0].split(",")[:3])
        return {"id": gpu_index, "model": name, "vram_mib": int(vram),
                "driver": driver}
    except Exception as exc:  # noqa: BLE001 - metadata only
        return {"id": gpu_index, "model": "UNKNOWN", "vram_mib": None,
                "driver": "UNKNOWN", "error": str(exc)}


def environment_fingerprint() -> dict[str, str]:
    import segmentation_models_pytorch as smp
    import sklearn
    import transformers

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "cuda": str(torch.version.cuda),
        "smp": smp.__version__,
        "transformers": transformers.__version__,
        "sklearn": sklearn.__version__,
        "hostname": platform.node()}


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True).stdout.strip()


def git_dirty() -> bool:
    return bool(subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True).stdout.strip())


def _run_dir(task: str, model: str, seed: int) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rid = f"{task}_{model}_seed-{seed}_{stamp}"
    d = RUNS_ROOT / task / model / f"seed-{seed}" / rid
    d.mkdir(parents=True, exist_ok=False)
    return d


# ---------------------------------------------------------------------------
# Train one run: neural models
# ---------------------------------------------------------------------------


def _build_model(model_name: str, in_channels: int) -> tuple[
        torch.nn.Module, dict[str, Any]]:
    if model_name == "unet":
        from spartina.models.baselines.unet import build_unet
        return build_unet(in_channels, pretrained=True)
    if model_name == "deeplabv3plus":
        from spartina.models.baselines.deeplabv3plus import build_deeplabv3plus
        return build_deeplabv3plus(in_channels, pretrained=True)
    if model_name == "segformer_b0":
        from spartina.models.baselines.segformer_b0 import build_segformer_b0
        return build_segformer_b0(in_channels, pretrained=True)
    raise ValueError(f"unknown neural model {model_name}")


def _train_pos_weight(specs: list[CellSpec], task: TaskSpec) -> float:
    pos = neg = 0
    for spec in specs:
        arrays = open_cell(spec, task.train_year)
        masks = cell_masks(arrays, task.label_family, task.train_year)
        bv = masks["binary_valid"]
        pos += int((masks["y"] & bv).sum())
        neg += int((~masks["y"] & bv).sum())
    ratio = min(POS_WEIGHT_CAP, neg / pos) if pos else float(POS_WEIGHT_CAP)
    return float(ratio)


def run_neural(
    task: TaskSpec, model_name: str, seed: int, gpu_index: int,
    smoke: bool = False,
) -> dict[str, Any]:
    if seed not in SEEDS:
        raise ValueError(f"seed {seed} not in frozen {SEEDS}")
    cfg = dict(MODEL_CONFIGS[model_name])
    max_epochs = 1 if smoke else int(cfg["max_epochs"])
    patience = 1 if smoke else EARLY_STOP_PATIENCE
    n_patches = 8 if smoke else TRAIN_PATCHES_PER_CELL
    device = torch.device(
        f"cuda:{gpu_index}" if torch.cuda.is_available() else "cpu")
    seed_everything(seed)

    norm, norm_audit = pooled_train_norm(task, smoke=smoke)
    t_specs = train_specs(task, smoke)
    pos_weight_value = _train_pos_weight(t_specs, task)
    model, pretrained_meta = _build_model(model_name, task.in_channels)
    model = model.to(device)
    pos_w = torch.tensor(pos_weight_value, device=device)

    dataset = CellPatchDataset(task, norm, seed, n_patches=n_patches,
                               train_cells=t_specs)
    gen = torch.Generator()
    gen.manual_seed(seed)
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True,
                        num_workers=0, generator=gen)
    opt = torch.optim.AdamW(model.parameters(),
                            lr=float(cfg["base_lr"]),
                            weight_decay=float(cfg["weight_decay"]))
    scaler = torch.amp.GradScaler(  # type: ignore[attr-defined]
        "cuda", enabled=device.type == "cuda")

    run_dir = _run_dir(task.task, model_name, seed)
    best_iou = -1.0
    best_epoch = -1
    best_threshold = 0.5
    best_state: dict[str, Any] | None = None
    history: list[dict[str, Any]] = []
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    t0 = time.time()
    nan_abort = False

    def predict_val(arrays: Any) -> np.ndarray[Any, Any]:
        x = apply_norm(arrays.features, arrays.valid, norm)
        return predict_neural(model, x, arrays.valid, device)

    for epoch in range(max_epochs):
        dataset.set_epoch(epoch, seed)
        lr = lr_at_epoch(float(cfg["base_lr"]), epoch, max_epochs,
                         WARMUP_EPOCHS)
        for pg in opt.param_groups:
            pg["lr"] = lr
        model.train()
        ep_losses: list[float] = []
        for xb, yb, vb in loader:
            xb = xb.to(device)
            yb = yb.unsqueeze(1).to(device)
            vb = vb.unsqueeze(1).to(device)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda",
                                enabled=device.type == "cuda"):
                logits = model(xb)
                loss, _, _ = segmentation_loss(logits, yb, vb, pos_w)
            if not torch.isfinite(loss):
                nan_abort = True
                break
            scaler.scale(loss).backward()  # type: ignore[no-untyped-call]
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            ep_losses.append(float(loss.detach().cpu()))
        if nan_abort:
            break
        threshold, val_iou, val_audit = pooled_val_threshold(predict_val, task)
        history.append({
            "epoch": epoch, "lr": lr,
            "train_loss": float(np.mean(ep_losses)) if ep_losses else None,
            "val_iou_2020": val_iou, "val_threshold": threshold,
            "val_audit": val_audit})
        if val_iou > best_iou:
            best_iou, best_epoch, best_threshold = val_iou, epoch, threshold
            best_state = {k: v.detach().cpu()
                          for k, v in model.state_dict().items()}
        if epoch - best_epoch >= patience:
            break

    train_wall = time.time() - t0
    if nan_abort or best_state is None:
        raise RuntimeError(f"{model_name} seed {seed}: non-finite loss "
                           "or no valid validation epoch")
    model.load_state_dict(best_state)

    # TEST is opened only now: selection (state, threshold) is frozen.
    def predict_test(arrays: Any) -> np.ndarray[Any, Any]:
        x = apply_norm(arrays.features, arrays.valid, norm)
        return predict_neural(model, x, arrays.valid, device)

    results = _evaluate_and_persist(
        task, model_name, seed, run_dir, cfg, norm, norm_audit,
        pos_weight_value, best_epoch, best_threshold, best_iou, history,
        train_wall, device, predict_test, best_state, pretrained_meta,
        smoke=smoke)
    return results


# ---------------------------------------------------------------------------
# Train one run: random forest (CPU)
# ---------------------------------------------------------------------------


def run_rf(task: TaskSpec, seed: int, smoke: bool = False) -> dict[str, Any]:
    from spartina.models.baselines.random_forest import fit_rf, sample_train_pixels

    if seed not in SEEDS:
        raise ValueError(f"seed {seed} not in frozen {SEEDS}")
    cfg = dict(MODEL_CONFIGS["rf_pixel"])
    cap = 200 if smoke else int(cfg["pixel_cap_per_train_cell"])
    cfg_fit = {
        "n_estimators": 10 if smoke else int(cfg["n_estimators"]),
        "class_weight": cfg["class_weight"], "max_features": cfg["max_features"],
        "min_samples_leaf": int(cfg["min_samples_leaf"]), "n_jobs": 8}
    seed_everything(seed)
    norm, norm_audit = pooled_train_norm(task, smoke=smoke)
    t_specs = train_specs(task, smoke)

    xs: list[np.ndarray[Any, Any]] = []
    ys: list[np.ndarray[Any, Any]] = []
    pos = neg = 0
    for spec in t_specs:
        arrays = open_cell(spec, task.train_year)
        masks = cell_masks(arrays, task.label_family, task.train_year)
        volume = rf_feature_volume(
            arrays.features, arrays.valid, norm, arrays.band_names)
        xc, yc = sample_train_pixels(
            volume, masks["y"], masks["binary_valid"], cap,
            _cell_seed(seed, spec.cell_id))
        xs.append(xc)
        ys.append(yc)
        bv = masks["binary_valid"]
        pos += int((masks["y"] & bv).sum())
        neg += int((~masks["y"] & bv).sum())
    X = np.concatenate(xs)
    y = np.concatenate(ys)
    t0 = time.time()
    rf = fit_rf(X, y, seed, cfg_fit)
    train_wall = time.time() - t0
    pos_weight_value = min(POS_WEIGHT_CAP, neg / pos) if pos else POS_WEIGHT_CAP

    def predict(arrays: Any) -> np.ndarray[Any, Any]:
        volume = rf_feature_volume(
            arrays.features, arrays.valid, norm, arrays.band_names)
        return predict_rf(rf, volume, arrays.valid)

    # threshold on VAL (train year) only
    best_threshold, best_iou, val_audit = pooled_val_threshold(predict, task)

    run_dir = _run_dir(task.task, "rf_pixel", seed)
    results = _evaluate_and_persist(
        task, "rf_pixel", seed, run_dir, cfg, norm, norm_audit,
        pos_weight_value, best_epoch=0, threshold=best_threshold,
        val_iou=best_iou, history=[{"val_audit": val_audit}],
        train_wall_s=train_wall, device=torch.device("cpu"),
        predict=predict, checkpoint_obj=rf, pretrained_meta={
            "pretrained": False, "features": cfg["features"]},
        smoke=smoke)
    return results


def _evaluate_and_persist(
    task: TaskSpec, model_name: str, seed: int, run_dir: Path,
    cfg: dict[str, Any], norm: NormStats, norm_audit: dict[str, Any],
    pos_weight_value: float, best_epoch: int, threshold: float,
    val_iou: float, history: list[dict[str, Any]], train_wall_s: float,
    device: torch.device, predict: Any, checkpoint_obj: Any,
    pretrained_meta: dict[str, Any], smoke: bool,
) -> dict[str, Any]:
    import joblib

    eval_payload: dict[str, Any] = {}
    prob_store_all: dict[str, np.ndarray[Any, Any]] = {}
    val_2020, val_probs = evaluate_role(
        predict, task, "val", task.train_year, threshold, bootstrap=False)
    eval_payload[f"val_{task.train_year}"] = val_2020
    for year in task.eval_years:
        view, probs = evaluate_role(
            predict, task, "test", year, threshold, bootstrap=not smoke)
        eval_payload[f"test_{year}"] = view
        for cell_id, arr in probs:
            prob_store_all[f"{cell_id}_{year}"] = arr
        if year == task.train_year:
            for cell_id, arr in val_probs:
                prob_store_all[f"{cell_id}_{year}_val"] = arr

    # persist prediction arrays (gitignored bytes, outside Git)
    np.savez_compressed(run_dir / "test_outputs.npz", **prob_store_all)

    checkpoint_name = "rf.joblib" if model_name == "rf_pixel" else "best.pt"
    checkpoint_path = run_dir / checkpoint_name
    ckpt_meta: dict[str, Any] = {"checkpoint": checkpoint_name}
    if model_name == "rf_pixel":
        joblib.dump(checkpoint_obj, checkpoint_path)
    else:
        torch.save({
            "model_state": checkpoint_obj, "model": model_name,
            "arm": task.arm, "seed": seed, "best_epoch": best_epoch,
            "val_threshold": threshold, "val_iou_2020": val_iou,
            "norm_stats": norm.to_dict(), "pretrained": pretrained_meta,
            "in_channels": task.in_channels}, checkpoint_path)
    ckpt_meta["checkpoint_sha256"] = sha256_file(checkpoint_path)
    ckpt_meta["checkpoint_size_bytes"] = checkpoint_path.stat().st_size

    peak_vram = (torch.cuda.max_memory_allocated(device) / 2**20
                 if device.type == "cuda" else 0.0)
    n_params = (sum(p.numel() for p in checkpoint_obj.parameters())
                if hasattr(checkpoint_obj, "parameters") else None)
    protocol = json.loads(PROTOCOL_PATH.read_text())
    summary: dict[str, Any] = {
        "protocol_name": PROTOCOL_NAME,
        "task": task.task, "arm": task.arm, "split_id": task.split_id,
        "model": model_name, "seed": seed, "smoke": smoke,
        "status": "COMPLETED",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": git_commit(), "git_dirty": git_dirty(),
        "protocol_checksum": protocol["checksum"],
        "splits_sha256": sha256_file(SPLITS_PATH),
        "support_matrix_sha256": sha256_file(MATRIX_PATH),
        "config": cfg,
        "normalization": norm_audit,
        "pos_weight_cap": POS_WEIGHT_CAP,
        "pos_weight": pos_weight_value,
        "training": {
            "best_epoch": best_epoch, "epochs_run": len(history),
            "val_threshold": threshold,
            f"val_iou_{task.train_year}": val_iou,
            "history": history,
            "train_wall_s": train_wall_s,
            "peak_vram_mib": peak_vram,
            "n_params": n_params,
            "early_stop_patience": EARLY_STOP_PATIENCE},
        "cells": {
            "train": [c.cell_id for c in task.cells_of("train")],
            "val": [c.cell_id for c in task.cells_of("val")],
            "test": [c.cell_id for c in task.cells_of("test")]},
        "evaluation": eval_payload,
        "artifacts": {
            "run_dir": str(run_dir.relative_to(REPO_ROOT)),
            **ckpt_meta,
            "test_outputs": str(
                (run_dir / "test_outputs.npz").relative_to(REPO_ROOT))},
        "gpu": gpu_info(device.index or 0) if device.type == "cuda" else {
            "id": None, "model": "cpu"},
        "environment": environment_fingerprint(),
        "pretrained": pretrained_meta}
    (run_dir / "run_manifest.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2,
                   ensure_ascii=False) + "\n")
    results_dir = RESULTS_DIR / task.task
    results_dir.mkdir(parents=True, exist_ok=True)
    tracked = dict(summary)
    tracked["artifacts"] = dict(summary["artifacts"])
    out_path = results_dir / f"{model_name}_{task.arm}_seed{seed}.json"
    out_path.write_text(json.dumps(tracked, sort_keys=True, indent=2,
                                   ensure_ascii=False) + "\n")
    return summary
