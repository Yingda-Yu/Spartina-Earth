"""Tests for the SpartinaShift-Silver v0.1 30 m data layer semantics."""

from __future__ import annotations

import numpy as np
import pytest

from spartina.benchmark.silver.data import (
    apply_norm,
    assert_weak_background_allowed,
    compute_norm_stats,
    feature_band_names,
    geometric_transform,
    sample_patch_origins,
    sensor_of,
    target_masks,
)


def test_sensor_parsing_and_band_names() -> None:
    assert sensor_of("NP19_R00000-C00000_S2_2020") == "sentinel2"
    assert sensor_of("NP19_R00000-C00000_L8_2015") == "landsat8"
    assert sensor_of("NP19_R00000-C00000_S1_2020_A") == "sentinel1"
    assert feature_band_names("sentinel2", False, 4) == (
        "B2", "B3", "B4", "B8")
    assert feature_band_names("landsat8", False, 7)[0] == "SR_B1"
    assert feature_band_names("sentinel1", True, 2) == ("VV", "VH")
    with pytest.raises(ValueError, match="parse sensor"):
        sensor_of("NP19_R00000-C00000_XX_2020")


def test_geodata_mask_semantics() -> None:
    # class map: 0 unknown (outside window), 1 positive, 2 mixed, 3 weak bg
    occ = np.array([[0, 1, 2, 3]], dtype=np.uint8)
    frac = np.array([[np.nan, 1.0, 0.5, 0.0]], dtype=np.float32)
    m = target_masks(frac, occ, "GEODATA", 2020)
    assert m["y"].tolist() == [[False, True, False, False]]
    assert m["background"].tolist() == [[False, False, False, True]]
    assert m["mixed"].tolist() == [[False, False, True, False]]
    assert m["binary_valid"].tolist() == [[False, True, False, True]]
    assert m["ignore"].tolist() == [[True, False, True, False]]


def test_cmsa_mask_semantics_and_whitelist() -> None:
    occ = np.array([[0, 1, 2, 0]], dtype=np.uint8)
    frac = np.array([[0.0, 1.0, 0.4, 0.0]], dtype=np.float32)
    m = target_masks(frac, occ, "CMSA", 2020)
    # fraction 0 is SOURCE_BACKGROUND_WEAK for whitelisted years, never
    # an ecological negative; mixed stays ignored in the binary view.
    assert m["background"].tolist() == [[True, False, False, True]]
    assert m["binary_valid"].tolist() == [[True, True, False, True]]
    assert m["mixed"].tolist() == [[False, False, True, False]]
    assert not m["unknown"].any()
    assert_weak_background_allowed("CMSA", 2020)
    assert_weak_background_allowed("GEODATA", 1990)
    with pytest.raises(ValueError, match="not whitelisted"):
        target_masks(frac, occ, "CMSA", 2019)


def test_norm_uses_valid_pixels_only() -> None:
    feat = np.concatenate([
        np.zeros((1, 4, 4), dtype=np.float32),
        np.full((1, 4, 4), 1000.0, dtype=np.float32)], axis=0)
    feat[0, :2] = 1.0  # band 0: valid rows =1, hidden rows=0
    valid = np.zeros((4, 4), dtype=bool)
    valid[:2] = True
    stats = compute_norm_stats(feat, valid, 0.0, 1.0)
    assert stats.p_low[0] == pytest.approx(1.0)
    assert stats.p_high[0] == pytest.approx(1.0)
    # band 1 has no valid finite values at all (all 1000 but valid rows
    # contribute 1000) -> quantile 1000 not error; instead check band 0
    out = apply_norm(feat, valid, stats)
    assert np.all(out[:, ~valid] == 0.0)
    assert np.isfinite(out).all()


def test_norm_raises_without_valid_pixels() -> None:
    feat = np.ones((1, 2, 2), dtype=np.float32)
    valid = np.zeros((2, 2), dtype=bool)
    with pytest.raises(ValueError, match="no valid training pixels"):
        compute_norm_stats(feat, valid)


def test_patch_origins_deterministic_and_bounded() -> None:
    valid = np.ones((200, 200), dtype=bool)
    y = np.zeros((200, 200), dtype=bool)
    y[100, 100] = True
    o1 = sample_patch_origins(
        valid, y, n_patches=16, patch=128, positive_fraction=0.5,
        seed=42)
    o2 = sample_patch_origins(
        valid, y, n_patches=16, patch=128, positive_fraction=0.5,
        seed=42)
    assert o1 == o2 and len(o1) == 16
    assert all(0 <= r <= 72 and 0 <= c <= 72 for r, c in o1)
    n_with_pos = sum(bool(y[r:r + 128, c:c + 128].any()) for r, c in o1)
    assert n_with_pos >= 8


def test_geometric_transforms_preserve_labels() -> None:
    x = np.arange(2 * 3 * 4, dtype=np.float32).reshape(2, 3, 4)
    y = np.zeros((3, 4), dtype=bool)
    y[0, 0] = True
    valid = np.ones((3, 4), dtype=bool)
    ignore = np.zeros((3, 4), dtype=bool)
    ignore[2, 3] = True
    for kind in range(6):
        xt, yt, vt, it = geometric_transform(
            x, y, valid, ignore, kind)
        assert yt.sum() == y.sum()
        assert it.sum() == ignore.sum()
        assert vt.shape == yt.shape
        assert xt.shape[1:] == yt.shape
