"""The committed M2.1a config must remain internally consistent."""

from __future__ import annotations

from pathlib import Path

import yaml

from spartina.data.gee.sentinel2 import S2_SCL_QA_POLICY_VERSION
from spartina.data.zhejiang.contracts import BAY_IDS, SENSORS

CONFIG = (Path(__file__).resolve().parents[2]
          / "configs/data/zhejiang_multibay_m21a.yaml")


def test_config_core_domains():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert int(cfg["time_axis"]["start_year"]) == 1985
    assert int(cfg["time_axis"]["end_year"]) == 2026
    ids = [b["roi_id"] for b in cfg["rois"]]
    assert ids == list(BAY_IDS)
    assert list(cfg["sensors"]) == list(SENSORS)
    for sensor in SENSORS:
        sec = cfg["sensors"][sensor]
        span = sec["operational_years"]
        assert len(span) == 2 and span[0] <= span[1]
        assert str(sec["gee_collection"]).startswith(("LANDSAT/",
                                                      "COPERNICUS/"))
    assert cfg["census"]["default_stage"] == "SCENE_METADATA"
    assert cfg["census"]["export_guard"] is True


def test_season_windows_are_marked_proposed_not_frozen():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    ids = []
    for w in cfg["season_windows"]:
        ids.append(w["id"])
        assert w["policy_status"] == "PROPOSED_NOT_FROZEN"
        assert 1 <= w["doy_start"] < w["doy_end"] <= 366
    assert "autumn_v0" in ids and "summer_v0" in ids


def test_s2_policy_pin_matches_factory():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert (cfg["sensors"]["sentinel2"]["scl_qa_policy"]
            == S2_SCL_QA_POLICY_VERSION == "s2_scl_qa_v1_1")


def test_sources_have_evidence_status_and_real_urls():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    ids = set()
    for src in cfg["sources"]:
        ids.add(src["id"])
        assert src["status"] in {"VERIFIED", "OBSERVED", "PROVISIONAL",
                                 "UNVERIFIED", "UNKNOWN", "CONTRADICTED",
                                 "MISSING"}
        assert str(src.get("url", ""))  # explicit URL, UNKNOWN, or N/A only
    assert len(ids) == len(cfg["sources"])
