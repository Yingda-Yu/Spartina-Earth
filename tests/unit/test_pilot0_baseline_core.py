"""M1.5 Pilot-0 baseline ladder: core (non-torch) contract tests.

Covers: train-only normalization, Hann mosaic blending, window order
invariance, threshold tie-break, component matching, TEST embargo.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

pytest.importorskip("numpy")
scipy = pytest.importorskip("scipy")  # noqa: F841
pytest.importorskip("sklearn")

from spartina.data.normalization import (  # noqa: E402
    apply_normalization,
    compute_band_stats,
)
from spartina.evaluation.metrics import (  # noqa: E402
    choose_threshold,
    patch_matching,
)
from spartina.evaluation.mosaic import ProbabilityMosaic  # noqa: E402
from spartina.experiments import embargo as embargo_mod  # noqa: E402

# ---------------------------------------------------------------- train stats

def test_train_only_normalization_statistics() -> None:
    rng = np.random.default_rng(7)
    stack = np.empty((2, 20, 20), dtype=np.float32)
    # band 0: train region ~ N(0,1), val/test region ~ N(50,1)
    stack[0] = rng.normal(0.0, 1.0, (20, 20)).astype(np.float32)
    stack[1] = rng.normal(2.0, 0.5, (20, 20)).astype(np.float32)
    train_mask = np.zeros((20, 20), dtype=bool)
    train_mask[:10, :] = True
    # extreme values only in train region; out-of-train must not leak
    stack[0, 0, 0] = 1000.0
    stack[0, 15:, :] += 50.0  # outside train
    # NaN invalid pixels
    stack[1, 5, 5] = np.nan
    stats = compute_band_stats(stack, train_mask, 0.005, 0.995)
    assert len(stats) == 2
    clipped_max = stats[0].p995
    assert clipped_max < 50.0  # out-of-train shift ignored
    norm = apply_normalization(stack, stats)
    assert np.nanmean(norm[0, train_mask]) == pytest.approx(0.0,
                                                            abs=1e-6)
    # NaN inputs are filled with normalized zero
    assert norm[1, 5, 5] == 0.0
    assert np.isfinite(norm).all()


# -------------------------------------------------------------------- mosaic

def test_mosaic_hann_blending_and_coverage() -> None:
    m = ProbabilityMosaic(height=144, width=144, patch=96)
    m.add_window(0, 0, np.full((96, 96), 0.2, dtype=np.float32))
    m.add_window(48, 48, np.full((96, 96), 0.8, dtype=np.float32))
    r = m.raster()
    assert np.isnan(r[0, 100])  # never covered
    assert r[0, 0] == pytest.approx(0.2)
    assert r[120, 120] == pytest.approx(0.8)
    # overlap interior: Hann-weighted mean strictly between 0.2 and 0.8
    assert 0.2 < r[70, 70] < 0.8


def test_window_order_invariance() -> None:
    wins = [(0, 0, np.random.default_rng(1).random((96, 96))
             .astype(np.float32)),
            (48, 0, np.random.default_rng(2).random((96, 96))
             .astype(np.float32)),
            (0, 48, np.random.default_rng(3).random((96, 96))
             .astype(np.float32)),
            (48, 48, np.random.default_rng(4).random((96, 96))
             .astype(np.float32))]
    a = ProbabilityMosaic(144, 144, 96)
    b = ProbabilityMosaic(144, 144, 96)
    for w in wins:
        a.add_window(*w)
    for w in reversed(wins):
        b.add_window(*w)
    ra, rb = a.raster(), b.raster()
    np.testing.assert_allclose(ra, rb, equal_nan=True, rtol=1e-12,
                               atol=1e-12)


# --------------------------------------------------------------- thresholds

def test_threshold_tie_break_prefers_half_then_lower() -> None:
    # All-positive valid set with a single TP at prob .4: any threshold
    # <= .4 gives identical confusion -> ties; closest to 0.5 wins.
    prob = np.zeros(10, dtype=np.float64)
    prob[0] = 0.4
    y = np.zeros(10, dtype=np.int8)
    y[0] = 1
    valid = np.ones(10, dtype=bool)
    t, iou = choose_threshold(prob, y, valid)
    assert t == pytest.approx(0.4)
    assert iou == pytest.approx(1.0)
    # symmetric tie on both sides of 0.5 -> lower threshold wins
    prob2 = np.array([0.3, 0.3, 0.7, 0.7])
    y2 = np.array([1, 1, 1, 1], dtype=np.int8)
    valid2 = np.ones(4, dtype=bool)
    t2, _ = choose_threshold(prob2, y2, valid2)
    assert t2 == pytest.approx(0.3)


# ------------------------------------------------------------- patch metrics

def test_component_one_to_one_matching_and_small_patch() -> None:
    ref = np.zeros((40, 40), dtype=bool)
    pred = np.zeros((40, 40), dtype=bool)
    ref[2:8, 2:8] = True          # 36 px
    pred[2:8, 2:8] = True         # exact match -> IoU 1.0
    ref[20, 20] = True            # 1 px small component
    pred[20, 20] = True
    pred[30:33, 30:33] = True     # unmatched FP component
    res25 = patch_matching(pred, ref, 0.25)
    assert res25["n_ref"] == 2
    assert res25["n_matches"] == 2
    assert res25["patch_precision"] == pytest.approx(2 / 3)
    assert res25["small_ref_count"] == 1
    assert res25["small_patch_recall"] == pytest.approx(1.0)
    res50 = patch_matching(pred, ref, 0.50)
    assert res50["n_matches"] == 2


def test_small_patch_recall_na_when_absent() -> None:
    ref = np.zeros((20, 20), dtype=bool)
    pred = np.zeros((20, 20), dtype=bool)
    ref[2:14, 2:14] = True
    pred[2:14, 2:14] = True
    res = patch_matching(pred, ref, 0.25)
    assert res["small_ref_count"] == 0
    assert res["small_patch_recall"] is None


# ------------------------------------------------------------------ embargo

def _lock_payload(status: str = "FROZEN", sfp: str = "s1",
                  norm: str = "n1") -> dict[str, str]:
    return {"status": status, "split_logical_fingerprint": sfp,
            "normalization_sha256": norm}


def test_test_embargo_violation_fixture(tmp_path, monkeypatch) -> None:
    lock = tmp_path / "FINAL_EVAL_LOCK.json"
    gate = embargo_mod.EmbargoGate(lock, "s1", "n1")

    # (a) normal training command: env unset -> denied
    monkeypatch.delenv(embargo_mod.ALLOW_TEST_ENV, raising=False)
    with pytest.raises(embargo_mod.TestEmbargoError):
        gate.request_split("test")
    assert gate.request_split("train") is None
    assert gate.request_split("val") is None

    # (b) env set but no lock file -> denied
    monkeypatch.setenv(embargo_mod.ALLOW_TEST_ENV, "1")
    with pytest.raises(embargo_mod.TestEmbargoError):
        gate.request_split("test")

    # (c) lock exists but not FROZEN -> denied
    lock.write_text(json.dumps(_lock_payload(status="DRAFT")))
    with pytest.raises(embargo_mod.TestEmbargoError):
        gate.request_split("test")

    # (d) FROZEN but fingerprint mismatch -> denied
    lock.write_text(json.dumps(_lock_payload(sfp="other")))
    with pytest.raises(embargo_mod.TestEmbargoError):
        gate.request_split("test")
    lock.write_text(json.dumps(_lock_payload(norm="other")))
    with pytest.raises(embargo_mod.TestEmbargoError):
        gate.request_split("test")

    # (e) everything consistent -> allowed exactly in final eval mode
    lock.write_text(json.dumps(_lock_payload()))
    assert gate.request_split("test") is None
