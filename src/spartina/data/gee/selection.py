"""Deterministic ``best_single_scene`` selection policy.

Issue #6 deliberately forbids starting with a median composite: the first
factory product is one verified scene per time/ROI, and every rejected
candidate stays in the table. This module ranks candidate rows
(:meth:`CandidateScene.to_record` shape plus a ``quality_extras`` dict)
with an explicit, explainable lexicographic key -- no learned fitting, no
threshold tuning on evaluation labels.

Ranking (most important first):
    1. ROI footprint coverage (higher better)
    2. ROI valid/observed pixel fraction (higher better)
    3. ROI cloud fraction (lower better; falls back to catalog cloud)
    4. circular distance of acquisition day-of-year to the target window
    5. acquisition time, then scene id (deterministic tie-break)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: Rejection reason labels written into the candidate table.
REASON_UNKNOWN_COVERAGE: str = "unknown_footprint_coverage"
REASON_LOW_COVERAGE: str = "low_footprint_coverage"
REASON_LOW_VALID: str = "low_valid_pixel_fraction"
REASON_HIGH_CLOUD: str = "high_roi_cloud_fraction"


@dataclass(frozen=True)
class SingleScenePolicy:
    """Acceptance thresholds for the best-single-scene policy."""

    min_footprint_coverage: float = 0.99
    min_valid_pixel_fraction: float = 0.95
    max_cloud_fraction: float = 0.30
    #: Target day-of-year for seasonal consistency; None disables ranking 4.
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


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def roi_cloud_fraction(record: dict[str, object]) -> float | None:
    """ROI raster cloud fraction, falling back to catalog scene cloud."""
    extras = record.get("quality_extras")
    if isinstance(extras, dict):
        value = _as_float(extras.get("roi_cloud_fraction"))
        if value is not None:
            return value
    return _as_float(record.get("cloud_cover_fraction"))


def rejection_reasons(
    record: dict[str, object], policy: SingleScenePolicy,
) -> tuple[str, ...]:
    """Explain why a candidate is not selectable under ``policy``."""
    reasons: list[str] = []
    coverage = _as_float(record.get("footprint_coverage_fraction"))
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
) -> tuple[float, float, float, float, str, str]:
    """Sort key for accepted candidates (sort descending on this tuple).

    Callers use ``sorted(rows, key=lambda r: rank_key(r, p), reverse=True)``
    """
    coverage = _as_float(record.get("footprint_coverage_fraction")) or 0.0
    valid = _as_float(record.get("valid_pixel_fraction")) or 0.0
    cloud = roi_cloud_fraction(record)
    cloud_score = -cloud if cloud is not None else 0.0
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
        float(season),
        str(record.get("acquisition_utc") or ""),
        str(record.get("scene_id") or ""),
    )


def best_single_scene(
    records: list[dict[str, object]], policy: SingleScenePolicy,
) -> dict[str, object] | None:
    """Return the best selectable scene record, or None if none qualifies.

    A record is selectable only when already accepted by upstream QA and
    :func:`rejection_reasons` is empty. The decision is deterministic.
    """
    eligible = [
        record for record in records
        if bool(record.get("accepted"))
        and not rejection_reasons(record, policy)]
    if not eligible:
        return None
    eligible.sort(key=lambda r: rank_key(r, policy), reverse=True)
    return eligible[0]


__all__ = [
    "REASON_HIGH_CLOUD",
    "REASON_LOW_COVERAGE",
    "REASON_LOW_VALID",
    "REASON_UNKNOWN_COVERAGE",
    "SingleScenePolicy",
    "best_single_scene",
    "circular_doy_distance",
    "rank_key",
    "rejection_reasons",
    "roi_cloud_fraction",
]
