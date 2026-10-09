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
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

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


def dim_actual_mask_v2(mf: dict[str, Any], pixel_m: float) -> Dimension:
    paths = _paths(mf)
    sensor = str(mf["sensor"])
    problems: list[str] = []
    detail: dict[str, Any] = {}
    if sensor == "sentinel2":
        observed, per_band = _s2_observed(paths["sr"])
        detail["per_band_finite_fraction"] = per_band
        total = int(observed.size)
        n_obs = int(observed.sum())
        basis = _DRIVER.BASIS_S2_V2
    else:
        d = _s1_dualpol(paths["vvvh"])
        observed = d["valid"]
        total = int(observed.size)
        n_obs = int(observed.sum())
        detail["dualpol_finite_fraction"] = float(d["dual"].mean())
        detail["floor_area_fraction"] = float(d["floor"].mean())
        basis = _DRIVER.BASIS_S1_V2
    byte_fraction = n_obs / total
    # Independent inside-W10-cell fraction (the cell is the product unit).
    hdr = QA1._header(paths["sr"] if sensor == "sentinel2"
                      else paths["vvvh"])
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
    if byte_fraction < ACTUAL_MASK_GATE:
        problems.append(
            f"grid actual-mask fraction {byte_fraction:.4f} < "
            f"{ACTUAL_MASK_GATE}")
    if in_cell < ACTUAL_MASK_GATE:
        problems.append(
            f"in-cell actual-mask fraction {in_cell:.4f} < "
            f"{ACTUAL_MASK_GATE}")
    # Cross-check the manifest's own landing-gate record pixel-for-pixel.
    rec = mf.get("qa", {}).get("actual_mask_v2", {})
    if not rec:
        problems.append("manifest missing qa.actual_mask_v2 record")
    else:
        # S2 records observed_pixels; the S1 token records valid_pixels.
        count_key = ("observed_pixels" if sensor == "sentinel2"
                     else "valid_pixels")
        if int(rec.get(count_key, -1)) != n_obs:
            problems.append(
                f"manifest {count_key} {rec.get(count_key)} != "
                f"recomputed {n_obs}")
        if abs(float(rec.get("actual_observed_fraction", -1))
               - byte_fraction) > 1e-12:
            problems.append("manifest actual fraction disagrees with bytes")
        gate = rec.get("gate", {})
        if not gate.get("gate_pass") or not gate.get("pass"):
            problems.append("landing gate record not PASS")
        detail["manifest_gate"] = gate
    if not problems:
        note = f"actual-mask coverage {byte_fraction:.4f} grid / " \
               f"{in_cell:.4f} in cell (gate {ACTUAL_MASK_GATE})"
    else:
        note = "; ".join(problems)
    return QA1.Dimension("actual_mask_v2_gate",
                         FAIL if problems else PASS, detail, note)


# ---------------------------------------------------------------------------
# interior NaN / hole morphology
# ---------------------------------------------------------------------------

