"""SpartinaShift v0.2 GOLD CANDIDATE registry rules (Issue #21 Phase K).

Builds ONLY a candidate registry for Issue #11. Nothing here creates
GOLD labels: GEODATA / CMSA / CM-SSM agreement cannot promote a site,
and every record is sealed GOLD_STATUS = CANDIDATE_ONLY pending
independent field / UAV / high-resolution evidence and permission
verification.

Membership is deterministic, model-free and quota-spread across coastal
segments, using only frozen label-source strata, patch/area class and
the panel's frozen acquisition plan summaries. Cells may carry several
candidate-type tags; the union is capped at 40 unique sites.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Final

import pandas as pd

from spartina.benchmark.v02.requirements import selection_hash_rank

REGISTRY_NAME: Final[str] = "V0_2_GOLD_CANDIDATE_REGISTRY"
GOLD_STATUS: Final[str] = "CANDIDATE_ONLY"
MAX_CANDIDATE_SITES: Final[int] = 40

#: (type token, quota, minimum distinct coastal segments demanded).
CANDIDATE_TYPES: Final[tuple[tuple[str, int, int], ...]] = (
    ("SOURCE_AGREEMENT_POSITIVE", 10, 4),
    ("SOURCE_DISAGREEMENT_POSITIVE", 8, 3),
    ("SOURCE_BACKGROUND", 8, 4),
    ("SMALL_FRAGMENTED_PATCH", 6, 3),
    ("BOUNDARY_SITE", 6, 3),
    ("CONFOUNDER_PRONE", 4, 2),
)
REGION_COLUMN: Final[str] = "coastal_segment"
UNKNOWN_REGION: Final[str] = "UNKNOWN"

#: Categories that indicate independent-source disagreement.
DISAGREEMENT_CATEGORIES: Final[frozenset[str]] = frozenset({
    "GEODATA_ONLY", "CMSA_ONLY", "CMSSM_ONLY",
    "GEODATA_CMSA_ONLY", "GEODATA_CMSSM_ONLY", "CMSA_CMSSM_PRESENT"})
#: Single/paired-source CM-SSM claims are the confounder-prone watch set
#: (independent source flags a site the operational products omit).
CONFOUNDER_CATEGORIES: Final[frozenset[str]] = frozenset({
    "CMSSM_ONLY", "GEODATA_CMSSM_ONLY"})
POSITIVE_AGREEMENT: Final[str] = "ALL_THREE_PRESENT"
BACKGROUND_AGREEMENT: Final[str] = "NONE_PRESENT"
EDGE_PROXIMITY_M: Final = 300.0


def _type_members(frame: pd.DataFrame, ctype: str) -> list[str]:
    """Deterministic eligibility of one candidate type."""
    positive = frame["any_positive"].astype(bool)
    if ctype == "SOURCE_AGREEMENT_POSITIVE":
        sel = frame["agreement_2020"] == POSITIVE_AGREEMENT
    elif ctype == "SOURCE_DISAGREEMENT_POSITIVE":
        sel = positive & frame["agreement_2020"].isin(
            DISAGREEMENT_CATEGORIES)
    elif ctype == "SOURCE_BACKGROUND":
        sel = frame["clean_background"].astype(bool)
    elif ctype == "SMALL_FRAGMENTED_PATCH":
        sel = positive & frame["area_class"].isin({"TRACE", "SMALL"})
    elif ctype == "BOUNDARY_SITE":
        temporal = (
            (frame["geo15"].astype(bool) & ~frame["geo20"].astype(bool))
            | (frame["cmsa20"].astype(bool) & ~frame["cmsa21"].astype(bool))
            | (~frame["cmsa20"].astype(bool)
               & frame["cmsa21"].astype(bool)))
        edge = frame.get("positive_edge_geodata2020")
        edge_bool = (edge.fillna(False).astype(bool)
                     if edge is not None else False)
        sel = positive & (temporal | edge_bool)
    elif ctype == "CONFOUNDER_PRONE":
        sel = frame["agreement_2020"].isin(CONFOUNDER_CATEGORIES)
    else:
        raise ValueError(f"unknown candidate type {ctype}")
    return list(frame.loc[sel, "cell_id"])


def _rank_in_type(
    frame: pd.DataFrame, cell_ids: list[str], ctype: str,
) -> list[str]:
    """Region round-robin, then hash rank, then cell id."""
    region_of = dict(zip(frame["cell_id"], frame[REGION_COLUMN],
                         strict=True))
    by_region: dict[str, list[str]] = defaultdict(list)
    for cid in cell_ids:
        by_region[str(region_of[cid])].append(cid)
    for ids in by_region.values():
        ids.sort(key=lambda c: (
            selection_hash_rank(f"gold_{ctype}", c), c))
    # Known regions first (UNKNOWN only fills after), region name order.
    known = sorted(r for r in by_region if r != UNKNOWN_REGION)
    ordered: list[str] = []
    region_round = {r: 0 for r in by_region}
    pending = True
    while pending:
        pending = False
        for region in known:
            idx = region_round[region]
            if idx < len(by_region[region]):
                ordered.append(by_region[region][idx])
                region_round[region] = idx + 1
                pending = True
        unknown = by_region.get(UNKNOWN_REGION, [])
        idx = region_round.get(UNKNOWN_REGION, 0)
        if idx < len(unknown):
            ordered.append(unknown[idx])
            region_round[UNKNOWN_REGION] = idx + 1
            pending = True
    return ordered


def build_registry(
    frame: pd.DataFrame,
    plan_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Assemble candidate records, quotas and honest deficits."""
    required = {
        "cell_id", REGION_COLUMN, "province", "agreement_2020",
        "area_class", "any_positive", "clean_background",
        "geo15", "geo20", "cmsa20", "cmsa21"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"gold frame missing columns: {sorted(missing)}")
    frame = frame.set_index("cell_id", drop=False)
    tags: dict[str, list[str]] = defaultdict(list)
    quotas: list[dict[str, Any]] = []
    for ctype, quota, min_regions in CANDIDATE_TYPES:
        members = _type_members(frame, ctype)
        ranked = _rank_in_type(frame, members, ctype)
        chosen = ranked[:quota]
        for cid in chosen:
            tags[cid].append(ctype)
        regions_used = sorted({
            str(frame.loc[cid, REGION_COLUMN]) for cid in chosen}
            - {UNKNOWN_REGION})
        deficits: list[str] = []
        if len(members) < quota:
            deficits.append(
                f"{ctype}: pool {len(members)} < quota {quota} "
                "(max attainable recorded; no fabrication)")
        if chosen and len(regions_used) < min_regions:
            deficits.append(
                f"{ctype}: only {len(regions_used)} known regions among "
                f"chosen (< demanded {min_regions})")
        quotas.append({
            "candidate_type": ctype, "quota": quota,
            "min_regions": min_regions,
            "pool_size": len(members), "selected": len(chosen),
            "regions_used": regions_used,
            "selected_cell_ids": chosen,
            "deficits_max_attainable": deficits})

    rows: list[dict[str, Any]] = []
    for cid in sorted(tags):
        r = frame.loc[cid]
        plans = plan_lookup.get(cid, {})
        rows.append({
            "cell_id": cid,
            "center_lon": float(r["center_lon"]),
            "center_lat": float(r["center_lat"]),
            "province": str(r["province"]),
            "coastal_segment": str(r[REGION_COLUMN]),
            "island": bool(r["island"]) if "island" in frame.columns else None,
            "candidate_types": tags[cid],
            "source_evidence": {
                "agreement_2020": str(r["agreement_2020"]),
                "area_class": str(r["area_class"]),
                "max_pos_area_km2": (
                    float(r["max_pos_area_km2"])
                    if "max_pos_area_km2" in frame.columns else None),
                "geodata_2015_present": bool(r["geo15"]),
                "geodata_2020_present": bool(r["geo20"]),
                "cmsa_2020_present": bool(r["cmsa20"]),
                "cmsa_2021_present": bool(r["cmsa21"]),
                "positive_edge_geodata2020": (
                    bool(r["positive_edge_geodata2020"])
                    if "positive_edge_geodata2020" in frame.columns
                    else None)},
            "relevant_acquisition_dates": plans,
            "reason_selected": (
                "deterministic quota+region spread from frozen label "
                "strata; no model output; no imagery inspected"),
            "high_resolution_evidence_status": "NOT_COLLECTED",
            "permission_provenance_status": "UNVERIFIED_PENDING_OWNER",
            "gold_status": GOLD_STATUS,
            "promotion_rule": (
                "no GEODATA/CMSA/CM-SSM label product can promote a "
                "candidate; GOLD requires independent field/UAV/expert "
                "evidence and permission under the future Issue #11 "
                "protocol"),
        })
    checksum = registry_checksum(rows)
    return {
        "product": REGISTRY_NAME,
        "issue": 21,
        "phase": "K",
        "n_candidates": len(rows),
        "max_candidate_sites": MAX_CANDIDATE_SITES,
        "candidate_type_quota": quotas,
        "edge_proximity_rule_m": EDGE_PROXIMITY_M,
        "candidates": rows,
        "checksum": checksum}


def canonical_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def registry_checksum(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(canonical_dumps(rows).encode("utf-8")).hexdigest()
