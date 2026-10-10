#!/usr/bin/env python3
"""Issue #19 V2 recovery canary Phase H/I QA gate.

Runs AFTER the four PILOT_EVENT_SELECTION_V2 recovery-canary products
have landed (one previously-empty S2, one previously-partial S1, one
normal KEPT S2, one normal KEPT S1). Every dimension emits an explicit
PASS / WARN / FAIL / SKIPPED; any FAIL is a hard stop
(V2_RECOVERY_CANARY_FAIL) and no further pilot export is allowed.

The frozen V1 dimensions (independent grid rebuild, component grids,
label-adapter alignment, coastline, sensor physics with LIVE GEE
cross-checks, quicklooks) are reused unchanged from
``pilot19_canary_qa.py``. V2 adds the owner-mandated gate dimensions:

* ``actual_mask_v2_gate``   -- production eligibility is the ACTUAL
  raster mask over the locked W10 grid (S2: all four SR bands finite;
  S1: the s1_dualpol_valid_v2 token), independently recomputed here and
  cross-checked pixel-against-record, >= 0.95 over the full grid and
  inside the W10 cell;
* ``interior_nan_scan``      -- no systematic interior non-observation
  (eroded-interior fraction + largest interior hole component);
* ``s1_extreme_floor_token`` -- token is a pixel-exact local derivation
  (finite VV AND finite VH AND VV > -70 dB AND VH > -70 dB), uint8 on
  the copied grid, and the RAW identity bytes are provably untouched;
  <= -70 dB populations are quantified and edge-associated;
* ``repair_provenance``      -- KEPT raw SHA-256 equal the archived V0
  manifest records; REPLACED slots have r2 bytes/events and their V0
  manifests+bytes sit in the move-not-delete supersession archive with
  verified hashes; event_selection blocks match the frozen V2 plan.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts/data/national"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
from scipy import ndimage  # noqa: E402

from spartina.data.gee.auth import initialize  # noqa: E402
from spartina.data.gee.provenance import git_context, runtime_environment  # noqa: E402

CANARY_V2_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_canary_v2.csv"
MANIFEST_DIR = REPO_ROOT / "work/national/pilot19/manifests"
SUPERSEDED_MANIFEST_DIR = (
    REPO_ROOT / "work/national/pilot19/manifests_v1_superseded")
SUPERSEDED_PRODUCT_DIR = (
    REPO_ROOT / "work/national/pilot19/products_v1_superseded")
SUPERSESSION_INDEX = (
    REPO_ROOT / "work/national/pilot19/v1_v2_product_supersession_index.json")
SUPPORTS_CSV = (
    REPO_ROOT / "datasets/manifests/national_pilot19_label_supports_v1.csv")
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_canary_qa_v2.json"

ACTUAL_MASK_GATE = 0.95
INTERIOR_ERODE_PX = 3
INTERIOR_FAIL_FRAC = 1e-4
#: Any all-band interior hole at or above 1 ha is a structural FAIL
#: regardless of the window-wide coverage fraction (canary mandate:
#: "no systematic NaN interior"). Band-limited source-scene fill is
#: classified separately (see dim_interior_nan).
STRUCTURAL_HOLE_AREA_M2 = 10_000.0
FLOOR_EDGE_NEAR_PX = 3
FLOOR_INTERIOR_FAIL_FRAC = 1e-3
LIVE_DB_EXTREMA_TOL = 1.0
LIVE_DB_PCT_TOL = 0.6

PASS, WARN, FAIL, SKIPPED = "PASS", "WARN", "FAIL", "SKIPPED"
_RANK = {PASS: 0, WARN: 1, SKIPPED: 1, FAIL: 2}

CANARY_CASES_REQUIRED = {
    "previously_empty_s2", "previously_partial_s1",
    "normal_kept_s2", "normal_kept_s1"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def worst(verdicts: list[str]) -> str:
    return max(verdicts, key=lambda v: _RANK[v])


def _load_module(name: str, rel: str) -> Any:
    path = REPO_ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_DRIVER = _load_module("pilot19_export_driver",
                       "scripts/data/national/pilot19_export_products.py")
#: frozen V1 QA dimensions, reused (not modified)
QA1 = _load_module("pilot19_canary_qa_v1lib",
                   "scripts/data/national/pilot19_canary_qa.py")

#: Dimension type comes from the frozen V1 QA module (Any: that module is
#: loaded dynamically from scripts/, not imported as a package).
Dimension = Any


def _paths(mf: dict[str, Any]) -> dict[str, Path]:
    return {f["role"]: Path(f["local_uri"]) for f in mf["landed_files"]}


def _sha256(path: Path) -> str:
    return str(QA1._sha256(path))  # noqa: SLF001 -- frozen helper


@functools.lru_cache(maxsize=1)
def _v1_landed_pids() -> frozenset[str]:
    """Product slots that reached LANDED under the V1 run.

    Authoritative source is the frozen V1 export progress ledger
    (state re-validated against manifests + re-hashed bytes by the
    exporter). Only these slots may carry an archived V0 manifest.
    """
    doc = json.loads(_DRIVER.PROGRESS_JSON_V1.read_text("utf-8"))
    return frozenset(
        str(p["product_id"]) for p in doc.get("products", [])
        if str(p.get("state")) == "LANDED")


# ---------------------------------------------------------------------------
# manifest integrity (V2-aware: derived token has no GEE export task)
# ---------------------------------------------------------------------------

def dim_manifest_integrity_v2(mf: dict[str, Any]) -> Dimension:
    problems: list[str] = []
    files: list[dict[str, Any]] = []
    task_states = {t["role"]: t.get("state") for t in mf.get("export_tasks", [])}
    for f in mf["landed_files"]:
        p = Path(f["local_uri"])
        rec: dict[str, Any] = {"role": f["role"], "path": str(p)}
        if not p.exists():
            problems.append(f"{f['role']}: missing")
            rec["exists"] = False
            files.append(rec)
            continue
        rec["exists"] = True
        rec["size_bytes_manifest"] = int(f["size_bytes"])
        rec["size_bytes_actual"] = p.stat().st_size
        if p.stat().st_size != int(f["size_bytes"]):
            problems.append(
                f"{f['role']}: size {p.stat().st_size} != {f['size_bytes']}")
        digest = _sha256(p)
        rec["sha256_manifest"] = f["sha256"]
        rec["sha256_recomputed"] = digest
        if digest != f["sha256"]:
            problems.append(f"{f['role']}: sha256 mismatch")
        if not f.get("grid_verified"):
            problems.append(f"{f['role']}: grid_verified not set")
        der = f.get("derivation")
        if der:
            rec["derived_locally"] = bool(der.get("derived_locally"))
            rec["raw_values_modified"] = bool(der.get("raw_values_modified"))
            if not der.get("derived_locally"):
                problems.append(f"{f['role']}: derived file not flagged local")
            if der.get("raw_values_modified"):
                problems.append(f"{f['role']}: claims raw values modified")
            src_role = der.get("source_role")
            src_rec = next((x for x in mf["landed_files"]
                            if x["role"] == src_role), None)
            if src_rec is None:
                problems.append(f"{f['role']}: source role {src_role} missing")
            elif der.get("source_sha256") != src_rec["sha256"]:
                problems.append(
                    f"{f['role']}: derivation source sha256 does not match "
                    f"the landed {src_role} file")
            if der.get("token") != _DRIVER.S1_VALID_V2_TOKEN:
                problems.append(f"{f['role']}: unexpected validity token")
            # derived roles have no GEE export task by construction.
        elif task_states.get(f["role"]) != "COMPLETED":
            problems.append(
                f"{f['role']}: export task state "
                f"{task_states.get(f['role'])}")
        files.append(rec)
    if mf.get("schema") != _DRIVER.SCHEMA_V1:
        problems.append(f"schema {mf.get('schema')} != {_DRIVER.SCHEMA_V1}")
    return QA1.Dimension(
        "manifest_integrity", FAIL if problems else PASS,
        {"files": files, "task_states": task_states,
         "schema": mf.get("schema"),
         "n_bytes_manifest": int(mf.get("n_bytes", 0))},
        "; ".join(problems))


# ---------------------------------------------------------------------------
# V2 actual-mask gate
# ---------------------------------------------------------------------------

def _s2_observed(path: Path) -> tuple[np.ndarray[Any, Any], dict[str, float]]:
    with rasterio.open(path) as ds:
        total = int(ds.width * ds.height)
        observed = np.ones((ds.height, ds.width), dtype=bool)
        per_band: dict[str, float] = {}
        for i in range(1, ds.count + 1):
            fin = np.isfinite(ds.read(i))
            per_band[str(ds.descriptions[i - 1]) or f"band_{i}"] = (
                float(fin.sum()) / total)
            observed &= fin
    return observed, per_band


def _s1_dualpol(path: Path) -> dict[str, Any]:
    with rasterio.open(path) as ds:
        vv = ds.read(1).astype("float64")
        vh = ds.read(2).astype("float64")
    fin_vv = np.isfinite(vv)
    fin_vh = np.isfinite(vh)
    dual = fin_vv & fin_vh
    floor_vv = dual & (vv <= _DRIVER.S1_FLOOR_DB)
    floor_vh = dual & (vh <= _DRIVER.S1_FLOOR_DB)
    floor = floor_vv | floor_vh
    valid = dual & ~floor
    return {"vv": vv, "vh": vh, "fin_vv": fin_vv, "fin_vh": fin_vh,
            "dual": dual, "floor_vv": floor_vv, "floor_vh": floor_vh,
            "floor": floor, "valid": valid}


def dim_actual_mask_v2(
    mf: dict[str, Any], pixel_m: float, plan_row: dict[str, Any],
) -> Dimension:
    paths = _paths(mf)
    sensor = str(mf["sensor"])
    problems: list[str] = []
    detail: dict[str, Any] = {}
    is_landsat = sensor.startswith("landsat")
    if sensor == "sentinel1":
        d = _s1_dualpol(paths["vvvh"])
        observed = d["valid"]
        total = int(observed.size)
        n_obs = int(observed.sum())
        detail["dualpol_finite_fraction"] = float(d["dual"].mean())
        detail["floor_area_fraction"] = float(d["floor"].mean())
        basis = _DRIVER.BASIS_S1_V2
    else:
        # Same all-required-SR-bands-finite rule for S2 and inherited
        # Landsat windows.
        observed, per_band = _s2_observed(paths["sr"])
        detail["per_band_finite_fraction"] = per_band
        total = int(observed.size)
        n_obs = int(observed.sum())
        basis = (_DRIVER.BASIS_LANDSAT_INHERITED if is_landsat
                 else _DRIVER.BASIS_S2_V2)
    byte_fraction = n_obs / total
    # Independent inside-W10-cell fraction (the cell is the product unit).
    hdr = QA1._header(paths["sr"] if "sr" in paths else paths["vvvh"])
    inside = QA1.centre_in_cell(str(mf["cell_id"]), int(mf["utm_zone"]),
                                hdr, pixel_m)
    in_cell = float((observed & inside).sum() / max(int(inside.sum()), 1))
    detail.update({
        "coverage_basis": basis,
        "grid_pixels": total,
        "observed_pixels": n_obs,
        "actual_observed_fraction_grid": byte_fraction,
        "actual_observed_fraction_in_w10_cell": in_cell,
        "gate": ACTUAL_MASK_GATE,
        "independently_recomputed": True})
    warns: list[str] = []
    # Owner F1 eligibility is the in-W10-cell fraction. The covering
    # export grid over-covers the cell; a grid shortfall is evidence
    # (WARN) but not an eligibility failure.
    if byte_fraction < ACTUAL_MASK_GATE:
        warns.append(
            f"grid actual-mask fraction {byte_fraction:.4f} < "
            f"{ACTUAL_MASK_GATE} (in-cell {in_cell:.4f})")
    if in_cell < ACTUAL_MASK_GATE:
        problems.append(
            f"in-cell actual-mask fraction {in_cell:.4f} < "
            f"{ACTUAL_MASK_GATE}")
    n_cell = int(inside.sum())
    n_cell_obs = int((observed & inside).sum())
    # Cross-check the manifest's own landing-gate record pixel-for-pixel.
    rec = mf.get("qa", {}).get("actual_mask_v2", {})
    if not rec:
        problems.append("manifest missing qa.actual_mask_v2 record")
    else:
        if int(rec.get("grid_pixels", -1)) != total:
            problems.append(
                f"manifest grid_pixels {rec.get('grid_pixels')} != "
                f"recomputed {total}")
        # S2 records observed_pixels; S1 token records valid_pixels; the
        # inherited Landsat record carries the joint observed_pixels.
        count_key = ("valid_pixels" if sensor == "sentinel1"
                     else "observed_pixels")
        if int(rec.get(count_key, -1)) != n_obs:
            problems.append(
                f"manifest {count_key} {rec.get(count_key)} != "
                f"recomputed {n_obs}")
        # Owner F1 denominator: in-W10-cell counts on every refreshed
        # record (S2, S1 token, inherited Landsat).
        if int(rec.get("cell_pixels", -1)) != n_cell:
            problems.append("manifest cell_pixels != recomputed")
        if int(rec.get("observed_in_cell_pixels", -1)) != n_cell_obs:
            problems.append(
                "manifest observed_in_cell_pixels != recomputed")
        if abs(float(rec.get(
                "actual_observed_fraction_in_w10_cell", -1))
                - in_cell) > 1e-12:
            problems.append(
                "manifest in-cell fraction disagrees with bytes")
        if abs(float(rec.get("actual_observed_fraction", -1))
               - byte_fraction) > 1e-12:
            problems.append("manifest actual fraction disagrees with bytes")
        rec_bands = rec.get("per_band_finite_fraction", {})
        for band, frac in detail.get("per_band_finite_fraction", {}).items():
            if abs(float(rec_bands.get(band, -1)) - frac) > 1e-12:
                problems.append(
                    f"manifest per-band fraction {band} disagrees")
        gate = rec.get("gate", {})
        if not gate.get("gate_pass") or gate.get("pass") is False:
            problems.append("landing gate record not PASS")
        if gate.get("gate_status_conflict"):
            problems.append(
                "landing gate records a byte/plan gate-status conflict")
        plan_frac = plan_row.get("v2_actual_observed_fraction")
        if is_landsat:
            # Inherited rows carry no re-measured V2 plan fraction.
            if not gate.get("plan_agreement_pass"):
                problems.append("landing gate plan agreement not PASS")
        elif plan_frac is not None and str(plan_frac) != "":
            pf = float(plan_frac)
            gpf = gate.get("plan_v2_fraction")
            if gpf is None or abs(float(gpf) - pf) > 1e-12:
                problems.append(
                    "manifest plan fraction disagrees with frozen V2 plan")
            independent_conflict = (
                (in_cell >= ACTUAL_MASK_GATE) != (pf >= ACTUAL_MASK_GATE))
            if independent_conflict:
                problems.append(
                    "independent bytes vs V2 plan disagree on the 0.95 gate")
            elif not gate.get("plan_agreement_pass"):
                # Both sides pass; residual delta is the documented
                # fractional edge-mask reduceRegion artifact -> WARN.
                codes = ";".join(str(w.get("code")) for w in gate.get(
                    "crosscheck_warnings", []))
                warns.append(
                    f"plan proxy delta beyond pixel tolerance but both "
                    f"sides PASS the gate ({codes})")
        detail["manifest_gate"] = gate
    if problems:
        verdict = FAIL
    elif warns:
        verdict = WARN
    else:
        verdict = PASS
    note = "; ".join(problems + warns) or (
        f"actual-mask coverage {byte_fraction:.4f} grid / "
        f"{in_cell:.4f} in cell (gate {ACTUAL_MASK_GATE})")
    return QA1.Dimension("actual_mask_v2_gate", verdict, detail, note)


# ---------------------------------------------------------------------------
# interior NaN / hole morphology
# ---------------------------------------------------------------------------

def classify_interior_morphology(
    any_bad: np.ndarray[Any, Any],
    all_bad: np.ndarray[Any, Any],
    band_bad: list[np.ndarray[Any, Any]],
    band_names: list[str],
    inside_cell: np.ndarray[Any, Any],
    pixel_m: float,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Classify non-observation morphology on the W10-cell support.

    PILOT_EVENT_SELECTION_V2 defines eligibility over the exact W10
    Albers cell (pixel-centre rule), not the ~27% larger covering
    export window; the systematic-interior test uses the SAME support.
    Two physically distinct all-band populations are separated by
    connectivity:

    * **enclosed interior holes** -- connected non-observation
      components that do not touch the export-window border. These are
      genuine acquisition/geometry holes surrounded by observed data,
      i.e. the V1 failure mode this gate exists to catch. Any component
      >= STRUCTURAL_HOLE_AREA_M2 intersecting the cell, or a total
      in-cell hole fraction >= INTERIOR_FAIL_FRAC, is a hard FAIL;
    * **footprint/frame-edge slivers** -- components contiguous with the
      window border that intrude into the cell corner (S1 GRD frame
      edges, scene-footprint bites). They are edge geometry by
      construction: quantified (area, maximum penetration past the cell
      boundary) and reported as WARN, never counted as interior holes.

    Band-limited fill (some required bands non-finite while others carry
    signal; e.g. Landsat LaSRC aerosol-inversion fill) is reported
    separately as WARN. Window-margin (outside-cell) pixels are
    evidence only.
    """
    h, w = all_bad.shape
    problems: list[str] = []
    warns: list[str] = []

    # Legacy window-eroded statistics (evidence; the export window is
    # not the V2 scientific support).
    window_interior = np.zeros((h, w), dtype=bool)
    window_interior[INTERIOR_ERODE_PX:h - INTERIOR_ERODE_PX,
                    INTERIOR_ERODE_PX:w - INTERIOR_ERODE_PX] = True
    wi_any = window_interior & any_bad
    wi_all = window_interior & all_bad

    # W10-cell support.
    cell_all = inside_cell & all_bad
    cell_any = inside_cell & any_bad
    cell_limited = cell_any & ~all_bad
    cell_support = int(inside_cell.sum())
    cell_frac = float(cell_all.sum() / max(cell_support, 1))
    inside_eroded = ndimage.binary_erosion(
        inside_cell, iterations=INTERIOR_ERODE_PX)
    er_support = int(inside_eroded.sum())
    er_all = inside_eroded & all_bad
    cell_eroded_frac = float(er_all.sum() / max(er_support, 1))

    # Connected components; window-border-touching == footprint/frame.
    labelled, n_comp = ndimage.label(all_bad)
    border_labels = set(np.unique(np.concatenate(
        [labelled[0, :], labelled[-1, :],
         labelled[:, 0], labelled[:, -1]])).tolist()) - {0}
    sizes = np.bincount(labelled.ravel())
    in_cell_labels = np.unique(labelled[cell_all])
    in_cell_labels = in_cell_labels[in_cell_labels != 0]

    hole_labels = [int(i) for i in in_cell_labels if i not in border_labels]
    edge_labels_cell = [int(i) for i in in_cell_labels
                        if i in border_labels]
    hole_pixels_in_cell = int(sum(
        int(cell_all[labelled == i].sum()) for i in hole_labels))
    # Largest enclosed component is measured over its FULL extent: it is
    # surrounded by observed data, and any part inside the cell makes the
    # whole hole in-scope.
    largest_hole = max((int(sizes[i]) for i in hole_labels), default=0)
    largest_hole_area_m2 = largest_hole * pixel_m * pixel_m
    hole_frac_in_cell = float(
        hole_pixels_in_cell / max(cell_support, 1))

    edge_px = int(cell_all.sum() - sum(
        int(cell_all[labelled == i].sum()) for i in hole_labels))
    edge_area_m2 = edge_px * pixel_m * pixel_m
    edge_penetration_px = 0.0
    if edge_labels_cell:
        edge_mask = np.isin(labelled, edge_labels_cell) & inside_cell
        dist = ndimage.distance_transform_edt(inside_cell)
        edge_penetration_px = float(dist[edge_mask].max(initial=0.0))

    limited_by_band = {
        band_names[i]: int((cell_limited & band_bad[i]).sum())
        for i in range(len(band_bad))
        if bool((cell_limited & band_bad[i]).any())}

    detail = {
        "support": "W10_ALBERS_CELL_PIXEL_CENTRES",
        "interior_erode_px": INTERIOR_ERODE_PX,
        # legacy window evidence (kept for cross-revision comparison)
        "interior_pixels": int(window_interior.sum()),
        "interior_nonobserved_pixels": int(wi_any.sum()),
        "interior_nonobserved_fraction": float(
            wi_any.sum() / max(int(window_interior.sum()), 1)),
        "interior_all_band_pixels": int(wi_all.sum()),
        "interior_all_band_fraction": float(
            wi_all.sum() / max(int(window_interior.sum()), 1)),
        # W10-cell evidence
        "cell_pixels": cell_support,
        "cell_all_band_pixels": int(cell_all.sum()),
        "cell_all_band_fraction": cell_frac,
        "cell_eroded_pixels": er_support,
        "cell_eroded_all_band_pixels": int(er_all.sum()),
        "cell_eroded_all_band_fraction": cell_eroded_frac,
        "interior_hole_components": len(hole_labels),
        "interior_hole_pixels_in_cell": hole_pixels_in_cell,
        "interior_hole_fraction_in_cell": hole_frac_in_cell,
        "largest_interior_hole_pixels": largest_hole,
        "largest_interior_hole_area_m2": largest_hole_area_m2,
        "largest_interior_hole_fraction": largest_hole / float(h * w),
        "footprint_edge_components_in_cell": len(edge_labels_cell),
        "footprint_edge_pixels_in_cell": edge_px,
        "footprint_edge_area_m2_in_cell": edge_area_m2,
        "footprint_edge_fraction_in_cell": float(
            edge_px / max(cell_support, 1)),
        "footprint_edge_max_penetration_px": edge_penetration_px,
        "footprint_edge_max_penetration_m": edge_penetration_px * pixel_m,
        "window_margin_all_band_pixels": int((all_bad & ~inside_cell).sum()),
        "band_limited_pixels": int(cell_limited.sum()),
        "band_limited_by_band": limited_by_band,
        "n_components_total": int(n_comp)}

    if largest_hole_area_m2 >= STRUCTURAL_HOLE_AREA_M2:
        problems.append(
            f"structural enclosed interior hole {largest_hole} px "
            f"({largest_hole_area_m2:.0f} m^2) intersects the W10 cell, "
            f">= {STRUCTURAL_HOLE_AREA_M2:.0f} m^2")
    if hole_frac_in_cell >= INTERIOR_FAIL_FRAC:
        problems.append(
            f"systematic enclosed interior non-observation in W10 cell: "
            f"{hole_frac_in_cell:.6f} >= {INTERIOR_FAIL_FRAC}")
    if cell_limited.any():
        warns.append(
            f"{int(cell_limited.sum())} band-limited fill pixels in cell "
            f"(not all bands): {limited_by_band}")
    if edge_px:
        warns.append(
            f"{edge_px} frame/footprint-edge non-observation pixels "
            f"({edge_area_m2:.0f} m^2, {edge_px / max(cell_support, 1):.4%} "
            f"of cell; max penetration {edge_penetration_px * pixel_m:.0f} m) "
            "contiguous with the scene edge")
    if hole_pixels_in_cell and not problems:
        warns.append(
            f"{hole_pixels_in_cell} sporadic enclosed interior non-"
            "observed pixels below structural thresholds")
    return problems, warns, detail


