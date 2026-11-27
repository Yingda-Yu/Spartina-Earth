#!/usr/bin/env python3
"""Issue #21, Phase B -- freeze the deterministic v0.2 new-cell panel.

Consumes the frozen national feature table (metadata + named-label
overlays only; no pixels, no model information) and the Phase A
requirements freeze, runs the fixed deterministic quota sequence in
``spartina.benchmark.v02.selection``, and persists the panel BEFORE any
pixel export:

  benchmarks/spartinashift/v0_2/v02_cell_panel.csv
  benchmarks/spartinashift/v0_2/SPARTINASHIFT_V0_2_CELL_PANEL.json
  work/issue21/derived/v02_domain_exclusion_ledger.csv  (all 3,319 cells)

The freeze is immutable: an existing panel with a different selected
set or checksum is never overwritten.
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

from spartina.benchmark.v02 import requirements as R  # noqa: E402
from spartina.benchmark.v02 import selection as S  # noqa: E402
from spartina.data.national.pilot_panel import coastal_segment  # noqa: E402

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
REQUIREMENTS_JSON = V02_DIR / "SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS.json"
FEATURES_CSV = REPO_ROOT / "work/issue21/derived/v02_cell_features.csv"
FEATURES_JSON = (
    REPO_ROOT / "work/issue21/derived/v02_cell_features_manifest.json")
REGISTRY_CSV = (
    REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_1_core_frozen.csv")
PANEL_CSV_OUT = V02_DIR / "v02_cell_panel.csv"
PANEL_JSON_OUT = V02_DIR / "SPARTINASHIFT_V0_2_CELL_PANEL.json"
LEDGER_CSV = REPO_ROOT / "work/issue21/derived/v02_domain_exclusion_ledger.csv"

PANEL_COLUMNS = [
    "cell_id", "province", "province_rule", "coastal_segment",
    "membership_v1_1", "island", "exclusive_stratum", "agreement_2020",
    "area_class", "max_pos_area_km2", "geo15", "geo20", "cmsa20",
    "cmsa21", "cmssm20", "geo_both", "cmsa_both", "any_positive",
    "clean_background", "pair20", "pair21", "pair_capable",
    "n_pair_years", "landsat_both_years", "s2_autumn_full_2020",
    "s2_autumn_full_2021", "s1_autumn_full_2020", "s1_autumn_full_2021",
    "landsat_autumn_full_2015", "landsat_autumn_full_2020",
    "inclusion_reasons"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
        capture_output=True, text=True).stdout.strip()


def document_checksum(doc: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        {k: v for k, v in doc.items()
         if k not in {"checksum", "git_commit", "generated_utc"}},
        sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()


def build_ledger(registry: pd.DataFrame, selected: set[str],
                 panel_ids: set[str]) -> pd.DataFrame:
    """Exclusion reason for EVERY frozen-registry cell (3,319)."""
    rows = []
    for r in registry.itertuples():
        keep = r.membership_v1_1 in (
            "KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL")
        eligible = keep and str(r.production_eligible).lower() == "true"
        if r.cell_id in selected:
            reason = "SELECTED"
        elif r.cell_id in panel_ids:
            reason = S.REASON_OLD_PANEL
        elif not eligible:
            reason = S.REASON_DOMAIN
        else:
            reason = S.REASON_RANK
        rows.append({
            "cell_id": r.cell_id,
            "membership_v1_1": r.membership_v1_1,
            "production_eligible": r.production_eligible,
            "selected": r.cell_id in selected,
            "stage1_panel": r.cell_id in panel_ids,
            "reason": reason})
    return pd.DataFrame(rows)


def main() -> int:
    requirements = json.loads(REQUIREMENTS_JSON.read_text())
    R.validate_requirements(requirements)
    features = pd.read_csv(FEATURES_CSV)
    result = S.select_panel(features)
    panel: pd.DataFrame = result["panel"].copy()
    panel["coastal_segment"] = panel["province"].map(coastal_segment)
    panel_out = panel[PANEL_COLUMNS]

    ledger = build_ledger(
        pd.read_csv(REGISTRY_CSV),
        selected=set(panel["cell_id"]),
        panel_ids=set(features.loc[
            features["old_stage1_panel"], "cell_id"]))

    slot_counts: dict[str, int] = {}
    for reasons in result["inclusion"].values():
        for slot in reasons:
            slot_counts[slot] = slot_counts.get(slot, 0) + 1

    feature_manifest = json.loads(FEATURES_JSON.read_text())
    document: dict[str, Any] = {
        "panel_name": "SPARTINASHIFT_V0_2_CELL_PANEL",
        "issue": 21,
        "phase": "B",
        "status": "FROZEN_PRE_EXPORT",
        "requirements_name": requirements["requirements_name"],
        "requirements_checksum": requirements["checksum"],
        "n_new_cells": int(len(panel_out)),
        "new_cell_cap": 96,
        "stage1_panel_excluded": int(features["old_stage1_panel"].sum()),
        "selected_cell_ids": sorted(panel_out["cell_id"]),
        "holdout_provinces": result["holdout_provinces"],
        "goal_attainment": result["goals"],
        "deficits_max_attainable": result["deficits"],
        "quota_slot_counts": slot_counts,
        "selection_algorithm": {
            "inputs": "frozen geography, target-independent provinces, "
                      "named label presence/area, Issue #18 strata, "
                      "area class, metadata-only EO availability",
            "forbidden": "model outputs, failure maps, uncertainty, "
                         "test performance, imagery appearance",
            "slot_order": [
                "holdout_positive_geo", "holdout_positive_cmsa",
                "holdout_background", "geodata_both_years",
                "cmsa_both_years", "outside_cells_guarantee",
                "outside_positive_guarantee", "pair_positive",
                "pair_any", "background_spread",
                "agreement_stratum:*", "area_class:*",
                "island_positive", "island_background"],
            "rank_within_slot": [
                "pair-capable years desc", "S2 event availability desc",
                "S1 event availability desc",
                "Landsat event availability desc",
                "slot-salted SHA-256 hash rank", "cell_id asc"],
        },
        "metadata_support_in_panel": {
            "s2_2020_cells": int((panel_out["s2_autumn_full_2020"] > 0)
                                 .sum()),
            "s2_2021_cells": int((panel_out["s2_autumn_full_2021"] > 0)
                                 .sum()),
            "s1_2020_cells": int((panel_out["s1_autumn_full_2020"] > 0)
                                 .sum()),
            "s1_2021_cells": int((panel_out["s1_autumn_full_2021"] > 0)
                                 .sum()),
            "landsat_2015_cells": int(
                (panel_out["landsat_autumn_full_2015"] > 0).sum()),
            "landsat_2020_cells": int(
                (panel_out["landsat_autumn_full_2020"] > 0).sum()),
        },
        "feature_table": {
            "path": str(FEATURES_CSV.relative_to(REPO_ROOT)),
            "sha256": sha256(FEATURES_CSV),
            "crosschecks": feature_manifest.get("crosschecks"),
            "geodata_2015_flag_crosscheck":
                feature_manifest.get("geodata_2015_flag_crosscheck"),
        },
        "panel_csv_sha256": None,
        "exclusion_ledger": {
            "path": str(LEDGER_CSV.relative_to(REPO_ROOT)),
            "n_rows": int(len(ledger)),
            "n_selected": int((ledger["reason"] == "SELECTED").sum()),
            "n_stage1_excluded": int(
                (ledger["reason"] == S.REASON_OLD_PANEL).sum()),
            "n_outside_domain": int(
                (ledger["reason"] == S.REASON_DOMAIN).sum()),
            "n_eligible_rank_excluded": int(
                (ledger["reason"] == S.REASON_RANK).sum()),
        },
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
    }

    PANEL_CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_CSV.parent.mkdir(parents=True, exist_ok=True)
    panel_out.to_csv(PANEL_CSV_OUT, index=False)
    ledger.to_csv(LEDGER_CSV, index=False)
    document["panel_csv_sha256"] = sha256(PANEL_CSV_OUT)
    document["exclusion_ledger"]["sha256"] = sha256(LEDGER_CSV)
    document["selection_checksum"] = result["checksum"]
    document["checksum"] = document_checksum(document)

    if PANEL_JSON_OUT.exists():
        old = json.loads(PANEL_JSON_OUT.read_text())
        if old.get("checksum") != document["checksum"]:
            raise SystemExit(
                "REFUSING TO MUTATE FROZEN PANEL: existing freeze has a "
                "different checksum; bump the version instead.")
        print("frozen panel already present and identical")
    else:
        PANEL_JSON_OUT.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(f"wrote {PANEL_JSON_OUT}")
    print(f"new cells: {document['n_new_cells']}")
    print(f"holdouts: {document['holdout_provinces']}")
    print(f"goals_met: {document['goal_attainment']['goals_met']}")
    if document["deficits_max_attainable"]:
        print("deficits:")
        for d in document["deficits_max_attainable"]:
            print(f"  - {d}")
    print(f"selection_checksum: {document['selection_checksum']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
