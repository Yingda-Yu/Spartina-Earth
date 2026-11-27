#!/usr/bin/env python3
"""Issue #21, Phase H -- project export scope vs the hard caps.

Reads the three frozen acquisition artifacts and a byte table measured
from landed Issue #19 pilot products, and emits a checksummed scope
estimate. A cap breach is an owner-review STOP; this script never trims
support to fit. Output:

  benchmarks/spartinashift/v0_2/V0_2_EXPORT_SCOPE_ESTIMATE.json
"""

from __future__ import annotations

import glob
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.benchmark.v02 import acquisition as A  # noqa: E402
from spartina.benchmark.v02 import scope as S  # noqa: E402

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
S2_JSON = V02_DIR / "V0_2_S2_ACQUISITION_PLAN.json"
L_JSON = V02_DIR / "V0_2_LANDSAT_ACQUISITION_PLAN.json"
G_JSON = V02_DIR / "V0_2_S1_PAIRING_LEDGER.json"
PILOT_PRODUCTS = REPO_ROOT / "work/national/pilot19/products"
OUT_JSON = V02_DIR / "V0_2_EXPORT_SCOPE_ESTIMATE.json"


def landed_size_table() -> tuple[dict[str, int], dict[str, int]]:
    """p90/median bytes per product kind from landed Issue #19 files."""
    files = glob.glob(str(PILOT_PRODUCTS / "*.tif"))
    if not files:
        raise SystemExit(f"no landed pilot products under {PILOT_PRODUCTS}")
    import os

    sizes = {
        "s2_event": [
            os.path.getsize(f) for f in files
            if "_S2_" in Path(f).name and "_sr_" in Path(f).name],
        "s1_pair": [
            os.path.getsize(f) for f in files
            if "_S1_" in Path(f).name and "_vvvh_" in Path(f).name],
        "landsat_observation": [
            os.path.getsize(f) for f in files
            if any(f"_{a}_" in Path(f).name for a in ("L5", "L7", "L8"))
            and "_sr_" in Path(f).name],
    }
    missing = [k for k, v in sizes.items() if not v]
    if missing:
        raise SystemExit(f"no landed evidence for byte kinds: {missing}")
    p90 = {k: int(np.quantile(v, 0.90)) for k, v in sizes.items()}
    median = {k: int(np.median(v)) for k, v in sizes.items()}
    return p90, median


def main() -> int:
    s2_doc = json.loads(S2_JSON.read_text("utf-8"))
    l_doc = json.loads(L_JSON.read_text("utf-8"))
    g_doc = json.loads(G_JSON.read_text("utf-8"))

    n_cells = int(s2_doc["n_cells"])
    s2_events = sum(
        1 for s in s2_doc["slots"] if s["status"] == A.STATUS_ELIGIBLE)
    s1_pairs = sum(
        1 for p in g_doc["pairings"] if p["status"] == A.STATUS_PAIRED)
    l_slots = l_doc["slots"]
    l_obs = sum(1 for s in l_slots if s["status"] == A.STATUS_ELIGIBLE)
    l_by_sensor = {
        sensor: sum(1 for s in l_slots
                    if s.get("sensor") == sensor
                    and s["status"] == A.STATUS_ELIGIBLE)
        for sensor in ("landsat8", "landsat7", "landsat5")}

    p90, median = landed_size_table()
    estimate = S.estimate_scope(
        n_cells=n_cells, s2_events=s2_events, s1_pairs=s1_pairs,
        landsat_observations=l_obs, size_table=p90,
        byte_quantile="p90_of_issue19_landed_sr_components")
    estimate.update({
        "plan_checksums": {
            "s2_plan": s2_doc["document_checksum"],
            "landsat_plan": l_doc["document_checksum"],
            "s1_pairing_ledger": g_doc["document_checksum"]},
        "landsat_eligible_by_sensor": l_by_sensor,
        "size_table_median_bytes": median,
        "size_table_evidence": (
            "p90/median GeoTIFF bytes of landed Issue #19 pilot SR "
            "components under work/national/pilot19/products; S2 valid "
            "and Landsat valid/QA_PIXEL components are < 0.1 MiB each and "
            "the locally derived S1 dualpol token ~15 KiB, counted as "
            "negligible against the 40 GiB cap but included in task rules"),
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True).stdout.strip(),
    })
    estimate["document_checksum"] = A.document_checksum(estimate)

    if OUT_JSON.exists():
        old = json.loads(OUT_JSON.read_text("utf-8"))
        if old.get("document_checksum") != estimate["document_checksum"]:
            raise SystemExit(
                "REFUSING TO MUTATE FROZEN SCOPE ESTIMATE: existing "
                "document differs")
        print("scope estimate already frozen and identical")
    else:
        OUT_JSON.write_text(
            json.dumps(estimate, indent=2, sort_keys=True) + "\n")
        print(f"wrote {OUT_JSON}")
    print(json.dumps(
        {"verdict": estimate["verdict"],
         "counts": estimate["counts"],
         "component_tasks": estimate["projected_gee_component_tasks"],
         "projected_gib": estimate["projected_landed_eo_gib"],
         "breaches": estimate["cap_breaches"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