def dim_interior_nan(mf: dict[str, Any]) -> Dimension:
    """Interior non-observation morphology over the W10-cell support.

    PILOT_EVENT_SELECTION_V2 defines the scientific support as the exact
    W10 Albers cell (pixel-centre rule), not the covering export window.
    Two physically distinct all-band populations are separated by
    connectivity by :func:`classify_interior_morphology`:

    * **enclosed interior holes** -- components not touching the window
      border; a hard FAIL above the structural-area / fraction thresholds
      (the V1 failure mode this gate exists to catch);
    * **frame/footprint-edge slivers** -- components contiguous with the
      window border intruding into the cell corner; quantified WARN
      evidence, never an interior hole.

    Band-limited fill (only some required bands non-finite; Landsat
    LaSRC aerosol-inversion fill) is WARN with morphology. Window-margin
    pixels outside the cell are evidence only.
    """
    paths = _paths(mf)
    sensor = str(mf["sensor"])
    band_bad: list[np.ndarray[Any, Any]] = []
    band_names: list[str] = []
    transform: Any
    zone: int
    if "sr" in paths:
        with rasterio.open(paths["sr"]) as ds:
            for i in range(1, ds.count + 1):
                b = ds.read(i)
                band_bad.append(~np.isfinite(b))
                band_names.append(str(ds.descriptions[i - 1]) or f"band_{i}")
            h, w = ds.height, ds.width
            transform = ds.transform
            zone = int(ds.crs.to_epsg()) - 32600
    else:
        d = _s1_dualpol(paths["vvvh"])
        with rasterio.open(paths["vvvh"]) as ds:
            transform = ds.transform
            zone = int(ds.crs.to_epsg()) - 32600
        pol_bad = (~d["fin_vv"]) | (d["vv"] <= _DRIVER.S1_FLOOR_DB)
        pol_bad_h = (~d["fin_vh"]) | (d["vh"] <= _DRIVER.S1_FLOOR_DB)
        band_bad = [pol_bad, pol_bad_h]
        band_names = ["VV", "VH"]
        h, w = pol_bad.shape
    any_bad = np.logical_or.reduce(band_bad)
    all_bad = np.logical_and.reduce(band_bad)
    pixel_m = 30.0 if sensor.startswith("landsat") else 10.0

    from build_pilot_label_supports_v1 import (  # noqa: PLC0415
        cell_polygon_utm,
        pixel_centres_in_cell,
    )

    cell_poly = cell_polygon_utm(str(mf["cell_id"]), zone)
    inside_cell = pixel_centres_in_cell(
        cell_poly, transform, h, w, int(pixel_m))

    problems, warns, detail = classify_interior_morphology(
        any_bad, all_bad, band_bad, band_names, inside_cell, pixel_m)

    # Frozen r2 rule: the derived VALID token must never mark a
    # non-observed pixel valid (window-wide check, stricter than cell).
    if "valid" in paths:
        with rasterio.open(paths["valid"]) as ds:
            valid = ds.read(1) == 1
        wi = np.zeros((h, w), dtype=bool)
        wi[INTERIOR_ERODE_PX:h - INTERIOR_ERODE_PX,
           INTERIOR_ERODE_PX:w - INTERIOR_ERODE_PX] = True
        valid_overlap = int((wi & any_bad & valid).sum())
        detail["interior_nonobserved_marked_valid"] = valid_overlap
        if valid_overlap:
            problems.append(
                f"{valid_overlap} interior non-observed pixels marked "
                "VALID (r2 exclusion violated)")
    else:
        detail["interior_nonobserved_marked_valid"] = None

    if problems:
        verdict = FAIL
        note = "; ".join(problems + warns)
    elif warns:
        verdict = WARN
        note = "; ".join(warns)
    else:
        verdict = PASS
        note = "no interior non-observed pixels in W10 cell"
    return QA1.Dimension("interior_nan_scan", verdict, detail, note)


