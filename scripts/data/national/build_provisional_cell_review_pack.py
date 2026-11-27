#!/usr/bin/env python3
"""Build the owner one-pass review pack for the 10 PROVISIONAL W10 cells.

Issue #17 closure step 1 (owner comment 2026-10-06): generate a one-page
evidence sheet/map per provisional cell with deterministic rule output,
admin/coast/island evidence, distances and a *recommended* decision, then
stop at OWNER_SIGNOFF_REQUIRED. This script never decides membership: the
owner_decision columns ship empty.

Evidence is strictly target-independent GIS, identical in spirit to
audit_domain_membership_v1.py:

* immutable W10 cell boxes rebuilt from the Albers grid registry;
* Natural Earth 10 m admin-0 ownership (PRC vs contested vs foreign);
* GSHHS 2.3.7 land/coastline, audit level h (rule input) and full level
  f (review-only corroboration; the v1 rule does not consume it);
* nearest-landfall distances in the project China Albers CRS.

No Spartina labels, model outputs, scene availability, Murray or JRC
layers are read.

Outputs:
* docs/data/owner_review/figures/<cell_id>.png (per-cell evidence map)
* docs/data/owner_review/figures/overview_kinmen.png
* docs/data/owner_review/figures/overview_offshore.png
* datasets/manifests/china_w10_provisional_owner_decisions_v1.csv
  (machine-readable decision template; owner columns blank)
* docs/data/owner_review/w10_provisional_review_facts_v1.json
"""

