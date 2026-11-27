"""Unit tests for the Issue #19 V2 W10-cell interior morphology gate.

The V2 scientific support is the exact W10 Albers cell, not the larger
covering export window. Frame-edge slivers contiguous with the scene
border must be quantified WARN evidence (even when large), while only
ENCLOSED interior holes trigger the hard FAIL thresholds.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts/data/national" / "pilot19_canary_v2_qa.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("pilot19_canary_v2_qa_gate_test", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


q2 = _load_module()

H = W = 400
PIXEL_M = 10.0


def _cell() -> np.ndarray[Any, Any]:
    """W10 cell support: central 340x340 px inside the export window."""
    inside = np.zeros((H, W), dtype=bool)
    inside[30:370, 30:370] = True
    return inside


def _classify(
    any_bad: np.ndarray[Any, Any],
    all_bad: np.ndarray[Any, Any],
    band_bad: list[np.ndarray[Any, Any]] | None = None,
    band_names: list[str] | None = None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    if band_bad is None:
        band_bad = [all_bad, all_bad]
    if band_names is None:
        band_names = ["VV", "VH"]
    problems, warns, detail = q2.classify_interior_morphology(
        any_bad, all_bad, band_bad, band_names, _cell(), PIXEL_M
    )
    return list(problems), list(warns), dict(detail)


def test_clean_product_has_no_problems_or_warns() -> None:
    bad = np.zeros((H, W), dtype=bool)
    problems, warns, detail = _classify(bad, bad)
    assert problems == []
    assert warns == []
    assert detail["cell_all_band_pixels"] == 0
    assert detail["support"] == "W10_ALBERS_CELL_PIXEL_CENTRES"


def test_frame_edge_sliver_intruding_into_cell_is_warn_not_fail() -> None:
    """Scene frame crosses the top window border and bites into the cell.

    Deliberately larger than the 1e-4 fraction threshold: edge-connected
    geometry must never be classified as an interior hole.
    """
    bad = np.zeros((H, W), dtype=bool)
    bad[0:46, 150:200] = True  # touches window top; 16 rows inside cell
    problems, warns, detail = _classify(bad, bad)
    assert problems == []
    assert any("frame/footprint-edge" in w for w in warns)
    assert detail["interior_hole_components"] == 0
    assert detail["interior_hole_pixels_in_cell"] == 0
    assert detail["footprint_edge_pixels_in_cell"] == 16 * 50
    assert detail["footprint_edge_fraction_in_cell"] >= 1e-4
    assert detail["footprint_edge_max_penetration_px"] == 16.0


def test_enclosed_large_hole_fails_structural_threshold() -> None:
    bad = np.zeros((H, W), dtype=bool)
    bad[100:140, 100:140] = True  # 1600 px == 1.6 ha, fully enclosed
    problems, _warns, detail = _classify(bad, bad)
    assert any("structural enclosed interior hole" in p for p in problems)
    assert detail["largest_interior_hole_pixels"] == 1600
    assert detail["interior_hole_pixels_in_cell"] == 1600
    assert detail["footprint_edge_pixels_in_cell"] == 0


def test_scattered_enclosed_speckle_above_fraction_fails() -> None:
    """Many isolated enclosed pixels: no 1 ha component but systematic."""
    bad = np.zeros((H, W), dtype=bool)
    grid = np.arange(60, 360, 20)
    for r in grid:
        for c in grid:
            bad[r, c] = True
    assert bad.sum() == 225
    problems, _warns, detail = _classify(bad, bad)
    assert any("systematic enclosed interior non-observation" in p for p in problems)
    assert detail["largest_interior_hole_area_m2"] < 10_000
    assert detail["interior_hole_fraction_in_cell"] >= 1e-4


def test_tiny_enclosed_specks_below_fraction_are_warn() -> None:
    bad = np.zeros((H, W), dtype=bool)
    bad[100, 100] = True
    bad[200, 200] = True
    bad[300, 300] = True
    problems, warns, detail = _classify(bad, bad)
    assert problems == []
    assert detail["interior_hole_pixels_in_cell"] == 3
    assert any("sporadic enclosed interior non-observed" in w for w in warns)


def test_band_limited_fill_is_warn_never_hole() -> None:
    any_bad = np.zeros((H, W), dtype=bool)
    all_bad = np.zeros((H, W), dtype=bool)
    vv_bad = np.zeros((H, W), dtype=bool)
    vv_bad[100:120, 100:120] = True  # one polarization only
    any_bad |= vv_bad
    problems, warns, detail = _classify(
        any_bad, all_bad, [vv_bad, np.zeros_like(vv_bad)], ["VV", "VH"]
    )
    assert problems == []
    assert any("band-limited fill" in w for w in warns)
    assert detail["band_limited_by_band"] == {"VV": 400}


def test_window_margin_nonobservation_is_evidence_only() -> None:
    bad = np.zeros((H, W), dtype=bool)
    bad[0:20, 0:300] = True  # outside the cell (rows < 30)
    problems, warns, detail = _classify(bad, bad)
    assert problems == []
    assert warns == []
    assert detail["window_margin_all_band_pixels"] == 20 * 300
    assert detail["cell_all_band_pixels"] == 0


def test_cell_filling_frame_sliver_matches_adjudicated_case() -> None:
    """R00349 S1 2015 geometry: cell ~= whole window, one edge sliver.

    0.5% window-interior fraction under the old window-scoped rule gave a
    hard FAIL although every bad pixel belongs to the single scene-edge
    component. Under the V2 cell support it is WARN, zero enclosed holes.
    """
    inside = np.ones((H, W), dtype=bool)
    bad = np.zeros((H, W), dtype=bool)
    bad[0:22, 178:242] = True  # corner frame sliver touching top border
    problems, warns, detail = q2.classify_interior_morphology(
        bad, bad, [bad, bad], ["VV", "VH"], inside, PIXEL_M
    )
    assert problems == []
    assert detail["interior_hole_components"] == 0
    assert detail["footprint_edge_pixels_in_cell"] == 22 * 64
    assert any("frame/footprint-edge" in w for w in warns)
