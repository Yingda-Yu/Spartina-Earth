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


def test_domain_variant_mask_keep_only_excludes_provisional() -> None:
    """Part B regression: KEEP_ONLY never contains PROVISIONAL cells.

    The primary Issue #18 inference universe is exactly the two owner
    KEEP statuses; PROVISIONAL_UNRESOLVED cells enter only the explicit
    sensitivity variant; EXCLUDE and missing statuses are always out.
    """
    statuses = np.array([
        "KEEP_MAINLAND_COASTAL",
        "KEEP_ISLAND_COASTAL",
        "PROVISIONAL_UNRESOLVED",
        "EXCLUDE_DOMAIN_ARTIFACT",
        "OUTSIDE",
    ])
    keep = sa.domain_variant_mask(statuses, include_provisional=False)
    assert keep.tolist() == [True, True, False, False, False]
    plus = sa.domain_variant_mask(statuses, include_provisional=True)
    assert plus.tolist() == [True, True, True, False, False]
    # Counts match the frozen Issue #18 domain: 3,011 / 3,021.
    full = np.concatenate([
        np.repeat("KEEP_MAINLAND_COASTAL", 2752),
        np.repeat("KEEP_ISLAND_COASTAL", 259),
        np.repeat("PROVISIONAL_UNRESOLVED", 10),
    ])
    assert int(sa.domain_variant_mask(full, False).sum()) == 3011
    assert int(sa.domain_variant_mask(full, True).sum()) == 3021
    # Shape and order are preserved; the mask is positional, not a join.
    assert keep.shape == statuses.shape


def test_independent_region_block_attribution_rules() -> None:
    """Part A regression: centroid / nearest / ambiguity / reach rules.

    Two province boxes share a vertical border at x=1000 m and cover
    land north of y=0. Centroid pixels on water just offshore are
    nearest-attributed except on the border tie; far-offshore pixels
    stay UNKNOWN and are never forced.
    """
    import importlib.util
    import sys
    from pathlib import Path

    import geopandas as gpd
    from shapely.geometry import box as sbox

    path = Path(__file__).resolve().parents[2] / (
        "scripts/analysis/labels/run_2020_scale_audit.py"
    )
    spec = importlib.util.spec_from_file_location(
        "run_2020_scale_audit_r1", path
    )
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    sys.modules["run_2020_scale_audit_r1"] = runner
    spec.loader.exec_module(runner)
    from spartina.data.national.geometry import CHINA_ALBERS_CRS

    geom_a = sbox(0.0, 0.0, 999.99, 1000.0)
    geom_b = sbox(1000.0, 0.0, 2000.0, 1000.0)
    prov = gpd.GeoDataFrame(
        {"code": np.int32([3, 7]), "name": ["A", "B"]},
        geometry=[geom_a, geom_b], crs=CHINA_ALBERS_CRS,
    )
    hh, hw = 12, 220
    ox, oyn = 0.0, 110.0
    halo = sbox(ox, oyn - hh * 10.0, ox + hw * 10.0, oyn)
    need = np.ones((hh, hw), dtype=bool)
    code, method = runner.independent_region_block(
        prov, halo, ox, oyn, 10.0, hh, hw, need
    )
    # Land row: centroid-within-province, deterministic split.
    assert code[0, 99] == 3 and code[0, 100] == 7
    assert method[0, 99] == runner.INDEP_METHOD_CENTROID
    # Water row 4.5 m offshore: nearest province far from the border.
    assert code[11, 0] == 3 and method[11, 0] == runner.INDEP_METHOD_NEAREST
    assert code[11, 219] == 7 and method[11, 219] == runner.INDEP_METHOD_NEAREST
    # Within the 300 m border tie no attribution is forced (UNKNOWN).
    border_tie = [
        c for c in range(85, 116)
        if method[11, c] == runner.INDEP_METHOD_UNKNOWN
    ]
    assert border_tie, "ambiguous border pixels must remain UNKNOWN"
    # Beyond the 25 km reach: UNKNOWN, never attributed.
    far_halo = sbox(0.0, -26_100.0, 20.0, -26_000.0)
    far_need = np.zeros((10, 2), dtype=bool)
    far_need[5, 0] = True
    far_code, far_method = runner.independent_region_block(
        prov.iloc[[0]], far_halo, 0.0, -26_000.0, 10.0, 10, 2, far_need
    )
    assert far_code[5, 0] == 0
    assert far_method[5, 0] == runner.INDEP_METHOD_UNKNOWN
    # need=False pixels never receive a code even on land.
    none_code, none_method = runner.independent_region_block(
        prov, halo, ox, oyn, 10.0, hh, hw, np.zeros((hh, hw), dtype=bool)
    )
    assert none_code.max() == 0 and none_method.max() == 0

