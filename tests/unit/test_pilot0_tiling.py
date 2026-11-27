"""Step 3 contract: deterministic geometry-derived tile IDs and windows."""

from __future__ import annotations

import pytest
from rasterio.transform import Affine

from spartina.data.tiling import (
    TILE_ID_REGEX,
    WindowSpec,
    packed_region_starts,
    parse_tile_id,
    tile_id,
    window_bounds,
    window_transform,
)

GRID = Affine(30.0, 0.0, 309290.0, 0.0, -30.0, 3364370.0)


def test_tile_id_format_and_roundtrip() -> None:
    tid = tile_id("HB2015", 96, 384, 96)
    assert tid == "HB2015_R0096_C0384_P096"
    assert TILE_ID_REGEX.match(tid)
    addr = parse_tile_id(tid)
    assert (addr.grid_id, addr.row_off, addr.col_off, addr.patch) == (
        "HB2015", 96, 384, 96)


def test_tile_id_is_generation_order_independent() -> None:
    # Same grid+address must always map to the same ID, regardless of
    # the order windows happen to be generated in.
    first = [tile_id("HB2015", r, c, 96) for r in (0, 96) for c in (0, 48)]
    second = [tile_id("HB2015", r, c, 96) for c in (48, 0) for r in (96, 0)]
    assert set(first) == set(second)


def test_tile_id_distinct_addresses_distinct_ids() -> None:
    ids = {tile_id("HB2015", r, c, 96) for r in range(0, 97, 48)
           for c in range(0, 97, 48)}
    assert len(ids) == 9


@pytest.mark.parametrize("bad", [
    "tile_00001", "HB2015_R96_C384_P96", "HB2015_R0096_C0384_P9600",
    "HB2015_R-001_C0000_P096", "HB2015_R0096_C0384", "",
])
def test_malformed_tile_ids_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_tile_id(bad)


def test_window_overlap_and_gap() -> None:
    a = WindowSpec(0, 0, 96, 96)
    touch = WindowSpec(0, 96, 96, 96)       # edge-adjacent, no shared px
    overlap = WindowSpec(0, 48, 96, 96)
    distant = WindowSpec(0, 300, 96, 96)
    assert not a.shares_pixels(touch)
    assert a.pixel_gap(touch) == 0
    assert a.shares_pixels(overlap)
    assert a.pixel_gap(overlap) == 0
    assert not a.shares_pixels(distant)
    assert a.pixel_gap(distant) == 300 - 96


def test_packed_starts_deterministic_and_inside_region() -> None:
    s1 = packed_region_starts(501, 96, 48, 0, 501)
    s2 = packed_region_starts(501, 96, 48, 0, 501)
    assert s1 == s2 == sorted(s1)
    assert all(s >= 0 and s + 96 <= 501 for s in s1)
    assert s1[0] == 0 and s1[-1] == 501 - 96


def test_packed_starts_narrow_region_empty() -> None:
    assert packed_region_starts(1292, 96, 48, 100, 150) == []


def test_packed_starts_region_edges_aligned() -> None:
    # Every region gets boundary-aligned windows, never lattice-only.
    starts = packed_region_starts(1292, 96, 48, 851, 1055)
    assert 851 in starts
    assert 1055 - 96 in starts
    assert all(s >= 851 and s + 96 <= 1055 for s in starts)


def test_window_transform_and_bounds() -> None:
    win = WindowSpec(0, 96, 96, 96)
    t = window_transform(GRID, win)
    assert t.c == pytest.approx(309290 + 96 * 30)
    assert t.f == pytest.approx(3364370)
    west, south, east, north = window_bounds(GRID, win)
    assert west == pytest.approx(309290 + 96 * 30)
    assert east == pytest.approx(309290 + 192 * 30)
    assert north == pytest.approx(3364370)
    assert south == pytest.approx(3364370 - 96 * 30)
