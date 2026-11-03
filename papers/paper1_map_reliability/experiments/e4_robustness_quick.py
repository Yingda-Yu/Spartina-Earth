"""P4 robustness — quick test of processing sensitivities. Single run @ 100m."""
import os, numpy as np, csv, time
import geopandas as gpd, rasterio, pyproj
from rasterio import features as rio_features, transform as rio_transform
from rasterio.warp import reproject, Resampling

os.environ["PROJ_LIB"] = "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj"

ROOT = "/data/yingda/Spartina-Earth"
RES_M = 100
TARGET_CRS = "EPSG:3410"
DOM_BUF = 10_000
RESULTS = os.path.join(ROOT, "papers", "paper1_map_reliability", "results")


def run_test(res_m, shift, all_touched, buf, label):
    t = time.time()
    cmsa = gpd.read_file(os.path.join(ROOT, "work", "intake", "staging",
        "中国大陆2017-2021互花米草CMSA", "CMSA_2020.shp"))
    cmsa = cmsa[cmsa["gridcode"] == 2].copy().to_crs(TARGET_CRS)
    cmssm = gpd.read_file(os.path.join(ROOT, "work", "external",
        "cm_ssm_2020_official", "extracted", "CM-SSM", "CM-SSM.shp")).to_crs(TARGET_CRS)

    d = cmsa.total_bounds
    d = np.array([d[0]-buf, d[1]-buf, d[2]+buf, d[3]+buf])
    w = int((d[2]-d[0])/res_m); h = int((d[3]-d[1])/res_m)
    tfm = rio_transform.from_bounds(d[0]+shift, d[1], d[0]+shift+w*res_m, d[1]+h*res_m, w, h)

    shapes_a = [(g,1) for g in cmsa.geometry if g is not None and not g.is_empty]
    shapes_b = [(g,1) for g in cmssm.geometry if g is not None and not g.is_empty]
    a = rio_features.rasterize(shapes_a, out_shape=(h,w), transform=tfm, fill=0, dtype="uint8", all_touched=all_touched)
    b = rio_features.rasterize(shapes_b, out_shape=(h,w), transform=tfm, fill=0, dtype="uint8", all_touched=all_touched)

    dst = np.zeros((h,w), dtype="uint8")
    with rasterio.open(os.path.join(ROOT, "work", "intake", "staging",
        "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体",
        "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif")) as src:
        reproject(source=rasterio.band(src,1), destination=dst,
            src_crs=src.crs, dst_crs=pyproj.CRS.from_user_input(TARGET_CRS),
            src_transform=src.transform, dst_transform=tfm,
            resampling=Resampling.nearest, src_nodata=255, dst_nodata=0)
    c = (dst == 1).astype("uint8")

    pairs = [("CMSA",a,"CMSSM",b),("CMSA",a,"GEODATA",c),("CMSSM",b,"GEODATA",c)]
    px = res_m**2/1e6
    out = []
    for na,arr_a,nb,arr_b in pairs:
        inter = int((arr_a & arr_b).sum()); union = int((arr_a | arr_b).sum())
        iou = inter/union if union else np.nan
        out.append({"pair":f"{na}_vs_{nb}","iou":round(iou,4),"dice":round(2*inter/(arr_a.sum()+arr_b.sum()),4) if (arr_a.sum()+arr_b.sum())>0 else np.nan,"area_a_km2":round(arr_a.sum()*px,2),"area_b_km2":round(arr_b.sum()*px,2),"intersection_km2":round(inter*px,2),"union_km2":round(union*px,2),"res_m":res_m,"shift_m":shift,"all_touched":str(all_touched),"buf_m":buf,"label":label})
    print(f"  [{label}] {res_m}m shift={shift}m at={all_touched} buf={buf}m — {time.time()-t:.0f}s")
    return out


all_rows = []
print("BASELINE")
all_rows += run_test(100, 0, False, 10000, "baseline")
for shift in [50, 100, -100]:
    all_rows += run_test(100, shift, False, 10000, f"shift_{shift}m")
all_rows += run_test(100, 0, True, 10000, "all_touched_true")
for buf in [0, 5000, 50000]:
    all_rows += run_test(100, 0, False, buf, f"buffer_{buf}m")

with open(os.path.join(RESULTS, "robustness_2020.csv"), "w", newline="") as f:
    keys = list(all_rows[0].keys())
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(all_rows)

print("\n=== ROBUSTNESS SUMMARY ===")
for pair in ["CMSA_vs_CMSSM","CMSA_vs_GEODATA","CMSSM_vs_GEODATA"]:
    pr = [r for r in all_rows if r["pair"]==pair]
    base_iou = [r for r in pr if r["label"]=="baseline"][0]["iou"]
    print(f"\n{pair} baseline IoU={base_iou}:")
    for r in pr:
        d = r["iou"] - base_iou
        print(f"  {r['label']:25s} IoU={r['iou']:.4f}  Δ={d:+.4f}  ({d/base_iou*100:+.2f}%)")
