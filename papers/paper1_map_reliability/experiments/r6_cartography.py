#!/usr/bin/env python3
"""
R6 cartography — shared design system for Paper 1 figures.

Unified, colorblind-safe, grayscale-print-safe academic cartography for all
Paper 1 maps. Base geographic data: Natural Earth 1:10m (public domain,
v5.1.1; passports in work/external/*/SOURCE_PASSPORT.json and
docs/audit/source_passports/). Product rasters: cached 100 m EPSG:3410
arrays (work/cache/paper1_100m/products_100m_epsg3410.npz) identical to the
analysis grids.

Design rules (auditable in audits/r6_cartographic_qa.md):
  - land warm gray, sea light blue-gray, coastline dark gray,
    province boundaries thin light gray
  - Spartina / agreement teal-green; only-A blue; only-B orange;
    disagreement hotspots warm red; unknown/undetected = basemap
  - Okabe-Ito colorblind-safe palette; distinct grayscale luminance
  - vector PDF output (rasterized dense data layers only)
  - no Google/commercial tiles; no fabricated boundaries
"""

import os
import numpy as np
import geopandas as gpd
import pyproj
from pyproj import Transformer
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch, FancyArrow

os.environ.setdefault(
    "PROJ_LIB", "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")

ROOT = "/data/yingda/Spartina-Earth"
NE_ADMIN0 = os.path.join(
    ROOT, "work/external/naturalearth_10m_admin0/extracted/"
          "ne_10m_admin_0_countries.shp")
NE_ADMIN1 = os.path.join(
    ROOT, "work/external/naturalearth_10m_admin1/extracted/"
          "ne_10m_admin_1_states_provinces.shp")
CACHE = os.path.join(ROOT, "work/cache/paper1_100m")

TARGET_CRS = "EPSG:3410"          # NSIDC EASE-Grid Global (equal-area)
RES_M = 100

# ----------------------------- palette ------------------------------------
PAL = {
    "land":       "#EDE7DC",   # warm gray
    "sea":        "#D7E0E8",   # light blue-gray
    "coast":      "#3F3F3F",   # dark gray coastline
    "province":   "#C9C3B8",   # thin light province lines
    "intl":       "#9C9C9C",   # international borders
    "spartina":   "#0F8A6D",   # teal-green (presence / agreement)
    "both":       "#0F8A6D",   # agreement class (same teal)
    "only_a":     "#0072B2",   # blue  (Okabe-Ito)
    "only_b":     "#E69F00",   # orange (Okabe-Ito)
    "hot":        "#D55E00",   # warm red (Okabe-Ito vermillion)
    "direct":     "#5AA8A0",   # direct marine-polygon membership (muted teal)
    "neutral":    "#BDBDBD",
    "region1":    "#7FA8CC",   # Bohai/Yellow tint (luminance ladder)
    "region2":    "#B0C4D6",   # East China tint
    "region3":    "#D3DEE8",   # South China tint
    "text":       "#2B2B2B",
    "zoombox":    "#B23A2E",   # zoom locator rectangle
}

REGION_LABEL = {
    "Bohai_Yellow": "Bohai / Yellow Sea",
    "East_China": "East China Sea",
    "South_China": "South China Sea",
}

_FAMILIES = {
    "serif": "DejaVu Serif",
}

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": [_FAMILIES["serif"]],
    "font.size": 8.0,
    "axes.linewidth": 0.5,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "savefig.dpi": 200,
})

_T = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
_Ti = Transformer.from_crs(TARGET_CRS, "EPSG:4326", always_xy=True)

# cached NE layers (module-level memo)
_ne_cache = {}


def load_countries():
    if "countries" not in _ne_cache:
        g = gpd.read_file(NE_ADMIN0).to_crs(TARGET_CRS)
        _ne_cache["countries"] = g
    return _ne_cache["countries"]


def load_china_provinces():
    if "provinces" not in _ne_cache:
        g = gpd.read_file(NE_ADMIN1)
        g = g[g["admin"] == "China"].to_crs(TARGET_CRS)
        _ne_cache["provinces"] = g
    return _ne_cache["provinces"]


def load_products():
    """Cached 100 m product rasters: returns (arrs, H, W, db_km) with
    db_km = (x0, y0, x1, y1) in km; row 0 = y0 (top)."""
    d = np.load(os.path.join(CACHE, "products_100m_epsg3410.npz"))
    arrs = {k: d[k].astype(bool) for k in ("cmsa", "cmssm", "geo")}
    db = [float(v) / 1000.0 for v in d["db"]]
    # db stored as (minx, miny, maxx, maxy); rows start at top (maxy)
    return arrs, int(d["H"]), int(d["W"]), db


def load_region_masks():
    m = np.load(os.path.join(CACHE, "marine_masks_100m.npz"))
    return {g: m[f"{g}__mask"].astype(bool)
            for g in ("Bohai_Yellow", "East_China", "South_China")}


def px_to_km(xs, ys, db):
    """Grid indices -> EPSG:3410 km coordinates (rows from top)."""
    x = db[0] + (np.asarray(xs) + 0.5) * RES_M / 1000.0
    y = db[3] - (np.asarray(ys) + 0.5) * RES_M / 1000.0
    return x, y


