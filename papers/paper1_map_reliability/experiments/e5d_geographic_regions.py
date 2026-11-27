#!/usr/bin/env python3
"""
E5d — Geographically defensible sea-region regionalization (replaces the
EPSG:3410 longitude bands that R2 mislabelled as Bohai/Yellow Sea, East China
Sea and South China Sea).

Why the previous regionalization was wrong
------------------------------------------
R2's E5/E5b/E5c split the harmonized EPSG:3410 domain at x = 11,000,000 m and
x = 11,500,000 m.  In EPSG:3410 (cylindrical equal-area, central meridian 0)
x is linear in longitude at ~96.3 km per degree, so those splits are meridian
slices: x = 11.0 Mm ~ 114.2 degE and x = 11.5 Mm ~ 119.4 degE.  The resulting
three "regions" therefore contained parts of very different coasts and could
not be called Bohai/Yellow Sea, East China Sea or South China Sea.  All R2
band products are preserved as superseded evidence under
results/superseded_e5_longitude_bands/.

Boundary source used here
-------------------------
Natural Earth 1:10m "geography marine polygons" (v5.1.1, public domain),
which are the IHO-derived named sea areas and carry official names:
  Bo Hai (渤海), Yellow Sea (黄海), East China Sea (东海),
  South China Sea (南海), Taiwan Strait (台湾海峡), Hangzhou Bay (杭州湾),
  Gulf of Tonkin (北部湾), Qiongzhou Strait (琼州海峡), Luzon Strait (吕宋海峡).
Grouping into the three conventional sea regions:
  Bohai_Yellow : Bo Hai + Yellow Sea
  East_China   : East China Sea + Hangzhou Bay + Taiwan Strait
  South_China  : South China Sea + Gulf of Tonkin + Qiongzhou Strait
The grouping of Taiwan Strait with the East China Sea is an explicit
convention (documented in the JSON); a per-polygon decomposition is also
written so the reader can regroup it.

Positive pixels that fall in no marine polygon (coastal land / intertidal
pixels seaward of the Natural Earth land polygons) are assigned to the
nearest group, measured against group boundary pixels on the 100 m grid
(exact to one pixel).  Their number, share and maximum distance are reported.

Outputs
  results/regional_geographic_2020.csv
  results/regional_area_share_geographic_2020.csv
  results/region_definitions_geographic.json
  results/regional_by_marine_polygon_2020.csv
"""
import os, csv, json, time, subprocess
os.environ.setdefault("PROJ_LIB",
    "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")
import numpy as np
import geopandas as gpd
import shapely
from shapely.geometry import box
import rasterio
from rasterio import features as rio_features
from scipy import ndimage
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PAPER = os.path.join(ROOT, "papers", "paper1_map_reliability")
RESULTS = os.path.join(PAPER, "results")
CACHE = os.path.join(ROOT, "work", "cache", "paper1_100m")
os.makedirs(CACHE, exist_ok=True)

RES_M = 100
TARGET_CRS = "EPSG:3410"

NE_MARINE = os.path.join(ROOT, "work", "external", "naturalearth_10m_marine",
    "ne_10m_geography_marine_polys.shp")

REGION_GROUPS = {
    "Bohai_Yellow": ["Bo Hai", "Yellow Sea"],
    "East_China": ["East China Sea", "Hangzhou Bay", "Taiwan Strait"],
    "South_China": ["South China Sea", "Gulf of Tonkin", "Qiongzhou Strait"],
}

PRODUCTS_NPZ = os.path.join(CACHE, "products_100m_epsg3410.npz")
MASKS_NPZ = os.path.join(CACHE, "marine_masks_100m.npz")
LOG_PATH = os.path.join(CACHE, "e5d_marine_run.log")

_T0 = time.time()


def log(msg):
    line = f"[{time.time()-_T0:7.1f}s] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def git_commit():
    try:
        return subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "UNKNOWN"


def load_products():
    d = np.load(PRODUCTS_NPZ)
    arr = {"CMSA": d["cmsa"], "CM-SSM": d["cmssm"], "GEODATA": d["geo"]}
    H, W = int(d["H"]), int(d["W"])
    db = d["db"]
    tr = rasterio.Affine(*d["transform"].tolist())
    log(f"loaded cached products: grid {W} x {H} = {W*H:,} px "
        f"({W*H/1e6:.2f} million)")
    return arr, H, W, db, tr


