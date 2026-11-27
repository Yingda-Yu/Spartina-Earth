"""M2.1b controlled real-pixel pilot: deterministic, label-only rules.

Pure (no Earth Engine, no raster IO) selection and event-eligibility
rules for Issue #13. The GEE live discovery and export drivers call
these primitives so that the science rules stay unit-testable and
identical between metadata planning and byte production.

Hard rules encoded here (Issue #13 + AGENTS.md):
* cells are chosen ONLY from label composition (SILVER fraction,
  SILVER/WEAK diagnostic disagreement, unlabeled coastal control) --
  never from observed or expected model performance;
* selection is deterministic (explicit ranking + cell_id tiebreak) and
  every choice carries a written rationale;
* optical eligibility = same-DATATAKE group, actual per-scene
  geometries, union coverage >= 0.99 and contributing-scene scene-level
  cloud <= 0.30; cross-date grouping is impossible because the key is
  the real datatake identifier;
* Sentinel-1 events stay strictly single-scene; ASCENDING and
  DESCENDING passes are never mixed;
* Sentinel-1 GRD bands are already decibels: the science transform is
  the identity, never 10*log10.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

PILOT_BAY_ID: Final[str] = "ZJ-HZB"
PILOT_YEAR: Final[int] = 2022
AUTUMN_PRIMARY_V1_DOY_START: Final[int] = 260
AUTUMN_PRIMARY_V1_DOY_END: Final[int] = 320
SEASON_POLICY_ID: Final[str] = "autumn_primary_v1_PROPOSED_NOT_FROZEN"
CELL_SIZE_M: Final[int] = 10_000

COVERAGE_MIN: Final[float] = 0.99
SCENE_CLOUD_MAX: Final[float] = 0.30

STRATUM_HIGH_SILVER: Final[str] = "HIGH_SILVER_FRACTION"
STRATUM_MEDIUM_SILVER: Final[str] = "MEDIUM_SILVER_FRACTION"
STRATUM_LOW_SILVER: Final[str] = "LOW_SILVER_FRACTION"
STRATUM_VERY_LOW_SILVER: Final[str] = "VERY_LOW_SILVER_FRACTION"
STRATUM_DISAGREEMENT: Final[str] = "SILVER_WEAK_DISAGREEMENT"
STRATUM_UNLABELED: Final[str] = "UNLABELED_COASTAL_CONTROL"

#: Plausible observed sigma0 decibel envelope for COPERNICUS/S1_GRD over
#: coastal 10 km cells that include intertidal flat, open water AND
#: developed shoreline/ports (VV corner-reflector returns over buildings
#: and ships can reach roughly +20..+25 dB). Used as a byte-level sanity
#: range only -- values outside it fail validation; it is not a rescaling
#: op. The decisive identity check is the independent GEE-side recompute
#: of the same percentiles in the export driver, not this envelope.
S1_DB_OBSERVED_MIN: Final[float] = -50.0
S1_DB_OBSERVED_MAX: Final[float] = 30.0


@dataclass(frozen=True)
class CellLabelSummary:
    """Label composition of one 10 km cell measured on the bay clip."""

    cell_id: str
    bay_clip_area_km2: float
    silver_area_km2: float
    silver_fraction: float
    silver_positive: bool
    any_weak_positive: bool
    weak_max_area_km2: float
    silver_status: str
    coastal_relevance: str
    s2_quality_event_2022_autumn_in_v0_1: bool

    @property
    def unlabeled(self) -> bool:
        return not self.silver_positive and not self.any_weak_positive


@dataclass(frozen=True)
class CellChoice:
    cell_id: str
    stratum: str
    rank_metric: str
    rank_value: float
    rationale: str
    label: CellLabelSummary


@dataclass(frozen=True)
class SceneCoverage:
    """One scene's ACTUAL measured coverage of one cell."""

    scene_id: str
    utc: str
    doy: int
    coverage_fraction: float
    cloud_fraction: float | None
    mgrs_tile: str | None = None
    datatake_identifier: str | None = None
    pass_direction: str | None = None
    relative_orbit: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventEligibility:
    cell_id: str
    sensor: str
    event_key: str
    event_utc: str
    doy: int
    member_scene_ids: tuple[str, ...]
    member_tiles: tuple[str, ...]
    coverage_fraction: float
    contributing_cloud_max: float | None
    coverage_gate: bool
    cloud_gate: str
    eligible: bool
    multi_tile: bool = False
    pass_direction: str | None = None
    relative_orbit: int | None = None


