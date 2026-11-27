"""Metric + spatial bootstrap test suite (BENCHMARK_METRIC_SPEC.md).

Tests the project metric implementation (src/spartina/evaluation/metrics.py)
and the cluster bootstrap (engineering/metrics/spatial_bootstrap.py).
Run: pytest engineering/tests/test_metrics_and_bootstrap.py -v
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for p in (ROOT, ROOT + "/src", os.path.join(ROOT, "engineering"),
          os.path.join(ROOT, "engineering", "metrics")):
    if p not in sys.path:
        sys.path.insert(0, p)

from spartina.evaluation.metrics import (  # noqa: E402
    boundary_f1,
    calibration,
    confusion,
    negative_log_likelihood,
    pixel_rates,
    area_metrics,
)
from spatial_bootstrap import cluster_bootstrap_ci  # noqa: E402


def valid_all(shape):
    return np.ones(shape, dtype=bool)


# ---------- confusion + pixel rates ----------

def test_confusion_counts():
    prob = np.array([[0.9, 0.1], [0.8, 0.7]])
    y = np.array([[1, 0], [0, 1]])
    c = confusion(prob, y, valid_all((2, 2)), threshold=0.5)
    # p=[[1,0],[1,1]] vs t=[[1,0],[0,1]]: (0,0) tp, (1,0) fp, (1,1) tp, (0,1) tn
    assert c["tp"] == 2 and c["fn"] == 0 and c["fp"] == 1 and c["tn"] == 1


def test_pixel_rates_iou_f1_precision_recall():
    prob = np.array([0.9, 0.2, 0.8, 0.1])
    y = np.array([1, 1, 0, 0])
    c = confusion(prob, y, valid_all(4), threshold=0.5)
    r = pixel_rates(c)
    assert r["iou"] == pytest.approx(1 / 3)     # tp=1, fp=1, fn=1
    assert r["f1"] == pytest.approx(0.5)
    assert r["precision"] == pytest.approx(0.5)
    assert r["recall"] == pytest.approx(0.5)


def test_pixel_rates_empty_prediction():
    prob = np.array([0.1, 0.2])
    y = np.array([1, 1])
    c = confusion(prob, y, valid_all(2), threshold=0.5)
    r = pixel_rates(c)
    assert r["iou"] == 0.0 and r["recall"] == 0.0 and r["precision"] is None


def test_pixel_rates_no_positive_label():
    prob = np.array([0.9, 0.1])
    y = np.array([0, 0])
    c = confusion(prob, y, valid_all(2), threshold=0.5)
    r = pixel_rates(c)
    assert r["iou"] == 0.0 and r["precision"] == 0.0 and r["recall"] is None


def test_perfect_prediction():
    rng = np.random.default_rng(7)
    y = (rng.random((32, 32)) > 0.7).astype(int)
    prob = y.astype(float)
    c = confusion(prob, y, valid_all((32, 32)), threshold=0.5)
    r = pixel_rates(c)
    assert r["iou"] == 1.0 and r["f1"] == 1.0


# ---------- boundary F1 ----------

def test_boundary_f1_perfect():
    y = np.zeros((20, 20), dtype=bool)
    y[5:10, 5:10] = True
    out = boundary_f1(y.copy(), y, tolerance_px=1)
    assert out == pytest.approx(1.0)


def test_boundary_f1_degrades_with_shift():
    y = np.zeros((20, 20), dtype=bool)
    y[5:10, 5:10] = True
    p = np.zeros((20, 20), dtype=bool)
    p[5:10, 7:12] = True  # 2-px shift
    out1 = boundary_f1(p, y, tolerance_px=1)
    out4 = boundary_f1(p, y, tolerance_px=4)
    assert out1 is not None and out1 < out4


# ---------- area metrics ----------

def test_area_metrics_sign_convention():
    # spec: positive signed bias = overestimate (pred - ref)/ref
    ref = np.ones((10, 10), dtype=bool)
    pred = np.zeros((10, 10), dtype=bool)
    m = area_metrics(pred, ref, pixel_area_m2=900.0)
    assert m["signed_area_bias"] == pytest.approx(-1.0)
    assert m["ref_area_ha"] == pytest.approx(9.0)  # 100 px * 900 m2 = 9 ha
    assert m["abs_area_error_ha"] == pytest.approx(9.0)


def test_area_metrics_overestimate_positive():
    ref = np.ones((10, 10), dtype=bool)   # 100 px
    pred = np.ones((11, 10), dtype=bool)  # 110 px (same pixel area, +10 px)
    m = area_metrics(pred, ref, pixel_area_m2=900.0)
    assert m["signed_area_bias"] == pytest.approx(0.1)


# ---------- calibration + NLL ----------

def test_calibration_reasonable():
    rng = np.random.default_rng(17)
    prob = rng.random(1000)
    y = (rng.random(1000) < prob).astype(int)
    out = calibration(prob, y, valid_all(1000))
    assert 0.0 <= out["ece"] <= 1.0
    assert 0.0 <= out["brier"] <= 1.0


def test_calibration_perfectly_calibrated_low_ece():
    rng = np.random.default_rng(23)
    prob = rng.random(20000)
    y = (rng.random(20000) < prob).astype(int)
    out = calibration(prob, y, valid_all(20000))
    assert out["ece"] < 0.05


def test_nll_bounds():
    rng = np.random.default_rng(29)
    prob = rng.random(500)
    y = (rng.random(500) < 0.5).astype(int)
    nll = negative_log_likelihood(prob, y, valid_all(500))
    assert nll > 0.0
    y2 = (prob > 0.5).astype(int)
    nll2 = negative_log_likelihood(np.clip(prob, 0.01, 0.99), y2, valid_all(500))
    assert nll2 < np.log(1 / 0.01)  # confident-correct predictions: bounded NLL


# ---------- spatial cluster bootstrap ----------

def test_bootstrap_recovers_mean_and_is_finite():
    rng = np.random.default_rng(3)
    values = rng.normal(0.5, 0.1, size=200)
    clusters = np.repeat(np.arange(20), 10)
    point, lo, hi, n_cl = cluster_bootstrap_ci(values, clusters, n_boot=500, seed=2026)
    assert n_cl == 20
    assert lo <= point <= hi
    assert point == pytest.approx(values.mean(), abs=1e-9)


def test_bootstrap_widens_with_cluster_correlation():
    rng = np.random.default_rng(11)
    n_cl, k = 20, 10
    cluster_effect = rng.normal(0, 0.3, size=n_cl)
    values = 0.5 + cluster_effect.repeat(k) + rng.normal(0, 0.05, size=n_cl * k)
    clusters = np.repeat(np.arange(n_cl), k)
    _, lo_c, hi_c, _ = cluster_bootstrap_ci(values, clusters, n_boot=1000, seed=2026)
    iid = rng.normal(0.5, 0.3, size=n_cl * k)
    _, lo_i, hi_i, _ = cluster_bootstrap_ci(iid, np.arange(n_cl * k), n_boot=1000, seed=2026)
    assert (hi_c - lo_c) > (hi_i - lo_i)


def test_bootstrap_seed_reproducible():
    rng = np.random.default_rng(5)
    values = rng.normal(0.5, 0.1, size=100)
    clusters = np.repeat(np.arange(10), 10)
    a = cluster_bootstrap_ci(values, clusters, n_boot=300, seed=2026)
    b = cluster_bootstrap_ci(values, clusters, n_boot=300, seed=2026)
    assert a == b


def test_bootstrap_rejects_degenerate_input():
    with pytest.raises(ValueError):
        cluster_bootstrap_ci([0.5], [1])
    with pytest.raises(ValueError):
        cluster_bootstrap_ci([], [])
