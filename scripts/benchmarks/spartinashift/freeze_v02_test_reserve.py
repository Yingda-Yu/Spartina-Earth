#!/usr/bin/env python3
"""Issue #21, Phase C -- freeze the pre-registered fresh test reserve.

Runs BEFORE any pixel export. The reserve is a sealed stratum of NEW
panel cells; final train/val/test roles are not assigned. Outputs:

  benchmarks/spartinashift/v0_2/V0_2_FRESH_TEST_RESERVE.json
  benchmarks/spartinashift/v0_2/v02_fresh_test_reserve.csv

Immutability mirrors the requirements and panel freezes.
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

from spartina.benchmark.v02 import reserve as Rv  # noqa: E402

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
PANEL_JSON = V02_DIR / "SPARTINASHIFT_V0_2_CELL_PANEL.json"
PANEL_CSV = V02_DIR / "v02_cell_panel.csv"
REQUIREMENTS_JSON = V02_DIR / "SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS.json"
OUT_JSON = V02_DIR / "V0_2_FRESH_TEST_RESERVE.json"
OUT_CSV = V02_DIR / "v02_fresh_test_reserve.csv"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def document_checksum(doc: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        {k: v for k, v in doc.items()
         if k not in {"checksum", "document_checksum", "git_commit",
                      "generated_utc"}},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    panel_freeze = json.loads(PANEL_JSON.read_text())
    requirements = json.loads(REQUIREMENTS_JSON.read_text())
    panel = pd.read_csv(PANEL_CSV)
    declaration = Rv.declare_reserve(panel)
    if declaration["checksum"] != Rv.reserve_checksum(declaration):
        raise SystemExit("reserve checksum self-check failed")

    reserve_ids = {m["cell_id"] for m in declaration["members"]}
    reserve_csv = panel[panel["cell_id"].isin(reserve_ids)][[
        "cell_id", "province", "coastal_segment", "any_positive",
        "clean_background", "geo_both", "cmsa_both", "agreement_2020",
        "area_class", "inclusion_reasons"]].sort_values("cell_id")
    reserve_csv = reserve_csv.merge(
        pd.DataFrame(declaration["members"]), on="cell_id")

    document: dict[str, Any] = {
        **declaration,
        "issue": 21,
        "phase": "C",
        "panel_name": panel_freeze["panel_name"],
        "panel_selection_checksum": panel_freeze["selection_checksum"],
        "panel_csv_sha256": sha256(PANEL_CSV),
        "requirements_checksum": requirements["checksum"],
        "stage1_panel_status": requirements["stage1_panel"]["status"],
        "stage1_inspected_test_witness": requirements["stage1_panel"][
            "inspected_test_witness_cell_ids"],
        "hard_exclusion_rule": (
            "no Stage-1 test/witness cell and no other DEVELOPMENT cell "
            "is eligible as a primary v0.2 test cell; reserve members "
            "are sealed from training, tuning and inspection until QA "
            "completes and the future v0.2 protocol freezes roles"),
        "reserve_csv_sha256": None,
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True).stdout.strip(),
    }

    reserve_csv.to_csv(OUT_CSV, index=False)
    document["reserve_csv_sha256"] = sha256(OUT_CSV)
    document["document_checksum"] = document_checksum(document)

    if OUT_JSON.exists():
        old = json.loads(OUT_JSON.read_text())
        if old.get("document_checksum") != document["document_checksum"]:
            raise SystemExit(
                "REFUSING TO MUTATE FROZEN RESERVE: existing freeze "
                "differs; bump the version instead.")
        print("frozen reserve already present and identical")
    else:
        OUT_JSON.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(f"wrote {OUT_JSON}")
    print(f"reserve cells: {document['n_cells']} "
          f"(+{document['n_positive']}/-{document['n_background']}) "
          f"across {document['n_provinces']} provinces")
    print(f"provinces: {document['selection_rule']['provinces_used']}")
    if document["deficits_max_attainable"]:
        for d in document["deficits_max_attainable"]:
            print(f"DEFICIT: {d}")
    print(f"checksum: {document['checksum']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
