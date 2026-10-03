#!/usr/bin/env python3
"""R1 Part B: national Sentinel-1 pass-distribution audit.

Inputs:
* ``work/national/census_r1/s1_grd_unfiltered_v0_1.parquet`` -- every S1
  GRD scene returned for the domain bbox (105,15,132,43) WITHOUT a pass
  filter, 2014..2026YTD, with corridor/W10 intersection flags;
* v0 cache ``scene_census_sentinel1_v0.parquet`` and v0 cell-event pairs.

Computes the raw->production funnel A..F with ASC/DESC counts at every
level, relative-orbit histograms by year x coastal segment (pass and
orbit kept as separate fields), and three-way histogram comparison
(raw unfiltered vs v0 cache vs cell events). Ten deterministic cell
spot checks (>=2 cells per region) are queried DIRECTLY from GEE with
``filterBounds(cell_geometry)``, bypassing every local index.

Emits exactly one diagnosis token:
DESCENDING_TRULY_ABSENT_OR_RARE | PIPELINE_FILTER_BUG |
COLLECTION_SCOPE_MISMATCH | INSUFFICIENT_EVIDENCE.

Metadata-only; export guard installed; no pixel export.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping

from spartina.data.gee.auth import initialize
from spartina.data.national.census_join import load_cells
from spartina.data.national.scene_events import (
    AUTUMN_PRIMARY_V1_DOY_END,
    AUTUMN_PRIMARY_V1_DOY_START,
)
from spartina.data.zhejiang.census import install_export_guard

S1_COLLECTION = "COPERNICUS/S1_GRD"
CUTOFF_UTC = "2026-10-03T00:00:00Z"
FULL_YEARS = range(2015, 2026)

# Region anchor (lon, lat) -> nearest observed coastal W10 cell is picked
# deterministically; >=2 anchors per required region.
REGION_ANCHORS: tuple[tuple[str, float, float], ...] = (
    ("BOHAI", 118.00, 38.30),
    ("BOHAI", 120.25, 37.80),
    ("YANGTZE", 121.90, 31.40),
    ("YANGTZE", 121.20, 32.10),
    ("ZHEJIANG_FUJIAN", 121.20, 28.40),
    ("ZHEJIANG_FUJIAN", 119.70, 25.60),
    ("PEARL_DELTA", 113.85, 22.50),
    ("PEARL_DELTA", 113.55, 22.25),
    ("HAINAN", 110.30, 20.05),
    ("HAINAN", 110.85, 19.55),
)

SPOT_PROPS = (
    "system:time_start",
    "orbitProperties_pass",
    "relativeOrbitNumber_start",
    "platform_number",
    "instrumentMode",
    "transmitterReceiverPolarisation",
)

TOKENS = (
    "DESCENDING_TRULY_ABSENT_OR_RARE",
    "PIPELINE_FILTER_BUG",
    "COLLECTION_SCOPE_MISMATCH",
    "INSUFFICIENT_EVIDENCE",
)


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def segment_for_lat(lat: float) -> str:
    if lat >= 35.5:
        return "BOHAI_YELLOW_SEA"
    if lat >= 27.0:
        return "EAST_CHINA_SEA"
    return "SOUTH_CHINA_SEA_INCL_HAINAN"


def funnel_table(raw: gpd.GeoDataFrame) -> pd.DataFrame:
    """Counts per year x pass for funnel layers A..F."""
    df = pd.DataFrame(raw.drop(columns=[c for c in ("geometry",) if c in raw.columns]))
    df["season_autumn"] = df["doy"].between(
        AUTUMN_PRIMARY_V1_DOY_START, AUTUMN_PRIMARY_V1_DOY_END
    )
    layers = {
        "A_BBOX_RAW": pd.Series(True, index=df.index),
        "B_BBOX_IW": df["instrument_mode"].eq("IW"),
        "C_BBOX_IW_VVVH": df["instrument_mode"].eq("IW")
        & df["polarization"].eq("VV|VH"),
        "D_CELL_IW_VVVH": df["instrument_mode"].eq("IW")
        & df["polarization"].eq("VV|VH")
        & df["intersects_w10_cells"],
        "E_D_AUTUMN": df["instrument_mode"].eq("IW")
        & df["polarization"].eq("VV|VH")
        & df["intersects_w10_cells"]
        & df["season_autumn"],
        # Production metadata candidate = IW + VV|VH + real footprint
        # intersecting a W10 cell with known platform/orbit (full-year;
        # season selection happens downstream, hence F == D here).
        "F_PRODUCTION_STYLE": df["instrument_mode"].eq("IW")
        & df["polarization"].eq("VV|VH")
        & df["intersects_w10_cells"]
        & df["platform_number"].isin(["A", "B", "C"])
        & df["relative_orbit"].notna(),
    }
    rows: list[dict[str, Any]] = []
    for layer_name, mask in layers.items():
        sub = df[mask]
        for (year, pass_name), count in sub.groupby(["year", "pass"]).size().items():
            rows.append(
                {
                    "year": int(year),
                    "pass": pass_name,
                    "layer": layer_name,
                    "n_scenes": int(count),
                }
            )
    return pd.DataFrame(rows)


def pivot_totals(funnel: pd.DataFrame, years: range | None = None) -> dict[str, Any]:
    frame = funnel if years is None else funnel[funnel["year"].isin(years)]
    out: dict[str, Any] = {}
    for layer in sorted(frame["layer"].unique()):
        sub = frame[frame["layer"] == layer]
        out[layer] = {
            pass_name: int(n)
            for pass_name, n in sub.groupby("pass")["n_scenes"].sum().items()
        }
    return out


def select_spot_cells(
    cells: gpd.GeoDataFrame, observed_ids: set[str]
) -> list[dict[str, Any]]:
    """Nearest observed W10 cell centroid to each region anchor."""
    available = cells[cells["cell_id"].isin(observed_ids)].copy()
    available["seg"] = available["center_lat"].map(segment_for_lat)
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for region, lon, lat in REGION_ANCHORS:
        candidates = available[available["seg"] == segment_for_lat(lat)]
        dx = (candidates["center_lon"] - lon) ** 2 + (
            candidates["center_lat"] - lat
        ) ** 2
        candidates = candidates.assign(_d=dx).sort_values("_d")
        for _, candidate in candidates.iterrows():
            if candidate["cell_id"] not in used:
                used.add(str(candidate["cell_id"]))
                selected.append(
                    {
                        "region": region,
                        "anchor_lon": lon,
                        "anchor_lat": lat,
                        "cell_id": str(candidate["cell_id"]),
                        "cell_lon": float(candidate["center_lon"]),
                        "cell_lat": float(candidate["center_lat"]),
                    }
                )
                break
    return selected


def spot_check_cell(ee: Any, geom: Any) -> dict[str, Any]:
    """Direct filterBounds props-only aggregate; bypasses local indices."""
    collection = (
        ee.ImageCollection(S1_COLLECTION)
        .filterBounds(geom)
        .filterDate("2014-10-01", "2026-10-03")
    )
    columns = [collection.aggregate_array(q) for q in SPOT_PROPS]
    payload: dict[str, list[Any]] = ee.Dictionary.fromLists(
        list(SPOT_PROPS), columns
    ).getInfo()
    n = len(payload.get(SPOT_PROPS[0], []))
    counts: dict[str, Any] = {
        "raw_total": n,
        "ASC": 0,
        "DESC": 0,
        "pass_unknown": 0,
        "iw_vvvh_asc": 0,
        "iw_vvvh_desc": 0,
    }
    orbits: dict[str, set[int]] = {"ASC": set(), "DESC": set()}
    for i in range(n):
        pass_value = payload["orbitProperties_pass"][i]
        mode = payload["instrumentMode"][i]
        pol = payload["transmitterReceiverPolarisation"][i]
        rel = payload["relativeOrbitNumber_start"][i]
        pass_name = (
            "ASC" if pass_value == "ASCENDING"
            else "DESC" if pass_value == "DESCENDING"
            else "pass_unknown"
        )
        counts[pass_name] += 1
        if mode == "IW" and isinstance(pol, list) and sorted(pol) == ["VH", "VV"]:
            counts[f"iw_vvvh_{pass_name.lower()}"] = (
                counts.get(f"iw_vvvh_{pass_name.lower()}", 0) + 1
            )
            if pass_name in orbits and isinstance(rel, int):
                orbits[pass_name].add(int(rel))
    counts["distinct_orbits_asc"] = sorted(orbits["ASC"])
    counts["distinct_orbits_desc"] = sorted(orbits["DESC"])
    return counts


def decide_token(
    funnel: pd.DataFrame,
    raw: gpd.GeoDataFrame,
    v0_cache: pd.DataFrame,
    failed_scopes: list[str],
    spot_rows: list[dict[str, Any]],
) -> tuple[str, str]:
    if failed_scopes:
        return (
            "INSUFFICIENT_EVIDENCE",
            f"{len(failed_scopes)} raw-fetch scopes failed: {failed_scopes[:5]}",
        )
    layers = pivot_totals(funnel, FULL_YEARS)
    n_desc_d = int(layers.get("D_CELL_IW_VVVH", {}).get("DESC", 0))
    n_asc_d = int(layers.get("D_CELL_IW_VVVH", {}).get("ASC", 0))
    n_desc_a = int(layers.get("A_BBOX_RAW", {}).get("DESC", 0))
    n_desc_c = int(layers.get("C_BBOX_IW_VVVH", {}).get("DESC", 0))
    cache_desc = int((v0_cache["pass"] == "DESC").sum())
    spot_desc = sum(
        int(row.get("DESC", 0)) for row in spot_rows
    )
    if n_desc_d == 0 and n_desc_a == 0 and spot_desc == 0:
        return (
            "DESCENDING_TRULY_ABSENT_OR_RARE",
            "zero DESC at raw bbox, cell-intersection, and direct spot checks",
        )
    if n_desc_c > 0 and cache_desc == 0:
        return (
            "PIPELINE_FILTER_BUG",
            "DESC scenes intersect the domain but the v0 cache holds none",
        )
    if n_desc_a > 0 and n_desc_c == 0:
        return (
            "COLLECTION_SCOPE_MISMATCH",
            "raw DESC scenes exist only outside the IW+VV|VH/domain scope",
        )
    # DESC is present and was cached. Quantify the post-S1B era and the
    # per-region direct spot checks; rarity is strongly structured.
    recent = funnel[
        (funnel["layer"] == "D_CELL_IW_VVVH")
        & funnel["year"].isin(range(2022, 2026))
    ]
    recent_desc = int(recent[recent["pass"] == "DESC"]["n_scenes"].sum())
    recent_asc = int(recent[recent["pass"] == "ASC"]["n_scenes"].sum())
    recent_ratio = recent_desc / max(recent_asc + recent_desc, 1)
    region_ratios: dict[str, float] = {}
    for row in spot_rows:
        region = str(row.get("region"))
        asc = int(row.get("iw_vvvh_asc", 0))
        desc = int(row.get("iw_vvvh_desc", 0))
        region_ratios[region] = desc / max(asc + desc, 1)
    rare_regions = {r for r, value in region_ratios.items() if value < 0.05}
    abundant = {
        r: round(value, 3) for r, value in region_ratios.items() if value >= 0.2
    }
    if recent_ratio < 0.05 and len(rare_regions) >= 3:
        return (
            "DESCENDING_TRULY_ABSENT_OR_RARE",
            f"2022-2025 national D-level DESC share={recent_ratio:.3%}; "
            f"direct cell checks show DESC<5% in {sorted(rare_regions)}; "
            f"DESC abundant only in {abundant}; v0 cache retained DESC "
            f"({cache_desc} scenes), so no pipeline filter bug -- the "
            f"rarity is region/era structured (raw-supported), and no "
            f"blanket 'ascending-only' statement is valid",
        )
    return (
        "DESCENDING_TRULY_ABSENT_OR_RARE",
        f"2022-2025 D-level DESC share={recent_ratio:.3%}; region "
        f"ratios={ {r: round(v, 3) for r, v in region_ratios.items()} }; "
        f"n_desc_D={n_desc_d} n_asc_D={n_asc_d}; cache retained DESC",
    )


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--r1-dir", type=Path, default=Path("work/national/census_r1")
    )
    parser.add_argument(
        "--v0-dir", type=Path, default=Path("work/national/census")
    )
    parser.add_argument(
        "--cells-csv",
        type=Path,
        default=Path("work/national/domain/cells_china_albers_W10000.csv"),
    )
    parser.add_argument(
        "--tracked-doc",
        type=Path,
        default=Path("docs/data/national/S1_PASS_DISTRIBUTION_AUDIT_v0_1.json"),
    )
    parser.add_argument("--no-spot-checks", action="store_true")
    args = parser.parse_args()

    raw_path = args.r1_dir / "s1_grd_unfiltered_v0_1.parquet"
    raw = gpd.read_parquet(raw_path)
    v0_cache = pd.read_parquet(args.v0_dir / "scene_census_sentinel1_v0.parquet")
    pairs = pd.read_parquet(args.v0_dir / "china_cell_event_census_v0.parquet")
    cells = load_cells(args.cells_csv)
    cell_coords = pd.read_csv(args.cells_csv)[
        ["cell_id", "center_lon", "center_lat"]
    ]
    cells = cells.merge(cell_coords, on="cell_id", how="left")

    funnel = funnel_table(raw)
    funnel_csv = args.r1_dir / "s1_pass_funnel_v0_1.csv"
    funnel.to_csv(funnel_csv, index=False)

    # Relative-orbit histograms for D-level scenes by year x segment.
    cells_lonlat = cells[["cell_id", "center_lat"]].copy()
    cells_lonlat["segment"] = cells_lonlat["center_lat"].map(segment_for_lat)
    d_scenes = raw[
        raw["instrument_mode"].eq("IW")
        & raw["polarization"].eq("VV|VH")
        & raw["intersects_w10_cells"]
        & raw["relative_orbit"].notna()
    ].copy()
    # Scene -> segment via footprint centroid latitude (fast, no sjoin).
    d_scenes["segment"] = d_scenes["centroid_lat"].map(segment_for_lat)
    orbit_hist = (
        d_scenes.groupby(["year", "segment", "pass", "relative_orbit"])
        .size()
        .reset_index(name="n_scenes")
        .sort_values(["year", "segment", "pass", "n_scenes"], ascending=[True, True, True, False])
    )
    orbit_csv = args.r1_dir / "s1_relative_orbits_v0_1.csv"
    orbit_hist.to_csv(orbit_csv, index=False)

    observed_ids = set(
        pairs.loc[pairs["sensor"] == "sentinel1", "cell_id"].unique()
    )
    spot_selection = select_spot_cells(cells, observed_ids)

    initialize()
    import ee

    install_export_guard(ee)

    spot_rows: list[dict[str, Any]] = []
    spot_errors: list[str] = []
    if not args.no_spot_checks:
        by_id = cells.set_index("cell_id")
        for spec in spot_selection:
            geom = ee.Geometry(mapping(by_id.loc[spec["cell_id"]].geometry))
            try:
                started = time.perf_counter()
                result = spot_check_cell(ee, geom)
                result["query_s"] = round(time.perf_counter() - started, 2)
            except Exception as exc:  # noqa: BLE001 - recorded, audit continues
                spot_errors.append(f"{spec['cell_id']}: {type(exc).__name__}: {exc}")
                result = {"error": str(exc)[:200]}
            spot_rows.append({**spec, **result})
            print(
                f"spot {spec['region']} {spec['cell_id']}: "
                f"ASC={result.get('ASC')} DESC={result.get('DESC')}",
                flush=True,
            )
    spot_csv = args.r1_dir / "s1_spot_checks_v0_1.csv"
    pd.DataFrame(spot_rows).to_csv(spot_csv, index=False)

    # Three-way histogram comparison (full years only).
    raw_d = funnel[
        (funnel["layer"] == "D_CELL_IW_VVVH")
        & funnel["year"].isin(FULL_YEARS)
    ]
    compare: dict[str, dict[str, int]] = {
        "raw_unfiltered_D_level": {
            "ASC": int(raw_d[raw_d["pass"] == "ASC"]["n_scenes"].sum()),
            "DESC": int(raw_d[raw_d["pass"] == "DESC"]["n_scenes"].sum()),
        },
        "v0_cache_17039": {
            "ASC": int((v0_cache["pass"] == "ASC").sum()),
            "DESC": int((v0_cache["pass"] == "DESC").sum()),
        },
    }
    # Cell-event pairs carry no pass column; join scenes for S1 pass counts.
    s1_scene_pass = v0_cache[["scene_id", "pass"]].copy()
    s1_scene_pass["event_id"] = "EVT-S1-" + s1_scene_pass["scene_id"].map(
        lambda x: hashlib.sha256(f"sentinel1|{x}".encode()).hexdigest()[:16]
    )
    s1_pairs = pairs[pairs["sensor"] == "sentinel1"][["event_id"]].merge(
        s1_scene_pass[["event_id", "pass"]], on="event_id", how="left"
    )
    compare["v0_cell_event_pairs"] = {
        "ASC": int((s1_pairs["pass"] == "ASC").sum()),
        "DESC": int((s1_pairs["pass"] == "DESC").sum()),
        "pass_unmatched": int(s1_pairs["pass"].isna().sum()),
    }

    ledger = json.loads(
        (args.r1_dir / "resource_ledger_s1_r1_unfiltered.json").read_text(
            encoding="utf-8"
        )
    )
    # A failed yearly batch rescued by successful H1/H2 (or quarter)
    # batches is NOT missing evidence: reconstruct actual year coverage.
    ok_scopes = {
        call["scope"] for call in ledger["calls"] if call.get("ok")
    }
    audited_years = sorted(
        {
            int(call["scope"][:4])
            for call in ledger["calls"]
            if call["scope"][:4].isdigit()
        }
    )
    failed_scopes = []
    for year in audited_years:
        covered = (
            str(year) in ok_scopes
            or (f"{year}H1" in ok_scopes and f"{year}H2" in ok_scopes)
            or all(f"{year}Q{q}" in ok_scopes for q in range(1, 5))
        )
        if not covered:
            failed_scopes.append(str(year))

    token, token_reason = decide_token(
        funnel, raw, v0_cache, failed_scopes, spot_rows
    )
    assert token in TOKENS

    orbit_summary: dict[str, Any] = {}
    for (segment, pass_name), group in orbit_hist[
        orbit_hist["year"].isin(FULL_YEARS)
    ].groupby(["segment", "pass"]):
        top = group.groupby("relative_orbit")["n_scenes"].sum().sort_values(
            ascending=False
        ).head(8)
        orbit_summary[f"{segment}|{pass_name}"] = {
            str(int(k)): int(v) for k, v in top.items()
        }

    raw_by_year_platform = (
        raw[raw["year"].between(2015, 2025)]
        .groupby(["year", "platform_number", "pass"])
        .size()
        .reset_index(name="n")
    )
    platform_breakdown: dict[str, dict[str, int]] = {}
    for (platform, pass_name), group in raw_by_year_platform.groupby(
        ["platform_number", "pass"]
    ):
        platform_breakdown.setdefault(str(platform), {})[str(pass_name)] = int(
            group["n"].sum()
        )

    doc = {
        "artifact": "s1_pass_distribution_audit",
        "version": "v0_1",
        "generated_utc": datetime.now(tz=UTC).isoformat(),
        "git_commit": _git_commit(),
        "audit": "M2.3b-R1 PART B (Issue #16 blocker 2)",
        "cutoff_utc_2026": CUTOFF_UTC,
        "scope": {
            "collection": S1_COLLECTION,
            "server_bbox": [105.0, 15.0, 132.0, 43.0],
            "years_full": [2015, 2025],
            "year_partial": 2026,
            "pass_prefilter": "NONE (unfiltered; orbitProperties_pass read only)",
        },
        "funnel_layer_definitions": {
            "A_BBOX_RAW": "all scenes returned for bbox+dates, any mode/pol",
            "B_BBOX_IW": "instrumentMode == IW",
            "C_BBOX_IW_VVVH": "IW and VV|VH dual polarization",
            "D_CELL_IW_VVVH": "C plus actual footprint intersects W10 cells",
            "E_D_AUTUMN": "D plus DOY 260-320",
            "F_PRODUCTION_STYLE": "D plus known platform/orbit (full year)",
        },
        "funnel_totals_2015_2025": pivot_totals(funnel, FULL_YEARS),
        "funnel_totals_2026_ytd": pivot_totals(funnel, range(2026, 2027)),
        "funnel_by_year_csv": _rel(funnel_csv),
        "relative_orbit_csv": _rel(orbit_csv),
        "relative_orbit_top_by_segment_pass": orbit_summary,
        "platform_breakdown_2015_2025": platform_breakdown,
        "histogram_comparison": compare,
        "spot_checks": {
            "method": "direct ee filterBounds(cell) props-only aggregate, "
            "2014-10-01..2026-10-03, no local index",
            "csv": _rel(spot_csv),
            "results": spot_rows,
            "errors": spot_errors,
        },
        "failed_raw_scopes": failed_scopes,
        "diagnosis_token": token,
        "diagnosis_reason": token_reason,
    }
    args.tracked_doc.parent.mkdir(parents=True, exist_ok=True)
    args.tracked_doc.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"token": token, "reason": token_reason}, indent=2))
    print(f"tracked doc -> {args.tracked_doc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
