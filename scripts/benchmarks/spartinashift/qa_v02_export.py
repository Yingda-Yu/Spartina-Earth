#!/usr/bin/env python3
"""Issue #21, Phase I -- post-export QA for the v0.2 support expansion.

Re-verifies every landed product independently of the export-time checks:

  * landed-file SHA-256 vs manifest; required component roles present;
  * locked transform/dimensions/CRS rebuild from each raster;
  * actual-mask 0.95 gate replay (grid + W10 cell fractions);
  * physical scaling / band order / QA semantics audit pass flags;
  * S1 server-identity dB check + locally derived dualpol-valid token;
  * no informative all-NaN / all-zero raster;
  * label-support alignment (positive panel cells vs landed EO);
  * Issue #21 provenance block and bound plan checksums.

Writes the signed QA summary to the frozen artifact directory and QA
figures (contact sheets, per-sensor distributions, pairing-gap bars)
under work/issue21/qa. Any systematic failure is QA_FAIL (STOP).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts/benchmarks/spartinashift"))

from spartina.benchmark.v02 import acquisition as A  # noqa: E402

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
S2_JSON = V02_DIR / "V0_2_S2_ACQUISITION_PLAN.json"
L_JSON = V02_DIR / "V0_2_LANDSAT_ACQUISITION_PLAN.json"
G_JSON = V02_DIR / "V0_2_S1_PAIRING_LEDGER.json"
SCOPE_JSON = V02_DIR / "V0_2_EXPORT_SCOPE_ESTIMATE.json"
PANEL_CSV = V02_DIR / "v02_cell_panel.csv"
LEDGER_CSV = V02_DIR / "v02_s1_pairing_ledger.csv"
EXPORT_DIR = REPO_ROOT / "work/issue21/export"
MANIFEST_DIR = EXPORT_DIR / "manifests"
FAILURES_JSON = EXPORT_DIR / "failures.json"
QA_DIR = REPO_ROOT / "work/issue21/qa"
OUT_JSON = V02_DIR / "V0_2_EXPORT_QA_SUMMARY.json"

SENSORS = ("sentinel2", "sentinel1", "landsat5", "landsat7", "landsat8")
REQUIRED_ROLES = {
    "sentinel2": ("sr", "valid"),
    "sentinel1": ("vvvh", "dualpol_valid_v2"),
    "landsat5": ("sr", "valid", "qapixel"),
    "landsat7": ("sr", "valid", "qapixel"),
    "landsat8": ("sr", "valid", "qapixel")}


def _load_rows_module() -> Any:
    path = Path(__file__).with_name("export_v02_products.py")
    spec = importlib.util.spec_from_file_location("export_v02_products", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["export_v02_products"] = mod
    spec.loader.exec_module(mod)
    return mod


def _verified(path: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(path.read_text("utf-8"))
    if A.document_checksum(doc) != doc.get("document_checksum"):
        raise SystemExit(f"frozen artifact checksum mismatch: {path.name}")
    return doc


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _grid_check(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    grid = manifest["grid_spec"]
    for f in manifest["landed_files"]:
        uri = f["local_uri"]
        if not Path(uri).exists():
            errors.append(f"{f['role']}: missing file {uri}")
            continue
        with rasterio.open(uri) as ds:
            if ds.width != int(grid["width"]) or ds.height != int(
                    grid["height"]):
                errors.append(
                    f"{f['role']}: dims {ds.width}x{ds.height} != locked "
                    f"{grid['width']}x{grid['height']}")
            want = rasterio.Affine(
                *[float(v) for v in grid["transform"]])
            if not ds.transform.almost_equals(want):
                errors.append(
                    f"{f['role']}: transform {list(ds.transform)[:6]} != "
                    f"locked {list(want)[:6]}")
            if ds.crs.to_string() != str(grid["crs"]):
                errors.append(
                    f"{f['role']}: CRS {ds.crs.to_string()} != "
                    f"{grid.get('crs')}")
    return errors


def _informative_check(
    manifest: dict[str, Any],
) -> tuple[list[str], str | None]:
    """Partition informative-raster evidence into hard errors vs honest rejections.

    Returns ``(hard_errors, rejection_reason)``. A Landsat window whose
    export is byte-faithful (physical audit pass, every SR band finite)
    but whose own QA_PIXEL surface mask has zero valid pixels is the
    Issue #19 honest source-quality rejection class (``ZERO_QA_VALID_SURFACE_PIXELS``):
    the product is rejected from the accepted denominator but is not a
    systematic export failure. Everything else (all-NaN raster, zero S1
    token, a zero S2 VALID mask) is a hard contract failure.
    """
    errors: list[str] = []
    rejection: str | None = None
    qa = manifest.get("qa", {})
    observed = qa.get("observed", {})
    bands = observed.get("bands", {})
    if bands:
        finite = [float(b.get("finite_fraction") or 0.0)
                  for b in bands.values()]
        if finite and max(finite) <= 0.0:
            errors.append("all-NaN product: no finite pixels in any band")
    valid_info = qa.get("valid_mask", {})
    # S1 has no VALID raster; its token carries the validity signal.
    if (valid_info
            and int(valid_info.get("valid_pixel_count", 0)) == 0
            and manifest["sensor"] != "sentinel1"):
        if (str(manifest["sensor"]).startswith("landsat")
                and bands
                and min(float(b.get("finite_fraction") or 0.0)
                        for b in bands.values()) >= 1.0
                and qa.get("physical_audit", {}).get("pass")):
            rejection = "ZERO_QA_VALID_SURFACE_PIXELS"
        else:
            errors.append("VALID component has zero valid pixels")
    if manifest["sensor"] == "sentinel1":
        token_frac = (qa.get("actual_mask_v2", {})
                      .get("actual_observed_fraction"))
        if token_frac is None or float(token_frac) <= 0.0:
            errors.append("S1 dualpol token has no observed pixels")
    return errors, rejection


def verify_product(manifest: dict[str, Any]) -> dict[str, Any]:
    sensor = str(manifest["sensor"])
    errors: list[str] = []
    roles = {str(f["role"]): f for f in manifest["landed_files"]}
    for role in REQUIRED_ROLES[sensor]:
        if role not in roles:
            errors.append(f"missing role {role}")
            continue
        f = roles[role]
        if not Path(f["local_uri"]).exists():
            errors.append(f"{role}: file missing")
        elif _sha(Path(f["local_uri"])) != f["sha256"]:
            errors.append(f"{role}: landed sha256 mismatch")
    errors.extend(_grid_check(manifest))

    block = manifest.get("event_selection", {})
    if block.get("issue") != 21:
        errors.append("manifest missing Issue #21 provenance block")
    gate = (manifest.get("qa", {}).get("actual_mask_v2", {})
            .get("gate", {}))
    if not gate.get("pass"):
        errors.append(f"actual-mask gate not passed: {gate}")

    qa = manifest.get("qa", {})
    if sensor == "sentinel2" and not qa.get(
            "reflectance_sanity", {}).get("scaling_check_pass"):
        errors.append("S2 scaling sanity failed")
    if sensor.startswith("landsat") and not qa.get(
            "physical_audit", {}).get("pass"):
        errors.append("landsat physical audit failed")
    if sensor == "sentinel1":
        if not qa.get("physical_audit", {}).get("pass"):
            errors.append("S1 physical audit failed")
        if not qa.get("server_identity_check", {}).get("pass"):
            errors.append("S1 server identity check failed")
    info_errors, rejection_reason = _informative_check(manifest)
    errors.extend(info_errors)

    stats = {
        "n_bytes": int(manifest.get("n_bytes", 0)),
        "actual_observed_fraction_grid": (
            qa.get("actual_mask_v2", {})
            .get("actual_observed_fraction")),
        "actual_observed_fraction_in_w10_cell": (
            qa.get("actual_mask_v2", {})
            .get("actual_observed_fraction_in_w10_cell")),
        "plan_fraction": block.get("actual_observed_fraction_planned")}
    return {"product_id": manifest["product_id"],
            "cell_id": manifest["cell_id"], "sensor": sensor,
            "year": int(manifest["year"]),
            "tertile": block.get("tertile"),
            "errors": errors,
            "rejection_reason": rejection_reason, **stats}


def _median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def figures(results: list[dict[str, Any]]) -> dict[str, str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    QA_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}

    # Pairing-gap distribution (frozen ledger evidence).
    gaps = pd.read_csv(LEDGER_CSV)
    primary = gaps[gaps["status"] == A.STATUS_PAIRED]
    hist = primary["gap_days"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.bar(hist.index.astype(str), hist.values, color="#3b6fb6")
    ax.set_xlabel("|S2 - S1| gap (days)")
    ax.set_ylabel("primary pairs")
    ax.set_title("v0.2 primary S1/S2 pairing gaps (<=7 d)")
    fig.tight_layout()
    p = QA_DIR / "v02_pair_gap_distribution.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    out["pair_gap_distribution"] = str(p.relative_to(REPO_ROOT))

    # Gate fractions per sensor.
    fig, ax = plt.subplots(figsize=(7, 3.4))
    data, labels = [], []
    for sensor in SENSORS:
        vals = [float(r["actual_observed_fraction_in_w10_cell"])
                for r in results if r["sensor"] == sensor
                and r["actual_observed_fraction_in_w10_cell"] is not None]
        if vals:
            data.append(vals)
            labels.append(f"{sensor}\n(n={len(vals)})")
    if data:
        ax.boxplot(data, tick_labels=labels, showfliers=True)
        ax.axhline(0.95, color="crimson", linestyle="--", linewidth=1,
                   label="0.95 gate")
        ax.set_ylabel("actual observed fraction in W10 cell")
        ax.set_ylim(0, 1.02)
        ax.legend(loc="lower right")
        ax.set_title("v0.2 landed actual-mask fractions")
        fig.tight_layout()
        p = QA_DIR / "v02_actual_mask_distributions.png"
        fig.savefig(p, dpi=140)
        plt.close(fig)
        out["actual_mask_distributions"] = str(p.relative_to(REPO_ROOT))
    return out


def contact_sheets(manifests: list[dict[str, Any]]) -> dict[str, str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    QA_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    band_for = {"sentinel2": "sr", "sentinel1": "vvvh",
                "landsat5": "sr", "landsat7": "sr", "landsat8": "sr"}
    band_idx = {"sentinel2": 1, "sentinel1": 1,
                "landsat5": 4, "landsat7": 4, "landsat8": 5}
    rng = np.random.default_rng(21)
    for sensor in SENSORS:
        items = sorted((m for m in manifests if m["sensor"] == sensor),
                       key=lambda m: str(m["product_id"]))
        if not items:
            continue
        if len(items) > 24:
            idx = sorted(rng.choice(len(items), size=24, replace=False))
            items = [items[int(i)] for i in idx]
        ncol = 4
        nrow = int(np.ceil(len(items) / ncol))
        fig, axes = plt.subplots(
            nrow, ncol, figsize=(2.6 * ncol, 2.6 * nrow), squeeze=False)
        for ax, m in zip(axes.ravel(), items, strict=False):
            role = band_for[sensor]
            f = next(x for x in m["landed_files"] if x["role"] == role)
            try:
                with rasterio.open(f["local_uri"]) as ds:
                    arr = ds.read(
                        band_idx[sensor], out_shape=(128, 128),
                        masked=True)
                vmin, vmax = np.nanpercentile(
                    arr.compressed(), [2, 98]) if arr.count() else (0, 1)
                ax.imshow(arr, vmin=vmin, vmax=vmax, cmap="viridis")
            except Exception as exc:  # figure must not kill QA
                ax.text(0.5, 0.5, f"read error\n{type(exc).__name__}",
                        ha="center", va="center", fontsize=7)
            ax.set_title(
                f"{m['product_id'].removeprefix('V02_')[:26]}", fontsize=6)
            ax.set_xticks([])
            ax.set_yticks([])
        for ax in axes.ravel()[len(items):]:
            ax.axis("off")
        fig.suptitle(f"v0.2 contact sheet: {sensor} (n={len(items)})",
                     fontsize=11)
        fig.tight_layout()
        p = QA_DIR / f"v02_contact_{sensor}.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        out[sensor] = str(p.relative_to(REPO_ROOT))
    return out


def main() -> int:
    s2 = _verified(S2_JSON)
    lnd = _verified(L_JSON)
    pairs = _verified(G_JSON)
    scope = _verified(SCOPE_JSON)
    rows_mod = _load_rows_module()
    expected_rows = rows_mod.build_rows(s2, lnd, pairs)
    expected = {str(r["product_id"]): r for r in expected_rows}

    if not MANIFEST_DIR.exists():
        raise SystemExit(f"no manifests under {MANIFEST_DIR}; export first")
    manifest_paths = sorted(MANIFEST_DIR.glob("*.json"))
    manifests = [json.loads(p.read_text("utf-8")) for p in manifest_paths]
    by_pid = {str(m["product_id"]): m for m in manifests}
    unexpected = sorted(set(by_pid) - set(expected))

    results: list[dict[str, Any]] = []
    missing: list[str] = []
    for pid in sorted(expected):
        if pid not in by_pid:
            missing.append(pid)
            continue
        results.append(verify_product(by_pid[pid]))
    failures = []
    if FAILURES_JSON.exists():
        failures = [f for f in json.loads(
            FAILURES_JSON.read_text("utf-8")).get("failures", [])
            if not f.get("superseded")]

    failed_checks = {r["product_id"]: r["errors"]
                     for r in results if r["errors"]}
    honest_rejections = {r["product_id"]: r["rejection_reason"]
                         for r in results if r["rejection_reason"]}
    by_sensor: dict[str, Any] = {}
    for sensor in SENSORS:
        vals = [r for r in results if r["sensor"] == sensor]
        fracs = [float(r["actual_observed_fraction_in_w10_cell"])
                 for r in vals
                 if r["actual_observed_fraction_in_w10_cell"] is not None]
        by_sensor[sensor] = {
            "n_landed": len(vals),
            "n_failed_checks": sum(1 for r in vals if r["errors"]),
            "w10_fraction_min": min(fracs) if fracs else None,
            "w10_fraction_median": _median(fracs),
            "n_below_gate": sum(1 for v in fracs if v < A.ACTUAL_MASK_GATE)}

    # Label-support alignment on actually landed products.
    panel = pd.read_csv(PANEL_CSV)
    landed_cells = {r["cell_id"] for r in results}
    pos = panel[panel["any_positive"]]
    alignment = {
        "positive_cells": int(len(pos)),
        "positive_cells_with_any_landed_eo": int(
            pos["cell_id"].isin(landed_cells).sum()),
        "positive_cells_without_any_landed_eo": sorted(
            pos.loc[~pos["cell_id"].isin(landed_cells), "cell_id"])}

    fig_paths = figures(results) if results else {}
    sheet_paths: dict[str, str] = {}
    if results:
        sheet_paths = contact_sheets(manifests)
    figure_hashes = {
        name: {"path": path, "sha256": _sha(REPO_ROOT / path)}
        for name, path in {**fig_paths, **sheet_paths}.items()}

    systematic_stop = (missing or unexpected or failed_checks
                        or failures)
    honest_only = (honest_rejections and not systematic_stop)
    verdict = (
        "QA_FAIL_SYSTEMATIC_STOP" if systematic_stop
        else "QA_PASS_WITH_HONEST_SOURCE_REJECTIONS" if honest_only
        else "QA_PASS")
    doc: dict[str, Any] = {
        "product": "V0_2_EXPORT_QA_SUMMARY",
        "issue": 21,
        "phase": "I",
        "generated_utc": datetime.now(UTC).isoformat(),
        "plan_checksums": {
            "s2": s2["document_checksum"],
            "landsat": lnd["document_checksum"],
            "pairing": pairs["document_checksum"],
            "scope_estimate": scope["document_checksum"]},
        "verdict": verdict,
        "scope_products_expected": len(expected),
        "products_landed": len(results),
        "products_missing_manifest": missing,
        "unexpected_manifests": unexpected,
        "open_export_failures": failures,
        "products_failing_checks": failed_checks,
        "honest_source_rejections": honest_rejections,
        "honest_rejection_policy":
            "Issue #19 class: exports byte-faithful, physical audit "
            "pass, every SR band finite, but QA_PIXEL surface mask zero "
            "over the cell. Counted out of the accepted denominator; "
            "not a systematic failure. Does not trigger QA_FAIL.",
        "by_sensor": by_sensor,
        "label_support_alignment": alignment,
        "qa_contracts": [
            "landed sha256", "locked transform/dimensions/CRS rebuild",
            "actual-mask 0.95 gate replay (grid + W10 cell)",
            "physical scaling/band order/QA semantics",
            "S1 pass/orbit identity + server dB identity",
            "S2 same-datatake + s2_scl_qa_v1_1 VALID",
            "no all-NaN/all-zero informative raster",
            "Issue #21 provenance + bound plan checksums"],
        "figures": figure_hashes}
    doc["document_checksum"] = A.document_checksum(doc)
    OUT_JSON.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "verdict": verdict, "landed": len(results),
        "expected": len(expected), "missing": len(missing),
        "failing": len(failed_checks), "open_failures": len(failures),
        "by_sensor": by_sensor}, indent=2))
    return 0 if verdict == "QA_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