def summarize_cell_labels(
    *,
    cell_id: str,
    overlap_rows: list[dict[str, Any]],
    coastal_relevance: str,
    s2_quality_event_in_v0_1: bool,
) -> CellLabelSummary:
    """Aggregate the v0_1 per-asset overlap rows for one 10 km cell.

    WEAK area is reported as the MAXIMUM over the audited WEAK products,
    never the sum (the products overlap and would double-count). The
    UNLABELED decision requires SILVER absent AND every WEAK product
    absent on the bay clip.
    """
    bay_clip = 0.0
    silver_area = 0.0
    silver_fraction = 0.0
    silver_status = "UNLABELED"
    weak_areas: list[float] = []
    for row in overlap_rows:
        if int(row["cell_size_m"]) != CELL_SIZE_M:
            continue
        bay_clip = max(bay_clip, float(row.get("bay_clip_area_km2") or 0.0))
        area = float(row.get("positive_area_km2_bay_clip") or 0.0)
        if str(row.get("label_tier")) == "SILVER":
            silver_area = max(silver_area, area)
            silver_fraction = max(
                silver_fraction,
                float(row.get("overlap_fraction_of_bay_clip") or 0.0))
            status = str(row.get("cell_label_status_bay_scoped") or "")
            if status:
                silver_status = status
        elif str(row.get("label_tier")) == "WEAK":
            weak_areas.append(area)
    weak_max = max(weak_areas, default=0.0)
    return CellLabelSummary(
        cell_id=cell_id,
        bay_clip_area_km2=round(bay_clip, 6),
        silver_area_km2=round(silver_area, 6),
        silver_fraction=round(silver_fraction, 6),
        silver_positive=silver_area > 0.0,
        any_weak_positive=weak_max > 0.0,
        weak_max_area_km2=round(weak_max, 6),
        silver_status=silver_status,
        coastal_relevance=coastal_relevance,
        s2_quality_event_2022_autumn_in_v0_1=s2_quality_event_in_v0_1)


