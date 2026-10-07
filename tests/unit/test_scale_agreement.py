"""Unit tests for the Issue #18 scale-audit pure helpers.

These cover agreement arithmetic, binning, mixed-pixel bookkeeping and
spatial block bootstrap semantics. Nothing here reads product bytes and
nothing here is an accuracy claim.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from spartina.labels import scale_agreement as sa


def test_signed_distance_signs_and_band_width() -> None:
    # One foreground pixel in the centre of a 21x21 lattice.
    mask = np.zeros((21, 21), dtype=bool)
    mask[10, 10] = True
    d = sa.signed_distance(mask, 10.0)
    # Foreground pixel: raster EDT measures one cell to the nearest
    # background cell centre -> +10 m inside; adjacent outside is -10 m.
    assert d[10, 10] == pytest.approx(10.0)
    assert d[9, 10] == pytest.approx(-10.0)
    assert d[10, 12] == pytest.approx(-20.0)
    # Far corner is negative and large, never zero (regression guard:
    # swapped EDT branches produced an all-zero field).
    assert d[0, 0] == pytest.approx(-10.0 * math.sqrt(200.0))
    # A solid block: interior pixels are positive (distance to boundary).
    block = np.zeros((21, 21), dtype=bool)
    block[5:16, 5:16] = True
    db = sa.signed_distance(block, 10.0)
    assert db[10, 10] > 0.0
    assert db[0, 0] < 0.0
    band = np.abs(db) <= 20.0
    assert int(band.sum()) == 21 * 21 - int((np.abs(db) > 20.0).sum())
    assert int((np.abs(db) > 20.0).sum()) > 0


def test_distance_band_first_lattice_ring_is_near() -> None:
    # The runner bins distance with right-inclusive edges so the
    # pre-registered "0-30m" near band contains the first lattice ring
    # on BOTH supports (30 m on the 30 m grid; 10/20/30 m on the 10 m
    # grid). A left-open convention leaves the band empty at 30 m.
    import importlib.util
    import sys

    path = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "scripts" / "analysis" / "labels" / "run_2020_scale_audit.py"
    )
    spec = importlib.util.spec_from_file_location("run_2020_scale_audit", path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    sys.modules["run_2020_scale_audit"] = runner
    spec.loader.exec_module(runner)

    d = np.array([0.0, 10.0, 20.0, 30.0, 42.4, 60.0, 120.0, 300.0, 300.1])
    labels = runner.distance_labels(d).tolist()
    assert labels == [
        "0-30m", "0-30m", "0-30m", "0-30m", "30-60m",
        "30-60m", "60-120m", "120-300m", ">=300m",
    ]


def test_jaccard_and_dice_known_values() -> None:
    # areas: A=8, B=6, intersection=4 -> union=10
    assert sa.jaccard(4.0, 8.0, 6.0) == pytest.approx(0.4)
    assert sa.dice(4.0, 8.0, 6.0) == pytest.approx(8.0 / 14.0)
    assert math.isnan(sa.jaccard(0.0, 0.0, 0.0))


def test_area_bias_and_omission_commission() -> None:
    # A smaller than B: B omits nothing relative to itself; A commission 0.
    assert sa.area_bias(9.0, 10.0) == pytest.approx(-0.1)
    omission, commission = sa.omission_commission(8.0, 10.0, 7.0)
    assert omission == pytest.approx(3.0)
    assert commission == pytest.approx(1.0)


def test_assign_bin_boundaries_are_consistent() -> None:
    edges = sa.PATCH_BIN_EDGES
    labels = sa.PATCH_BIN_LABELS
    assert sa.assign_bin(0.0, edges, labels) == "<100m2(sliver)"
    assert sa.assign_bin(99.99, edges, labels) == "<100m2(sliver)"
    assert sa.assign_bin(900.0, edges, labels) == "900-2500m2"
    assert sa.assign_bin(10_000.0, edges, labels) == "1e4-1e5m2"
    assert sa.assign_bin(5e8, edges, labels) == ">=1e5m2"
    # Distance bins share the same rule.
    assert sa.assign_bin(0.0, sa.DISTANCE_BIN_EDGES,
                         sa.DISTANCE_BIN_LABELS) == "0-30m"
    assert sa.assign_bin(301.0, sa.DISTANCE_BIN_EDGES,
                         sa.DISTANCE_BIN_LABELS) == ">=300m"
    assert sa.assign_bin(299.9, sa.DISTANCE_BIN_EDGES,
                         sa.DISTANCE_BIN_LABELS) == "120-300m"


def test_fine_coverage_bins_monotone() -> None:
    cover = np.array([0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0])
    idx = sa.fine_coverage_bins(cover)
    # Five bins, right-edge inclusive per pre-registered "(0,0.25]"
    # notation: exact zero, then four positive bands; 0.75-1.0 bin 4.
    assert idx.tolist() == [0, 1, 1, 2, 3, 4, 4]


def test_mixed_pixel_split_partitions_all_pixels() -> None:
    g = np.array([0, 0, 0, 1, 1, 1], dtype=np.uint8)
    cover = np.array([0.05, 0.5, 0.95, 0.05, 0.5, 0.95])
    split = sa.mixed_pixel_split(g, cover)
    assert sum(split.values()) == g.size
    # H6 diagnostic cells: coarse=1 with mixed fine occupancy, and
    # coarse=0 with high fine occupancy, are counted explicitly.
    assert split["g0_fine_mixed"] == 1
    assert split["g1_fine_mixed"] == 1
    assert split["g1_fine_empty"] == 1
    assert split["g0_fine_full"] == 1


def test_tally_accumulates_counts_and_areas() -> None:
    tally = sa.Tally()
    tally.add_many(
        [("r1", "near"), ("r1", "near"), ("r2", "far")],
        np.array([1, 2, 1]),
        np.array([900.0, 1800.0, 900.0]),
    )
    rows = tally.rows(("region", "band"))
    near = next(r for r in rows if r["band"] == "near")
    assert near["pixel_count"] == 3
    assert near["area_km2"] == pytest.approx(0.0027)


def test_block_bootstrap_ci_blocks_not_pixels() -> None:
    rng = np.random.default_rng(0)
    # 40 spatial blocks with block-level mean disagreement.
    blocks = rng.beta(2, 5, size=40)
    lo, hi = sa.block_bootstrap_ci(blocks, n_boot=200, seed=7)
    point = float(blocks.mean())
    assert lo <= point <= hi
    assert hi - lo < 0.25
    # Degenerate case.
    nan_lo, nan_hi = sa.block_bootstrap_ci(np.array([]), n_boot=10)
    assert math.isnan(nan_lo) and math.isnan(nan_hi)


def test_block_bootstrap_weights_affect_interval() -> None:
    blocks = np.array([0.0, 0.0, 0.0, 1.0, 1.0])
    w_ones = np.array([100.0, 100.0, 100.0, 1.0, 1.0])
    lo_w, hi_w = sa.block_bootstrap_ci(blocks, w_ones, n_boot=400, seed=3)
    # Weighted resamples draw almost only the zero-valued blocks.
    assert lo_w >= 0.0
    assert (lo_w + hi_w) / 2.0 < 0.15
