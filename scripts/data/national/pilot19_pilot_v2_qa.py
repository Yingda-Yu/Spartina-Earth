#!/usr/bin/env python3
"""Issue #19 Phase H/I pilot-wide QA under PILOT_EVENT_SELECTION_V2.

Runs the V2 canary gate dimensions (actual-mask gate, interior scan,
S1 floor token, repair provenance plus every frozen V1 geometry /
physics / alignment dimension) over every LANDED V2-eligible pilot
product, then aggregates exactly the owner-requested Phase H/I items:

* actual observed coverage by product; PASS/WARN/FAIL distribution;
* sensor / year / region distributions;
* physical ranges, all-zero / all-NaN / constant products;
* S1 floor-mask area fractions; duplicate-byte checks;
* S1 pass/orbit consistency and ASC/DESC separation;
* transform/grid rebuild residuals; EO-label adapter alignment.

Live GEE identity cross-checks run on a deterministic 20% product subset
(the byte-level gates cover every product). Every plan-eligible slot that
did not land is independently recomputed from its on-disk evidence raster:
a slot with in-W10-cell coverage < 0.95 is a CONFIRMED honest actual-mask
rejection (the owner-approved honest-small-set outcome), while bytes
>= 0.95 contradict the rejection and FAIL QA; a slot with no bytes at all
is an unresolved incompleteness FAIL (unless --allow-partial).
Any FAIL => PILOT_V2_QA_FAIL.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import matplotlib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MANIFEST_DIR = REPO_ROOT / "work/national/pilot19/manifests"
SHEET_DIR = REPO_ROOT / "work/national/pilot19/contact_sheets/v2"
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_pilot_qa_v2.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_pilot_qa_v2.csv"
OUT_FULL_JSON = REPO_ROOT / "work/national/pilot19/qa/pilot_qa_v2_full.json"

_SCALAR_PRODUCT_KEYS = (
    "product_id",
    "cell_id",
    "sensor",
    "year",
    "variant",
    "region_province",
    "v2_change",
    "coverage_tier",
    "verdict",
    "live_cross_checked",
    "actual_observed_fraction",
    "n_bytes",
)
_PIXEL_SCAN_SUMMARY_KEYS = (
    "sensor",
    "actual_observed_fraction",
    "v2_change",
    "all_nan",
    "all_zero",
    "constant",
    "role",
    "bands",
    "finite_fraction",
    "valid_fraction",
    "floor_area_fraction",
    "dualpol_finite_fraction",
    "gee_pass",
    "variant",
    "n_scene_ids",
)


def slim_product(product: dict[str, Any]) -> dict[str, Any]:
    """Tracked-manifest view: scalars, dimension verdicts, scan summary.

    The full diagnostic (dimension details, per-band percentile stats,
    per-file integrity listings) is written separately under work/,
    which is outside Git, to keep the tracked manifest under the
    repository large-file threshold.
    """
    slim = {k: product[k] for k in _SCALAR_PRODUCT_KEYS if k in product}
    scan = product.get("pixel_scan")
    if isinstance(scan, dict):
        slim["pixel_scan"] = {k: scan[k] for k in _PIXEL_SCAN_SUMMARY_KEYS if k in scan}
    slim["dimensions"] = [
        {"name": d["name"], "verdict": d["verdict"]} for d in product.get("dimensions", [])
    ]
    return slim


def slim_report(report: dict[str, Any], full_path: Path) -> dict[str, Any]:
    return {
        **{k: v for k, v in report.items() if k != "products"},
        "full_diagnostic_artifact": str(full_path),
        "products": [slim_product(p) for p in report.get("products", [])],
    }


PASS, WARN, FAIL, SKIPPED = "PASS", "WARN", "FAIL", "SKIPPED"
_RANK = {PASS: 0, WARN: 1, SKIPPED: 1, FAIL: 2}
LIVE_FRACTION = 0.20
SHEET_N = 24


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _load(name: str, rel: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


Q2 = _load("pilot19_canary_v2_qa_gate", "scripts/data/national/pilot19_canary_v2_qa.py")
DRIVER = Q2._DRIVER  # noqa: SLF001


def worst(verdicts: list[str]) -> str:
    return max(verdicts, key=lambda v: _RANK[v])


def verdict_ignoring_skipped(dims: list[Any]) -> str:
    real = [str(d.verdict) for d in dims if d.verdict != SKIPPED]
    return worst(real) if real else PASS


def live_eligible(pid: str) -> bool:
    return hashlib.sha256(pid.encode("utf-8")).digest()[0] < int(256 * LIVE_FRACTION)


def verify_rejected_slot(plan_row: dict[str, Any]) -> dict[str, Any]:
    """Independently verify an unlanded planned-eligible slot from bytes.

    The exporter rejects products whose ACTUAL landed raster fails the
    0.95 in-W10-cell gate, leaving the downloaded (identical-grid) rasters
    on disk as evidence. QA never trusts the failure ledger: it recomputes
    grid and in-W10-cell fractions from those bytes. A slot is a confirmed
    honest rejection only when the bytes independently measure in-cell
    coverage < 0.95; bytes >= 0.95 contradict the rejection and FAIL QA.
    """
    pid = str(plan_row["product_id"])
    sensor = str(plan_row["sensor"])
    pixel_m = 30.0 if sensor.startswith("landsat") else 10.0
    prefix = DRIVER.prefix_for(plan_row, "sr", plan_version="v2")
    sr_candidates = sorted(DRIVER.PRODUCT_DIR.glob(f"{prefix}*.tif"))
    rec: dict[str, Any] = {
        "product_id": pid,
        "cell_id": str(plan_row["cell_id"]),
        "sensor": sensor,
        "year": int(plan_row["year"]),
    }
    if not sr_candidates:
        rec.update(
            {"status": "UNRESOLVED_NO_BYTES", "note": "no manifest and no evidence raster on disk"}
        )
        return rec
    sr = sr_candidates[0]
    stats = DRIVER.s2_sr_actual_mask(str(sr))
    with rasterio.open(sr) as ds:
        zone = int(ds.crs.to_epsg()) - 32600
    cell = DRIVER.sr_in_w10_cell_fraction(str(sr), str(plan_row["cell_id"]), zone, pixel_m)
    in_cell = float(cell["actual_observed_fraction_in_w10_cell"])
    ledger_entries = json.loads(DRIVER.FAILURES_JSON.read_text("utf-8")).get("failures", [])
    ledger = next(
        (
            str(f.get("detail", ""))[:400]
            for f in ledger_entries
            if str(f.get("product_id")) == pid and not f.get("superseded")
        ),
        "",
    )
    rec.update(
        {
            "evidence_raster": sr.name,
            "grid_fraction": stats["actual_observed_fraction"],
            "observed_pixels": stats["observed_pixels"],
            "grid_pixels": stats["grid_pixels"],
            "per_band_finite_fraction": stats["per_band_finite_fraction"],
            "cell_pixels": cell["cell_pixels"],
            "observed_in_cell_pixels": cell["observed_in_cell_pixels"],
            "actual_observed_fraction_in_w10_cell": in_cell,
            "failure_ledger_detail": ledger,
            "status": (
                "CONFIRMED_ACTUAL_MASK_REJECTION"
                if in_cell < 0.95
                else "REJECTION_CONTRADICTED_BY_BYTES"
            ),
        }
    )
    return rec


# ---------------------------------------------------------------------------
# per-product pixel scan (cheap numpy pass, V2 fields)
# ---------------------------------------------------------------------------


def pixel_scan(mf: dict[str, Any]) -> dict[str, Any]:
    paths = Q2._paths(mf)  # noqa: SLF001
    sensor = str(mf["sensor"])
    out: dict[str, Any] = {"sensor": sensor}
    gate_rec = mf.get("qa", {}).get("actual_mask_v2", {})
    out["actual_observed_fraction"] = float(gate_rec.get("actual_observed_fraction", -1.0))
    out["v2_change"] = str(mf.get("event_selection", {}).get("v2_change"))
    out["all_nan"] = False
    out["constant"] = False
    out["all_zero"] = False
    if sensor == "sentinel1":
        with rasterio.open(paths["vvvh"]) as ds:
            arr = ds.read().astype("float64")
            dsmask = ds.dataset_mask() > 0
        role = "vvvh"
    else:
        with rasterio.open(paths["sr"]) as ds:
            arr = ds.read().astype("float64")
            dsmask = ds.dataset_mask() > 0
        role = "sr"
    out["role"] = role
    out["bands"] = int(arr.shape[0])
    finite_each = [dsmask & np.isfinite(arr[i]) for i in range(arr.shape[0])]
    out["finite_fraction"] = float(np.stack(finite_each).all(axis=0).mean())
    band_rows: list[dict[str, Any]] = []
    any_nonzero = False
    for i in range(arr.shape[0]):
        vals = arr[i][finite_each[i]]
        if vals.size == 0:
            band_rows.append({"band": i + 1, "empty": True})
            continue
        any_nonzero |= bool(np.any(vals != 0.0))
        band_rows.append(
            {
                "band": i + 1,
                "min": float(vals.min()),
                "p01": float(np.percentile(vals, 1)),
                "p50": float(np.percentile(vals, 50)),
                "p99": float(np.percentile(vals, 99)),
                "max": float(vals.max()),
                "constant": bool(vals.std() == 0.0),
            }
        )
        if vals.std() == 0.0:
            out["constant"] = True
    out["band_stats"] = band_rows
    out["all_nan"] = all(b.get("empty", False) for b in band_rows)
    out["all_zero"] = (not out["all_nan"]) and not any_nonzero
    if "valid" in paths:
        with rasterio.open(paths["valid"]) as ds:
            valid = ds.read(1)
        out["valid_fraction"] = float((valid == 1).mean())
    if sensor == "sentinel1":
        out["floor_area_fraction"] = float(gate_rec.get("floor_area_fraction", -1.0))
        out["dualpol_finite_fraction"] = float(gate_rec.get("dualpol_finite_fraction", -1.0))
        props = mf.get("processing_config", {}).get("properties", {})
        out["gee_pass"] = props.get("orbitProperties_pass")
        out["variant"] = str(mf.get("variant"))
        out["n_scene_ids"] = len(mf.get("source_scene_ids", []))
    return out


# ---------------------------------------------------------------------------
# contact sheets
# ---------------------------------------------------------------------------


def _thumb(mf: dict[str, Any], target: int = 200) -> np.ndarray[Any, Any]:
    paths = Q2._paths(mf)  # noqa: SLF001
    sensor = str(mf["sensor"])
    if sensor.startswith("landsat") or sensor == "sentinel2":
        hdr = Q2.QA1._header(paths["sr"])  # noqa: SLF001
        names = hdr["descriptions"]
        idx = [names.index(n) for n in Q2.QA1.RGB_BANDS[sensor]]
        with rasterio.open(paths["sr"]) as ds:
            arr = ds.read().astype("float64")
            dsmask = ds.dataset_mask() > 0
        rgb = np.dstack(
            [
                Q2.QA1._stretch(
                    arr[i],  # noqa: SLF001
                    dsmask & np.isfinite(arr[i]),
                )
                for i in idx
            ]
        )
    else:
        with rasterio.open(paths["vvvh"]) as ds:
            vv = ds.read(1).astype("float64")
            vh = ds.read(2).astype("float64")
            dsmask = ds.dataset_mask() > 0
        fv, fh = dsmask & np.isfinite(vv), dsmask & np.isfinite(vh)
        rgb = np.dstack(
            [
                Q2.QA1._stretch(vv, fv),  # noqa: SLF001
                Q2.QA1._stretch(vh, fh),  # noqa: SLF001
                (
                    Q2.QA1._stretch(vv, fv)  # noqa: SLF001
                    + Q2.QA1._stretch(vh, fh)
                )
                / 2.0,
            ]
        )
    step = max(1, int(np.ceil(max(rgb.shape) / target)))
    return rgb[::step, ::step]


def contact_sheet(products: list[dict[str, Any]], sensor: str, picked: list[str]) -> str:
    cols = 4
    rows = int(np.ceil(len(picked) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.0 * cols, 3.6 * rows))
    axes = np.atleast_1d(axes).ravel()
    by_id = {p["product_id"]: p for p in products}
    for ax, pid in zip(axes, picked, strict=False):
        mf = json.loads((MANIFEST_DIR / f"{pid}.json").read_text())
        ax.imshow(_thumb(mf), interpolation="nearest")
        verdict = by_id[pid]["verdict"]
        color = {"PASS": "green", "WARN": "orange", "FAIL": "red"}.get(verdict, "gray")
        ax.set_title(f"{pid}\n{verdict}", fontsize=7, color=color)
        ax.set_xticks([])
        ax.set_yticks([])
    for ax in axes[len(picked) :]:
        ax.axis("off")
    fig.suptitle(f"Issue #19 V2 Phase I contact sheet: {sensor}")
    fig.tight_layout()
    out = SHEET_DIR / f"contact_v2_{sensor}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return str(out)


def _pick(group: list[dict[str, Any]]) -> list[str]:
    bad = sorted(p["product_id"] for p in group if p["verdict"] in (WARN, FAIL))
    rest = sorted(p["product_id"] for p in group if p["verdict"] == PASS)
    return (bad + rest)[:SHEET_N]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-live", action="store_true")
    ap.add_argument(
        "--allow-partial",
        action="store_true",
        help="do not FAIL when some eligible products are " "unlanded (debug only)",
    )
    ap.add_argument(
        "--out", type=Path, default=OUT_JSON, help="tracked slim summary manifest (Git-friendly)"
    )
    ap.add_argument("--out-csv", type=Path, default=OUT_CSV)
    ap.add_argument(
        "--out-full",
        type=Path,
        default=OUT_FULL_JSON,
        help="full diagnostic artifact with dimension details " "and per-band stats (outside Git)",
    )
    args = ap.parse_args()

    scope = {
        str(r["product_id"]): r
        for r in DRIVER.load_scope(canary=False, only_sensor=None, plan_version="v2")
    }
    plan_checksum = DRIVER.plan_csv_sha256("v2")
    supersession = json.loads(Q2.SUPERSESSION_INDEX.read_text("utf-8"))  # noqa: SLF001
    panel = {str(cid): row for cid, row in DRIVER.load_panel().iterrows()}
    supports = pd.read_csv(Q2.SUPPORTS_CSV)  # noqa: SLF001

    ee: Any | None = None
    if not args.no_live:
        Q2.initialize()  # noqa: SLF001
        import ee as _ee  # noqa: PLC0415

        ee = _ee

    products: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for pid in sorted(scope):
        mf_path = MANIFEST_DIR / f"{pid}.json"
        if not mf_path.exists():
            rejected.append(verify_rejected_slot(scope[pid]))
            continue
        mf = json.loads(mf_path.read_text())
        plan_row = scope[pid]
        shim = SimpleNamespace(v2_change=str(plan_row.get("v2_change")))
        live = ee if (not args.no_live and live_eligible(pid)) else None
        dims = Q2.run_product(  # noqa: SLF001
            mf,
            plan_row,
            shim,
            panel[str(mf["cell_id"])],
            supports,
            live,
            plan_checksum,
            supersession,
        )
        verdict = verdict_ignoring_skipped(dims)
        scan = pixel_scan(mf)
        products.append(
            {
                "product_id": pid,
                "cell_id": str(mf["cell_id"]),
                "sensor": str(mf["sensor"]),
                "year": int(mf["year"]),
                "variant": str(mf.get("variant")),
                "region_province": str(mf.get("region_province")),
                "v2_change": scan["v2_change"],
                "coverage_tier": str(mf.get("coverage_tier")),
                "verdict": verdict,
                "live_cross_checked": live is not None,
                "actual_observed_fraction": scan["actual_observed_fraction"],
                "pixel_scan": scan,
                "n_bytes": int(mf.get("n_bytes", 0)),
                "dimensions": [d.to_dict() for d in dims],
            }
        )
        print(
            f"[{pid}] {verdict} actual={scan['actual_observed_fraction']:.4f}"
            + (" LIVE" if live is not None else ""),
            flush=True,
        )

    # Flat table + aggregates.
    df = pd.DataFrame(
        [
            {
                "product_id": p["product_id"],
                "sensor": p["sensor"],
                "year": p["year"],
                "variant": p["variant"],
                "region_province": p["region_province"],
                "v2_change": p["v2_change"],
                "verdict": p["verdict"],
                "live": p["live_cross_checked"],
                "actual_observed_fraction": p["actual_observed_fraction"],
                "finite_fraction": p["pixel_scan"]["finite_fraction"],
                "valid_fraction": p["pixel_scan"].get("valid_fraction"),
                "floor_area_fraction": p["pixel_scan"].get("floor_area_fraction"),
                "all_nan": p["pixel_scan"]["all_nan"],
                "all_zero": p["pixel_scan"]["all_zero"],
                "constant": p["pixel_scan"]["constant"],
                "n_bytes": p["n_bytes"],
            }
            for p in products
        ]
    )
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out_csv, index=False)

    aggregates: dict[str, Any] = {}
    for key in ("sensor", "year", "region_province", "v2_change"):
        aggregates[key] = {}
        if df.empty:
            continue
        for val, grp in df.groupby(key, dropna=False):
            aggregates[key][str(val)] = {
                "n": int(len(grp)),
                "verdicts": grp["verdict"].value_counts().to_dict(),
                "actual_coverage_min": float(grp["actual_observed_fraction"].min()),
                "actual_coverage_mean": float(grp["actual_observed_fraction"].mean()),
                "all_nan": int(grp["all_nan"].sum()),
                "all_zero": int(grp["all_zero"].sum()),
                "constant": int(grp["constant"].sum()),
                "total_bytes": int(grp["n_bytes"].sum()),
            }

    # Physical ranges per sensor band across the pilot.
    physical: dict[str, Any] = {}
    for p in products:
        sensor = p["sensor"]
        physical.setdefault(sensor, {})
        for b in p["pixel_scan"]["band_stats"]:
            if b.get("empty"):
                continue
            name = str(b["band"])
            rec = physical[sensor].setdefault(
                name, {"min": [], "p01": [], "p50": [], "p99": [], "max": []}
            )
            for k in rec:
                rec[k].append(float(b[k]))
    physical_summary: dict[str, Any] = {}
    for sensor, bands in physical.items():
        sensor_summary: dict[str, Any] = {}
        for name, stat in bands.items():
            sensor_summary[name] = {f"min_of_{k}": float(min(v)) for k, v in stat.items()}
            for k, v in stat.items():
                sensor_summary[name][f"mean_of_{k}"] = float(np.mean(v))
                sensor_summary[name][f"max_of_{k}"] = float(max(v))
        physical_summary[sensor] = sensor_summary

    # Cross-product checks: duplicate bytes, pass/orbit, grid/alignment.
    seen_sha: dict[tuple[str, str], str] = {}
    duplicate_bytes: list[dict[str, str]] = []
    pass_orbit_violations: list[str] = []
    grid_residual_fail: list[str] = []
    label_alignment_warn_fail: list[dict[str, str]] = []
    s1_floors: list[dict[str, Any]] = []
    for p in products:
        mf = json.loads((MANIFEST_DIR / f"{p['product_id']}.json").read_text())
        for f in mf["landed_files"]:
            if f.get("derivation"):
                continue
            sha_key = (str(f["role"]), str(f["sha256"]))
            if sha_key in seen_sha:
                duplicate_bytes.append(
                    {
                        "role": str(f["role"]),
                        "sha256": str(f["sha256"]),
                        "product_a": seen_sha[sha_key],
                        "product_b": p["product_id"],
                    }
                )
            else:
                seen_sha[sha_key] = p["product_id"]
        if p["sensor"] == "sentinel1":
            scan = p["pixel_scan"]
            s1_floors.append(
                {
                    "product_id": p["product_id"],
                    "variant": scan["variant"],
                    "gee_pass": scan["gee_pass"],
                    "floor_area_fraction": scan["floor_area_fraction"],
                }
            )
            expect = "ASCENDING" if scan["variant"] == "A" else "DESCENDING"
            if scan["n_scene_ids"] != 1 or scan["gee_pass"] != expect:
                pass_orbit_violations.append(
                    f"{p['product_id']}: variant {scan['variant']} pass "
                    f"{scan['gee_pass']} n_scenes={scan['n_scene_ids']}"
                )
        dims_by_name = {d["name"]: d for d in p["dimensions"]}
        ig = dims_by_name.get("independent_grid_rebuild")
        if ig is not None and ig["verdict"] == FAIL:
            grid_residual_fail.append(p["product_id"])
        la = dims_by_name.get("label_adapter_alignment")
        if la is not None and la["verdict"] in (WARN, FAIL):
            label_alignment_warn_fail.append(
                {"product_id": p["product_id"], "verdict": la["verdict"], "note": la["note"]}
            )

    s1_floor_fracs = [f["floor_area_fraction"] for f in s1_floors]
    s1_floor_summary = {
        "n_s1_products": len(s1_floors),
        "floor_fraction_max": (max(s1_floor_fracs) if s1_floor_fracs else None),
        "floor_fraction_mean": (float(np.mean(s1_floor_fracs)) if s1_floor_fracs else None),
        "products_with_floor_pixels": [f for f in s1_floors if f["floor_area_fraction"] > 0],
        "pass_orbit_violations": pass_orbit_violations,
    }

    cross_checks = {
        "duplicate_bytes": duplicate_bytes,
        "s1_pass_orbit": s1_floor_summary,
        "independent_grid_failures": grid_residual_fail,
        "label_alignment_warn_fail": label_alignment_warn_fail,
    }

    sheets: dict[str, str] = {}
    for sensor in sorted({p["sensor"] for p in products}):
        group = [p for p in products if p["sensor"] == sensor]
        if group:
            sheets[sensor] = contact_sheet(products, sensor, _pick(group))

    product_gate = worst([p["verdict"] for p in products]) if products else FAIL
    confirmed = [r for r in rejected if r["status"] == "CONFIRMED_ACTUAL_MASK_REJECTION"]
    contradictions = [r for r in rejected if r["status"] == "REJECTION_CONTRADICTED_BY_BYTES"]
    unresolved = [r for r in rejected if r["status"] == "UNRESOLVED_NO_BYTES"]
    complete = not unresolved
    completeness = "PASS" if complete else ("WARN" if args.allow_partial else "FAIL")
    gate = worst([product_gate, completeness, FAIL if contradictions else PASS])
    print(
        f"[rejected] {len(confirmed)} confirmed actual-mask rejections, "
        f"{len(contradictions)} contradicted by bytes, "
        f"{len(unresolved)} unresolved",
        flush=True,
    )
    report = {
        "schema": "spartina_pilot19_pilot_qa_v2",
        "issue": "#19",
        "selection_revision": DRIVER.SELECTION_V2,
        "created_utc": _now(),
        "live_gee_subset_fraction": 0.0 if args.no_live else LIVE_FRACTION,
        "plan_v2_csv_sha256": plan_checksum,
        "n_products_eligible": len(scope),
        "n_products_landed": len(products),
        "n_unlanded": len(rejected),
        "actual_mask_rejections": {
            "confirmed": confirmed,
            "contradicted_by_bytes": contradictions,
            "unresolved_no_bytes": unresolved,
            "note": (
                "planned V2-eligible slots honestly excluded after "
                "actual landed bytes measured in-W10-cell coverage "
                "< 0.95; independently recomputed by QA, not trusted "
                "from the failure ledger; the count is never forced"
            ),
        },
        "completeness": completeness,
        "gate_verdict": gate,
        "verdict_counts": (df["verdict"].value_counts().to_dict() if not df.empty else {}),
        "total_landed_bytes": int(df["n_bytes"].sum()) if not df.empty else 0,
        "aggregates": aggregates,
        "physical_ranges": physical_summary,
        "cross_checks": cross_checks,
        "contact_sheets": sheets,
        "products": products,
    }
    args.out_full.parent.mkdir(parents=True, exist_ok=True)
    args.out_full.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    args.out.write_text(
        json.dumps(slim_report(report, args.out_full), indent=2, ensure_ascii=False)
    )
    print(
        f"PILOT_V2_QA_{gate}: {len(products)}/{len(scope)} products "
        f"({len(rejected)} unlanded: {len(confirmed)} confirmed actual-"
        f"mask rejections) -> {args.out} (full: {args.out_full})",
        flush=True,
    )
    return 0 if gate != FAIL else 2


if __name__ == "__main__":
    raise SystemExit(main())
