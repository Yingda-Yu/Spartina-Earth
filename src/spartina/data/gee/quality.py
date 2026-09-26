"""Quality-filter interfaces for catalog scenes (M0 contracts).

Concrete per-sensor QA decoding (Landsat QA_PIXEL bit unpacking, Sentinel-2
SCL classes, cloud-probability thresholds, SLC-off gap policy) is an M1
implementation behind these predicates; M0 provides the interface and one
simple metadata-level filter used by mocked tests.
"""

from __future__ import annotations

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


__all__ = ["CloudCoverFilter", "QAFilter", "apply_filters"]
