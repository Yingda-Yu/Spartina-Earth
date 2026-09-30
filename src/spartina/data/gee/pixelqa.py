"""Real server-side pixel-quality fractions over an ROI.

The catalog :class:`~spartina.data.gee.quality.CandidateScene` distinguishes
catalog-level cloud metadata from *ROI-level* raster quality: how much of
this exact ROI the scene observed, how much is cloud/shadow/snow there.
These functions compute those fractions inside Earth Engine via one
``reduceRegion`` per scene (mapped over the collection, one ``getInfo``),
so nothing about the answer is guessed from scene-wide metadata.

All Earth Engine usage stays lazy; importing this module without
credentials / earthengine-api is safe.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from spartina.data.gee.landsat import (
    QA_CIRRUS,
    QA_CLOUD,
    QA_CLOUD_SHADOW,
    QA_DILATED_CLOUD,
    QA_FILL,
    QA_SNOW,
)

#: Fraction of the ROI observed by the sensor (mask present / SCL nonzero).
VALID_KEY: str = "valid_pixel_fraction"
#: Fraction of the ROI flagged cloud/shadow/cirrus/snow (optical only).
CLOUD_KEY: str = "roi_cloud_fraction"
#: Fraction of the ROI passing the same clear rule used for masking.
CLEAR_KEY: str = "clear_pixel_fraction"


def _fraction_table(
    ee: Any,
    collection: Any,
    roi: Any,
    mask_builder: Callable[[Any, Any], Any],
    band_names: tuple[str, ...],
    scale_m: float,
    *,
    tile_scale: int = 4,
) -> dict[str, dict[str, float | None]]:
    """Map ``mask_builder`` over the collection and reduce means on the ROI.

    Returns ``{scene_id: {band: fraction or None}}``. Mask bands are
    explicitly ``unmask(0)`` before reducing so that fully masked pixels
    count as zero coverage instead of disappearing from the denominator.
    """

    def to_feature(image: Any) -> Any:
        masks = mask_builder(ee, image).unmask(0).select(list(band_names))
        stats = masks.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=float(scale_m),
            maxPixels=10_000_000,
            bestEffort=True,
            tileScale=int(tile_scale),
        )
        return ee.Feature(
            None, stats.set("scene_id", image.get("system:index")))

    features = collection.map(to_feature).getInfo().get("features", [])
    table: dict[str, dict[str, float | None]] = {}
    for feature in features:
        props = dict(feature.get("properties", {}))
        scene_id = props.pop("scene_id", None)
        if scene_id is None:
            continue
        table[str(scene_id)] = {
            key: (float(props[key]) if isinstance(
                props.get(key), int | float) else None)
            for key in band_names}
    return table


def landsat_mask_bands(ee: Any, image: Any) -> Any:
    """QA_PIXEL-based 0/1 bands: observed / cloud-flagged / fully clear."""
    qa = image.select("QA_PIXEL")
    radsat = image.select("QA_RADSAT")
    fill = qa.bitwiseAnd(1 << QA_FILL)
    observed = fill.eq(0)
    cloud = (
        qa.bitwiseAnd(1 << QA_DILATED_CLOUD).neq(0)
        .Or(qa.bitwiseAnd(1 << QA_CIRRUS).neq(0))
        .Or(qa.bitwiseAnd(1 << QA_CLOUD).neq(0))
        .Or(qa.bitwiseAnd(1 << QA_CLOUD_SHADOW).neq(0))
        .Or(qa.bitwiseAnd(1 << QA_SNOW).neq(0))
    )
    clear = (
        observed.And(cloud.Not())
        .And(qa.bitwiseAnd(1 << 6).neq(0))
        .And(radsat.eq(0))
    )
    return ee.Image.cat([
        observed.rename(VALID_KEY),
        cloud.rename(CLOUD_KEY),
        clear.rename(CLEAR_KEY),
    ])


def sentinel2_mask_bands(ee: Any, image: Any) -> Any:
    """SCL-based 0/1 bands: observed / cloud-flagged / clear-surface."""
    scl = image.select("SCL")
    observed = scl.mask()
    cloud = (
        scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10)))
    clear = (
        scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(11)))
    return ee.Image.cat([
        observed.rename(VALID_KEY),
        cloud.rename(CLOUD_KEY),
        clear.rename(CLEAR_KEY),
    ])


def sentinel1_mask_bands(ee: Any, image: Any) -> Any:
    """VV mask as per-pixel observation coverage for the ROI."""
    observed = image.select("VV").mask()
    return ee.Image.cat([observed.rename(VALID_KEY)])


def evaluate_landsat(
    ee: Any, collection: Any, roi: Any, *, scale_m: float = 30.0,
) -> dict[str, dict[str, float | None]]:
    """ROI fractions for every Landsat scene in ``collection``."""
    return _fraction_table(
        ee, collection, roi, landsat_mask_bands,
        (VALID_KEY, CLOUD_KEY, CLEAR_KEY), scale_m)


def evaluate_sentinel2(
    ee: Any, collection: Any, roi: Any, *, scale_m: float = 10.0,
) -> dict[str, dict[str, float | None]]:
    """ROI fractions for every S2 scene (SCL based; CLDPRB join is v1.1)."""
    return _fraction_table(
        ee, collection, roi, sentinel2_mask_bands,
        (VALID_KEY, CLOUD_KEY, CLEAR_KEY), scale_m)


def evaluate_sentinel1(
    ee: Any, collection: Any, roi: Any, *, scale_m: float = 10.0,
) -> dict[str, dict[str, float | None]]:
    """Per-pixel coverage fraction for every S1 scene."""
    return _fraction_table(
        ee, collection, roi, sentinel1_mask_bands, (VALID_KEY,), scale_m)


__all__ = [
    "CLEAR_KEY",
    "CLOUD_KEY",
    "VALID_KEY",
    "evaluate_landsat",
    "evaluate_sentinel1",
    "evaluate_sentinel2",
]