from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spartina.data.national import geometry as nat_geom
from spartina.data.national.coastal_domain import ISLAND_MAX_AREA_M2, ISLAND_NEAR_M
from spartina.data.national.domain_membership import (
    CHINA_ADMIN_UNITS,
    CONTESTED_ADMIN_UNITS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
GRID_CSV = REPO_ROOT / "work/national/domain/cells_china_albers_W10000.csv"
CANDIDATE_CSV = (
    REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_candidate.csv"
)
GSHHS_H = (
    REPO_ROOT
    / "work/external/gshhg_2_3_7/extracted/GSHHS_shp/h/GSHHS_h_L1.shp"
)
GSHHS_F = (
    REPO_ROOT
    / "work/external/gshhg_2_3_7/extracted/GSHHS_shp/f/GSHHS_f_L1.shp"
)
ADMIN0 = (
    REPO_ROOT
    / "work/external/naturalearth_10m_admin0/extracted/ne_10m_admin_0_countries.shp"
)
FIG_DIR = REPO_ROOT / "docs/data/owner_review/figures"
DECISION_CSV = (
    REPO_ROOT / "datasets/manifests/china_w10_provisional_owner_decisions_v1.csv"
)
FACTS_JSON = (
    REPO_ROOT / "docs/data/owner_review/w10_provisional_review_facts_v1.json"
)
WIDTH_M = 10_000

# Analyst recommendations for the owner to accept or reject. These are not
# decisions; every row ships with owner_decision blank.
RECOMMENDATIONS: dict[str, dict[str, str]] = {
    "CNA10K-R00231-C00093": {
        "recommended_decision": "KEEP_ISLAND_COASTAL",
        "confidence": "MEDIUM",
        "rationale": (
            "GSHHS full resolution confirms one real 2.868 km2 island "
            "(rep 114.005E,21.860N; Wanshan island-group setting, formal "
            "name TODO_VERIFY against the official Zhuhai island "
            "register) with no administered owner in NE 10 m; nearest "
            "PRC-administered landfall 27.6 km versus foreign land 621.6 "
            "km. Binding failure is only the 25 km island reach; requires "
            "an owner-approved v1.1 verified-offshore-island rule."
        ),
    },
    "CNA10K-R00283-C00149": {
        "recommended_decision": "REMAIN_PROVISIONAL",
        "confidence": "MEDIUM",
        "rationale": (
            "Four unadministered GSHHS-f polygons (largest 2.890 km2 at "
            "119.979E,25.959N) sit 27.7-29.3 km from the PRC mainland in "
            "the Matsu channel at coordinates consistent with the "
            "Taiwan-administered Juguang group; NE 10 m omits them, so "
            "PRC ownership cannot be established and contested ownership "
            "is plausible. Needs higher-resolution admin attribution or "
            "owner expert attestation; never auto-claimed."
        ),
    },
    "CNA10K-R00314-C00162": {
        "recommended_decision": "KEEP_ISLAND_COASTAL",
        "confidence": "HIGH",
        "rationale": (
            "GSHHS-f confirms the Dachen islands (9.643 km2 main island "
            "at 121.893E,28.494N; Taizhou, Zhejiang) plus one 0.063 km2 "
            "islet; nearest administered landfall is PRC mainland 25.3- "
            "27.7 km, foreign land >334 km. Real Chinese nearshore "
            "islands kept out only by the 25 km reach; v1.1 verified-"
            "offshore-island rule required."
        ),
    },
    "CNA10K-R00314-C00163": {
        "recommended_decision": "KEEP_ISLAND_COASTAL",
        "confidence": "HIGH",
        "rationale": (
            "Same Dachen 9.643 km2 island plus islets to 0.245 km2 "
            "(121.920E,28.539N), PRC mainland landfall 27.7-31.1 km, "
            "foreign land >327 km. Real Chinese islands; binding failure "
            "is the 25 km reach only."
        ),
    },
    "CNA10K-R00316-C00163": {
        "recommended_decision": "KEEP_ISLAND_COASTAL",
        "confidence": "HIGH",
        "rationale": (
            "GSHHS-f confirms the Dongji group (largest 2.967 km2 at "
            "121.919E,28.715N; Linhai, Zhejiang) and three islets "
            "0.048-0.106 km2; PRC mainland landfall 26.2-27.3 km, "
            "foreign land >343 km. Real Chinese islands kept out only by "
            "the 25 km reach; v1.1 rule required."
        ),
    },
    "CNA10K-R00263-C00134": {
        "recommended_decision": "KEEP_ISLAND_COASTAL",
        "confidence": "LOW_POLICY_HIGH_GEOGRAPHY",
        "rationale": (
            "Kinmen archipelago cell 7.7 km off Fujian: 9.86% contested-"
            "admin (Kinmen) land, 2.80% PRC-rule nearshore islets, GSHHS "
            "land 14.30%. Geographically a nearshore island cell; keep "
            "only under an explicit owner programme decision to include "
            "contested-admin cells with disclaimer (recorded alternative: "
            "EXCLUDE_DOMAIN_ARTIFACT)."
        ),
    },
    "CNA10K-R00264-C00134": {
        "recommended_decision": "KEEP_ISLAND_COASTAL",
        "confidence": "LOW_POLICY_HIGH_GEOGRAPHY",
        "rationale": (
            "Kinmen archipelago cell 3.0 km off Fujian: 23.40% "
            "contested-admin land, 9.34% PRC-rule nearshore islets, "
            "GSHHS land 32.78%. Nearshore island geography; include only "
            "with the owner contested-territory disclaimer; alternative "
            "EXCLUDE_DOMAIN_ARTIFACT recorded."
        ),
    },
    "CNA10K-R00264-C00135": {
        "recommended_decision": "KEEP_ISLAND_COASTAL",
        "confidence": "LOW_POLICY_HIGH_GEOGRAPHY",
        "rationale": (
            "Core Kinmen cell 8.9 km off Fujian: 59.92% contested-admin "
            "land (the 142 km2 Kinmen island polygon), no PRC-admin land. "
            "Inclusion is a programme sovereignty-posture decision, not a "
            "GIS decision; recommended include-with-disclaimer for "
            "coastal-monitoring completeness, alternative EXCLUDE."
        ),
    },
    "CNA10K-R00264-C00136": {
        "recommended_decision": "KEEP_ISLAND_COASTAL",
        "confidence": "LOW_POLICY_HIGH_GEOGRAPHY",
        "rationale": (
            "Eastern Kinmen archipelago cell 5.6 km off Fujian: 22.88% "
            "contested-admin land, 0.43% PRC-rule nearshore islets, plus "
            "nine small GSHHS-f islets. Nearshore island geography; "
            "include only with owner contested-territory disclaimer; "
            "alternative EXCLUDE."
        ),
    },
    "CNA10K-R00265-C00136": {
        "recommended_decision": "KEEP_ISLAND_COASTAL",
        "confidence": "LOW_POLICY_HIGH_GEOGRAPHY",
        "rationale": (
            "Closest Kinmen-archipelago cell, 0.9 km from the Fujian "
            "shore: 1.94% contested-admin land, 0.47% PRC-rule nearshore "
            "islets, GSHHS land 2.41%; mostly water. A mainland-adjacent "
            "monitoring cell; include only with owner contested-territory "
            "disclaimer; alternative EXCLUDE."
        ),
    },
}


@dataclass
class Layers:
    """Pre-clipped target-independent layers in China Albers CRS."""

    land_h: gpd.GeoDataFrame
    land_f: gpd.GeoDataFrame
    china_admin: BaseGeometry
    mainland_land: gpd.GeoDataFrame
    contested_land: gpd.GeoDataFrame
    foreign_land: gpd.GeoDataFrame


def git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def load_cells() -> gpd.GeoDataFrame:
    frame = pd.read_csv(GRID_CSV)
    aea = nat_geom.CHINA_ALBERS_CRS
    geometries = [
        box(int(r.col) * WIDTH_M, int(r.row) * WIDTH_M,
            (int(r.col) + 1) * WIDTH_M, (int(r.row) + 1) * WIDTH_M)
        for r in frame.itertuples(index=False)
    ]
    return gpd.GeoDataFrame(frame, geometry=geometries, crs=aea)


def load_layers(bbox_wgs: tuple[float, float, float, float]) -> Layers:
    aea = nat_geom.CHINA_ALBERS_CRS
    margin = box(
        bbox_wgs[0] - 0.3, bbox_wgs[1] - 0.3,
        bbox_wgs[2] + 0.3, bbox_wgs[3] + 0.3,
    )
    region_wgs = gpd.GeoSeries([margin], crs=4326)

    def _land(level: str) -> gpd.GeoDataFrame:
        raw = gpd.read_file(level, bbox=margin.bounds, engine="pyogrio")
        clipped = gpd.clip(raw, region_wgs)
        return gpd.GeoDataFrame(
            geometry=list(clipped.to_crs(aea).geometry), crs=aea
        )

    land_h = _land(str(GSHHS_H))
    land_f = _land(str(GSHHS_F))
    admin = gpd.read_file(ADMIN0, bbox=margin.bounds, engine="pyogrio")
    china_wgs = unary_union(
        admin.loc[admin["ADMIN"].isin(CHINA_ADMIN_UNITS), "geometry"].tolist()
    )
    china_admin = gpd.GeoSeries([china_wgs], crs=4326).to_crs(aea).iloc[0]
    foreign_admin = (
        admin[
            ~admin["ADMIN"].isin(CHINA_ADMIN_UNITS | CONTESTED_ADMIN_UNITS)
        ][["ADMIN", "geometry"]]
        .to_crs(aea)
        .dissolve(by="ADMIN", as_index=False)
    )
    contested_admin = (
        admin[admin["ADMIN"].isin(CONTESTED_ADMIN_UNITS)][["ADMIN", "geometry"]]
        .to_crs(aea)
        .dissolve(by="ADMIN", as_index=False)
    )
    mainland_land = gpd.GeoDataFrame(
        geometry=gpd.clip(land_f, gpd.GeoSeries([china_admin], crs=aea)).geometry,
        crs=aea,
    )
    contested_land = gpd.overlay(
        land_f, contested_admin, how="intersection", keep_geom_type=True
    )
    foreign_land = gpd.overlay(
        land_f, foreign_admin, how="intersection", keep_geom_type=True
    )
    return Layers(
        land_h=land_h,
        land_f=land_f,
        china_admin=china_admin,
        mainland_land=mainland_land,
        contested_land=contested_land,
        foreign_land=foreign_land,
    )


def pieces_in_cell(
    layers: Layers, cell: BaseGeometry
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    def _clip(land: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        joined = gpd.sjoin(
            gpd.GeoDataFrame(geometry=[cell], crs=layers.land_f.crs),
            land,
            how="inner",
            predicate="intersects",
        )
        if joined.empty:
            return gpd.GeoDataFrame(
                geometry=[], crs=layers.land_f.crs
            )
        selected = land.loc[joined["index_right"].unique()]
        return gpd.GeoDataFrame(
            geometry=list(selected.geometry), crs=layers.land_f.crs
        )

    mainland = _clip(layers.mainland_land)
    contested = gpd.clip(
        layers.contested_land, gpd.GeoSeries([cell], crs=layers.land_f.crs)
    )
    foreign = gpd.clip(
        layers.foreign_land, gpd.GeoSeries([cell], crs=layers.land_f.crs)
    )
    return mainland, contested, foreign


def unadministered_pieces(
    layers: Layers, cell: BaseGeometry
) -> list[dict[str, Any]]:
    """Full-resolution land pieces with no admin-0 polygon (review only)."""
    joined = gpd.sjoin(
        gpd.GeoDataFrame(geometry=[cell], crs=layers.land_f.crs),
        layers.land_f,
        how="inner",
        predicate="intersects",
    )
    out: list[dict[str, Any]] = []
    if joined.empty:
        return out
    for idx in joined["index_right"].unique():
        geom = layers.land_f.loc[idx, "geometry"]
        rep = geom.representative_point()
        if rep.within(layers.china_admin):
            admin_state = "PRC_ADMIN"
        elif any(rep.within(g) for g in layers.contested_land.geometry):
            admin_state = "CONTESTED_ADMIN"
        elif any(rep.within(g) for g in layers.foreign_land.geometry):
            admin_state = "FOREIGN_ADMIN"
        else:
            admin_state = "UNADMINISTERED"
        landfall = layers.china_admin.boundary.interpolate(
            layers.china_admin.boundary.project(rep)
        )
        rep_wgs = gpd.GeoSeries([rep], crs=layers.land_f.crs).to_crs(4326).iloc[0]
        lf_wgs = (
            gpd.GeoSeries([landfall], crs=layers.land_f.crs).to_crs(4326).iloc[0]
        )
        out.append({
            "polygon_idx": int(idx),
            "admin_state_at_rep": admin_state,
            "area_km2": round(geom.area / 1e6, 4),
            "rep_lon": round(rep_wgs.x, 5),
            "rep_lat": round(rep_wgs.y, 5),
            "nearest_prc_mainland_landfall_lon": round(lf_wgs.x, 5),
            "nearest_prc_mainland_landfall_lat": round(lf_wgs.y, 5),
            "rep_dist_to_prc_mainland_m": round(rep.distance(layers.china_admin), 1),
            "within_25km_island_reach": bool(
                rep.distance(layers.china_admin) <= ISLAND_NEAR_M
                and geom.area <= ISLAND_MAX_AREA_M2
            ),
        })
    out.sort(key=lambda item: -item["area_km2"])
    return out


def render_map(
    cell_id: str,
    cell: BaseGeometry,
    layers: Layers,
    mainland: gpd.GeoDataFrame,
    contested: gpd.GeoDataFrame,
    pieces: list[dict[str, Any]],
    reason: str,
    center_lon: float,
    center_lat: float,
    out_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 8.0), dpi=150)
    # Land context (GSHHS full resolution): neutral fill.
    layers.land_f.plot(ax=ax, facecolor="#e8e6df", edgecolor="#9a968b",
                       linewidth=0.4)
    if not mainland.empty:
        mainland.plot(ax=ax, facecolor="#bdd7ee", edgecolor="#2f5f9f",
                      linewidth=0.8)
    if not contested.empty:
        contested.plot(ax=ax, facecolor="#f4c7c3", edgecolor="#b33a3a",
                       linewidth=0.9, hatch="////")
    # Unadministered review pieces highlighted in gold with rep markers.
    for piece in pieces:
        geom = layers.land_f.loc[piece["polygon_idx"], "geometry"]
        if piece["admin_state_at_rep"] == "UNADMINISTERED":
            gpd.GeoSeries([geom], crs=layers.land_f.crs).plot(
                ax=ax, facecolor="#ffe08a", edgecolor="#b58900", linewidth=1.0
            )
            rep = geom.representative_point()
            ax.plot(rep.x, rep.y, marker="^", color="#8a5c00", markersize=7)
            landfall = layers.china_admin.boundary.interpolate(
                layers.china_admin.boundary.project(rep)
            )
            ax.plot([rep.x, landfall.x], [rep.y, landfall.y],
                    color="#8a5c00", linestyle="--", linewidth=1.0)
            ax.annotate(
                f"{piece['area_km2']:.3f} km2\n"
                f"{piece['rep_dist_to_prc_mainland_m']/1000:.1f} km",
                xy=(rep.x, rep.y), xytext=(6, 4),
                textcoords="offset points", fontsize=7, color="#5c3d00",
            )
    # Cell boundary last.
    gpd.GeoSeries([cell], crs=layers.land_f.crs).plot(
        ax=ax, facecolor="none", edgecolor="black", linewidth=2.0
    )
    minx, miny, maxx, maxy = cell.bounds
    pad = 2_500
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(
        f"{cell_id}\n{reason} | center {center_lon:.4f}E, {center_lat:.4f}N",
        fontsize=10,
    )
    legend_items = [
        Patch(facecolor="#bdd7ee", edgecolor="#2f5f9f",
              label="PRC-admin land (NE 10m + GSHHS-f)"),
        Patch(facecolor="#f4c7c3", edgecolor="#b33a3a", hatch="////",
              label="Contested-admin land (NE 10m: Taiwan)"),
        Patch(facecolor="#ffe08a", edgecolor="#b58900",
              label="Unadministered GSHHS-f land (review)"),
        Patch(facecolor="#e8e6df", edgecolor="#9a968b",
              label="Other GSHHS-f land"),
        Line2D([0], [0], color="#8a5c00", linestyle="--",
               label="rep point to nearest PRC landfall"),
        Line2D([0], [0], color="black", linewidth=2.0,
               label="Immutable W10 cell boundary"),
    ]
    ax.legend(handles=legend_items, loc="lower left", fontsize=7,
              framealpha=0.92, title="Target-independent evidence only",
              title_fontsize=7)
    # Simple 2 km scale bar.
    x0 = maxx - 4_800
    y0 = miny + 700
    ax.plot([x0, x0 + 2_000], [y0, y0], color="black", linewidth=3.0)
    ax.text(x0 + 1_000, y0 + 220, "2 km", ha="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def render_overview(
    cells: gpd.GeoDataFrame,
    layers: Layers,
    group_ids: list[str],
    title: str,
    out_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8.0, 9.0), dpi=150)
    layers.land_f.plot(ax=ax, facecolor="#e8e6df", edgecolor="#b7b2a6",
                       linewidth=0.3)
    if not layers.mainland_land.empty:
        layers.mainland_land.plot(ax=ax, facecolor="#bdd7ee",
                                  edgecolor="#2f5f9f", linewidth=0.5)
    if not layers.contested_land.empty:
        layers.contested_land.plot(ax=ax, facecolor="#f4c7c3",
                                   edgecolor="#b33a3a", linewidth=0.5)
    subset = cells.loc[cells.index.isin(group_ids)].reset_index()
    subset.boundary.plot(ax=ax, edgecolor="black", linewidth=1.4)
    for item in subset.itertuples():
        ax.annotate(
            item.cell_id.replace("CNA10K-", ""),
            xy=(item.geometry.centroid.x, item.geometry.centroid.y),
            ha="center", va="center", fontsize=6.5,
        )
    minx, miny, maxx, maxy = subset.total_bounds
    ax.set_xlim(minx - 12_000, maxx + 12_000)
    ax.set_ylim(miny - 12_000, maxy + 12_000)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    DECISION_CSV.parent.mkdir(parents=True, exist_ok=True)

    candidate = pd.read_csv(CANDIDATE_CSV)
    provisional = candidate[
        candidate["membership_v1_candidate"] == "PROVISIONAL_UNRESOLVED"
    ].copy()
    assert len(provisional) == 10, f"expected 10 provisional cells, got {len(provisional)}"
    cells = load_cells().set_index("cell_id")

    # Two region groups (Pearl + Matsu + Zhejiang are far apart; the two
    # groups are rendered separately for readability).
    kinmen_ids = [
        cid for cid in provisional["cell_id"]
        if provisional.loc[provisional.cell_id == cid, "membership_reason"]
        .iloc[0] == "CONTESTED_ADMIN_NEARSHORE"
    ]
    offshore_ids = [
        cid for cid in provisional["cell_id"] if cid not in kinmen_ids
    ]

    facts: dict[str, Any] = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "status": "OWNER_SIGNOFF_REQUIRED",
        "rule_input_shoreline": "GSHHS 2.3.7 level h (rule); level f review-only",
        "admin_layer": "Natural Earth 10 m admin-0 countries",
        "analysis_crs": str(nat_geom.CHINA_ALBERS_CRS),
        "island_rule_reach_m": ISLAND_NEAR_M,
        "island_rule_max_area_km2": ISLAND_MAX_AREA_M2 / 1e6,
        "cells": {},
    }
    template_rows: list[dict[str, str]] = []

    groups = {"kinmen": kinmen_ids, "offshore": offshore_ids}
    layer_cache: dict[str, Layers] = {}
    for group, ids in groups.items():
        sub = cells.loc[ids]
        wgs = sub.to_crs(4326)
        layer_cache[group] = load_layers(tuple(wgs.total_bounds))

    for item in provisional.itertuples():
        cid = str(item.cell_id)
        cell = cells.loc[cid, "geometry"]
        group = "kinmen" if cid in kinmen_ids else "offshore"
        layers = layer_cache[group]
        mainland, contested, _foreign = pieces_in_cell(layers, cell)
        pieces = unadministered_pieces(layers, cell)
        evidence = json.loads(item.membership_evidence)
        fig_path = FIG_DIR / f"{cid}.png"
        render_map(
            cid, cell, layers, mainland, contested, pieces,
            item.membership_reason,
            float(item.center_lon), float(item.center_lat),
            fig_path,
        )
        rec = RECOMMENDATIONS[cid]
        binding = (
            "contested-territory programme policy (include-with-disclaimer "
            "vs exclude)"
            if item.membership_reason == "CONTESTED_ADMIN_NEARSHORE"
            else "25 km island reach / NE 10 m admin attribution gap"
        )
        facts["cells"][cid] = {
            "center_lon": float(item.center_lon),
            "center_lat": float(item.center_lat),
            "membership_reason": item.membership_reason,
            "deterministic_rule_result": item.membership_v1_candidate,
            "rule_evidence_h_level": evidence,
            "f_level_review_pieces": pieces,
            "mainland_land_area_frac_f": round(
                float(mainland.area.sum()) / (WIDTH_M**2), 6
            ),
            "contested_land_area_frac_f": round(
                float(contested.area.sum()) / (WIDTH_M**2), 6
            ),
            "figure": str(fig_path.relative_to(REPO_ROOT)),
            "recommended_decision": rec["recommended_decision"],
            "recommendation_confidence": rec["confidence"],
            "recommendation_rationale": rec["rationale"],
            "binding_issue": binding,
        }
        template_rows.append({
            "cell_id": cid,
            "center_lon": f"{float(item.center_lon):.6f}",
            "center_lat": f"{float(item.center_lat):.6f}",
            "provisional_reason": item.membership_reason,
            "deterministic_rule_result": item.membership_v1_candidate,
            "recommended_decision": rec["recommended_decision"],
            "recommendation_confidence": rec["confidence"],
            "binding_issue": binding,
            "owner_decision": "",
            "owner_name": "",
            "owner_signoff_date": "",
            "owner_notes": "",
            "review_status": "OWNER_SIGNOFF_REQUIRED",
            "pack_figure": str(fig_path.relative_to(REPO_ROOT)),
        })

    render_overview(
        cells, layer_cache["kinmen"], kinmen_ids,
        "Five Kinmen-archipelago provisional cells (contested admin)",
        FIG_DIR / "overview_kinmen.png",
    )
    render_overview(
        cells, layer_cache["offshore"], offshore_ids,
        "Five unattributed-land provisional cells (Wanshan / Matsu / Zhejiang)",
        FIG_DIR / "overview_offshore.png",
    )

    fieldnames = list(template_rows[0].keys())
    with DECISION_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(template_rows)
    FACTS_JSON.write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {DECISION_CSV}")
    print(f"wrote {FACTS_JSON}")
    print(f"wrote {len(template_rows) + 2} figures to {FIG_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