def build_marine_masks(H, W, db, tr):
    if os.path.exists(MASKS_NPZ):
        d = np.load(MASKS_NPZ)
        masks = {k[:-6]: d[k].astype(bool) for k in d.files
                 if k.endswith("__mask") and not k.startswith("poly_")}
        poly_masks = {k[5:-6]: d[k].astype(bool) for k in d.files
                      if k.endswith("__mask") and k.startswith("poly_")}
        poly_masks = {k.replace("_", " "): v for k, v in poly_masks.items()}
        per_poly = json.loads(str(d["per_poly"]))
        log(f"loaded cached marine masks {MASKS_NPZ}")
        return masks, per_poly, poly_masks

    log("reading Natural Earth 10m marine polygons")
    mp = gpd.read_file(NE_MARINE)
    dom = box(db[0], db[1], db[2], db[3])
    # filter in 4326 to reduce projected geometry, then clip in the analysis CRS
    mp = mp[mp.geometry.intersects(
        gpd.GeoSeries([dom], crs=TARGET_CRS).to_crs(mp.crs).iloc[0])]
    mp = mp.to_crs(TARGET_CRS)
    mp["geometry"] = mp.geometry.intersection(dom)
    mp = mp[~mp.geometry.is_empty]
    log(f"marine polygons intersecting domain: {len(mp)}")

    wanted = sorted({n for v in REGION_GROUPS.values() for n in v})
    have = set(mp["name"])
    core = {"Bo Hai", "Yellow Sea", "East China Sea", "South China Sea",
            "Gulf of Tonkin"}
    missing_core = sorted(core - have)
    if missing_core:
        raise RuntimeError(
            f"Natural Earth marine polygons missing (core): {missing_core}")
    missing_opt = [n for n in wanted if n not in have]
    if missing_opt:
        log(f"optional marine polygons not present after clipping: {missing_opt}")

    masks = {}
    per_poly = []
    for gname, names in REGION_GROUPS.items():
        present = [n for n in names if n in have]
        sel = mp[mp["name"].isin(present)]
        t = time.time()
        r = rio_features.rasterize([(g, 1) for g in sel.geometry],
            out_shape=(H, W), transform=tr, fill=0, dtype="uint8", all_touched=False)
        masks[gname] = r.astype(bool)
        log(f"rasterized {gname}: {int(masks[gname].sum()):,} px "
            f"({time.time()-t:.1f}s) from {present}")
        per_poly.append({"region": gname, "polygons": present,
                         "absent_after_clip": [n for n in names if n not in have]})

    # per-polygon decomposition (for readers who want a different grouping)
    poly_masks = {}
    for nm in sorted(have & set(wanted)):
        sel = mp[mp["name"] == nm]
        r = rio_features.rasterize([(g, 1) for g in sel.geometry],
            out_shape=(H, W), transform=tr, fill=0, dtype="uint8",
            all_touched=False).astype(bool)
        poly_masks[nm] = r

    np.savez_compressed(MASKS_NPZ,
        **{f"{k}__mask": v for k, v in masks.items()},
        **{f"poly_{const(k)}__mask": v for k, v in poly_masks.items()},
        per_poly=np.array(json.dumps(per_poly))
    )
    log(f"cached marine masks -> {MASKS_NPZ}")
    return masks, per_poly, poly_masks


def const(name):
    return name.replace(" ", "_").replace("/", "_")


def assign_residual(union_pos, masks):
    """Assign positive pixels outside all group masks to nearest group boundary."""
    residual = union_pos & ~np.logical_or.reduce([m for m in masks.values()])
    n_resid = int(residual.sum())
    log(f"residual positive px outside all marine groups: {n_resid:,}")
    if n_resid == 0:
        return residual, {}, 0.0

    ys, xs = np.nonzero(residual)
    query = np.column_stack([ys, xs]).astype(np.float32)
    names = [g for g, m in masks.items() if int(m.sum()) > 0]

    trees = {}
    for gname in names:
        m = masks[gname]
        edge = m & ~ndimage.binary_erosion(m, structure=np.ones((3, 3), bool),
                                           border_value=0)
        ey, ex = np.nonzero(edge)
        trees[gname] = cKDTree(np.column_stack([ey, ex]).astype(np.float32))
        log(f"  boundary KD-tree {gname}: {len(ey):,} px")

    best_d = np.full(n_resid, np.inf, dtype=np.float32)
    best_k = np.full(n_resid, -1, dtype=np.int8)
    for k, gname in enumerate(names):
        dd, _ = trees[gname].query(query, k=1, workers=-1)
        upd = dd < best_d
        best_d[upd] = dd[upd]
        best_k[upd] = k

    assigned = {g: 0 for g in names}
    flat_idx = ys.astype(np.int64) * residual.shape[1] + xs.astype(np.int64)
    buf = np.zeros(residual.size, dtype=bool)
    for k, gname in enumerate(names):
        sel = (best_k == k)
        assigned[gname] = int(sel.sum())
        if assigned[gname]:
            buf[:] = False
            buf[flat_idx[sel]] = True
            masks[gname] = masks[gname] | buf.reshape(residual.shape)
    log(f"nearest-group assignment: {assigned}")
    return residual, assigned, float(best_d.max()) * RES_M / 1000.0


