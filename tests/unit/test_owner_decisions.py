"""Tests for the Issue #17 owner-decision layer and v1.1 core freeze.

The deterministic v1 rule is never modified by an owner decision: these
tests pin that the rule output is carried unchanged, that the five
contested-administered Kinmen cells enter the KEEP core only under the
standing disclaimer, that beyond-reach offshore cells become
PROVISIONAL_OFFSHORE_POLICY (never ad-hoc KEEP), and that the committed
v1.1 freeze artefacts are internally consistent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from spartina.data.national.domain_membership import (
    DECISION_TOKENS,
    EXCLUDE_DOMAIN_ARTIFACT,
    KEEP_ISLAND_COASTAL,
    KEEP_MAINLAND_COASTAL,
    PROVISIONAL_OFFSHORE_POLICY,
    PROVISIONAL_UNRESOLVED,
    REASON_CONTESTED_ADMIN_NEARSHORE,
    REASON_UNADMINISTERED_LAND,
    CellMembershipEvidence,
    decide_membership,
    is_production_kept,
    is_provisional,
)
from spartina.data.national.owner_decisions import (
    CONTESTED_ADMIN_DISCLAIMER,
    CONTESTED_ADMIN_DISCLAIMER_REF,
    CORE_FREEZE_VERDICT,
    OWNER_DECISION_KEEP,
    OWNER_DECISION_REMAIN_PROVISIONAL,
    apply_owner_decisions,
    membership_changes,
    owner_decisions_from_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_CSV = REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_candidate.csv"
V1_1_CSV = REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_1_core_frozen.csv"
V1_1_PARQUET = REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_1_core_frozen.parquet"
V1_SUPERSESSION = REPO_ROOT / "docs/data/national/CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json"
V1_1_SUPERSESSION = REPO_ROOT / "docs/data/national/CHINA_DOMAIN_SUPERSESSION_v1_to_v1_1.json"
OWNER_TABLE = REPO_ROOT / "docs/data/owner_review/w10_owner_decision_table_v1.csv"

KINMEN = [
    "CNA10K-R00263-C00134",
    "CNA10K-R00264-C00134",
    "CNA10K-R00264-C00135",
    "CNA10K-R00264-C00136",
    "CNA10K-R00265-C00136",
]
OFFSHORE = [
    "CNA10K-R00231-C00093",
    "CNA10K-R00283-C00149",
    "CNA10K-R00314-C00162",
    "CNA10K-R00314-C00163",
    "CNA10K-R00316-C00163",
]


def _candidate_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cell_id": "CNA10K-R00001-C00001",
                "membership_v1_candidate": KEEP_MAINLAND_COASTAL,
                "membership_reason": "CHINA_MAINLAND_LAND",
                "membership_evidence": '{"contested_admin_area_frac": 0.0}',
            },
            {
                "cell_id": KINMEN[0],
                "membership_v1_candidate": PROVISIONAL_UNRESOLVED,
                "membership_reason": REASON_CONTESTED_ADMIN_NEARSHORE,
                "membership_evidence": '{"contested_admin_area_frac": 0.0986}',
            },
            {
                "cell_id": OFFSHORE[0],
                "membership_v1_candidate": PROVISIONAL_UNRESOLVED,
                "membership_reason": REASON_UNADMINISTERED_LAND,
                "membership_evidence": '{"dist_to_china_mainland_m": 27600.0}',
            },
        ]
    )


def test_status_vocabulary_and_eligibility_helpers() -> None:
    assert PROVISIONAL_OFFSHORE_POLICY in DECISION_TOKENS
    assert is_production_kept(KEEP_MAINLAND_COASTAL)
    assert is_production_kept(KEEP_ISLAND_COASTAL)
    assert not is_production_kept(PROVISIONAL_UNRESOLVED)
    assert not is_production_kept(PROVISIONAL_OFFSHORE_POLICY)
    assert not is_production_kept(EXCLUDE_DOMAIN_ARTIFACT)
    assert is_provisional(PROVISIONAL_UNRESOLVED)
    assert is_provisional(PROVISIONAL_OFFSHORE_POLICY)
    assert not is_provisional(KEEP_ISLAND_COASTAL)


def test_deterministic_rule_never_emits_offshore_policy_token() -> None:
    """decide_membership must stay pure; the owner layer owns v1.1 tokens."""
    ev = CellMembershipEvidence(
        cell_id="x",
        cell_area_m2=1.0e8,
        corridor_half_width_m=10_000.0,
        china_mainland_area_m2=0.0,
        china_island_area_m2=0.0,
        foreign_land_area_m2=0.0,
        unadministered_land_area_m2=0.0,
        dist_to_china_mainland_m=1_000.0,
        dist_to_foreign_land_m=100_000.0,
        contested_admin_area_m2=500.0,
    )
    decision = decide_membership(ev)
    assert decision.decision == PROVISIONAL_UNRESOLVED


def test_apply_owner_decisions_keeps_contested_with_disclaimer() -> None:
    decisions = {
        KINMEN[0]: OWNER_DECISION_KEEP,
        OFFSHORE[0]: OWNER_DECISION_REMAIN_PROVISIONAL,
    }
    out = apply_owner_decisions(_candidate_frame(), decisions)
    by_id = out.set_index("cell_id")

    kept = by_id.loc[KINMEN[0]]
    assert kept["membership_v1_1"] == KEEP_ISLAND_COASTAL
    assert kept["owner_decision"] == OWNER_DECISION_KEEP
    assert kept["v1_1_basis"] == "OWNER_DECISION_2026-10-08"
    assert kept["disclaimer_ref"] == CONTESTED_ADMIN_DISCLAIMER_REF
    assert bool(kept["production_eligible"]) is True
    # contested evidence is preserved, not erased
    assert kept["membership_reason"] == REASON_CONTESTED_ADMIN_NEARSHORE
    assert "0.0986" in kept["membership_evidence"]

    offshore = by_id.loc[OFFSHORE[0]]
    assert offshore["membership_v1_1"] == PROVISIONAL_OFFSHORE_POLICY
    assert offshore["owner_decision"] == OWNER_DECISION_REMAIN_PROVISIONAL
    assert offshore["disclaimer_ref"] == ""
    assert bool(offshore["production_eligible"]) is False

    rule_cell = by_id.loc["CNA10K-R00001-C00001"]
    assert rule_cell["membership_v1_1"] == KEEP_MAINLAND_COASTAL
    assert rule_cell["owner_decision"] == ""
    assert rule_cell["v1_1_basis"] == "DETERMINISTIC_RULE_V1"

    changes = membership_changes(out)
    assert set(changes["cell_id"]) == {KINMEN[0], OFFSHORE[0]}


def test_keep_decision_rejected_for_beyond_reach_unadministered_cell() -> None:
    """The 25 km reach must not be extended by an ad-hoc exception."""
    with pytest.raises(ValueError, match="25 km"):
        apply_owner_decisions(
            _candidate_frame(),
            {OFFSHORE[0]: OWNER_DECISION_KEEP},
            require_complete=False,
        )


def test_incomplete_or_extra_decisions_are_rejected() -> None:
    frame = _candidate_frame()
    with pytest.raises(ValueError, match="without decision"):
        apply_owner_decisions(frame, {KINMEN[0]: OWNER_DECISION_KEEP})
    with pytest.raises(ValueError, match="non-provisional"):
        apply_owner_decisions(
            frame,
            {
                KINMEN[0]: OWNER_DECISION_KEEP,
                OFFSHORE[0]: OWNER_DECISION_REMAIN_PROVISIONAL,
                "CNA10K-R00001-C00001": OWNER_DECISION_KEEP,
            },
        )


def test_owner_table_is_complete_and_split_five_five() -> None:
    decisions = owner_decisions_from_csv(str(OWNER_TABLE))
    assert set(decisions) == set(KINMEN) | set(OFFSHORE)
    assert [decisions[c] for c in KINMEN] == [OWNER_DECISION_KEEP] * 5
    assert [decisions[c] for c in OFFSHORE] == ([OWNER_DECISION_REMAIN_PROVISIONAL] * 5)


@pytest.mark.skipif(not V1_1_CSV.exists(), reason="v1.1 freeze not yet built")
def test_committed_v1_1_freeze_registry() -> None:
    candidate = pd.read_csv(CANDIDATE_CSV, keep_default_na=False)
    frozen = pd.read_csv(V1_1_CSV, keep_default_na=False)
    assert len(frozen) == len(candidate) == 3319

    counts = frozen["membership_v1_1"].value_counts().to_dict()
    assert counts == {
        KEEP_MAINLAND_COASTAL: 2752,
        KEEP_ISLAND_COASTAL: 264,
        EXCLUDE_DOMAIN_ARTIFACT: 298,
        PROVISIONAL_OFFSHORE_POLICY: 5,
    }
    assert int(frozen["production_eligible"].sum()) == 3016

    # rule evidence carried byte-for-byte
    v1_cols = list(candidate.columns)
    merged = frozen[v1_cols].reset_index(drop=True).sort_values("cell_id")
    original = candidate[v1_cols].reset_index(drop=True).sort_values("cell_id")
    pd.testing.assert_frame_equal(
        merged.reset_index(drop=True), original.reset_index(drop=True), check_like=True
    )

    kept = frozen.loc[
        frozen["cell_id"].isin(KINMEN),
        ["cell_id", "membership_v1_1", "disclaimer_ref", "production_eligible"],
    ]
    assert set(kept["membership_v1_1"]) == {KEEP_ISLAND_COASTAL}
    assert set(kept["disclaimer_ref"]) == {CONTESTED_ADMIN_DISCLAIMER_REF}
    assert bool(kept["production_eligible"].all())

    prov = frozen.loc[frozen["cell_id"].isin(OFFSHORE)]
    assert set(prov["membership_v1_1"]) == {PROVISIONAL_OFFSHORE_POLICY}
    assert not bool(prov["production_eligible"].any())

    # CSV and parquet carry identical membership assignments
    parquet = pd.read_parquet(V1_1_PARQUET)
    csv_view = frozen.sort_values("cell_id").reset_index(drop=True)
    pq_view = parquet.sort_values("cell_id").reset_index(drop=True)[csv_view.columns]
    # empty CSV cells (utm_zone / owner_decision / ...) round-trip as
    # NaN in parquet; normalise before comparing content
    pq_view = pq_view.fillna("")
    csv_view = csv_view.fillna("")
    pd.testing.assert_frame_equal(csv_view, pq_view, check_dtype=False)


@pytest.mark.skipif(not V1_1_SUPERSESSION.exists(), reason="v1.1 freeze JSON not yet built")
def test_committed_v1_1_supersession_json() -> None:
    payload = json.loads(V1_1_SUPERSESSION.read_text())
    assert payload["freeze_verdict"] == CORE_FREEZE_VERDICT
    assert payload["to_version"] == "v1_1_core_frozen"

    counts = payload["counts"]
    assert counts["kept_cells"] == 3016
    assert counts["kept_mainland_cells"] == 2752
    assert counts["kept_island_cells"] == 264
    assert counts["excluded_cells"] == 298
    assert counts["provisional_cells"] == 5
    assert counts["provisional_offshore_policy_cells"] == 5
    assert counts["provisional_unresolved_cells"] == 0

    layer = payload["owner_decision_layer"]
    assert layer["contested_admin_disclaimer"] == CONTESTED_ADMIN_DISCLAIMER
    assert CONTESTED_ADMIN_DISCLAIMER.startswith(
        "Inclusion of cells intersecting contested-administered islands"
    )
    assert layer["offshore_reach_policy"]["reach_extended"] is False
    assert layer["offshore_reach_policy"]["island_near_m_unchanged"] == 25_000
    assert payload["provisional_offshore_policy_cell_ids"] == sorted(OFFSHORE)

    changes = {c["cell_id"]: c for c in payload["membership_changes"]}
    assert set(changes) == set(KINMEN) | set(OFFSHORE)
    for cell_id in KINMEN:
        assert changes[cell_id]["to"] == KEEP_ISLAND_COASTAL
    for cell_id in OFFSHORE:
        assert changes[cell_id]["to"] == PROVISIONAL_OFFSHORE_POLICY

    # rule layer still reproduces the original 3,011/298/10 candidate
    assert (
        payload["rule_layer"]["v1_rule_reproduction"]["v1_candidate_csv_sha256"]
        == hashlib.sha256(CANDIDATE_CSV.read_bytes()).hexdigest()
    )

    # every checksum field matches the file it names
    for name, rel in (
        ("v1_1_core_frozen_csv_sha256", V1_1_CSV),
        ("v1_1_core_frozen_parquet_sha256", V1_1_PARQUET),
        ("owner_decision_table_csv_sha256", OWNER_TABLE),
    ):
        assert payload["checksums"][name] == (hashlib.sha256(rel.read_bytes()).hexdigest())

    eligibility = payload["production_eligibility"]
    assert eligibility["eligible_cells"] == 3016
    assert PROVISIONAL_OFFSHORE_POLICY in eligibility["excluded_statuses"]
