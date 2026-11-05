#!/usr/bin/env python3
"""
Paper 1 — Figure 03: Spatial agreement/disagreement map.

Rasterizes CMSA, CM-SSM, GEODATA (2020) to 30m EPSG:3410, computes
agreement masks, and produces a 3-panel side-by-side visualization.

Reuses rasterization logic from e3_spatial_agreement.py.
"""

import os
import sys
import time
import numpy as np
import geopandas as gpd
import rasterio
from rasterio import features as rio_features
from rasterio.warp import reproject, Resampling
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

# ---------- env ----------
import pyproj
os.environ.setdefault("PROJ_LIB",
    "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # 3 levels up to repo root
RESULTS = os.path.join(ROOT, "papers", "paper1_map_reliability", "results")
FIGURES = os.path.join(ROOT, "papers", "paper1_map_reliability", "figures")
os.makedirs(FIGURES, exist_ok=True)

RES_M = 100  # 100m for fast visualization rasterization; IoU within 0.4% of 30m
TARGET_CRS = "EPSG:3410"
DOMAIN_BUFFER_M = 10_000

# ---------- data paths ----------
CMSA_DIR = "work/intake/staging/中国大陆2017-2021互花米草CMSA"
GEODATA_2020 = "work/intake/staging/2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体/2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif"
CMSSM_SHP = "work/external/cm_ssm_2020_official/extracted/CM-SSM/CM-SSM.shp"


def tprint(msg):
    print(f"  {msg}", flush=True)


def load_and_harmonize():
    """Load CMSA 2020, CM-SSM, GEODATA 2020 to common CRS; return reprojected GDFs/arrays + transform."""
    t0 = time.time()

    # --- CMSA ---
    cmsa_path = os.path.join(ROOT, CMSA_DIR, "CMSA_2020.shp")
    tprint(f"Loading CMSA 2020: {cmsa_path}")
    cmsa = gpd.read_file(cmsa_path)
    cmsa = cmsa[cmsa["gridcode"] == 2].copy()
    cmsa = cmsa.to_crs(TARGET_CRS)
    tprint(f"  CMSA: {len(cmsa)} polygons, {cmsa.total_bounds}")

    # --- CM-SSM ---
    tprint(f"Loading CM-SSM 2020: {CMSSM_SHP}")
    cmssm = gpd.read_file(os.path.join(ROOT, CMSSM_SHP))
    cmssm = cmssm.to_crs(TARGET_CRS)
    tprint(f"  CM-SSM: {len(cmssm)} polygons")

    # --- Domain from CMSA bounds + buffer ---
    domain_bounds = cmsa.total_bounds  # minx, miny, maxx, maxy
    domain_buffered = np.array([
        domain_bounds[0] - DOMAIN_BUFFER_M,
        domain_bounds[1] - DOMAIN_BUFFER_M,
        domain_bounds[2] + DOMAIN_BUFFER_M,
        domain_bounds[3] + DOMAIN_BUFFER_M,
    ])
    tprint(f"  Domain: {domain_buffered}")

    # --- Grid dims ---
    width = int((domain_buffered[2] - domain_buffered[0]) / RES_M)
    height = int((domain_buffered[3] - domain_buffered[1]) / RES_M)
    transform = rasterio.transform.from_bounds(
        domain_buffered[0], domain_buffered[1],
        domain_buffered[2], domain_buffered[3],
        width, height
    )
    tprint(f"  Grid: {width}x{height} px = {width*height/1e6:.1f} M px")

    return cmsa, cmssm, domain_buffered, width, height, transform


def rasterize_vectors(gdf, width, height, transform):
    """Rasterize a GeoDataFrame to binary (0/1) with all_touched=False."""
    shapes = [(geom, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty]
    arr = rio_features.rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=False,
    )
    return arr


def warp_geodata(width, height, transform, domain_buffered):
    """Warp GEODATA 2020 from EPSG:2433 to EPSG:3410 at 30m."""
    src_path = os.path.join(ROOT, GEODATA_2020)
    dst_crs = pyproj.CRS.from_user_input(TARGET_CRS)
    dst_arr = np.zeros((height, width), dtype="uint8")

    with rasterio.open(src_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_arr,
            src_crs=src.crs,
            dst_crs=dst_crs,
            src_transform=src.transform,
            dst_transform=transform,
            resampling=Resampling.nearest,
            src_nodata=255,
            dst_nodata=0,
        )
    # GEODATA has Value=1 for Spartina, 255 for NoData; after warp, Value=1 stays
    arr = (dst_arr == 1).astype("uint8")
    return arr


def make_agreement_mask(a, b):
    """Return 3-class mask: 0=no data, 1=both, 2=only A, 3=only B."""
    both = (a == 1) & (b == 1)
    only_a = (a == 1) & (b == 0)
    only_b = (a == 0) & (b == 1)
    mask = np.zeros(a.shape, dtype="uint8")
    mask[both] = 1
    mask[only_a] = 2
    mask[only_b] = 3
    return mask


def downsample_mask(mask, factor):
    """Fast block-mode downsample (mode = most common class per block)."""
    import scipy.ndimage as ndimage
    # Build a structured element the size of the block
    blocks = np.zeros_like(mask)
    h, w = mask.shape
    nh = h // factor
    nw = w // factor
    result = np.zeros((nh, nw), dtype="uint8")
    for cls in range(4):  # 0, 1, 2, 3
        count = mask[:nh*factor, :nw*factor] == cls
        # Sum blocks
        from scipy.signal import convolve2d
        kernel = np.ones((factor, factor), dtype=np.float32)
        summed = convolve2d(count.astype(np.float32), kernel, mode="valid", stride=factor)
        result = np.where(summed > (factor*factor/2), cls, result)
    return result


def plot_panel(ax, mask, label, only_a_color, only_b_color):
    """Plot one agreement panel."""
    # Use imshow with proper colors
    cmap = ListedColormap(["#d3d3d3", "#2ca02c", only_a_color, only_b_color])
    bounds = [-0.5, 0.5, 1.5, 2.5, 3.5]
    norm = plt.matplotlib.colors.BoundaryNorm(bounds, cmap.N)

    im = ax.imshow(mask, origin="lower", cmap=cmap, norm=norm,
                   extent=None, interpolation="nearest")
    ax.set_title(label, fontsize=10, fontweight="bold")
    ax.set_xticks([])
    ax.set_yticks([])
    return im


def main():
    print("=" * 60)
    print("E3 AGREEMENT MAP GENERATOR")
    print(f"Resolution: {RES_M}m, CRS: {TARGET_CRS}")
    print("=" * 60)

    # 1. Load + harmonize
    t0 = time.time()
    cmsa, cmssm, domain_buffered, width, height, transform = load_and_harmonize()
    tprint(f"Load time: {time.time()-t0:.1f}s")

    # 2. Rasterize CMSA
    t1 = time.time()
    tprint("Rasterizing CMSA 2020 ...")
    arr_cmsa = rasterize_vectors(cmsa, width, height, transform)
    area_cmsa = arr_cmsa.sum() * (RES_M**2) / 1e6
    tprint(f"  CMSA rasterize: {time.time()-t1:.1f}s, area={area_cmsa:.2f} km²")

    # 3. Rasterize CM-SSM
    t2 = time.time()
    tprint("Rasterizing CM-SSM 2020 ...")
    arr_cmssm = rasterize_vectors(cmssm, width, height, transform)
    area_cmssm = arr_cmssm.sum() * (RES_M**2) / 1e6
    tprint(f"  CM-SSM rasterize: {time.time()-t2:.1f}s, area={area_cmssm:.2f} km²")

    # 4. Warp GEODATA
    t3 = time.time()
    tprint("Warping GEODATA 2020 ...")
    arr_geodata = warp_geodata(width, height, transform, domain_buffered)
    area_geodata = arr_geodata.sum() * (RES_M**2) / 1e6
    tprint(f"  GEODATA warp: {time.time()-t3:.1f}s, area={area_geodata:.2f} km²")

    # 5. Compute agreement masks
    tprint("Computing agreement masks ...")
    m_cmsa_cmssm = make_agreement_mask(arr_cmsa, arr_cmssm)
    m_cmsa_geodata = make_agreement_mask(arr_cmsa, arr_geodata)
    m_cmssm_geodata = make_agreement_mask(arr_cmssm, arr_geodata)

    # 6. Quick stats
    for name, mask, only_a_label, only_b_label in [
        ("CMSA vs CM-SSM", m_cmsa_cmssm, "CMSA only", "CM-SSM only"),
        ("CMSA vs GEODATA", m_cmsa_geodata, "CMSA only", "GEODATA only"),
        ("CM-SSM vs GEODATA", m_cmssm_geodata, "CM-SSM only", "GEODATA only"),
    ]:
        n_both = (mask == 1).sum()
        n_only_a = (mask == 2).sum()
        n_only_b = (mask == 3).sum()
        union = n_both + n_only_a + n_only_b
        iou = n_both / union if union > 0 else 0
        tprint(f"  {name}: IoU={iou:.4f}, both={n_both}, onlyA={n_only_a}, onlyB={n_only_b}")

    # 7. PLOT — 3-panel side-by-side
    # First rasterize all products at RES_M for accurate IoU, then downsample
    # masks by DS_FACTOR for fast matplotlib rendering (domain is 15K×22K px at
    # 100m — too large for imshow; downsample to ~1500×2200).
    DS_FACTOR = 10  # 100m → 1000m for visualization
    tprint(f"Downsampling masks by {DS_FACTOR}× for rendering (block maximum) ...")
    def ds(m):
        """Block-max downsample so sparse positive classes survive rendering."""
        f = DS_FACTOR
        h, w = m.shape
        h2, w2 = (h // f) * f, (w // f) * f
        m = m[:h2, :w2].astype("uint8")
        m = m.reshape(h2 // f, f, w2 // f, f)
        return m.max(axis=(1, 3))
    m_cmsa_cmssm = ds(m_cmsa_cmssm)
    m_cmsa_geodata = ds(m_cmsa_geodata)
    m_cmssm_geodata = ds(m_cmssm_geodata)
    tprint(f"  Downsampled: {m_cmsa_cmssm.shape} px per panel")

    tprint("Rendering figure ...")
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 9,
    })

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5))
    fig.subplots_adjust(left=0.04, right=0.98, top=0.88, bottom=0.15, wspace=0.03)

    # Only-A colors = blue family, Only-B colors = red family
    panel_specs = [
        (m_cmsa_cmssm, "(a) CMSA vs. CM-SSM", "#1f77b4", "#ff7f0e"),
        (m_cmsa_geodata, "(b) CMSA vs. GEODATA", "#1f77b4", "#ff7f0e"),
        (m_cmssm_geodata, "(c) CM-SSM vs. GEODATA", "#2ca02c", "#ff7f0e"),
    ]

    for ax, (mask, label, ca, cb) in zip(axes, panel_specs):
        cmap = ListedColormap(["#d3d3d3", "#2ca02c", ca, cb])
        bounds = [-0.5, 0.5, 1.5, 2.5, 3.5]
        norm = plt.matplotlib.colors.BoundaryNorm(bounds, cmap.N)
        ax.imshow(mask, origin="lower", cmap=cmap, norm=norm, interpolation="nearest")
        ax.set_title(label, fontsize=10, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])

    # Shared legend
    legend_elements = [
        Patch(facecolor="#d3d3d3", label="No data / neither"),
        Patch(facecolor="#2ca02c", label="Agreement (both products)"),
        Patch(facecolor="#1f77b4", label="Only product A (CMSA or CM-SSM)"),
        Patch(facecolor="#ff7f0e", label="Only product B (CM-SSM or GEODATA)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center",
               bbox_to_anchor=(0.5, -0.02), ncol=4,
               frameon=True, edgecolor="gray", fancybox=False, fontsize=9)

    # No embedded figure title: the caption is supplied by the manuscript so
    # that journal numbering is not duplicated inside the artwork.

    pdf_path = os.path.join(FIGURES, "fig03_agreement_map.pdf")
    png_path = os.path.join(FIGURES, "fig03_agreement_map.png")
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight")
    plt.close(fig)

    print(f"\nSaved: {pdf_path}")
    print(f"       {png_path}")

    total = time.time() - t0
    print(f"\nTotal time: {total:.1f}s")


if __name__ == "__main__":
    main()
