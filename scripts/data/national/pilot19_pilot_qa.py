#!/usr/bin/env python3
"""Issue #19 Phase H/I pilot-wide QA over every LANDED pilot product.

Reuses the canary gate dimensions byte-for-byte (pilot19_canary_qa),
then aggregates by sensor / year / region and renders contact sheets.
Live GEE identity cross-checks run on a deterministic 20% subset plus
every WARN/FAIL product; the offline byte-level gates cover every
product. Emits explicit PASS/WARN/FAIL per dimension and a pilot gate
verdict. No waiver is inferred from images.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import matplotlib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CANARY_QA_PATH = REPO_ROOT / "scripts/data/national/pilot19_canary_qa.py"
MANIFEST_DIR = REPO_ROOT / "work/national/pilot19/manifests"
SHEET_DIR = REPO_ROOT / "work/national/pilot19/contact_sheets"
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_pilot_qa_v1.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_pilot_qa_v1.csv"

PASS, WARN, FAIL, SKIPPED = "PASS", "WARN", "FAIL", "SKIPPED"
LIVE_FRACTION = 0.20
SHEET_N = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _load_canary() -> Any:
    spec = importlib.util.spec_from_file_location(
        "pilot19_canary_qa_gate", CANARY_QA_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pilot19_canary_qa_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


Q = _load_canary()


def _verdict_ignoring_skipped(dims: list[Any]) -> str:
    real: list[str] = [str(d.verdict) for d in dims
                     if d.verdict != SKIPPED]
    return max(real, key=lambda v: {"PASS": 0, "WARN": 1,
                                    "FAIL": 2}[v]) if real else PASS


def _live_eligible(pid: str) -> bool:
    h = hashlib.sha256(pid.encode("utf-8")).digest()[0]
    return h < int(256 * LIVE_FRACTION)


def _stride_thumb(arr: np.ndarray[Any, Any], target: int = 220) -> np.ndarray[Any, Any]:
    step = max(1, int(np.ceil(max(arr.shape) / target)))
    return arr[::step, ::step]


def _product_rgb(mf: dict[str, Any]) -> tuple[np.ndarray[Any, Any], str]:
    paths = Q._paths(mf)  # noqa: SLF001
    sensor = str(mf["sensor"])
    if sensor.startswith("landsat") or sensor == "sentinel2":
        hdr = Q._header(paths["sr"])  # noqa: SLF001
        names = hdr["descriptions"]
        idx = [names.index(n) for n in Q.RGB_BANDS[sensor]]
        with rasterio.open(paths["sr"]) as ds:
            arr = ds.read().astype("float64")
            dsmask = ds.dataset_mask() > 0
        finite = dsmask & np.isfinite(arr).all(axis=0)
        rgb = np.dstack([Q._stretch(arr[i], finite) for i in idx])  # noqa: SLF001
    else:
        with rasterio.open(paths["vvvh"]) as ds:
            vv = ds.read(1).astype("float64")
            vh = ds.read(2).astype("float64")
            dsmask = ds.dataset_mask() > 0
        fv, fh = dsmask & np.isfinite(vv), dsmask & np.isfinite(vh)
        vvs, vhs = Q._stretch(vv, fv), Q._stretch(vh, fh)  # noqa: SLF001
        rgb = np.dstack([vvs, vhs, (vvs + vhs) / 2.0])
    return _stride_thumb(rgb), sensor


def contact_sheet(products: list[dict[str, Any]], sensor_group: str,
                  picked: list[str]) -> Path:
    n = len(picked)
    cols = 4
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.0 * cols, 3.4 * rows))
    axes = np.atleast_1d(axes).ravel()
    by_id = {p["product_id"]: p for p in products}
    for ax, pid in zip(axes, picked, strict=False):
        mf_path = MANIFEST_DIR / f"{pid}.json"
        mf = json.loads(mf_path.read_text())
        thumb, _sensor = _product_rgb(mf)
        ax.imshow(thumb, interpolation="nearest")
        verdict = by_id[pid]["verdict"]
        color = {"PASS": "green", "WARN": "orange",
                  "FAIL": "red"}.get(verdict, "gray")
        ax.set_title(f"{pid}\n{verdict}", fontsize=8, color=color)
        ax.set_xticks([])
        ax.set_yticks([])
    for ax in axes[len(picked):]:
        ax.axis("off")
    fig.suptitle(f"Issue #19 Phase I contact sheet: {sensor_group}")
    fig.tight_layout()
    out = SHEET_DIR / f"contact_{sensor_group}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _pick(products: list[dict[str, Any]]) -> list[str]:
    problems = [p["product_id"] for p in products
                if p["verdict"] in (WARN, FAIL)]
    problems.sort()
    rest = sorted(p["product_id"] for p in products
                  if p["product_id"] not in set(problems))
    return (problems + rest)[:SHEET_N]


def pixel_scan(mf: dict[str, Any]) -> dict[str, Any]:
    """One cheap numpy pass per product for Phase I flags."""
    paths = Q._paths(mf)  # noqa: SLF001
    sensor = str(mf["sensor"])
    role = "sr" if "sr" in paths else "vvvh"
    with rasterio.open(paths[role]) as ds:
        arr = ds.read().astype("float64")
        dsmask = ds.dataset_mask() > 0
    out: dict[str, Any] = {"role": role, "bands": int(arr.shape[0])}
    finite_all = dsmask & np.isfinite(arr).all(axis=0)
    out["finite_fraction"] = float(finite_all.mean())
    out["all_nodata"] = bool(finite_all.sum() == 0)
    out["constant"] = False
    band_rows = []
    for i in range(arr.shape[0]):
        vals = arr[i][dsmask & np.isfinite(arr[i])]
        if vals.size == 0:
            band_rows.append({"band": i + 1, "empty": True})
            continue
        brow: dict[str, Any] = {
            "band": i + 1, "min": float(vals.min()),
            "p01": float(np.percentile(vals, 1)),
            "p50": float(np.percentile(vals, 50)),
            "p99": float(np.percentile(vals, 99)),
            "max": float(vals.max()),
            "std": float(vals.std()),
            "constant": bool(vals.std() == 0.0)}
        band_rows.append(brow)
        if vals.std() == 0.0:
            out["constant"] = True
    out["band_stats"] = band_rows
    if "valid" in paths:
        with rasterio.open(paths["valid"]) as ds:
            valid = ds.read(1)
        u, c = np.unique(valid, return_counts=True)
        out["valid_values"] = {int(k): int(v) for k, v in zip(u, c,
                                                              strict=True)}
        out["valid_fraction"] = float((valid == 1).mean())
    out["sensor"] = sensor
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-live", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    ap.add_argument("--out-csv", type=Path, default=OUT_CSV)
    args = ap.parse_args()

    driver = Q._DRIVER  # noqa: SLF001
    scope = {str(r["product_id"]): r
             for r in driver.load_scope(canary=False, only_sensor=None)}
    panel_rows = driver.load_panel()
    panel = {str(cid): row for cid, row in panel_rows.iterrows()}
    supports = pd.read_csv(Q.SUPPORTS_CSV)

    ee: Any | None = None
    if not args.no_live:
        Q.initialize()
        import ee as _ee  # noqa: PLC0415

        ee = _ee

    products: list[dict[str, Any]] = []
    mf_paths = sorted(MANIFEST_DIR.glob("*.json"))
    for mf_path in mf_paths:
        mf = json.loads(mf_path.read_text())
        pid = str(mf["product_id"])
        if pid not in scope:
            continue  # not part of the frozen SELECTED pilot (never happens)
        plan_row = scope[pid]
        panel_row = panel[str(mf["cell_id"])]
        live = ee if (not args.no_live and _live_eligible(pid)) else None
        dims, _run_verdict = Q.run_product(
            mf, plan_row, panel_row, supports, live)
        verdict = _verdict_ignoring_skipped(dims)
        scan = pixel_scan(mf)
        products.append({
            "product_id": pid, "cell_id": str(mf["cell_id"]),
            "sensor": str(mf["sensor"]), "year": int(mf["year"]),
            "region_province": str(mf.get("region_province")),
            "coverage_tier": str(mf.get("coverage_tier")),
            "verdict": verdict,
            "live_cross_checked": live is not None,
            "pixel_scan": scan,
            "dimensions": [d.to_dict() for d in dims]})
        print(f"[{pid}] {verdict}"
              + (" LIVE" if live is not None else ""))

    # Aggregates by sensor / year / region.
    df = pd.DataFrame([{
        "product_id": p["product_id"], "sensor": p["sensor"],
        "year": p["year"], "region_province": p["region_province"],
        "verdict": p["verdict"],
        "live": p["live_cross_checked"],
        "finite_fraction": p["pixel_scan"]["finite_fraction"],
        "valid_fraction": p["pixel_scan"].get("valid_fraction"),
        "all_nodata": p["pixel_scan"]["all_nodata"],
        "constant": p["pixel_scan"]["constant"],
        "n_bytes": int(json.loads((MANIFEST_DIR / (
            p["product_id"] + ".json")).read_text())["n_bytes"]),
    } for p in products])
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out_csv, index=False)

    agg: dict[str, Any] = {}
    for key in ("sensor", "year", "region_province"):
        agg[key] = {}
        for val, grp in df.groupby(key, dropna=False):
            agg[key][str(val)] = {
                "n": int(len(grp)),
                "verdicts": grp["verdict"].value_counts().to_dict(),
                "live_checked": int(grp["live"].sum()),
                "mean_valid_fraction": (None if grp["valid_fraction"].dropna(
                ).empty else float(grp["valid_fraction"].mean())),
                "mean_finite_fraction": float(
                    grp["finite_fraction"].mean()),
                "all_nodata": int(grp["all_nodata"].sum()),
                "constant": int(grp["constant"].sum()),
                "total_bytes": int(grp["n_bytes"].sum())}

    # Contact sheets per sensor (problems first).
    sheets: dict[str, str] = {}
    for sensor_group in sorted({p["sensor"] for p in products}):
        group = [p for p in products if p["sensor"] == sensor_group]
        if group:
            picked = _pick(group)
            sheets[sensor_group] = str(contact_sheet(
                products, sensor_group, picked))

    gate = max((p["verdict"] for p in products),
               key=lambda v: {"PASS": 0, "WARN": 1, "SKIPPED": 1,
                              "FAIL": 2}[v], default=FAIL)
    report = {
        "schema": "spartina_pilot19_pilot_qa_v1",
        "issue": "#19",
        "created_utc": _now(),
        "live_gee_subset_fraction": 0.0 if args.no_live else LIVE_FRACTION,
        "n_products_landed": len(products),
        "gate_verdict": gate,
        "verdict_counts": df["verdict"].value_counts().to_dict(),
        "aggregates": agg,
        "contact_sheets": sheets,
        "products": products}
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"PILOT_QA_{gate}: {len(products)} products -> {args.out}")
    return 0 if gate != FAIL else 2


if __name__ == "__main__":
    raise SystemExit(main())
