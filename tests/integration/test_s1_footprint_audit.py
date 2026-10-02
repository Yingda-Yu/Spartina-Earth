"""Live geometry-only Sentinel-1 footprint audit (M2.1a2-R1 blocker #3).

One getInfo on a deterministic <=60-scene IW sample; reads only per-scene
footprint geometry, never pixels. The script installs the export guard.

Run: pytest -m gee_integration -k s1_footprint -v
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from spartina.data.gee import auth

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.gee_integration,
    pytest.mark.skipif(not auth.credentials_available(),
                       reason="GEE credentials not configured."),
    pytest.mark.skipif(not auth.configured_project(),
                       reason="SPARTINA_GEE_PROJECT is unset."),
]


def _load_audit():
    path = REPO_ROOT / "scripts/data/zhejiang/audit_s1_footprints.py"
    spec = importlib.util.spec_from_file_location("audit_s1_footprints",
                                                  path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_s1_footprint_audit_deterministic_sample_and_outputs() -> None:
    mod = _load_audit()
    df = mod.run_audit()
    n_scenes = df.scene_id.nunique()
    assert mod.MIN_SCENES <= n_scenes <= mod.MAX_SCENES
    assert set(df.bay_id.unique()) == {"ZJ-HZB", "ZJ-SMB", "ZJ-YQB"}
    assert df.orbit_direction.nunique() == 2
    assert df.relative_orbit_number.nunique() >= 4
    assert df.year.nunique() >= 5
    assert df["actual_geometry_present"].all()
    summary = mod._summary(df)
    assert len(summary)
    policy = mod.write_policy(df, summary)
    assert policy["marker"] == (
        "S1_REPRESENTATIVE_FOOTPRINT_NOT_PRODUCTION_GEOMETRY")
    assert policy["overall"]["coverage_max_abs_error"] >= 0.0
