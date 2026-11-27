"""Unit tests for the Issue #19 F3 S1 extreme-floor evidence audit."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import rasterio

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = (
    REPO_ROOT / "scripts/data/national"
    / "pilot19_s1_floor_audit.py")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "pilot19_s1_floor_audit", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


a = _load_module()


def test_band_record_stats_and_floor_counts() -> None:
    arr = np.full((4, 4), -12.5, dtype="float64")
    arr[0, 0] = -80.031       # discrete floor pixel
    arr[1, 1] = -71.0         # at-or-below -70
    arr[2, 2] = -67.98        # above the threshold, must stay observed
    arr[3, 3] = np.nan
    rec = a._band_record("VV", arr)
    assert rec["band"] == "VV"
    assert rec["finite_fraction"] == 0.9375
    assert rec["min_db"] == -80.031
    assert rec["p50_db"] == -12.5
    assert rec["n_at_or_below_floor"] == 2
    low_values = {d["value_db"] for d in
                  rec["discrete_values_at_or_below_minus65_db"]}
    assert -80.031 in low_values and -71.0 in low_values
    assert -67.98 in low_values  # listed below -65 but NOT floor-masked


def test_edge_localization_places_floor_on_observed_boundary() -> None:
    observed = np.zeros((20, 20), dtype=bool)
    observed[4:16, 4:16] = True
    floor = np.zeros_like(observed)
    floor[4, 8] = True   # first observed row == edge pixel (10 m grid)
    loc = a._edge_localization(observed, floor, 10.0)
    assert loc["n_floor_pixels"] == 1
    assert loc["touching_nonobserved_2px_fraction"] == 1.0
    assert loc["distance_to_nonobserved_edge_m"]["max"] == 10.0
    assert loc["beyond_interior_margins_m"]["50"]["pixels"] == 0
    assert loc["beyond_interior_margins_m"]["1000"]["pixels"] == 0


def test_edge_localization_flags_deep_interior_floor() -> None:
    observed = np.ones((300, 300), dtype=bool)  # full 3 km window
    floor = np.zeros_like(observed)
    floor[150, 150] = True  # >1 km from every edge
    loc = a._edge_localization(observed, floor, 10.0)
    assert loc["beyond_interior_margins_m"]["50"]["pixels"] == 1
    assert loc["beyond_interior_margins_m"]["1000"]["pixels"] == 1
    assert loc["touching_nonobserved_2px_fraction"] == 0.0


def _record(product_id: str, evidence_class: str, observed_frac: float,
            deep50_pixels: int, interior_frac: float) -> dict:
    return {
        "product_id": product_id,
        "evidence_class": evidence_class,
        "dualpol_observed_fraction": observed_frac,
        "floor_edge_localization": {
            "beyond_interior_margins_m": {
                "50": {"pixels": deep50_pixels,
                       "fraction_of_floor": 0.0,
                       "fraction_of_observed_interior": interior_frac}}}}


def test_policy_confirmed_for_edge_only_floor() -> None:
    records = [
        _record("P_NORMAL", "LANDED", 1.0, 0, 0.0),
        _record("P_PARTIAL", "QUARANTINED_UNLANDED", 0.31, 0, 0.0),
    ]
    decision = a._policy_decision(records)
    assert decision["verdict"] == "POLICY_CONFIRMED_S1_DUALPOL_VALID_V2"
    assert decision["violations"] == []


def test_policy_stops_when_interior_removed_from_full_product() -> None:
    records = [_record("P_BAD", "LANDED", 0.99, 7, 5e-5)]
    decision = a._policy_decision(records)
    assert decision["verdict"] == "STOP_OWNER_REVIEW"
    assert any("P_BAD" in v for v in decision["violations"])


def test_audit_raster_applies_dualpol_floor_mask(tmp_path) -> None:  # type: ignore[no-untyped-def]
    H = W = 40
    vv = np.full((H, W), -10.0, dtype="float32")
    vh = np.full((H, W), -18.0, dtype="float32")
    vv[:5, :] = np.nan          # frame-edge nonobservation band mask
    vh[:5, :] = np.nan
    vv[10, 10] = -80.031        # interior discrete floor -> must be masked
    vh[10, 10] = -80.031
    path = tmp_path / "s1.tif"
    transform = rasterio.transform.from_origin(0.0, 400.0, 10.0, 10.0)
    with rasterio.open(
        path, "w", driver="GTiff", height=H, width=W, count=2,
        dtype="float32", crs="EPSG:32650", transform=transform,
    ) as ds:
        ds.write(vv, 1)
        ds.write(vh, 2)
    rec = a.audit_raster(path)
    assert rec["dualpol_observed_fraction"] == 0.875
    assert rec["floor_masked_pixels"] == 1
    assert rec["s1_dualpol_valid_v2_fraction_of_grid"] == 0.875 - 1 / (H * W)
