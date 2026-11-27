"""Deterministic ``best_single_scene`` selection policy.

Issue #6 deliberately forbids starting with a median composite: the first
factory product is one verified scene per time/ROI, and every rejected
candidate stays in the table. This module ranks candidate rows
(:meth:`CandidateScene.to_record` shape, or the flat real-smoke row shape)
with an explicit, explainable lexicographic key -- no learned fitting, no
threshold tuning on evaluation labels.

Optical ranking (most important first):
    1. ROI footprint coverage (higher better)
    2. ROI valid/observed pixel fraction (higher better)
    3. ROI cloud fraction (lower better; falls back to catalog cloud)
    4. ROI cloud-shadow fraction (lower better)
    5. circular distance of acquisition day-of-year to the target window
    6. acquisition time, then scene id (deterministic tie-break)

Sentinel-1 has no optical cloud/shadow metrics; its ranks use coverage,
valid fraction and season only, and ASCENDING / DESCENDING passes are
ranked separately -- the two are never silently treated as equivalent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

#: Rejection reason labels written into the candidate table.
REASON_UNKNOWN_COVERAGE: str = "unknown_footprint_coverage"
REASON_LOW_COVERAGE: str = "low_footprint_coverage"
REASON_LOW_VALID: str = "low_valid_pixel_fraction"
REASON_HIGH_CLOUD: str = "high_roi_cloud_fraction"
REASON_SAR_NOT_IW: str = "sar_instrument_mode_not_iw"
REASON_SAR_MISSING_POLS: str = "sar_missing_vv_or_vh"


@dataclass(frozen=True)
class SingleScenePolicy:
    """Acceptance thresholds for the best-single-scene policy."""

    min_footprint_coverage: float = 0.99
    min_valid_pixel_fraction: float = 0.95
    max_cloud_fraction: float = 0.30
    #: Target day-of-year for seasonal consistency; None disables ranking 5.
    target_doy: int | None = None

    def __post_init__(self) -> None:
        if not 0.0 < self.min_footprint_coverage <= 1.0:
            raise ValueError("min_footprint_coverage must be within (0, 1]")
        if not 0.0 < self.min_valid_pixel_fraction <= 1.0:
            raise ValueError("min_valid_pixel_fraction must be within (0, 1]")
        if not 0.0 <= self.max_cloud_fraction <= 1.0:
            raise ValueError("max_cloud_fraction must be within [0, 1]")
        if self.target_doy is not None and not 1 <= self.target_doy <= 366:
            raise ValueError("target_doy must be within [1, 366]")

    def to_record(self) -> dict[str, float | int | None]:
        return {
            "min_footprint_coverage": self.min_footprint_coverage,
            "min_valid_pixel_fraction": self.min_valid_pixel_fraction,
            "max_cloud_fraction": self.max_cloud_fraction,
            "target_doy": self.target_doy,
        }


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _extras(record: dict[str, object]) -> dict[str, object]:
    nested = record.get("quality_extras")
    return dict(nested) if isinstance(nested, dict) else {}


def _field(record: dict[str, object], key: str) -> object:
    if key in record:
        return record[key]
    return _extras(record).get(key)


def footprint_coverage(record: dict[str, object]) -> float | None:
    """ROI coverage under either the candidate-row or flat smoke-row name."""
    for key in ("footprint_coverage_fraction", "roi_coverage_fraction",
                "roi_intersection_fraction"):
        value = _as_float(record.get(key))
        if value is not None:
            return value
    nested = _as_float(_extras(record).get("footprint_coverage_fraction"))
    return nested


def roi_cloud_fraction(record: dict[str, object]) -> float | None:
    """ROI raster cloud fraction, falling back to catalog scene cloud."""
    value = _as_float(_field(record, "roi_cloud_fraction"))
    if value is not None:
        return value
    return _as_float(record.get("cloud_cover_fraction"))


def roi_shadow_fraction(record: dict[str, object]) -> float | None:
    """ROI raster cloud-shadow fraction (optical only; None for SAR)."""
    return _as_float(_field(record, "roi_shadow_fraction"))


def rejection_reasons(
    record: dict[str, object], policy: SingleScenePolicy,
) -> tuple[str, ...]:
    """Explain why a candidate is not selectable under ``policy``."""
    reasons: list[str] = []
    coverage = footprint_coverage(record)
    if coverage is None:
        reasons.append(REASON_UNKNOWN_COVERAGE)
    elif coverage < policy.min_footprint_coverage:
        reasons.append(REASON_LOW_COVERAGE)
    valid = _as_float(record.get("valid_pixel_fraction"))
    if valid is None or valid < policy.min_valid_pixel_fraction:
        reasons.append(REASON_LOW_VALID)
    cloud = roi_cloud_fraction(record)
    if cloud is not None and cloud > policy.max_cloud_fraction:
        reasons.append(REASON_HIGH_CLOUD)
    return tuple(reasons)


def circular_doy_distance(doy_a: int, doy_b: int) -> int:
    """Day-of-year distance on the annual circle (max 182/183)."""
    direct = abs(doy_a - doy_b)
    return min(direct, 365 - direct)


def _acquisition_doy(record: dict[str, object]) -> int | None:
    raw = record.get("acquisition_utc")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timetuple().tm_yday
    except ValueError:
        return None


def rank_key(
    record: dict[str, object], policy: SingleScenePolicy,
) -> tuple[float, float, float, float, float, str, str]:
    """Sort key for accepted candidates (sort descending on this tuple).

    Callers use ``sorted(rows, key=lambda r: rank_key(r, p), reverse=True)``.
    SAR rows carry no cloud/shadow values; those components score as the
    neutral best (0.0) so SAR ranking collapses to coverage/valid/season.
    """
    coverage = footprint_coverage(record) or 0.0
    valid = _as_float(record.get("valid_pixel_fraction")) or 0.0
    cloud = roi_cloud_fraction(record)
    cloud_score = -cloud if cloud is not None else 0.0
    shadow = roi_shadow_fraction(record)
    shadow_score = -shadow if shadow is not None else 0.0
    if policy.target_doy is not None:
        doy = _acquisition_doy(record)
        season = (float(-circular_doy_distance(doy, policy.target_doy))
                  if doy is not None else -365.0)
    else:
        season = 0.0
    return (
        round(coverage, 6),
        round(valid, 6),
        round(cloud_score, 6),
        round(shadow_score, 6),
        float(season),
        str(record.get("acquisition_utc") or ""),
        str(record.get("scene_id") or ""),
    )


def selection_score(
    record: dict[str, object], policy: SingleScenePolicy,
) -> list[float | str]:
    """JSON-serializable ranking components (same order as ``rank_key``)."""
    return list(rank_key(record, policy))


def _eligible(
    record: dict[str, object], policy: SingleScenePolicy,
) -> bool:
    if not bool(record.get("accepted")):
        return False
    extra = record.get("rejection_reasons")
    if isinstance(extra, list) and extra:
        return False
    return not rejection_reasons(record, policy)


def rank_eligibles(
    records: list[dict[str, object]],
    policy: SingleScenePolicy,
    *,
    orbit: str | None = None,
) -> list[dict[str, object]]:
    """Return policy-eligible records with deterministic rank annotations.

    Each returned record gets ``selection_rank`` (1-based),
    ``selection_score`` and ``selection_reason``. ``orbit`` restricts the
    pool to one Sentinel-1 pass (ASCENDING / DESCENDING); the two passes
    must be ranked independently rather than silently merged.
    """
    pool = [dict(record) for record in records]
    if orbit is not None:
        pool = [r for r in pool
                if str(r.get("orbit_direction")) == orbit]
    eligible = [r for r in pool if _eligible(r, policy)]
    eligible.sort(key=lambda r: rank_key(r, policy), reverse=True)
    reason = ("rank order: coverage > valid_pixel_fraction > "
              "roi_cloud_fraction > roi_shadow_fraction > circular DOY "
              f"{policy.target_doy} > acquisition_utc > scene_id"
              if orbit is None else
              "rank order within SAR pass: coverage > valid_pixel_fraction "
              f"> circular DOY {policy.target_doy} > acquisition_utc > "
              "scene_id")
    for rank, record in enumerate(eligible, start=1):
        record["selection_rank"] = rank
        record["selection_score"] = selection_score(record, policy)
        record["selection_reason"] = reason
    return eligible


def best_single_scene(
    records: list[dict[str, object]], policy: SingleScenePolicy,
) -> dict[str, object] | None:
    """Return the best selectable scene record, or None if none qualifies.

    A record is selectable only when already accepted by upstream QA and
    :func:`rejection_reasons` is empty. The decision is deterministic.
    """
    ranked = rank_eligibles(records, policy)
    return ranked[0] if ranked else None


def best_per_sar_pass(
    records: list[dict[str, object]], policy: SingleScenePolicy,
) -> dict[str, dict[str, object] | None]:
    """Best eligible Sentinel-1 scene per orbit pass (kept separate)."""
    out: dict[str, dict[str, object] | None] = {}
    for orbit in ("ASCENDING", "DESCENDING"):
        ranked = rank_eligibles(records, policy, orbit=orbit)
        out[orbit] = ranked[0] if ranked else None
    return out


def canonical_fingerprint(payload: Any) -> str:
    """Stable SHA-256 over a canonical JSON encoding of ``payload``."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


__all__ = [
    "REASON_HIGH_CLOUD",
    "REASON_LOW_COVERAGE",
    "REASON_LOW_VALID",
    "REASON_SAR_MISSING_POLS",
    "REASON_SAR_NOT_IW",
    "REASON_UNKNOWN_COVERAGE",
    "SingleScenePolicy",
    "best_per_sar_pass",
    "best_single_scene",
    "canonical_fingerprint",
    "circular_doy_distance",
    "footprint_coverage",
    "rank_eligibles",
    "rank_key",
    "rejection_reasons",
    "roi_cloud_fraction",
    "roi_shadow_fraction",
    "selection_score",
]
