"""Step 5/7/13 units: components, macro blocks, fingerprints."""

from __future__ import annotations

import numpy as np
import pytest

from spartina.benchmark.splits.blocks import (
    choose_stripe_boundaries,
    make_regions,
)
from spartina.benchmark.splits.components import (
    crossing_component_ids,
    label_components,
)
from spartina.benchmark.splits.fingerprint import (
    logical_manifest_fingerprint,
    split_config_fingerprint,
)


def test_label_components_eight_connectivity_and_registry() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[0, 0] = True
    mask[1, 1] = True       # diagonal: one 8-connected component
    mask[5, 5] = True       # separate
    labels, reg = label_components(mask, "silver")
    assert len(reg) == 2
    assert reg[1].component_id == "silver-0000"
    assert reg[1].pixel_count == 2
    assert (reg[1].bbox_left, reg[1].bbox_right) == (0, 2)
    assert reg[2].component_id == "silver-0001"
    assert labels.dtype == np.int32
    assert set(np.unique(labels)).issubset({0, 1, 2})


def test_crossing_component_ids() -> None:
    labels = np.zeros((4, 10), dtype=np.int32)
    labels[:, 3] = 1            # ends exactly on the left
    labels[:, 6:8] = 2          # straddles boundary 7
    labels[:, 0:2] = 3
    assert crossing_component_ids(labels, 7) == {2}
    assert crossing_component_ids(labels, 9) == set()


def test_make_regions_guard_geometry() -> None:
    r = make_regions(1292, 803, 1103, 48)
    assert (r["train"].owner_start, r["train"].owner_end) == (0, 803)
    assert (r["train"].usable_start, r["train"].usable_end) == (0, 755)
    assert (r["val"].usable_start, r["val"].usable_end) == (851, 1055)
    assert (r["test"].usable_start, r["test"].usable_end) == (1151, 1292)
    # usable interiors never touch: 96 px (= 2 * guard) between them
    assert r["val"].usable_start - r["train"].usable_end == 96
    assert r["test"].usable_start - r["val"].usable_end == 96


def _constant_stats(lo: int, hi: int, q_s, q_w):
    tracks = max(0, (hi - lo) // 200)
    silver = tracks * 2
    return tracks, tracks * 6, silver


def test_choose_boundaries_deterministic_and_target_like() -> None:
    width = 1200
    rng = np.random.default_rng(0)
    col_silver = rng.integers(0, 10, size=width).astype(float)
    col_valid = np.full(width, 100.0)
    empty = np.array([], dtype=np.int64)
    kw = dict(
        region_window_stats=_constant_stats,
        min_column_tracks=1, min_eval_windows=1,
    )
    b1a, b2a, da = choose_stripe_boundaries(
        width, col_silver, col_valid, empty, empty, empty, empty,
        96, 48, **kw)
    b1b, b2b, db = choose_stripe_boundaries(
        width, col_silver, col_valid, empty, empty, empty, empty,
        96, 48, **kw)
    assert (b1a, b2a) == (b1b, b2b)
    assert da["silver_components_cut"] == 0
    assert sum(da["silver_area_shares"]) == pytest.approx(1.0)


def test_choose_boundaries_infeasible_raises() -> None:
    # No window fits a 300 px strip with a 96 px patch and 2-track rule.
    col_silver = np.ones(300)
    empty = np.array([], dtype=np.int64)
    with pytest.raises(RuntimeError):
        choose_stripe_boundaries(
            300, col_silver, col_silver, empty, empty, empty, empty,
            96, 48, _constant_stats,
            min_column_tracks=2, min_eval_windows=5)


def test_logical_fingerprint_order_and_container_insensitive() -> None:
    records = [
        {"tile_id": "HB2015_R0000_C0000_P096", "row_off": 0, "col_off": 0,
         "height": 96, "width": 96, "split": "train",
         "silver_positive_pixels": 5, "silver_eval_pixels": 4,
         "weak_positive_pixels": 0, "weak_eval_pixels": 0,
         "ignore_pixels": 1, "weak_only_candidate_pixels": 0,
         "eligible_for_train": True, "eligible_for_eval": False,
         "exclusion_reason": "", "silver_component_ids": ["silver-0001"],
         "weak_candidate_component_ids": [],
         "source_stack_checksum": "abc"},
        {"tile_id": "HB2015_R0000_C0096_P096", "row_off": 0, "col_off": 96,
         "height": 96, "width": 96, "split": "val",
         "silver_positive_pixels": 0, "silver_eval_pixels": 0,
         "weak_positive_pixels": 3, "weak_eval_pixels": 2,
         "ignore_pixels": 0, "weak_only_candidate_pixels": 3,
         "eligible_for_train": False, "eligible_for_eval": False,
         "exclusion_reason": "", "silver_component_ids": [],
         "weak_candidate_component_ids": ["weakcand-0002"],
         "source_stack_checksum": "abc",
         "generated_utc": "2099-01-01T00:00:00Z"},
    ]
    f1 = logical_manifest_fingerprint(records)
    f2 = logical_manifest_fingerprint(list(reversed(records)))
    assert f1 == f2
    # adding/removing non-logical metadata does not change the fingerprint
    records[0]["generated_utc"] = "1999-01-01T00:00:00Z"
    records[0]["container_path"] = "/tmp/x.parquet"
    assert logical_manifest_fingerprint(records) == f1
    # changing a logical field does
    records[0]["silver_eval_pixels"] = 99
    assert logical_manifest_fingerprint(records) != f1
    cfg = {"patch_px": 96, "guard_band_px": 48}
    assert split_config_fingerprint(cfg) == split_config_fingerprint(dict(cfg))
