"""Real server-side pixel-quality counts and fractions over an ROI.

The catalog :class:`~spartina.data.gee.quality.CandidateScene` distinguishes
catalog-level cloud metadata from *ROI-level* raster quality: how much of
this exact ROI the scene observed, how much is cloud/shadow/cirrus/snow
there. These functions compute those numbers inside Earth Engine via one
mapped ``reduceRegion`` (sum reducer) per sensor (one ``getInfo`` round
trip), so nothing about the answer is guessed from scene-wide metadata.

Returned count bands are explicitly ``unmask(0)`` before reducing, and the
denominator is a constant-1 image summed over the ROI, so fully masked
pixels count as zero coverage instead of disappearing.

All Earth Engine usage stays lazy; importing this module without
credentials / earthengine-api is safe.
"""

from __future__ import annotations

from typing import Any

from spartina.data.gee.landsat import (
    QA_CIRRUS,
    QA_CLEAR,
    QA_CLOUD,
    QA_CLOUD_SHADOW,
    QA_DILATED_CLOUD,
    QA_FILL,
    QA_SNOW,
)

#: Fraction of the ROI observed by the sensor (mask present / SCL nonzero).
VALID_KEY: str = "valid_pixel_fraction"
#: Fraction of the ROI flagged as cloud family (dilated/cirrus/opaque).
CLOUD_KEY: str = "roi_cloud_fraction"
#: Fraction of the ROI passing the same clear rule used for masking.
CLEAR_KEY: str = "clear_pixel_fraction"

# Count-band names written by the detailed evaluators.
TOTAL_PIXELS: str = "roi_total_pixels"
VALID_PIXELS: str = "roi_valid_pixels"
CLOUD_PIXELS: str = "roi_cloud_pixels"
SHADOW_PIXELS: str = "roi_cloud_shadow_pixels"
CIRRUS_PIXELS: str = "roi_cirrus_pixels"
SNOW_PIXELS: str = "roi_snow_pixels"
SATURATED_PIXELS: str = "roi_saturated_pixels"
CLEAR_PIXELS: str = "roi_clear_pixels"

# Server-side flag properties attached per scene (read back after getInfo).
PROP_CLDPRB: str = "spartina_cldprb_available"
PROP_SCL: str = "spartina_scl_available"
PROP_BAND_PREFIX: str = "spartina_band_"


def _count_table(
    ee: Any,
    collection: Any,
    roi: Any,
    band_builder: Any,
    band_names: tuple[str, ...],
    scale_m: float,
    *,
    property_names: tuple[str, ...] = (),
    tile_scale: int = 4,
) -> dict[str, dict[str, Any]]:
    """Map ``band_builder`` over the collection and sum counts on the ROI.

    Returns ``{scene_id: {band: int_count, ...prop: value}}``.
    """

    def to_feature(image: Any) -> Any:
        counts = band_builder(ee, image).unmask(0).select(list(band_names))
        stats = counts.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=float(scale_m),
            maxPixels=10_000_000,
            bestEffort=True,
            tileScale=int(tile_scale),
        )
        for name in property_names:
            stats = stats.set(name, image.get(name))
        return ee.Feature(
            None, stats.set("scene_id", image.get("system:index")))

    features = collection.map(to_feature).getInfo().get("features", [])
    table: dict[str, dict[str, Any]] = {}
    for feature in features:
        props = dict(feature.get("properties", {}))
        scene_id = props.pop("scene_id", None)
        if scene_id is None:
            continue
        row: dict[str, Any] = {}
        for key in band_names:
            value = props.get(key)
            row[key] = int(value) if isinstance(value, int | float) else None
        for name in property_names:
            row[name] = props.get(name)
        table[str(scene_id)] = row
    return table


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    if not isinstance(numerator, int) or not isinstance(denominator, int):
        return None
    if denominator <= 0:
        return None
    return numerator / denominator


# ---------------------------------------------------------------------------
# Landsat Collection 2 Level-2 (QA_PIXEL + QA_RADSAT)
# ---------------------------------------------------------------------------

