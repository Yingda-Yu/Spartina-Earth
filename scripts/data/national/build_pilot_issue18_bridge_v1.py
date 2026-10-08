#!/usr/bin/env python3
"""Issue #19 Phase J -- bridge the pilot supports to frozen Issue #18.

The pilot label supports (Phase F/G, per-cell native UTM grids) and the
frozen Issue #18 R1 audit (national GEODATA-native Krasovsky grid) derive
from the SAME frozen source archives, but on deliberately different
lattices. This builder joins, per 2020 panel cell, the in-cell Spartina
areas from both independent implementations so any grid/projection
effect is measured rather than asserted away:

* 30 m: GEODATA (binary pixels) and exact CMSA / CM-SSM polygon fractions
  (Issue #18 columns g/c/m, pixel area 900 m^2);
* 10 m: CMSA / CM-SSM fractions (Issue #18 s10 c/m, pixel area 100 m^2;
  GEODATA has no 10 m product, rule 7).

The frozen Issue #18 contingency counts (gc/gm/cm/dgc/dgm/dcm, gridcode-0
mixes) are carried as reference columns only; no new contingency is
computed here (Phase I runs semantic QA after Phase D pixels exist).

Outputs:
* datasets/manifests/national_pilot19_issue18_bridge_v1.csv
* datasets/manifests/national_pilot19_issue18_bridge_v1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts/data/national"))

import pandas as pd  # noqa: E402
from freeze_first_pixel_panel_v1 import _v1_domain_order  # noqa: E402

from spartina.data.national.pilot_labels import ADAPTER_VERSION, UNKNOWN_GRIDCODE_ZERO  # noqa: E402

PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
SUPPORTS_CSV = (
    REPO_ROOT / "datasets/manifests/national_pilot19_label_supports_v1.csv")
S30_CELLS = REPO_ROOT / "work/issue18/derived/s30_cells.csv"
S10_CELLS = REPO_ROOT / "work/issue18/derived/s10_cells.csv"
ISSUE18_MANIFEST = REPO_ROOT / "work/issue18/transform_manifest.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_issue18_bridge_v1.csv"
OUT_JSON = (
    REPO_ROOT / "datasets/manifests/national_pilot19_issue18_bridge_v1.json")

PX_AREA_30 = 900.0
PX_AREA_10 = 100.0
#: Per-cell differences at/below this area are treated as grid noise.
SMALL_AREA_KM2 = 0.05
REL_TOL_SMALL = 0.10

FAMILY_KEYS = {"GEODATA": "geodata", "CMSA": "cmsa", "CM-SSM": "cmssm"}


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pilot_value(
    sub: pd.DataFrame, family: str, support_m: int, col: str,
    default: Any = 0,
) -> Any:
    try:
        v = sub.loc[(family, support_m), col]
        return default if pd.isna(v) else v
    except KeyError:
        return default


def _delta(pilot: float, frozen: float) -> dict[str, float]:
    diff = pilot - frozen
    denom = max(abs(frozen), SMALL_AREA_KM2)
    return {"diff_km2": round(diff, 6),
            "rel_vs_floor": round(diff / denom, 6)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-csv", default=str(OUT_CSV))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    args = parser.parse_args()

    panel = pd.read_csv(PANEL_CSV).set_index("cell_id")
    supports = pd.read_csv(SUPPORTS_CSV)
    s30 = pd.read_csv(S30_CELLS).set_index("cell_idx")
    s10 = pd.read_csv(S10_CELLS).set_index("cell_idx")
    domain = _v1_domain_order().set_index("cell_id")

    rows: list[dict[str, Any]] = []
    for cell_id in panel.index:
        cell_idx = int(domain.loc[cell_id, "cell_idx"])
        r30 = s30.loc[cell_idx] if cell_idx in s30.index else None
        r10 = s10.loc[cell_idx] if cell_idx in s10.index else None
        sub = supports[(supports.cell_id == cell_id)
                       & (supports.year == 2020)].set_index(
            ["family", "support_m"])

        g30 = float(_pilot_value(
            sub, "GEODATA", 30, "positive_area_km2_in_cell"))
        c30 = float(_pilot_value(
            sub, "CMSA", 30, "positive_area_km2_in_cell"))
        m30 = float(_pilot_value(
            sub, "CM-SSM", 30, "positive_area_km2_in_cell"))
        m10 = float(_pilot_value(
            sub, "CM-SSM", 10, "positive_area_km2_in_cell"))

        old = {
            "g30": float(r30.g) * PX_AREA_30 / 1e6 if r30 is not None else 0.0,
            "c30": float(r30.c) * PX_AREA_30 / 1e6 if r30 is not None else 0.0,
            "m30": float(r30.m) * PX_AREA_30 / 1e6 if r30 is not None else 0.0,
            "m10": float(r10.m) * PX_AREA_10 / 1e6 if r10 is not None else 0.0}
        d = {
            "g30": _delta(g30, old["g30"]),
            "c30": _delta(c30, old["c30"]),
            "m30": _delta(m30, old["m30"]),
            "m10": _delta(m10, old["m10"])}
        rows.append({
            "cell_id": cell_id,
            "cell_idx": cell_idx,
            "utm_zone": int(sub.iloc[0]["utm_zone"]),
            "category_2020": panel.loc[
                cell_id, "agreement_category_2020"],
            # grid sizes (pixel centres assigned to the exact cell)
            "pilot_n_pixels_30m": int(_pilot_value(
                sub, "GEODATA", 30, "n_pixels_in_cell")),
            "issue18_n_pixels_30m": int(r30.n) if r30 is not None else 0,
            "pilot_n_pixels_10m_cmssm": int(_pilot_value(
                sub, "CM-SSM", 10, "n_pixels_in_cell")),
            "issue18_n_pixels_10m": int(r10.n) if r10 is not None else 0,
            # 30 m in-cell Spartina area, both implementations
            "pilot_geodata_km2_30m": round(g30, 6),
            "issue18_geodata_km2_30m": round(old["g30"], 6),
            "pilot_cmsa_km2_30m": round(c30, 6),
            "issue18_cmsa_km2_30m": round(old["c30"], 6),
            "pilot_cmssm_km2_30m": round(m30, 6),
            "issue18_cmssm_km2_30m": round(old["m30"], 6),
            # 10 m CM-SSM only (CMSA/GEODATA are 30 m products, rule 7)
            "pilot_cmssm_km2_10m": round(m10, 6),
            "issue18_cmssm_km2_10m": round(old["m10"], 6),
            "diff_geodata_km2_30m": d["g30"]["diff_km2"],
            "diff_cmsa_km2_30m": d["c30"]["diff_km2"],
            "diff_cmssm_km2_30m": d["m30"]["diff_km2"],
            "diff_cmssm_km2_10m": d["m10"]["diff_km2"],
            "rel_geodata_vs_floor_30m": d["g30"]["rel_vs_floor"],
            "rel_cmsa_vs_floor_30m": d["c30"]["rel_vs_floor"],
            "rel_cmssm_vs_floor_30m": d["m30"]["rel_vs_floor"],
            "rel_cmssm_vs_floor_10m": d["m10"]["rel_vs_floor"],
            # CMSA gridcode-0 uncertainty present in this cell (pilot)
            "pilot_gridcode0_pixels_30m": int(_pilot_value(
                sub, "CMSA", 30, "gridcode0_pixels")),
            "pilot_gridcode0_token": UNKNOWN_GRIDCODE_ZERO,
            # frozen Issue #18 contingency reference (NOT recomputed)
            "issue18_gc_30m": int(r30.gc) if r30 is not None else 0,
            "issue18_gm_30m": int(r30.gm) if r30 is not None else 0,
            "issue18_cm_30m": int(r30.cm) if r30 is not None else 0,
            "issue18_dgc_30m": int(r30.dgc) if r30 is not None else 0,
            "issue18_dgm_30m": int(r30.dgm) if r30 is not None else 0,
            "issue18_dcm_30m": int(r30.dcm) if r30 is not None else 0,
            "issue18_g0mix_c_30m": int(r30.g0mix_c)
            if r30 is not None else 0,
            "issue18_g0mix_m_30m": int(r30.g0mix_m)
            if r30 is not None else 0,
            "issue18_dcm_10m": int(r10.dcm) if r10 is not None else 0,
        })

    bridge = pd.DataFrame(rows)
    out_csv = Path(args.out_csv)
    bridge.to_csv(out_csv, index=False)

    rel_cols = [c for c in bridge.columns if c.startswith("rel_")]
    exceed = {c: float(bridge[c].abs().max()) for c in rel_cols
              if float(bridge[c].abs().max()) > REL_TOL_SMALL}

    totals = {
        fam: {
            "pilot_km2": round(float(
                bridge[f"pilot_{key}_km2_30m"].sum()), 6),
            "issue18_km2": round(float(
                bridge[f"issue18_{key}_km2_30m"].sum()), 6)}
        for fam, key in FAMILY_KEYS.items()}
    for _fam, v in totals.items():
        v["pct_diff_vs_issue18"] = (
            round(100 * (v["pilot_km2"] - v["issue18_km2"])
                  / v["issue18_km2"], 3) if v["issue18_km2"] else 0.0)
    m10_tot = {
        "pilot_km2": round(float(bridge["pilot_cmssm_km2_10m"].sum()), 6),
        "issue18_km2": round(float(bridge["issue18_cmssm_km2_10m"].sum()), 6)}
    m10_tot["pct_diff_vs_issue18"] = round(
        100 * (m10_tot["pilot_km2"] - m10_tot["issue18_km2"])
        / m10_tot["issue18_km2"], 3) if m10_tot["issue18_km2"] else 0.0

    manifest = {
        "product": "national_pilot19_issue18_bridge_v1",
        "issue": 19,
        "adapter_version": ADAPTER_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "git_commit": _git_commit(),
        "purpose": (
            "connect the Issue #19 pilot derived supports to the frozen "
            "Issue #18 R1 2020 three-product audit; same frozen sources, "
            "independent grid implementations"),
        "grid_difference": (
            "Issue #18 used the national GEODATA-native Krasovsky Albers "
            "grid (EPSG:4024, origin = GEODATA raster); the pilot uses a "
            "per-cell native UTM covering_grid on densified Albers-cell "
            "bounds with pixel-centre-in-cell assignment. Per-cell "
            "differences are lattice/projection effects, not label "
            "contradictions; agreement is assessed on panel totals and on "
            f"per-cell areas above the {SMALL_AREA_KM2} km2 floor "
            f"(rel tolerance {REL_TOL_SMALL:.0%})."),
        "rule7_reminder": (
            "GEODATA and CMSA have no 10 m support (no 30->10 upsampling); "
            "only CM-SSM is compared at 10 m."),
        "totals_2020_30m": totals,
        "totals_2020_cmssm_10m": m10_tot,
        "per_cell_rel_exceedances_vs_floor": exceed,
        "max_abs_diff_km2": {
            col: round(float(bridge[col].abs().max()), 6)
            for col in (
                "diff_geodata_km2_30m", "diff_cmsa_km2_30m",
                "diff_cmssm_km2_30m", "diff_cmssm_km2_10m")},
        "n_rows": len(bridge),
        "rows": rows,
        "checksums": {
            "panel_csv_sha256": _sha256(PANEL_CSV),
            "supports_csv_sha256": _sha256(SUPPORTS_CSV),
            "issue18_s30_cells_sha256": _sha256(S30_CELLS),
            "issue18_s10_cells_sha256": _sha256(S10_CELLS),
            "issue18_transform_manifest_sha256":
                _sha256(ISSUE18_MANIFEST),
            "bridge_csv_sha256":
                hashlib.sha256(out_csv.read_bytes()).hexdigest()},
    }
    out_json = Path(args.out_json)
    out_json.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    print(json.dumps({
        "rows": len(bridge),
        "totals_2020_30m": totals,
        "totals_2020_cmssm_10m": m10_tot,
        "rel_exceedances": exceed,
        "max_abs_diff_km2": manifest["max_abs_diff_km2"]}, indent=2))


if __name__ == "__main__":
    main()
