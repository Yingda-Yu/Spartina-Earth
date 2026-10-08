"""Unit tests for the Issue #19 pilot panel logic (Phase A/B helpers)."""

from __future__ import annotations

import pytest

from spartina.data.national.pilot_panel import (
    ANCHOR_SLOTS,
    PROVINCE_SEGMENT,
    PanelError,
    SensorYearStatus,
    coastal_segment,
    label_agreement_category_2020,
    verify_panel,
)

CID = "CNA10K-R00236-C00083"


def test_verify_panel_accepts_keep_eligible() -> None:
    result = verify_panel(
        [CID], {CID}, {CID: "KEEP_CORE_FROZEN"}, {CID: True})
    assert result == {"ok": [CID], "rejected": []}


def test_verify_panel_rejects_unknown_nonkeep_and_ineligible() -> None:
    with pytest.raises(PanelError, match="preflight"):
        verify_panel(
            ["CNA10K-R99999-C99999", CID, "CNA10K-R00001-C00001"],
            {CID, "CNA10K-R00001-C00001"},
            {CID: "KEEP_CORE_FROZEN",
             "CNA10K-R00001-C00001": "PROVISIONAL_OFFSHORE_POLICY"},
            {CID: True, "CNA10K-R00001-C00001": False})


def test_verify_panel_rejects_duplicates_and_foreign_ids() -> None:
    with pytest.raises(PanelError, match="duplicate"):
        verify_panel([CID, CID], {CID}, {CID: "KEEP_x"}, {CID: True})
    with pytest.raises(PanelError, match="id space"):
        verify_panel(["WRONG-1"], {"WRONG-1"}, {"WRONG-1": "KEEP_x"},
                     {"WRONG-1": True})


def test_coastal_segment_deterministic() -> None:
    assert coastal_segment("Liaoning") == "BOHAI_YELLOW_SEA"
    assert coastal_segment("Guangxi") == "BEIBU_GULF"
    assert coastal_segment(None) == "UNKNOWN"
    assert coastal_segment("Sichuan") == "UNKNOWN"
    # Every mapped province resolves to a non-unknown segment.
    assert all(coastal_segment(p) != "UNKNOWN" for p in PROVINCE_SEGMENT)


@pytest.mark.parametrize(
    "g,c,m,expected",
    [(True, True, True, "ALL_THREE_PRESENT"),
     (True, False, False, "GEODATA_ONLY"),
     (False, True, True, "CMSA_CMSSM_PRESENT"),
     (True, True, False, "GEODATA_CMSA_ONLY"),
     (True, False, True, "GEODATA_CMSSM_ONLY"),
     (False, True, False, "CMSA_ONLY"),
     (False, False, True, "CMSSM_ONLY"),
     (False, False, False, "NONE_PRESENT")])
def test_label_agreement_categories(g: bool, c: bool, m: bool,
                                    expected: str) -> None:
    assert label_agreement_category_2020(g, c, m) == expected


def test_anchor_slot_invariants() -> None:
    by = {(s.sensor, s.year): s for s in ANCHOR_SLOTS}
    assert by[("landsat5", 1990)].fallback_sensors == ()
    assert by[("landsat5", 2000)].fallback_sensors == ("landsat7",)
    assert by[("sentinel2", 2020)].priority == "PRIMARY"
    assert by[("sentinel1", 2020)].per_pass is True
    assert by[("landsat8", 2020)].per_pass is False
    # S1 slots are the only per-pass slots; S2/Landsat never are.
    assert all(s.per_pass == (s.sensor == "sentinel1") for s in ANCHOR_SLOTS)


def test_sensor_year_states_are_honest_tokens() -> None:
    assert SensorYearStatus.NO_SCENE.value == "NO_SCENE"
    assert SensorYearStatus.NO_ELIGIBLE_EVENT.value == "NO_ELIGIBLE_EVENT"
    assert SensorYearStatus.SELECTED.value == "SELECTED"
