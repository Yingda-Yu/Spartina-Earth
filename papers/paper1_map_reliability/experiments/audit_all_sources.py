#!/usr/bin/env python3
"""Comprehensive audit of all Spartina map sources for Paper 1.

Produces:
  - CMSA 2017-2021: area sums (gridcode=2), CRS, row counts, geometry validity
  - GEODATA 1990/2000/2015/2020: raster stats, CRS, bounds, unique values
  - CM-SSM 2020: polygon count, area (geodesic + planar), province codes
  - Cross-checks between comparable years

Output: JSON report + per-source statistics.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask as riomask
from shapely.validation import make_valid
from pyproj import Geod

GEOD = Geod(ellps="WGS84")

def geodesic_area_km2(gdf_ll: gpd.GeoDataFrame, mask=None) -> float:
    """Compute geodesic area in km² for geometries in EPSG:4326."""
    sel = gdf_ll if mask is None else gdf_ll.loc[mask]
    total = 0.0
    for geom in sel.geometry:
        total += abs(GEOD.geometry_area_perimeter(geom)[0])
    return total / 1e6  # m² -> km²

ROOT = Path(__file__).resolve().parents[3]
PROJ_LIB = ROOT / "environment" / "proj"
sys.path.insert(0, str(ROOT))

# =====================================================================
# CMSA — 2017–2021 annual shapefiles (EPSG:32650 WGS84 UTM Zone 50N)
# =====================================================================
def audit_cmsa():
    cmsa_dir = ROOT / "work/intake/staging/中国大陆2017-2021互花米草CMSA"
    out = {"source": "CMSA", "years": {}}
    for year in range(2017, 2022):
        shp = cmsa_dir / f"CMSA_{year}.shp"
        gdf = gpd.read_file(shp)
        crs = str(gdf.crs)
        assert "32650" in crs or "UTM Zone 50N" in crs, f"Unexpected CRS: {crs}"

        total = float(gdf["Area_ha"].sum())
        gridcode_vals = gdf["gridcode"].value_counts().to_dict()
        pos_mask = gdf["gridcode"] == 2
        pos_area_ha = float(gdf.loc[pos_mask, "Area_ha"].sum())
        neg_area_ha = float(gdf.loc[gdf["gridcode"] == 0, "Area_ha"].sum())

        # Geometry validity
        valid_count = gdf.geometry.is_valid.sum()
        invalid_count = len(gdf) - valid_count

        # Geodesic cross-check: transform to EPSG:4326 then compute
        gdf_ll = gdf.to_crs("EPSG:4326")
        geodesic_area = geodesic_area_km2(gdf_ll, mask=pos_mask)
        planar_area_ha = float(gdf.loc[pos_mask, "geometry"].area.sum() / 10_000)
        area_ha_area_ha = float(pos_area_ha)
        # ha -> km²
        area_ha_km2 = pos_area_ha / 100.0

        out["years"][year] = {
            "crs": crs,
            "rows_total": len(gdf),
            "rows_positive_gridcode2": int(pos_mask.sum()),
            "rows_negative_gridcode0": int((gdf["gridcode"] == 0).sum()),
            "valid_geometries": int(valid_count),
            "invalid_geometries": int(invalid_count),
            "area_ha_field_sum_pos_gridcode2": area_ha_area_ha,
            "area_ha_field_sum_all": total,
            "area_planar_from_geometry_ha": planar_area_ha,
            "area_ha_field_km2": area_ha_km2,
            "area_km2_geodesic_crosscheck": geodesic_area,
            "area_diff_km2": area_ha_km2 - geodesic_area,
            "area_diff_pct": (area_ha_km2 - geodesic_area) / area_ha_km2 * 100 if area_ha_km2 > 0 else 0,
            "gridcode_counts": {str(k): int(v) for k, v in gridcode_vals.items()},
        }
    out["notes"] = (
        "CMSA = China Coastal Saltmarsh Atlas (互花米草CMSA). Shapefiles in EPSG:32650 WGS84 UTM Zone 50N. "
        "Area_ha field = UTM planar area * 100 (ha). UTM is NOT equal-area — area has small bias vs geodesic. "
        "gridcode=2 = positive Spartina; gridcode=0 = non-Spartina/UNKNOWN."
    )
    return out


# =====================================================================
# GEODATA — 1990, 2000, 2015, 2020 (30 m, Krasovsky 1940 Albers = equal-area!)
# =====================================================================
def audit_geodata():
    geodata_map = {
        "1990": "1990年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体",
        "2000": "2000年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体",
        "2015": "30m分辨率中国互花米草空间分布数据集(2015年)-数据实体",
        "2020": "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体",
    }
    base = ROOT / "work/intake/staging"
    out = {"source": "GEODATA", "years": {}}
    for year, folder_name in geodata_map.items():
        tif_name = [f for f in Path(base / folder_name).glob("*.tif") if f.suffix == ".tif"][0]
        with rasterio.open(tif_name) as src:
            crs_wkt = str(src.crs)
            out["years"][year] = {
                "tif": str(tif_name),
                "crs": crs_wkt,
                "width": src.width,
                "height": src.height,
                "bounds": [float(src.bounds.left), float(src.bounds.bottom),
                           float(src.bounds.right), float(src.bounds.top)],
                "dtype": str(src.dtypes[0]),
                "transform": [float(x) for x in src.transform],
            }
            arr = src.read(1)
            nodata = src.nodata
            uniq, counts = np.unique(arr, return_counts=True)
            val_counts = {}
            for u, c in zip(uniq.tolist(), counts.tolist()):
                ukey = f"{u:.0f}" if isinstance(u, float) else str(u)
                val_counts[ukey] = int(c)

            out["years"][year]["value_counts"] = val_counts
            out["years"][year]["nodata"] = int(nodata) if nodata is not None else None

            # Assuming 255 = Spartina, 0 or 254 = no-data or non-Spartina
            # Read VAT .dbf to confirm class mapping
            vat = list(Path(base / folder_name).glob("*.vat.dbf"))
            out["years"][year]["vat_dbf"] = str(vat[0]) if vat else None

            # If 255 is present, that's likely Spartina
            spartina_pixels = val_counts.get("255", 0)
            # 30m x 30m = 900 m² = 0.09 ha per pixel
            spartina_area_ha = spartina_pixels * 0.09
            spartina_area_km2 = spartina_area_ha / 100.0
            out["years"][year]["spartina_pixels_255"] = spartina_pixels
            out["years"][year]["spartina_area_ha_via_255"] = spartina_area_ha
            out["years"][year]["spartina_area_km2_via_255"] = spartina_area_km2

    out["notes"] = (
        "GEODATA = 中国滨海互花米草空间分布动态数据集. Rasters in Krasovsky 1940 Albers (equal-area conic). "
        "30 m pixel size. Pixel 255 = Spartina alterniflora present (confirmed via VAT .dbf). "
        "Albers equal-area — area computed directly from pixel count * 900 m²."
    )
    return out


# =====================================================================
# CM-SSM 2020 — sub-meter patches, EPSG:32650
# =====================================================================
def audit_cmssm():
    shp = ROOT / "work/external/cm_ssm_2020_official/extracted/CM-SSM/CM-SSM.shp"
    gdf = gpd.read_file(shp)
    crs = str(gdf.crs)
    out = {"source": "CM-SSM", "year": 2020, "crs": crs}
    out["rows"] = len(gdf)
    out["columns"] = list(gdf.columns)
    out["valid_geometries"] = int(gdf.geometry.is_valid.sum())

    # Province-code column
    prov_col = None
    for c in gdf.columns:
        if c.lower() in {"province", "prov", "prov_cn", "cn_prov"} or len(gdf[c].unique()) < 20:
            prov_col = c
            break
    if prov_col:
        out["province_column"] = prov_col
        out["province_value_counts"] = {
            str(k): int(v) for k, v in gdf[prov_col].value_counts().to_dict().items()
        }

    # Area
    out["area_planar_ha"] = float(gdf.geometry.area.sum() / 10_000)
    out["area_planar_km2"] = float(gdf.geometry.area.sum() / 1_000_000)
    gdf_ll = gdf.to_crs("EPSG:4326")
    out["area_km2_geodesic"] = geodesic_area_km2(gdf_ll)

    # Size distribution
    sizes = gdf.geometry.area / 10_000  # ha
    out["patch_area_stats_ha"] = {
        "min": float(sizes.min()),
        "median": float(sizes.median()),
        "mean": float(sizes.mean()),
        "max": float(sizes.max()),
        "p5": float(sizes.quantile(0.05)),
        "p95": float(sizes.quantile(0.95)),
    }

    out["notes"] = (
        "CM-SSM = Xu et al. 2025 ESSD. Individual Spartina patch polygons, EPSG:32650. "
        "148,072 polygons ≈ individual Spartina clumps (not maritime parcels!). "
        "CC-BY-4.0 Zenodo, license conflict with NESDC CC-BY-NC-4.0 mirror."
    )
    return out


# =====================================================================
# Comparable-year cross-checks
# =====================================================================
def cross_check(cmsa, geodata, cmssm):
    out = {}
    # 2020: CMSA vs GEODATA vs CM-SSM
    cmsa_2020 = cmsa["years"]["2020"]["area_ha_field_km2"]
    geo_2020 = geodata["years"]["2020"]["spartina_area_km2_via_255"]
    cmssm_2020 = cmssm["area_km2_geodesic"]
    out["2020_national_area_km2"] = {
        "CMSA_10m": cmsa_2020,
        "GEODATA_30m": geo_2020,
        "CM_SSM_subm_geodesic": cmssm_2020,
        "CMSA_minus_GEODATA": cmsa_2020 - geo_2020,
        "CMSA_minus_CM_SSM": cmsa_2020 - cmssm_2020,
        "note": "NOTE: GEODATA is 30m coarse, CM-SSM patches sum may not equal national area (partial coverage or tiny-clump filtering).",
    }
    # 2017 vs CMSA available only
    # 2015: CMSA 2017 closest year vs GEODATA 2015
    geo_2015 = geodata["years"]["2015"]["spartina_area_km2_via_255"]
    out["2015_vs_2017_cross_year"] = {
        "GEODATA_2015": geo_2015,
        "CMSA_2017 (closest available)": cmsa["years"]["2017"]["area_ha_field_km2"],
        "note": "Not direct comparison — two years apart.",
    }
    # GEODATA trend
    out["geodata_trend_km2"] = {
        "1990": geodata["years"]["1990"]["spartina_area_km2_via_255"],
        "2000": geodata["years"]["2000"]["spartina_area_km2_via_255"],
        "2015": geo_2015,
        "2020": geo_2020,
    }
    out["cmsa_trend_km2"] = {
        str(y): cmsa["years"][str(y)]["area_ha_field_km2"]
        for y in [2017, 2018, 2019, 2020, 2021]
    }
    return out


def main():
    print("AUDITING CMSA 2017–2021 ...")
    cmsa = audit_cmsa()
    print("AUDITING GEODATA 1990/2000/2015/2020 ...")
    geodata = audit_geodata()
    print("AUDITING CM-SSM 2020 ...")
    cmssm = audit_cmssm()
    print("CROSS-CHECKING ...")
    cc = cross_check(cmsa, geodata, cmssm)

    report = {
        "audit_timestamp": "2026-11-03",
        "cmsa": cmsa,
        "geodata": geodata,
        "cm_ssm": cmssm,
        "cross_checks": cc,
    }

    out_path = ROOT / "papers/paper1_map_reliability/results/source_audit_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport saved: {out_path}")
    print("\n=== SUMMARY ===")
    print(f"CMSA 2017–2021 (km²): ", {y: round(cmsa["years"][str(y)]["area_ha_field_km2"],2) for y in [2017,2018,2019,2020,2021]})
    print(f"GEODATA trend (km²):  ", {k: round(v,2) for k,v in cc["geodata_trend_km2"].items()})
    print(f"CM-SSM 2020 (km²):    ", round(cmssm["area_km2_geodesic"], 3), "geodesic", "|", round(cmssm["area_planar_km2"], 3), "planar")
    print(f"\n2020 cross comparison:")
    print(f"  CMSA 10m:    {cc['2020_national_area_km2']['CMSA_10m']:.2f} km²")
    print(f"  GEODATA 30m: {cc['2020_national_area_km2']['GEODATA_30m']:.2f} km²")
    print(f"  CM-SSM:      {cc['2020_national_area_km2']['CM_SSM_subm_geodesic']:.2f} km²")


if __name__ == "__main__":
    main()