# ---------------------------------------------------------------------------
# S1 extreme-floor token (F3)
# ---------------------------------------------------------------------------

def dim_s1_floor_token(mf: dict[str, Any]) -> Dimension:
    paths = _paths(mf)
    problems: list[str] = []
    warns: list[str] = []
    tok_rec = next((f for f in mf["landed_files"]
                    if f["role"] == _DRIVER.S1_VALID_V2_ROLE), None)
    if tok_rec is None:
        return QA1.Dimension(
            "s1_extreme_floor_token", FAIL,
            {}, "manifest missing dualpol_valid_v2 derived file")
    tok_path = paths[_DRIVER.S1_VALID_V2_ROLE]
    vvvh_path = paths["vvvh"]
    d = _s1_dualpol(vvvh_path)
    with rasterio.open(tok_path) as ds:
        tok = ds.read(1)
        tok_hdr = QA1._header(tok_path)
    raw_hdr = QA1._header(vvvh_path)
    if tok_hdr["dtypes"] != ["uint8"] or tok_hdr["count"] != 1:
        problems.append("token must be single-band uint8")
    if tok_hdr["descriptions"] != ["S1_DUALPOL_VALID_V2"]:
        problems.append(f"token band description {tok_hdr['descriptions']}")
    for key in ("crs_epsg", "transform", "width", "height"):
        if tok_hdr[key] != raw_hdr[key]:
            problems.append(f"token {key} differs from raw vvvh grid")
    if not np.array_equal(tok.astype(bool), d["valid"]):
        problems.append(
            "token bytes != independent recomputation "
            "(finite VV & finite VH & VV>-70 & VH>-70)")
    # <= -70 dB distribution and edge association.
    floor = d["floor"]
    n = int(floor.size)
    border_bg = np.zeros_like(floor)
    border_bg[1:-1, 1:-1] = True
    dist_border = ndimage.distance_transform_edt(
        border_bg, return_distances=True)
    # distance to footprint edge: distance through finite pixels to a
    # non-finite pixel (0 where non-finite).
    dist_fp = ndimage.distance_transform_edt(d["dual"],
                                             return_distances=True)
    interior = np.zeros_like(floor)
    interior[FLOOR_EDGE_NEAR_PX:-FLOOR_EDGE_NEAR_PX,
             FLOOR_EDGE_NEAR_PX:-FLOOR_EDGE_NEAR_PX] = True
    if floor.any():
        near = ((dist_border <= FLOOR_EDGE_NEAR_PX)
                | (dist_fp <= FLOOR_EDGE_NEAR_PX))
        edge_frac = float((floor & near).sum() / floor.sum())
        interior_floor_frac = float(
            (floor & interior).sum() / max(int(interior.sum()), 1))
        dists = np.asarray(dist_border[floor])
        dist_detail = {"min": float(dists.min()), "median": float(
            np.median(dists)), "max": float(dists.max())}
    else:
        edge_frac = None
        interior_floor_frac = 0.0
        dist_detail = None
    band_stats: dict[str, dict[str, float]] = {}
    for name, b, fin in (("VV", d["vv"], d["fin_vv"]),
                         ("VH", d["vh"], d["fin_vh"])):
        vals = b[fin]
        band_stats[name] = {
            "min": float(vals.min()),
            "p01": float(np.percentile(vals, 1)),
            "p50": float(np.percentile(vals, 50)),
            "p99": float(np.percentile(vals, 99)),
            "max": float(vals.max()),
            "fraction_le_minus70": float((vals <= _DRIVER.S1_FLOOR_DB)
                                         .mean())}
    if interior_floor_frac > FLOOR_INTERIOR_FAIL_FRAC:
        problems.append(
            f"<= -70 dB removes meaningful interior population: "
            f"{interior_floor_frac:.6f} of interior pixels -> STOP owner "
            "review per F3")
    detail = {
        "floor_rule_db": _DRIVER.S1_FLOOR_DB,
        "floor_semantics": "NON_OBSERVATION_EXTREME_FLOOR",
        "floor_pixels_vv": int(d["floor_vv"].sum()),
        "floor_pixels_vh": int(d["floor_vh"].sum()),
        "floor_pixels_either": int(floor.sum()),
        "floor_area_fraction": float(floor.sum() / n),
        "interior_floor_fraction": interior_floor_frac,
        "floor_edge_associated_fraction": edge_frac,
        "edge_near_px": FLOOR_EDGE_NEAR_PX,
        "floor_distance_to_border": dist_detail,
        "raw_band_statistics_db": band_stats,
        "token_pixel_identical_to_rule": bool(
            np.array_equal(tok.astype(bool), d["valid"])),
        "raw_values_modified": False}
    if floor.any() and edge_frac is not None and edge_frac < 0.99:
        warns.append(
            f"only {edge_frac:.4f} of <= -70 dB pixels within "
            f"{FLOOR_EDGE_NEAR_PX} px of footprint/border edge")
    note = "; ".join(problems + warns) or (
        f"token pixel-exact; floor area fraction "
        f"{detail['floor_area_fraction']:.6f}; raw identity bytes preserved")
    return QA1.Dimension(
        "s1_extreme_floor_token",
        FAIL if problems else (WARN if warns else PASS), detail, note)