def select_pilot_cells(
    summaries: dict[str, CellLabelSummary],
    disagreement: dict[str, dict[str, Any]],
) -> list[CellChoice]:
    """Deterministic stratified selection of 6-8 HZB 10 km cells.

    Fixed rules, in order; each rule only fills slots still empty:

    1. HIGH    -- highest SILVER bay-clip fraction (1 cell);
    2. MEDIUM  -- next two ranks by SILVER fraction (2 cells);
    3. LOW     -- next SILVER-positive rank (1 cell);
    4. DISAGREE-- SILVER/WEAK diagnostic cell with the LOWEST Jaccard,
                  if not already chosen (1 cell);
    5. DISAGREE2-- next-lowest-Jaccard diagnostic cell not chosen
                  (captures partial disagreement at larger support);
    6. VERY LOW-- smallest positive SILVER fraction among cells that the
                  corrected v0_1 artifact already shows carrying a
                  quality 2022 autumn S2 event (pilot-eligibility
                  constraint, not model performance);
    7. UNLABELED-- largest bay-clip coastal cell with SILVER absent and
                  every WEAK product absent, likewise requiring an
                  existing v0_1 quality S2 event so the control cell is
                  observable under the current contract.

    Every ranking key ends with the lexical cell_id, so the output is a
    pure function of the tracked manifests.
    """
    chosen: list[CellChoice] = []
    chosen_ids: set[str] = set()

    def take(cell_id: str, stratum: str, metric: str, value: float,
             why: str) -> None:
        if cell_id in chosen_ids:
            return
        chosen.append(CellChoice(
            cell_id=cell_id, stratum=stratum, rank_metric=metric,
            rank_value=round(value, 6), rationale=why,
            label=summaries[cell_id]))
        chosen_ids.add(cell_id)

    silver = sorted(
        (s for s in summaries.values() if s.silver_positive),
        key=lambda s: (-s.silver_fraction, s.cell_id))

    def silver_rank_label(rank: int) -> str:
        return f"rank {rank} of {len(silver)} SILVER-positive cells"

    if silver:
        hi = silver[0]
        take(hi.cell_id, STRATUM_HIGH_SILVER, "silver_fraction_desc",
             hi.silver_fraction,
             f"maximum SILVER bay-clip fraction; {silver_rank_label(1)}")
    for rank, med in enumerate(silver[1:3], start=2):
        take(med.cell_id, STRATUM_MEDIUM_SILVER,
             "silver_fraction_desc", med.silver_fraction,
             f"medium SILVER fraction; {silver_rank_label(rank)}")
    if len(silver) >= 4:
        lo = silver[3]
        take(lo.cell_id, STRATUM_LOW_SILVER, "silver_fraction_desc",
             lo.silver_fraction,
             f"low SILVER fraction; {silver_rank_label(4)}")

    diag = sorted(
        (d for cid, d in disagreement.items() if cid in summaries),
        key=lambda d: (float(d["jaccard"]), str(d.get("cell_id"))))
    if diag:
        d0 = diag[0]
        cid = str(d0["cell_id"])
        take(cid, STRATUM_DISAGREEMENT, "jaccard_asc",
             float(d0["jaccard"]),
             "lowest SILVER/WEAK diagnostic Jaccard over bay clip "
             f"({d0['silver_only_px']} SILVER-only / "
             f"{d0['weak_only_px']} WEAK-only px); diagnostic layer is "
             "not relabeling and neither tier changes")
    if len(diag) >= 2:
        for d in diag[1:]:
            cid = str(d["cell_id"])
            if cid not in chosen_ids:
                take(cid, STRATUM_DISAGREEMENT, "jaccard_asc",
                     float(d["jaccard"]),
                     "second-lowest diagnostic Jaccard; partial-agreement "
                     "cell with substantial support on both tiers")
                break

    observable_positive = sorted(
        (s for s in silver
         if s.s2_quality_event_2022_autumn_in_v0_1 and s.cell_id
         not in chosen_ids),
        key=lambda s: (s.silver_fraction, s.cell_id))
    if observable_positive:
        vlo = observable_positive[0]
        take(vlo.cell_id, STRATUM_VERY_LOW_SILVER, "silver_fraction_asc",
             vlo.silver_fraction,
             "smallest positive SILVER fraction among cells with an "
             "existing corrected v0_1 quality 2022 autumn S2 event; "
             "tests sparse-positive handling")

    controls = sorted(
        (s for s in summaries.values()
         if s.unlabeled and s.coastal_relevance == "COASTAL_RELEVANT"
         and s.s2_quality_event_2022_autumn_in_v0_1
         and s.cell_id not in chosen_ids
         and s.bay_clip_area_km2 > 0.0),
        key=lambda s: (-s.bay_clip_area_km2, s.cell_id))
    if controls:
        ctl = controls[0]
        take(ctl.cell_id, STRATUM_UNLABELED, "bay_clip_area_desc",
             ctl.bay_clip_area_km2,
             "largest-bay-clip coastal cell with SILVER absent and all "
             "WEAK products absent; UNLABELED control, never NEGATIVE")

    return chosen


def evaluate_optical_group(
    *, cell_id: str, sensor: str, group_key: str,
    scenes: list[SceneCoverage], union_coverage: float,
) -> EventEligibility:
    """Apply coverage + contributing-scene cloud gates to one group."""
    if not scenes:
        raise ValueError("optical group must contain >=1 scene")
    # R1 semantics (identical to the v0_1 simulator): a contributing
    # scene is any member whose ACTUAL geometry intersects the cell at
    # all; the 0.99 gate applies to the group UNION coverage only.
    contributing = tuple(s for s in scenes if s.coverage_fraction > 0.0)
    coverage_gate = union_coverage + 1e-12 >= COVERAGE_MIN
    clouds = [s.cloud_fraction for s in contributing]
    if not contributing:
        cloud_gate = "NO_CONTRIBUTING_SCENE"
        cloud_max: float | None = None
        eligible = False
    elif any(c is None for c in clouds):
        cloud_gate = "MISSING_CLOUD_METADATA"
        cloud_max = None
        eligible = False
    else:
        cloud_max = max(float(c) for c in clouds)  # type: ignore[arg-type]
        cloud_gate = "PASS" if cloud_max <= SCENE_CLOUD_MAX else "FAIL"
        eligible = coverage_gate and cloud_gate == "PASS"
    scenes_sorted = sorted(scenes, key=lambda s: s.scene_id)
    tiles = tuple(sorted({s.mgrs_tile for s in contributing
                          if s.mgrs_tile}))
    first = min(scenes_sorted, key=lambda s: (s.utc, s.scene_id))
    return EventEligibility(
        cell_id=cell_id, sensor=sensor, event_key=group_key,
        event_utc=first.utc, doy=first.doy,
        member_scene_ids=tuple(s.scene_id for s in scenes_sorted),
        member_tiles=tiles, coverage_fraction=round(union_coverage, 6),
        contributing_cloud_max=(
            round(cloud_max, 6) if cloud_max is not None else None),
        coverage_gate=coverage_gate, cloud_gate=cloud_gate,
        eligible=eligible, multi_tile=len(tiles) > 1)


