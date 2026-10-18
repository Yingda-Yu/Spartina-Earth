#!/usr/bin/env python3
"""Issue #21, Phase J -- SpartinaShift v0.2 support matrix.

Built AFTER the Phase H export and Phase I landing validation. Every
count is MEASURED from frozen artifacts and landed manifests:

  * 53 NEW panel cells (the Issue #21 expansion; exported here),
  * 20 original Stage-1 cells (DEVELOPMENT_INSTRUMENTATION_ONLY; their
    bytes came from Issue #19 and they can never be pristine v0.2 test),
  * 24 fresh reserve cells (untouched, never exported, potential only).

All counts are cell-level: multiple patches inside one cell are never
counted as independent cells. Outputs:

  benchmarks/spartinashift/v0_2/V0_2_SUPPORT_MATRIX.json
  benchmarks/spartinashift/v0_2/v02_support_matrix_per_cell.csv
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.benchmark.v02 import acquisition as A  # noqa: E402

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
PANEL_CSV = V02_DIR / "v02_cell_panel.csv"
RESERVE_CSV = V02_DIR / "v02_fresh_test_reserve.csv"
S2_JSON = V02_DIR / "V0_2_S2_ACQUISITION_PLAN.json"
L_JSON = V02_DIR / "V0_2_LANDSAT_ACQUISITION_PLAN.json"
G_JSON = V02_DIR / "V0_2_S1_PAIRING_LEDGER.json"
SCOPE_JSON = V02_DIR / "V0_2_EXPORT_SCOPE_ESTIMATE.json"
EXPORT_INDEX = REPO_ROOT / "work/issue21/export/v02_export_index.json"
OLD_PANEL_CSV = (REPO_ROOT / "datasets/manifests"
                 / "national_first_pixel_panel_v1.csv")
OLD_PROGRESS = (REPO_ROOT / "work/national/pilot19"
                / "export_progress_v2.json")
OUT_JSON = V02_DIR / "V0_2_SUPPORT_MATRIX.json"
OUT_CSV = V02_DIR / "v02_support_matrix_per_cell.csv"

OLD_ROLE = "DEVELOPMENT_INSTRUMENTATION_ONLY"
RESERVE_ROLE = "FRESH_TEST_RESERVE_UNTOUCHED"
NEW_ROLE = "V0_2_NEW_PANEL_EXPORTED"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verified(path: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(path.read_text("utf-8"))
    if A.document_checksum(doc) != doc.get("document_checksum"):
        raise SystemExit(f"frozen artifact checksum mismatch: {path.name}")
    return doc


def _per_cell_year(slots: list[dict[str, Any]], eligible: bool) -> dict[str, int]:
    dist: dict[str, int] = {}
    keys = {(s["cell_id"], int(s["year"])) for s in slots}
    for key in keys:
        n = sum(1 for s in slots
                if (s["cell_id"], int(s["year"])) == key
                and (s["status"] == A.STATUS_ELIGIBLE) == eligible)
        dist[str(n)] = dist.get(str(n), 0) + 1
    return dict(sorted(dist.items(), key=lambda kv: int(kv[0])))


def _events_by_cell_year(
    slots: list[dict[str, Any]],
) -> dict[tuple[str, int], int]:
    out: dict[tuple[str, int], int] = {}
    for s in slots:
        if s["status"] != A.STATUS_ELIGIBLE:
            continue
        key = (s["cell_id"], int(s["year"]))
        out[key] = out.get(key, 0) + 1
    return out


def _tertile_fill(slots: list[dict[str, Any]]) -> dict[str, Any]:
    by_year_tertile: dict[str, dict[str, int]] = {}
    for s in slots:
        if s["status"] != A.STATUS_ELIGIBLE:
            continue
        yd = by_year_tertile.setdefault(str(int(s["year"])),
                                        {t: 0 for t in A.TERTILE_ORDER})
        yd[s["tertile"]] += 1
    return by_year_tertile


def _region_table(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (province, segment), g in frame.groupby(
            ["region_province", "coastal_segment"], sort=True):
        rows.append({
            "region_province": str(province),
            "coastal_segment": str(segment),
            "cells": int(len(g)),
            "any_positive_cells": int(g["any_positive"].sum()),
            "clean_background_cells": int(g["clean_background"].sum()),
            "cells_with_landed_eo": int(g["any_landed"].sum())})
    return sorted(rows, key=lambda r: (-r["cells"], r["region_province"]))


def main() -> int:
    panel = pd.read_csv(PANEL_CSV)
    reserve = pd.read_csv(RESERVE_CSV)
    old = pd.read_csv(OLD_PANEL_CSV)
    s2 = _verified(S2_JSON)
    lnd = _verified(L_JSON)
    pairs = _verified(G_JSON)
    scope = _verified(SCOPE_JSON)
    if not EXPORT_INDEX.exists():
        raise SystemExit(
            f"missing {EXPORT_INDEX}; run Phase H export before Phase J")
    index: dict[str, Any] = json.loads(EXPORT_INDEX.read_text("utf-8"))
    if int(index["n_landed"]) != int(index["n_scope"]):
        raise SystemExit(
            f"export incomplete: {index['n_landed']}/{index['n_scope']} "
            "landed; Phase J requires the full frozen scope landed")

    panel_ids = set(panel["cell_id"])
    reserve_ids = set(reserve["cell_id"])
    old_ids = set(old["cell_id"])
    # Design: reserve is a subset drawn FROM the new panel (same 53 cells
    # pool) and must never overlap the Stage-1 DEVELOPMENT_INSTRUMENTATION_ONLY
    # cells or the old Issue #19 panel.
    if panel_ids & old_ids or reserve_ids & old_ids:
        raise SystemExit(
            "reserve/panel overlap with Stage-1 old cells violates frozen rule")
    if not reserve_ids <= panel_ids:
        raise SystemExit(
            "fresh reserve cells must be drawn from the new panel pool")

    s2_slots = s2["slots"]
    l_slots = lnd["slots"]
    pair_rows = pairs["pairings"]
    s2_cy = _events_by_cell_year(s2_slots)
    l_cy = _events_by_cell_year(l_slots)
    pair_cy: dict[tuple[str, int], int] = {}
    for p in pair_rows:
        if p["status"] != A.STATUS_PAIRED:
            continue
        key = (p["cell_id"], int(p["year"]))
        pair_cy[key] = pair_cy.get(key, 0) + 1

    # Landed products (Phase H outcome) aggregated per cell/year/sensor.
    landed = pd.DataFrame(index["products"])
    landed["year"] = landed["year"].astype(int)
    landed_s2 = {k: int(n) for k, n in landed[
        landed["sensor"] == "sentinel2"].groupby(
            ["cell_id", "year"]).size().items()}
    landed_l = {k: int(n) for k, n in landed[
        landed["sensor"].astype(str).str.startswith("landsat")].groupby(
            ["cell_id", "year"]).size().items()}
    landed_pairs = {k: int(n) for k, n in landed[
        landed["sensor"] == "sentinel1"].groupby(
            ["cell_id", "year"]).size().items()}
    landed_cells = set(landed["cell_id"])

    per_cell = panel.rename(columns={"province": "region_province"})[
        ["cell_id", "region_province", "coastal_segment", "agreement_2020",
         "area_class", "geo15", "geo20", "cmsa20", "cmsa21", "cmssm20",
         "any_positive", "clean_background"]].copy()
    for year in A.S2_YEARS:
        per_cell[f"s2_eligible_{year}"] = per_cell["cell_id"].map(
            lambda c, y=year: s2_cy.get((c, y), 0))
        per_cell[f"s2_landed_{year}"] = per_cell["cell_id"].map(
            lambda c, y=year: landed_s2.get((c, y), 0))
        per_cell[f"pairs_eligible_{year}"] = per_cell["cell_id"].map(
            lambda c, y=year: pair_cy.get((c, y), 0))
        per_cell[f"pairs_landed_{year}"] = per_cell["cell_id"].map(
            lambda c, y=year: landed_pairs.get((c, y), 0))
    for year in A.LANDSAT_YEARS:
        per_cell[f"landsat_eligible_{year}"] = per_cell["cell_id"].map(
            lambda c, y=year: l_cy.get((c, y), 0))
        per_cell[f"landsat_landed_{year}"] = per_cell["cell_id"].map(
            lambda c, y=year: landed_l.get((c, y), 0))
    per_cell["any_landed"] = per_cell["cell_id"].isin(landed_cells)
    per_cell["role"] = NEW_ROLE

    def _year_block(
        cy: dict[tuple[str, int], int], years: tuple[int, ...],
        landed_cy: dict[tuple[str, int], int],
        all_slots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        block: dict[str, Any] = {}
        for year in years:
            n_ge = {1: 0, 2: 0, 3: 0}
            landed_ok = 0
            for cid in panel_ids:
                n = cy.get((cid, year), 0)
                for k in n_ge:
                    if n >= k:
                        n_ge[k] += 1
                if landed_cy.get((cid, year), 0) >= 1:
                    landed_ok += 1
            year_slots = [s for s in all_slots if int(s["year"]) == year]
            block[str(year)] = {
                "eligible_events_per_cell_year": _per_cell_year(
                    year_slots, True),
                "cells_with_ge1_event": n_ge[1],
                "cells_with_ge2_events": n_ge[2],
                "cells_with_3_events_full_tertile_spread": n_ge[3],
                "tertile_slots_filled": _tertile_fill(year_slots).get(
                    str(year)),
                "cells_with_ge1_landed": landed_ok}
        return block

    pos = per_cell[per_cell["any_positive"]]
    defects = {
        "positive_cells_with_no_s2_event_either_year": sorted(
            pos[(pos["s2_eligible_2020"] == 0)
                & (pos["s2_eligible_2021"] == 0)]["cell_id"]),
        "positive_cells_with_no_landsat_event_either_year": sorted(
            pos[(pos["landsat_eligible_2015"] == 0)
                & (pos["landsat_eligible_2020"] == 0)]["cell_id"]),
        "positive_cells_with_no_primary_pair_either_year": sorted(
            pos[(pos["pairs_eligible_2020"] == 0)
                & (pos["pairs_eligible_2021"] == 0)]["cell_id"]),
        "new_cells_with_no_landed_eo": sorted(
            per_cell[~per_cell["any_landed"]]["cell_id"])}

    # Old Stage-1 cells: landed Issue #19 V2 products, instrumentation only.
    old_progress = json.loads(OLD_PROGRESS.read_text("utf-8"))
    old_products = [p for p in old_progress.get("products", [])
                    if p.get("state") == "LANDED"]
    # product_id does not carry the cell id; join from the pilot v2 plan.
    pilot_plan = pd.read_csv(
        REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v2.csv")
    pid_cell = dict(zip(pilot_plan["product_id"], pilot_plan["cell_id"],
                        strict=True))
    old_landed = pd.DataFrame([{
        "cell_id": pid_cell.get(p["product_id"]),
        "sensor": p["sensor"], "year": int(p["year"])}
        for p in old_products if p["product_id"] in pid_cell])
    old_landed = old_landed[old_landed["cell_id"].isin(old_ids)]
    old_by_sensor = {s: int((old_landed["sensor"] == s).sum())
                     for s in ("sentinel2", "sentinel1",
                               "landsat5", "landsat7", "landsat8")}
    old_supported = sorted(set(old_landed["cell_id"]))

    reserve = reserve.rename(
        columns={"province_x": "region_province"})
    reserve_regions = reserve.groupby(
        ["region_province", "coastal_segment"]).size().reset_index(
            name="cells")

    doc: dict[str, Any] = {
        "product": "V0_2_SUPPORT_MATRIX",
        "issue": 21,
        "phase": "J",
        "counting_unit": "CELL; multiple patches per cell never counted "
                         "as independent cells",
        "plan_checksums": {
            "s2": s2["document_checksum"],
            "landsat": lnd["document_checksum"],
            "pairing": pairs["document_checksum"],
            "scope_estimate": scope["document_checksum"],
            "export_index_sha256": sha256(EXPORT_INDEX)},
        "cell_roles": {
            "new_panel_cells": len(panel_ids),
            "fresh_reserve_cells": len(reserve_ids),
            "old_stage1_cells": len(old_ids),
            "roles_pairwise_disjoint": True},
        "new_panel_strata": {
            "geodata_2015_positive_cells": int(panel["geo15"].sum()),
            "geodata_2020_positive_cells": int(panel["geo20"].sum()),
            "cmsa_2020_positive_cells": int(panel["cmsa20"].sum()),
            "cmsa_2021_positive_cells": int(panel["cmsa21"].sum()),
            "cmssm_2020_positive_cells": int(panel["cmssm20"].sum()),
            "any_positive_cells": int(panel["any_positive"].sum()),
            "clean_background_cells": int(
                panel["clean_background"].sum()),
            "agreement_2020": {
                str(k): int(v) for k, v in
                panel["agreement_2020"].value_counts().items()},
            "area_class": {
                str(k): int(v) for k, v in
                panel["area_class"].value_counts().items()}},
        "regions_new_panel": _region_table(per_cell),
        "s2_multi_date": _year_block(
            s2_cy, A.S2_YEARS, landed_s2, s2_slots),
        "landsat_multi_date": _year_block(
            l_cy, A.LANDSAT_YEARS, landed_l, l_slots),
        "s1_s2_pairs": {
            "by_year": {
                str(y): {
                    "primary_pairs_lte7d_planned": sum(
                        1 for p in pair_rows
                        if int(p["year"]) == y
                        and p["status"] == A.STATUS_PAIRED),
                    "pairs_landed": sum(
                        1 for cid in panel_ids
                        for yy in (y,)
                        if landed_pairs.get((cid, yy), 0)),
                    "cells_with_ge1_pair": sum(
                        1 for cid in panel_ids
                        if pair_cy.get((cid, y), 0) >= 1)}
                for y in A.S2_YEARS},
            "gap_distribution": pairs["counts"],
            "sensitivity_tier_only_events": sum(
                1 for p in pair_rows
                if p["status"] == A.STATUS_SENSITIVITY),
            "note": ("sensitivity 14 d tier is analysis-only; no GEE tasks, "
                     "never back-fills primary view")},
        "label_support_alignment_defects": defects,
        "old_stage1_cells": {
            "role": OLD_ROLE,
            "n_cells": len(old_ids),
            "n_cells_with_landed_pilot19_v2_products": len(old_supported),
            "landed_products_by_sensor": old_by_sensor,
            "cells": sorted(old_ids),
            "pristine_v0_2_test_eligibility": False},
        "fresh_reserve": {
            "role": RESERVE_ROLE,
            "n_cells": len(reserve_ids),
            "export_status": "UNTOUCHED_NOT_EXPORTED",
            "any_positive_cells": int(reserve["any_positive"].sum()),
            "clean_background_cells": int(
                reserve["clean_background"].sum()),
            "agreement_2020": {
                str(k): int(v) for k, v in
                reserve["agreement_2020"].value_counts().items()},
            "regions": reserve_regions.to_dict("records")},
        "landed_totals": {
            "products_landed": int(index["n_landed"]),
            "landed_bytes": int(index["landed_bytes"]),
            "open_failures": int(index["n_failures_open"])},
    }

    out_rows = per_cell[[
        "cell_id", "role", "region_province", "coastal_segment",
        "agreement_2020", "area_class", "geo15", "geo20", "cmsa20",
        "cmsa21", "cmssm20", "any_positive", "clean_background",
        "s2_eligible_2020", "s2_landed_2020", "s2_eligible_2021",
        "s2_landed_2021", "landsat_eligible_2015", "landsat_landed_2015",
        "landsat_eligible_2020", "landsat_landed_2020",
        "pairs_eligible_2020", "pairs_landed_2020", "pairs_eligible_2021",
        "pairs_landed_2021", "any_landed"]]
    out_rows.to_csv(OUT_CSV, index=False)
    doc["per_cell_csv_sha256"] = sha256(OUT_CSV)
    doc["generated_utc"] = datetime.now(UTC).isoformat()
    doc["git_commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
        capture_output=True, text=True).stdout.strip()
    doc["document_checksum"] = A.document_checksum(doc)

    if OUT_JSON.exists():
        old_doc = json.loads(OUT_JSON.read_text("utf-8"))
        if old_doc.get("document_checksum") != doc["document_checksum"]:
            raise SystemExit(
                "REFUSING TO MUTATE FROZEN SUPPORT MATRIX: existing "
                "document differs")
        print("support matrix already frozen and identical")
    else:
        OUT_JSON.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False, default=str)
            + "\n", encoding="utf-8")
        print(f"wrote {OUT_JSON.name}")
    print(json.dumps({
        "new_cells": doc["cell_roles"]["new_panel_cells"],
        "positive": doc["new_panel_strata"]["any_positive_cells"],
        "background": doc["new_panel_strata"]["clean_background_cells"],
        "s2_pairs": doc["s1_s2_pairs"]["by_year"],
        "landed": doc["landed_totals"],
        "defects": {k: len(v) for k, v in defects.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