def grid_extent_km(db):
    """imshow extent=(left,right,bottom,top) in km for row-0-at-top rasters."""
    return (db[0], db[2], db[1], db[3])


# --------------------------- basemap drawing -------------------------------

def _prefilter_clip(gdf, extent_km, cache_key=None):
    """Spatial-index prefilter + memoized exact clip (fast repeated use)."""
    from shapely.geometry import box as shp_box
    x0, x1, y0, y1 = extent_km
    key = (cache_key, round(x0, -1), round(x1, -1), round(y0, -1),
           round(y1, -1))
    if key in _ne_cache:
        return _ne_cache[key]
    sub = gdf.cx[x0 * 1000:x1 * 1000, y0 * 1000:y1 * 1000]
    from shapely.geometry import box as _box
    clipped = gpd.clip(sub, _box(x0 * 1000, y0 * 1000, x1 * 1000,
                                 y1 * 1000)) if len(sub) else sub
    if cache_key is not None:
        _ne_cache[key] = clipped
    return clipped


def _as_km(gdf):
    """Geometries in metres -> km (all panel coordinates are km)."""
    g = gdf.copy()
    g["geometry"] = gdf.geometry.scale(xfact=1e-3, yfact=1e-3, origin=(0, 0))
    return g


def add_basemap(ax, extent_km, provinces=True, intl=True):
    """Fill land/sea + coastline + province and international boundaries.

    extent_km = (x0, x1, y0, y1) in EPSG:3410 km.
    """
    x0, x1, y0, y1 = extent_km

    ax.set_facecolor(PAL["sea"])

    land = _as_km(_prefilter_clip(load_countries(), extent_km,
                                  cache_key="land"))
    land.plot(ax=ax, facecolor=PAL["land"], edgecolor=PAL["coast"],
              linewidth=0.45, zorder=2, rasterized=True)

    if intl:
        # international borders = shared boundaries between admin0 units
        land.plot(ax=ax, facecolor="none", edgecolor=PAL["intl"],
                  linewidth=0.35, linestyle=(0, (4, 2)), zorder=2.5,
                  rasterized=True)

    if provinces:
        prov = _as_km(_prefilter_clip(load_china_provinces(), extent_km,
                                       cache_key="prov"))
        prov.boundary.plot(ax=ax, color=PAL["province"], linewidth=0.30,
                           zorder=3, rasterized=True)

    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")


def add_graticule(ax, extent_km, step_deg=5, label_x=True, label_y=True):
    """CEA graticule: meridians are vertical, parallels horizontal.
    Ticks labeled in °E / °N."""
    x0, x1, y0, y1 = extent_km
    lon_c, lat_lo = _Ti.transform(x0 * 1000, y0 * 1000)
    lon_c2, lat_hi = _Ti.transform(x1 * 1000, y1 * 1000)
    lat_lo, lat_hi = min(lat_lo, lat_hi), max(lat_lo, lat_hi)

    lon0 = int(np.ceil(lon_c / step_deg) * step_deg)
    lons = [l for l in range(lon0, 181, step_deg)
            if x0 < _T.transform(l, 30)[0] / 1000 < x1]
    lat0 = int(np.ceil(lat_lo / step_deg) * step_deg)
    lats = [t for t in range(lat0, 61, step_deg)
            if y0 < _T.transform(120, t)[1] / 1000 < y1]

    for l in lons:
        x = _T.transform(l, 30)[0] / 1000
        ax.plot([x, x], [y0, y1], color="#FFFFFF", lw=0.4, alpha=0.9,
                zorder=1.6)
        ax.plot([x, x], [y0, y1], color="#8C8C8C", lw=0.25, alpha=0.7,
                zorder=1.7)
    for t in lats:
        y = _T.transform(120, t)[1] / 1000
        ax.plot([x0, x1], [y, y], color="#FFFFFF", lw=0.4, alpha=0.9,
                zorder=1.6)
        ax.plot([x0, x1], [y, y], color="#8C8C8C", lw=0.25, alpha=0.7,
                zorder=1.7)

    if label_x:
        ax.set_xticks([_T.transform(l, 30)[0] / 1000 for l in lons])
        ax.set_xticklabels([f"{abs(l)}°{'E' if l >= 0 else 'W'}" for l in lons])
    else:
        ax.set_xticks([])
    if label_y:
        ax.set_yticks([_T.transform(120, t)[1] / 1000 for t in lats])
        ax.set_yticklabels([f"{abs(t)}°{'N' if t >= 0 else 'S'}" for t in lats])
    else:
        ax.set_yticks([])
    ax.tick_params(labelsize=6.5)
    return lons, lats


