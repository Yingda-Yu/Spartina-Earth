#!/usr/bin/env python3
"""Freeze W10 domain v1.1 core from the v1 candidate + owner decisions.

Issue #17 owner decision, 2026-10-08.  The deterministic v1 rule output is
immutable; this script layers the recorded human decisions from
``docs/data/owner_review/w10_owner_decision_table_v1.csv`` on top of the
v1 candidate and emits the v1.1 core-frozen membership registry:

* datasets/manifests/china_coastal_cells_v1_1_core_frozen.csv|.parquet
* docs/data/national/CHINA_DOMAIN_SUPERSESSION_v1_to_v1_1.json

Effective v1.1 statuses:

* five contested-administered Kinmen cells -> KEEP_ISLAND_COASTAL
  (operational nearshore-frame inclusion under a standing disclaimer;
  never a sovereignty / administration statement);
* five beyond-reach offshore cells -> PROVISIONAL_OFFSHORE_POLICY
  (the fixed 25 km island reach is NOT extended; they stay out of all
  production datasets and primary inference, IDs/evidence preserved for
  a later general offshore-island policy review).

No geometry is recomputed here; rule reproducibility is verified by
re-running ``audit_domain_membership_v1.py --from-cache`` and confirming
the v1 candidate checksum is unchanged.

Usage::

    PYTHONPATH=src python3 scripts/data/national/freeze_domain_membership_v1_1.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from spartina.data.national.domain_membership import (
    DECISION_TOKENS,
    EXCLUDE_DOMAIN_ARTIFACT,
    KEEP_DOMAIN_STATUSES,
    KEEP_ISLAND_COASTAL,
    KEEP_MAINLAND_COASTAL,
    PROVISIONAL_OFFSHORE_POLICY,
    PROVISIONAL_UNRESOLVED,
)
from spartina.data.national.owner_decisions import (
    CONTESTED_ADMIN_DISCLAIMER,
    CONTESTED_ADMIN_DISCLAIMER_REF,
    CORE_FREEZE_VERDICT,
    OFFSHORE_POLICY_PENDING_REVIEW,
    apply_owner_decisions,
    membership_changes,
    owner_decisions_from_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIR = REPO_ROOT / "datasets/manifests"
DOCS_NATIONAL = REPO_ROOT / "docs/data/national"
OWNER_TABLE = REPO_ROOT / "docs/data/owner_review/w10_owner_decision_table_v1.csv"
V1_CANDIDATE_CSV = MANIFEST_DIR / "china_coastal_cells_v1_candidate.csv"
V1_CANDIDATE_PARQUET = MANIFEST_DIR / "china_coastal_cells_v1_candidate.parquet"
V1_SUPERSESSION = DOCS_NATIONAL / "CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json"
OUT_CSV = MANIFEST_DIR / "china_coastal_cells_v1_1_core_frozen.csv"
OUT_PARQUET = MANIFEST_DIR / "china_coastal_cells_v1_1_core_frozen.parquet"
OUT_SUPERSESSION = DOCS_NATIONAL / "CHINA_DOMAIN_SUPERSESSION_v1_to_v1_1.json"
OWNER_DECISION_DATE = "2026-10-08"


def _git_commit() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    candidate = pd.read_csv(V1_CANDIDATE_CSV)
    decisions = owner_decisions_from_csv(str(OWNER_TABLE))
    v1_1 = apply_owner_decisions(candidate, decisions, require_complete=True)

    status_counts = v1_1["membership_v1_1"].value_counts().to_dict()
    n_mainland = int((v1_1["membership_v1_1"] == KEEP_MAINLAND_COASTAL).sum())
    n_island = int((v1_1["membership_v1_1"] == KEEP_ISLAND_COASTAL).sum())
    n_keep = int(v1_1["production_eligible"].sum())
    n_exclude = int((v1_1["membership_v1_1"] == EXCLUDE_DOMAIN_ARTIFACT).sum())
    n_offshore = int((v1_1["membership_v1_1"] == PROVISIONAL_OFFSHORE_POLICY).sum())
    n_unresolved = int((v1_1["membership_v1_1"] == PROVISIONAL_UNRESOLVED).sum())
    expected = {
        KEEP_MAINLAND_COASTAL: 2752,
        KEEP_ISLAND_COASTAL: 264,
        EXCLUDE_DOMAIN_ARTIFACT: 298,
        PROVISIONAL_OFFSHORE_POLICY: 5,
        PROVISIONAL_UNRESOLVED: 0,
    }
    if {k: status_counts.get(k, 0) for k in expected} != expected:
        raise AssertionError(
            f"v1.1 counts {status_counts} do not match owner decision " f"expectation {expected}"
        )

    changed = membership_changes(v1_1)
    if len(changed) != 10:
        raise AssertionError(f"expected exactly 10 membership changes, got {len(changed)}")
    kept_promotions = changed.loc[
        changed["membership_v1_1"] == KEEP_ISLAND_COASTAL, "cell_id"
    ].tolist()
    offshore_ids = changed.loc[
        changed["membership_v1_1"] == PROVISIONAL_OFFSHORE_POLICY, "cell_id"
    ].tolist()
    if len(kept_promotions) != 5 or len(offshore_ids) != 5:
        raise AssertionError("expected 5 KEEP promotions and 5 offshore cells")

    # Evidence preservation: the v1 rule columns are carried byte-for-byte.
    v1_cols = list(candidate.columns)
    preserved = candidate[v1_cols].equals(v1_1[v1_cols])
    if not preserved:
        raise AssertionError("v1 candidate evidence columns were modified")

    ordered_cols = v1_cols + [
        "owner_decision",
        "membership_v1_1",
        "v1_1_basis",
        "disclaimer_ref",
        "production_eligible",
    ]
    v1_1 = v1_1[ordered_cols]
    v1_1.to_csv(OUT_CSV, index=False)
    v1_1.to_parquet(OUT_PARQUET, index=False)

    v1_meta = json.loads(V1_SUPERSESSION.read_text())
    pinned_v1_sha = v1_meta["v1_candidate_csv_sha256"]
    actual_v1_sha = _sha256(V1_CANDIDATE_CSV)
    if pinned_v1_sha != actual_v1_sha:
        raise AssertionError(
            "v1 candidate CSV checksum does not match the value pinned in "
            f"{V1_SUPERSESSION.name}: {actual_v1_sha} != {pinned_v1_sha}"
        )

    decision_rows = []
    for cell_id, token in sorted(decisions.items()):
        row = changed.loc[changed["cell_id"] == cell_id].iloc[0]
        decision_rows.append(
            {
                "cell_id": cell_id,
                "v1_candidate_status": PROVISIONAL_UNRESOLVED,
                "v1_rule_reason": row["membership_reason"],
                "owner_decision": token,
                "membership_v1_1": row["membership_v1_1"],
                "disclaimer_ref": (
                    CONTESTED_ADMIN_DISCLAIMER_REF
                    if row["membership_v1_1"] == KEEP_ISLAND_COASTAL
                    else ""
                ),
            }
        )

    payload: dict[str, Any] = {
        "artifact": "china_mainland_coastal_domain_membership",
        "supersedes": "china_mainland_coastal_domain_membership_v1_candidate",
        "from_version": "v1_candidate",
        "to_version": "v1_1_core_frozen",
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "freeze_verdict": CORE_FREEZE_VERDICT,
        "freeze_scope": (
            "The KEEP core (3,016 W10 cells: 2,752 mainland coastal + "
            "264 island coastal, including five operationally included "
            "Kinmen cells) is frozen for production use. Five beyond-reach "
            "offshore cells remain outside the frozen core as "
            "PROVISIONAL_OFFSHORE_POLICY. This freeze does not resolve "
            "every spatial-policy question; the general offshore-island "
            "policy is a separate later decision."
        ),
        "grid_policy": v1_meta["grid_policy"],
        "decision_vocabulary": list(DECISION_TOKENS),
        "rule_layer": {
            "rule": "unchanged deterministic v1 rule "
            "(audit_domain_membership_v1.py); no rule parameter "
            "was modified by the owner decision",
            "rule_parameters": v1_meta["rule_parameters"],
            "v1_rule_reproduction": {
                "method": (
                    "re-run audit_domain_membership_v1.py --from-cache; "
                    "v1 candidate CSV SHA-256 matches the value pinned in "
                    "CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json"
                ),
                "v1_candidate_csv_sha256": actual_v1_sha,
                "rule_counts": v1_meta["counts"]["decision_counts"],
            },
        },
        "owner_decision_layer": {
            "decision_date": OWNER_DECISION_DATE,
            "source": "docs/data/owner_review/w10_owner_decision_table_v1.csv",
            "source_csv_sha256": _sha256(OWNER_TABLE),
            "issue": "Issue #17",
            "decisions": decision_rows,
            "contested_admin_disclaimer_ref": CONTESTED_ADMIN_DISCLAIMER_REF,
            "contested_admin_disclaimer": CONTESTED_ADMIN_DISCLAIMER,
            "disclaimer_scope": (
                "Applies to the five Kinmen cells whose owner decision is "
                "KEEP_ISLAND_COASTAL; their contested-admin evidence "
                "remains verbatim in membership_evidence / membership_reason."
            ),
            "offshore_reach_policy": {
                "island_near_m_unchanged": 25_000,
                "reach_extended": False,
                "policy": (
                    "The existing 25 km offshore-island reach is not "
                    "extended and no ad-hoc cell-specific exception is "
                    "created. Wanshan, Dachen (x2), Dongji and Juguang "
                    "cells remain provisional until a separate, general, "
                    "target-independent offshore-island policy is "
                    "established with authoritative island / "
                    "administration evidence."
                ),
                "review_window": OFFSHORE_POLICY_PENDING_REVIEW,
            },
        },
        "target_independence": v1_meta["target_independence"]
        + " The v1.1 layer contains owner spatial-policy decisions only; "
        "it still contains no labels, scene counts or model outputs.",
        "counts": {
            "total_cells": 3319,
            "kept_cells": n_keep,
            "kept_mainland_cells": n_mainland,
            "kept_island_cells": n_island,
            "excluded_cells": n_exclude,
            "provisional_cells": n_offshore + n_unresolved,
            "provisional_offshore_policy_cells": n_offshore,
            "provisional_unresolved_cells": n_unresolved,
            "decision_counts": expected,
            "kept_cell_union_area_km2": 301600.0,
            "excluded_cell_union_area_km2": 29800.0,
            "provisional_cell_union_area_km2": 500.0,
        },
        "membership_changes": [
            {
                "cell_id": r["cell_id"],
                "from": r["membership_v1_candidate"],
                "to": r["membership_v1_1"],
                "rule_reason": r["membership_reason"],
                "owner_decision": r["owner_decision"],
            }
            for r in changed.to_dict(orient="records")
        ],
        "provisional_offshore_policy_cell_ids": offshore_ids,
        "production_eligibility": {
            "eligible_statuses": sorted(KEEP_DOMAIN_STATUSES),
            "eligible_cells": n_keep,
            "excluded_statuses": [
                EXCLUDE_DOMAIN_ARTIFACT,
                PROVISIONAL_UNRESOLVED,
                PROVISIONAL_OFFSHORE_POLICY,
            ],
            "rule": (
                "KEEP cells may be used downstream. "
                "PROVISIONAL_OFFSHORE_POLICY cells must be excluded from "
                "production datasets and primary inference; their cell IDs "
                "and full GIS evidence are preserved in this registry for "
                "the v1.1 offshore-policy review."
            ),
        },
        "evidence_preservation": {
            "candidate_columns_carried_unchanged": v1_cols,
            "contested_admin_evidence": (
                "membership_evidence JSON (contested_admin_area_frac, "
                "dist_to_china_mainland_m, admin names) and "
                "membership_reason=CONTESTED_ADMIN_NEARSHORE are retained "
                "for all five Kinmen cells."
            ),
        },
        "checksums": {
            "v0_registry_sha256": v1_meta["v0_registry_sha256"],
            "v1_candidate_csv_sha256": actual_v1_sha,
            "v1_candidate_parquet_sha256": _sha256(V1_CANDIDATE_PARQUET),
            "owner_decision_table_csv_sha256": _sha256(OWNER_TABLE),
            "v1_1_core_frozen_csv_sha256": _sha256(OUT_CSV),
            "v1_1_core_frozen_parquet_sha256": _sha256(OUT_PARQUET),
        },
    }
    OUT_SUPERSESSION.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    print(f"wrote {OUT_CSV}")
    print(f"wrote {OUT_PARQUET}")
    print(f"wrote {OUT_SUPERSESSION}")
    print(
        "counts: "
        f"KEEP={n_keep} (mainland {n_mainland} + island {n_island}), "
        f"EXCLUDE={n_exclude}, "
        f"PROVISIONAL_OFFSHORE_POLICY={n_offshore}, "
        f"PROVISIONAL_UNRESOLVED={n_unresolved}"
    )
    print("promoted to KEEP:", kept_promotions)
    print("remaining provisional:", offshore_ids)


if __name__ == "__main__":
    main()
