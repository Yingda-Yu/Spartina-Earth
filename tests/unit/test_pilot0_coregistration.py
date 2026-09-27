"""Unit tests for Pilot-0 co-registration / arbitration primitives.

These tests exercise pure functions imported from the scripts
(scripts/ is not a package); rasterio/scipy are optional deps.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "data" / "hangzhou2015"

rasterio = pytest.importorskip("rasterio")  # noqa: F841
scipy = pytest.importorskip("scipy")  # noqa: F841


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def coreg():
    return _load("coregister")


@pytest.fixture(scope="module")
def arbitrate():
    return _load("arbitrate_labels")


def test_snapped_grid_deterministic_and_anchored(coreg):
    from rasterio.transform import Affine

    west, south, east, north = 309313.0, 3349363.9, 348028.8, 3364366.7
    g1, w1, h1, b1 = coreg.snapped_grid(west, south, east, north, 30.0)
    g2, w2, h2, b2 = coreg.snapped_grid(west, south, east, north, 30.0)
    assert (w1, h1) == (w2, h2)
    assert Affine(*g2) == Affine(*g1)
    assert b1 == b2
    # origin must sit on a 30 m lattice from the UTM false easting
    assert (g1[2] - 500_000.0) % 30.0 == 0.0
    assert (g1[5] - 500_000.0) % 30.0 == 0.0
    # covering grid must contain the source bounds
    assert b2[0] <= west and b2[1] <= south
    assert b2[2] >= east and b2[3] >= north


def test_lag_ncc_finds_known_shift(coreg):
    rng = np.random.default_rng(7)
    base = rng.standard_normal((80, 80))
    valid = np.ones_like(base, dtype=bool)
    shifted = np.roll(np.roll(base, 2, axis=1), -1, axis=0)
    res = coreg.lag_ncc(base, shifted, 5, valid)
    # moving (shifted) must be moved WEST 2 and SOUTH 1 to match fixed
    assert res["best_dx_px"] == -2
    assert res["best_dy_px"] == 1
    assert res["peak_ncc"] > 0.9


def test_lag_ncc_zero_shift_identity(coreg):
    rng = np.random.default_rng(11)
    a = rng.standard_normal((60, 60))
    valid = np.ones_like(a, dtype=bool)
    res = coreg.lag_ncc(a, a, 4, valid)
    assert (res["best_dx_px"], res["best_dy_px"]) == (0, 0)
    assert res["peak_ncc"] == pytest.approx(1.0, abs=1e-9)


def test_resampling_signature_detects_nn_upsampling(coreg):
    rng = np.random.default_rng(3)
    fine_native = rng.standard_normal((90, 90))
    # genuine factor-3 NN enlargement
    up = np.repeat(np.repeat(fine_native, 3, axis=0), 3, axis=1)
    sig = coreg.resampling_signature(
        up, np.ones_like(up, dtype=bool), factor=3)
    assert sig["nn_upsampled_control_share"] == pytest.approx(1.0)
    assert sig["identical_block_share"] > 0.99
    # a genuinely fine image must not look like NN enlargement
    fine = rng.standard_normal(up.shape)
    sig2 = coreg.resampling_signature(
        fine, np.ones_like(fine, dtype=bool), factor=3)
    assert sig2["identical_block_share"] < 0.01


def test_confusion_identities(arbitrate):
    weak = np.array([[1, 1, 0, 0], [1, 0, 0, 0]], dtype="uint8")
    silver = np.array([[1, 0, 0, 1], [1, 0, 0, 0]], dtype="uint8")
    valid = np.ones_like(weak, dtype=bool)
    c = arbitrate.confusion(weak, silver, valid)
    assert c["both_tp_pixels"] == 2
    assert c["weak_only_fp_pixels"] == 1
    assert c["silver_only_fn_pixels"] == 1
    assert c["neither_tn_pixels"] == 4
    assert c["jaccard"] == pytest.approx(2 / 4)
    assert c["precision_of_weak_vs_silver"] == pytest.approx(2 / 3)
    assert c["recall_of_weak_vs_silver"] == pytest.approx(2 / 3)


def test_best_threshold_separable(arbitrate):
    values = np.linspace(-1, 1, 1000, dtype="float64")
    target = values < -0.25
    valid = np.ones_like(target, dtype=bool)
    res = arbitrate.best_threshold(values, target, valid, "less",
                                   n_steps=200)
    assert res["threshold"] == pytest.approx(-0.25, abs=0.02)
    assert res["jaccard"] > 0.99


def test_shift_scan_peak_at_zero_when_aligned(arbitrate):
    a = np.zeros((40, 40), dtype="uint8")
    a[10:20, 10:20] = 1
    b = a.copy()
    res = arbitrate.shift_jaccard_scan(a == 1, b == 1, max_shift=5)
    assert res["peak_at_zero"] is True
    assert res["jaccard_at_zero"] == pytest.approx(1.0)


def test_shift_scan_detects_translation(arbitrate):
    silver = np.zeros((40, 40), dtype="uint8")
    silver[10:20, 10:20] = 1
    weak = np.roll(silver, 2, axis=0)  # weak is silver shifted down 2 px
    res = arbitrate.shift_jaccard_scan(weak == 1, silver == 1, max_shift=5)
    assert tuple(res["best_shift_row_col_px"]) == (2, 0)
    assert res["best_jaccard"] > res["jaccard_at_zero"]
