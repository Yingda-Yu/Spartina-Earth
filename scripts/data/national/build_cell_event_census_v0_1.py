"""Build the R1 (v0_1) national census four-products from local caches.

No GEE calls. Inputs (all under ignored ``work/`` tree):

* v0 scene caches ``work/national/census/scene_census_<sensor>_v0.parquet``;
* R1 affected-range incremental caches
  ``work/national/census_r1/incremental/scene_census_<sensor>_incremental_v0_1.parquet``;
* R1 2026 YTD optical caches
  ``work/national/census_r1/scene_census_<sensor>_2026ytd_v0_1.parquet``;
* R1 L7 Extended Science Mission ACTUAL geometry
  ``work/national/census_r1/l7_extended_geometry_v0_1.parquet``;
* R1 unfiltered S1 D-level cache
  ``work/national/census_r1/s1_grd_unfiltered_v0_1.parquet``;
* footprint indices v0_1 and the W10 cell list.

Outputs (bytes under ``work/``; fingerprints recorded in tracked docs):

* ``china_eo_scene_census_v0_1.parquet``;
* ``china_cell_event_census_v0_1.parquet``;
* ``china_eo_availability_v0_1.csv`` (2026 rows are PARTIAL_YEAR);
* ``china_eo_data_gap_matrix_v0_1.csv`` (full years only);
* ``china_eo_census_report_v0_1.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import numpy as np
import pandas as pd

from spartina.data.national.census_join import (
    FULL_COVER,
    L7_EXTENDED_BASIS,
    build_availability,
    cell_events_union,
    chronic_gap_flags,
    join_landsat_family,
    join_s1_scenes,
    join_s2_granules,
    load_cells,
)
from spartina.data.national.footprints import (
    L7_STANDBY_ORBIT_LOWERING,
    l7_era,
    l7_footprint_is_nominal_wrs2,
    mission_phase,
)
from spartina.data.national.footprints import (
    default_production_eligible as is_default_production_eligible,
)
from spartina.data.national.scene_events import (
    _platform_s1,
    event_id,
    season_tag,
)

LANDSAT_SENSORS = ("landsat5", "landsat7", "landsat8", "landsat9")
CUTOFF_UTC = "2026-10-03T00:00:00Z"
PARTIAL_YEARS = frozenset({2026})
YEAR_RE = re.compile(r"(\d{4})")


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _read_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path)
    return cast(pd.DataFrame, frame)


def _failed_scopes(ledger_paths: list[Path]) -> set[str]:
    """A sensor:year is failed only when EVERY call for it failed.

    Handles yearly, half-year and quarterly scopes; any successful call
    (rescue split) means the year is covered.
    """
    seen: dict[tuple[str, int], set[bool]] = {}
    for ledger_path in ledger_paths:
        if not ledger_path.exists():
            continue
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        for call in ledger.get("calls", []):
            scope = str(call.get("scope", ""))
            if ":" not in scope:
                continue
            sensor, token = scope.split(":", 1)
            match = YEAR_RE.search(token)
            if match is None:
                continue
            key = (sensor, int(match.group(1)))
            seen.setdefault(key, set()).add(bool(call.get("ok", True)))
    return {
        f"{sensor}:{year}"
        for (sensor, year), states in seen.items()
        if states == {False}
    }


def _annotate_year_status(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["year_status"] = np.where(
        frame["year"].isin(PARTIAL_YEARS), "PARTIAL_YEAR", "FULL_YEAR"
    )
    frame["census_cutoff_utc"] = None
    frame.loc[
        frame["year_status"] == "PARTIAL_YEAR", "census_cutoff_utc"
    ] = CUTOFF_UTC
    return frame


def _add_phase_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    utc = pd.to_datetime(frame["utc"], utc=True, format="ISO8601")
    sensor = cast(pd.Series, frame["sensor"]).astype(str)
    phases = [
        mission_phase(s, t) for s, t in zip(sensor.tolist(), utc, strict=True)
    ]
    frame["mission_phase"] = phases
    frame["default_production_eligible"] = [
        is_default_production_eligible(s, t)
        for s, t in zip(sensor.tolist(), utc, strict=True)
    ]
    return frame


def _build_landsat(
    sensor: str,
    v0_dir: Path,
    r1_dir: Path,
    frame_keys: set[tuple[int, int]],
) -> tuple[pd.DataFrame, int]:
    """Historical v0 + affected-range incremental + 2026 YTD."""
    frames = [_read_parquet(v0_dir / f"scene_census_{sensor}_v0.parquet")]
    frames[0]["source"] = "v0"
    incremental = _read_parquet(
        r1_dir / "incremental" / f"scene_census_{sensor}_incremental_v0_1.parquet"
    )
    if len(incremental):
        incremental = incremental.drop(
            columns=["year_status", "census_cutoff_utc"], errors="ignore"
        )
        incremental["source"] = "r1_incremental"
        frames.append(incremental)
    ytd = _read_parquet(r1_dir / f"scene_census_{sensor}_2026ytd_v0_1.parquet")
    if len(ytd):
        ytd = ytd[
            ytd.apply(
                lambda r: (int(r["wrs_path"]), int(r["wrs_row"])) in frame_keys,
                axis=1,
            )
        ].copy()
        ytd = ytd.drop(
            columns=["in_v0_index", "year_status", "census_cutoff_utc"],
            errors="ignore",
        )
        ytd["source"] = "r1_2026_ytd"
        frames.append(ytd)
    scenes = pd.concat(frames, ignore_index=True, sort=False)
    before = len(scenes)
    scenes = scenes.drop_duplicates(subset=["scene_id"], keep="first")
    dupes = before - len(scenes)
    if sensor == "landsat7":
        # Nominal WRS-2 join track only. Extended Science Mission rows
        # (>=2022-05-05) and the short 2022 standby/orbit-lowering gap
        # ride the separate native-geometry track built from the full R1
        # extended pull, which is a superset of the v0 extended rows.
        when = pd.to_datetime(cast(pd.Series, scenes["utc"]), utc=True)
        scenes = scenes[when.map(l7_footprint_is_nominal_wrs2)].copy()
    return cast(pd.DataFrame, scenes), dupes


def _preserved_l7_legacy_rows(
    v0_dir: Path, r1_dir: Path
) -> pd.DataFrame:
    """L7 non-nominal rows not covered by the R1 native-geometry pull.

    Mandate: all 20,187 v0 L7 rows are preserved. Extended Science
    Mission rows are carried by the full R1 geometry pull (verified
    superset of the v0 extended rows); this track retains anything left
    — in practice only the 2022-04-06..2022-05-04 standby/orbit-lowering
    rows — as metadata-only census rows (no geometry, no pairs).
    """
    legacy = _read_parquet(v0_dir / "scene_census_landsat7_v0.parquet")
    legacy = legacy.drop(columns=["source"], errors="ignore")
    when = pd.to_datetime(cast(pd.Series, legacy["utc"]), utc=True)
    non_nominal = legacy[~when.map(l7_footprint_is_nominal_wrs2)].copy()
    ext = cast(
        pd.DataFrame,
        gpd.read_parquet(r1_dir / "l7_extended_geometry_v0_1.parquet")[
            ["scene_id"]
        ],
    )
    covered = set(cast(pd.Series, ext["scene_id"]).astype(str))
    kept = non_nominal[
        ~cast(pd.Series, non_nominal["scene_id"]).astype(str).isin(covered)
    ].copy()
    kept = kept.drop(columns=["geometry"], errors="ignore")
    kept["source"] = "r1_l7_standby_preserved_no_native_geometry"
    eras = pd.to_datetime(cast(pd.Series, kept["utc"]), utc=True).map(l7_era)
    if len(kept) and not set(eras.unique()) <= {L7_STANDBY_ORBIT_LOWERING}:
        raise ValueError(
            "unexpected non-standby L7 legacy rows outside R1 geometry pull"
        )
    return cast(pd.DataFrame, kept)


def _build_s2(
    v0_dir: Path, r1_dir: Path, tile_keys: set[str]
) -> tuple[pd.DataFrame, int]:
    v0 = _read_parquet(v0_dir / "scene_census_sentinel2_v0.parquet")
    v0["source"] = "v0"
    frames = [v0]
    incremental = _read_parquet(
        r1_dir / "incremental" / "scene_census_sentinel2_incremental_v0_1.parquet"
    )
    if len(incremental):
        incremental = incremental.drop(
            columns=["year_status", "census_cutoff_utc"], errors="ignore"
        )
        incremental["source"] = "r1_incremental"
        frames.append(incremental)
    ytd = _read_parquet(r1_dir / "scene_census_sentinel2_2026ytd_v0_1.parquet")
    if len(ytd):
        ytd = ytd[ytd["mgrs_tile"].astype(str).isin(tile_keys)].copy()
        ytd = ytd.drop(
            columns=["in_v0_index", "year_status", "census_cutoff_utc"],
            errors="ignore",
        )
        ytd["source"] = "r1_2026_ytd"
        frames.append(ytd)
    scenes = pd.concat(frames, ignore_index=True, sort=False)
    before = len(scenes)
    scenes = scenes.drop_duplicates(subset=["system_index"], keep="first")
    return cast(pd.DataFrame, scenes), before - len(scenes)


def _build_s1(r1_dir: Path) -> gpd.GeoDataFrame:
    """D-level production-style universe: IW + VV|VH + intersects W10 cells."""
    raw = cast(gpd.GeoDataFrame, gpd.read_parquet(r1_dir / "s1_grd_unfiltered_v0_1.parquet"))
    keep = (
        (cast(pd.Series, raw["instrument_mode"]) == "IW")
        & (cast(pd.Series, raw["polarization"]) == "VV|VH")
        & (cast(pd.Series, raw["intersects_w10_cells"]) == True)  # noqa: E712
    )
    d_level = cast(gpd.GeoDataFrame, raw[keep].copy())
    utc = pd.to_datetime(cast(pd.Series, d_level["utc"]), utc=True, format="ISO8601")
    platforms = [_platform_s1(p) for p in cast(pd.Series, d_level["platform_number"])]
    built = pd.DataFrame(
        {
            "event_id": [
                event_id("sentinel1", str(s))
                for s in cast(pd.Series, d_level["scene_id"])
            ],
            "sensor": "sentinel1",
            "scene_id": cast(pd.Series, d_level["scene_id"]).astype(str).values,
            "utc": pd.Series(utc.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")).values,
            "year": cast(pd.Series, d_level["year"]).astype(int).values,
            "doy": cast(pd.Series, d_level["doy"]).astype(int).values,
            "season_tag": [season_tag(t.date()) for t in utc],
            "pass": cast(pd.Series, d_level["pass"]).astype(str).values,
            "relative_orbit": cast(pd.Series, d_level["relative_orbit"])
            .astype(int)
            .values,
            "orbit_start": cast(pd.Series, d_level["orbit_start"]).astype(int).values,
            "platform": platforms,
            "polarization": cast(pd.Series, d_level["polarization"]).astype(str).values,
            "instrument_mode": cast(pd.Series, d_level["instrument_mode"])
            .astype(str)
            .values,
            "footprint_sha256": cast(pd.Series, d_level["footprint_sha256"]).values,
            "min_lon": cast(pd.Series, d_level["min_lon"]).astype(float).values,
            "min_lat": cast(pd.Series, d_level["min_lat"]).astype(float).values,
            "max_lon": cast(pd.Series, d_level["max_lon"]).astype(float).values,
            "max_lat": cast(pd.Series, d_level["max_lat"]).astype(float).values,
        }
    )
    built["source"] = "r1_unfiltered_d_level"
    gdf = gpd.GeoDataFrame(
        built, geometry=cast(Any, d_level.geometry.values), crs="EPSG:4326"
    )
    if cast(pd.Series, gdf["platform"]).isna().any():
        raise ValueError("unmapped S1 platform_number in D-level set")
    return cast(gpd.GeoDataFrame, gdf.drop_duplicates(subset=["scene_id"]))


def _build_l7_extended(r1_dir: Path) -> tuple[gpd.GeoDataFrame, int]:
    """Full R1 native-geometry pull (all 6,156 rows), with W10 count.

    Every pulled scene is preserved in the scene census; the pairwise
    join naturally produces pairs only for the ~1.4k intersecting cells.
    """
    ext = cast(
        gpd.GeoDataFrame,
        gpd.read_parquet(r1_dir / "l7_extended_geometry_v0_1.parquet"),
    )
    intersects = int(
        cast(pd.Series, ext["intersects_w10_cells"]).sum()
    )
    utc = pd.to_datetime(cast(pd.Series, ext["utc"]), utc=True, format="ISO8601")
    ext_gdf = gpd.GeoDataFrame(
        {
            "event_id": [
                event_id("landsat7", str(s))
                for s in cast(pd.Series, ext["scene_id"])
            ],
            "sensor": "landsat7",
            "scene_id": cast(pd.Series, ext["scene_id"]).astype(str).values,
            "utc": pd.Series(utc.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")).values,
            "year": cast(pd.Series, ext["year"]).astype(int).values,
            "doy": cast(pd.Series, ext["doy"]).astype(int).values,
            "season_tag": [season_tag(t.date()) for t in utc],
            "footprint_sha256": cast(pd.Series, ext["footprint_sha256"]).values,
            "intersects_w10_cells": cast(pd.Series, ext["intersects_w10_cells"])
            .astype(bool)
            .values,
            "source": "r1_l7_extended_native_geometry",
        },
        geometry=cast(Any, ext.geometry.values),
        crs="EPSG:4326",
    )
    return cast(gpd.GeoDataFrame, ext_gdf), intersects


def _quantiles(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for sensor, group in frame.groupby("sensor"):
        values = cast(pd.Series, group["n"]).to_numpy(dtype=float)
        out[str(sensor)] = {
            f"p{int(q * 100):02d}": float(np.quantile(values, q))
            for q in (0.05, 0.5, 0.95)
        }
    return out


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v0-dir", type=Path, default=Path("work/national/census"))
    parser.add_argument("--r1-dir", type=Path, default=Path("work/national/census_r1"))
    parser.add_argument(
        "--footprint-dir", type=Path, default=Path("work/national/footprints")
    )
    parser.add_argument(
        "--cells-csv",
        type=Path,
        default=Path("work/national/domain/cells_china_albers_W10000.csv"),
    )
    parser.add_argument("--year-start", type=int, default=1984)
    parser.add_argument("--year-end", type=int, default=2026)
    args = parser.parse_args()

    out_dir = args.r1_dir / "products"
    out_dir.mkdir(parents=True, exist_ok=True)

    cells = load_cells(args.cells_csv)
    frames = cast(
        gpd.GeoDataFrame,
        gpd.read_file(
            args.footprint_dir / "wrs2_china_coast_v0_1.gpkg", engine="pyogrio"
        ),
    )
    tiles = cast(
        gpd.GeoDataFrame,
        gpd.read_file(
            args.footprint_dir / "mgrs_china_coast_v0_1.gpkg", engine="pyogrio"
        ),
    )
    frame_keys = {
        (int(p), int(r))
        for p, r in zip(
            cast(pd.Series, frames["path"]), cast(pd.Series, frames["row"]),
            strict=True,
        )
    }
    tile_keys = set(cast(pd.Series, tiles["mgrs_tile"]).astype(str))

    scene_frames: list[pd.DataFrame] = []
    landsat_frames: list[pd.DataFrame] = []
    deduped: dict[str, int] = {}
    for sensor in LANDSAT_SENSORS:
        scenes, n_dupes = _build_landsat(sensor, args.v0_dir, args.r1_dir, frame_keys)
        deduped[sensor] = n_dupes
        scene_frames.append(scenes)
        landsat_frames.append(scenes.drop(columns=["source"], errors="ignore"))
    s2_scenes, s2_dupes = _build_s2(args.v0_dir, args.r1_dir, tile_keys)
    deduped["sentinel2"] = s2_dupes
    scene_frames.append(s2_scenes)
    s1_scenes = _build_s1(args.r1_dir)
    deduped["sentinel1"] = 0
    scene_frames.append(pd.DataFrame(s1_scenes.drop(columns="geometry")))

    l7_extended, n_l7_ext_intersects = _build_l7_extended(args.r1_dir)
    scene_frames.append(
        pd.DataFrame(
            l7_extended.drop(
                columns=["geometry", "intersects_w10_cells"], errors="ignore"
            )
        )
    )
    l7_legacy = _preserved_l7_legacy_rows(args.v0_dir, args.r1_dir)
    if len(l7_legacy):
        scene_frames.append(l7_legacy)
    landsat_all = pd.concat(landsat_frames, ignore_index=True, sort=False)

    pair_frames = [
        join_landsat_family(landsat_all, frames, cells, extended_scenes=l7_extended)
    ]
    extended_l7_scenes = pair_frames[0][1]
    pair_frames = [pair_frames[0][0]]
    pair_frames.append(
        join_s2_granules(
            s2_scenes.drop(columns=["source"], errors="ignore"), tiles, cells
        )
    )
    pair_frames.append(join_s1_scenes(s1_scenes, cells))
    cell_events = cell_events_union(pair_frames)

    failed_scopes = _failed_scopes(
        [
            args.v0_dir / "resource_ledger_optical_v0.json",
            args.v0_dir / "resource_ledger_s1_v0.json",
            args.r1_dir / "resource_ledger_optical_2026ytd_r1.json",
            args.r1_dir / "resource_ledger_s1_r1_unfiltered.json",
            args.r1_dir / "incremental" / "resource_ledger_incremental_r1.json",
        ]
    )

    availability = build_availability(
        cell_events,
        cast("pd.Series[str]", cells["cell_id"]),
        args.year_start,
        args.year_end,
        failed_scopes,
        partial_years=PARTIAL_YEARS,
        cutoff_utc=CUTOFF_UTC,
    )
    gaps = chronic_gap_flags(availability)

    scene_census = pd.concat(scene_frames, ignore_index=True, sort=True)
    scene_census = _annotate_year_status(scene_census)
    scene_census = _add_phase_columns(
        cast(pd.DataFrame, scene_census.drop(columns=["source"], errors="ignore"))
    )

    scene_path = out_dir / "china_eo_scene_census_v0_1.parquet"
    events_path = out_dir / "china_cell_event_census_v0_1.parquet"
    availability_path = out_dir / "china_eo_availability_v0_1.csv"
    gaps_path = out_dir / "china_eo_data_gap_matrix_v0_1.csv"
    scene_census.to_parquet(scene_path, engine="pyarrow")
    cell_events.to_parquet(events_path, engine="pyarrow")
    availability.to_csv(availability_path, index=False)
    gaps.to_csv(gaps_path, index=False)

    # ---- aggregates (executed, no hand-patching) ------------------------
    scene_counts = {
        str(sensor): int(
            (cast(pd.Series, scene_census["sensor"]) == sensor).sum()
        )
        for sensor in [*LANDSAT_SENSORS, "sentinel2", "sentinel1"]
    }
    scene_counts_2026 = {
        str(sensor): int(
            (
                (cast(pd.Series, scene_census["sensor"]) == sensor)
                & (cast(pd.Series, scene_census["year"]) == 2026)
            ).sum()
        )
        for sensor in [*LANDSAT_SENSORS, "sentinel2", "sentinel1"]
    }
    eligible_counts = {
        str(sensor): int(
            (
                (cast(pd.Series, scene_census["sensor"]) == sensor)
                & (cast(pd.Series, scene_census["default_production_eligible"]))
            ).sum()
        )
        for sensor in scene_counts
    }

    per_cy = (
        cell_events.groupby(["cell_id", "year", "sensor"])["event_id"]
        .nunique()
        .rename("n")
        .reset_index()
    )
    full_quantiles = _quantiles(per_cy[~per_cy["year"].isin(PARTIAL_YEARS)])
    partial_quantiles = _quantiles(per_cy[per_cy["year"].isin(PARTIAL_YEARS)])

    basis_counts = {
        str(k): int(v)
        for k, v in cast(
            pd.Series, cell_events["geometry_basis"].value_counts()
        ).items()
    }
    common_pairs = cast(
        pd.DataFrame, cell_events[cell_events["year"].between(2015, 2025)]
    )
    full_cover_fraction = {
        str(sensor): round(
            float((cast(pd.Series, sub["coverage"]) == FULL_COVER).mean()), 4
        )
        for sensor, sub in common_pairs.groupby("sensor")
    }
    l7_pairs = cast(
        pd.DataFrame, cell_events[cell_events["sensor"] == "landsat7"]
    )
    l7_ext_pairs = l7_pairs[l7_pairs["geometry_basis"] == L7_EXTENDED_BASIS]
    l7_nom_pairs = l7_pairs[l7_pairs["geometry_basis"] != L7_EXTENDED_BASIS]
    l7_scene_table = cast(
        pd.DataFrame, scene_census[scene_census["sensor"] == "landsat7"]
    )
    l7_phase_scene_counts = {
        str(k): int(v)
        for k, v in cast(
            pd.Series, l7_scene_table["mission_phase"].value_counts()
        ).items()
    }

    def _span(frame: pd.DataFrame) -> dict[str, str | None]:
        if not len(frame):
            return {"first_utc": None, "last_utc": None}
        utc = pd.to_datetime(frame["utc"], utc=True, format="ISO8601")
        return {
            "first_utc": utc.min().isoformat(),
            "last_utc": utc.max().isoformat(),
        }

    spans = {
        sensor: _span(
            cast(pd.DataFrame, scene_census[scene_census["sensor"] == sensor])
        )
        for sensor in scene_counts
    }

    s1_table = cast(
        pd.DataFrame, scene_census[scene_census["sensor"] == "sentinel1"]
    )
    s1_pass_full = {
        str(year): {
            "ASC": int(
                (
                    (cast(pd.Series, s1_table["year"]) == year)
                    & (cast(pd.Series, s1_table["pass"]) == "ASC")
                ).sum()
            ),
            "DESC": int(
                (
                    (cast(pd.Series, s1_table["year"]) == year)
                    & (cast(pd.Series, s1_table["pass"]) == "DESC")
                ).sum()
            ),
        }
        for year in sorted(cast(pd.Series, s1_table["year"]).unique())
    }

    chronic_counts = {
        str(sensor): int(
            (cast(pd.Series, sub["gap_class"]) == "CHRONIC_ZERO_COMMON_ERA").sum()
        )
        for sensor, sub in gaps.groupby("sensor")
    }
    gap_class_counts = {
        str(k): int(v)
        for k, v in cast(pd.Series, gaps["gap_class"].value_counts()).items()
    }

    ne_audit = json.loads(
        Path("docs/data/national/NE_CHRONIC_ZERO_AUDIT_v0.json").read_text(
            encoding="utf-8"
        )
    )
    fp_indices = json.loads(
        Path("docs/data/national/FOOTPRINT_INDICES_v0_1.json").read_text(
            encoding="utf-8"
        )
    )
    s1_audit = json.loads(
        Path("docs/data/national/S1_PASS_DISTRIBUTION_AUDIT_v0_1.json").read_text(
            encoding="utf-8"
        )
    )

    products = {
        "china_eo_scene_census_v0_1.parquet": scene_path,
        "china_cell_event_census_v0_1.parquet": events_path,
        "china_eo_availability_v0_1.csv": availability_path,
        "china_eo_data_gap_matrix_v0_1.csv": gaps_path,
    }
    fingerprints = {name: _sha256(path) for name, path in products.items()}
    product_bytes = {name: path.stat().st_size for name, path in products.items()}

    observed_cells = int(cell_events["cell_id"].nunique())
    observed_full_years = set(
        cast(
            pd.Series,
            cell_events[
                cell_events["year"].between(2015, 2025)
            ]["cell_id"],
        ).astype(str)
    )
    island_table: dict[str, dict[str, float]] = {}
    island_csv = args.v0_dir / "island_cell_classification_W10000.csv"
    if island_csv.exists():
        classes = pd.read_csv(island_csv)
        for name, group in classes.groupby("land_class"):
            ids = set(cast(pd.Series, group["cell_id"]).astype(str))
            island_table[str(name)] = {
                "n_cells": float(len(ids)),
                "observed_2015_2025": float(len(ids & observed_full_years)),
                "fraction_observed": round(
                    len(ids & observed_full_years) / len(ids), 4
                ),
            }
    report: dict[str, Any] = {
        "product": "china_eo_census_v0_1",
        "supersedes": "china_eo_census_v0",
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "census_cutoff_utc": CUTOFF_UTC,
        "year_status_policy": {
            "partial_years": sorted(PARTIAL_YEARS),
            "note": (
                "2026 is YTD through the frozen cutoff; PARTIAL_YEAR rows "
                "are excluded from full-year comparisons and chronic flags"
            ),
        },
        "grid": "mainland China coastal domain / W10000 Albers (3319 cells)",
        "footprint_indices_version": "v0_1",
        "footprint_indices_summary": {
            "wrs2_n_frames": fp_indices["wrs2"]["n_frames"],
            "wrs2_paths": fp_indices["wrs2"]["paths"],
            "mgrs_n_tiles": fp_indices["mgrs"]["n_tiles"],
        },
        "scene_counts": scene_counts,
        "scene_counts_2026_ytd": scene_counts_2026,
        "default_production_eligible_counts": eligible_counts,
        "duplicate_scene_ids_dropped": deduped,
        "unique_scenes_total": int(scene_census["event_id"].nunique()),
        "cell_event_pairs": len(cell_events),
        "observed_cells": observed_cells,
        "geometry_basis_pair_counts": basis_counts,
        "full_cover_pair_fraction_2015_2025": full_cover_fraction,
        "l7_extended_mission": {
            "extended_scene_rows_in_census": l7_phase_scene_counts.get(
                "OFF_NOMINAL_EXTENDED_MISSION", 0
            ),
            "standby_gap_scene_rows_no_native_geometry": l7_phase_scene_counts.get(
                "STANDBY_ORBIT_LOWERING", 0
            ),
            "standby_gap_note": (
                "2022-04-06..2022-05-04 orbit-lowering window: rows preserved "
                "in the scene census; no WRS-2 guarantee and no native "
                "geometry, so they produce no cell-event pairs"
            ),
            "extended_scene_rows_pulled_total": int(len(l7_extended)),
            "extended_scene_rows_with_w10_intersection": int(
                n_l7_ext_intersects
            ),
            "nominal_track_non_nominal_rows_removed": int(extended_l7_scenes),
            "legacy_non_nominal_rows_preserved_without_pairs": int(
                len(l7_legacy)
            ),
            "v0_l7_rows_all_preserved": bool(
                set(
                    cast(
                        pd.Series,
                        _read_parquet(
                            args.v0_dir / "scene_census_landsat7_v0.parquet"
                        )["scene_id"],
                    ).astype(str)
                )
                <= set(
                    cast(
                        pd.Series,
                        l7_scene_table["scene_id"],
                    ).astype(str)
                )
            ),
            "nominal_cell_event_pairs": int(len(l7_nom_pairs)),
            "extended_cell_event_pairs": int(len(l7_ext_pairs)),
            "nominal_distinct_events": int(l7_nom_pairs["event_id"].nunique()),
            "extended_distinct_events": int(l7_ext_pairs["event_id"].nunique()),
            "phase_scene_counts": l7_phase_scene_counts,
            "geometry_basis_token": L7_EXTENDED_BASIS,
        },
        "failed_scopes": sorted(failed_scopes),
        "events_per_cell_year_quantiles_full_years": full_quantiles,
        "events_per_cell_year_quantiles_2026_ytd": partial_quantiles,
        "s1_pass_distribution": s1_pass_full,
        "s1_pass_audit_token": s1_audit.get("diagnosis_token"),
        "chronic_zero_cells_common_era": chronic_counts,
        "gap_class_counts": gap_class_counts,
        "availability_rows": len(availability),
        "gap_rows": len(gaps),
        "ne_chronic_zero_audit": {
            "n_cells": int(ne_audit.get("n_cells", 23)),
            "class_counts": ne_audit.get("class_counts"),
        },
        "land_class_observation_2015_2025": island_table,
        "utc_spans": spans,
        "product_bytes": product_bytes,
        "sha256": fingerprints,
    }
    report_path = out_dir / "china_eo_census_report_v0_1.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
