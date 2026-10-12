"""SpartinaShift v0.2 multi-date acquisition rules (Issue #21 Phases D/E/G).

Pure, deterministic, model-free selection logic. Every rule here is
predeclared before any pixel/coverage is inspected; the live GEE driver
only supplies actual-mask fractions through the injected evaluator
callback, so the ranking itself stays unit-testable without Earth Engine.

Phase D -- Sentinel-2: up to three same-datatake union events per
cell-year (2020/2021), at most one per predeclared phenology tertile,
each passing the existing >= 0.95 actual observed-mask gate. Tertile
partitioning (not a greedy top-3) is the anti-near-duplicate mechanism.

Phase E -- Landsat: up to three Collection-2 L2 observations per
cell-year (2015/2020), one per tertile, sensor identity preserved,
observed-coverage gate measured on the exact 30 m export grid. No
cross-sensor compositing and no spectral harmonization.

Phase G -- Sentinel-1 pairing: one search per selected S2 event in each
orbit pass; primary pair iff absolute UTC-date gap <= 7 d and the
s1_dualpol_valid_v2 actual mask passes. A predeclared 14 d sensitivity
tier is recorded separately and can never widen the primary threshold.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from spartina.data.national.pilot_events import (
    AUTUMN_DOY_END,
    AUTUMN_DOY_START,
)

# -- years / counts ------------------------------------------------------
S2_YEARS: Final[tuple[int, ...]] = (2020, 2021)
LANDSAT_YEARS: Final[tuple[int, ...]] = (2015, 2020)
MAX_DATATAKES_PER_CELL_YEAR: Final[int] = 3
MAX_LANDSAT_PER_CELL_YEAR: Final[int] = 3
LANDSAT_TARGET_PER_CELL_YEAR: Final[int] = 2

#: Optical cloud metadata ceiling (same predeclared rule as Issue #19).
OPTICAL_CLOUD_MAX: Final[float] = 0.30
#: Nominal WRS/MGRS geometry is discovery prefilter only.
NOMINAL_PREFILTER_MIN: Final[float] = 0.90
#: Actual observed-coverage gate on the exact locked export grid.
ACTUAL_MASK_GATE: Final[float] = 0.95

# -- predeclared phenology tertiles (inclusive DOY bounds) ---------------
# Window 260..320 is 61 days: two 20-day tertiles and one 21-day tertile.
TERTILE_EARLY: Final[str] = "EARLY"
TERTILE_MID: Final[str] = "MID"
TERTILE_LATE: Final[str] = "LATE"
#: (name, doy_min, doy_max, preferred_center_doy)
TERTILES: Final[tuple[tuple[str, int, int, int], ...]] = (
    (TERTILE_EARLY, 260, 279, 269),
    (TERTILE_MID, 280, 299, 289),
    (TERTILE_LATE, 300, 320, 310),
)
TERTILE_ORDER: Final[tuple[str, ...]] = tuple(t[0] for t in TERTILES)
_TERTILE_BY_NAME: Final[dict[str, tuple[int, int, int]]] = {
    name: (lo, hi, center) for name, lo, hi, center in TERTILES}

# -- Landsat source sensor priority (deterministic; L8 preferred) --------
#: Predeclared preference for complete-frame, better-radiometric L8;
#: L7 SLC-off frames cannot pass the 0.95 observed gate anyway, but the
#: identity is always preserved per event and sensors are never merged.
LANDSAT_SENSOR_PRIORITY: Final[dict[str, int]] = {
    "landsat8": 0, "landsat7": 1, "landsat5": 2}

# -- Phase G pairing ------------------------------------------------------
S1_PRIMARY_GAP_DAYS: Final[int] = 7
S1_SENSITIVITY_GAP_DAYS: Final[int] = 14
#: Primary pairing search must stay inside the predeclared autumn window.
PAIR_PRIMARY_DOY_MIN: Final[int] = AUTUMN_DOY_START
PAIR_PRIMARY_DOY_MAX: Final[int] = AUTUMN_DOY_END
#: Sensitivity-only tier may reach 14 d beyond the optical window; every
#: such candidate is flagged outside_autumn_window and never promoted.
PAIR_EXTENDED_DOY_MIN: Final[int] = AUTUMN_DOY_START - S1_SENSITIVITY_GAP_DAYS
PAIR_EXTENDED_DOY_MAX: Final[int] = AUTUMN_DOY_END + S1_SENSITIVITY_GAP_DAYS

STATUS_ELIGIBLE: Final[str] = "V02_ELIGIBLE"
STATUS_NO_ELIGIBLE: Final[str] = "NO_ELIGIBLE_EVENT_ACTUAL_MASK"
STATUS_NO_SCENE: Final[str] = "NO_SCENE"
STATUS_PAIRED: Final[str] = "PAIRED_PRIMARY_LTE7D"
STATUS_SENSITIVITY: Final[str] = "SENSITIVITY_TIER_LTE14D_ONLY"
STATUS_UNAVAILABLE: Final[str] = "MODALITY_SLOT_UNAVAILABLE"
SAME_DAY_TOKEN: Final[str] = "SAME_DAY_GAP0"
NEAR_SYNC_TOKEN: Final[str] = "NEAR_SYNCHRONOUS_GTE1D_LTE7D"

S2_PLAN_NAME: Final[str] = "V0_2_S2_ACQUISITION_PLAN"
LANDSAT_PLAN_NAME: Final[str] = "V0_2_LANDSAT_ACQUISITION_PLAN"
PAIRING_LEDGER_NAME: Final[str] = "V0_2_S1_PAIRING_LEDGER"

#: Keys that never enter a document checksum.
VOLATILE_KEYS: Final[frozenset[str]] = frozenset(
    {"generated_utc", "git_commit", "document_checksum"})


# ---------------------------------------------------------------------------
# canonical serialization / checksums
# ---------------------------------------------------------------------------

def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=str)


def document_checksum(document: dict[str, Any]) -> str:
    body = {k: v for k, v in document.items() if k not in VOLATILE_KEYS}
    return hashlib.sha256(canonical_dumps(body).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Phase D/E -- tertile slotting and deterministic ranking
# ---------------------------------------------------------------------------

def tertile_of(doy: int) -> str | None:
    """Return the predeclared tertile name for an autumn DOY, else None."""
    for name, lo, hi, _center in TERTILES:
        if lo <= int(doy) <= hi:
            return name
    return None


def _tertile_center(name: str) -> int:
    return _TERTILE_BY_NAME[name][2]


def s2_slot_rank(candidate: dict[str, Any], tertile: str) -> tuple[Any, ...]:
    """Within-tertile S2 rank: cloud asc, distance to slot center, id."""
    return (
        round(float(candidate["cloud_fraction"]), 6),
        abs(int(candidate["doy"]) - _tertile_center(tertile)),
        str(candidate["event_id"]),
    )


def landsat_slot_rank(
    candidate: dict[str, Any], tertile: str,
) -> tuple[Any, ...]:
    """Within-tertile Landsat rank: cloud, slot-center distance, sensor."""
    return (
        round(float(candidate["cloud_fraction"]), 6),
        abs(int(candidate["doy"]) - _tertile_center(tertile)),
        LANDSAT_SENSOR_PRIORITY.get(str(candidate["sensor"]), 99),
        str(candidate["scene_id"]),
    )


def order_by_tertile(
    candidates: Sequence[dict[str, Any]],
    rank_key: Callable[[dict[str, Any], str], tuple[Any, ...]],
) -> dict[str, list[dict[str, Any]]]:
    """Partition candidates into tertiles and freeze evaluation order."""
    slots: dict[str, list[dict[str, Any]]] = {name: [] for name in TERTILE_ORDER}
    for cand in candidates:
        name = tertile_of(int(cand["doy"]))
        if name is not None:
            slots[name].append(cand)
    for name in TERTILE_ORDER:
        t_default = name

        def _key(c: dict[str, Any], t: str = t_default) -> tuple[Any, ...]:
            return rank_key(c, t)

        slots[name].sort(key=_key)
    return slots


#: Evaluator maps an event key to its actual-mask evidence dict:
#: {"fraction": float, "evidence_source": str, ...sensor-specific extras}.
Evaluator = Callable[[dict[str, Any]], dict[str, Any]]


def select_tertile_slots(
    cell_id: str,
    year: int,
    sensor: str,
    candidates: Sequence[dict[str, Any]],
    rank_key: Callable[[dict[str, Any], str], tuple[Any, ...]],
    evaluate: Evaluator,
) -> list[dict[str, Any]]:
    """Pick at most one gate-passing event per tertile.

    Candidates are evaluated in frozen rank order within each tertile;
    the first reaching ACTUAL_MASK_GATE is the slot pick. Slots never
    borrow dates from other tertiles (that would defeat spreading), and
    failed candidates keep their measured fraction in the ledger.
    """
    ordered = order_by_tertile(candidates, rank_key)
    slots_out: list[dict[str, Any]] = []
    for tertile in TERTILE_ORDER:
        pool = ordered[tertile]
        evaluated: list[dict[str, Any]] = []
        pick: dict[str, Any] | None = None
        pick_evidence: dict[str, Any] | None = None
        for rank, cand in enumerate(pool, start=1):
            evidence = evaluate(cand)
            rec = {
                "rank": rank,
                "event_id": str(cand["event_id"]),
                "doy": int(cand["doy"]),
                "cloud_fraction": float(cand["cloud_fraction"]),
                "actual_observed_fraction": float(evidence["fraction"]),
                "evidence_source": str(evidence["evidence_source"]),
            }
            evaluated.append(rec)
            if float(evidence["fraction"]) >= ACTUAL_MASK_GATE:
                pick = cand
                pick_evidence = evidence
                break
        best = max((e["actual_observed_fraction"] for e in evaluated),
                   default=None)
        if pick is not None:
            assert pick_evidence is not None
            slots_out.append({
                "cell_id": cell_id, "year": year, "sensor": sensor,
                "tertile": tertile, "status": STATUS_ELIGIBLE,
                "event_id": str(pick["event_id"]),
                "event_utc": str(pick["utc"]),
                "doy": int(pick["doy"]),
                "cloud_fraction": float(pick["cloud_fraction"]),
                "actual_observed_fraction": float(
                    pick_evidence["fraction"]),
                "evidence_source": str(pick_evidence["evidence_source"]),
                "n_candidates_evaluated": len(evaluated),
                "evaluated": evaluated,
            })
        else:
            slots_out.append({
                "cell_id": cell_id, "year": year, "sensor": sensor,
                "tertile": tertile,
                "status": STATUS_NO_SCENE if not pool else STATUS_NO_ELIGIBLE,
                "event_id": "", "event_utc": "", "doy": None,
                "cloud_fraction": None,
                "actual_observed_fraction": best,
                "evidence_source": "",
                "n_candidates_evaluated": len(evaluated),
                "evaluated": evaluated,
            })
    return slots_out


# ---------------------------------------------------------------------------
# Phase G -- S1 pairing scans
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class S1Candidate:
    event_id: str
    scene_id: str
    utc: str
    doy: int
    pass_direction: str
    relative_orbit: int | None
    platform: str


@dataclass
class PairScanPass:
    """Result of scanning one orbit pass for one S2 event."""

    pass_direction: str
    status: str
    pick: S1Candidate | None = None
    gap_days: int | None = None
    actual_observed_fraction: float | None = None
    evidence_source: str = ""
    evaluated: list[dict[str, Any]] = field(default_factory=list)
    nearest_primary_gap: int | None = None
    nearest_primary_fraction: float | None = None


def _gap(s2_doy: int, cand: S1Candidate) -> int:
    return abs(int(cand.doy) - int(s2_doy))


def scan_pass(
    s2_event: dict[str, Any],
    pass_direction: str,
    candidates: Sequence[S1Candidate],
    evaluate: Evaluator,
) -> PairScanPass:
    """Scan one pass in gap order; primary <=7 d, sensitivity <=14 d.

    Scan rule (predeclared):
    1. Autumn-window candidates within +/- 7 d, gap-asc; first passing
       the actual-mask gate is the primary pick, stop.
    2. If none, autumn-window candidates within +/- 14 d, gap-asc; first
       passing is the sensitivity-tier pick, stop.
    Every evaluated candidate is ledgered; the nearest-gap primary-window
    candidate's measured fraction is recorded even when it fails the
    gate (best achievable evidence, never hidden).
    """
    s2_doy = int(s2_event["doy"])
    by_gap = sorted(candidates, key=lambda c: (_gap(s2_doy, c), c.scene_id))
    primary_window = [
        c for c in by_gap
        if _gap(s2_doy, c) <= S1_PRIMARY_GAP_DAYS
        and PAIR_PRIMARY_DOY_MIN <= c.doy <= PAIR_PRIMARY_DOY_MAX]
    extended_only = [
        c for c in by_gap
        if _gap(s2_doy, c) <= S1_SENSITIVITY_GAP_DAYS
        and PAIR_EXTENDED_DOY_MIN <= c.doy <= PAIR_EXTENDED_DOY_MAX
        and not (PAIR_PRIMARY_DOY_MIN <= c.doy <= PAIR_PRIMARY_DOY_MAX
                 and _gap(s2_doy, c) <= S1_PRIMARY_GAP_DAYS)]
    out = PairScanPass(pass_direction=pass_direction,
                       status=STATUS_NO_SCENE if not by_gap
                       else STATUS_UNAVAILABLE)

    def _scan(window: Sequence[S1Candidate], window_tag: str,
              ok_status: str, *, rank_start: int = 1) -> PairScanPass | None:
        for rank, cand in enumerate(window, start=rank_start):
            evidence = evaluate(cand.__dict__)
            gap = _gap(s2_doy, cand)
            if window_tag == "PRIMARY_LTE7D" and rank == rank_start:
                out.nearest_primary_gap = gap
                out.nearest_primary_fraction = float(evidence["fraction"])
            out.evaluated.append({
                "rank": rank, "window": window_tag,
                "event_id": cand.event_id, "scene_id": cand.scene_id,
                "doy": cand.doy, "gap_days": gap,
                "outside_autumn_window": not (
                    PAIR_PRIMARY_DOY_MIN <= cand.doy <= PAIR_PRIMARY_DOY_MAX),
                "actual_observed_fraction": float(evidence["fraction"]),
                "s1_floor_check_fraction": float(
                    evidence.get("s1_floor_check_fraction",
                                 evidence["fraction"])),
                "evidence_source": str(evidence["evidence_source"]),
            })
            if float(evidence["fraction"]) >= ACTUAL_MASK_GATE:
                out.status = ok_status
                out.pick = cand
                out.gap_days = gap
                out.actual_observed_fraction = float(evidence["fraction"])
                out.evidence_source = str(evidence["evidence_source"])
                return out
        return None

    hit = _scan(primary_window, "PRIMARY_LTE7D", STATUS_PAIRED)
    if hit is not None:
        return hit
    _scan(extended_only, "SENSITIVITY_LTE14D", STATUS_SENSITIVITY,
          rank_start=len(out.evaluated) + 1)
    return out


def pair_s2_event(
    s2_event: dict[str, Any],
    candidates_by_pass: Mapping[str, Sequence[S1Candidate]],
    evaluate: Evaluator,
) -> dict[str, Any]:
    """Pair one selected S2 event, preserving ASC/DESC and orbit identity.

    Primary choice across passes: minimum gap, then higher actual
    fraction, then ASC before DESC, then source id. "Simultaneous" is
    used only when gap == 0.
    """
    scans = {
        pass_direction: scan_pass(s2_event, pass_direction, cands, evaluate)
        for pass_direction, cands in candidates_by_pass.items()}
    primary_passes = [s for s in scans.values()
                      if s.status == STATUS_PAIRED and s.pick is not None]
    record: dict[str, Any] = {
        "cell_id": s2_event["cell_id"], "year": s2_event["year"],
        "tertile": s2_event["tertile"],
        "s2_event_id": s2_event["event_id"],
        "s2_event_utc": s2_event["event_utc"], "s2_doy": s2_event["doy"],
        "pass_scans": [],
    }
    if primary_passes:
        chosen = min(
            primary_passes,
            key=lambda s: (
                s.gap_days if s.gap_days is not None else 10**9,
                (-s.actual_observed_fraction
                 if s.actual_observed_fraction is not None else 0.0),
                0 if s.pass_direction == "ASC" else 1,
                str(s.pick.scene_id) if s.pick else "",
            ))
        cand = chosen.pick
        assert cand is not None
        assert chosen.gap_days is not None
        assert chosen.actual_observed_fraction is not None
        record.update({
            "status": STATUS_PAIRED,
            "pair_token": (SAME_DAY_TOKEN if chosen.gap_days == 0
                           else NEAR_SYNC_TOKEN),
            "s1_event_id": cand.event_id, "s1_scene_id": cand.scene_id,
            "s1_event_utc": cand.utc, "s1_doy": cand.doy,
            "gap_days": chosen.gap_days,
            "pass": cand.pass_direction,
            "relative_orbit": cand.relative_orbit,
            "platform": cand.platform,
            "actual_observed_fraction": chosen.actual_observed_fraction,
            "evidence_source": chosen.evidence_source,
        })
    else:
        sensitivity = [s for s in scans.values()
                       if s.status == STATUS_SENSITIVITY and s.pick is not None]
        chosen_sens = min(
            sensitivity,
            key=lambda s: (
                s.gap_days if s.gap_days is not None else 10**9,
                (-s.actual_observed_fraction
                 if s.actual_observed_fraction is not None else 0.0),
                0 if s.pass_direction == "ASC" else 1,
                str(s.pick.scene_id) if s.pick else "",
            ),
            default=None)
        record["status"] = (STATUS_SENSITIVITY if chosen_sens is not None
                            else STATUS_UNAVAILABLE)
        record.update({
            "pair_token": "", "s1_event_id": "", "s1_scene_id": "",
            "s1_event_utc": "", "s1_doy": None, "gap_days": None,
            "pass": "", "relative_orbit": None, "platform": "",
            "actual_observed_fraction": None, "evidence_source": ""})
        if chosen_sens is not None and chosen_sens.pick is not None:
            assert chosen_sens.gap_days is not None
            assert chosen_sens.actual_observed_fraction is not None
            c = chosen_sens.pick
            record.update({
                "s1_event_id": c.event_id, "s1_scene_id": c.scene_id,
                "s1_event_utc": c.utc, "s1_doy": c.doy,
                "gap_days": chosen_sens.gap_days,
                "pass": c.pass_direction, "relative_orbit": c.relative_orbit,
                "platform": c.platform,
                "actual_observed_fraction":
                    chosen_sens.actual_observed_fraction,
                "evidence_source": chosen_sens.evidence_source})
        # Best achievable primary-window gap across passes (honest ledger).
        nearest = [s.nearest_primary_gap for s in scans.values()
                   if s.nearest_primary_gap is not None]
        record["best_primary_window_gap_days"] = (
            min(nearest) if nearest else None)
    for pass_direction, scan in scans.items():
        record["pass_scans"].append({
            "pass": pass_direction, "status": scan.status,
            "s1_event_id": scan.pick.event_id if scan.pick else "",
            "gap_days": scan.gap_days,
            "actual_observed_fraction": scan.actual_observed_fraction,
            "nearest_primary_gap_days": scan.nearest_primary_gap,
            "nearest_primary_fraction": scan.nearest_primary_fraction,
            "n_evaluated": len(scan.evaluated),
            "evaluated": scan.evaluated,
        })
    return record
