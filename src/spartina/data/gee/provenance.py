"""Provenance-chain verification for real GEE factory products.

Implements the Issue #6 acceptance rule that a landed GeoTIFF must be
traceable backwards through: exact source scene -> acquisition UTC ->
selection configuration -> processing configuration -> export task ->
fixed GridSpec -> landed file + checksum. Standard library only for the
context helpers; rasterio is imported lazily inside the raster checks.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

MANIFEST_VERSION = "GEE_DATA_FACTORY_V1"


class ProvenanceError(RuntimeError):
    """The export provenance chain is broken (Issue #6 gate failure)."""


def git_context(repo_root: str | Path) -> dict[str, Any]:
    """Current commit and dirty-tree flag (never raises; records UNKNOWN)."""
    root = str(repo_root)

    def _run(args: list[str]) -> str | None:
        try:
            out = subprocess.run(  # noqa: S603
                ["git", *args], cwd=root, check=False,
                capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    commit = _run(["rev-parse", "HEAD"])
    porcelain = _run(["status", "--porcelain"])
    return {
        "git_commit": commit or "UNKNOWN",
        "dirty_tree": bool(porcelain) if porcelain is not None else "UNKNOWN",
    }


def runtime_environment() -> dict[str, str]:
    """Installed versions recorded into the manifest."""
    def _version(distribution: str) -> str:
        try:
            return metadata.version(distribution)
        except metadata.PackageNotFoundError:
            return "MISSING"

    return {
        "python": sys.version.split()[0],
        "earthengine_api": _version("earthengine-api"),
        "rasterio": _version("rasterio"),
    }


def sha256_file(path: str | Path, *, chunk: int = 1 << 20) -> str:
    """Stream-hash a landed file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def raster_grid_info(path: str | Path) -> dict[str, Any]:
    """Read driver/CRS/transform/dimensions/dtype/nodata via rasterio."""
    import rasterio

    with rasterio.open(path) as dataset:
        return {
            "driver": dataset.driver,
            "crs_epsg": dataset.crs.to_epsg(),
            "transform": list(dataset.transform)[:6],
            "bounds": list(dataset.bounds),
            "width": dataset.width,
            "height": dataset.height,
            "count": dataset.count,
            "dtypes": list(dataset.dtypes),
            "nodata": [dataset.nodata] * dataset.count
            if dataset.nodata is not None else [None] * dataset.count,
            "band_names": list(dataset.descriptions),
        }


def assert_grid_matches(raster_info: dict[str, Any],
                        grid: dict[str, Any]) -> None:
    """Hard-fail when a landed raster disagrees with the manifest GridSpec."""
    errors: list[str] = []
    if raster_info["crs_epsg"] != int(str(grid["crs"]).split(":")[1]):
        errors.append("crs mismatch")
    if raster_info["width"] != grid["width"]:
        errors.append("width mismatch")
    if raster_info["height"] != grid["height"]:
        errors.append("height mismatch")
    if [round(v, 6) for v in raster_info["transform"]] != [
            round(float(v), 6) for v in grid["transform"]]:
        errors.append("transform mismatch")
    pixel = grid.get("pixel_size_m")
    if pixel is not None and raster_info["transform"][0] != float(pixel[0]):
        errors.append("pixel size mismatch")
    if errors:
        raise ProvenanceError(
            f"landed raster disagrees with the GridSpec: {errors}; "
            f"raster={raster_info} grid={grid}")


def reflectance_sanity(
    path: str | Path, band_count: int = 7,
) -> dict[str, Any]:
    """Per-band min/P01/P05/median/P95/P99/max + scaling-bug screen.

    Small negative reflectance is allowed (residual atmospheric effects).
    A bulk of values at DN scale (~1000/10000) or |reflectance| >> 1 over
    valid pixels indicates a missing/broken scale and FAILS the check.
    """
    import numpy as np
    import rasterio

    stats: dict[str, Any] = {"bands": {}}
    scale_failures: list[str] = []
    with rasterio.open(path) as dataset:
        if dataset.count != band_count:
            raise ProvenanceError(
                f"expected {band_count} reflectance bands, "
                f"got {dataset.count}")
        for index in range(1, band_count + 1):
            band = dataset.read(index).astype("float64")
            finite = np.isfinite(band)
            if dataset.nodata is not None:
                finite &= band != float(dataset.nodata)
            total = int(band.size)
            valid_count = int(finite.sum())
            invalid_fraction = (
                1.0 - valid_count / total if total else None)
            values = band[finite]
            percentiles: dict[str, float | None]
            if values.size == 0:
                percentiles = {k: None for k in
                               ("min", "p01", "p05", "median",
                                "p95", "p99", "max")}
            else:
                ps = np.percentile(values, [0, 1, 5, 50, 95, 99, 100])
                percentiles = dict(zip(
                    ("min", "p01", "p05", "median", "p95", "p99", "max"),
                    [float(v) for v in ps], strict=True))
                # Unscaled Collection-2 DN would be ~0..65455 integer-ish
                # values; /10000 S2-style would be ~1000-10000.
                over_one = float((np.abs(values) > 1.5).mean())
                dn_like = float(((values > 500) & (values < 65535)).mean())
                median = percentiles["median"]
                if dn_like > 0.5 or over_one > 0.25 or (
                        median is not None and abs(median) > 1.5):
                    scale_failures.append(
                        f"band {index}: median={median}, "
                        f"fraction_|v|>1.5={over_one:.3f}, "
                        f"fraction_DN_like={dn_like:.3f}")
            stats["bands"][f"SR_B{index}"] = {
                **percentiles,
                "valid_pixel_count": valid_count,
                "invalid_fraction": invalid_fraction}
    stats["scaling_check_pass"] = not scale_failures
    stats["scaling_failures"] = scale_failures
    if scale_failures:
        raise ProvenanceError(
            "reflectance scaling sanity failed: " + "; ".join(scale_failures))
    return stats


def valid_mask_info(path: str | Path) -> dict[str, Any]:
    """Audit a byte VALID mask raster and its grid.

    Hard-fails unless the mask is one uint8 band whose only values are
    0/1 (Issue #6 M1.6c raster contract). Returns grid metadata, unique
    values/counts and the valid fraction for manifest recording.
    """
    import numpy as np
    import rasterio

    with rasterio.open(path) as dataset:
        arr = dataset.read(1)
        info: dict[str, Any] = {
            "driver": dataset.driver,
            "crs_epsg": dataset.crs.to_epsg(),
            "transform": list(dataset.transform)[:6],
            "bounds": list(dataset.bounds),
            "width": dataset.width,
            "height": dataset.height,
            "count": dataset.count,
            "dtypes": list(dataset.dtypes),
            "nodata": dataset.nodata,
            "band_names": list(dataset.descriptions),
        }
    total = int(arr.size)
    values, counts = np.unique(arr, return_counts=True)
    unique = [int(value) for value in values]
    valid_count = int((arr == 1).sum())
    info.update({
        "unique_values": unique,
        "unique_value_counts": {
            int(value): int(count)
            for value, count in zip(values, counts, strict=True)},
        "total_pixel_count": total,
        "valid_pixel_count": valid_count,
        "valid_fraction": valid_count / total if total else None,
        "binary_values_only": all(value in (0, 1) for value in unique),
    })
    if info["dtypes"][0] != "uint8":
        raise ProvenanceError(
            f"VALID mask must be uint8, got {info['dtypes']} ({path})")
    if info["count"] != 1:
        raise ProvenanceError(
            f"VALID mask must have exactly 1 band, got {info['count']}")
    if not info["binary_values_only"]:
        raise ProvenanceError(
            f"VALID mask values must be subset of {{0, 1}}, got {unique}")
    return info


def reflectance_sanity_masked(
    sr_path: str | Path, valid_path: str | Path,
    band_names: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    """Per-band reflectance statistics restricted to VALID==1 pixels.

    Used by the Sentinel-2 real-byte smoke, where reflectance and VALID
    land as separate files. For every band reports min, P01, P05, median,
    P95, P99, max, mean, std and the negative / >1 fractions. Reflectance
    is not required to lie inside [0, 1] (small negatives and slight
    over-unity values are physical residual-atmosphere effects and are
    REPORTED ONLY), but a bulk at DN scale (~1000/10000) or |v|>>1 means
    the explicit 1e-4 scale was not applied and FAILS.
    """
    import numpy as np
    import rasterio

    stats: dict[str, Any] = {
        "pixel_selection": "VALID==1 AND finite (nodata excluded)",
        "bands": {}}
    scale_failures: list[str] = []
    with rasterio.open(valid_path) as valid_dataset:
        valid = valid_dataset.read(1) == 1
    expected_valid_count = int(valid.sum())
    with rasterio.open(sr_path) as dataset:
        if dataset.count != len(band_names):
            raise ProvenanceError(
                f"expected {len(band_names)} reflectance bands, "
                f"got {dataset.count}")
        nodata = float(dataset.nodata) if dataset.nodata is not None else None
        for index, name in enumerate(band_names, start=1):
            band = dataset.read(index).astype("float64")
            selected = valid & np.isfinite(band)
            if nodata is not None:
                selected &= band != nodata
            values = band[selected]
            count = int(values.size)
            entry: dict[str, Any] = {"valid_pixel_count": count}
            if count != expected_valid_count:
                raise ProvenanceError(
                    f"band {name}: {count} finite VALID pixels != mask "
                    f"{expected_valid_count}")
            if count:
                percentiles = np.percentile(
                    values, [0, 1, 5, 50, 95, 99, 100])
                entry.update(dict(zip(
                    ("min", "p01", "p05", "median", "p95", "p99", "max"),
                    [float(v) for v in percentiles], strict=True)))
                entry["mean"] = float(values.mean())
                entry["std"] = float(values.std(ddof=0))
                entry["negative_fraction"] = float((values < 0).mean())
                entry["over_one_fraction"] = float((values > 1).mean())
                dn_like = float(((values > 500) & (values < 65535)).mean())
                abs_over = float((np.abs(values) > 1.5).mean())
                entry["fraction_abs_gt_1_5"] = abs_over
                entry["fraction_dn_like"] = dn_like
                median = entry["median"]
                if (dn_like > 0.5 or abs_over > 0.25
                        or abs(median) > 1.5):
                    scale_failures.append(
                        f"band {name}: median={median}, "
                        f"fraction_|v|>1.5={abs_over:.3f}, "
                        f"fraction_DN_like={dn_like:.3f}")
            else:
                for key in ("min", "p01", "p05", "median", "p95", "p99",
                            "max", "mean", "std", "negative_fraction",
                            "over_one_fraction", "fraction_abs_gt_1_5",
                            "fraction_dn_like"):
                    entry[key] = None
            stats["bands"][name] = entry
    stats["valid_pixel_count"] = expected_valid_count
    stats["scaling_check_pass"] = not scale_failures
    stats["scaling_failures"] = scale_failures
    if scale_failures:
        raise ProvenanceError(
            "reflectance scaling sanity failed: " + "; ".join(scale_failures))
    return stats


def assert_provenance_chain(manifest: dict[str, Any]) -> None:
    """Verify every link of the source-scene -> landed-file chain.

    Raises :class:`ProvenanceError` listing every broken link.
    """
    errors: list[str] = []
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        errors.append(f"manifest_version != {MANIFEST_VERSION}")

    request = manifest.get("export_request", {})
    selected = manifest.get("selected_scene_ids", [])
    candidates = {row.get("scene_id"): row
                  for row in manifest.get("candidate_scenes", [])}
    if not selected:
        errors.append("no selected_scene_ids")
    if list(request.get("source_scene_ids", ())) != list(selected):
        errors.append("export_request.source_scene_ids != selected_scene_ids")
    for scene_id in selected:
        row = candidates.get(scene_id)
        if row is None:
            errors.append(f"selected scene {scene_id} absent from candidates")
            continue
        if not row.get("acquisition_utc"):
            errors.append(f"scene {scene_id} missing acquisition_utc")
        if not row.get("product_id") or row.get("product_id") == "MISSING":
            errors.append(f"scene {scene_id} missing real product_id")

    grid = manifest.get("grid", {})
    for key in ("crs", "transform", "width", "height", "pixel_size_m",
                "bounds"):
        if key not in grid:
            errors.append(f"grid missing {key!r}")

    task = manifest.get("export_task", {})
    if not task.get("task_id"):
        errors.append("export_task.task_id missing")
    if task.get("state") != "COMPLETED":
        errors.append(f"export_task.state={task.get('state')} (need COMPLETED)")

    processing = manifest.get("processing_config", {})
    for key in ("reflectance_scale", "reflectance_offset", "masking",
                "band_order", "composite"):
        if key not in processing:
            errors.append(f"processing_config missing {key!r}")

    landed = manifest.get("landed_files", [])
    if not landed:
        errors.append("no landed_files")
    for record in landed:
        path = record.get("local_uri")
        if not path or not Path(path).is_file():
            errors.append(f"landed file missing on disk: {path}")
            continue
        if len(str(record.get("sha256", ""))) != 64:
            errors.append(f"{path}: sha256 malformed")
        elif sha256_file(path) != record["sha256"]:
            errors.append(f"{path}: sha256 mismatch on re-hash")
        if not isinstance(record.get("size_bytes"), int) or \
                record["size_bytes"] <= 0:
            errors.append(f"{path}: size_bytes invalid")
        if record.get("grid_verified") is not True:
            errors.append(f"{path}: grid_verified is not true")

    for section in ("project_id", "code", "environment"):
        if not manifest.get(section):
            errors.append(f"manifest missing {section!r} section")

    if errors:
        raise ProvenanceError("; ".join(errors))


__all__ = [
    "MANIFEST_VERSION",
    "ProvenanceError",
    "assert_grid_matches",
    "assert_provenance_chain",
    "git_context",
    "raster_grid_info",
    "reflectance_sanity",
    "reflectance_sanity_masked",
    "runtime_environment",
    "sha256_file",
    "valid_mask_info",
]
