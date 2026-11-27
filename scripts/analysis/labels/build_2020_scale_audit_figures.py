#!/usr/bin/env python3
"""Candidate figures for the Issue #18 audit (A-E).

Reads tracked aggregate tables plus the original product bytes for the
two spatial example sites only. Native vector geometry is drawn as
vectors; the 30 m GEODATA window is warped (nearest neighbour) into the
local UTM frame for visual comparison. Nothing is upsampled to imply
greater information content: panel labels state each product's nominal
resolution.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import rasterio.warp
from matplotlib.patches import Patch
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_TABLES = REPO_ROOT / "datasets/manifests/2020_label_scale_audit_v1"
FIG_OUT = REPO_ROOT / "docs/analysis/figures"
WORK = REPO_ROOT / "work/issue18"

GEODATA_TIF = REPO_ROOT / (
    "work/intake/staging/2020年中国滨海30 m分辨率互花米草空间分布动态数据集"
    "-数据实体/2020年中国滨海30 m分辨率互花米草空间分布动态数据集"
    "-数据实体.tif"
)
CMSA_SHP = REPO_ROOT / (
    "work/intake/staging/中国大陆2017-2021互花米草CMSA/CMSA_2020.shp"
)
CMSSM_SHP = REPO_ROOT / "old datasets/30mSpartinaChina/2020/CM-SSM/CM-SSM.shp"

C_GEO = "#c0392b"
C_CMSA = "#1f6fb4"
C_CMSSM = "#238b45"
plt.rcParams.update({
    "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
    "figure.dpi": 130, "savefig.dpi": 200, "font.family": "DejaVu Sans",
})

REGION_ORDER = [
    "Liaoning", "Tianjin", "Hebei", "Shandong", "Jiangsu", "Shanghai",
    "Zhejiang", "Fujian", "Guangdong", "Guangxi", "UNATTRIBUTED",
]
DIST_ORDER = ["0-30m", "30-60m", "60-120m", "120-300m", ">=300m"]
PATCH_ORDER = [
    "<100m2(sliver)", "100-900m2", "900-2500m2", "2500-1e4m2",
    "1e4-1e5m2", ">=1e5m2",
]
OCC_ORDER = ["0", "(0,0.25]", "(0.25,0.5]", "(0.5,0.75]", "(0.75,1]"]


def figure_a() -> None:
    area = pd.read_csv(OUT_TABLES / "table1_mapped_area.csv")
    pw = pd.read_csv(OUT_TABLES / "table2_pairwise_agreement_by_region.csv")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 3.8))

    native = area[area.support == "native"].set_index("product")
    labels = ["GEODATA\n30 m raster", "CMSA\n10 m vector", "CM-SSM\nsub-m vector"]
    vals = [native.loc["geodata", "mapped_area_km2"],
            native.loc["cmsa", "mapped_area_km2"],
            native.loc["cmssm", "mapped_area_km2"]]
    bars = ax1.bar(labels, vals, color=[C_GEO, C_CMSA, C_CMSSM])
    for bar, v in zip(bars, vals, strict=True):
        ax1.text(bar.get_x() + bar.get_width() / 2, v + 6, f"{v:.1f}",
                 ha="center", fontsize=9)
    ax1.set_ylabel("2020 mapped area (km$^2$)")
    ax1.set_title("A1 National mapped area, native support")
    ax1.set_ylim(0, max(vals) * 1.15)

    sub = pw[pw.support == "30m_GEODATA_native_grid"]
    rows = []
    for region in REGION_ORDER:
        rsub = sub[sub.region == region].set_index("pair")
        if rsub.empty:
            continue
        rows.append({
            "region": region,
            "GEODATA": float(rsub.loc["GEO_CMSA", "area_a_km2"]),
            "CMSA": float(rsub.loc["GEO_CMSA", "area_b_km2"]),
            "CMSSM": float(rsub.loc["GEO_CMSSM", "area_b_km2"]),
        })
    reg = pd.DataFrame(rows).set_index("region")
    x = np.arange(len(reg))
    w = 0.26
    ax2.bar(x - w, reg["GEODATA"], w, label="GEODATA", color=C_GEO)
    ax2.bar(x, reg["CMSA"], w, label="CMSA", color=C_CMSA)
    ax2.bar(x + w, reg["CMSSM"], w, label="CM-SSM", color=C_CMSSM)
    ax2.set_xticks(x)
    ax2.set_xticklabels(reg.index, rotation=40, ha="right", fontsize=8)
    ax2.set_ylabel("Mapped area on 30 m support (km$^2$)")
    ax2.set_title("A2 Regional mapped area (30 m comparison support)")
    ax2.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_OUT / "figA_mapped_area.png", bbox_inches="tight")
    plt.close(fig)


def figure_c() -> None:
    b = pd.read_csv(OUT_TABLES / "table4_boundary_distance_disagreement.csv")
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    styles = {
        ("30m_GEODATA_native_grid", "GEO_CMSA"): (C_GEO, "o", "GEO vs CMSA (30 m)"),
        ("30m_GEODATA_native_grid", "GEO_CMSSM"): (C_CMSSM, "s", "GEO vs CM-SSM (30 m)"),
        ("30m_GEODATA_native_grid", "CMSA_CMSSM"): ("#d95f02", "^", "CMSA vs CM-SSM (30 m)"),
        ("10m_project_lattice", "CMSA_CMSSM"): ("#7b5ea7", "D", "CMSA vs CM-SSM (10 m)"),
    }
    for (support, pair), grp0 in b.groupby(["support", "pair"]):
        grp = grp0.copy()
        grp["distance_to_nearest_mapped_boundary_m"] = grp[
            "distance_to_nearest_mapped_boundary_m"
        ].astype(str)
        agg = grp.groupby(
            "distance_to_nearest_mapped_boundary_m", observed=True
        ).apply(lambda g: np.average(
            g["binary_disagreement_fraction"], weights=g["denominator_pixels"]
        ), include_groups=False)
        agg = agg.reindex([d for d in DIST_ORDER if d in agg.index])
        if agg.dropna().empty:
            continue
        color, marker, label = styles[(support, pair)]
        ax.plot(range(len(agg)), agg.values, color=color, marker=marker,
                lw=1.6, ms=5, label=label)
    ax.set_xticks(range(len(DIST_ORDER)))
    ax.set_xticklabels(DIST_ORDER)
    ax.set_xlabel("Distance to nearest mapped boundary")
    ax.set_ylabel("Binary disagreement fraction")
    ax.set_title("C Disagreement concentrates at mapped boundaries")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_OUT / "figC_boundary_distance.png", bbox_inches="tight")
    plt.close(fig)


def figure_d() -> None:
    om = pd.read_csv(OUT_TABLES / "table6_patch_omission_by_size.csv")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.0, 3.9))

    sub = om[om.support == "30m"]
    x = np.arange(len(PATCH_ORDER))
    w = 0.38
    for i, (product, color, label) in enumerate(
        (("cmsa", C_CMSA, "CMSA patches"), ("cmssm", C_CMSSM, "CM-SSM patches"))
    ):
        s = sub[sub["product"] == product].set_index("patch_size_class")
        vals = [float(s.loc[p, "zero_geodata_patch_fraction"]) if p in s.index
                else np.nan for p in PATCH_ORDER]
        ax1.bar(x + (i - 0.5) * w, vals, w, color=color, label=label)
    ax1.set_xticks(x)
    ax1.set_xticklabels(PATCH_ORDER, rotation=35, ha="right", fontsize=7.5)
    ax1.set_ylabel("Fraction of patches with zero GEODATA cover")
    ax1.set_title("D1 Coarse-product omission vs patch size (30 m support)")
    ax1.legend(frameon=False, fontsize=8)

    sub10 = om[om.support == "10m"]
    for i, (product, color, label) in enumerate(
        (("cmsa", C_CMSA, "CMSA patches (by CM-SSM)"),
         ("cmssm", C_CMSSM, "CM-SSM patches (by CMSA)"))
    ):
        s = sub10[sub10["product"] == product].set_index("patch_size_class")
        vals = [float(s.loc[p, "zero_other_fine_patch_fraction"]) if p in s.index
                else np.nan for p in PATCH_ORDER]
        ax2.bar(x + (i - 0.5) * w, vals, w, color=color, label=label)
    ax2.set_xticks(x)
    ax2.set_xticklabels(PATCH_ORDER, rotation=35, ha="right", fontsize=7.5)
    ax2.set_ylabel("Fraction of patches absent in the other fine product")
    ax2.set_title("D2 Fine-product mutual omission vs patch size (10 m support)")
    ax2.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_OUT / "figD_patch_size.png", bbox_inches="tight")
    plt.close(fig)


def figure_e() -> None:
    occ = pd.read_csv(OUT_TABLES / "table7_coarse_pixel_occupancy.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.8), sharey=True)
    colors = ["#2c3e50", "#9ecae1", "#f6c465", "#e08214", "#a63603"]
    for ax, fine in zip(axes, ("CMSA", "CMSSM"), strict=True):
        sub = occ[occ.fine_product == fine]
        x = np.array([0, 1])
        bottoms = np.zeros(2)
        for bin_label, color in zip(OCC_ORDER, colors, strict=True):
            vals = []
            for g in (0, 1):
                row = sub[(sub.geodata_class == g)
                          & (sub.fine_occupancy_bin == bin_label)]
                vals.append(float(row.fraction_within_geodata_class.iloc[0])
                            if len(row) else 0.0)
            ax.bar(x, vals, bottom=bottoms, color=color, label=bin_label,
                   width=0.55)
            bottoms += np.array(vals)
        ax.set_xticks(x)
        ax.set_xticklabels(["GEODATA = 0", "GEODATA = 1"])
        ax.set_title(f"{fine} fractional occupancy within 30 m pixels")
    axes[0].set_ylabel("Fraction of 30 m pixels")
    axes[1].legend(title="Fine occupancy", frameon=False, fontsize=7.5,
                   bbox_to_anchor=(1.02, 1.0), loc="upper left")
    fig.suptitle(
        "E Binary 30 m classes contain broadly mixed fine-resolution occupancy",
        y=1.02, fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(FIG_OUT / "figE_occupancy.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure B: multi-resolution site panels
# ---------------------------------------------------------------------------

def _repair(product_path: Path, gridcode_filter: int | None = None) -> gpd.GeoDataFrame:
    """Same make_valid/explode recipe as the audit runner (visual copy)."""
    gdf = gpd.read_file(product_path, engine="pyogrio")
    if gridcode_filter is not None:
        gdf = gdf[gdf["gridcode"] == gridcode_filter].copy()
    fixed = gpd.GeoDataFrame(
        gdf.drop(columns="geometry"), geometry=gdf.make_valid(), crs=gdf.crs
    ).explode(ignore_index=True)
    fixed = fixed[~fixed.geometry.is_empty].copy()
    fixed = fixed[fixed.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    return fixed


def _choose_sites(cmsa: gpd.GeoDataFrame,
                  cmssm: gpd.GeoDataFrame) -> tuple[tuple[float, float, str],
                                                    tuple[float, float, str]]:
    # Site 1: centroid of the largest CMSA patch (large continuous meadow).
    patch_areas = cmsa.groupby("Id").geometry.apply(lambda s: s.area.sum())
    big_id = patch_areas.idxmax()
    p_big = cmsa[cmsa["Id"] == big_id].union_all()
    sx, sy = p_big.centroid.x, p_big.centroid.y

    # Site 2: densest cluster of small CM-SSM patches in Zhejiang.
    from scipy.spatial import cKDTree

    zj = cmssm[(cmssm["name"] == "ZJ")
               & (cmssm.geometry.area > 5_000)
               & (cmssm.geometry.area < 20_000)].copy()
    centroids = zj.geometry.centroid
    coords = np.column_stack([centroids.x.to_numpy(),
                              centroids.y.to_numpy()])
    tree = cKDTree(coords)
    counts = tree.query_ball_point(coords, r=1200.0, return_length=True)
    j = int(np.asarray(counts).argmax())
    return (
        (sx, sy, "large_continuous"),
        (float(coords[j, 0]), float(coords[j, 1]), "fragmented_small"),
    )


def figure_b() -> None:
    cmsa = _repair(CMSA_SHP, gridcode_filter=2)
    cmssm = _repair(CMSSM_SHP)
    sites = _choose_sites(cmsa, cmssm)
    extent_m = 2400.0

    fig, axes = plt.subplots(
        3, 2, figsize=(7.6, 10.6),
        gridspec_kw={"hspace": 0.12, "wspace": 0.05},
    )
    site_meta = []
    for col, (cx, cy, kind) in enumerate(sites):
        minx, miny = cx - extent_m / 2, cy - extent_m / 2
        maxx, maxy = cx + extent_m / 2, cy + extent_m / 2
        win = box(minx, miny, maxx, maxy)
        for row, (gdf, color, title) in enumerate((
            (cmssm, C_CMSSM, "CM-SSM 2020 (native sub-m vector)"),
            (cmsa, C_CMSA, "CMSA 2020 (native 10 m vector delivery)"),
        )):
            ax = axes[row, col]
            sel = gpd.clip(gdf, win)
            if not sel.empty:
                sel.plot(ax=ax, facecolor=color, edgecolor="none", alpha=0.85)
            ax.set_xlim(minx, maxx)
            ax.set_ylim(miny, maxy)
            ax.set_xticks([])
            ax.set_yticks([])
            if col == 0:
                ax.set_ylabel(title, fontsize=9)
        ax = axes[2, col]
        size = 240
        dst_transform = from_bounds(minx, miny, maxx, maxy, size, size)
        dst = np.zeros((size, size), dtype="uint8")
        with rasterio.open(GEODATA_TIF) as ds:
            rasterio.warp.reproject(
                source=rasterio.band(ds, 1),
                destination=dst,
                src_transform=ds.transform,
                src_crs=ds.crs,
                dst_transform=dst_transform,
                dst_crs="EPSG:32650",
                resampling=Resampling.nearest,
            )
        view = dst.astype(float)
        view[dst != 1] = np.nan
        ax.imshow(
            view,
            extent=(minx, maxx, miny, maxy), origin="upper",
            cmap=matplotlib.colors.ListedColormap([C_GEO]),
            vmin=0.0, vmax=1.0, zorder=2,
        )
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        ax.set_xticks([])
        ax.set_yticks([])
        if col == 0:
            ax.set_ylabel("GEODATA 2020 (native 30 m raster, NN warp)",
                          fontsize=9)
        site_meta.append({"kind": kind, "utm50_center_x": cx,
                          "utm50_center_y": cy, "extent_m": extent_m})
    titles = ["B1 Large continuous meadow setting",
              "B2 Fragmented small-patch setting"]
    for col, t in enumerate(titles):
        axes[0, col].set_title(t, fontsize=10)
    legend_handles = [
        Patch(facecolor=C_CMSSM, label="CM-SSM"),
        Patch(facecolor=C_CMSA, label="CMSA"),
        Patch(facecolor=C_GEO, label="GEODATA"),
    ]
    fig.legend(handles=legend_handles, loc="lower center", ncol=3,
               frameon=False, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout()
    fig.savefig(FIG_OUT / "figB_site_panels.png", bbox_inches="tight")
    plt.close(fig)
    (WORK / "figB_sites.json").write_text(
        json.dumps(site_meta, indent=2) + "\n"
    )


def main() -> int:
    FIG_OUT.mkdir(parents=True, exist_ok=True)
    figure_a()
    figure_c()
    figure_d()
    figure_e()
    figure_b()
    for p in sorted(FIG_OUT.glob("fig*.png")):
        if p.name.startswith(("figA", "figB", "figC", "figD", "figE")):
            print(p.name, p.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