LANDSAT_COUNT_BANDS: tuple[str, ...] = (
    TOTAL_PIXELS, VALID_PIXELS, CLOUD_PIXELS, SHADOW_PIXELS,
    CIRRUS_PIXELS, SNOW_PIXELS, SATURATED_PIXELS, CLEAR_PIXELS,
)


def landsat_qa_count_bands(ee: Any, image: Any) -> Any:
    """0/1 count bands for every documented QA_PIXEL/QA_RADSAT category.

    Water is never a defect (bit 7 ignored; coastal ROI). ``cloud`` is the
    opaque cloud family (dilated | cirrus | cloud); shadow and snow are
    counted separately so the selection policy can rank on them.
    """
    qa = image.select("QA_PIXEL")
    radsat = image.select("QA_RADSAT")
    observed = qa.bitwiseAnd(1 << QA_FILL).eq(0)
    dilated = qa.bitwiseAnd(1 << QA_DILATED_CLOUD).neq(0)
    cirrus = qa.bitwiseAnd(1 << QA_CIRRUS).neq(0)
    cloud = qa.bitwiseAnd(1 << QA_CLOUD).neq(0)
    shadow = qa.bitwiseAnd(1 << QA_CLOUD_SHADOW).neq(0)
    snow = qa.bitwiseAnd(1 << QA_SNOW).neq(0)
    saturated = radsat.neq(0)
    cloud_family = dilated.Or(cirrus).Or(cloud)
    clear = (
        observed
        .And(cloud_family.Not())
        .And(shadow.Not())
        .And(snow.Not())
        .And(qa.bitwiseAnd(1 << QA_CLEAR).neq(0))
        .And(saturated.Not())
    )
    return ee.Image.cat([
        ee.Image.constant(1).rename(TOTAL_PIXELS),
        observed.rename(VALID_PIXELS),
        cloud_family.rename(CLOUD_PIXELS),
        shadow.rename(SHADOW_PIXELS),
        cirrus.rename(CIRRUS_PIXELS),
        snow.rename(SNOW_PIXELS),
        saturated.rename(SATURATED_PIXELS),
        clear.rename(CLEAR_PIXELS),
    ])


def landsat_mask_bands(ee: Any, image: Any) -> Any:
    """QA_PIXEL-based 0/1 bands: observed / cloud-flagged / fully clear."""
    qa = image.select("QA_PIXEL")
    radsat = image.select("QA_RADSAT")
    observed = qa.bitwiseAnd(1 << QA_FILL).eq(0)
    cloud = (
        qa.bitwiseAnd(1 << QA_DILATED_CLOUD).neq(0)
        .Or(qa.bitwiseAnd(1 << QA_CIRRUS).neq(0))
        .Or(qa.bitwiseAnd(1 << QA_CLOUD).neq(0))
        .Or(qa.bitwiseAnd(1 << QA_CLOUD_SHADOW).neq(0))
        .Or(qa.bitwiseAnd(1 << QA_SNOW).neq(0))
    )
    clear = (
        observed.And(cloud.Not())
        .And(qa.bitwiseAnd(1 << QA_CLEAR).neq(0))
        .And(radsat.eq(0))
    )
    return ee.Image.cat([
        observed.rename(VALID_KEY),
        cloud.rename(CLOUD_KEY),
        clear.rename(CLEAR_KEY),
    ])


