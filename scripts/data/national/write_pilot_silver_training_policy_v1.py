#!/usr/bin/env python3
"""Issue #19 Phase K -- SILVER training-use policy framework (v1).

The frozen external-label registry currently flags every 2017-2021 label
product as ``internal_training_allowed = NO_REFERENCE_ONLY``. Issue #19
asks us to revisit that overly restrictive default and RECORD a tiered
policy BEFORE any model training begins. This script emits the framework
as a recommendation only:

* it changes NO registry value and authorises NO training run;
* it becomes effective only by explicit owner decision (recorded here as
  ``STATUS = POLICY_RECOMMENDATION_NOT_IN_FORCE``);
* the three tiers and the seven eligibility gates are predeclared so a
  later Issue #20 benchmark can be audited against them.

Output:
* docs/data/national/PILOT_SILVER_TRAINING_POLICY_v1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.data.national.pilot_labels import (  # noqa: E402
    ADAPTER_VERSION,
    LABEL_SOURCES,
    UNKNOWN_GRIDCODE_ZERO,
)

REGISTRY_CSV = (
    REPO_ROOT / "datasets/manifests"
    / "china_external_label_registry_v1.csv")
SUPPORTS_CSV = (
    REPO_ROOT / "datasets/manifests/national_pilot19_label_supports_v1.csv")
PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
OUT_JSON = (
    REPO_ROOT / "docs/data/national/PILOT_SILVER_TRAINING_POLICY_v1.json")

POLICY_VERSION = "PILOT_SILVER_TRAINING_POLICY_V1"

#: Tiers (Issue #19 section F wording, made machine-readable).
TIERS = {
    "SILVER_TRAINING_ELIGIBLE": (
        "SILVER product allowed to supervise INTERNAL research training "
        "runs, but only for spatially disjoint training units and only "
        "while every G1-G7 gate below is satisfied. SILVER labels are "
        "occupancy summaries, never ground truth; their own pixels can "
        "never be quoted as model accuracy."),
    "EXTERNAL_REFERENCE_ONLY": (
        "Product usable for comparison, calibration, visual review and "
        "external-reference metrics, never as a training target. Within "
        "any one experiment the same SILVER product on an evaluation "
        "unit is automatically EXTERNAL_REFERENCE_ONLY there even when "
        "it is SILVER_TRAINING_ELIGIBLE elsewhere."),
    "FINAL_GOLD_EVAL_ONLY": (
        "GOLD label (field/UAV/expert-verified, tier per AGENTS.md "
        "data provenance policy) reserved for the final evaluation. "
        "GOLD sites must be spatially isolated from all training and "
        "from any SILVER-derived target. NO GOLD LABELS EXIST IN THE "
        "PILOT AS OF THIS POLICY (GOLD count = 0)."),
}

GATES = [
    {"id": "G1_PROVENANCE",
     "rule": ("every training example carries dataset manifest entry, "
              "source product id, adapter version, support resolution, "
              "and per-pixel UNKNOWN mask; unprovenanced pixels are "
              "dropped")},
    {"id": "G2_GOLD_ISOLATION",
     "rule": ("no GOLD site, scene or adjacent (buffered) unit may occur "
              "in training; isolation verified with "
              "spartina.evaluation.splits.assert_spatially_disjoint")},
    {"id": "G3_SOURCE_SPECIFIC_EVALUATION",
     "rule": ("metrics are reported per source family and year; SILVER "
              "agreement is never called accuracy and no pooled "
              "'ground-truth accuracy' is reported")},
    {"id": "G4_SPATIAL_LEAKAGE_CONTROL",
     "rule": ("only spatially disjoint splits (W10-cell units with "
              "buffers; scenes of one location grouped across dates); "
              "a split manifest plus a leakage report are required "
              "before any training; Issue #19 creates NO split")},
    {"id": "G5_LICENSE",
     "rule": ("RESTRICTED_RESEARCH_ONLY and CC-BY-NC-4.0 products permit "
              "internal research training only; no commercial use; "
              "source archives and label-derived bytes are never "
              "redistributed; SOURCE_LICENSE_CONFLICT products are used "
              "under the most restrictive terms until TODO_VERIFY is "
              "cleared (DATA_LICENSE.md)")},
    {"id": "G6_UNKNOWN_SEMANTICS",
     "rule": ("CMSA gridcode-0 regions are an ignore mask "
              f"({UNKNOWN_GRIDCODE_ZERO}); GEODATA in-window background "
              "is a WEAK negative and may only be used as a hard "
              "negative under a documented class-balancing scheme; "
              "out-of-window/uncovered pixels are ignored, not negative")},
    {"id": "G7_PILOT_ISOLATION",
     "rule": ("RECOMMENDATION: the 20 Issue #19 pilot cells are excluded "
              "from any training set feeding the Issue #20 benchmark, "
              "so the first controlled national read remains uncontaminated "
              "by development evidence; owner decides at Issue #20 setup")},
]

#: Source-specific conditions attached to the proposed tier assignment.
SOURCE_CONDITIONS: dict[str, str] = {
    "GEODATA": (
        "binary NN-warped masks; background 255 is WEAK negative, never "
        "hard-verified; train only on positive + documented weak-negative "
        "scheme; out-of-window = ignore"),
    "CMSA": (
        "polygon union fractions 2017-2021; gridcode 0 = ignore mask; "
        "no verified negatives; CC-BY-NC-4.0 (attribution NESDC + "
        "Li/Tian/Li 2024)"),
    "CM-SSM": (
        "polygon union fractions 2020; no verified negatives; "
        "SOURCE_LICENSE_CONFLICT -> treat as CC-BY-NC until TODO_VERIFY; "
        "finest resolution, preferred external spatial-detail reference"),
}


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    args = parser.parse_args()

    registry = pd.read_csv(REGISTRY_CSV).set_index("product_id")
    panel = pd.read_csv(PANEL_CSV)

    assignments = []
    for policy in LABEL_SOURCES:
        reg = registry.loc[policy.registry_product_id]
        assignments.append({
            "source_key": policy.key,
            "registry_product_id": policy.registry_product_id,
            "label_tier_in_registry": reg["label_tier"],
            "registry_internal_training_flag":
                reg["internal_training_allowed"],
            "proposed_usage_tier": "SILVER_TRAINING_ELIGIBLE",
            "proposed_scope": (
                "internal research training on spatially disjoint "
                "training units, gates G1-G7 all satisfied"),
            "source_specific_conditions":
                SOURCE_CONDITIONS[policy.family],
            "license_class": reg["license"].split(" (")[0],
            "gold_use_in_registry": bool(reg["gold_use"]),
            "change_requires": (
                "owner approval + registry flag update in a separate "
                "commit; THIS FILE ALONE CHANGES NOTHING"),
        })

    panel_cells = sorted(panel.cell_id)
    policy_doc = {
        "product": POLICY_VERSION,
        "issue": 19,
        "phase": "K (policy framework only; no training, no split)",
        "status": "POLICY_RECOMMENDATION_NOT_IN_FORCE",
        "adapter_version": ADAPTER_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "git_commit": _git_commit(),
        "decision_needed_from": "repository owner (explicit approval)",
        "gold_labels_current_count": 0,
        "tiers": TIERS,
        "eligibility_gates": GATES,
        "context_rules": (
            "Tier assignment is per-experiment contextual: a product can "
            "be SILVER_TRAINING_ELIGIBLE in registry-level policy while "
            "being EXTERNAL_REFERENCE_ONLY on every evaluation unit; a "
            "GOLD product is FINAL_GOLD_EVAL_ONLY everywhere."),
        "weak_negative_policy": (
            "GEODATA in-window background and uncovered vector pixels "
            "never behave as verified negatives; weak negatives require "
            "a documented sampling/loss treatment under G6"),
        "proposed_registry_assignments": assignments,
        "pilot_panel": {
            "n_cells": len(panel_cells),
            "cell_ids": panel_cells,
            "recommended_status": (
                "EXCLUDED_FROM_TRAINING (gate G7 recommendation) until "
                "owner decides the Issue #20 hold-out design"),
        },
        "not_done_here": [
            "no registry value modified",
            "no training run launched",
            "no split or HPO created",
            "no accuracy claim derived from SILVER products",
        ],
        "checksums": {
            "label_registry_csv_sha256": _sha256(REGISTRY_CSV),
            "panel_csv_sha256": _sha256(PANEL_CSV),
            "supports_csv_sha256": _sha256(SUPPORTS_CSV),
        },
    }
    out = Path(args.out_json)
    out.write_text(
        json.dumps(policy_doc, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    print(json.dumps({
        "out": str(out.relative_to(REPO_ROOT)),
        "status": policy_doc["status"],
        "products_assigned": len(assignments),
        "gates": len(GATES),
        "gold_count": 0}, indent=2))


if __name__ == "__main__":
    main()
