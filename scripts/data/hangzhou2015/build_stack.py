"""Assemble the versioned Pilot-0 analysis-ready stack on the 30 m grid.

Outputs (work/ only; bytes never committed):
  pilot0_stack_30m.tif   11 float32 bands: B1..B7 SR (scaled), NDVI,
                         SAI, VV_dB, VH_dB
  pilot0_labels_30m.tif  uint8 bands: weak_mask, silver_2015 (0/1),
                         ignore_mask
  label_disagreement_30m.tif / silver_2015_30m.tif (from arbitrate_labels)
  pilot0_stack_v1.meta.json  band descriptions, scale, provenance pointers

Manifest (committed, checksums only):
  datasets/manifests/hangzhou2015_pilot0_v1.csv (+ .parquet)
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import numpy as np
import rasterio

STACK_BANDS = [
    ("l8_sr_B1_coast", "Landsat-8 C02 L2 SR B1 reflectance DN*2.75e-5-0.2; DN=0 fill"),
    ("l8_sr_B2_blue", "Landsat-8 C02 L2 SR B2 reflectance DN*2.75e-5-0.2; DN=0 fill"),
    ("l8_sr_B3_green", "Landsat-8 C02 L2 SR B3 reflectance DN*2.75e-5-0.2; DN=0 fill"),
    ("l8_sr_B4_red", "Landsat-8 C02 L2 SR B4 reflectance DN*2.75e-5-0.2; DN=0 fill"),
    ("l8_sr_B5_nir", "Landsat-8 C02 L2 SR B5 reflectance DN*2.75e-5-0.2; DN=0 fill"),
    ("l8_sr_B6_swir1", "Landsat-8 C02 L2 SR B6 reflectance DN*2.75e-5-0.2; DN=0 fill"),
    ("l8_sr_B7_swir2", "Landsat-8 C02 L2 SR B7 reflectance DN*2.75e-5-0.2; DN=0 fill"),
    ("ndvi", "legacy NDVI composite, bilinear-warped"),
    ("sai", "SAI=(Red-NIR)/NIR composite per Zuo et al. 2025; negated polarity"),
    ("s1_vv_db", "Sentinel-1 VV GRD composite dB, bilinear-warped to 30 m"),
    ("s1_vh_db", "Sentinel-1 VH GRD composite dB, bilinear-warped to 30 m"),
]
LABEL_BANDS = [
    ("weak_local_mask", "legacy Hangzhou mask c201511839DTSP_2.tif; WEAK tier"),
    ("silver_national_2015", "IGA national 2015 product window; SILVER tier"),
    ("ignore_mask", "boundary/invalid IGNORE for Pilot-0 validation"),
]

# schema.json-conformant manifest columns
MANIFEST_COLS = [
    "asset_id", "source", "provider", "sensor", "product",
    "acquisition_time", "year", "region", "bbox", "crs", "resolution",
    "bands", "label_type", "label_quality", "license", "permission",
    "local_uri", "remote_uri", "checksum", "provenance", "status", "notes",
]


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def read_one(path: Path, band: int = 1) -> np.ndarray[Any, Any]:
    with rasterio.open(path) as ds:
        return cast(np.ndarray[Any, Any], ds.read(band).astype("float32"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", type=Path, default=Path("work/hangzhou2015/v1"))
    ap.add_argument("--manifest-csv", type=Path,
                    default=Path("datasets/manifests/hangzhou2015_pilot0_v1.csv"))
    args = ap.parse_args(argv)
    wd = args.work_dir

    spec = json.loads((wd / "grid_spec.json").read_text())["grid_30m"]
    from rasterio.transform import Affine

    g30 = Affine(*spec["transform"])
    w, h = spec["width"], spec["height"]

    sr_path = wd / "l8_sr_30m.tif"
    with rasterio.open(sr_path) as ds:
        sr = ds.read().astype("float32")
    ndvi = read_one(wd / "ndvi_30m.tif")
    sai = read_one(wd / "sai_30m.tif")
    vv = read_one(wd / "s1_vv_30m.tif")
    vh = read_one(wd / "s1_vh_30m.tif")
    stack = np.concatenate([sr, ndvi[None], sai[None], vv[None], vh[None]])

    stack_path = wd / "pilot0_stack_30m.tif"
    with rasterio.open(
        stack_path, "w", driver="GTiff", width=w, height=h, count=11,
        dtype="float32", crs="EPSG:32651", transform=g30, nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(stack)
        for i, (name, desc) in enumerate(STACK_BANDS, start=1):
            dst.set_band_description(i, name)
            dst.update_tags(i, description=desc)

    weak = rasterio.open(wd / "label_mask_30m.tif").read(1)
    silver = rasterio.open(wd / "silver_2015_30m.tif").read(1)
    ignore = rasterio.open(wd / "ignore_30m.tif").read(1)
    labels_path = wd / "pilot0_labels_30m.tif"
    with rasterio.open(
        labels_path, "w", driver="GTiff", width=w, height=h, count=3,
        dtype="uint8", crs="EPSG:32651", transform=g30, nodata=127,
        compress="deflate",
    ) as dst:
        dst.write(np.stack([weak, silver, ignore]))
        for i, (name, desc) in enumerate(LABEL_BANDS, start=1):
            dst.set_band_description(i, name)
            dst.update_tags(i, description=desc)

    bbox = [g30.c, g30.f + h * g30.e, g30.c + w * g30.a, g30.f]
    meta = {
        "version": "v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 (py3.10 compat)
        "crs": "EPSG:32651",
        "grid_origin": [g30.c, g30.f],
        "pixel_size_m": 30.0,
        "width": w,
        "height": h,
        "bbox_utm51n": bbox,
        "data_bands": [{"band": i, "name": n, "description": d}
                       for i, (n, d) in enumerate(STACK_BANDS, 1)],
        "label_bands": [{"band": i, "name": n, "description": d}
                        for i, (n, d) in enumerate(LABEL_BANDS, 1)],
        "acquisition_dates": "UNKNOWN (no TIFF tags; see date_recovery.json)",
        "composite_scene_ids": "MISSING_EVIDENCE",
        "provenance_reports": [
            "artifacts/audit/pilot0/date_recovery.json",
            "artifacts/audit/pilot0/coregistration.json",
            "artifacts/audit/pilot0/label_arbitration.json",
        ],
    }
    (wd / "pilot0_stack_v1.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # --- manifest ----------------------------------------------------------
    rows: list[dict[str, Any]] = []

    def row(asset_id: str, path: Path, bands: str, label_type: str,
            label_quality: str, notes: str, sensor: str = "UNKNOWN",
            license_: str = "UNKNOWN", resolution: str = "30 m",
            acquisition: str = "UNKNOWN") -> None:
        rows.append({
            "asset_id": asset_id,
            "source": "legacy_recovery_work_product",
            "provider": "Spartina Earth Pilot-0 (derived; read-only legacy inputs)",
            "sensor": sensor,
            "product": path.name,
            "acquisition_time": acquisition,
            "year": 2015,
            "region": "Hangzhou Bay (121.018-121.418E, 30.266-30.396N)",
            "bbox": json.dumps(bbox),
            "crs": "EPSG:32651",
            "resolution": resolution,
            "bands": bands,
            "label_type": label_type,
            "label_quality": label_quality,
            "license": license_,
            "permission": "derived for internal research; upstream license applies",
            "local_uri": str(path),
            "remote_uri": None,
            "checksum": f"sha256:{sha256_of(path)}",
            "provenance": ("scripts/data/hangzhou2015/{coregister.py,"
                           "arbitrate_labels.py,build_stack.py}; inputs in "
                           "old datasets/Spartina/HangZhouBay (read-only) and "
                           "30mSpartinaChina (read-only)"),
            "status": "ANALYSIS_READY_PILOT0_V1",
            "notes": notes,
        })

    silver_license = "restrictive (geodata.cn IGA product; see DATA_PROVENANCE_AND_LICENSE.md)"
    row("hz2015-v1-stack", stack_path,
        ",".join(n for n, _ in STACK_BANDS), "none", "UNLABELED",
        "NaN = no valid optical/SAR value; acquisition dates UNKNOWN",
        sensor="Landsat-8 + Sentinel-1 + legacy indices")
    row("hz2015-v1-labels", labels_path,
        ",".join(n for n, _ in LABEL_BANDS), "raster_binary", "MIXED",
        "weak=WEAK local legacy mask; silver=SILVER national 2015 window; "
        "neither is GOLD; ignore=boundary/invalid",
        license_=silver_license)
    row("hz2015-v1-disagreement", wd / "label_disagreement_30m.tif",
        "code 0 neither,1 both,2 silver_only,3 weak_only",
        "raster_disagreement_code", "DERIVED",
        "background of national product treated negative; domain semantics "
        "MISSING_EVIDENCE", license_=silver_license)
    row("hz2015-v1-silver-window", wd / "silver_2015_30m.tif",
        "binary presence", "raster_binary", "SILVER",
        "NN-warped EPSG:32650->32651 window of IGA national 2015 product",
        sensor="Landsat (national product)", license_=silver_license)
    row("hz2015-v1-s1-10m-vv", wd / "s1_vv_10m.tif", "vv_db", "none",
        "UNLABELED", "S1 VV on 10 m analysis-density grid",
        sensor="Sentinel-1 GRD", resolution="10 m")
    row("hz2015-v1-s1-10m-vh", wd / "s1_vh_10m.tif", "vh_db", "none",
        "UNLABELED", "S1 VH on 10 m analysis-density grid",
        sensor="Sentinel-1 GRD", resolution="10 m")

    args.manifest_csv.parent.mkdir(parents=True, exist_ok=True)
    import csv

    with open(args.manifest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLS)
        writer.writeheader()
        writer.writerows(rows)
    try:
        import pandas as pd

        pd.DataFrame(rows, columns=MANIFEST_COLS).to_parquet(
            args.manifest_csv.with_suffix(".parquet"), index=False)
    except ImportError:
        pass
    print(f"stack: {stack_path} ({stack.shape})")
    print(f"labels: {labels_path}")
    print(f"manifest: {args.manifest_csv} ({len(rows)} assets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
