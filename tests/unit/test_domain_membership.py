"""Tests for the v1 mainland coastal-domain membership rule and artefacts.

The membership rule is target-independent by construction: no labels,
scene counts, model outputs, or Murray/JRC context may enter a decision.
These tests pin the closed decision vocabulary, the deterministic rule
ordering, and the consistency of the generated supersession artefacts.
"""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
from collections import Counter
from pathlib import Path

import pytest

from spartina.data.national.domain_membership import (
    CHINA_ADMIN_UNITS,
    CONTESTED_ADMIN_UNITS,
    EXCLUDE_DOMAIN_ARTIFACT,
    KEEP_ISLAND_COASTAL,
    KEEP_MAINLAND_COASTAL,
    PROVISIONAL_UNRESOLVED,
    REASON_BORDER_LANDFALL_TIE,
    REASON_CHINA_MAINLAND_LAND,
    REASON_CHINA_NEARSHORE_ISLAND,
    REASON_CHINA_SEAWARD_WATER,
    REASON_CONTESTED_ADMIN_NEARSHORE,
    REASON_CONTESTED_OUTSIDE_REACH,
    REASON_FOREIGN_LAND_ONLY,
    REASON_FOREIGN_NEARER_LANDFALL,
    REASON_MISSING_EVIDENCE,
    REASON_OPEN_WATER_OUTSIDE_REACH,
    REASON_UNADMINISTERED_LAND,
    CellMembershipEvidence,
    decide_membership,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_W10 = REPO_ROOT / "work/national/domain/cells_china_albers_W10000.csv"
CANDIDATE_CSV = REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_candidate.csv"
ARTIFACT_CSV = REPO_ROOT / "datasets/manifests/china_domain_artifact_audit_v0.csv"
SUPERSESSION_JSON = REPO_ROOT / "docs/data/national/CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json"
PILOT_JSON = REPO_ROOT / "docs/data/national/FIRST_PIXEL_PILOT_DESIGN_v0.json"

WIDTH = 10_000
CELL_AREA = float(WIDTH * WIDTH)


def _evidence(**overrides: object) -> CellMembershipEvidence:
    base: dict[str, object] = dict(
        cell_id="CNA10K-R00001-C00001",
        cell_area_m2=CELL_AREA,
        corridor_half_width_m=float(WIDTH),
        china_mainland_area_m2=0.0,
        china_island_area_m2=0.0,
        foreign_land_area_m2=0.0,
        unadministered_land_area_m2=0.0,
        contested_admin_area_m2=0.0,
        foreign_landfall_area_m2=0.0,
        dist_to_china_mainland_m=20_000.0,
        dist_to_foreign_land_m=80_000.0,
    )
    base.update(overrides)
    return CellMembershipEvidence(**base)  # type: ignore[arg-type]


# --- pure rule behaviour -------------------------------------------------


def test_decision_is_deterministic_for_same_evidence() -> None:
    ev = _evidence(china_mainland_area_m2=5e7)
    first = decide_membership(ev)
    for _ in range(5):
        assert decide_membership(_evidence(china_mainland_area_m2=5e7)) == first


def test_china_mainland_land_kept_even_when_foreign_sliver_present() -> None:
    ev = _evidence(china_mainland_area_m2=4e7, foreign_land_area_m2=2e7)
    out = decide_membership(ev)
    assert out.decision == KEEP_MAINLAND_COASTAL
    assert out.reason == REASON_CHINA_MAINLAND_LAND
    assert out.admin_class == "MIXED_CHINA_FOREIGN"


def test_foreign_land_only_cell_is_excluded() -> None:
    ev = _evidence(foreign_land_area_m2=8e7, dist_to_china_mainland_m=3_000.0)
    out = decide_membership(ev)
    assert out.decision == EXCLUDE_DOMAIN_ARTIFACT
    assert out.reason == REASON_FOREIGN_LAND_ONLY


def test_foreign_landfall_island_excluded() -> None:
    # The v0 island rule could admit a small island <=25 km from China
    # even when the foreign landfall is strictly nearer (Tumen border).
    ev = _evidence(
        foreign_landfall_area_m2=2e6,
        dist_to_china_mainland_m=20_000.0,
        dist_to_foreign_land_m=5_000.0,
    )
    out = decide_membership(ev)
    assert out.decision == EXCLUDE_DOMAIN_ARTIFACT
    assert out.reason == REASON_FOREIGN_LAND_ONLY


def test_nearshore_island_cell_kept() -> None:
    ev = _evidence(china_island_area_m2=5e6)
    out = decide_membership(ev)
    assert out.decision == KEEP_ISLAND_COASTAL
    assert out.reason == REASON_CHINA_NEARSHORE_ISLAND


def test_water_cells_follow_nearest_landfall_rule() -> None:
    kept = decide_membership(
        _evidence(dist_to_china_mainland_m=8_000.0, dist_to_foreign_land_m=40_000.0)
    )
    assert kept.decision == KEEP_MAINLAND_COASTAL
    assert kept.reason == REASON_CHINA_SEAWARD_WATER

    out_of_reach = decide_membership(
        _evidence(dist_to_china_mainland_m=12_000.0, dist_to_foreign_land_m=90_000.0)
    )
    assert out_of_reach.decision == EXCLUDE_DOMAIN_ARTIFACT
    assert out_of_reach.reason == REASON_OPEN_WATER_OUTSIDE_REACH

    foreign_nearer = decide_membership(
        _evidence(dist_to_china_mainland_m=8_000.0, dist_to_foreign_land_m=4_000.0)
    )
    assert foreign_nearer.decision == EXCLUDE_DOMAIN_ARTIFACT
    assert foreign_nearer.reason == REASON_FOREIGN_NEARER_LANDFALL

    tie = decide_membership(
        _evidence(dist_to_china_mainland_m=8_000.0, dist_to_foreign_land_m=8_300.0)
    )
    assert tie.decision == PROVISIONAL_UNRESOLVED
    assert tie.reason == REASON_BORDER_LANDFALL_TIE


def test_missing_distances_are_never_guessed() -> None:
    out = decide_membership(
        _evidence(dist_to_china_mainland_m=None, dist_to_foreign_land_m=None)
    )
    assert out.decision == PROVISIONAL_UNRESOLVED
    assert out.reason == REASON_MISSING_EVIDENCE


def test_material_unadministered_land_is_provisional() -> None:
    out = decide_membership(_evidence(unadministered_land_area_m2=2e6))
    assert out.decision == PROVISIONAL_UNRESOLVED
    assert out.reason == REASON_UNADMINISTERED_LAND
    # A sliver below 1 % of cell area does not block the water rule.
    sliver = decide_membership(
        _evidence(
            unadministered_land_area_m2=1e4,
            dist_to_china_mainland_m=8_000.0,
            dist_to_foreign_land_m=40_000.0,
        )
    )
    assert sliver.reason == REASON_CHINA_SEAWARD_WATER


def test_sar_admin_units_are_china_not_foreign() -> None:
    assert {"Hong Kong S.A.R.", "Macao S.A.R"} <= CHINA_ADMIN_UNITS
    assert CHINA_ADMIN_UNITS.isdisjoint(CONTESTED_ADMIN_UNITS)


def test_contested_land_is_provisional_within_reach_excluded_beyond() -> None:
    near = decide_membership(
        _evidence(
            contested_admin_area_m2=5e7,
            china_island_area_m2=5e5,  # islet sliver must not override
            dist_to_china_mainland_m=8_000.0,
        )
    )
    assert near.decision == PROVISIONAL_UNRESOLVED
    assert near.reason == REASON_CONTESTED_ADMIN_NEARSHORE

    far = decide_membership(
        _evidence(
            contested_admin_area_m2=5e7,
            dist_to_china_mainland_m=30_000.0,
            dist_to_foreign_land_m=200_000.0,
        )
    )
    assert far.decision == EXCLUDE_DOMAIN_ARTIFACT
    assert far.reason == REASON_CONTESTED_OUTSIDE_REACH

    # Contested sliver alongside real Chinese mainland land: keep, and
    # the decision is still mainland-based.
    mixed = decide_membership(
        _evidence(china_mainland_area_m2=4e7, contested_admin_area_m2=5e5)
    )
    assert mixed.decision == KEEP_MAINLAND_COASTAL
    assert mixed.reason == REASON_CHINA_MAINLAND_LAND


def test_rule_cannot_consume_labels_or_context() -> None:
    fields = set(CellMembershipEvidence.__dataclass_fields__)
    forbidden = {
        "label",
        "labels",
        "target",
        "targets",
        "y",
        "scene_count",
        "event_count",
        "pair_count",
        "murray",
        "jrc",
        "intertidal_fraction",
        "model_score",
        "prediction",
    }
    assert fields.isdisjoint(forbidden)
    params = set(inspect.signature(decide_membership).parameters)
    assert params == {"ev"}


def test_min_land_touch_threshold_rejects_slivers() -> None:
    ev = _evidence(
        china_mainland_area_m2=50.0,  # below 100 m^2 touch threshold
        dist_to_china_mainland_m=8_000.0,
        dist_to_foreign_land_m=40_000.0,
    )
    out = decide_membership(ev)
    assert out.decision == KEEP_MAINLAND_COASTAL
    assert out.reason == REASON_CHINA_SEAWARD_WATER


# --- generated artefact consistency --------------------------------------


@pytest.fixture(scope="module")
def registry_ids() -> set[str]:
    with REGISTRY_W10.open(newline="") as handle:
        return {row["cell_id"] for row in csv.DictReader(handle)}


@pytest.fixture(scope="module")
def candidate_rows() -> list[dict[str, str]]:
    with CANDIDATE_CSV.open(newline="") as handle:
        return list(csv.DictReader(handle))


needs_v1_artefacts = pytest.mark.skipif(
    not (CANDIDATE_CSV.exists() and SUPERSESSION_JSON.exists() and REGISTRY_W10.exists()),
    reason="v1 membership artefacts not generated",
)


@needs_v1_artefacts
def test_candidate_manifest_keeps_every_v0_cell_id(
    registry_ids: set[str], candidate_rows: list[dict[str, str]]
) -> None:
    candidate_ids = {row["cell_id"] for row in candidate_rows}
    assert candidate_ids == registry_ids  # same cell_id space, no deletions


@needs_v1_artefacts
def test_excluded_cells_remain_in_grid_registry(
    registry_ids: set[str], candidate_rows: list[dict[str, str]]
) -> None:
    excluded = {
        row["cell_id"]
        for row in candidate_rows
        if row["membership_v1_candidate"] == EXCLUDE_DOMAIN_ARTIFACT
    }
    assert excluded  # the audit must find real artifacts
    assert excluded <= registry_ids


@needs_v1_artefacts
def test_decision_tokens_and_v0_membership_closed(
    candidate_rows: list[dict[str, str]]
) -> None:
    allowed = {
        KEEP_MAINLAND_COASTAL,
        KEEP_ISLAND_COASTAL,
        EXCLUDE_DOMAIN_ARTIFACT,
        PROVISIONAL_UNRESOLVED,
    }
    assert {row["membership_v1_candidate"] for row in candidate_rows} <= allowed
    assert {row["membership_v0"] for row in candidate_rows} == {"INCLUDED"}


@needs_v1_artefacts
def test_supersession_registry_hash_and_lists_are_consistent(
    registry_ids: set[str], candidate_rows: list[dict[str, str]]
) -> None:
    payload = json.loads(SUPERSESSION_JSON.read_text())
    sha = hashlib.sha256(REGISTRY_W10.read_bytes()).hexdigest()
    assert payload["v0_registry_sha256"] == sha
    decisions = {row["cell_id"]: row["membership_v1_candidate"] for row in candidate_rows}
    for cell_id in payload["excluded_cell_ids"]:
        assert decisions[cell_id] == EXCLUDE_DOMAIN_ARTIFACT
    for cell_id in payload["provisional_cell_ids"]:
        assert decisions[cell_id] == PROVISIONAL_UNRESOLVED
    counts = payload["counts"]
    actual = Counter(decisions.values())
    assert counts["excluded_cells"] == actual[EXCLUDE_DOMAIN_ARTIFACT]
    assert counts["provisional_cells"] == actual[PROVISIONAL_UNRESOLVED]
    assert counts["v0_cells"] == len(registry_ids)


@needs_v1_artefacts
def test_all_twenty_flagged_cells_are_excluded() -> None:
    with ARTIFACT_CSV.open(newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["v0_classification"] != "INDEX_MISS"]
    assert len(rows) == 20
    assert all(r["membership_v1_candidate"] == EXCLUDE_DOMAIN_ARTIFACT for r in rows)


@needs_v1_artefacts
def test_context_columns_never_carry_labels(
    candidate_rows: list[dict[str, str]]
) -> None:
    for row in candidate_rows:
        assert "murray_intertidal_present_30km" in row  # present column
        context = row["water_context"]
        if context:
            assert "MURRAY_JRC_CONTEXT_ONLY_NEVER_A_SPARTINA_LABEL" in context


@pytest.mark.skipif(not PILOT_JSON.exists(), reason="pilot design not present")
@needs_v1_artefacts
def test_first_pixel_pilot_references_only_active_v1_cells(
    candidate_rows: list[dict[str, str]]
) -> None:
    design = json.loads(PILOT_JSON.read_text())
    decisions = {
        row["cell_id"]: row["membership_v1_candidate"] for row in candidate_rows
    }
    pilot_ids = [str(c) for c in design.get("selected_cell_ids", [])]
    if not pilot_ids and design.get("selected_cells"):
        pilot_ids = [str(c["cell_id"]) for c in design["selected_cells"]]
    assert pilot_ids, "pilot design must record selected_cell_ids"
    for cell_id in pilot_ids:
        assert decisions.get(cell_id) in {
            KEEP_MAINLAND_COASTAL,
            KEEP_ISLAND_COASTAL,
        }, f"pilot cell {cell_id} is not an active v1 coastal cell"
