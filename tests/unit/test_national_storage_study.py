"""Unit tests for the Issue #19 Phase M storage-study byte accounting.

Only pure helpers are tested here; the builder itself replays the frozen
national census and is run explicitly, never from the test suite.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = (
    REPO_ROOT / "scripts/data/national"
    / "build_pilot_storage_study_v1.py")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_pilot_storage_study_v1", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Required before exec: the module defines a frozen dataclass.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load_module()


def _factors() -> dict[str, m.ByteFactor]:
    """Deterministic synthetic factors (ratio r, raw bytes from module)."""
    specs = {
        "l57_sr": (24.0, 1.0, "EST"),
        "l89_sr": (28.0, 1.0, "MEASURED"),
        "l_qa": (2.0, 0.5, "MEASURED"),
        "l_valid": (1.0, 0.5, "MEASURED"),
        "s2_sr": (16.0, 0.5, "MEASURED"),
        "s2_valid": (1.0, 0.5, "MEASURED"),
        "s1_vvvh": (8.0, 1.0, "MEASURED"),
    }
    return {
        k: m.ByteFactor(k, 1, raw, ratio, ratio, ratio, token)
        for k, (raw, ratio, token) in specs.items()}


def test_raw_bytes_per_pixel_band_accounting() -> None:
    # 6/7 x float32 Landsat SR; 4 x float32 S2; 2 x float32 S1; masks.
    assert m.RAW_BPP["l57_sr"] == 24.0
    assert m.RAW_BPP["l89_sr"] == 28.0
    assert m.RAW_BPP["s2_sr"] == 16.0
    assert m.RAW_BPP["s1_vvvh"] == 8.0
    assert m.RAW_BPP["l_qa"] == 2.0
    assert m.RAW_BPP["l_valid"] == m.RAW_BPP["s2_valid"] == 1.0


def test_bundle_components_match_m21b_evidence() -> None:
    assert m.BUNDLE_COMPONENTS["landsat5"] == ("l57_sr", "l_qa", "l_valid")
    assert m.BUNDLE_COMPONENTS["landsat8"] == ("l89_sr", "l_qa", "l_valid")
    assert m.BUNDLE_COMPONENTS["sentinel2"] == ("s2_sr", "s2_valid")
    assert m.BUNDLE_COMPONENTS["sentinel1"] == ("s1_vvvh",)
    assert set(m.BUNDLE_COMPONENTS) == {
        "landsat5", "landsat7", "landsat8", "landsat9",
        "sentinel1", "sentinel2"}


def test_byte_factor_variants() -> None:
    f = m.ByteFactor("s2_sr", 10, 16.0, 0.7, 0.49, 0.83, "MEASURED")
    assert f.bytes_per_pixel() == 11.2
    assert f.bytes_per_pixel("low") == 7.84
    assert f.bytes_per_pixel("high") == 13.28


def test_bundle_bytes() -> None:
    factors = _factors()
    px = 100.0
    # L8: sr 28*1.0 + qa 2*0.5 + valid 1*0.5 = 29.5 / pixel
    assert m.bundle_bytes("landsat8", px, factors) == 2950.0
    # L5: 24*1.0 + 1 + 0.5 = 25.5
    assert m.bundle_bytes("landsat5", px, factors) == 2550.0
    # S2: 16*0.5 + 1*0.5 = 8.5 ; S1: 8*1.0 = 8
    assert m.bundle_bytes("sentinel2", px, factors) == 850.0
    assert m.bundle_bytes("sentinel1", px, factors) == 800.0


def test_line_and_totals() -> None:
    factors = _factors()
    dims = pd.DataFrame({
        "cell_id": ["A", "B"], "px30": [100, 200], "px10": [900, 1800]})
    rl = m.line("sc", "x", "landsat8", "slot", "strict", "", {"A", "B"},
                dims, factors)
    assert rl["n_products"] == 2
    assert rl["n_gee_tasks"] == 6  # 2 products x 3 components
    assert rl["grid_pixels_sum"] == 300
    assert rl["bytes_base"] == round(300 * 29.5)
    rs = m.line("sc", "x", "sentinel1", "slot", "t", "ASC", {"A"},
                dims, factors)
    assert rs["n_gee_tasks"] == 1
    assert rs["grid_pixels_sum"] == 900
    tot = m.totals([rl, rs])
    assert tot["n_products"] == 3
    assert tot["n_gee_tasks"] == 7
    assert tot["bytes_base"] == rl["bytes_base"] + rs["bytes_base"]


def test_s2_sensitivity_only_moves_s2_component() -> None:
    factors = _factors()
    dims = pd.DataFrame({"cell_id": ["A"], "px30": [100], "px10": [100]})
    r = m.line("sc", "x", "sentinel2", "s", "t", "", {"A"}, dims, factors)
    # synthetic ratio equal for low/base/high (factor spread = 0)
    assert r["bytes_low"] == r["bytes_base"] == r["bytes_high"]


def test_standard_years_exclude_partial_2026() -> None:
    for years in m.STANDARD_YEARS.values():
        assert 2026 not in years
    assert m.STANDARD_YEARS["landsat5"][0] == 1984
    assert m.STANDARD_YEARS["landsat5"][-1] == 2011
    assert m.STANDARD_YEARS["sentinel1"] == list(range(2015, 2026))
    assert m.STANDARD_ADD_ON == ("landsat9",)
