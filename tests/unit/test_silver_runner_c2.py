"""Unit tests for the frozen SpartinaShift-Silver v0.1 C2 runner logic."""

from __future__ import annotations

import numpy as np
import pytest

from spartina.benchmark.silver import runner as R
from spartina.benchmark.silver.protocol import (
    BLOCK_BOOTSTRAP_M,
    SEEDS,
)
from spartina.benchmark.silver.protocol import (
    protocol_checksum as frozen_checksum,
)
from spartina.evaluation.metrics import evaluate_view


@pytest.fixture(scope="module")
def frozen():
    protocol, splits, matrix = R.load_frozen_inputs()
    task = R.build_c2_spec(matrix, splits, arm="s2")
    return protocol, splits, matrix, task


def test_protocol_checksum_verifies(frozen):
    protocol, _, _, _ = frozen
    assert protocol["checksum"] == frozen_checksum(protocol)
    assert protocol["status"] == "FROZEN_PRE_TRAINING"


def test_tampered_protocol_rejected(frozen):
    protocol, _, _, _ = frozen
    tampered = dict(protocol)
    tampered["model_configs"] = {"rf_pixel": {"n_estimators": 1}}
    assert frozen_checksum(tampered) != protocol["checksum"]


def test_c2_spec_roles_and_products(frozen):
    _, _, _, task = frozen
    assert task.in_channels == 4
    assert task.eval_years == (2020, 2021)
    counts = {r: len(task.cells_of(r)) for r in ("train", "val", "test")}
    assert counts == {"train": 11, "val": 3, "test": 4}
    for spec in task.cells.values():
        assert set(spec.product_by_year) == {2020, 2021}
        assert all(pid.split("_")[2] == "S2"
                   for pid in spec.product_by_year.values())
        assert spec.label_by_year == {2020: "CMSA_2020", 2021: "CMSA_2021"}
        assert spec.extra_product_by_year == {}
    assert sum(c.positive for c in task.cells_of("train")) == 2
    assert sum(c.positive for c in task.cells_of("val")) == 1
    assert sum(c.positive for c in task.cells_of("test")) == 2


def test_resolve_product_missing_raises(frozen):
    _, _, matrix, _ = frozen
    with pytest.raises(ValueError, match="expected exactly 1"):
        R._resolve_product(
            matrix, "CNA10K-R00346-C00154", 2020, "sentinel2", "CMSA_1999")


def test_train_specs_smoke(frozen):
    _, _, _, task = frozen
    assert len(R.train_specs(task, smoke=False)) == 11
    smoke_cells = R.train_specs(task, smoke=True)
    assert len(smoke_cells) == 2
    assert smoke_cells == task.cells_of("train")[:2]


def _synth_views(h=64, w=64, seed=0):
    rng = np.random.default_rng(seed)
    y = np.zeros((h, w), dtype=bool)
    y[10:20, 10:20] = True
    y[40:55, 40:55] = True
    prob = rng.random((h, w)).astype(np.float32) * 0.3
    prob[12:19, 12:19] += 0.6
    valid = np.ones((h, w), dtype=bool)
    valid[:3, :] = False
    return np.clip(prob, 0, 1), y, valid


def test_pooled_view_equals_single_cell_view():
    prob, y, valid = _synth_views()
    single = evaluate_view(prob, y, valid, 0.5)
    pooled = R.pooled_view([(prob, y, valid)], 0.5)
    for key in ("iou", "precision", "recall", "f1", "auprc", "bf1_30m",
                "bf1_60m", "brier", "ece", "pred_area_ha", "ref_area_ha",
                "signed_area_bias"):
        assert pooled[key] == pytest.approx(single[key])
    for key in ("patch_025", "patch_050"):
        for sub in ("n_ref", "n_pred", "n_matches", "patch_precision",
                    "patch_recall"):
            assert pooled[key][sub] == single[key][sub]


def test_pooled_view_all_negative_cell_safe():
    rng = np.random.default_rng(1)
    h = w = 64
    prob = rng.random((h, w)).astype(np.float32) * 0.3
    valid = np.ones((h, w), dtype=bool)
    y = np.zeros((h, w), dtype=bool)
    out = R.pooled_view([(prob, y, valid)], 0.5)
    assert out["iou"] is None
    assert out["recall"] is None
    assert out["n_positive_pixels"] == 0
    assert out["patch_025"]["n_ref"] == 0


def test_block_bootstrap_determinism_and_shape():
    v1 = _synth_views(seed=2)
    v2 = _synth_views(seed=3)
    a = R.block_bootstrap_ci([v1, v2], 0.5, reps=200, seed=123)
    b = R.block_bootstrap_ci([v1, v2], 0.5, reps=200, seed=123)
    c = R.block_bootstrap_ci([v1, v2], 0.5, reps=200, seed=999)
    assert a["block_m"] == BLOCK_BOOTSTRAP_M
    assert a["block_px"] == 33
    assert a["reps"] == 200
    assert a["n_blocks"] == b["n_blocks"]
    assert a["iou_ci95"] == b["iou_ci95"]
    assert a["iou_ci95"][0] <= a["iou_ci95"][1]
    assert c["n_blocks"] == a["n_blocks"]
    for key in ("iou_ci95", "f1_ci95", "precision_ci95", "recall_ci95"):
        assert len(a[key]) == 2


def test_mixed_agreement_descriptive():
    rng = np.random.default_rng(7)
    fraction = np.full((32, 32), np.nan, dtype=np.float32)
    fraction[5:25, 5:25] = np.linspace(0.1, 0.8, 400).reshape(20, 20)
    mixed = (fraction > 0) & (fraction < 0.9)
    prob = fraction * 0.9 + rng.normal(0, 0.02, fraction.shape)
    valid = np.isfinite(fraction)
    out = R.mixed_agreement([(
        np.nan_to_num(prob.astype(np.float32)), fraction, mixed, valid)])
    assert out["n_mixed_pixels"] == 400
    assert out["spearman_prob_fraction"] > 0.99
    assert 0 <= out["mae_prob_fraction"] < 0.1


def test_seeds_are_frozen():
    assert SEEDS == (17, 42, 2026)
    # seed guard runs before any data access
    with pytest.raises(ValueError):
        R.run_rf(None, seed=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        R.run_neural(None, "unet", seed=1, gpu_index=0)  # type: ignore[arg-type]


def test_c5_optical_sar_spec(frozen):
    protocol, splits, matrix, _ = frozen
    task = R.build_c5_spec(protocol, matrix, splits)
    assert task.task == "C5" and task.arm == "s2_s1"
    assert task.in_channels == 6
    # 17 eligible cells; R00279 excluded (no S1-A); roles inherited
    assert len(task.cells) == 17
    counts = {r: len(task.cells_of(r)) for r in ("train", "val", "test")}
    assert counts == {"train": 10, "val": 3, "test": 4}
    excluded = "CNA10K-R00279-C00143"
    assert excluded not in task.cells
    for spec in task.cells.values():
        assert set(spec.extra_product_by_year) == {2020, 2021}
        assert all(pid.split("_")[2] == "S1" and pid.endswith("_A")
                   for pid in spec.extra_product_by_year.values())