def dim_interior_nan(mf: dict[str, Any]) -> Dimension:
    paths = _paths(mf)
    sensor = str(mf["sensor"])
    if sensor == "sentinel2":
        observed, _ = _s2_observed(paths["sr"])
    else:
        observed = _s1_dualpol(paths["vvvh"])["valid"]
    h, w = observed.shape
    interior = np.zeros((h, w), dtype=bool)
    interior[INTERIOR_ERODE_PX:h - INTERIOR_ERODE_PX,
             INTERIOR_ERODE_PX:w - INTERIOR_ERODE_PX] = True
    interior_bad = interior & ~observed
    interior_frac = float(interior_bad.sum() / max(int(interior.sum()), 1))
    # Largest non-observed component that does not touch the window edge
    # (a geometric interior hole, as opposed to a footprint-edge bite).
    holes, n_holes = ndimage.label(~observed)
    edge_labels = np.unique(np.concatenate(
        [holes[0, :], holes[-1, :], holes[:, 0], holes[:, -1]]))
    edge_labels = set(edge_labels.tolist()) - {0}
    sizes = np.bincount(holes.ravel())
    interior_hole_sizes = [
        int(sizes[i]) for i in range(1, n_holes + 1) if i not in edge_labels]
    largest_hole = max(interior_hole_sizes, default=0)
    detail = {
        "interior_erode_px": INTERIOR_ERODE_PX,
        "interior_pixels": int(interior.sum()),
        "interior_nonobserved_pixels": int(interior_bad.sum()),
        "interior_nonobserved_fraction": interior_frac,
        "n_interior_hole_components": len(interior_hole_sizes),
        "largest_interior_hole_pixels": largest_hole,
        "largest_interior_hole_fraction": largest_hole / float(h * w)}
    if interior_frac >= INTERIOR_FAIL_FRAC:
        verdict = FAIL
        note = (f"systematic interior non-observation: "
                f"{interior_frac:.6f} >= {INTERIOR_FAIL_FRAC}")
    elif interior_frac > 0:
        verdict = WARN
        note = f"{int(interior_bad.sum())} sporadic interior non-observed pixels"
    else:
        verdict = PASS
        note = "no interior non-observed pixels"
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
    es = mf.get("event_selection", {})
    checks = {
        "revision_pilot_event_selection_v2":
            es.get("revision") == _DRIVER.SELECTION_V2,
        "plan_checksum": es.get("plan_csv_sha256") == plan_checksum,
        "eligibility_v2_eligible":
            es.get("eligibility_status") == _DRIVER.STATUS_V2_ELIGIBLE,
        "v2_change_matches_plan": es.get("v2_change") == change,
        "v2_change_matches_canary":
            es.get("v2_change") == canary_v2_change,
        "gate_0p95": es.get("actual_mask_gate") == ACTUAL_MASK_GATE,
        "label_independent": es.get("label_independent") is True,
        "threshold_relaxation_forbidden":
            es.get("threshold_relaxation_forbidden") is True,
        "planned_fraction_matches_plan": abs(
            float(es.get("actual_observed_fraction_planned", -1))
            - float(plan_row.get("v2_actual_observed_fraction", -1)))
        < 1e-12,
        "manifest_event_date_matches_v2_plan":
            str(mf.get("acquisition_utc_planned", ""))[:10]
            == str(plan_row.get("event_utc"))[:10],
    }
    detail["event_selection_checks"] = checks
    problems.extend(k for k, ok in checks.items() if not ok)
    pid = str(mf["product_id"])
    archived_manifest = SUPERSEDED_MANIFEST_DIR / f"{pid}.json"
    if not archived_manifest.exists():
        problems.append("archived V0 manifest copy missing")
    else:
        old = json.loads(archived_manifest.read_text("utf-8"))
        detail["archived_v0_schema"] = old.get("schema")
        old_sha = {f["role"]: f["sha256"] for f in old["landed_files"]}
        if change == _DRIVER.CHANGE_KEPT:
            # Raw bytes must be byte-identical to the V0 record (metadata
            # only enrichment; no resubmission).
            kept: dict[str, bool] = {}
            for f in mf["landed_files"]:
                if f.get("derivation"):
                    continue
                kept[f["role"]] = old_sha.get(f["role"]) == f["sha256"]
            detail["kept_raw_sha_matches_v0"] = kept
            if not all(kept.values()):
                problems.append("KEPT raw bytes differ from V0 SHA record")
            if str(old.get("acquisition_utc_planned", ""))[:10] != str(
                    mf.get("acquisition_utc_planned", ""))[:10]:
                problems.append("KEPT event date changed")
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
                            f"archived byte {rec['name']} missing/hash bad")
                detail["archived_files"] = archived_files
                detail["v1_event_utc"] = entry.get("v1_event_utc")
                detail["v2_event_utc"] = entry.get("v2_event_utc")
                if str(entry.get("v2_event_utc", ""))[:10] != str(
                        plan_row.get("event_utc"))[:10]:
                    problems.append("index v2 event != plan event")
            # New bytes must carry the r2 revision + V2 date; no r1 file
            # for the new event may exist (old-event orphan rule).
            for role in _DRIVER.COMPONENTS[str(mf["sensor"])]:
                expect_prefix = _DRIVER.prefix_for(
                    plan_row, role, plan_version="v2")
                got = {Path(f["local_uri"]).name for f in mf["landed_files"]
                       if f["role"] == role}
                if got != {f"{expect_prefix}.tif"}:
                    problems.append(
                        f"{role}: expected {expect_prefix}.tif, got {got}")
        else:
            problems.append(f"unknown v2_change {change}")
    detail["v2_change"] = change
    return QA1.Dimension(
        "repair_provenance", FAIL if problems else PASS, detail,
        "; ".join(problems) or f"{change}: V0 history preserved and verified")


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
    if sensor == "sentinel2":
        dims.extend(QA1.qa_s2(ee, mf))
    else:
        dims.extend(qa_s1_v2(ee, mf, plan_row))
    dims.append(dim_actual_mask_v2(mf, pixel_m))
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
