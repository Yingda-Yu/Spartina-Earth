"""Documented owner-decision layer over the deterministic v1 candidate.

The deterministic v1 rule in :mod:`spartina.data.national.domain_membership`
is target-independent and reproducible; it cannot, and must not, settle a
programme-level spatial-policy question.  Issue #17 left ten W10 cells at
``PROVISIONAL_UNRESOLVED`` and routed them to human review.  On
2026-10-08 the programme owner recorded binding decisions in
``docs/data/owner_review/w10_owner_decision_table_v1.csv``:

* five contested-administered Kinmen cells (0.9-8.9 km from the Fujian
  mainland) are kept operationally as ``KEEP_ISLAND_COASTAL`` because
  they are part of the mainland-Fujian nearshore observation frame;
* five cells beyond the fixed 25 km offshore-island reach
  (Wanshan / Dachen / Dongji / Juguang settings) remain provisional,
  reclassified ``PROVISIONAL_OFFSHORE_POLICY`` pending a separate,
  general, target-independent offshore-island policy supported by
  authoritative island / administration evidence.

This module only validates and applies those *recorded* decisions; it
contains no geometry, no labels, and no way to invent an ad-hoc
exception.  The deterministic rule output (the v1 candidate) is never
mutated -- every row keeps its ``membership_v1_candidate`` value and its
full evidence JSON, and the effective v1.1 status is written beside it.

Production eligibility is defined once, here:

* ``KEEP_MAINLAND_COASTAL`` / ``KEEP_ISLAND_COASTAL`` -> eligible;
* every provisional status (unresolved or offshore-policy) -> excluded
  from production datasets and primary inference.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import pandas as pd

from spartina.data.national.domain_membership import (
    KEEP_ISLAND_COASTAL,
    PROVISIONAL_OFFSHORE_POLICY,
    PROVISIONAL_UNRESOLVED,
    REASON_CONTESTED_ADMIN_NEARSHORE,
    REASON_UNADMINISTERED_LAND,
    is_production_kept,
)

# --- owner-recorded decision tokens (owner table vocabulary) -------------

OWNER_DECISION_KEEP: Final[str] = KEEP_ISLAND_COASTAL
"""Owner keeps the cell in the operational nearshore frame."""

OWNER_DECISION_REMAIN_PROVISIONAL: Final[str] = "REMAIN_PROVISIONAL"
"""Owner leaves the cell out of production pending a general policy."""

OWNER_DECISION_TOKENS: Final[frozenset[str]] = frozenset(
    {OWNER_DECISION_KEEP, OWNER_DECISION_REMAIN_PROVISIONAL}
)

# --- standing policy record (Issue #17, owner mandate A) -----------------

CONTESTED_ADMIN_DISCLAIMER_REF: Final[str] = "CONTESTED_ADMIN_OPERATIONAL_INCLUSION_DISCLAIMER_V1"

CONTESTED_ADMIN_DISCLAIMER: Final[str] = (
    "Inclusion of cells intersecting contested-administered islands is an "
    "operational spatial-domain decision based on proximity to the mainland "
    "coast and does not constitute a statement on sovereignty or "
    "administrative status."
)
"""Verbatim standing disclaimer.  Applies to the five Kinmen cells kept by
the 2026-10-08 owner decision; their contested-admin evidence remains in
the v1 candidate evidence columns and must never be erased."""

CORE_FREEZE_VERDICT: Final[str] = "W10_DOMAIN_V1_CORE_FROZEN"
"""Freeze verdict: the 3,016-cell KEEP core is frozen; five cells remain
versioned PROVISIONAL_OFFSHORE_POLICY outside the frozen core."""

OFFSHORE_POLICY_PENDING_REVIEW: Final[str] = "v1.1"
"""Intended review window for the offshore-policy provisional cells."""

_BASIS_RULE: Final[str] = "DETERMINISTIC_RULE_V1"
_BASIS_OWNER: Final[str] = "OWNER_DECISION_2026-10-08"

_CELL_ID = "cell_id"
_CANDIDATE = "membership_v1_candidate"
_REASON = "membership_reason"


def owner_decisions_from_csv(path: str) -> dict[str, str]:
    """Load non-empty ``OWNER_DECISION`` values from the owner table.

    Rows whose decision cell is blank (an unreviewed table) are skipped;
    every recorded value must be in :data:`OWNER_DECISION_TOKENS`.
    """
    frame = pd.read_csv(path, dtype=str).fillna("")
    if _CELL_ID not in frame.columns or "OWNER_DECISION" not in frame.columns:
        raise ValueError(
            f"{path}: owner table must contain {_CELL_ID!r} and " "'OWNER_DECISION' columns"
        )
    decisions: dict[str, str] = {}
    for row in frame.itertuples(index=False):
        token = str(row.OWNER_DECISION).strip()
        if not token:
            continue
        if token not in OWNER_DECISION_TOKENS:
            raise ValueError(f"{row.cell_id}: unknown OWNER_DECISION {token!r}")
        decisions[row.cell_id] = token
    return decisions


def apply_owner_decisions(
    candidate: pd.DataFrame,
    decisions: Mapping[str, str],
    *,
    require_complete: bool = True,
) -> pd.DataFrame:
    """Apply recorded owner decisions to the immutable v1 candidate.

    Parameters
    ----------
    candidate:
        The v1 candidate frame with at least ``cell_id``,
        ``membership_v1_candidate`` and ``membership_reason`` columns.
        Never mutated.
    decisions:
        Maps cell ID to an :data:`OWNER_DECISION_TOKENS` value.
    require_complete:
        When true (freeze use) every provisional cell must have exactly
        one decision and decisions may only target provisional cells.

    Returns
    -------
    pandas.DataFrame
        All candidate columns, unchanged, plus:

        ``owner_decision``
            The recorded owner token, or empty for rule-decided cells.
        ``membership_v1_1``
            Effective v1.1 status (closed vocabulary of
            :data:`~spartina.data.national.domain_membership.DECISION_TOKENS`).
        ``v1_1_basis``
            ``DETERMINISTIC_RULE_V1`` or ``OWNER_DECISION_2026-10-08``.
        ``disclaimer_ref``
            Disclaimer key for operationally included contested-admin
            cells, empty otherwise.
        ``production_eligible``
            True for the two KEEP statuses only.

    Rules enforced
    --------------
    * ``KEEP_ISLAND_COASTAL`` is accepted only for
      ``CONTESTED_ADMIN_NEARSHORE`` cells -- the operational nearshore
      frame decision.  It cannot extend the 25 km offshore-island reach.
    * ``REMAIN_PROVISIONAL`` on an ``UNADMINISTERED_LAND`` cell produces
      ``PROVISIONAL_OFFSHORE_POLICY``; on any other provisional reason
      the cell stays ``PROVISIONAL_UNRESOLVED``.
    * The deterministic status of every other cell is copied unchanged.
    """
    for col in (_CELL_ID, _CANDIDATE, _REASON):
        if col not in candidate.columns:
            raise ValueError(f"candidate frame missing required column {col!r}")

    provisional_ids = set(candidate.loc[candidate[_CANDIDATE] == PROVISIONAL_UNRESOLVED, _CELL_ID])
    decision_ids = set(decisions)
    if require_complete:
        unhandled = provisional_ids - decision_ids
        extra = decision_ids - provisional_ids
        problems = []
        if unhandled:
            problems.append(f"provisional cells without decision: {sorted(unhandled)}")
        if extra:
            problems.append(f"decisions on non-provisional cells: {sorted(extra)}")
        if problems:
            raise ValueError(
                "owner decisions do not cover the v1 candidate: " + "; ".join(problems)
            )
    elif not decision_ids <= provisional_ids:
        raise ValueError(
            "decisions target non-provisional cells: " f"{sorted(decision_ids - provisional_ids)}"
        )

    out = candidate.reset_index(drop=True).copy()
    n = len(out)
    owner_col = [""] * n
    effective = out[_CANDIDATE].astype(str).tolist()
    basis = [_BASIS_RULE] * n
    disclaimer = [""] * n

    id_to_pos = {cid: i for i, cid in enumerate(out[_CELL_ID].tolist())}
    for cell_id, token in decisions.items():
        if token not in OWNER_DECISION_TOKENS:
            raise ValueError(f"{cell_id}: unknown OWNER_DECISION {token!r}")
        pos = id_to_pos[cell_id]
        reason = str(out.at[pos, _REASON])
        owner_col[pos] = token
        basis[pos] = _BASIS_OWNER
        if token == OWNER_DECISION_KEEP:
            if reason != REASON_CONTESTED_ADMIN_NEARSHORE:
                raise ValueError(
                    f"{cell_id}: KEEP_ISLAND_COASTAL owner decision is only "
                    "valid for CONTESTED_ADMIN_NEARSHORE cells; the 25 km "
                    "offshore-island reach must not be extended by ad-hoc "
                    f"exceptions (rule reason: {reason})"
                )
            effective[pos] = KEEP_ISLAND_COASTAL
            disclaimer[pos] = CONTESTED_ADMIN_DISCLAIMER_REF
        else:  # OWNER_DECISION_REMAIN_PROVISIONAL
            if reason == REASON_UNADMINISTERED_LAND:
                effective[pos] = PROVISIONAL_OFFSHORE_POLICY
            else:
                effective[pos] = PROVISIONAL_UNRESOLVED

    out["owner_decision"] = owner_col
    out["membership_v1_1"] = effective
    out["v1_1_basis"] = basis
    out["disclaimer_ref"] = disclaimer
    out["production_eligible"] = [is_production_kept(status) for status in effective]
    return out


def membership_changes(v1_1: pd.DataFrame) -> pd.DataFrame:
    """Rows whose effective v1.1 status differs from the v1 candidate."""
    changed = v1_1.loc[
        v1_1["membership_v1_1"] != v1_1[_CANDIDATE],
        [_CELL_ID, _REASON, _CANDIDATE, "owner_decision", "membership_v1_1"],
    ]
    return changed.reset_index(drop=True)
