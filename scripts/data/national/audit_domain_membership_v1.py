#!/usr/bin/env python3
"""Audit mainland coastal-domain membership v1 (Issue #17).

Separates immutable W5/W10/W20 grid-cell geometry from versioned domain
membership.  Membership evidence is strictly target-independent GIS:

* Natural Earth admin-0 ownership (China vs foreign vs unadministered);
* GSHHS high-resolution land / coastline;
* the fixed a-priori nearshore-island rule (area <= 100 km^2,
  representative point within 25 km of the China mainland, no foreign
  admin polygon);
* nearest-landfall distance for open-water cells.

Murray/JRC context CSVs (produced by fetch_domain_context_gee.py) are
joined for reporting only; they are not inputs to the decision and can
never set a target label.

Outputs (W10 membership; W5/W20 sensitivity only):

* work/national/domain_v1/gis_evidence_W{5000,10000,20000}.csv (cache)
* datasets/manifests/china_coastal_cells_v1_candidate.csv|.parquet
* datasets/manifests/china_domain_artifact_audit_v0.csv
* datasets/manifests/china_intertidal_context_v0.csv|.parquet
* docs/data/national/CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json
* docs/data/national/DOMAIN_V1_SENSITIVITY.json

Usage::

    PYTHONPATH=src python3 scripts/data/national/audit_domain_membership_v1.py \
        --gshhs-shp work/external/gshhg_2_3_7/extracted/GSHHS_shp/h/GSHHS_h_L1.shp \
        --admin0-shp work/external/naturalearth_10m_admin0/extracted/ne_10m_admin_0_countries.shp
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spartina.data.national import geometry as nat_geom
from spartina.data.national.coastal_domain import (
    DEFAULT_BBOX_WGS84,
    ISLAND_MAX_AREA_M2,
    ISLAND_NEAR_M,
    build_china_land,
)
from spartina.data.national.domain_membership import (
    CHINA_ADMIN_UNITS,
    CONTESTED_ADMIN_UNITS,
    KEEP_ISLAND_COASTAL,
    KEEP_MAINLAND_COASTAL,
    V0_MEMBERSHIP,
    CellMembershipEvidence,
    decide_membership,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DOMAIN_DIR = REPO_ROOT / "work/national/domain"
WORK_DIR = REPO_ROOT / "work/national/domain_v1"
MANIFEST_DIR = REPO_ROOT / "datasets/manifests"
DOCS_NATIONAL = REPO_ROOT / "docs/data/national"
WIDTHS: tuple[int, ...] = (5_000, 10_000, 20_000)
MEMBERSHIP_WIDTH = 10_000

# Context layers may inform coastal-relevance reporting, never decisions.
CONTEXT_NOTE = "MURRAY_JRC_CONTEXT_ONLY_NEVER_A_SPARTINA_LABEL"


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cells(width: int) -> gpd.GeoDataFrame:
    """Load an immutable grid registry and rebuild Albers cell polygons."""
    frame = pd.read_csv(DOMAIN_DIR / f"cells_china_albers_W{width}.csv")
    aea = nat_geom.CHINA_ALBERS_CRS
    geometries = [
        box(int(row.col) * width, int(row.row) * width,
            (int(row.col) + 1) * width, (int(row.row) + 1) * width)
        for row in frame.itertuples(index=False)
    ]
    return gpd.GeoDataFrame(frame, geometry=geometries, crs=aea)


def _intersection_areas(
    cells: gpd.GeoDataFrame,
    pieces: gpd.GeoDataFrame,
    extra_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Vectorised per-cell intersection areas against attributed pieces."""
    cells = cells.reset_index(drop=True)
    pieces = pieces[["geometry"] + (extra_cols or [])].reset_index(drop=True)
    joined = gpd.sjoin(
        cells[["cell_id", "geometry"]],
        pieces,
        how="inner",
        predicate="intersects",
    )
    if joined.empty:
        return pd.DataFrame(columns=["cell_id", "area_m2"] + (extra_cols or []))
    left_geom = cells.geometry.iloc[joined.index.to_numpy()].to_numpy()
    right_geom = pieces.geometry.iloc[joined["index_right"].to_numpy()].to_numpy()
    # NOTE: assign as a numpy array -- DataFrame.assign would align a
    # Series by index and silently misattribute areas when sjoin returns
    # non-RangeIndex labels (one cell matching many pieces).
    areas = (
        gpd.GeoSeries(left_geom, crs=cells.crs)
        .intersection(gpd.GeoSeries(right_geom, crs=pieces.crs), align=False)
        .area.to_numpy()
    )
    joined = joined.assign(area_m2=areas)
    return joined[["cell_id", "area_m2"] + (extra_cols or [])]


