"""Quality-filter interfaces for catalog scenes (M0 contracts).

Concrete per-sensor QA decoding (Landsat QA_PIXEL bit unpacking, Sentinel-2
SCL classes, cloud-probability thresholds, SLC-off gap policy) is an M1
implementation behind these predicates; M0 provides the interface and one
simple metadata-level filter used by mocked tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from spartina.data.gee.catalog import SceneMetadata


class QAFilter(Protocol):
    """A predicate deciding whether a scene passes quality criteria."""

    def accept(self, scene: SceneMetadata) -> bool:
        """Return True when the scene is acceptable for downstream use."""
        ...


class CloudCoverFilter:
    """Reject optical scenes whose catalog cloud fraction exceeds a limit."""

    def __init__(self, max_cloud_cover: float) -> None:
        if not 0.0 <= max_cloud_cover <= 1.0:
            raise ValueError("max_cloud_cover must be within [0, 1]")
        self.max_cloud_cover = max_cloud_cover

    def accept(self, scene: SceneMetadata) -> bool:
        """Pass scenes with no cloud value or with cloud at/under the cap."""
        if scene.cloud_cover is None:
            return True
        return scene.cloud_cover <= self.max_cloud_cover


def apply_filters(scenes: list[SceneMetadata], filters: list[QAFilter]) -> list[SceneMetadata]:
    """Return the scenes accepted by every filter."""
    return [scene for scene in scenes if all(rule.accept(scene) for rule in filters)]


@dataclass(frozen=True)
class CandidateScene:
    """One row of the candidate-scene table.

    Every catalogued scene is retained — rejected scenes are flagged via
    ``accepted``/``rejection_reasons`` rather than silently dropped, and
    the chosen scene is explicit. Pixel-level quality (valid fraction)
    comes from the raster QC pass and stays ``None`` until computed.
    """

    scene: SceneMetadata
    footprint_coverage_fraction: float | None
    valid_pixel_fraction: float | None
    quality_extras: dict[str, object]
    accepted: bool
    rejection_reasons: tuple[str, ...]
    selected: bool = False

    def to_record(self) -> dict[str, object]:
        """Flat JSON-serializable candidate row."""
        return {
            "scene_id": self.scene.scene_id,
            "product_id": self.scene.extra.get("product_id"),
            "sensor": self.scene.sensor_name,
            "acquisition_utc": self.scene.acquisition_time,
            "cloud_cover_fraction": self.scene.cloud_cover,
            "footprint_coverage_fraction": self.footprint_coverage_fraction,
            "valid_pixel_fraction": self.valid_pixel_fraction,
            "orbit_direction": self.scene.extra.get("orbit_direction"),
            "relative_orbit_number": self.scene.extra.get(
                "relative_orbit_number"),
            "mgrs_tile": self.scene.extra.get("mgrs_tile"),
            "wrs_path": self.scene.extra.get("wrs_path"),
            "wrs_row": self.scene.extra.get("wrs_row"),
            "accepted": self.accepted,
            "selected": self.selected,
            "rejection_reasons": list(self.rejection_reasons),
            "quality_extras": dict(self.quality_extras),
        }


class CoverageFilter:
    """Reject scenes whose ROI coverage is below a required fraction."""

    def __init__(self, min_coverage: float) -> None:
        if not 0.0 < min_coverage <= 1.0:
            raise ValueError("min_coverage must be within (0, 1]")
        self.min_coverage = min_coverage

    def accept(
        self, coverage_fraction: float | None,
    ) -> bool:
        """Unknown coverage never auto-passes a coverage requirement."""
        return (coverage_fraction is not None
                and coverage_fraction >= self.min_coverage)


def build_candidate_table(
    scenes: list[SceneMetadata],
    accepted_scene_ids: frozenset[str],
    *,
    coverage_by_scene: dict[str, float] | None = None,
    pixel_quality_by_scene: dict[str, dict[str, object]] | None = None,
    selected_scene_id: str | None = None,
) -> list[CandidateScene]:
    """Build the full candidate table — rejected scenes stay visible.

    Raises if a selected/accepted id is not among the candidates, so a
    chosen scene can never reference a non-catalogued acquisition.
    """
    coverage_by_scene = coverage_by_scene or {}
    pixel_quality_by_scene = pixel_quality_by_scene or {}
    ids = {scene.scene_id for scene in scenes}
    if not accepted_scene_ids <= ids:
        raise KeyError(
            f"accepted ids not in candidates: {sorted(accepted_scene_ids - ids)}")
    if selected_scene_id is not None and selected_scene_id not in ids:
        raise KeyError(f"selected scene {selected_scene_id!r} is not a candidate")
    rows: list[CandidateScene] = []
    for scene in scenes:
        accepted = scene.scene_id in accepted_scene_ids
        coverage = coverage_by_scene.get(scene.scene_id)
        pixel_quality = pixel_quality_by_scene.get(scene.scene_id, {})
        valid_fraction = pixel_quality.get("valid_pixel_fraction")
        valid_fraction = (float(valid_fraction)
                          if isinstance(valid_fraction, int | float)
                          else None)
        reasons: list[str] = []
        if not accepted:
            reasons.append("failed_qa_or_metadata_filter")
        if coverage is not None and coverage < 1.0:
            reasons.append("partial_footprint_coverage")
        rows.append(CandidateScene(
            scene=scene,
            footprint_coverage_fraction=coverage,
            valid_pixel_fraction=valid_fraction,
            quality_extras=dict(pixel_quality),
            accepted=accepted,
            rejection_reasons=tuple(reasons),
            selected=scene.scene_id == selected_scene_id))
    if selected_scene_id is not None:
        chosen = next(r for r in rows if r.selected)
        if not chosen.accepted:
            raise ValueError("selected scene was not accepted by QA")
    return rows


def candidate_records(rows: list[CandidateScene]) -> list[dict[str, object]]:
    """Serialize a candidate table."""
    return [row.to_record() for row in rows]


__all__ = [
    "CandidateScene",
    "CloudCoverFilter",
    "CoverageFilter",
    "QAFilter",
    "apply_filters",
    "build_candidate_table",
    "candidate_records",
]