# ---------------------------------------------------------------------------
# S1 identity/physics under F3 (no symmetric lower raw reject)
# ---------------------------------------------------------------------------

def qa_s1_v2(ee: Any | None, mf: dict[str, Any],
             plan_row: dict[str, Any]) -> list[Dimension]:
    paths = _paths(mf)
    hdr = QA1._header(paths["vvvh"])
    problems: list[str] = []
    if hdr["count"] != 2 or hdr["dtypes"] != ["float32", "float32"]:
        problems.append("must be 2x float32")
    if hdr["descriptions"] != ["VV", "VH"]:
        problems.append(f"band order {hdr['descriptions']}")
    d = _s1_dualpol(paths["vvvh"])
    stats: dict[str, dict[str, Any] | None] = {}
    for name, b, fin in (("VV", d["vv"], d["fin_vv"]),
                         ("VH", d["vh"], d["fin_vh"])):
        vals = b[fin]
        if not vals.size:
            stats[name] = None
            continue
        rec: dict[str, Any] = {
            k: float(v) for k, v in zip(
                ("min", "p01", "p50", "p99", "max"),
                np.percentile(vals, [0, 1, 50, 99, 100]),
                strict=True)}
        rec["std"] = float(vals.std())
        rec["finite_fraction"] = float(fin.mean())
        stats[name] = rec
    vv_stats = stats["VV"]
    vh_stats = stats["VH"]
    if vv_stats is None or vh_stats is None:
        problems.append("all-nodata VV/VH band in window")
    elif vv_stats["std"] <= 0 or vh_stats["std"] <= 0:
        problems.append("constant band")
    # Upper hard envelope only (F3); the low end is the validity token.
    n_above = 0
    tail_frac: dict[str, float] = {}
    for name, b, fin in (("VV", d["vv"], d["fin_vv"]),
                         ("VH", d["vh"], d["fin_vh"])):
        vals = b[fin]
        n_above += int((vals > _DRIVER.S1_DB_HARD_MAX).sum())
        tail = ((vals > _DRIVER.S1_FLOOR_DB)
                & (vals < _DRIVER.S1_DB_BULK_MIN)) | (
            vals > _DRIVER.S1_DB_BULK_MAX)
        tail_frac[name] = float(tail.mean()) if vals.size else 0.0
    if n_above:
        problems.append(
            f"{n_above} pixels above upper hard envelope "
            f"{_DRIVER.S1_DB_HARD_MAX} dB")
    if any(f > _DRIVER.S1_TAIL_OUTSIDE_BULK_HARD_FRACTION
           for f in tail_frac.values()):
        problems.append(f"physical tail fraction {tail_frac} exceeds "
                        f"{_DRIVER.S1_TAIL_OUTSIDE_BULK_HARD_FRACTION}")
    live: dict[str, Any] = {"attempted": ee is not None}
    if ee is not None:
        try:
            live_stats = QA1._live_s1_stats(ee, mf)  # noqa: SLF001
            checks: dict[str, bool] = {}
            deltas: dict[str, float] = {}
            for band in ("VV", "VH"):
                bstats = stats[band]
                if bstats is None:
                    checks[f"{band}_finite_pixels"] = False
                    problems.append(
                        f"live cross-check skipped: {band} no finite pixels")
                    continue
                for stat, tol in (("min", LIVE_DB_EXTREMA_TOL),
                                  ("max", LIVE_DB_EXTREMA_TOL),
                                  ("p01", LIVE_DB_PCT_TOL),
                                  ("p50", LIVE_DB_PCT_TOL),
                                  ("p99", LIVE_DB_PCT_TOL)):
                    dd = abs(float(bstats[stat])
                             - float(live_stats[band][stat]))
                    deltas[f"{band}_{stat}"] = round(dd, 4)
                    checks[f"{band}_{stat}"] = dd <= tol
            live = {"attempted": True, "server_stats": live_stats,
                    "abs_deltas": deltas, "checks": checks,
                    "pass": all(checks.values())}
            if not live["pass"]:
                problems.append(
                    f"live identity mismatch: "
                    f"{[k for k, ok in checks.items() if not ok]}")
        except Exception as exc:  # noqa: BLE001
            live = {"attempted": True, "error": str(exc)}
            problems.append(f"live S1 cross-check failed: {exc}")
    dims = [QA1.Dimension(
        "s1_identity_and_physics",
        FAIL if problems else (SKIPPED if ee is None else PASS),
        {"bands": stats, "above_hard_envelope_pixels": n_above,
         "physical_tail_fraction": tail_frac,
         "upper_hard_envelope_db": _DRIVER.S1_DB_HARD_MAX,
         "live": live,
         "transform": "IDENTITY_SELECT_ONLY_NO_10LOG10"},
        "; ".join(problems))]

    pass_problems: list[str] = []
    props = mf["processing_config"].get("properties", {})
    plan_pass = str(plan_row.get("orbit_pass") or "")
    plan_orbit = plan_row.get("relative_orbit")
    gee_pass = props.get("orbitProperties_pass")
    expect = {"ASC": "ASCENDING", "DESC": "DESCENDING"}.get(plan_pass)
    if expect is not None and gee_pass != expect:
        pass_problems.append(f"pass {gee_pass} != plan {plan_pass}")
    if plan_orbit is None or pd.isna(plan_orbit):
        plan_relative_orbit: int | None = None
    else:
        plan_relative_orbit = int(float(plan_orbit))
        if int(props.get("relativeOrbitNumber_start", -1)) \
                != plan_relative_orbit:
            pass_problems.append("relative orbit mismatch")
    pol = props.get("transmitterReceiverPolarisation")
    if sorted(pol or []) != ["VH", "VV"]:
        pass_problems.append(f"polarisation {pol}")
    dims.append(QA1.Dimension(
        "s1_pass_orbit_footprint", FAIL if pass_problems else PASS,
        {"plan_pass": plan_pass, "gee_pass": gee_pass,
         "plan_relative_orbit": plan_relative_orbit,
         "gee_relative_orbit": props.get("relativeOrbitNumber_start"),
         "polarisation": pol,
         "VV_finite_fraction": (vv_stats["finite_fraction"]
                                if vv_stats is not None else None),
         "VH_finite_fraction": (vh_stats["finite_fraction"]
                                if vh_stats is not None else None),
         "coverage_tier": mf.get("coverage_tier")},
        "; ".join(pass_problems)))
    dims.append(QA1.Dimension(
        "measured_lzw_compression", PASS,
        {"components": QA1.compression_records(mf)}, ""))
    return dims


