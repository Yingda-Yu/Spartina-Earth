"""Scene catalog query interfaces (M0 contracts + in-memory mock)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Protocol


@dataclass(frozen=True)
class Region:
    """Query region as GeoJSON geometry plus an EPSG code."""

    geometry: dict[str, object]
    crs_epsg: int


@dataclass(frozen=True)
class SceneQuery:
    """Parameters for a catalog query."""

    sensor_name: str
    start_date: str  # ISO YYYY-MM-DD
    end_date: str
    region: Region
    max_cloud_cover: float | None = None  # fraction 0..1, optical only
    limit: int | None = None


@dataclass(frozen=True)
class SceneMetadata:
    """Catalog-level metadata for one scene (no pixel data)."""

    scene_id: str
    sensor_name: str
    acquisition_time: str
    cloud_cover: float | None
    bbox: tuple[float, float, float, float]
    crs: str
    extra: dict[str, object] = field(default_factory=dict)


class CatalogClient(Protocol):
    """Interface every catalog backend implements."""

    def query(self, query: SceneQuery) -> list[SceneMetadata]:
        """Return matching scenes, newest or catalog order documented."""
        ...


class MockCatalogClient:
    """Deterministic in-memory catalog for unit tests and offline demos."""

    def __init__(self, scenes: tuple[SceneMetadata, ...] = ()) -> None:
        self._scenes = scenes
        self.calls: list[SceneQuery] = []

    def query(self, query: SceneQuery) -> list[SceneMetadata]:
        """Filter the fixture scenes by sensor and cloud threshold."""
        self.calls.append(query)
        result: list[SceneMetadata] = []
        for scene in self._scenes:
            if scene.sensor_name != query.sensor_name:
                continue
            if (
                query.max_cloud_cover is not None
                and scene.cloud_cover is not None
                and scene.cloud_cover > query.max_cloud_cover
            ):
                continue
            result.append(scene)
        if query.limit is not None:
            result = result[: query.limit]
        return result


#: Sentinel used by smoke-level tests / demos; empty production client is
#: intentionally absent in M0.
NO_NETWORK: Final[bool] = True


__all__ = [
    "CatalogClient",
    "MockCatalogClient",
    "Region",
    "SceneMetadata",
    "SceneQuery",
]
