"""Live metadata-only spot-check backing the 2022 S2 funnel verdict.

Runs the deterministic 9-scene sample (3 smallest autumn scene ids per
bay, deduped). Exactly one getInfo; no pixels, no reduceRegion, no export.
The script installs the export guard internally.

Run: pytest -m gee_integration -k s2_2022 -v
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


def _load_spotcheck():
    path = (REPO_ROOT
            / "scripts/data/zhejiang/spotcheck_s2_2022_gee.py")
    spec = importlib.util.spec_from_file_location("spotcheck_s2_2022", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_s2_2022_spotcheck_metadata_matches_census() -> None:
    mod = _load_spotcheck()
    df = mod.run_spotcheck()
    assert len(df) == 9
    assert (df.status == "PASS").all()
    assert df.mgrs_match.all()
    assert df.datatake_match.all()
    assert df.date_match.all()
    assert df.cloud_match.all()
    out = REPO_ROOT / "datasets/manifests" / mod.OUTPUT_NAME
    assert out.exists()