# ---------------------------------------------------------------------------
# repair provenance: archive integrity + KEPT byte preservation
# ---------------------------------------------------------------------------

def dim_repair_provenance(
    mf: dict[str, Any], plan_row: dict[str, Any],
    canary_v2_change: str, plan_checksum: str,
    supersession: dict[str, Any],
) -> Dimension:
    problems: list[str] = []
    detail: dict[str, Any] = {}
    change = str(plan_row.get("v2_change"))
    is_landsat = str(mf["sensor"]).startswith("landsat")
    es = mf.get("event_selection", {})
    want_revision = (_DRIVER.SELECTION_V1_LANDSAT_INHERITED if is_landsat
                     else _DRIVER.SELECTION_V2)
    want_eligibility = ("SELECTED" if is_landsat
                        else _DRIVER.STATUS_V2_ELIGIBLE)
    planned_es = es.get("actual_observed_fraction_planned")
    plan_frac = plan_row.get("v2_actual_observed_fraction")
    plan_frac_null = plan_frac is None or (
        isinstance(plan_frac, float) and np.isnan(plan_frac))
    if planned_es is None or plan_frac_null:
        planned_check = planned_es is None and plan_frac_null
    else:
        assert plan_frac is not None
        planned_check = abs(float(planned_es) - float(plan_frac)) < 1e-12
    checks = {
        "selection_revision": es.get("revision") == want_revision,
        "plan_checksum": es.get("plan_csv_sha256") == plan_checksum,
        "eligibility": es.get("eligibility_status") == want_eligibility,
        "v2_change_matches_plan": es.get("v2_change") == change,
        "v2_change_matches_canary":
            es.get("v2_change") == canary_v2_change,
        "gate_0p95": es.get("actual_mask_gate") == ACTUAL_MASK_GATE,
        "label_independent": es.get("label_independent") is True,
        "threshold_relaxation_forbidden":
            es.get("threshold_relaxation_forbidden") is True,
        "planned_fraction_matches_plan": planned_check,
        "manifest_event_date_matches_v2_plan":
            str(mf.get("acquisition_utc_planned", ""))[:10]
            == str(plan_row.get("event_utc"))[:10],
    }
    detail["event_selection_checks"] = checks
    problems.extend(k for k, ok in checks.items() if not ok)
    pid = str(mf["product_id"])
    v1_landed = pid in _v1_landed_pids()
    detail["v1_landed"] = v1_landed
    archived_manifest = SUPERSEDED_MANIFEST_DIR / f"{pid}.json"
    if change not in (_DRIVER.CHANGE_KEPT, _DRIVER.CHANGE_REPLACED,
                      _DRIVER.CHANGE_LANDSAT):
        problems.append(f"unknown v2_change {change}")
    if v1_landed:
        # Slots that reached LANDED under V1 must have a move/copy of
        # their V0 manifest, with history verified against it.
        if not archived_manifest.exists():
            problems.append("archived V0 manifest copy missing")
        else:
            old = json.loads(archived_manifest.read_text("utf-8"))
            detail["archived_v0_schema"] = old.get("schema")
            old_sha = {f["role"]: f["sha256"] for f in old["landed_files"]}
            if change in (_DRIVER.CHANGE_KEPT, _DRIVER.CHANGE_LANDSAT):
                # Raw bytes must be byte-identical to the V0 record
                # (metadata-only enrichment; no resubmission). Applies to
                # KEPT sentinel events and inherited Landsat windows.
                kept: dict[str, bool] = {}
                for f in mf["landed_files"]:
                    if f.get("derivation"):
                        continue
                    kept[f["role"]] = old_sha.get(f["role"]) == f["sha256"]
                detail["kept_raw_sha_matches_v0"] = kept
                if not all(kept.values()):
                    problems.append("retained raw bytes differ from V0 SHA")
                if str(old.get("acquisition_utc_planned", ""))[:10] != str(
                        mf.get("acquisition_utc_planned", ""))[:10]:
                    problems.append("retained event date changed")
            elif change == _DRIVER.CHANGE_REPLACED:
                entry = supersession.get("products", {}).get(pid)
                if entry is None:
                    problems.append("supersession index entry missing")
                else:
                    archived_files: list[dict[str, Any]] = []
                    for rec in entry.get("archived_files", []):
                        ap = SUPERSEDED_PRODUCT_DIR / rec["name"]
                        ok = ap.exists() and _sha256(ap) == rec["sha256"]
                        archived_files.append(
                            {"name": rec["name"], "exists_and_sha_ok": ok})
                        if not ok:
                            problems.append(
                                f"archived byte {rec['name']} "
                                "missing/hash bad")
                    detail["archived_files"] = archived_files
                    detail["v1_event_utc"] = entry.get("v1_event_utc")
                    detail["v2_event_utc"] = entry.get("v2_event_utc")
                    if str(entry.get("v2_event_utc", ""))[:10] != str(
                            plan_row.get("event_utc"))[:10]:
                        problems.append("index v2 event != plan event")
    else:
        # D1 was halted mid-pilot: this slot was never LANDED under V1, so
        # no genuine V0 manifest/bytes can exist. The enrichment preflight
        # nevertheless copies each manifest aside before rewriting it, so
        # a slot first landed under V2 may carry a PRE-REFRESH V2 SNAPSHOT
        # in the archive folder. Discriminate by manifest content: a V2
        # snapshot already carries the V2 event-selection block / actual
        # mask record; a genuine V0 manifest does not.
        if archived_manifest.exists():
            old = json.loads(archived_manifest.read_text("utf-8"))
            old_rev = old.get("event_selection", {}).get("revision")
            is_v2_snapshot = (
                old.get("qa", {}).get("actual_mask_v2") is not None
                or old_rev == _DRIVER.SELECTION_V2
                or old_rev == _DRIVER.SELECTION_V1_LANDSAT_INHERITED)
            if not is_v2_snapshot:
                problems.append(
                    "archived genuine V0 manifest exists for a slot never "
                    "LANDED under V1")
            else:
                # Metadata-only V2 refresh: every current non-derived
                # component must be byte-identical to the snapshot and the
                # event date must not have moved.
                old_sha = {f["role"]: f["sha256"]
                           for f in old.get("landed_files", [])}
                same: dict[str, bool] = {}
                for f in mf["landed_files"]:
                    if f.get("derivation"):
                        continue
                    same[f["role"]] = old_sha.get(f["role"]) == f["sha256"]
                detail["v2_snapshot_sha_continuity"] = same
                if not same or not all(same.values()):
                    problems.append(
                        "pre-refresh V2 snapshot bytes differ from current")
                if str(old.get("acquisition_utc_planned", ""))[:10] != str(
                        mf.get("acquisition_utc_planned", ""))[:10]:
                    problems.append(
                        "pre-refresh V2 snapshot event date changed")
                detail["archived_manifest_class"] = "PRE_REFRESH_V2_SNAPSHOT"
        if change == _DRIVER.CHANGE_REPLACED:
            entry = supersession.get("products", {}).get(pid)
            if entry is None:
                problems.append("supersession index entry missing")
            elif entry.get("archived_manifest") is not None:
                problems.append(
                    "index claims archived V0 bytes for a never-landed "
                    "slot")
            else:
                detail["v2_event_utc"] = entry.get("v2_event_utc")
                if str(entry.get("v2_event_utc", ""))[:10] != str(
                        plan_row.get("event_utc"))[:10]:
                    problems.append("index v2 event != plan event")
    # Every component file must carry the plan-correct revision
    # (r1 retained / r2 replaced; derived tokens checked separately).
    for role in _DRIVER.COMPONENTS[str(mf["sensor"])]:
        expect_prefix = _DRIVER.prefix_for(
            plan_row, role, plan_version="v2")
        got = {Path(f["local_uri"]).name for f in mf["landed_files"]
               if f["role"] == role}
        if got != {f"{expect_prefix}.tif"}:
            problems.append(
                f"{role}: expected {expect_prefix}.tif, got {got}")
    detail["v2_change"] = change
    if problems:
        note = "; ".join(problems)
    elif v1_landed:
        note = f"{change}: V0 history preserved and verified"
    else:
        note = f"{change}: fresh V2 landing (slot never LANDED under V1)"
    return QA1.Dimension("repair_provenance", FAIL if problems else PASS,
                         detail, note)