def region_metrics(arr_a, arr_b, mask, res_m, region_label, pair_label):
    a = arr_a[mask]
    b = arr_b[mask]
    pa = int(a.sum())
    pb = int(b.sum())
    inter = int((a & b).sum())
    union = int((a | b).sum())
    only_a = pa - inter
    only_b = pb - inter
    px_km2 = res_m ** 2 / 1e6
    iou = inter / union if union > 0 else float("nan")
    dice = 2 * inter / (pa + pb) if (pa + pb) > 0 else float("nan")
    return {
        "subregion": region_label, "pair": pair_label, "resolution_m": res_m,
        "area_a_km2": round(pa * px_km2, 2),
        "area_b_km2": round(pb * px_km2, 2),
        "intersection_km2": round(inter * px_km2, 2),
        "union_km2": round(union * px_km2, 2),
        "only_a_km2": round(only_a * px_km2, 2),
        "only_b_km2": round(only_b * px_km2, 2),
        "disagree_km2": round((only_a + only_b) * px_km2, 2),
        "iou": round(iou, 4), "dice": round(dice, 4),
        "a_over_b_ratio": round(pa / pb, 3) if pb > 0 else None,
        "region_area_km2": round(float(mask.sum()) * px_km2, 2),
        "a_coverage_pct": round(pa / float(mask.sum()) * 100, 3) if int(mask.sum()) else None,
        "b_coverage_pct": round(pb / float(mask.sum()) * 100, 3) if int(mask.sum()) else None,
    }


