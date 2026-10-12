"""Cell-level EO/label arrays for SpartinaShift-Silver v0.1 (Stage 1).

Reads ONLY frozen Issue #19 V2 bytes (read-only):

* EO products from ``work/national/pilot19/products`` (7-band Landsat SR,
  4-band Sentinel-2 SR, VV/VH Sentinel-1, per-product VALID bytes);
* 2-band SILVER label supports from ``work/national/pilot19/labels``
  (band 1 fractional occupancy, band 2 occupancy class).

Everything is aligned to the native 30 m label grid: 10 m Sentinel EO is
aggregated DOWN with average resampling and a >= 5/9 sub-pixel validity
rule; no label is ever moved onto a 10 m grid. Aggregated arrays are
cached (out of Git) keyed by product and label-support checksums.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[4]
PRODUCTS_DIR: Final[Path] = REPO_ROOT / "work/national/pilot19/products"
LABELS_DIR: Final[Path] = REPO_ROOT / "work/national/pilot19/labels"
CACHE_DIR: Final[Path] = REPO_ROOT / "work/issue20/cache"

VALID_SUBPIXEL_FRACTION: Final[float] = 5.0 / 9.0

#: Family/year combinations for which the unmapped fraction-0 region may
#: be read as SOURCE_BACKGROUND_WEAK: gridcode-0 must be absent (Phase B
#: verified zero gridcode-0 pixels for CMSA 2020/2021 in the C2 cells).
WEAK_BACKGROUND_WHITELIST: Final[frozenset[tuple[str, int]]] = frozenset({
    ("CMSA", 2020), ("CMSA", 2021), ("CM-SSM", 2020)})


@dataclass(frozen=True)
class ProductFiles:
    product_id: str
    sensor: str
    feature_tif: Path
    valid_tif: Path
    is_sar: bool


def sensor_of(product_id: str) -> str:
    token = product_id.split("_")[2]
    if token not in {"L5", "L7", "L8", "S1", "S2"}:
        raise ValueError(f"cannot parse sensor from {product_id}")
    return {"L5": "landsat5", "L7": "landsat7", "L8": "landsat8",
            "S1": "sentinel1", "S2": "sentinel2"}[token]


def feature_band_names(
    sensor: str, is_sar: bool, n_bands: int,
) -> tuple[str, ...]:
    if is_sar:
        return ("VV", "VH")[:n_bands] if n_bands <= 2 else tuple(
            f"SAR{i}" for i in range(n_bands))
    order: tuple[str, ...]
    if sensor == "sentinel2":
        order = ("B2", "B3", "B4", "B8")
    else:
        order = tuple(f"SR_B{i + 1}" for i in range(7))
    return order[:n_bands]


@dataclass(frozen=True)
class CellArrays:
    """30 m analysis-grid arrays for one EO product x label source."""

    product_id: str
    label_source_key: str
    features: np.ndarray[Any, Any]  # (C, H, W) float32
    valid: np.ndarray[Any, Any]  # (H, W) bool: every band valid
    fraction: np.ndarray[Any, Any]  # (H, W) float32 occupancy fraction
    occ_class: np.ndarray[Any, Any]  # (H, W) uint8
    transform: Any
    crs_epsg: int
    band_names: tuple[str, ...]
    label_tif_sha256: str


def _cell_rc(cell_id: str) -> str:
    prefix = "CNA10K-"
    if not cell_id.startswith(prefix):
        raise ValueError(f"unexpected cell id {cell_id}")
    return cell_id[len(prefix):]


def label_path(cell_id: str, source_key: str, support_m: int = 30) -> Path:
    return (
        LABELS_DIR / _cell_rc(cell_id)
        / f"{source_key}_{support_m}m.tif")


def find_product_files(product_id: str) -> ProductFiles:
    matches = sorted(PRODUCTS_DIR.glob(f"spartina_pilot19_{product_id}_*"))
    feature = [p for p in matches if p.name.split(product_id + "_")[1]
               .split("_")[0] in ("sr", "vvvh")]
    valid = [p for p in matches if "valid" in p.name
             and "qapixel" not in p.name]
    if len(feature) != 1 or len(valid) != 1:
        raise FileNotFoundError(
            f"{product_id}: expected 1 feature and 1 valid tif, found "
            f"{[p.name for p in feature]} / {[p.name for p in valid]}")
    is_sar = "vvvh" in feature[0].name
    return ProductFiles(
        product_id, sensor_of(product_id), feature[0], valid[0], is_sar)


def _reproject_to_grid(
    src: rasterio.io.DatasetReader,
    dst_shape: tuple[int, int],
    dst_transform: Any,
    dst_crs: Any,
    *,
    average: bool,
    src_band: int | None = None,
) -> np.ndarray[Any, Any]:
    n_bands = src.count if src_band is None else 1
    out = np.full(
        (n_bands, dst_shape[0], dst_shape[1]), np.nan, dtype=np.float32)
    for i in range(n_bands):
        reproject(
            source=rasterio.band(src, src_band if src_band is not None
                                 else i + 1),
            destination=out[i],
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.average if average else Resampling.nearest,
            src_nodata=src.nodata)
    return out


def _load_product_30m(
    files: ProductFiles,
    dst_shape: tuple[int, int],
    dst_transform: Any,
    dst_crs: Any,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], tuple[str, ...]]:
    with rasterio.open(files.feature_tif) as feat:
        if feat.crs is None:
            raise ValueError(f"{files.feature_tif}: missing CRS")
        same_grid = (
            feat.crs.to_epsg() == dst_crs.to_epsg()
            and feat.width == dst_shape[1]
            and feat.height == dst_shape[0]
            and tuple(feat.transform)[:6] == tuple(dst_transform)[:6])
        if not same_grid and abs(feat.res[0] - 30.0) < 0.5:
            raise ValueError(
                f"{files.product_id}: 30 m product grid does not match "
                "label grid; refusing to warp native-30 m EO")
        if not same_grid and feat.res[0] > 30.0:
            raise ValueError(
                f"{files.product_id}: source resolution "
                f"{feat.res[0]} m coarser than the 30 m analysis grid")
        bands = feature_band_names(
            files.sensor, files.is_sar, feat.count)
        features = _reproject_to_grid(
            feat, dst_shape, dst_transform, dst_crs, average=True)
    with rasterio.open(files.valid_tif) as vf:
        valid_frac = _reproject_to_grid(
            vf, dst_shape, dst_transform, dst_crs, average=True,
            src_band=1)[0]
    valid = valid_frac >= VALID_SUBPIXEL_FRACTION
    features[:, ~valid] = np.nan
    return features.astype(np.float32), valid, bands


def load_cell_arrays(
    cell_id: str,
    product_id: str,
    label_source_key: str,
    *,
    extra_product_id: str | None = None,
    use_cache: bool = True,
) -> CellArrays:
    """Load (and cache) the 30 m feature/label arrays for one pairing.

    ``extra_product_id`` stacks a second sensor's bands (used by the
    optical+SAR arm); the validity mask is the per-sensor intersection.
    """
    import hashlib
    import json

    files = find_product_files(product_id)
    extra = find_product_files(extra_product_id) if extra_product_id \
        else None
    lp = label_path(cell_id, label_source_key)
    label_sha = hashlib.sha256(lp.read_bytes()).hexdigest()
    cache_key = "|".join(
        [product_id, extra_product_id or "-", label_source_key, label_sha])
    cache_path = CACHE_DIR / (
        hashlib.sha256(cache_key.encode()).hexdigest() + ".npz")
    meta_path = cache_path.with_suffix(".json")
    if use_cache and cache_path.exists() and meta_path.exists():
        z = np.load(cache_path)
        with rasterio.open(lp) as ds:
            transform = ds.transform
            epsg = int(ds.crs.to_epsg()) if ds.crs else 0
        meta = json.loads(meta_path.read_text())
        return CellArrays(
            product_id, label_source_key, z["features"], z["valid"],
            z["fraction"], z["occ_class"], transform, epsg,
            tuple(meta["band_names"]), label_sha)

    with rasterio.open(lp) as lab:
        fraction = lab.read(1).astype(np.float32)
        occ_class = lab.read(2).astype(np.uint8)
        dst_transform = lab.transform
        dst_crs = lab.crs
        dst_shape = (lab.height, lab.width)
        epsg = int(lab.crs.to_epsg()) if lab.crs else 0

    features, valid, bands = _load_product_30m(
        files, dst_shape, dst_transform, dst_crs)
    if extra is not None:
        f2, v2, b2 = _load_product_30m(
            extra, dst_shape, dst_transform, dst_crs)
        features = np.concatenate([features, f2], axis=0)
        valid = valid & v2
        bands = bands + b2

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache_path, features=features, valid=valid, fraction=fraction,
        occ_class=occ_class)
    meta_path.write_text(json.dumps({
        "product_id": product_id,
        "extra_product_id": extra_product_id,
        "label_source_key": label_source_key,
        "label_tif_sha256": label_sha,
        "band_names": list(bands),
        "feature_tif": str(files.feature_tif.relative_to(REPO_ROOT)),
        "valid_tif": str(files.valid_tif.relative_to(REPO_ROOT)),
    }, indent=2) + "\n")
    return CellArrays(
        product_id, label_source_key, features, valid, fraction,
        occ_class, dst_transform, epsg, bands, label_sha)


def target_masks(
    fraction: np.ndarray[Any, Any],
    occ_class: np.ndarray[Any, Any],
    family: str,
    year: int,
) -> dict[str, np.ndarray[Any, Any]]:
    """Frozen SOURCE_MAPPED_POSITIVE / background / MIXED / ignore views.

    GEODATA: only the adapter's in-window weak background (class 3) is a
    binary negative; class 0 outside-window pixels stay ignored.
    CMSA/CM-SSM (whitelisted years): the product is positive-only but
    gridcode-0/unknown pixels are verified absent in the task cells, so
    valid fraction-0 pixels are SOURCE_BACKGROUND_WEAK; MIXED is ignored
    in the binary view and reported separately.
    """
    y = fraction >= 0.90
    mixed = (fraction > 0.0) & (fraction < 0.90)
    notfinite = ~np.isfinite(fraction)
    if family == "GEODATA":
        background = occ_class == 3
        unknown = (occ_class == 0) | notfinite
    else:
        assert_weak_background_allowed(family, year)
        background = np.isfinite(fraction) & (fraction <= 0.0)
        unknown = notfinite
    binary_valid = (y | background) & ~mixed & ~unknown
    ignore = ~binary_valid
    return {
        "y": y,
        "background": background,
        "mixed": mixed,
        "unknown": unknown,
        "binary_valid": binary_valid,
        "ignore": ignore,
    }


def assert_weak_background_allowed(family: str, year: int) -> None:
    if family not in ("GEODATA",) and (family, year) \
            not in WEAK_BACKGROUND_WHITELIST:
        raise ValueError(
            f"{family} {year}: SOURCE_BACKGROUND_WEAK is not whitelisted "
            "(gridcode-0/unknown not verified absent); refusing to treat "
            "fraction-0 pixels as binary negatives")


@dataclass(frozen=True)
class NormStats:
    p_low: np.ndarray[Any, Any]  # (C,)
    p_high: np.ndarray[Any, Any]
    mean: np.ndarray[Any, Any]
    std: np.ndarray[Any, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "p_low": [float(v) for v in self.p_low],
            "p_high": [float(v) for v in self.p_high],
            "mean": [float(v) for v in self.mean],
            "std": [float(v) for v in self.std]}


def compute_norm_stats(
    features: np.ndarray[Any, Any], valid: np.ndarray[Any, Any],
    p_low_q: float = 0.005, p_high_q: float = 0.995,
) -> NormStats:
    """Per-band percentile/mean/std from VALID pixels (train only)."""
    n_bands = features.shape[0]
    lo = np.zeros(n_bands, dtype=np.float32)
    hi = np.zeros(n_bands, dtype=np.float32)
    mean = np.zeros(n_bands, dtype=np.float32)
    std = np.zeros(n_bands, dtype=np.float32)
    for i in range(n_bands):
        vals = features[i][valid & np.isfinite(features[i])]
        if vals.size == 0:
            raise ValueError(f"band {i}: no valid training pixels")
        lo[i] = float(np.quantile(vals, p_low_q))
        hi[i] = float(np.quantile(vals, p_high_q))
        clipped = np.clip(vals, lo[i], hi[i])
        mean[i] = float(clipped.mean())
        std[i] = float(clipped.std())
        if std[i] < 1e-8:
            std[i] = 1.0
    return NormStats(lo, hi, mean, std)


def apply_norm(features: np.ndarray[Any, Any], valid: np.ndarray[Any, Any],
               stats: NormStats) -> np.ndarray[Any, Any]:
    out = np.empty_like(features)
    for i in range(features.shape[0]):
        clipped = np.clip(features[i], stats.p_low[i], stats.p_high[i])
        out[i] = (clipped - stats.mean[i]) / stats.std[i]
    out[:, ~valid] = 0.0
    out[~np.isfinite(out)] = 0.0
    return out.astype(np.float32)


def sample_patch_origins(
    valid: np.ndarray[Any, Any],
    y: np.ndarray[Any, Any],
    *,
    n_patches: int,
    patch: int,
    positive_fraction: float,
    seed: int,
) -> list[tuple[int, int]]:
    """Deterministic 128 px patch top-left coordinates per cell.

    At least ``round(n*positive_fraction)`` patches are positive-centred
    (where the cell has positives); the rest are random valid windows,
    which may themselves contain positives. Positions repeat across
    epochs by (cell, seed); epoch variation comes from augmentation.
    """
    rng = np.random.default_rng(seed)
    h, w = valid.shape
    row_max = max(h - patch, 0)
    col_max = max(w - patch, 0)
    pos_rows, pos_cols = np.nonzero(y)
    origins: list[tuple[int, int]] = []
    n_pos = int(round(n_patches * positive_fraction))
    if pos_rows.size > 0:
        for _ in range(n_pos):
            k = int(rng.integers(0, pos_rows.size))
            r = int(pos_rows[k])
            c = int(pos_cols[k])
            r0 = int(np.clip(r - rng.integers(0, patch), 0, row_max))
            c0 = int(np.clip(c - rng.integers(0, patch), 0, col_max))
            origins.append((r0, c0))
    while len(origins) < n_patches:
        r0 = int(rng.integers(0, row_max + 1))
        c0 = int(rng.integers(0, col_max + 1))
        # Protocol: the remaining half are random VALID windows; they may
        # themselves contain positives (no positive-exclusion rule).
        if valid[r0:r0 + patch, c0:c0 + patch].mean() >= 0.5:
            origins.append((r0, c0))
    return origins


def geometric_transform(
    x: np.ndarray[Any, Any], y: np.ndarray[Any, Any],
    valid: np.ndarray[Any, Any], ignore: np.ndarray[Any, Any],
    kind: int,
) -> tuple[
    np.ndarray[Any, Any], np.ndarray[Any, Any],
    np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Deterministic 6-way flips/rotations (kind 0..5)."""
    if kind == 0:
        return x, y, valid, ignore
    if kind == 1:
        return x[:, :, ::-1], y[:, ::-1], valid[:, ::-1], ignore[:, ::-1]
    if kind == 2:
        return x[:, ::-1, :], y[::-1, :], valid[::-1, :], ignore[::-1, :]
    k = kind - 1
    x = np.rot90(x, k=k, axes=(1, 2))
    return (x, np.rot90(y, k=k), np.rot90(valid, k=k),
            np.rot90(ignore, k=k))