def counts_landsat(
    ee: Any, collection: Any, roi: Any, *, scale_m: float = 30.0,
) -> dict[str, dict[str, Any]]:
    """Detailed ROI pixel counts + derived fractions per Landsat scene."""
    table = _count_table(
        ee, collection, roi, landsat_qa_count_bands, LANDSAT_COUNT_BANDS,
        scale_m)
    for row in table.values():
        total = row.get(TOTAL_PIXELS)
        row[VALID_KEY] = _safe_ratio(row.get(VALID_PIXELS), total)
        row[CLOUD_KEY] = _safe_ratio(row.get(CLOUD_PIXELS), total)
        row["roi_shadow_fraction"] = _safe_ratio(
            row.get(SHADOW_PIXELS), total)
        row["roi_cirrus_fraction"] = _safe_ratio(
            row.get(CIRRUS_PIXELS), total)
        row["roi_snow_fraction"] = _safe_ratio(row.get(SNOW_PIXELS), total)
        row["roi_saturated_fraction"] = _safe_ratio(
            row.get(SATURATED_PIXELS), total)
        row[CLEAR_KEY] = _safe_ratio(row.get(CLEAR_PIXELS), total)
    return table


# ---------------------------------------------------------------------------
# Sentinel-2 SR Harmonized (SCL; MSK_CLDPRB availability flagged, not joined)
# ---------------------------------------------------------------------------

S2_COUNT_BANDS: tuple[str, ...] = LANDSAT_COUNT_BANDS
S2_FLAG_PROPERTIES: tuple[str, ...] = (PROP_CLDPRB, PROP_SCL)


def with_s2_band_flags(ee: Any, image: Any) -> Any:
    """Attach whether SCL / MSK_CLDPRB bands exist on this exact scene."""
    names = image.bandNames()
    return image.set(
        PROP_CLDPRB, names.contains("MSK_CLDPRB"),
        PROP_SCL, names.contains("SCL"))


def sentinel2_qa_count_bands(ee: Any, image: Any) -> Any:
    """SCL-class count bands. Water (6) stays a valid surface observation."""
    scl = image.select("SCL")
    observed = scl.mask()
    cloud_family = scl.eq(8).Or(scl.eq(9)).Or(scl.eq(10))
    shadow = scl.eq(3)
    cirrus = scl.eq(10)
    snow = scl.eq(11)
    # SCL 0 = no data, 1 = saturated/defective -> sensor-side invalidity.
    saturated = scl.eq(0).Or(scl.eq(1))
    clear = (
        scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(11)))
    return ee.Image.cat([
        ee.Image.constant(1).rename(TOTAL_PIXELS),
        observed.rename(VALID_PIXELS),
        cloud_family.rename(CLOUD_PIXELS),
        shadow.rename(SHADOW_PIXELS),
        cirrus.rename(CIRRUS_PIXELS),
        snow.rename(SNOW_PIXELS),
        saturated.rename(SATURATED_PIXELS),
        clear.rename(CLEAR_PIXELS),
    ])


def sentinel2_mask_bands(ee: Any, image: Any) -> Any:
    """SCL-based 0/1 bands: observed / cloud-flagged / clear-surface."""
    scl = image.select("SCL")
    observed = scl.mask()
    cloud = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10))
    clear = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(11))
    return ee.Image.cat([
        observed.rename(VALID_KEY),
        cloud.rename(CLOUD_KEY),
        clear.rename(CLEAR_KEY),
    ])


def counts_sentinel2(
    ee: Any, collection: Any, roi: Any, *, scale_m: float = 10.0,
) -> dict[str, dict[str, Any]]:
    """Detailed SCL counts/fractions + MSK_CLDPRB availability per scene."""
    flagged = collection.map(lambda image: with_s2_band_flags(ee, image))
    table = _count_table(
        ee, flagged, roi, sentinel2_qa_count_bands, S2_COUNT_BANDS,
        scale_m, property_names=S2_FLAG_PROPERTIES)
    for row in table.values():
        total = row.get(TOTAL_PIXELS)
        row[VALID_KEY] = _safe_ratio(row.get(VALID_PIXELS), total)
        row[CLOUD_KEY] = _safe_ratio(row.get(CLOUD_PIXELS), total)
        row["roi_shadow_fraction"] = _safe_ratio(
            row.get(SHADOW_PIXELS), total)
        row["roi_cirrus_fraction"] = _safe_ratio(
            row.get(CIRRUS_PIXELS), total)
        row["roi_snow_fraction"] = _safe_ratio(row.get(SNOW_PIXELS), total)
        row["roi_saturated_fraction"] = _safe_ratio(
            row.get(SATURATED_PIXELS), total)
        row[CLEAR_KEY] = _safe_ratio(row.get(CLEAR_PIXELS), total)
        row["cloud_probability_available"] = bool(row.get(PROP_CLDPRB))
    return table


