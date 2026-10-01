#!/usr/bin/env python3
"""Intersect every legacy label / stack asset with the three bay ROIs.

M2.1a (Issue #7) label inventory, read-only over ``old datasets/`` (which
is permanently read-only and Git-ignored). Overlap is computed, never
guessed:

* vector assets -> bbox-filtered read, reprojection, real intersection
  feature counts and areas in EPSG:32651;
* raster LABEL assets -> windowed reads + rasterized ROI mask -> positive
  pixel counts and areas (observed pixel values are recorded);
* raster STACK / composite assets -> footprint-only overlap (UNLABELED).

Nothing here promotes anything to GOLD; that process is owned by Issue
#11. Outputs: datasets/manifests/zhejiang_legacy_label_inventory_v0.{csv,parquet}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyproj  # noqa: E402
import rasterio  # noqa: E402
from rasterio.mask import raster_geometry_mask  # noqa: E402
from shapely.geometry import box, shape  # noqa: E402
from shapely.ops import transform as shp_transform  # noqa: E402

from spartina.data.gee.selection import canonical_fingerprint  # noqa: E402
from spartina.data.zhejiang.contracts import (  # noqa: E402
    LABEL_INVENTORY_COLUMNS,
    LABEL_SILVER,
    LABEL_UNLABELED,
    LABEL_WEAK,
    USE_DESCRIPTIVE_ONLY,
    USE_DIAGNOSTIC_ONLY,
    USE_VALIDATION_REFERENCE,
)

OLD = REPO_ROOT / "old datasets"
TO_32651 = pyproj.Transformer.from_crs(4326, 32651, always_xy=True).transform
TO_4326 = pyproj.Transformer.from_crs(32651, 4326, always_xy=True).transform

# Static audit metadata from M0/M1.1 reviews (docs/audit/LABEL_*.md).
ASSETS: list[dict] = [
    {
        "asset_id": "L1-china2015-raster30m",
        "asset_name": "30m中国互花米草空间分布数据集(2015)",
        "asset_kind": "RASTER_LABEL",
        "relpath": "30mSpartinaChina/30m分辨率中国互花米草空间分布数据集(2015年)-数据实体/30m中国互花米草空间分布数据集(2015年)-数据实体.tif",
        "nominal_year": 2015,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "中国科学院东北地理与农业生态研究所 王宗明团队（geodata.cn）",
        "method": "全国30m遥感分类栅格；DOI 10.12041/geodata.65372070926827.ver1.db",
        "label_tier": LABEL_SILVER,
        "license": "RESTRICTED_REDISTRIBUTION (geodata.cn; OA约92%)",
        "redistributable": "NO_WITHOUT_PERMISSION",
        "known_problems": "再分发受限；总体精度约92%(产品页)；本地未复算",
        "allowed_use": USE_VALIDATION_REFERENCE,
        "allowed_use_reason": "唯一SILVER；仅作验证参考，不进入训练分发",
        "notes": "全国正样本608,287像元(547.46 km2)为M0审计值",
    },
    {
        "asset_id": "L2-cmssm2020-polygons",
        "asset_name": "CM-SSM 2020 全国互花米草分布多边形",
        "asset_kind": "VECTOR_LABEL",
        "relpath": "30mSpartinaChina/2020/CM-SSM/CM-SSM.shp",
        "nominal_year": 2020,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "UNKNOWN（发表链接未确认）",
        "method": "全国多边形产品(Id/name/area字段)；148,072要素",
        "label_tier": LABEL_WEAK,
        "license": "UNKNOWN",
        "redistributable": "UNKNOWN",
        "known_problems": ("2,402自相交；100,455要素<100 m2；全国593.71 km2；"
                           "出处未确认"),
        "allowed_use": USE_DIAGNOSTIC_ONLY,
        "allowed_use_reason": "几何/出处缺陷，仅诊断，不训练不评估",
        "notes": "M0审计：浙江省要素数39,764",
    },
    {
        "asset_id": "L3-hangzhou-mask-2015",
        "asset_name": "c201511839DTSP_2.tif 杭州湾局部分类掩膜",
        "asset_kind": "RASTER_LABEL",
        "relpath": "Spartina/HangZhouBay/c201511839DTSP_2.tif",
        "nominal_year": 2015,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "UNKNOWN（文件名来源机构未解析）",
        "method": "约30m单波段二值掩膜，EPSG:32651",
        "label_tier": LABEL_WEAK,
        "license": "UNKNOWN",
        "redistributable": "UNKNOWN",
        "known_problems": ("来源未解析；与全国产品Jaccard 0.497；"
                           "SAI阈值极性方向一致但未证明"),
        "allowed_use": USE_DIAGNOSTIC_ONLY,
        "allowed_use_reason": "来源与阈值均未证实，仅诊断",
        "notes": "M0：15,600正像元(约14.0 km2)",
    },
    {
        "asset_id": "L4-cmsa-polygons-2019",
        "asset_name": "CMSA_2019 局地多边形（实际位置：乐清湾湾顶片区）",
        "asset_kind": "VECTOR_LABEL",
        "relpath": "spartinatest/CMSA_2019.shp",
        "nominal_year": 2019,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "UNKNOWN",
        "method": "78个多边形，EPSG:4326，gridcode=2",
        "label_tier": LABEL_WEAK,
        "license": "UNKNOWN",
        "redistributable": "UNKNOWN",
        "known_problems": "出处/方法未确认；M0曾误记为福建片区，实际bbox在浙东",
        "allowed_use": USE_DIAGNOSTIC_ONLY,
        "allowed_use_reason": "出处不明WEAK标签，仅诊断",
        "notes": "bbox 121.150-121.219E,28.269-28.376N（本次实测）",
    },
    {
        "asset_id": "L5-cmsa-polygons-2020",
        "asset_name": "CMSA_2020 局地多边形（实际位置：乐清湾湾顶片区）",
        "asset_kind": "VECTOR_LABEL",
        "relpath": "spartinatest/CMSA_2020.shp",
        "nominal_year": 2020,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "UNKNOWN",
        "method": "191个多边形，EPSG:4326，gridcode=2",
        "label_tier": LABEL_WEAK,
        "license": "UNKNOWN",
        "redistributable": "UNKNOWN",
        "known_problems": "出处/方法未确认；M0曾误记为福建片区，实际bbox在浙东",
        "allowed_use": USE_DIAGNOSTIC_ONLY,
        "allowed_use_reason": "出处不明WEAK标签，仅诊断",
        "notes": "bbox 121.151-121.219E,28.297-28.373N（本次实测）",
    },
    {
        "asset_id": "L6-cmsa-polygons-2021",
        "asset_name": "CMSA_2021 局地多边形（实际位置：乐清湾湾顶片区）",
        "asset_kind": "VECTOR_LABEL",
        "relpath": "spartinatest/CMSA_2021.shp",
        "nominal_year": 2021,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "UNKNOWN",
        "method": "105个多边形，EPSG:4326，gridcode=2",
        "label_tier": LABEL_WEAK,
        "license": "UNKNOWN",
        "redistributable": "UNKNOWN",
        "known_problems": "出处/方法未确认；M0曾误记为福建片区，实际bbox在浙东",
        "allowed_use": USE_DIAGNOSTIC_ONLY,
        "allowed_use_reason": "出处不明WEAK标签，仅诊断",
        "notes": "bbox 121.150-121.220E,28.269-28.379N（本次实测）",
    },
    {
        "asset_id": "U1-hzb-l8allbands-2015",
        "asset_name": "HangZhouBay L8_AllBands_2015 合成",
        "asset_kind": "RASTER_STACK_FOOTPRINT",
        "relpath": "Spartina/HangZhouBay/L8_AllBands_2015.tif",
        "nominal_year": 2015,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "legacy 工作目录",
        "method": "7波段L8合成，约30m，EPSG:4326",
        "label_tier": LABEL_UNLABELED,
        "license": "UNKNOWN_DERIVED_FROM_USGS_LANDSAT",
        "redistributable": "UNKNOWN",
        "known_problems": "合成日期/云掩膜过程UNKNOWN",
        "allowed_use": USE_DESCRIPTIVE_ONLY,
        "allowed_use_reason": "无标签，仅记录覆盖",
        "notes": "",
    },
    {
        "asset_id": "U2-hzb-ndvi-2015",
        "asset_name": "HangZhouBay NDVI_2015",
        "asset_kind": "RASTER_STACK_FOOTPRINT",
        "relpath": "Spartina/HangZhouBay/NDVI_2015.tif",
        "nominal_year": 2015,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "legacy 工作目录",
        "method": "单波段NDVI指数，约30m，EPSG:4326",
        "label_tier": LABEL_UNLABELED,
        "license": "UNKNOWN_DERIVED_FROM_USGS_LANDSAT",
        "redistributable": "UNKNOWN",
        "known_problems": "指数定义/合成过程未复核",
        "allowed_use": USE_DESCRIPTIVE_ONLY,
        "allowed_use_reason": "指数层非标签，仅记录覆盖",
        "notes": "",
    },
    {
        "asset_id": "U3-hzb-sai-2015",
        "asset_name": "HangZhouBay SAI_2015（互花米草指数）",
        "asset_kind": "RASTER_STACK_FOOTPRINT",
        "relpath": "Spartina/HangZhouBay/SAI_2015.tif",
        "nominal_year": 2015,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "legacy 工作目录",
        "method": "单波段SAI指数，约30m，EPSG:4326",
        "label_tier": LABEL_UNLABELED,
        "license": "UNKNOWN_DERIVED_FROM_USGS_LANDSAT",
        "redistributable": "UNKNOWN",
        "known_problems": "指数公式/阈值未复核；与L3掩膜关系未证明",
        "allowed_use": USE_DESCRIPTIVE_ONLY,
        "allowed_use_reason": "指数层非标签，仅记录覆盖",
        "notes": "",
    },
    {
        "asset_id": "U4-hzb-s1vv-2015",
        "asset_name": "HangZhouBay S1_VV_2015",
        "asset_kind": "RASTER_STACK_FOOTPRINT",
        "relpath": "Spartina/HangZhouBay/S1_VV_2015.tif",
        "nominal_year": 2015,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "legacy 工作目录",
        "method": "单极化SAR后向散射，约10m，EPSG:4326",
        "label_tier": LABEL_UNLABELED,
        "license": "UNKNOWN_DERIVED_FROM_COPERNICUS_S1",
        "redistributable": "UNKNOWN",
        "known_problems": "轨道/预处理/日期UNKNOWN",
        "allowed_use": USE_DESCRIPTIVE_ONLY,
        "allowed_use_reason": "无标签，仅记录覆盖",
        "notes": "",
    },
    {
        "asset_id": "U5-hzb-s1vh-2015",
        "asset_name": "HangZhouBay S1_VH_2015",
        "asset_kind": "RASTER_STACK_FOOTPRINT",
        "relpath": "Spartina/HangZhouBay/S1_VH_2015.tif",
        "nominal_year": 2015,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "legacy 工作目录",
        "method": "单极化SAR后向散射，约10m，EPSG:4326",
        "label_tier": LABEL_UNLABELED,
        "license": "UNKNOWN_DERIVED_FROM_COPERNICUS_S1",
        "redistributable": "UNKNOWN",
        "known_problems": "轨道/预处理/日期UNKNOWN",
        "allowed_use": USE_DESCRIPTIVE_ONLY,
        "allowed_use_reason": "无标签，仅记录覆盖",
        "notes": "",
    },
    {
        "asset_id": "U6-zj-featurestack-A",
        "asset_name": "浙江11波段特征堆栈 tile-A(28.03-30.72N)",
        "asset_kind": "RASTER_STACK_FOOTPRINT",
        "relpath": "Spartina/zhejiang/Spartina_2015-0000000000-0000000000.tif",
        "nominal_year": 2015,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "legacy 工作目录",
        "method": "11波段特征堆栈，约30m，EPSG:4326",
        "label_tier": LABEL_UNLABELED,
        "license": "UNKNOWN",
        "redistributable": "UNKNOWN",
        "known_problems": "668MB；波段定义/特征构造/标签含义UNKNOWN",
        "allowed_use": USE_DESCRIPTIVE_ONLY,
        "allowed_use_reason": "特征堆栈非标签，仅记录覆盖",
        "notes": "文件名含Spartina但不视为标签证据",
    },
    {
        "asset_id": "U7-zj-featurestack-B",
        "asset_name": "浙江11波段特征堆栈 tile-B(27.46-28.03N)",
        "asset_kind": "RASTER_STACK_FOOTPRINT",
        "relpath": "Spartina/zhejiang/Spartina_2015-0000009984-0000000000.tif",
        "nominal_year": 2015,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "legacy 工作目录",
        "method": "11波段特征堆栈，约30m，EPSG:4326",
        "label_tier": LABEL_UNLABELED,
        "license": "UNKNOWN",
        "redistributable": "UNKNOWN",
        "known_problems": "53MB；波段定义/特征构造/标签含义UNKNOWN",
        "allowed_use": USE_DESCRIPTIVE_ONLY,
        "allowed_use_reason": "特征堆栈非标签，仅记录覆盖",
        "notes": "文件名含Spartina但不视为标签证据",
    },
]
# S2 composites 2019-2025 share metadata; generated below.
for yr in range(2019, 2026):
    ASSETS.append({
        "asset_id": f"U8-yqb-s2-composite-{yr}",
        "asset_name": f"spartinatest S2_{yr} 局地合成（乐清湾湾顶片区）",
        "asset_kind": "RASTER_STACK_FOOTPRINT",
        "relpath": f"spartinatest/S2_{yr}.tif",
        "nominal_year": yr,
        "verified_acquisition_date": "UNKNOWN",
        "source_owner": "legacy 工作目录",
        "method": "5波段S2合成，约10m，EPSG:4326",
        "label_tier": LABEL_UNLABELED,
        "license": "UNKNOWN_DERIVED_FROM_COPERNICUS_S2",
        "redistributable": "UNKNOWN",
        "known_problems": "合成日期/云过滤/波段顺序UNKNOWN",
        "allowed_use": USE_DESCRIPTIVE_ONLY,
        "allowed_use_reason": "合成影像非标签，仅记录覆盖",
        "notes": "bbox约121.160-121.220E,28.310-28.370N",
    })


def load_rois(geojson_path: Path) -> dict[str, object]:
    fc = json.loads(geojson_path.read_text(encoding="utf-8"))
    return {
        f["properties"]["roi_id"]: shape(f["geometry"])
        for f in fc["features"]
    }


def area_km2_32651(geom: object) -> float:
    return shp_transform(TO_32651, geom).area / 1_000_000.0


def vector_overlap(path: Path, roi_geoms: dict[str, object]) -> dict[str, tuple[int, float]]:
    result: dict[str, tuple[int, float]] = {}
    for roi_id, roi in roi_geoms.items():
        minx, miny, maxx, maxy = roi.bounds
        try:
            gdf = gpd.read_file(path, bbox=(minx, miny, maxx, maxy))
        except Exception as exc:  # noqa: BLE001 - record, never fabricate
            result[roi_id] = (-1, 0.0)
            print(f"  WARN read {path.name} / {roi_id}: {exc}", file=sys.stderr)
            continue
        if len(gdf) == 0:
            result[roi_id] = (0, 0.0)
            continue
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)
        hits = gdf.geometry[gdf.geometry.intersects(roi)]
        if len(hits) == 0:
            result[roi_id] = (0, 0.0)
            continue
        inter = hits.intersection(roi)
        area = sum(area_km2_32651(g) for g in inter if not g.is_empty)
        result[roi_id] = (int(len(hits)), round(area, 4))
    return result


def raster_label_overlap(
    path: Path, roi_geoms: dict[str, object]
) -> tuple[dict[str, tuple[int, float]], str]:
    counts: dict[str, tuple[int, float]] = {}
    values_seen: set = set()
    with rasterio.open(path) as ds:
        for roi_id, roi_geog in roi_geoms.items():
            # reproject ROI into raster CRS
            to_raster = pyproj.Transformer.from_crs(
                4326, ds.crs, always_xy=True
            ).transform
            roi_raster_crs = shp_transform(to_raster, roi_geog)
            try:
                mask, transform, window = raster_geometry_mask(
                    ds, [roi_raster_crs], crop=True, invert=True
                )
            except ValueError:
                counts[roi_id] = (0, 0.0)
                continue
            data = ds.read(1, window=window)
            nodata = ds.nodata
            valid = mask
            if nodata is not None:
                valid &= data != nodata
            positive = valid & (data > 0)
            n = int(np.count_nonzero(positive))
            px_area = abs(transform.a * transform.e)
            if ds.crs.is_geographic:
                # approximate metres at mean latitude of the window
                lat = float(np.mean([transform.f, transform.f +
                                     transform.e * window.height]))
                m_lat = 111_320.0
                m_lon = 111_320.0 * np.cos(np.radians(lat))
                px_area = abs(transform.a * transform.e) * m_lat * m_lon
            vals = np.unique(data[valid]) if valid.any() else np.array([])
            values_seen.update(float(v) for v in vals[:10])
            counts[roi_id] = (n, round(n * px_area / 1_000_000.0, 4))
    vals_text = ",".join(f"{v:g}" for v in sorted(values_seen)) or "NONE_IN_WINDOWS"
    return counts, vals_text


def raster_footprint_overlap(
    path: Path, roi_geoms: dict[str, object]
) -> dict[str, tuple[float, float, float]]:
    """Return (footprint_area_km2, intersection_km2, roi_covered_frac)."""
    out: dict[str, tuple[float, float, float]] = {}
    with rasterio.open(path) as ds:
        to_target = pyproj.Transformer.from_crs(
            ds.crs, 4326, always_xy=True
        ).transform
        fp_geog = shp_transform(to_target, box(*ds.bounds))
        for roi_id, roi in roi_geoms.items():
            inter = fp_geog.intersection(roi)
            inter_km2 = 0.0 if inter.is_empty else area_km2_32651(inter)
            roi_km2 = area_km2_32651(roi)
            out[roi_id] = (
                round(area_km2_32651(fp_geog), 4),
                round(inter_km2, 4),
                round(inter_km2 / roi_km2, 5) if roi_km2 else 0.0,
            )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rois",
                        default=str(REPO_ROOT / "datasets/rois/zhejiang_bays_v0.geojson"))
    parser.add_argument("--manifest-dir",
                        default=str(REPO_ROOT / "datasets/manifests"))
    args = parser.parse_args()

    roi_geoms = load_rois(Path(args.rois))
    rows: list[dict] = []
    for asset in ASSETS:
        path = OLD / asset["relpath"]
        row = {k: "" for k in LABEL_INVENTORY_COLUMNS}
        row["resolution_m"] = None
        row.update({
            "asset_id": asset["asset_id"],
            "asset_name": asset["asset_name"],
            "asset_kind": asset["asset_kind"],
            "nominal_year": asset["nominal_year"],
            "verified_acquisition_date": asset["verified_acquisition_date"],
            "source_owner": asset["source_owner"],
            "method": asset["method"],
            "resolution_m": 30 if "30m" in asset["method"] or "约30m" in asset["method"]
            else (10 if "约10m" in asset["method"] or "约10 m" in asset["method"] else None),
            "crs": "",
            "label_tier": asset["label_tier"],
            "license": asset["license"],
            "redistributable": asset["redistributable"],
            "known_problems": asset["known_problems"],
            "allowed_use": asset["allowed_use"],
            "allowed_use_reason": asset["allowed_use_reason"],
            "gold_candidate_issue": ("ISSUE_11_OWNS_GOLD_PROMOTION;"
                                     "NO_GOLD_CANDIDATE_AT_M21A"),
            "local_path": str(Path("old datasets") / asset["relpath"]),
            "notes": asset["notes"],
        })
        if not path.exists():
            for bid in roi_geoms:
                row[f"overlap_{bid.lower().replace('-', '_')}"] = "MISSING_FILE"
            row["overlap_units"] = "NONE"
            row["notes"] += " | FILE NOT FOUND"
            rows.append(row)
            continue

        if asset["asset_kind"] == "VECTOR_LABEL":
            ov = vector_overlap(path, roi_geoms)
            row["crs"] = gpd.read_file(path, rows=0).crs.to_string() \
                if gpd.read_file(path, rows=0).crs else "UNKNOWN"
            for bid, (n, area) in ov.items():
                row[f"overlap_{bid.lower().replace('-', '_')}"] = n
            row["overlap_units"] = "FEATURES"
            row["overlap_area_km2"] = round(
                sum(a for _, a in ov.values()), 4)
        elif asset["asset_kind"] == "RASTER_LABEL":
            with rasterio.open(path) as ds:
                row["crs"] = str(ds.crs)
                row["resolution_m"] = round(
                    abs(ds.transform.a) if ds.crs.is_projected else
                    abs(ds.transform.a) * 111_320.0, 2)
            ov, vals = raster_label_overlap(path, roi_geoms)
            for bid, (n, area) in ov.items():
                row[f"overlap_{bid.lower().replace('-', '_')}"] = n
            row["overlap_units"] = "POSITIVE_PIXELS"
            row["overlap_area_km2"] = round(
                sum(a for _, a in ov.values()), 4)
            row["notes"] = f"{asset['notes']} | observed_values={vals}".strip(" |")
        else:  # footprint-only composites
            with rasterio.open(path) as ds:
                row["crs"] = str(ds.crs)
                row["resolution_m"] = round(
                    abs(ds.transform.a) if ds.crs.is_projected else
                    abs(ds.transform.a) * 111_320.0, 2)
            ov = raster_footprint_overlap(path, roi_geoms)
            for bid, (_fp, inter, frac) in ov.items():
                row[f"overlap_{bid.lower().replace('-', '_')}"] = (
                    f"footprint_intersection_km2={inter};roi_covered_frac={frac}")
            row["overlap_units"] = "FOOTPRINT_KM2"
            row["overlap_area_km2"] = round(
                sum(inter for _, inter, _ in ov.values()), 4)

        row["geometry_kind"] = asset["asset_kind"].split("_")[0].title()
        row["logical_fingerprint"] = canonical_fingerprint(
            {k: row[k] for k in LABEL_INVENTORY_COLUMNS if k != "logical_fingerprint"}
        )
        rows.append(row)
        print(f"{asset['asset_id']:28s} "
              f"HZB={row['overlap_zj_hzb']} SMB={row['overlap_zj_smb']} "
              f"YQB={row['overlap_zj_yqb']} ({row['overlap_units']})")

    out_dir = Path(args.manifest_dir)
    csv_path = out_dir / "zhejiang_legacy_label_inventory_v0.csv"
    pq_path = out_dir / "zhejiang_legacy_label_inventory_v0.parquet"
    df = pd.DataFrame(rows, columns=list(LABEL_INVENTORY_COLUMNS))
    for col in ("overlap_zj_hzb", "overlap_zj_smb", "overlap_zj_yqb"):
        df[col] = df[col].astype(str)
    df.to_csv(csv_path, index=False)
    df.to_parquet(pq_path, index=False)
    print(f"wrote {csv_path.relative_to(REPO_ROOT)} and parquet ({len(df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