def main():
    open(LOG_PATH, "w").close()
    log("=" * 72)
    log("E5d — marine-polygon sea-region regionalization (Natural Earth 10m)")
    log("=" * 72)
    log(f"git_commit={git_commit()}")

    arr, H, W, db, tr = load_products()
    masks, per_poly, poly_masks = build_marine_masks(H, W, db, tr)

    union_pos = np.zeros((H, W), dtype=bool)
    for a in arr.values():
        union_pos |= a.astype(bool)
    n_pos_union = int(union_pos.sum())
    log(f"positive union px: {n_pos_union:,}")
    in_any = int((union_pos & np.logical_or.reduce(list(masks.values()))).sum())
    log(f"positive px directly inside a marine polygon: {in_any:,} "
        f"({in_any/n_pos_union*100:.1f}%)")

    residual, assigned, max_dist_km = assign_residual(union_pos, masks)
    n_resid = int(residual.sum())
    log(f"offshore/land residual assigned by nearest group: {n_resid:,} "
        f"({n_resid/n_pos_union*100:.2f}% of positive union); "
        f"max distance {max_dist_km:.1f} km")

    pairs = [("CMSA_vs_CMSSM", arr["CMSA"], arr["CM-SSM"]),
             ("CMSA_vs_GEODATA", arr["CMSA"], arr["GEODATA"]),
             ("CMSSM_vs_GEODATA", arr["CM-SSM"], arr["GEODATA"])]

    rows = []
    for gname in ["Bohai_Yellow", "East_China", "South_China"]:
        for pair_label, a, b in pairs:
            rows.append(region_metrics(a, b, masks[gname], RES_M, gname, pair_label))

    whole = np.ones((H, W), dtype=bool)
    for pair_label, a, b in pairs:
        rows.append(region_metrics(a, b, whole, RES_M, "National", pair_label))

    out_csv = os.path.join(RESULTS, "regional_geographic_2020.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # mapped-area share by sea region
    share_rows = []
    for prod, arr_p in arr.items():
        b = arr_p.astype(bool)
        total = int(b.sum())
        for gname in ["Bohai_Yellow", "East_China", "South_China"]:
            n = int(b[masks[gname]].sum())
            share_rows.append({"product": prod, "region": gname,
                               "area_km2": round(n * RES_M**2 / 1e6, 2),
                               "share_pct": round(n / total * 100, 2) if total else None})
    share_csv = os.path.join(RESULTS, "regional_area_share_geographic_2020.csv")
    with open(share_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["product", "region", "area_km2", "share_pct"])
        w.writeheader()
        w.writerows(share_rows)

    # per-marine-polygon decomposition
    poly_rows = []
    for prod, arr_p in arr.items():
        b = arr_p.astype(bool)
        total = int(b.sum())
        for nm in sorted(poly_masks):
            n = int(b[poly_masks[nm]].sum())
            poly_rows.append({"product": prod, "marine_polygon": nm,
                              "area_km2": round(n * RES_M**2 / 1e6, 2),
                              "share_pct": round(n / total * 100, 2) if total else None})
    poly_csv = os.path.join(RESULTS, "regional_by_marine_polygon_2020.csv")
    with open(poly_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["product", "marine_polygon",
                                          "area_km2", "share_pct"])
        w.writeheader()
        w.writerows(poly_rows)

    defs = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_commit": git_commit(),
        "method": "Natural Earth 10m IHO-derived marine polygons rasterized at "
                  "100 m EPSG:3410 over the CMSA+10 km domain; positive pixels "
                  "outside every polygon assigned to the nearest group measured "
                  "against group boundary pixels (KD-tree, exact to 1 pixel)",
        "boundary_source": {
            "dataset": "Natural Earth 1:10m Physical Vectors, Geography Marine Polygons",
            "version": "5.1.1",
            "license": "public domain (Natural Earth terms of use)",
            "path": NE_MARINE,
            "note": "IHO-derived named sea areas; names verified against name_zh",
        },
        "region_groups": REGION_GROUPS,
        "grouping_conventions": {
            "Taiwan Strait": "grouped with East China Sea (conventional); "
                             "per-polygon CSV allows regrouping",
            "Yellow Sea contains Bo Hai": "Bo Hai is a separate NE polygon but "
                                          "included with the Yellow Sea group",
        },
        "provenance_per_group": per_poly,
        "grid": {"crs": TARGET_CRS, "res_m": RES_M, "width": W, "height": H,
                 "total_px": W * H},
        "domain_bounds_m": [round(float(v), 1) for v in db],
        "positive_union_pixels": n_pos_union,
        "positive_px_inside_marine_polygon": in_any,
        "positive_px_assigned_by_nearest": n_resid,
        "positive_px_assigned_fraction_pct": round(n_resid / n_pos_union * 100, 2),
        "nearest_assignment_counts": assigned,
        "nearest_max_distance_km": round(max_dist_km, 2),
        "explored_but_not_primary": {
            "approach": "Natural Earth 10m admin-1 province groups + nearest-province",
            "result": "86.0% of positive union pixels fall outside the admin-1 "
                      "land polygons (coarse coastline excludes intertidal "
                      "flats), so province groups cannot be used as the primary "
                      "regional definition",
        },
        "note_supersedes": "results/superseded_e5_longitude_bands/",
        "note_grid_arithmetic": "verified W*H = 15096*22166 = 334617936 "
                                "(334.62 million)",
    }
    with open(os.path.join(RESULTS, "region_definitions_geographic.json"), "w") as f:
        json.dump(defs, f, indent=2, ensure_ascii=False)

    log("regional metrics (2020, 100 m):")
    for r in rows:
        if r["subregion"] != "National":
            log(f"  {r['subregion']:14s} {r['pair']:17s} "
                f"IoU={r['iou']:.4f} Dice={r['dice']:.4f} "
                f"A={r['area_a_km2']:7.2f} B={r['area_b_km2']:7.2f} "
                f"union={r['union_km2']:7.2f} covA={r['a_coverage_pct']:5.3f}%")
    log("national (whole domain) 100 m:")
    for r in rows:
        if r["subregion"] == "National":
            log(f"  National {r['pair']:17s} IoU={r['iou']:.4f} "
                f"Dice={r['dice']:.4f} A={r['area_a_km2']:.2f} "
                f"B={r['area_b_km2']:.2f} union={r['union_km2']:.2f}")
    log(f"saved: {out_csv}")
    log(f"saved: {share_csv}")
    log(f"saved: {poly_csv}")
    log(f"runtime: {time.time()-_T0:.1f}s")


if __name__ == "__main__":
    main()
