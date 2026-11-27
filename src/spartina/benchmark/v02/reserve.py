"""Issue #21, Phase C — pre-registered fresh v0.2 test reserve.

The reserve is a sealed stratum of NEW panel cells declared BEFORE any
pixel export. It is not a train/val/test split: acquisition QA is
incomplete, so final roles are assigned later by the frozen v0.2
protocol using ONLY this pre-registered reserve for primary temporal
test. Nothing here looks at Stage-1 performance, model outputs, or
imagery.

Membership is deterministic: provinces are ordered by (panel positive
count desc, province asc); in the top ``POSITIVE_PROVINCES`` provinces
``POSITIVE_PER_PROVINCE`` positives and ``BACKGROUND_PER_PROVINCE``
backgrounds are hash-ranked into the reserve.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

import pandas as pd

from spartina.benchmark.v02.requirements import selection_hash_rank

RESERVE_NAME: Final[str] = "V0_2_FRESH_NEW_CELL_TEST_RESERVE"
FINAL_ROLES: Final[str] = "PRE_REGISTERED_ROLES_NOT_ASSIGNED"
POSITIVE_PROVINCES: Final[int] = 8
POSITIVE_PER_PROVINCE: Final[int] = 2
BACKGROUND_PER_PROVINCE: Final[int] = 1
RESERVE_POSITIVE_SLOT: Final[str] = "reserve_positive"
RESERVE_BACKGROUND_SLOT: Final[str] = "reserve_background"


def _ranked_ids(cells: pd.DataFrame, slot: str) -> list[str]:
    ranked = sorted(
        cells["cell_id"],
        key=lambda cid: (selection_hash_rank(f"slot:{slot}", cid), cid))
    return ranked


def declare_reserve(panel: pd.DataFrame) -> dict[str, Any]:
    """Build the deterministic reserve declaration from the frozen panel."""
    needed = {"cell_id", "province", "any_positive", "clean_background"}
    missing = needed - set(panel.columns)
    if missing:
        raise ValueError(f"panel missing columns: {sorted(missing)}")

    usable = panel[panel["province"] != "UNKNOWN"]
    counts = usable.groupby("province").agg(
        n_positive=("any_positive", "sum"),
        n_background=("clean_background", "sum"))
    eligible = counts[
        (counts["n_positive"] >= POSITIVE_PER_PROVINCE)
        & (counts["n_background"] >= BACKGROUND_PER_PROVINCE)]
    province_order = eligible.sort_values(
        ["n_positive", "province"], ascending=[False, True]).index.tolist()
    province_order = province_order[:POSITIVE_PROVINCES]

    members: dict[str, dict[str, str]] = {}
    deficits: list[str] = []
    if len(province_order) < POSITIVE_PROVINCES:
        deficits.append(
            f"reserve spans {len(province_order)} provinces with >= "
            f"{POSITIVE_PER_PROVINCE} positives + >= "
            f"{BACKGROUND_PER_PROVINCE} background "
            f"(predeclared design seeks {POSITIVE_PROVINCES})")

    for prov in province_order:
        pc = usable[(usable["province"] == prov) & usable["any_positive"]]
        for cid in _ranked_ids(pc, RESERVE_POSITIVE_SLOT)[
                :POSITIVE_PER_PROVINCE]:
            members[cid] = {"province": prov, "stratum": "positive"}
        bc = usable[(usable["province"] == prov)
                    & usable["clean_background"]]
        for cid in _ranked_ids(bc, RESERVE_BACKGROUND_SLOT)[
                :BACKGROUND_PER_PROVINCE]:
            members.setdefault(cid, {"province": prov,
                                     "stratum": "background"})

    reserve_ids = sorted(members)
    by_province = (
        pd.Series([m["province"] for m in members.values()])
        .value_counts().sort_index().to_dict())
    n_positive = sum(1 for m in members.values() if m["stratum"] == "positive")
    declaration = {
        "reserve_name": RESERVE_NAME,
        "final_roles_status": FINAL_ROLES,
        "sealed_until": (
            "acquisition QA completes and the future SpartinaShift v0.2 "
            "protocol freezes final train/val/test roles"),
        "model_output_influence": False,
        "stage1_test_witness_eligible": False,
        "selection_rule": {
            "province_order": "(panel positive count desc, province asc)",
            "provinces_used": province_order,
            "positive_per_province": POSITIVE_PER_PROVINCE,
            "background_per_province": BACKGROUND_PER_PROVINCE,
            "rank": "slot-salted SHA-256 hash rank, then cell_id",
        },
        "n_cells": len(reserve_ids),
        "n_positive": n_positive,
        "n_background": len(reserve_ids) - n_positive,
        "n_provinces": len(by_province),
        "by_province": by_province,
        "members": [
            {"cell_id": cid, "province": members[cid]["province"],
             "stratum": members[cid]["stratum"]}
            for cid in reserve_ids],
        "deficits_max_attainable": deficits,
    }
    declaration["checksum"] = reserve_checksum(declaration)
    return declaration


def reserve_checksum(declaration: dict[str, Any]) -> str:
    body = {
        "reserve_name": declaration["reserve_name"],
        "members": [(m["cell_id"], m["stratum"])
                    for m in declaration["members"]],
        "provinces_used": declaration["selection_rule"]["provinces_used"],
    }
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