# ---------------------------------------------------------------------------
# Sentinel-1 GRD (no optical QA; coverage from the VV observation mask)
# ---------------------------------------------------------------------------

S1_COUNT_BANDS: tuple[str, ...] = (TOTAL_PIXELS, VALID_PIXELS)
S1_BANDS: tuple[str, ...] = ("VV", "VH", "HH", "HV", "angle")


def with_s1_band_flags(ee: Any, image: Any) -> Any:
    """Attach per-polarisation / angle band availability on this scene."""
    names = image.bandNames()
    props: dict[str, Any] = {}
    for band in S1_BANDS:
        props[f"{PROP_BAND_PREFIX}{band}"] = names.contains(band)
    return image.set(props)


def sentinel1_qa_count_bands(ee: Any, image: Any) -> Any:
    """Observation coverage counts from the VV mask."""
    observed = image.select("VV").mask()
    return ee.Image.cat([
        ee.Image.constant(1).rename(TOTAL_PIXELS),
        observed.rename(VALID_PIXELS),
    ])


def sentinel1_mask_bands(ee: Any, image: Any) -> Any:
    """VV mask as per-pixel observation coverage for the ROI."""
    observed = image.select("VV").mask()
    return ee.Image.cat([observed.rename(VALID_KEY)])


def counts_sentinel1(
    ee: Any, collection: Any, roi: Any, *, scale_m: float = 10.0,
) -> dict[str, dict[str, Any]]:
    """Coverage counts/fractions + VV/VH/HH/HV/angle availability per scene."""
    prop_names = tuple(f"{PROP_BAND_PREFIX}{b}" for b in S1_BANDS)
    flagged = collection.map(lambda image: with_s1_band_flags(ee, image))
    table = _count_table(
        ee, flagged, roi, sentinel1_qa_count_bands, S1_COUNT_BANDS,
        scale_m, property_names=prop_names)
    for row in table.values():
        total = row.get(TOTAL_PIXELS)
        row[VALID_KEY] = _safe_ratio(row.get(VALID_PIXELS), total)
        for band in S1_BANDS:
            row[f"{band.lower()}_available"] = bool(
                row.pop(f"{PROP_BAND_PREFIX}{band}", False))
    return table


# ---------------------------------------------------------------------------
# Fraction-only API retained for callers/tests that need the v1 fractions
# ---------------------------------------------------------------------------

def _fraction_table(
    ee: Any,
    collection: Any,
    roi: Any,
    mask_builder: Any,
    band_names: tuple[str, ...],
    scale_m: float,
    *,
    tile_scale: int = 4,
) -> dict[str, dict[str, float | None]]:
    """Mean of 0/1 masks = fraction; masks are unmasked for the denominator."""

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
    "CLEAR_PIXELS",
    "CLOUD_KEY",
    "CLOUD_PIXELS",
    "CIRRUS_PIXELS",
    "PROP_BAND_PREFIX",
    "PROP_CLDPRB",
    "PROP_SCL",
    "SATURATED_PIXELS",
    "SHADOW_PIXELS",
    "SNOW_PIXELS",
    "TOTAL_PIXELS",
    "VALID_KEY",
    "VALID_PIXELS",
    "counts_landsat",
    "counts_sentinel1",
    "counts_sentinel2",
    "evaluate_landsat",
    "evaluate_sentinel1",
    "evaluate_sentinel2",
    "landsat_mask_bands",
    "landsat_qa_count_bands",
    "sentinel1_mask_bands",
    "sentinel1_qa_count_bands",
    "sentinel2_mask_bands",
    "sentinel2_qa_count_bands",
    "with_s1_band_flags",
    "with_s2_band_flags",
]
