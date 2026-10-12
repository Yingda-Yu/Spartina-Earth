"""Unit tests for v0.2 frozen view contracts (Issue #21 Phase F)."""

from __future__ import annotations

import pytest

from spartina.benchmark.v02 import views
from spartina.data.gee.sentinel2 import S2_SCL_QA_POLICY_VERSION


def test_view_contract_is_self_consistent() -> None:
    doc = views.build_view_contracts("a" * 64)
    views.validate_view_contracts(doc)
    assert doc["document_checksum"]
    assert doc["views"][views.VIEW_SINGLE_EVENT]["s2_qa_policy"] == (
        S2_SCL_QA_POLICY_VERSION)
    assert S2_SCL_QA_POLICY_VERSION == "s2_scl_qa_v1_1"


def test_view_contract_binds_requirements_checksum() -> None:
    d1 = views.build_view_contracts("a" * 64)
    d2 = views.build_view_contracts("b" * 64)
    assert d1["document_checksum"] != d2["document_checksum"]


def test_view_contract_rejects_tampering() -> None:
    doc = views.build_view_contracts("a" * 64)
    doc["views"][views.VIEW_MULTI_DATE]["slot_ordering"] = ["EARLY", "LATE",
                                                            "MID"]
    with pytest.raises(ValueError, match="slot ordering"):
        views.validate_view_contracts(doc)


def test_view_contract_forbids_sensor_merge_and_harmonization() -> None:
    doc = views.build_view_contracts("a" * 64)
    multi = doc["views"][views.VIEW_MULTI_DATE]
    rule = multi["landsat_seasonal_rule"]["sensor_identity"]
    assert "never jointly medianed" in rule
    single = doc["views"][views.VIEW_SINGLE_EVENT]
    assert single["landsat_rule"]["harmonization"].startswith("NONE")
    assert multi["s1_seasonal_rule"].startswith("S1 remains paired")