def pick_primary_s2_event(
    events: list[EventEligibility],
) -> EventEligibility | None:
    """Clearest eligible S2 event; ties by earliest UTC then event key."""
    ok = [e for e in events if e.eligible]
    if not ok:
        return None
    return sorted(
        ok, key=lambda e: (
            float(e.contributing_cloud_max or 0.0),
            e.event_utc, e.event_key))[0]


def pick_extra_multitile_event(
    events: list[EventEligibility], exclude_keys: set[str],
) -> EventEligibility | None:
    """Clearest eligible same-datatake multi-tile event, if encountered."""
    ok = [e for e in events
          if e.eligible and e.multi_tile and e.event_key not in exclude_keys]
    if not ok:
        return None
    return sorted(
        ok, key=lambda e: (
            float(e.contributing_cloud_max or 0.0),
            e.event_utc, e.event_key))[0]


def first_eligible(
    scenes: list[SceneCoverage],
) -> SceneCoverage | None:
    """Earliest eligible single-scene event (Landsat), deterministic."""
    ok = [s for s in scenes
          if s.coverage_fraction + 1e-12 >= COVERAGE_MIN
          and s.cloud_fraction is not None
          and float(s.cloud_fraction) <= SCENE_CLOUD_MAX]
    if not ok:
        return None
    return sorted(ok, key=lambda s: (s.utc, s.scene_id))[0]


def first_s1_per_pass(
    scenes: list[SceneCoverage],
) -> dict[str, SceneCoverage]:
    """Earliest eligible actual-geometry IW scene per orbit direction."""
    out: dict[str, SceneCoverage] = {}
    for pass_dir in ("ASCENDING", "DESCENDING"):
        ok = [s for s in scenes
              if s.pass_direction == pass_dir
              and s.coverage_fraction + 1e-12 >= COVERAGE_MIN]
        if ok:
            out[pass_dir] = sorted(
                ok, key=lambda s: (s.utc, s.scene_id))[0]
    return out


def s1_db_audit(stats: dict[str, float]) -> dict[str, Any]:
    """Decide whether observed VV/VH statistics look like dB values.

    The GEE S1_GRD product is already sigma0 in dB; exports must be the
    identity transform. This audit only checks that observed extrema sit
    inside a physically plausible decibel envelope -- it never rescales.
    """
    checks: dict[str, bool] = {}
    for band in ("VV", "VH"):
        obs_min = float(stats[f"{band}_min"])
        obs_max = float(stats[f"{band}_max"])
        checks[f"{band}_within_db_envelope"] = (
            obs_min >= S1_DB_OBSERVED_MIN and obs_max <= S1_DB_OBSERVED_MAX)
        checks[f"{band}_ordered_percentiles"] = (
            obs_min <= float(stats[f"{band}_p01"])
            <= float(stats[f"{band}_p50"])
            <= float(stats[f"{band}_p99"]) <= obs_max)
    return {
        "expected_units": "sigma0 dB (COPERNICUS/S1_GRD pre-converted)",
        "transform_applied": "IDENTITY_SELECT_ONLY_NO_10LOG10",
        "plausible_envelope_db": [S1_DB_OBSERVED_MIN, S1_DB_OBSERVED_MAX],
        "stats": dict(stats),
        "checks": checks,
        "pass": all(checks.values()),
    }


__all__ = [
    "AUTUMN_PRIMARY_V1_DOY_END",
    "AUTUMN_PRIMARY_V1_DOY_START",
    "CELL_SIZE_M",
    "COVERAGE_MIN",
    "CellChoice",
    "CellLabelSummary",
    "EventEligibility",
    "PILOT_BAY_ID",
    "PILOT_YEAR",
    "SCENE_CLOUD_MAX",
    "STRATUM_DISAGREEMENT",
    "STRATUM_HIGH_SILVER",
    "STRATUM_LOW_SILVER",
    "STRATUM_MEDIUM_SILVER",
    "STRATUM_UNLABELED",
    "STRATUM_VERY_LOW_SILVER",
    "SceneCoverage",
    "SEASON_POLICY_ID",
    "evaluate_optical_group",
    "first_eligible",
    "first_s1_per_pass",
    "pick_extra_multitile_event",
    "pick_primary_s2_event",
    "s1_db_audit",
    "select_pilot_cells",
    "summarize_cell_labels",
]