def add_scalebar(ax, length_km, x_frac=0.05, y_frac=0.06, fontsize=7):
    """Geodesically honest scale bar drawn at the panel's centre latitude."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    lon_c, lat_c = _Ti.transform((x0 + x1) / 2 * 1000, (y0 + y1) / 2 * 1000)
    dlon_deg = (length_km / (111.320 * max(np.cos(np.deg2rad(lat_c)),
                                           1e-6)) / 2)
    px0 = _T.transform(lon_c - dlon_deg, lat_c)[0] / 1000
    px1 = _T.transform(lon_c + dlon_deg, lat_c)[0] / 1000
    py = y0 + (y1 - y0) * y_frac
    ax.plot([px0, px1], [py, py], color="#1A1A1A", lw=1.6,
            solid_capstyle="butt", zorder=8)
    for px in (px0, px1):
        ax.plot([px, px], [py - (y1 - y0) * 0.004, py + (y1 - y0) * 0.004],
                color="#1A1A1A", lw=1.2, zorder=8)
    ax.text((px0 + px1) / 2, py + (y1 - y0) * 0.010,
            f"{length_km:g} km", ha="center", va="bottom", fontsize=fontsize,
            color="#1A1A1A", zorder=8)


def add_north_arrow(ax, x_frac=0.955, y_frac=0.93, size=7):
    """North arrow — valid for north-up CEA projection."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x0 + (x1 - x0) * x_frac
    y = y0 + (y1 - y0) * y_frac
    dy = (y1 - y0) * 0.035
    ax.annotate("", xy=(x, y), xytext=(x, y - dy),
                arrowprops=dict(arrowstyle="-|>", color="#1A1A1A", lw=1.1),
                zorder=8)
    ax.text(x, y + dy * 0.35, "N", ha="center", va="bottom", fontsize=size,
            color="#1A1A1A", fontweight="bold", zorder=8)


def add_locator_inset(ax, extent_km, width="28%", height="30%",
                      loc="lower left", borderpad=0.6,
                      context_bounds=(72, 145, 14, 54), facecolor="white"):
    """Small overview map (lon/lat bounds) showing the panel extent."""
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes
    ins = inset_axes(ax, width=width, height=height, loc=loc,
                     borderpad=borderpad,
                     bbox_to_anchor=(0, 0, 1, 1), bbox_transform=ax.transAxes)
    lon0, lon1, lat0, lat1 = context_bounds
    cx0, cy0 = _T.transform(lon0, lat0)
    cx1, cy1 = _T.transform(lon1, lat1)
    ins.set_facecolor(facecolor)
    add_basemap(ins, (cx0 / 1000, cx1 / 1000, cy0 / 1000, cy1 / 1000),
                provinces=False, intl=False)
    ins.set_xticks([]); ins.set_yticks([])
    for s in ins.spines.values():
        s.set_linewidth(0.6); s.set_color("#666666")
    x0, x1, y0, y1 = extent_km
    ins.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0,
                            fill=False, edgecolor=PAL["zoombox"],
                            linewidth=0.9, zorder=9))
    return ins


def overlay_mask(ax, mask, db, color, alpha=1.0, zorder=5, block=None,
                 extent_km=None):
    """Overlay a boolean raster (row 0 at top) as a colored mask.

    extent_km (x0, x1, y0, y1) crops the raster to the panel before any
    downsampling (huge saving on zoomed panels). block: optional int
    downsample factor (block-max, keeps sparse positives).
    """
    m = mask
    res_km = RES_M / 1000.0
    if extent_km is not None:
        ex0, ex1, ey0, ey1 = extent_km
        c0 = max(0, int((ex0 - db[0]) / res_km))
        c1 = min(m.shape[1], int(np.ceil((ex1 - db[0]) / res_km)))
        r0 = max(0, int((db[3] - ey1) / res_km))
        r1 = min(m.shape[0], int(np.ceil((db[3] - ey0) / res_km)))
        if r1 <= r0 or c1 <= c0:
            return None
        m = m[r0:r1, c0:c1]
        sub_db = (db[0] + c0 * res_km, db[3] - r1 * res_km,
                  db[0] + c1 * res_km, db[3] - r0 * res_km)
    else:
        sub_db = db
    if block and block > 1:
        h, w = m.shape
        h2, w2 = (h // block) * block, (w // block) * block
        mm = m[:h2, :w2].reshape(h2 // block, block, w2 // block, block)
        m = mm.max(axis=(1, 3))
    from matplotlib.colors import to_rgba
    r, g, b, a = to_rgba(color, alpha)
    rgba = np.zeros((*m.shape, 4), dtype=np.uint8)
    rgba[..., 0][m] = int(r * 255); rgba[..., 1][m] = int(g * 255)
    rgba[..., 2][m] = int(b * 255); rgba[..., 3][m] = int(a * 255)
    im = ax.imshow(rgba, origin="upper", interpolation="nearest",
                   extent=grid_extent_km(sub_db), zorder=zorder)
    im.set_rasterized(True)
    return im


def clean_axes(ax):
    for s in ax.spines.values():
        s.set_linewidth(0.5)
        s.set_color("#555555")


def attribution_note(fig, text, y=0.005, fontsize=6.2):
    fig.text(0.01, y, text, fontsize=fontsize, color="#555555",
             ha="left", va="bottom", style="italic")


NE_NOTE = ("Base map: Natural Earth 1:10m (public domain, v5.1.1). "
           "Projection: EPSG:3410 equal-area.")
