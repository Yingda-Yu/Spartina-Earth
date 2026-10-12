#!/usr/bin/env python3
"""C5 per-cell S2 vs S1-A acquisition date-gap ledger (frozen evidence).

The optical and SAR sensors are never simultaneous: every reported gap
is days between the paired scene acquisition times, taken from the
frozen support matrix. Season match window 30 d, near-date window 7 d.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCH = REPO_ROOT / "benchmarks" / "spartinashift" / "silver_v0_1"
SEASON_DAYS = 30
NEAR_DAYS = 7


def main() -> int:
    protocol = json.loads((BENCH / "SPARTINASHIFT_SILVER_V0_1_PROTOCOL.json")
                          .read_text())
    eligible = protocol["tasks"]["C5_modality_ablation"][
        "optical_sar_arm"]["eligible_cells"]
    with (BENCH / "support_matrix_v0_1.csv").open(newline="") as fh:
        matrix = list(csv.DictReader(fh))
    rows_out = []
    gaps = []
    for cell in eligible:
        for year in (2020, 2021):
            s2 = next(r for r in matrix if r["cell_id"] == cell
                      and int(r["year"]) == year
                      and r["sensor"] == "sentinel2"
                      and r["label_source_key"] == f"CMSA_{year}"
                      and r["label_support_m"] == "30"
                      and r["pairing_state"] == "PAIRED_LANDED")
            s1 = next(r for r in matrix if r["cell_id"] == cell
                      and int(r["year"]) == year
                      and r["sensor"] == "sentinel1"
                      and r["eo_variant"] == "A"
                      and r["label_source_key"] == f"CMSA_{year}"
                      and r["label_support_m"] == "30"
                      and r["pairing_state"] == "PAIRED_LANDED")
            gap = int(abs((np.datetime64(s2["event_utc"][:19])
                       - np.datetime64(s1["event_utc"][:19]))
                      .astype("timedelta64[D]").astype(int)))
            gaps.append(gap)
            rows_out.append({
                "cell_id": cell, "year": year,
                "s2_product_id": s2["product_id"],
                "s1a_product_id": s1["product_id"],
                "s2_event_utc": s2["event_utc"],
                "s1a_event_utc": s1["event_utc"],
                "gap_days": gap,
                "within_30d_season_window": gap <= SEASON_DAYS,
                "within_7d_near_window": gap <= NEAR_DAYS,
                "simultaneous": gap == 0})
    gaps_arr = np.array(gaps)
    ledger = {
        "protocol_name": protocol["protocol_name"],
        "protocol_checksum": protocol["checksum"],
        "task": "C5", "support_matrix_sha256": hashlib.sha256(
            (BENCH / "support_matrix_v0_1.csv").read_bytes()).hexdigest(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True).stdout.strip(),
        "emitted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "language": "paired acquisitions with a date gap; never simultaneous",
        "season_window_days": SEASON_DAYS,
        "near_window_days": NEAR_DAYS,
        "n_pairs": len(rows_out),
        "gap_days_min": int(gaps_arr.min()),
        "gap_days_median": float(np.median(gaps_arr)),
        "gap_days_max": int(gaps_arr.max()),
        "n_within_7d": int((gaps_arr <= NEAR_DAYS).sum()),
        "n_within_30d": int((gaps_arr <= SEASON_DAYS).sum()),
        "n_simultaneous": int((gaps_arr == 0).sum()),
        "pairs": rows_out}
    out = BENCH / "results" / "C5" / "date_gap_ledger.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, sort_keys=True, indent=2,
                              ensure_ascii=False) + "\n")
    print(f"wrote {out.relative_to(REPO_ROOT)}: n={len(rows_out)} "
          f"median {np.median(gaps_arr)} d, max {gaps_arr.max()} d, "
          f"simultaneous {int((gaps_arr == 0).sum())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