# ---------------------------------------------------------------------------
# per-product runner
# ---------------------------------------------------------------------------

def run_product(
    mf: dict[str, Any], plan_row: dict[str, Any],
    canary_row: Any, panel_row: pd.Series, supports: pd.DataFrame,
    ee: Any | None, plan_checksum: str, supersession: dict[str, Any],
) -> list[Dimension]:
    sensor = str(mf["sensor"])
    pixel_m = 30.0 if sensor.startswith("landsat") else 10.0
    dims: list[Dimension] = [
        dim_manifest_integrity_v2(mf),
        QA1.dim_component_grids(mf),
        QA1.dim_independent_grid(mf, panel_row, pixel_m),
        QA1.dim_cell_coverage(mf, pixel_m),
    ]
    paths = _paths(mf)
    sr_role = "sr" if "sr" in paths else "vvvh"
    sr_hdr = QA1._header(paths[sr_role])
    eo_observed = QA1.observed_masks(
        paths[sr_role], sr_hdr["count"]).all(axis=0)
    eo_valid: np.ndarray[Any, Any] | None = None
    if "valid" in paths:
        with rasterio.open(paths["valid"]) as ds:
            eo_valid = ds.read(1) == 1
    dims.append(QA1.dim_label_alignment(mf, supports, eo_valid, eo_observed))
    dims.append(QA1.dim_coastline(mf, panel_row))
    if sensor.startswith("landsat"):
        dims.extend(QA1.qa_landsat(ee, mf))
    elif sensor == "sentinel2":
        dims.extend(QA1.qa_s2(ee, mf))
    else:
        dims.extend(qa_s1_v2(ee, mf, plan_row))
    dims.append(dim_actual_mask_v2(mf, pixel_m, plan_row))
    dims.append(dim_interior_nan(mf))
    if sensor == "sentinel1":
        dims.append(dim_s1_floor_token(mf))
    dims.append(dim_repair_provenance(
        mf, plan_row, str(canary_row.v2_change), plan_checksum,
        supersession))
    qpath = QA1.render_quicklook(mf, supports)
    dims.append(QA1.Dimension(
        "quicklook",
        PASS if qpath.exists() and qpath.stat().st_size > 0 else FAIL,
        {"path": str(qpath), "bytes": qpath.stat().st_size}))
    return dims


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-live", action="store_true",
                    help="skip live GEE cross-checks (not recommended)")
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    args = ap.parse_args()
    ee: Any | None = None
    if not args.no_live:
        initialize()
        import ee as _ee  # noqa: PLC0415

        ee = _ee

    canary = pd.read_csv(CANARY_V2_CSV)
    cases = set(canary["canary_case"].astype(str))
    case_verdict = PASS if cases == CANARY_CASES_REQUIRED else FAIL
    scope = {str(r["product_id"]): r
             for r in _DRIVER.load_scope(canary=True, only_sensor=None,
                                         plan_version="v2")}
    supports = pd.read_csv(SUPPORTS_CSV)
    panel_rows = _DRIVER.load_panel()
    panel = {str(cid): row for cid, row in panel_rows.iterrows()}
    plan_checksum = _DRIVER.plan_csv_sha256("v2")
    supersession = json.loads(SUPERSESSION_INDEX.read_text("utf-8"))

    products: list[dict[str, Any]] = []
    verdicts_all: list[str] = [case_verdict]
    for crow in canary.itertuples(index=False):
        pid = str(crow.product_id)
        mf_path = MANIFEST_DIR / f"{pid}.json"
        if not mf_path.exists():
            products.append({"product_id": pid, "fatal": "manifest missing"})
            verdicts_all.append(FAIL)
            continue
        mf = json.loads(mf_path.read_text("utf-8"))
        plan_row = scope[pid]
        panel_row = panel[str(mf["cell_id"])]
        dims = run_product(mf, plan_row, crow, panel_row, supports, ee,
                           plan_checksum, supersession)
        verdict = worst([d.verdict for d in dims])
        verdicts_all.append(verdict)
        products.append({
            "product_id": pid, "cell_id": str(mf["cell_id"]),
            "sensor": str(mf["sensor"]), "year": int(mf["year"]),
            "canary_case": str(crow.canary_case),
            "v2_change": str(crow.v2_change),
            "verdict": verdict,
            "dimensions": [d.to_dict() for d in dims]})
        print(f"[{pid}] {verdict} ({crow.canary_case}): "
              + ", ".join(f"{d.name}={d.verdict}" for d in dims),
              flush=True)
    gate = worst(verdicts_all) if verdicts_all else FAIL
    decision = ("V2_RECOVERY_CANARY_PASS" if gate != FAIL
                else "V2_RECOVERY_CANARY_FAIL")
    report = {
        "schema": "spartina_pilot19_canary_qa_v2",
        "issue": "#19",
        "selection_revision": _DRIVER.SELECTION_V2,
        "created_utc": _now(),
        "live_gee_cross_checks": not args.no_live,
        "canary_cases_present": sorted(cases),
        "canary_cases_required": sorted(CANARY_CASES_REQUIRED),
        "gate_verdict": gate,
        "decision": decision,
        "actual_mask_gate": ACTUAL_MASK_GATE,
        "plan_v2_csv_sha256": plan_checksum,
        "git": git_context(str(REPO_ROOT)),
        "environment": runtime_environment(),
        "products": products}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"{decision}; report -> {args.out}", flush=True)
    return 0 if gate != FAIL else 2


if __name__ == "__main__":
    raise SystemExit(main())