def compute_gis_evidence(
    gshhs_shp: Path, admin0_shp: Path, widths: tuple[int, ...] = WIDTHS
) -> dict[int, pd.DataFrame]:
    """Compute target-independent ownership/coast evidence for each width."""
    aea = nat_geom.CHINA_ALBERS_CRS
    west, south, east, north = DEFAULT_BBOX_WGS84
    bbox_margin = (west - 1.0, south - 1.0, east + 1.0, north + 1.0)

    gshhs_raw = gpd.read_file(gshhs_shp, bbox=bbox_margin, engine="pyogrio")
    admin0 = gpd.read_file(admin0_shp, bbox=bbox_margin, engine="pyogrio")
    # Clip in geographic space BEFORE projecting: transforming the whole
    # Africa-Eurasia polygon into the regional China-Albers CRS produces
    # wrap-around geometry that corrupts regional spatial predicates.
    region_wgs = gpd.GeoSeries([box(*bbox_margin)], crs=4326)
    gshhs = gpd.clip(gshhs_raw, region_wgs)
    land = gpd.GeoDataFrame(geometry=list(gshhs.to_crs(aea).geometry), crs=aea)

    # Ownership normalisation on Natural Earth admin-0 map units:
    #   * China + Hong Kong SAR + Macao SAR -> PRC-administered China
    #     (the SARs are Chinese territory, never "foreign");
    #   * Taiwan / Scarborough Reef -> contested, handled separately;
    #   * every other map unit -> foreign state.
    china_admin_wgs = unary_union(
        admin0.loc[admin0["ADMIN"].isin(CHINA_ADMIN_UNITS), "geometry"].tolist()
    )
    china_series = gpd.GeoSeries([china_admin_wgs], crs=4326).to_crs(aea)
    foreign_admin = (
        admin0[
            ~admin0["ADMIN"].isin(CHINA_ADMIN_UNITS | CONTESTED_ADMIN_UNITS)
        ][["ADMIN", "geometry"]]
        .to_crs(aea)
        .dissolve(by="ADMIN", as_index=False)
    )
    contested_admin = (
        admin0[admin0["ADMIN"].isin(CONTESTED_ADMIN_UNITS)][["ADMIN", "geometry"]]
        .to_crs(aea)
        .dissolve(by="ADMIN", as_index=False)
    )
    china_land = build_china_land(gshhs, admin0, aea.to_proj4())
    v0_island_count = china_land.added_island_count

    # Mainland = GSHHS land clipped to the PRC-administered polygon.
    mainland = gpd.clip(land, china_series)
    mainland_union = mainland.union_all()

    # Foreign-state land and contested-admin land, split at admin units.
    foreign_pieces = gpd.overlay(
        land, foreign_admin[["ADMIN", "geometry"]], how="intersection", keep_geom_type=True
    )
    contested_pieces = gpd.overlay(
        land, contested_admin[["ADMIN", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    foreign_union = foreign_pieces.union_all()
    nonchina_union = unary_union(
        list(foreign_admin.geometry) + list(contested_admin.geometry)
    )

    # Attribute every GSHHS polygon that falls inside no admin-0 polygon
    # (coast-generalization gaps, small islands) by nearest administered
    # landfall.  This generalises the v0 island rule:
    #   * <=100 km^2, rep point <=25 km from China, Chinese landfall
    #     nearest -> Chinese nearshore island (v1 island set, a strict
    #     subset of the v0 recovered islands);
    #   * foreign-state landfall nearest -> foreign evidence (the v0 rule
    #     admitted some of these near the Tumen triple-border);
    #   * neither -> genuinely unattributed land, stays unresolved
    #     (contested-admin landfall is never auto-claimed).
    rep_all = gpd.GeoSeries(
        land.geometry.map(lambda geom: geom.representative_point()), crs=aea
    )
    rep_in_china = rep_all.map(lambda point: point.within(china_series.iloc[0]))
    rep_in_other = rep_all.map(lambda point: point.within(nonchina_union))
    unowned = land[~(rep_in_china | rep_in_other)]
    d_china = rep_all.loc[unowned.index].distance(mainland_union)
    d_foreign = rep_all.loc[unowned.index].distance(foreign_union)
    near_china = (d_china <= ISLAND_NEAR_M) & (
        unowned.area <= ISLAND_MAX_AREA_M2
    ).to_numpy()
    chinese_landfall = d_china < d_foreign
    islands = unowned[near_china.to_numpy() & chinese_landfall.to_numpy()]
    foreign_landfall = unowned[
        (~chinese_landfall).to_numpy() & (d_foreign < d_china).to_numpy()
    ]
    unresolved_land = unowned[
        ~unowned.index.isin(islands.index)
        & ~unowned.index.isin(foreign_landfall.index)
    ]

    print(
        f"attributed layers: mainland_pieces={len(mainland)} "
        f"v0_islands={v0_island_count} china_islands_v1={len(islands)} "
        f"foreign_landfall_pieces={len(foreign_landfall)} "
        f"unresolved_pieces={len(unresolved_land)} "
        f"foreign_admin_pieces={len(foreign_pieces)} "
        f"contested_admin_pieces={len(contested_pieces)}"
    )

    results: dict[int, pd.DataFrame] = {}
    for width in widths:
        cells = load_cells(width)
        total = _intersection_areas(cells, land).groupby("cell_id")["area_m2"].sum()
        mainland_area = (
            _intersection_areas(cells, gpd.GeoDataFrame(geometry=mainland.geometry, crs=aea))
            .groupby("cell_id")["area_m2"].sum()
        )
        island_area = (
            _intersection_areas(cells, gpd.GeoDataFrame(geometry=islands.geometry, crs=aea))
            .groupby("cell_id")["area_m2"].sum()
        )
        foreign_landfall_area = (
            _intersection_areas(
                cells, gpd.GeoDataFrame(geometry=foreign_landfall.geometry, crs=aea)
            )
            .groupby("cell_id")["area_m2"].sum()
        )
        unresolved_area = (
            _intersection_areas(
                cells, gpd.GeoDataFrame(geometry=unresolved_land.geometry, crs=aea)
            )
            .groupby("cell_id")["area_m2"].sum()
        )
        foreign_pair = _intersection_areas(cells, foreign_pieces, extra_cols=["ADMIN"])
        foreign_area = foreign_pair.groupby("cell_id")["area_m2"].sum()
        foreign_names = (
            foreign_pair.groupby("cell_id")["ADMIN"]
            .apply(lambda values: "|".join(sorted(set(values))))
        )
        contested_pair = _intersection_areas(
            cells, contested_pieces, extra_cols=["ADMIN"]
        )
        contested_area = contested_pair.groupby("cell_id")["area_m2"].sum()
        contested_names = (
            contested_pair.groupby("cell_id")["ADMIN"]
            .apply(lambda values: "|".join(sorted(set(values))))
        )

        frame = cells.drop(columns=["geometry"]).copy()
        frame["width_m"] = width
        frame["cell_area_m2"] = float(width * width)
        frame["china_mainland_area_m2"] = (
            frame["cell_id"].map(mainland_area).fillna(0.0)
        )
        frame["china_island_area_m2"] = frame["cell_id"].map(island_area).fillna(0.0)
        frame["foreign_landfall_area_m2"] = (
            frame["cell_id"].map(foreign_landfall_area).fillna(0.0)
        )
        frame["foreign_land_area_m2"] = frame["cell_id"].map(foreign_area).fillna(0.0)
        frame["contested_admin_area_m2"] = (
            frame["cell_id"].map(contested_area).fillna(0.0)
        )
        frame["contested_admin_names"] = (
            frame["cell_id"].map(contested_names).fillna("")
        )
        frame["total_land_area_m2"] = frame["cell_id"].map(total).fillna(0.0)
        # Unattributed area is measured directly (not as a subtraction
        # residual) so tiny overlay rounding differences cannot create
        # spurious provisional cells.
        frame["unadministered_land_area_m2"] = (
            frame["cell_id"].map(unresolved_area).fillna(0.0)
        )
        frame["dist_to_china_mainland_m"] = cells.geometry.distance(mainland_union)
        frame["dist_to_foreign_land_m"] = cells.geometry.distance(foreign_union)
        frame["foreign_admin_names"] = (
            frame["cell_id"].map(foreign_names).fillna("")
        )
        results[width] = frame
        print(f"W{width}: evidence for {len(frame)} cells")

    return results


def write_gis_cache(frames: dict[int, pd.DataFrame]) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    for width, frame in frames.items():
        path = WORK_DIR / f"gis_evidence_W{width}.csv"
        frame.to_csv(path, index=False)
        print(f"wrote {path}")


def load_gis_cache() -> dict[int, pd.DataFrame]:
    return {
        width: pd.read_csv(WORK_DIR / f"gis_evidence_W{width}.csv") for width in WIDTHS
    }


def evidence_for_row(row: pd.Series) -> CellMembershipEvidence:
    width = int(row.width_m)
    return CellMembershipEvidence(
        cell_id=str(row.cell_id),
        cell_area_m2=float(row.cell_area_m2),
        corridor_half_width_m=float(width),
        china_mainland_area_m2=float(row.china_mainland_area_m2),
        china_island_area_m2=float(row.china_island_area_m2),
        foreign_land_area_m2=float(row.foreign_land_area_m2),
        unadministered_land_area_m2=float(row.unadministered_land_area_m2),
        contested_admin_area_m2=float(row.contested_admin_area_m2),
        foreign_landfall_area_m2=float(
            row.foreign_landfall_area_m2
        ),
        dist_to_china_mainland_m=(
            None
            if pd.isna(row.dist_to_china_mainland_m)
            else float(row.dist_to_china_mainland_m)
        ),
        dist_to_foreign_land_m=(
            None
            if pd.isna(row.dist_to_foreign_land_m)
            else float(row.dist_to_foreign_land_m)
        ),
    )


def apply_rule(frame: pd.DataFrame) -> pd.DataFrame:
    decisions = [decide_membership(evidence_for_row(row)) for row in frame.itertuples()]
    out = frame.copy()
    out["membership_v1_candidate"] = [d.decision for d in decisions]
    out["membership_reason"] = [d.reason for d in decisions]
    out["admin_class"] = [d.admin_class for d in decisions]
    out["island_class_rule"] = [d.island_class for d in decisions]
    out["membership_v0"] = V0_MEMBERSHIP
    return out


def load_context() -> pd.DataFrame:
    murray = pd.read_csv(WORK_DIR / "context_murray_v0.csv")
    jrc = pd.read_csv(WORK_DIR / "context_jrc_v0.csv")
    return murray.merge(jrc, on="cell_id", how="outer", validate="one_to_one")


def _evidence_json(row: pd.Series) -> str:
    area = float(row.cell_area_m2)
    payload = {
        "china_mainland_area_frac": round(float(row.china_mainland_area_m2) / area, 6),
        "china_island_area_frac": round(float(row.china_island_area_m2) / area, 6),
        "foreign_land_area_frac": round(float(row.foreign_land_area_m2) / area, 6),
        "foreign_landfall_area_frac": round(
            float(row.foreign_landfall_area_m2) / area, 6
        ),
        "unadministered_land_area_frac": round(
            float(row.unadministered_land_area_m2) / area, 6
        ),
        "contested_admin_area_frac": round(
            float(row.contested_admin_area_m2) / area, 6
        ),
        "foreign_admin_names": str(row.foreign_admin_names),
        "contested_admin_names": str(row.contested_admin_names),
        "dist_to_china_mainland_m": round(float(row.dist_to_china_mainland_m), 1),
        "dist_to_foreign_land_m": round(float(row.dist_to_foreign_land_m), 1),
        "gshhs_land_area_frac": round(float(row.total_land_area_m2) / area, 6),
    }
    return json.dumps(payload, sort_keys=True)


def write_candidate_manifest(frame: pd.DataFrame, context: pd.DataFrame | None) -> Path:
    out = frame.copy()
    out["murray_intertidal_coarse_fraction_30km"] = -1.0
    out["murray_intertidal_present_30km"] = 0
    if context is not None:
        ctx = context.set_index("cell_id")
        out["murray_intertidal_coarse_fraction_30km"] = (
            out["cell_id"]
            .map(ctx.get("murray_intertidal_coarse_fraction"))
            .fillna(-1.0)
        )
        out["murray_intertidal_present_30km"] = (
            out["cell_id"]
            .map(ctx.get("murray_intertidal_present_30km"))
            .fillna(0)
            .astype(int)
        )
        water_context: list[str] = []
        for cell_id in out["cell_id"]:
            if cell_id not in ctx.index:
                water_context.append("")
                continue
            r = ctx.loc[cell_id]
            payload = {
                "jrc_occurrence_mean_pct": _safe_round(r.get("jrc_occurrence_mean_pct")),
                "jrc_water_ever_fraction": _safe_round(r.get("jrc_water_ever_fraction")),
                "jrc_seasonality_mean_months": _safe_round(
                    r.get("jrc_seasonality_mean_months")
                ),
                "murray_intertidal_present_30km": _safe_round(
                    r.get("murray_intertidal_present_30km")
                ),
                "murray_intertidal_coarse_fraction_30km": _safe_round(
                    r.get("murray_intertidal_coarse_fraction")
                ),
                "murray_scale_note": (
                    "30 km coarse support indicator, not an area measurement"
                ),
                "context_use": CONTEXT_NOTE,
            }
            water_context.append(json.dumps(payload, sort_keys=True))
        out["water_context"] = water_context
    else:
        out["water_context"] = ""
    out["membership_evidence"] = [_evidence_json(row) for row in out.itertuples()]
    columns = [
        "cell_id", "grid_kind", "utm_zone", "row", "col",
        "intersection_area_m2", "center_lon", "center_lat",
        "membership_v0", "membership_v1_candidate", "membership_reason",
        "membership_evidence",
        "murray_intertidal_coarse_fraction_30km",
        "murray_intertidal_present_30km",
        "water_context",
        "admin_class", "island_class_rule",
    ]
    out = out[columns].rename(columns={"island_class_rule": "island_class"})
    csv_path = MANIFEST_DIR / "china_coastal_cells_v1_candidate.csv"
    parquet_path = MANIFEST_DIR / "china_coastal_cells_v1_candidate.parquet"
    out.to_csv(csv_path, index=False)
    out.to_parquet(parquet_path, index=False)
    print(f"wrote {csv_path} and {parquet_path}")
    return csv_path


def _safe_round(value: Any, digits: int = 6) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def write_intertidal_context(context: pd.DataFrame) -> Path:
    out = context.copy()
    out["context_use"] = CONTEXT_NOTE
    csv_path = MANIFEST_DIR / "china_intertidal_context_v0.csv"
    parquet_path = MANIFEST_DIR / "china_intertidal_context_v0.parquet"
    out.to_csv(csv_path, index=False)
    out.to_parquet(parquet_path, index=False)
    print(f"wrote {csv_path} and {parquet_path}")
    return csv_path


def write_artifact_audit(
    frame: pd.DataFrame, context: pd.DataFrame | None
) -> Path:
    """Detailed per-cell records for the 20 v0-flagged artifact cells."""
    ne_path = MANIFEST_DIR / "china_ne_chronic_zero_audit_v0.csv"
    flagged = pd.read_csv(ne_path)
    flagged = flagged[flagged["classification"] != "INDEX_MISS"].copy()
    assert len(flagged) == 20, f"expected 20 flagged cells, got {len(flagged)}"

    aea = nat_geom.CHINA_ALBERS_CRS
    cells = load_cells(MEMBERSHIP_WIDTH)
    cell_geom = cells.set_index("cell_id")

    # GSHHS coastline length inside each flagged cell.
    bbox_rows = flagged.merge(
        frame[["cell_id"]], on="cell_id", validate="one_to_one"
    )
    west = float(bbox_rows.centroid_lon.min()) - 0.3
    east = float(bbox_rows.centroid_lon.max()) + 0.3
    south = float(bbox_rows.centroid_lat.min()) - 0.3
    north = float(bbox_rows.centroid_lat.max()) + 0.3
    gshhs = gpd.read_file(
        REPO_ROOT / "work/external/gshhg_2_3_7/extracted/GSHHS_shp/h/GSHHS_h_L1.shp",
        bbox=(west, south, east, north),
        engine="pyogrio",
    ).to_crs(aea)
    coast_boundary: BaseGeometry = unary_union(list(gshhs.boundary))

    decided = frame.set_index("cell_id")
    ctx_index = context.set_index("cell_id") if context is not None else None
    rows: list[dict[str, Any]] = []
    for item in flagged.itertuples(index=False):
        cell_id = str(item.cell_id)
        ev = decided.loc[cell_id]
        geom = cell_geom.loc[cell_id, "geometry"]
        coast_len = float(geom.intersection(coast_boundary).length)
        area = float(ev.cell_area_m2)
        row = {
            "cell_id": cell_id,
            "centroid_lon": round(float(item.centroid_lon), 6),
            "centroid_lat": round(float(item.centroid_lat), 6),
            "albers_geometry_wkt": geom.wkt,
            "v0_classification": item.classification,
            "v0_classification_note": item.classification_note,
            "china_mainland_area_frac": round(
                float(ev.china_mainland_area_m2) / area, 6
            ),
            "china_island_area_frac": round(
                float(ev.china_island_area_m2) / area, 6
            ),
            "foreign_land_area_frac": round(
                float(ev.foreign_land_area_m2) / area, 6
            ),
            "foreign_landfall_area_frac": round(
                float(ev.foreign_landfall_area_m2) / area, 6
            ),
            "foreign_admin_names": str(ev.foreign_admin_names),
            "contested_admin_area_frac": round(
                float(ev.contested_admin_area_m2) / area, 6
            ),
            "contested_admin_names": str(ev.contested_admin_names),
            "unadministered_land_area_frac": round(
                float(ev.unadministered_land_area_m2) / area, 6
            ),
            "gshhs_land_area_frac": round(float(ev.total_land_area_m2) / area, 6),
            "gshhs_water_fraction": round(
                1.0 - float(ev.total_land_area_m2) / area, 6
            ),
            "gshhs_coastline_length_inside_m": round(coast_len, 1),
            "dist_to_china_mainland_m": round(
                float(ev.dist_to_china_mainland_m), 1
            ),
            "dist_to_foreign_land_m": round(float(ev.dist_to_foreign_land_m), 1),
            "nearshore_island_status": str(ev.island_class_rule),
            "membership_v1_candidate": ev.membership_v1_candidate,
            "membership_reason": ev.membership_reason,
            "admin_class": ev.admin_class,
            "v0_event_pairs_2015_2025": int(item.v0_event_pairs_2015_2025),
            "decision_input_note": (
                "target-independent GIS only; event counts recorded for "
                "provenance and are NOT decision inputs"
            ),
        }
        if ctx_index is not None and cell_id in ctx_index.index:
            c = ctx_index.loc[cell_id]
            row["murray_intertidal_present_30km"] = _safe_round(
                c.get("murray_intertidal_present_30km")
            )
            row["murray_intertidal_coarse_fraction_30km"] = _safe_round(
                c.get("murray_intertidal_coarse_fraction")
            )
            row["jrc_occurrence_mean_pct"] = _safe_round(
                c.get("jrc_occurrence_mean_pct")
            )
            row["jrc_water_ever_fraction"] = _safe_round(
                c.get("jrc_water_ever_fraction")
            )
            row["jrc_seasonality_mean_months"] = _safe_round(
                c.get("jrc_seasonality_mean_months")
            )
        else:
            row["murray_intertidal_present_30km"] = None
            row["murray_intertidal_coarse_fraction_30km"] = None
            row["jrc_occurrence_mean_pct"] = None
            row["jrc_water_ever_fraction"] = None
            row["jrc_seasonality_mean_months"] = None
        rows.append(row)
    out = pd.DataFrame(rows)
    csv_path = MANIFEST_DIR / "china_domain_artifact_audit_v0.csv"
    out.to_csv(csv_path, index=False)
    print(f"wrote {csv_path}")
    return csv_path


def summarize(frame: pd.DataFrame) -> dict[str, Any]:
    keep = frame["membership_v1_candidate"].isin(
        [KEEP_MAINLAND_COASTAL, KEEP_ISLAND_COASTAL]
    )
    reason_counts = frame["membership_reason"].value_counts().to_dict()
    admin_counts = frame["admin_class"].value_counts().to_dict()
    island_counts = frame["island_class_rule"].value_counts().to_dict()
    v0_area = float(frame["cell_area_m2"].sum())
    v1_area = float(frame.loc[keep, "cell_area_m2"].sum())
    return {
        "v0_cells": int(len(frame)),
        "v1_candidate_cells_kept": int(keep.sum()),
        "excluded_cells": int(
            (frame["membership_v1_candidate"] == "EXCLUDE_DOMAIN_ARTIFACT").sum()
        ),
        "provisional_cells": int(
            (frame["membership_v1_candidate"] == "PROVISIONAL_UNRESOLVED").sum()
        ),
        "kept_mainland_cells": int(
            (frame["membership_v1_candidate"] == KEEP_MAINLAND_COASTAL).sum()
        ),
        "kept_island_cells": int(
            (frame["membership_v1_candidate"] == KEEP_ISLAND_COASTAL).sum()
        ),
        "decision_counts": frame["membership_v1_candidate"].value_counts().to_dict(),
        "reason_counts": {str(k): int(v) for k, v in reason_counts.items()},
        "admin_class_counts": {str(k): int(v) for k, v in admin_counts.items()},
        "island_class_counts": {str(k): int(v) for k, v in island_counts.items()},
        "v0_cell_union_area_km2": round(v0_area / 1e6, 2),
        "v1_cell_union_area_km2": round(v1_area / 1e6, 2),
        "area_difference_km2": round((v0_area - v1_area) / 1e6, 2),
    }


def sensitivity(all_frames: dict[int, pd.DataFrame]) -> dict[str, Any]:
    """W5/W10/W20 membership sensitivity (membership geometry only)."""
    out: dict[str, Any] = {}
    for width, frame in all_frames.items():
        decided = apply_rule(frame)
        stats = summarize(decided)
        island_only = int(
            (decided["island_class_rule"] == "NEARSHORE_ISLAND").sum()
        )
        mixed_island = int(
            (decided["island_class_rule"] == "MAINLAND_PLUS_NEARSHORE_ISLAND").sum()
        )
        kept = decided[
            decided["membership_v1_candidate"].isin(
                [KEEP_MAINLAND_COASTAL, KEEP_ISLAND_COASTAL]
            )
        ]
        intertidal_support = None
        if "murray_intertidal_present_30km" in decided.columns:
            intertidal_support = int(
                kept["murray_intertidal_present_30km"].fillna(0).sum()
            )
        out[f"W{width}"] = {
            "cell_edge_m": width,
            "v0_cells": stats["v0_cells"],
            "v1_kept_cells": stats["v1_candidate_cells_kept"],
            "excluded_cells": stats["excluded_cells"],
            "provisional_cells": stats["provisional_cells"],
            "artifact_rate_v0": round(
                stats["excluded_cells"] / stats["v0_cells"], 6
            ),
            "island_only_cells": island_only,
            "mainland_plus_island_cells": mixed_island,
            "island_fragmentation_fraction": round(
                island_only / max(stats["v0_cells"], 1), 6
            ),
            "v1_cell_union_area_km2": stats["v1_cell_union_area_km2"],
            "cells_with_murray_intertidal_present": intertidal_support,
        }
    return out


def write_supersession(
    frame: pd.DataFrame, csv_path: Path, context_path: Path | None
) -> Path:
    stats = summarize(frame)
    excluded = frame[frame["membership_v1_candidate"] == "EXCLUDE_DOMAIN_ARTIFACT"]
    provisional = frame[frame["membership_v1_candidate"] == "PROVISIONAL_UNRESOLVED"]
    payload = {
        "artifact": "china_mainland_coastal_domain_membership",
        "supersedes": "china_national_coastal_domain_v0",
        "from_version": "v0",
        "to_version": "v1_candidate",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "grid_policy": (
            "grid_cell_geometry and cell IDs are immutable; the v0 cell "
            "registries are never overwritten or deleted. Membership is a "
            "versioned attribute on the same cell_id space."
        ),
        "decision_vocabulary": [
            "KEEP_MAINLAND_COASTAL",
            "KEEP_ISLAND_COASTAL",
            "EXCLUDE_DOMAIN_ARTIFACT",
            "PROVISIONAL_UNRESOLVED",
        ],
        "rule_parameters": {
            "island_max_area_m2": ISLAND_MAX_AREA_M2,
            "island_near_m": ISLAND_NEAR_M,
            "island_nearest_landfall": (
                "Chinese mainland strictly nearer than foreign land; "
                "v1 refinement of the v0 island rule"
            ),
            "min_land_touch_m2": 100.0,
            "border_tie_m": 500.0,
            "unadministered_land_provisional_frac": 0.01,
            "corridor_half_width_m": MEMBERSHIP_WIDTH,
            "china_admin_units": sorted(CHINA_ADMIN_UNITS),
            "contested_admin_units": sorted(CONTESTED_ADMIN_UNITS),
            "ownership_policy": (
                "Hong Kong and Macao map units are folded into PRC China; "
                "contested units are provisional within corridor reach and "
                "excluded beyond it; they are never folded or silently "
                "claimed."
            ),
        },
        "target_independence": (
            "decisions use admin ownership, GSHHS land/coastline and "
            "fixed-distance rules only; no labels, scene counts or model "
            "outputs are inputs. Murray/JRC layers are context columns only."
        ),
        "counts": stats,
        "excluded_cell_ids": sorted(excluded["cell_id"].tolist()),
        "provisional_cell_ids": sorted(provisional["cell_id"].tolist()),
        "v0_registry_sha256": _sha256(
            DOMAIN_DIR / "cells_china_albers_W10000.csv"
        ),
        "v1_candidate_csv_sha256": _sha256(csv_path),
        "artifact_audit_csv": str(
            (MANIFEST_DIR / "china_domain_artifact_audit_v0.csv").relative_to(
                REPO_ROOT
            )
        ),
        "intertidal_context_csv": (
            str(context_path.relative_to(REPO_ROOT)) if context_path else None
        ),
    }
    path = DOCS_NATIONAL / "CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {path}")
    return path


def write_sensitivity(payload: dict[str, Any]) -> Path:
    path = DOCS_NATIONAL / "DOMAIN_V1_SENSITIVITY.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gshhs-shp",
        type=Path,
        default=REPO_ROOT
        / "work/external/gshhg_2_3_7/extracted/GSHHS_shp/h/GSHHS_h_L1.shp",
    )
    parser.add_argument(
        "--admin0-shp",
        type=Path,
        default=REPO_ROOT
        / "work/external/naturalearth_10m_admin0/extracted/ne_10m_admin_0_countries.shp",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="reuse work/national/domain_v1/gis_evidence_W*.csv (no GIS rebuild)",
    )
    args = parser.parse_args()

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_NATIONAL.mkdir(parents=True, exist_ok=True)

    frames = load_gis_cache() if args.from_cache else compute_gis_evidence(
        args.gshhs_shp, args.admin0_shp
    )
    if not args.from_cache:
        write_gis_cache(frames)

    context: pd.DataFrame | None = None
    murray_path = WORK_DIR / "context_murray_v0.csv"
    jrc_path = WORK_DIR / "context_jrc_v0.csv"
    if murray_path.exists() and jrc_path.exists():
        context = load_context()
        write_intertidal_context(context)

    w10 = apply_rule(frames[MEMBERSHIP_WIDTH])
    if context is not None:
        w10 = w10.merge(
            context[
                [
                    "cell_id",
                    "murray_intertidal_present_30km",
                    "murray_intertidal_coarse_fraction",
                ]
            ],
            on="cell_id",
            how="left",
        )
    csv_path = write_candidate_manifest(w10, context)
    write_artifact_audit(w10, context)
    context_manifest = (
        MANIFEST_DIR / "china_intertidal_context_v0.csv" if context is not None else None
    )
    write_supersession(w10, csv_path, context_manifest)

    sens_frames = dict(frames)
    if context is not None:
        for width in WIDTHS:
            if width == MEMBERSHIP_WIDTH:
                sens_frames[width] = w10
            else:
                # Exact area-weighted aggregation of W10 context onto the
                # nested coarser/finer grids is not 1:1; report GIS-only
                # membership metrics for non-W10 widths (see audit doc).
                pass
    write_sensitivity({"generated_utc": datetime.now(UTC).isoformat(),
                       "widths": sensitivity(sens_frames)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
