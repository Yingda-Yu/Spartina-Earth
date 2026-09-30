"""Scene catalog query interfaces (M0 contracts + in-memory mock)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Protocol


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
    bbox: tuple[float, ...]
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


def epoch_ms_to_iso(epoch_ms: object) -> str | None:
    """Convert GEE ``system:time_start`` milliseconds to UTC ISO 8601."""
    if not isinstance(epoch_ms, int | float):
        return None
    from datetime import datetime, timezone

    # timezone.utc keeps this importable on Python 3.10 minimal envs
    return datetime.fromtimestamp(
        float(epoch_ms) / 1000.0, tz=timezone.utc).isoformat()  # noqa: UP017


# Per-sensor property mappers and collection builders live in dedicated
# modules; this dict is resolved lazily so importing catalog never pulls
# Earth Engine into the process.
def _sensor_mapper(sensor_name: str) -> Any:
    if sensor_name.startswith("landsat"):
        from spartina.data.gee import landsat
        return landsat
    if sensor_name == "sentinel2":
        from spartina.data.gee import sentinel2
        return sentinel2
    if sensor_name == "sentinel1":
        from spartina.data.gee import sentinel1
        return sentinel1
    raise KeyError(f"no GEE catalog mapper for sensor {sensor_name!r}")


class EarthEngineCatalogClient:
    """Real GEE catalog backend.

    Earth Engine is imported lazily and only when a query is executed, so
    the module imports without credentials and without ``earthengine-api``
    installed (operations then raise a clear RuntimeError; integration
    tests skip via the ``gee_integration`` marker).
    """

    def __init__(self, *, compute_footprint_coverage: bool = True,
                 max_error_m: float = 30.0) -> None:
        self.compute_footprint_coverage = compute_footprint_coverage
        self.max_error_m = max_error_m
        self._ee: Any | None = None

    def _ee_module(self) -> Any:
        if self._ee is None:
            try:
                import ee
            except ImportError as exc:
                raise RuntimeError(
                    "earthengine-api is not installed and/or no "
                    "credentials are configured; real catalog queries are "
                    "BLOCKED_BY_AUTH (see gee_integration marker)") from exc
            from spartina.data.gee.auth import credentials_available, initialize

            if not credentials_available():
                raise RuntimeError(
                    "GEE credentials unavailable: real catalog query "
                    "BLOCKED_BY_AUTH")
            initialize()
            self._ee = ee
        return self._ee

    @staticmethod
    def _region_geometry(ee: Any, region: Region) -> Any:
        return ee.Geometry(region.geometry, f"EPSG:{region.crs_epsg}",
                           False)

    def query(self, query: SceneQuery) -> list[SceneMetadata]:
        """Return *all* matching scenes as SceneMetadata (no auto-pick).

        The caller is expected to persist every returned scene as a
        candidate row; selection happens explicitly in the quality stage.
        """
        ee = self._ee_module()
        mapper = _sensor_mapper(query.sensor_name)
        roi = self._region_geometry(ee, query.region)
        kwargs: dict[str, object] = {}
        if query.sensor_name != "sentinel1":
            kwargs["max_cloud_cover"] = query.max_cloud_cover
        collection = mapper.load_collection(
            ee, roi, query.start_date, query.end_date, **kwargs)
        if self.compute_footprint_coverage:
            roi_area = roi.area(self.max_error_m)
            collection = collection.map(
                lambda image: _annotate_coverage(
                    image, roi, roi_area, self.max_error_m))
        if query.limit is not None:
            collection = collection.limit(int(query.limit))
        features = collection.getInfo().get("features", [])
        scenes: list[SceneMetadata] = []
        for feature in features:
            props = dict(feature.get("properties", {}))
            record = mapper.record_from_properties(props)
            scenes.append(SceneMetadata(
                scene_id=str(record["scene_id"]),
                sensor_name=query.sensor_name,
                acquisition_time=(
                    epoch_ms_to_iso(record["acquisition_epoch_ms"]) or ""),
                cloud_cover=(record.get("cloud_cover_fraction")
                             or record.get("cloudy_pixel_fraction")),
                bbox=_bbox_from_feature(feature),
                crs=f"EPSG:{query.region.crs_epsg}",
                extra={
                    **{k: v for k, v in record.items()
                       if k not in ("scene_id", "acquisition_epoch_ms")
                       and v is not None},
                    "roi_coverage_fraction":
                        props.get("spartina_roi_coverage_fraction"),
                },
            ))
        return scenes


def _annotate_coverage(image: Any, roi: Any, roi_area: Any,
                       max_error_m: float) -> Any:
    """Attach ROI footprint coverage fraction to a scene image."""
    intersection = image.geometry(max_error_m).intersection(
        roi, max_error_m)
    coverage = intersection.area(max_error_m).divide(roi_area)
    return image.set("spartina_roi_coverage_fraction", coverage)


def _bbox_from_feature(feature: dict[str, object]) -> tuple[float, ...]:
    """Best-effort bbox (west, south, east, north) from a GEE feature."""
    geometry = feature.get("geometry")
    coords = geometry.get("coordinates") if isinstance(
        geometry, dict) else None
    if not coords:
        return ()
    flats: list[list[float]] = []

    def walk(node: object) -> None:
        if (isinstance(node, list | tuple) and node
                and isinstance(node[0], int | float)):
            flats.append(list(node))
        elif isinstance(node, list | tuple):
            for child in node:
                walk(child)

    walk(coords)
    if not flats:
        return ()
    xs = [p[0] for p in flats]
    ys = [p[1] for p in flats]
    return (min(xs), min(ys), max(xs), max(ys))


__all__ = [
    "CatalogClient",
    "EarthEngineCatalogClient",
    "MockCatalogClient",
    "NO_NETWORK",
    "Region",
    "SceneMetadata",
    "SceneQuery",
    "epoch_ms_to_iso",
]
