"""Pilot-0 Hangzhou Bay 2015: define analysis grids and quantify co-registration.

Read-only on ``old datasets/``. Every reprojected/resampled product is a
COPY written under ``work/hangzhou2015/v1/``.

Produces (all deterministic):
- grid_spec.json                     : CRS/resolution/origin decision
- label_mask_30m.tif                 : local WEAK mask, NEAREST warp
- l8_sr_30m.tif (7 bands reflectance): bilinear, C02-L2 DN*2.75e-5-0.2 (fill 0)
- l8_valid_30m.tif                   : non-fill optical pixels
- ndvi_30m.tif / sai_30m.tif         : bilinear continuous indices
- s1_vv_30m.tif / s1_vh_30m.tif      : bilinear in dB to the 30 m grid
- s1_vv_10m.tif / s1_vh_10m.tif      : bilinear to the native-density 10 m grid
- optical_edges_10m.tif / s1_edges_10m.tif : diagnostic edge maps
- coregistration_diagnostics.json    : lag-NCC shifts, grid phases,
                                        S1 resampling signature, gate result

Predeclared tolerances (Issue M1.3 C):
- optical <-> label shift <= 15 m (0.5 Landsat pixel)
- S1 <-> optical shift <= 10 m (1 Sentinel-1 pixel)
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, cast

import numpy as np
import rasterio
import rasterio.warp  # noqa: F401  (registers rasterio.warp)
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import transform_bounds
from scipy import ndimage

ANALYSIS_CRS = "EPSG:32651"  # UTM zone 51N, correct zone for ~121.2E
RES_30M = 30.0
RES_10M = 10.0
ANCHOR_EASTING = 500000.0  # UTM false easting -> canonical grid anchor
TOL_OPT_M = 15.0
TOL_S1_M = 10.0

MASK_NAME = "c201511839DTSP_2.tif"
L8_NAME = "L8_AllBands_2015.tif"
NDVI_NAME = "NDVI_2015.tif"
SAI_NAME = "SAI_2015.tif"
S1_NAMES = {"vv": "S1_VV_2015.tif", "vh": "S1_VH_2015.tif"}


def snapped_grid(
    west: float, south: float, east: float, north: float,
    res: float,
) -> tuple[Affine, int, int, tuple[float, float, float, float]]:
    """Deterministic UTM-anchored grid fully covering the bounds."""
    x0 = math.floor((west - ANCHOR_EASTING) / res) * res + ANCHOR_EASTING
    y0 = math.ceil((north - ANCHOR_EASTING) / res) * res + ANCHOR_EASTING
    x1 = math.ceil((east - ANCHOR_EASTING) / res) * res + ANCHOR_EASTING
    y1 = math.floor((south - ANCHOR_EASTING) / res) * res + ANCHOR_EASTING
    width = int(round((x1 - x0) / res))
    height = int(round((y0 - y1) / res))
    return Affine(res, 0.0, x0, 0.0, -res, y0), width, height, (x0, y1, x1, y0)


def warp_to_grid(
    src_path: Path,
    dst_path: Path,
    dst_transform: Affine,
    dst_crs: str,
    width: int,
    height: int,
    *,
    bands: int = 1,
    dtype: str = "float32",
    resampling: Resampling = Resampling.bilinear,
    src_band: int = 1,
    nodata: float | None = None,
    scale: float = 1.0,
    offset: float = 0.0,
    src_nodata: float | None = None,
) -> None:
    """Warp one (scaled) band or all bands of a source onto the target grid."""
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(src_path) as src:
        src_count = src.count if bands > 1 else 1
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": src_count,
            "dtype": dtype,
            "crs": dst_crs,
            "transform": dst_transform,
            "compress": "deflate",
            "predictor": 2,
        }
        if nodata is not None:
            profile["nodata"] = nodata
        with rasterio.open(dst_path, "w", **profile) as dst:
            band_indices = range(1, src.count + 1) if bands > 1 else [src_band]
            for out_i, b in enumerate(band_indices, start=1):
                dst_arr = np.full((height, width),
                                  nodata if nodata is not None else 0,
                                  dtype=dtype)
                rasterio.warp.reproject(
                    source=rasterio.band(src, b),
                    destination=dst_arr,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs=dst_crs,
                    src_nodata=src_nodata,
                    dst_nodata=nodata,
                    resampling=resampling,
                )
                if scale != 1.0 or offset != 0.0:
                    m = np.isfinite(dst_arr)
                    dst_arr[m] = dst_arr[m] * scale + offset
                dst.write(dst_arr.astype(dtype), out_i)
                if bands > 1:
                    dst.set_band_description(out_i, src.descriptions[b - 1])


def edge_map(arr: np.ndarray[Any, Any], valid: np.ndarray[Any, Any] | None = None,
             top_fraction: float = 0.20) -> np.ndarray[Any, Any]:
    """Sobel gradient magnitude, thresholded to the strongest edge pixels."""
    a = arr.astype("float64")
    finite = np.isfinite(a)
    a = np.where(finite, a, 0.0)
    if valid is not None:
        a = np.where(valid, a, 0.0)
    gx = ndimage.sobel(a, axis=1)
    gy = ndimage.sobel(a, axis=0)
    mag = np.hypot(gx, gy)
    interior = np.ones_like(mag, dtype=bool)
    interior[:12, :] = interior[-12:, :] = False
    interior[:, :12] = interior[:, -12:] = False
    if valid is not None:
        interior &= valid
    vals = mag[interior]
    cutoff = np.quantile(vals, 1 - top_fraction)
    edges = (mag >= cutoff) & interior
    return cast(np.ndarray[Any, Any], edges.astype("float32"))


def lag_ncc(
    fixed: np.ndarray[Any, Any],
    moving: np.ndarray[Any, Any],
    maxlag: int,
    valid: np.ndarray[Any, Any] | None = None,
) -> dict[str, Any]:
    """Best integer-lag alignment of two edge maps (moving shifted vs fixed).

    Returns dx,dy in pixels (positive dx: moving must shift east by +dx),
    peak NCC, subpixel peak via 2-D quadratic refinement, and the full
    correlation surface.
    """
    f = fixed.astype("float64")
    m = moving.astype("float64")
    if valid is None:
        valid = np.ones_like(f, dtype=bool)
    f = f - f[valid].mean()
    m = m - m[valid].mean()
    norm_f = math.sqrt(float((f[valid] ** 2).sum()))
    surface = np.full((2 * maxlag + 1, 2 * maxlag + 1), np.nan)
    best = (-np.inf, 0, 0)
    for dy in range(-maxlag, maxlag + 1):
        for dx in range(-maxlag, maxlag + 1):
            shifted = np.roll(np.roll(m, dy, axis=0), dx, axis=1)
            v = np.roll(np.roll(valid, dy, axis=0), dx, axis=1) & valid
            denom = norm_f * math.sqrt(float((shifted[v] ** 2).sum()))
            corr = float((f[v] * shifted[v]).sum()) / denom if denom > 0 else np.nan
            surface[dy + maxlag, dx + maxlag] = corr
            if np.isfinite(corr) and corr > best[0]:
                best = (corr, dx, dy)
    peak, bx, by = best
    # 2-D quadratic subpixel refinement (peak neighbourhood)
    sx = sy = 0.0
    i, j = by + maxlag, bx + maxlag
    try:
        z = surface
        dx_num = 0.5 * (z[i, j - 1] - z[i, j + 1])
        dx_den = z[i, j - 1] - 2 * z[i, j] + z[i, j + 1]
        dy_num = 0.5 * (z[i - 1, j] - z[i + 1, j])
        dy_den = z[i - 1, j] - 2 * z[i, j] + z[i + 1, j]
        sx = dx_num / dx_den if abs(dx_den) > 1e-12 else 0.0
        sy = dy_num / dy_den if abs(dy_den) > 1e-12 else 0.0
        sx = float(np.clip(sx, -1, 1))
        sy = float(np.clip(sy, -1, 1))
    except (IndexError, ZeroDivisionError):
        pass
    # surface secondary peak for sharpness
    flat = surface[~np.isnan(surface)]
    second = np.partition(flat, -2)[-2] if flat.size > 1 else np.nan
    return {
        "best_dx_px": bx,
        "best_dy_px": by,
        "best_dx_subpx": bx + sx,
        "best_dy_subpx": by + sy,
        "peak_ncc": peak,
        "second_peak_ncc": float(second),
        "peak_sharpness": peak - float(second),
        "surface": surface.tolist(),
    }


def resampling_signature(arr: np.ndarray[Any, Any], valid: np.ndarray[Any, Any],
                         factor: int = 3) -> dict[str, Any]:
    """Detect nearest-neighbour upsampling from a coarser grid.

    If the raster were factor-NN-upsampled, factor*factor blocks would be
    constant. Report identical-block share plus high-frequency energy
    ratio, against a matched NN-upsampled control built from the raster
    itself.
    """
    a = arr.astype("float32")
    h, w = (s // factor * factor for s in a.shape)
    a = a[:h, :w]
    valid = valid[:h, :w]
    blocks = a.reshape(h // factor, factor, w // factor, factor)
    p2p = blocks.max(axis=(1, 3)) - blocks.min(axis=(1, 3))
    vblocks = valid.reshape(h // factor, factor, w // factor, factor).all(axis=(1, 3))
    identical = float((p2p[vblocks] == 0).mean())

    # High-frequency energy: energy above 1/(2*30m) Nyquist of the 10 m grid.
    cy, cx = (np.array(a.shape) / 2).astype(int)
    yy, xx = np.indices(a.shape)
    freq = np.sqrt(((yy - cy) / h) ** 2 + ((xx - cx) / w) ** 2)
    a_filled = np.where(valid, a, np.nanmean(a[valid]))
    spec = np.fft.fftshift(np.abs(np.fft.fft2(a_filled - a_filled.mean())) ** 2)
    total = float(spec.sum())
    hi = float(spec[freq > 1.0 / (2 * factor)].sum()) / total if total > 0 else float("nan")

    # Control: NN upsample block means, measure its identical-block share.
    means = blocks.mean(axis=(1, 3))
    up = np.repeat(np.repeat(means, factor, axis=0), factor, axis=1)
    up_blocks = up.reshape(h // factor, factor, w // factor, factor)
    control_identical = float(
        ((up_blocks.max(axis=(1, 3)) - up_blocks.min(axis=(1, 3)))[vblocks] == 0).mean()
    )
    return {
        "factor_tested": factor,
        "identical_block_share": identical,
        "nn_upsampled_control_share": control_identical,
        "high_freq_energy_fraction": hi,
        "interpretation": (
            "share near 1.0 with near-zero high-frequency energy would "
            "indicate factor-NN upsampling; share near 0 indicates native "
            "fine-grid information"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src-dir", type=Path,
                    default=Path("old datasets/Spartina/HangZhouBay"))
    ap.add_argument("--work-dir", type=Path,
                    default=Path("work/hangzhou2015/v1"))
    ap.add_argument("--json-out", type=Path,
                    default=Path("artifacts/audit/pilot0/coregistration.json"))
    args = ap.parse_args(argv)
    wd = args.work_dir
    wd.mkdir(parents=True, exist_ok=True)

    diagnostics: dict[str, Any] = {
        "analysis_crs": ANALYSIS_CRS,
        "tolerances_m": {"optical_label": TOL_OPT_M, "s1_optical": TOL_S1_M},
        "products": {},
    }

    # --- coverage rectangle from the mask (native UTM 51N) ---------------
    with rasterio.open(args.src_dir / MASK_NAME) as ds:
        mask_bounds = list(ds.bounds)
        mask_transform = list(ds.transform)[:6]
        mask_shape = (ds.height, ds.width)
    diagnostics["source_mask"] = {
        "bounds_utm51n": mask_bounds,
        "transform": mask_transform,
        "shape": mask_shape,
    }

    g30, w30, h30, b30 = snapped_grid(
        mask_bounds[0], mask_bounds[1], mask_bounds[2], mask_bounds[3], RES_30M)
    g10, w10, h10, b10 = snapped_grid(
        mask_bounds[0], mask_bounds[1], mask_bounds[2], mask_bounds[3], RES_10M)
    diagnostics["grids"] = {
        "30m": {"transform": list(g30)[:6], "width": w30, "height": h30,
                "bounds": b30},
        "10m": {"transform": list(g10)[:6], "width": w10, "height": h10,
                "bounds": b10},
        "decision": (
            "30 m UTM 51N anchored grid is the analysis grid: label-native "
            "(mask 29.98x29.95 m) and Landsat-native (~30 m); no fake 10 m "
            "information. S1 is also retained on its own 10 m-density grid."
        ),
    }
    (wd / "grid_spec.json").write_text(
        json.dumps(
            {
                "crs": ANALYSIS_CRS,
                "grid_30m": {"transform": list(g30)[:6], "width": w30,
                             "height": h30, "bounds": b30},
                "grid_10m": {"transform": list(g10)[:6], "width": w10,
                             "height": h10, "bounds": b10},
                "anchor_easting": ANCHOR_EASTING,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # --- labels (nearest) -------------------------------------------------
    warp_to_grid(args.src_dir / MASK_NAME, wd / "label_mask_30m.tif",
                 g30, ANALYSIS_CRS, w30, h30, dtype="uint8",
                 resampling=Resampling.nearest, nodata=127)

    # --- L8 SR (all 7 bands, reflectance scaled) --------------------------
    # Landsat C02 L2 Science Product transform: reflectance = DN*2.75e-5 - 0.2
    warp_to_grid(args.src_dir / L8_NAME, wd / "l8_sr_30m.tif",
                 g30, ANALYSIS_CRS, w30, h30, bands=7, dtype="float32",
                 resampling=Resampling.bilinear, nodata=np.nan,
                 src_nodata=0, scale=2.75e-5, offset=-0.2)
    with rasterio.open(wd / "l8_sr_30m.tif") as ds:
        sr = ds.read().astype("float32")
    valid_opt = np.all(np.isfinite(sr), axis=0)
    with rasterio.open(
        wd / "l8_valid_30m.tif", "w", driver="GTiff", height=h30, width=w30,
        count=1, dtype="uint8", crs=ANALYSIS_CRS, transform=g30,
        compress="deflate",
    ) as dst:
        dst.write(valid_opt.astype("uint8"), 1)

    # --- indices -----------------------------------------------------------
    warp_to_grid(args.src_dir / NDVI_NAME, wd / "ndvi_30m.tif",
                 g30, ANALYSIS_CRS, w30, h30, dtype="float32",
                 resampling=Resampling.bilinear, nodata=np.nan)
    warp_to_grid(args.src_dir / SAI_NAME, wd / "sai_30m.tif",
                 g30, ANALYSIS_CRS, w30, h30, dtype="float32",
                 resampling=Resampling.bilinear, nodata=np.nan)

    # --- S1 at 30 m and at native-density 10 m ----------------------------
    for key, name in S1_NAMES.items():
        warp_to_grid(args.src_dir / name, wd / f"s1_{key}_30m.tif",
                     g30, ANALYSIS_CRS, w30, h30, dtype="float32",
                     resampling=Resampling.bilinear, nodata=np.nan)
        warp_to_grid(args.src_dir / name, wd / f"s1_{key}_10m.tif",
                     g10, ANALYSIS_CRS, w10, h10, dtype="float32",
                     resampling=Resampling.bilinear, nodata=np.nan)

    # --- edge maps on the 10 m grid --------------------------------------
    with rasterio.open(wd / "ndvi_30m.tif") as ds:
        ndvi30 = ds.read(1)
    ndvi10 = np.empty((h10, w10), "float32")
    with rasterio.open(args.src_dir / NDVI_NAME) as src:
        rasterio.warp.reproject(
            source=rasterio.band(src, 1), destination=ndvi10,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=g10, dst_crs=ANALYSIS_CRS,
            resampling=Resampling.bilinear,
        )
    with rasterio.open(wd / "s1_vv_10m.tif") as ds:
        vv10 = ds.read(1)
    with rasterio.open(wd / "s1_vh_10m.tif") as ds:
        vh10 = ds.read(1)
    valid10 = np.isfinite(ndvi10) & np.isfinite(vv10) & np.isfinite(vh10)
    e_opt = edge_map(ndvi10, valid10)
    e_vv = edge_map(vv10, valid10)
    e_vh = edge_map(vh10, valid10)
    for nm, e in (("optical_edges_10m.tif", e_opt),
                  ("s1_vv_edges_10m.tif", e_vv),
                  ("s1_vh_edges_10m.tif", e_vh)):
        with rasterio.open(
            wd / nm, "w", driver="GTiff", height=h10, width=w10, count=1,
            dtype="float32", crs=ANALYSIS_CRS, transform=g10,
        ) as dst:
            dst.write(e, 1)

    ncc_vv = lag_ncc(e_opt, e_vv, 12, valid10)
    ncc_vh = lag_ncc(e_opt, e_vh, 12, valid10)
    for r in (ncc_vv, ncc_vh):
        r["shift_m_east"] = r["best_dx_subpx"] * RES_10M
        r["shift_m_north"] = -r["best_dy_subpx"] * RES_10M
        r.pop("surface")
    diagnostics["edge_alignment_10m"] = {"S1_VV_vs_optical_NDVI": ncc_vv,
                                         "S1_VH_vs_optical_NDVI": ncc_vh}

    # --- mask edges vs optical edges on 30 m grid -------------------------
    with rasterio.open(wd / "label_mask_30m.tif") as ds:
        mask30 = ds.read(1)
    valid30 = valid_opt & (mask30 != 127) & np.isfinite(ndvi30)
    e_mask = edge_map((mask30 == 1).astype("float32"), valid30)
    e_opt30 = edge_map(ndvi30, valid30)
    ncc_mask = lag_ncc(e_opt30, e_mask, 6, valid30)
    ncc_mask["shift_m_east"] = ncc_mask["best_dx_subpx"] * RES_30M
    ncc_mask["shift_m_north"] = -ncc_mask["best_dy_subpx"] * RES_30M
    ncc_mask["note"] = (
        "label edges are classification boundaries; correlation is "
        "supportive only, not a substitute for stable-feature GCPs"
    )
    ncc_mask.pop("surface")
    diagnostics["edge_alignment_30m"] = {"mask_vs_optical_NDVI": ncc_mask}

    # --- S1 resampling signature ------------------------------------------
    diagnostics["s1_resampling_signature"] = {
        "VV": resampling_signature(vv10, valid10, factor=3),
        "VH": resampling_signature(vh10, valid10, factor=3),
    }

    # --- footprint edge offsets (grid phase, from M1.1 observation) ------
    with rasterio.open(args.src_dir / S1_NAMES["vv"]) as ds:
        s1_bounds_lonlat = list(ds.bounds)
        s1_shape = (ds.height, ds.width)
    s1_b = transform_bounds("EPSG:4326", ANALYSIS_CRS, *s1_bounds_lonlat)
    diagnostics["footprint_offsets"] = {
        "s1_bounds_utm51n": s1_b,
        "mask_bounds_utm51n": mask_bounds,
        "west_edge_delta_m": s1_b[0] - mask_bounds[0],
        "east_edge_delta_m": s1_b[2] - mask_bounds[2],
        "south_edge_delta_m": s1_b[1] - mask_bounds[1],
        "north_edge_delta_m": s1_b[3] - mask_bounds[3],
        "s1_shape": s1_shape,
        "interpretation": (
            "edge deltas measure export-rectangle origin differences, not "
            "pixel misregistration; true shift is judged from edge NCC"
        ),
    }

    # --- gate --------------------------------------------------------------
    shifts = {
        "s1_vv_vs_optical_m": math.hypot(ncc_vv["shift_m_east"],
                                         ncc_vv["shift_m_north"]),
        "s1_vh_vs_optical_m": math.hypot(ncc_vh["shift_m_east"],
                                         ncc_vh["shift_m_north"]),
        "mask_vs_optical_m": math.hypot(ncc_mask["shift_m_east"],
                                        ncc_mask["shift_m_north"]),
    }
    gate = {
        "s1_vv_within_10m": shifts["s1_vv_vs_optical_m"] <= TOL_S1_M,
        "s1_vh_within_10m": shifts["s1_vh_vs_optical_m"] <= TOL_S1_M,
        "mask_within_15m": shifts["mask_vs_optical_m"] <= TOL_OPT_M,
        "measured_shift_magnitudes_m": shifts,
    }
    gate["pass"] = all(
        [gate["s1_vv_within_10m"], gate["s1_vh_within_10m"],
         gate["mask_within_15m"]]
    )
    diagnostics["alignment_gate"] = gate

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(diagnostics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(gate, indent=2))
    print(f"-> {args.json_out}")
    return 0 if gate["pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
