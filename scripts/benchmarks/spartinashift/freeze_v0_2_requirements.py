#!/usr/bin/env python3
"""Issue #21, Phase A -- freeze SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS.

Runs BEFORE any new-cell selection and before any pixel export. Emits:

  benchmarks/spartinashift/v0_2/SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS.json

The freeze binds:
  * the Phase A support goals (never forced);
  * the Phase H hard caps (96 new cells / 40 GiB / 10,000 GEE tasks);
  * the legal/forbidden selection inputs (no model information);
  * the Phases D-G acquisition rules;
  * the DEVELOPMENT_INSTRUMENTATION_ONLY status of the 20 Stage-1
    cells and the inspected test/witness exclusion;
  * SHA-256 of every frozen input artifact.

The freeze is immutable: if the output already exists, its body
checksum and panel identity must match the recomputed values or the
script refuses to continue.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.benchmark.v02 import requirements as R  # noqa: E402

OUTPUT = (REPO_ROOT / "benchmarks" / "spartinashift" / "v0_2"
          / "SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS.json")
PANEL_JSON = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.json"
SPLITS_JSON = (REPO_ROOT / "benchmarks" / "spartinashift" / "silver_v0_1"
               / "splits_v0_1.json")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
        capture_output=True, text=True).stdout.strip()


def load_stage1_panel() -> dict[str, Any]:
    panel = json.loads(PANEL_JSON.read_text())
    cell_ids = sorted(c["cell_id"] for c in panel["cells"])
    if len(cell_ids) != 20:
        raise SystemExit(f"expected 20 Stage-1 panel cells, got {len(cell_ids)}")

    splits = json.loads(SPLITS_JSON.read_text())
    inspected: set[str] = set()
    for split in splits["splits"].values():
        inspected.update(split.get("test", []))
        inspected.update(split.get("witness_2020", []))
    inspected_ids = sorted(c for c in inspected if c in set(cell_ids))
    return {
        "status": R.STAGE1_PANEL_STATUS,
        "panel_manifest": str(PANEL_JSON.relative_to(REPO_ROOT)),
        "splits_manifest": str(SPLITS_JSON.relative_to(REPO_ROOT)),
        "cell_ids": cell_ids,
        "inspected_test_witness_cell_ids": inspected_ids,
        "eligible_as_primary_v02_test": False,
        "note": (
            "the original 20 Issue #19/#20 cells are development and "
            "instrumentation only for v0.2; inspected Stage-1 "
            "test/witness cells are excluded from the pristine "
            "primary v0.2 test reserve"),
    }


def build_document() -> dict[str, Any]:
    input_artifacts = []
    for rel in R.INPUT_ARTIFACTS:
        path = REPO_ROOT / rel
        if not path.exists():
            raise SystemExit(f"missing frozen input artifact: {rel}")
        input_artifacts.append({"path": rel, "sha256": sha256_file(path)})

    protocol_rel = next(
        a["path"] for a in input_artifacts
        if a["path"].endswith("SPARTINASHIFT_SILVER_V0_1_PROTOCOL.json"))
    v01_protocol = json.loads((REPO_ROOT / protocol_rel).read_text())

    document: dict[str, Any] = {
        "requirements_name": R.REQUIREMENTS_NAME,
        "requirements_version": R.REQUIREMENTS_VERSION,
        "issue": R.ISSUE,
        "phase": R.PHASE,
        "status": R.STATUS,
        "scientific_interpretation": {
            "stage1_statement": R.STAGE1_INTERPRETATION,
            "forbidden_claim": R.FORBIDDEN_CLAIM,
        },
        "selection_universe": {
            "domain_token": R.DOMAIN_TOKEN,
            "keep_cells": R.DOMAIN_KEEP_CELLS,
            "excluded_cells": R.DOMAIN_EXCLUDED_CELLS,
            "provisional_cells": R.DOMAIN_PROVISIONAL_CELLS,
            "production_eligible_required": R.PRODUCTION_ELIGIBLE_REQUIRED,
            "selection_unit": R.SELECTION_UNIT,
            "selection_namespace": R.SELECTION_NAMESPACE,
            "cell_id_tie_break": R.CELL_ID_TIE_BREAK,
        },
        "support_goals": {
            "attainability_policy": R.ATTAINABILITY_POLICY,
            "geodata_temporal": dict(R.GEODATA_TEMPORAL_GOALS),
            "cmsa_temporal": dict(R.CMSA_TEMPORAL_GOALS),
            "cross_region": dict(R.CROSS_REGION_GOALS),
            "near_synchronous": dict(R.NEAR_SYNCHRONOUS_GOALS),
        },
        "hard_scope_caps": {
            "max_new_cells": R.MAX_NEW_CELLS,
            "max_landed_eo_gib": R.MAX_LANDED_EO_GIB,
            "max_gee_component_tasks": R.MAX_GEE_COMPONENT_TASKS,
            "owner_review_stop": (
                "projected scope exceeding ANY cap stops for owner "
                "review; scientific support is not silently weakened "
                "to fit the caps"),
            "no_national_batch": True,
        },
        "selection_inputs": {
            "legal": list(R.LEGAL_SELECTION_INPUTS),
            "forbidden": list(R.FORBIDDEN_SELECTION_INPUTS),
        },
        "acquisition_rules": {
            "phenology": dict(R.PHENOLOGY),
            "sentinel2": dict(R.S2_RULES),
            "landsat": dict(R.LANDSAT_RULES),
            "views": dict(R.VIEW_CONTRACT),
            "sentinel1": dict(R.S1_RULES),
        },
        "fresh_test_reserve": dict(R.FRESH_TEST_RESERVE_RULES),
        "stage1_panel": load_stage1_panel(),
        "input_artifacts": input_artifacts,
        "silver_v0_1_protocol_checksum": v01_protocol.get("checksum"),
        "production_contracts": {
            "reuse": "Issue #19 V2 production contracts "
                     "(national_pilot_event_plan_v2 / pilot19 export)",
            "guard": "ee.batch.Export guard; metadata-only census has "
                     "zero pixel exports",
        },
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
    }
    document["checksum"] = R.requirements_checksum(document)
    return document


def main() -> int:
    document = build_document()
    R.validate_requirements(document)

    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text())
        same_body = (
            existing.get("checksum") == document["checksum"])
        old_panel = existing.get("stage1_panel", {}).get("cell_ids")
        same_panel = old_panel == document["stage1_panel"]["cell_ids"]
        if not (same_body and same_panel):
            raise SystemExit(
                "REFUSING TO MUTATE FROZEN REQUIREMENTS: existing file "
                f"{OUTPUT} has a different body checksum or panel. A "
                "changed freeze requires a new versioned artifact, not "
                "an overwrite.")
        print(f"frozen requirements already present and identical: {OUTPUT}")
        print(f"checksum: {document['checksum']}")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT}")
    print(f"checksum: {document['checksum']}")
    print(f"stage1 inspected test/witness: "
          f"{document['stage1_panel']['inspected_test_witness_cell_ids']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
