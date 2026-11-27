"""Fetch target-independent Murray/JRC cell-context summaries from GEE.

CONTEXT LAYERS ONLY.  These summaries are never Spartina labels and are
never inputs to domain-membership decisions (see
``src/spartina/data/national/domain_membership.py``).  Membership is
computed first; context is joined afterwards as descriptive columns.

Hard constraints honoured here:

* no national image/array export -- only scalar per-cell summaries are
  downloaded through batched server-side ``reduceRegions`` calls;
* analysis scale is 30,000 m (bestEffort convention of the Issue #16
  chronic-zero audit): coarse presence/support indicators, not precise
  area measurements;
* resumable: completed cells are skipped on rerun;
* no credentials in the repository; project comes from
  ``SPARTINA_GEE_PROJECT`` (see ``spartina.data.gee.auth``).

Outputs (work/ -- never committed):
    work/national/domain_v1/context_murray_v0.csv
    work/national/domain_v1/context_jrc_v0.csv

The audit script joins these onto the membership candidate manifest and
emits ``datasets/manifests/china_intertidal_context_v0.{csv,parquet}``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from spartina.data.gee.auth import initialize
from spartina.data.national import geometry as nat_geom

REPO_ROOT = Path(__file__).resolve().parents[3]
DOMAIN_DIR = REPO_ROOT / "work/national/domain"
WORK_DIR = REPO_ROOT / "work/national/domain_v1"
DOCS_NATIONAL = REPO_ROOT / "docs/data/national"

MEMBERSHIP_WIDTH = 10_000
ANALYSIS_SCALE_M = 30_000
BATCH_SIZE = 40

MURRAY_ASSET = "UQ/murray/Intertidal/v1_1/global_intertidal"
JRC_ASSET = "JRC/GSW1_4/GlobalSurfaceWater"

# License/version facts verified against the GEE catalog pages on the
# access date recorded in the passport (see write_passport).
MURRAY_LICENSE = "CC BY 4.0"
MURRAY_CATALOG_URL = (
    "https://developers.google.com/earth-engine/datasets/catalog/"
    "UQ_murray_Intertidal_v1_1_global_intertidal"
)
MURRAY_DOI = "10.1038/s41586-018-0805-8"
JRC_LICENSE = "Copernicus Programme, free of charge without restriction"
JRC_CATALOG_URL = (
    "https://developers.google.com/earth-engine/datasets/catalog/"
    "JRC_GSW1_4_GlobalSurfaceWater"
)
JRC_DOI = "10.1038/nature20584"
ACCESS_DATE = "2026-10-04"

CONTEXT_ROLE = "MURRAY_JRC_CONTEXT_ONLY_NEVER_A_SPARTINA_LABEL"

MURRAY_COLUMNS = [
    "cell_id",
    "murray_intertidal_present_30km",
    "murray_intertidal_coarse_pixel_count",
    "murray_intertidal_coarse_area_m2",
    "murray_intertidal_coarse_fraction",
    "murray_scale_m",
    "murray_status",
]
JRC_COLUMNS = [
    "cell_id",
    "jrc_occurrence_mean_pct",
    "jrc_water_ever_area_m2",
    "jrc_water_ever_fraction",
    "jrc_seasonality_mean_months",
    "jrc_scale_m",
    "jrc_status",
]


class CallLedger:
    """Counts server round-trips for the provenance ledger."""

    def __init__(self) -> None:
        self.metadata_calls = 0
        self.reduce_calls = 0
        self.failed_calls = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "metadata_getinfo_calls": self.metadata_calls,
            "reduce_regions_getinfo_calls": self.reduce_calls,
            "failed_getinfo_calls": self.failed_calls,
        }


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cells() -> gpd.GeoDataFrame:
    """Load the immutable W10 registry and rebuild Albers polygons."""
    frame = pd.read_csv(DOMAIN_DIR / f"cells_china_albers_W{MEMBERSHIP_WIDTH}.csv")
    width = MEMBERSHIP_WIDTH
    geometries = [
        box(
            int(row.col) * width,
            int(row.row) * width,
            (int(row.col) + 1) * width,
            (int(row.row) + 1) * width,
        )
        for row in frame.itertuples(index=False)
    ]
    cells = gpd.GeoDataFrame(frame, geometry=geometries, crs=nat_geom.CHINA_ALBERS_CRS)
    return cells.to_crs(4326)


def _feature_collection(ee: Any, batch: gpd.GeoDataFrame) -> Any:
    features = [
        ee.Feature(ee.Geometry(geom.__geo_interface__), {"cell_id": cell_id})
        for cell_id, geom in zip(batch["cell_id"], batch.geometry, strict=True)
    ]
    return ee.FeatureCollection(features)


def _getinfo_with_retry(
    ee_obj: Any,
    ledger: CallLedger,
    *,
    reducer_call: bool = False,
    attempts: int = 4,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            value = ee_obj.getInfo()
            if reducer_call:
                ledger.reduce_calls += 1
            else:
                ledger.metadata_calls += 1
            return value
        except Exception as exc:  # noqa: BLE001 -- retry, then surface
            last_exc = exc
            ledger.failed_calls += 1
            if attempt == attempts:
                break
            time.sleep(min(2**attempt, 60))
    assert last_exc is not None
    raise last_exc


def fetch_murray(
    ee: Any, cells: gpd.GeoDataFrame, out_path: Path, ledger: CallLedger
) -> int:
    """Ever-intertidal (1984-2016, any of 11 epochs) coarse area fraction."""
    collection = ee.ImageCollection(MURRAY_ASSET)
    n_tiles = int(_getinfo_with_retry(collection.size(), ledger))
    intertidal = (
        collection.max()
        .select("classification")
        .bitwiseAnd(1)
        .eq(1)
    )
    area_image = (
        ee.Image.pixelArea()
        .updateMask(intertidal)
        .rename("intertidal_area")
    )
    # 30 km scale (Issue #16 audit convention): this is a COARSE SUPPORT
    # INDICATOR ("any tidal-flat mapping within ~30 km weighting"), not an
    # area measurement -- fractions can exceed 1 from coarse weighting.
    reducer = ee.Reducer.sum().combine(ee.Reducer.count(), sharedInputs=True)

    _drop_error_rows(out_path, "murray_status")
    done = _done_ids(out_path)
    write_header = not out_path.exists()
    with out_path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MURRAY_COLUMNS)
        if write_header:
            writer.writeheader()
        pending = cells[~cells["cell_id"].isin(done)]
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending.iloc[start : start + BATCH_SIZE]
            fc = _feature_collection(ee, batch)
            try:
                result = _getinfo_with_retry(
                    area_image.reduceRegions(
                        collection=fc,
                        reducer=reducer,
                        scale=ANALYSIS_SCALE_M,
                        tileScale=4,
                    ),
                    ledger,
                    reducer_call=True,
                )
                by_id = {
                    str(f["properties"]["cell_id"]): f["properties"]
                    for f in result["features"]
                }
                rows = []
                for cell_id in batch["cell_id"]:
                    props = by_id.get(str(cell_id), {})
                    # reduceRegions names single-band combined outputs
                    # "sum" / "count" rather than "<band>_<reducer>".
                    area = props.get("intertidal_area_sum", props.get("sum"))
                    count = props.get(
                        "intertidal_area_count", props.get("count")
                    )
                    area_f = float(area) if area is not None else 0.0
                    count_f = float(count) if count is not None else 0.0
                    rows.append(
                        {
                            "cell_id": str(cell_id),
                            "murray_intertidal_present_30km": int(count_f > 0),
                            "murray_intertidal_coarse_pixel_count": count_f,
                            "murray_intertidal_coarse_area_m2": round(area_f, 1),
                            "murray_intertidal_coarse_fraction": round(
                                area_f / (MEMBERSHIP_WIDTH**2), 6
                            ),
                            "murray_scale_m": ANALYSIS_SCALE_M,
                            "murray_status": "OK",
                        }
                    )
            except Exception as exc:  # noqa: BLE001 -- keep provenance honest
                rows = [
                    {
                        "cell_id": str(cell_id),
                        "murray_intertidal_present_30km": "",
                        "murray_intertidal_coarse_pixel_count": "",
                        "murray_intertidal_coarse_area_m2": "",
                        "murray_intertidal_coarse_fraction": "",
                        "murray_scale_m": ANALYSIS_SCALE_M,
                        "murray_status": f"ERROR:{type(exc).__name__}",
                    }
                    for cell_id in batch["cell_id"]
                ]
            writer.writerows(rows)
            handle.flush()
            print(
                f"murray batch {start // BATCH_SIZE + 1}/"
                f"{(len(pending) + BATCH_SIZE - 1) // BATCH_SIZE} "
                f"({len(batch)} cells)"
            )
    print(f"Murray asset tiles: {n_tiles}")
    return n_tiles


def fetch_jrc(
    ee: Any, cells: gpd.GeoDataFrame, out_path: Path, ledger: CallLedger
) -> None:
    """Mean occurrence, ever-water fraction, mean seasonality (coarse).

    Explicitly NOT a tide proxy: JRC surface water does not distinguish
    tidal inundation from permanent water.
    """
    gsw = ee.Image(JRC_ASSET)
    water_ever_area = (
        ee.Image.pixelArea()
        .updateMask(gsw.select("max_extent").eq(1))
        .rename("water_ever_area")
    )
    image = gsw.select(["occurrence", "seasonality"]).addBands(water_ever_area)
    reducer = ee.Reducer.mean().combine(ee.Reducer.sum(), sharedInputs=True)

    _drop_error_rows(out_path, "jrc_status")
    done = _done_ids(out_path)
    write_header = not out_path.exists()
    with out_path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=JRC_COLUMNS)
        if write_header:
            writer.writeheader()
        pending = cells[~cells["cell_id"].isin(done)]
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending.iloc[start : start + BATCH_SIZE]
            fc = _feature_collection(ee, batch)
            try:
                result = _getinfo_with_retry(
                    image.reduceRegions(
                        collection=fc,
                        reducer=reducer,
                        scale=ANALYSIS_SCALE_M,
                        tileScale=4,
                    ),
                    ledger,
                    reducer_call=True,
                )
                by_id = {
                    str(f["properties"]["cell_id"]): f["properties"]
                    for f in result["features"]
                }
                rows = []
                for cell_id in batch["cell_id"]:
                    props = by_id.get(str(cell_id), {})
                    area = props.get("water_ever_area_sum")
                    area_f = float(area) if area is not None else 0.0
                    rows.append(
                        {
                            "cell_id": str(cell_id),
                            "jrc_occurrence_mean_pct": _round(props.get("occurrence_mean")),
                            "jrc_water_ever_area_m2": round(area_f, 1),
                            "jrc_water_ever_fraction": round(
                                area_f / (MEMBERSHIP_WIDTH**2), 6
                            ),
                            "jrc_seasonality_mean_months": _round(
                                props.get("seasonality_mean")
                            ),
                            "jrc_scale_m": ANALYSIS_SCALE_M,
                            "jrc_status": "OK",
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                rows = [
                    {
                        "cell_id": str(cell_id),
                        "jrc_occurrence_mean_pct": "",
                        "jrc_water_ever_area_m2": "",
                        "jrc_water_ever_fraction": "",
                        "jrc_seasonality_mean_months": "",
                        "jrc_scale_m": ANALYSIS_SCALE_M,
                        "jrc_status": f"ERROR:{type(exc).__name__}",
                    }
                    for cell_id in batch["cell_id"]
                ]
            writer.writerows(rows)
            handle.flush()
            print(
                f"jrc batch {start // BATCH_SIZE + 1}/"
                f"{(len(pending) + BATCH_SIZE - 1) // BATCH_SIZE} "
                f"({len(batch)} cells)"
            )


def _round(value: Any, digits: int = 4) -> float | str:
    if value is None:
        return ""
    return round(float(value), digits)


def _drop_error_rows(path: Path, status_col: str) -> None:
    """Remove failed rows so a resume retry does not duplicate cell_id."""
    if not path.exists():
        return
    frame = pd.read_csv(path)
    ok = frame[frame[status_col] == "OK"]
    ok.to_csv(path, index=False)


def _done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    frame = pd.read_csv(path)
    status_col = [c for c in frame.columns if c.endswith("_status")]
    if not status_col:
        return set()
    ok = frame[frame[status_col[0]] == "OK"]
    return set(ok["cell_id"].astype(str))


def write_passport(murray_path: Path, jrc_path: Path) -> Path:
    payload = {
        "artifact": "china_domain_v1_context_passport",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "access_date": ACCESS_DATE,
        "git_commit": _git_commit(),
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "context_role": CONTEXT_ROLE,
        "not_a_tide_proxy": (
            "JRC Global Surface Water reports all surface water; it does "
            "not distinguish tidal inundation. Murray intertidal covers "
            "1984-2016 only. Neither layer feeds membership or labels."
        ),
        "sources": [
            {
                "name": "Murray Global Intertidal Change Classification v1.1",
                "gee_asset": MURRAY_ASSET,
                "version": "v1_1",
                "native_resolution_m": 30,
                "temporal_coverage": "11 three-year epochs, 1984-2016",
                "band_used": (
                    "classification bit 0 (1=intertidal), max over 11 epochs; "
                    "30 km scale coarse support indicator (count + weighted "
                    "area), NOT a precise intertidal area measurement"
                ),
                "license": MURRAY_LICENSE,
                "catalog_url": MURRAY_CATALOG_URL,
                "citation_doi": MURRAY_DOI,
                "output_csv": str(murray_path.relative_to(REPO_ROOT)),
                "output_sha256": _sha256(murray_path),
            },
            {
                "name": "JRC Global Surface Water Mapping Layers v1.4",
                "gee_asset": JRC_ASSET,
                "version": "v1.4 (1_4)",
                "native_resolution_m": 30,
                "temporal_coverage": "1984-2021",
                "bands_used": "occurrence, seasonality, max_extent",
                "license": JRC_LICENSE,
                "attribution_required": "Source: EC JRC/Google",
                "catalog_url": JRC_CATALOG_URL,
                "citation_doi": JRC_DOI,
                "output_csv": str(jrc_path.relative_to(REPO_ROOT)),
                "output_sha256": _sha256(jrc_path),
            },
        ],
    }
    path = DOCS_NATIONAL / "DOMAIN_V1_CONTEXT_PASSPORT_v0.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {path}")
    return path


def write_ledger(
    ledger: CallLedger,
    n_cells: int,
    murray_tiles: int | None,
    murray_path: Path,
    jrc_path: Path | None,
) -> Path:
    import math

    murray_rows = (
        len(pd.read_csv(murray_path)) if murray_path.exists() else 0
    )
    jrc_rows = len(pd.read_csv(jrc_path)) if jrc_path and jrc_path.exists() else 0
    batches = math.ceil(n_cells / BATCH_SIZE)
    payload = {
        "artifact": "china_domain_v1_context_fetch_ledger",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "access_date": ACCESS_DATE,
        "git_commit": _git_commit(),
        "cells_requested": n_cells,
        "batch_size": BATCH_SIZE,
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "murray_tiles_in_asset": murray_tiles,
        "murray_rows_written": murray_rows,
        "jrc_rows_written": jrc_rows,
        "resumable": (
            "fetches are resumable; gee_call_counts below records THIS "
            "invocation only. Both datasets were fetched on the access "
            "date (Murray was refetched once after a property-name fix)."
        ),
        "gee_call_counts_this_invocation": ledger.to_dict(),
        "full_clean_run_expected_calls": {
            "metadata_getinfo_calls": 1,
            "reduce_regions_getinfo_calls": 2 * batches,
        },
        "exports": "scalar per-cell summaries only; no national image export",
        "gee_project_source": "SPARTINA_GEE_PROJECT env var (value never recorded)",
    }
    path = DOCS_NATIONAL / "DOMAIN_V1_CONTEXT_FETCH_LEDGER_v0.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-cells",
        type=int,
        default=None,
        help="smoke-test limit (processes the first N pending cells)",
    )
    parser.add_argument(
        "--skip-murray", action="store_true", help="fetch JRC only"
    )
    parser.add_argument(
        "--skip-jrc", action="store_true", help="fetch Murray only"
    )
    args = parser.parse_args()

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_NATIONAL.mkdir(parents=True, exist_ok=True)

    initialize()
    import ee  # imported after credential/project validation

    cells = load_cells()
    if args.max_cells is not None:
        cells = cells.iloc[: args.max_cells]
    print(f"cells in scope: {len(cells)}")

    murray_path = WORK_DIR / "context_murray_v0.csv"
    jrc_path = WORK_DIR / "context_jrc_v0.csv"
    ledger = CallLedger()
    murray_tiles: int | None = None

    if not args.skip_murray:
        murray_tiles = fetch_murray(ee, cells, murray_path, ledger)
    if not args.skip_jrc:
        fetch_jrc(ee, cells, jrc_path, ledger)

    if murray_path.exists() and jrc_path.exists():
        murray = pd.read_csv(murray_path)
        jrc = pd.read_csv(jrc_path)
        m_errors = (murray["murray_status"] != "OK").sum()
        j_errors = (jrc["jrc_status"] != "OK").sum()
        if m_errors or j_errors:
            raise SystemExit(
                f"context fetch has error rows (murray={m_errors}, jrc={j_errors}); "
                "rerun to resume and retry, or investigate before proceeding"
            )
        write_passport(murray_path, jrc_path)
    write_ledger(ledger, len(cells), murray_tiles, murray_path, jrc_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
