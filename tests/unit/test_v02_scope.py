"""Unit tests for v0.2 Phase H scope accounting."""

from __future__ import annotations

from spartina.benchmark.v02 import scope


def test_scope_within_cap() -> None:
    table = {"s2_event": 18_000_000, "s1_pair": 12_100_000,
             "landsat_observation": 4_700_000}
    out = scope.estimate_scope(
        n_cells=53, s2_events=240, s1_pairs=220,
        landsat_observations=130, size_table=table,
        byte_quantile="p90")
    assert out["verdict"] == scope.VERDICT_PROCEED
    assert out["component_tasks_by_sensor"] == {
        "sentinel2": 480, "sentinel1": 220, "landsat": 390}
    assert out["projected_gee_component_tasks"] == 1090
    assert out["cap_breaches"] == {}


def test_scope_cells_breach_is_stop() -> None:
    table = {"s2_event": 1, "s1_pair": 1, "landsat_observation": 1}
    out = scope.estimate_scope(
        n_cells=97, s2_events=1, s1_pairs=0,
        landsat_observations=0, size_table=table, byte_quantile="p90")
    assert out["verdict"] == scope.VERDICT_STOP
    assert "new_cells" in out["cap_breaches"]


def test_scope_tasks_breach_is_stop() -> None:
    table = {"s2_event": 1, "s1_pair": 1, "landsat_observation": 1}
    out = scope.estimate_scope(
        n_cells=1, s2_events=5_001, s1_pairs=0,
        landsat_observations=0, size_table=table, byte_quantile="p90")
    assert out["verdict"] == scope.VERDICT_STOP
    assert out["cap_breaches"]["gee_component_tasks"]["cap"] == 10_000


def test_scope_bytes_breach_is_stop() -> None:
    big = {"s2_event": 10 * 1024**3, "s1_pair": 0,
           "landsat_observation": 0}
    out = scope.estimate_scope(
        n_cells=1, s2_events=5, s1_pairs=0,
        landsat_observations=0, size_table=big, byte_quantile="p90")
    assert out["verdict"] == scope.VERDICT_STOP
    assert "landed_eo_bytes" in out["cap_breaches"]
