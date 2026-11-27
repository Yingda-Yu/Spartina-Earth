"""Build the machine-generated asset manifest for ``old datasets/``.

Outputs one row per on-disk file as both CSV and Parquet:

    datasets/manifests/old_assets.csv
    datasets/manifests/old_assets.parquet

Rules
-----
* Read-only: the scanned tree is never modified.
* SHA-256 is computed ONLY for files the transfer report marks
  STABLE_CANDIDATE. Everything else gets ``sha256 = null`` and
  ``transfer_status = PENDING_TRANSFER``.
* Semantic columns (source, provider, sensor, year, label tier, license...)
  default to UNKNOWN; they are filled only from direct file bytes/metadata,
  never inferred from a filename's similarity to a paper or product.
* Raster/vector metadata comes from rasterio/fiona metadata calls only;
  pixel statistics belong to inspect_raster.py and are never read here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UNKNOWN = "UNKNOWN"

COLUMNS = [
    "asset_id",
    "relative_path",
    "filename",
    "extension",
    "size_bytes",
    "mtime_utc",
    "transfer_status",
    "sha256",
    "asset_type",
    "source",
    "provider",
    "author_or_owner",
    "project_origin",
    "year",
    "acquisition_start",
    "acquisition_end",
    "sensor",
    "product",
    "modality",
    "region_name",
    "bbox",
    "crs",
    "pixel_size_x",
    "pixel_size_y",
    "width",
    "height",
    "band_count",
    "band_names",
    "dtype",
    "nodata",
    "feature_count",
    "geometry_type",
    "label_role",
    "label_quality",
    "license",
    "permission_status",
    "citation",
    "provenance_status",
    "candidate_use",
    "known_issues",
    "notes",
]

# Compound suffixes must be checked before single extensions.
_COMPOUND = {".tar.gz": "archive_tar_gz", ".shp.xml": "shapefile_metadata_xml"}

_EXTENSION_TYPE = {
    ".tif": "geotiff",
    ".tiff": "geotiff",
    ".jp2": "jpeg2000",
    ".shp": "shapefile",
    ".dbf": "shapefile_sidecar_dbf",
    ".shx": "shapefile_sidecar_shx",
    ".prj": "shapefile_sidecar_prj",
    ".cpg": "shapefile_sidecar_cpg",
    ".sbn": "shapefile_sidecar_sbn",
    ".sbx": "shapefile_sidecar_sbx",
    ".fix": "shapefile_sidecar_fix",
    ".gpkg": "geopackage",
    ".geojson": "geojson",
    ".csv": "csv",
    ".json": "json",
    ".npy": "numpy_npy",
    ".npz": "numpy_npz",
    ".pt": "checkpoint_pt",
    ".pth": "checkpoint_pth",
    ".ckpt": "checkpoint_ckpt",
    ".h5": "hdf5",
    ".hdf5": "hdf5",
    ".docx": "docx",
    ".pdf": "pdf",
    ".png": "image_png",
    ".zip": "archive_zip",
    ".rar": "archive_rar",
    ".tar": "archive_tar",
    ".tgz": "archive_tgz",
    ".7z": "archive_7z",
    ".tfw": "worldfile",
    ".ovr": "raster_overview",
    ".aux": "aux_metadata",
    ".xml": "xml_metadata",
    ".exe": "windows_executable",
    ".lock": "lock_file",
    ".md": "markdown",
    ".txt": "text",
}


def classify(name: str) -> tuple[str, str]:
    """Return (asset_type, extension) using compound-aware suffix matching."""
    lower = name.lower()
    for suffix, kind in _COMPOUND.items():
        if lower.endswith(suffix):
            return kind, suffix
    if lower.endswith(".aux.xml"):
        return "gdal_aux_xml", ".aux.xml"
    if lower.endswith(".vat.dbf"):
        return "raster_vat_dbf", ".vat.dbf"
    stem = Path(lower)
    ext = stem.suffix
    return _EXTENSION_TYPE.get(ext, "other"), ext


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def load_transfer_state(path: Path | None) -> dict[str, str]:
    """Map relative_path -> transfer_status from a detect_transfer_state report."""
    if path is None:
        return {}
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return {f["relative_path"]: f["transfer_status"] for f in payload.get("files", [])}


def _epsg_code(crs: Any) -> str | None:
    try:
        epsg = crs.to_epsg()
    except Exception:  # noqa: BLE001 - metadata probing must be defensive
        return None
    return f"EPSG:{epsg}" if epsg else None


def raster_metadata(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        import rasterio
    except ImportError:
        return {}, "rasterio not available in this interpreter"
    try:
        with rasterio.open(path) as ds:
            crs = ds.crs
            crs_str = _epsg_code(crs) if crs else None
            if crs_str is None and crs is not None:
                crs_str = "CRS_WKT_PRESENT_EPSG_UNKNOWN"
            descriptions = [
                (desc if isinstance(desc, str) and desc else UNKNOWN)
                for desc in ds.descriptions
            ]
            return {
                "crs": crs_str or UNKNOWN,
                "pixel_size_x": ds.transform.a,
                "pixel_size_y": abs(ds.transform.e),
                "width": ds.width,
                "height": ds.height,
                "band_count": ds.count,
                "band_names": json.dumps(descriptions, ensure_ascii=False),
                "dtype": ",".join(sorted(set(ds.dtypes))),
                "nodata": ds.nodata if ds.nodata is not None else UNKNOWN,
                "bbox": json.dumps([round(v, 8) for v in ds.bounds]),
            }, None
    except Exception as exc:  # noqa: BLE001
        return {}, f"rasterio open failed: {type(exc).__name__}: {exc}"


def vector_metadata(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        import fiona
    except ImportError:
        return {}, "fiona not available in this interpreter"
    try:
        with fiona.open(path) as collection:
            crs = collection.crs
            epsg = None
            try:
                epsg = crs.to_epsg()
            except Exception:  # noqa: BLE001
                epsg = None
            geom_types = sorted({
                record["geometry"]["type"]
                for record in collection
                if record.get("geometry") is not None
            })
            return {
                "crs": f"EPSG:{epsg}" if epsg else (UNKNOWN if crs is None else "CRS_WKT_PRESENT"),
                "feature_count": len(collection),
                "geometry_type": ",".join(geom_types) if geom_types else UNKNOWN,
                "bbox": json.dumps([round(v, 8) for v in collection.bounds]),
            }, None
    except Exception as exc:  # noqa: BLE001
        return {}, f"fiona open failed: {type(exc).__name__}: {exc}"


def build_rows(root: Path, statuses: dict[str, str], do_hash: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        st = path.stat()
        asset_type, ext = classify(path.name)
        stable = statuses.get(rel) == "STABLE_CANDIDATE"
        transfer_status = "STABLE_CANDIDATE" if stable else "PENDING_TRANSFER"
        digest = sha256_file(path) if (do_hash and stable) else None
        notes: list[str] = []
        row: dict[str, Any] = {key: UNKNOWN for key in COLUMNS}
        row.update(
            asset_id=(f"old-{digest[:12]}" if digest else f"old-pending-{rel}"),
            relative_path=rel,
            filename=path.name,
            extension=ext,
            size_bytes=st.st_size,
            mtime_utc=datetime.fromtimestamp(
                st.st_mtime, tz=timezone.utc  # noqa: UP017 (system Python 3.10 compat)
            ).isoformat(timespec="seconds"),
            transfer_status=transfer_status,
            sha256=digest,
            asset_type=asset_type,
        )
        if asset_type == "geotiff":
            meta, issue = raster_metadata(path)
            row.update(meta)
            if issue:
                notes.append(issue)
        elif asset_type in {"shapefile", "geopackage", "geojson"}:
            meta, issue = vector_metadata(path)
            row.update(meta)
            if issue:
                notes.append(issue)
        if not stable:
            notes.append("not hashed/audited: transfer not proven stable")
        row["notes"] = " | ".join(notes) if notes else ""
        rows.append(row)
    # Byte-identical duplicates share an asset_id; surface that explicitly.
    seen: dict[str, str] = {}
    for row in rows:
        if row["sha256"] is None:
            continue
        if row["sha256"] in seen:
            row["known_issues"] = (
                f"byte-identical duplicate of {seen[row['sha256']]}"
            )
        else:
            seen[row["sha256"]] = row["relative_path"]
    return rows


NUMERIC_COLUMNS = [
    "size_bytes",
    "pixel_size_x",
    "pixel_size_y",
    "width",
    "height",
    "band_count",
    "feature_count",
    "nodata",
]


def write_outputs(rows: list[dict[str, Any]], csv_out: Path, parquet_out: Path | None) -> None:
    import pandas as pd

    csv_out.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=COLUMNS)
    # Numeric columns mix UNKNOWN sentinel strings with numbers; coerce them
    # to a nullable numeric dtype so Parquet gets a legal schema.
    for col in NUMERIC_COLUMNS:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("Float64")
    frame.to_csv(csv_out, index=False)
    if parquet_out is not None:
        try:
            frame.to_parquet(parquet_out, index=False)
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: parquet write failed ({exc}); CSV still written", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("old datasets"))
    parser.add_argument("--transfer-state", type=Path, default=None)
    parser.add_argument("--out-csv", type=Path, default=Path("datasets/manifests/old_assets.csv"))
    parser.add_argument(
        "--out-parquet",
        type=Path,
        default=Path("datasets/manifests/old_assets.parquet"),
    )
    parser.add_argument("--no-hash", action="store_true", help="skip SHA-256 even for stable files")
    args = parser.parse_args(argv)

    statuses = load_transfer_state(args.transfer_state)
    rows = build_rows(args.root, statuses, do_hash=not args.no_hash)
    write_outputs(rows, args.out_csv, args.out_parquet)
    stable = sum(r["transfer_status"] == "STABLE_CANDIDATE" for r in rows)
    print(
        json.dumps(
            {
                "files": len(rows),
                "stable_hashed": stable,
                "pending": len(rows) - stable,
                "csv": str(args.out_csv),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
