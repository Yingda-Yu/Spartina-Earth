#!/usr/bin/env python3
"""Effect of the Issue #17 owner decision on the 2020 scale-audit KEEP set.

The executed Issue #18 audit primary was the 3,011-cell KEEP_ONLY universe
of the v1 candidate.  The 2026-10-08 owner decision freezes a 3,016-cell
KEEP core (five contested-administered Kinmen cells included under the
standing operational disclaimer).  This script re-evaluates the audit's
pooled-Dice cluster bootstrap on the two universes from the *existing*
per-cell aggregate tables in ``work/issue18/derived`` -- no pixels are
re-exported and no raster pipeline is re-run.

Outputs (datasets/manifests/2020_label_scale_audit_v2/):

* table15_domain_v1_1_keep_effect.csv
* table15_note_domain_v1_1.json

Protocol matches ``build_2020_scale_audit_report.py``: W10 cells are the
cluster blocks, cells with zero mapped area enter as zero rows, 500
resamples with seed 20201018, percentile 95 % CI of the POOLED binary
Dice.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED = REPO_ROOT / "work/issue18/derived"
GRID = REPO_ROOT / "work/national/domain/cells_china_albers_W10000.csv"
V1_CANDIDATE = REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_candidate.csv"
V1_1_FROZEN = REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_1_core_frozen.csv"
OUT_DIR = REPO_ROOT / "datasets/manifests/2020_label_scale_audit_v2"

PAIR_DEFS_30 = (
    ("GEO_CMSA", "g", "bc", "gc"),
    ("GEO_CMSSM", "g", "bm", "gm"),
    ("CMSA_CMSSM", "bc", "bm", "cmb"),
)
PAIR_DEFS_10 = (("CMSA_CMSSM", "bc", "bm", "cmb"),)
SEED = 20201018
N_BOOT = 500
KINMEN = [
    "CNA10K-R00263-C00134",
    "CNA10K-R00264-C00134",
    "CNA10K-R00264-C00135",
    "CNA10K-R00264-C00136",
    "CNA10K-R00265-C00136",
]
OFFSHORE = [
    "CNA10K-R00231-C00093",
    "CNA10K-R00283-C00149",
    "CNA10K-R00314-C00162",
    "CNA10K-R00314-C00163",
    "CNA10K-R00316-C00163",
]


def _git_commit() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blocks(derived_csv: Path, status: pd.Series) -> pd.DataFrame:
    """Registry-status KEEP block table with zero-filled empty cells."""
    n = len(status)
    frame = pd.read_csv(derived_csv).set_index("cell_idx")
    frame = frame.reindex(np.arange(n)).fillna(0.0)
    frame["status"] = status.to_numpy()
    frame = frame[frame["status"].isin(("KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL"))]
    return frame.reset_index(drop=True)


def _bootstrap(
    cells: pd.DataFrame,
    pairs: tuple[tuple[str, str, str, str], ...],
    support: str,
    universe: str,
) -> list[dict[str, object]]:
    n_cells = len(cells)
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, n_cells, size=(N_BOOT, n_cells))
    rows: list[dict[str, object]] = []
    for pair, a_col, b_col, i_col in pairs:
        a = cells[a_col].to_numpy(dtype=np.float64)
        b = cells[b_col].to_numpy(dtype=np.float64)
        i = cells[i_col].to_numpy(dtype=np.float64)
        point = float(2.0 * i.sum() / (a.sum() + b.sum()))
        boots = np.array([2.0 * i[t].sum() / (a[t].sum() + b[t].sum()) for t in draws])
        lo = float(np.nanquantile(boots, 0.025))
        hi = float(np.nanquantile(boots, 0.975))
        rows.append(
            {
                "support": support,
                "pair": pair,
                "universe": universe,
                "spatial_blocks": n_cells,
                "pooled_dice": round(point, 4),
                "ci95_low": round(lo, 4),
                "ci95_high": round(hi, 4),
            }
        )
    return rows


def main() -> None:
    v1 = pd.read_csv(V1_CANDIDATE)[["cell_id", "membership_v1_candidate"]]
    v1_1 = pd.read_csv(V1_1_FROZEN)[["cell_id", "membership_v1_1"]]
    grid = pd.read_csv(GRID)[["cell_id"]]
    registry = grid.merge(v1, on="cell_id", how="left").merge(v1_1, on="cell_id")
    if len(registry) != 3319:
        raise AssertionError(f"expected 3,319 registry rows, got {len(registry)}")
    # Derived cell_idx values index the 3,021-cell domain universe
    # (KEEP + PROVISIONAL), in registry order -- mirror the report builder.
    dom = registry[
        registry["membership_v1_candidate"].isin(
            (
                "KEEP_MAINLAND_COASTAL",
                "KEEP_ISLAND_COASTAL",
                "PROVISIONAL_UNRESOLVED",
            )
        )
    ].reset_index(drop=True)
    if len(dom) != 3021:
        raise AssertionError(f"expected 3,021 domain rows, got {len(dom)}")

    rows: list[dict[str, object]] = []
    for tag, col, support, pairs, derived in (
        (
            "KEEP_ONLY_V1",
            "membership_v1_candidate",
            "30m_GEODATA_native_grid",
            PAIR_DEFS_30,
            DERIVED / "s30_cells.csv",
        ),
        (
            "KEEP_V1_1_CORE_FROZEN",
            "membership_v1_1",
            "30m_GEODATA_native_grid",
            PAIR_DEFS_30,
            DERIVED / "s30_cells.csv",
        ),
        (
            "KEEP_ONLY_V1",
            "membership_v1_candidate",
            "10m_project_lattice",
            PAIR_DEFS_10,
            DERIVED / "s10_cells.csv",
        ),
        (
            "KEEP_V1_1_CORE_FROZEN",
            "membership_v1_1",
            "10m_project_lattice",
            PAIR_DEFS_10,
            DERIVED / "s10_cells.csv",
        ),
    ):
        blocks = _blocks(derived, dom[col])
        rows.extend(_bootstrap(blocks, pairs, support, tag))

    table = pd.DataFrame(rows)
    deltas = []
    for (support, pair), grp in table.groupby(["support", "pair"], sort=False):
        old = grp.loc[grp.universe == "KEEP_ONLY_V1"].iloc[0]
        new = grp.loc[grp.universe == "KEEP_V1_1_CORE_FROZEN"].iloc[0]
        deltas.append(
            {
                "support": support,
                "pair": pair,
                "v1_3011_dice": old["pooled_dice"],
                "v1_1_3016_dice": new["pooled_dice"],
                "delta_dice": round(float(new["pooled_dice"]) - float(old["pooled_dice"]), 4),
            }
        )
    delta_frame = pd.DataFrame(deltas)
    out_csv = OUT_DIR / "table15_domain_v1_1_keep_effect.csv"
    table.to_csv(out_csv, index=False)

    # Added mapped area carried by the five promoted cells.  Four of the
    # five Kinmen cells and all five offshore cells are empty in the 2020
    # products; only the core Kinmen cell contributes pixels.
    s30 = pd.read_csv(DERIVED / "s30_cells.csv")
    s10 = pd.read_csv(DERIVED / "s10_cells.csv")
    promoted_idx = dom.index[dom.cell_id.isin(KINMEN)]
    added30 = s30[s30.cell_idx.isin(promoted_idx)][["g", "bc", "bm", "cmb", "gc", "gm"]].sum()
    added10 = s10[s10.cell_idx.isin(promoted_idx)][["bc", "bm", "cmb"]].sum()
    note = {
        "artifact": "table15_domain_v1_1_keep_effect_note",
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "method": (
            "Pooled binary Dice and W10-cell cluster bootstrap "
            "(500 resamples, seed 20201018) recomputed from the existing "
            "Issue #18 per-cell aggregates; no raster re-export. "
            "Universe KEEP_ONLY_V1 = 3,011 v1-candidate KEEP cells; "
            "KEEP_V1_1_CORE_FROZEN = 3,016 v1.1 frozen KEEP cells."
        ),
        "promoted_kinmen_cells": KINMEN,
        "remaining_provisional_offshore_cells": OFFSHORE,
        "added_30m_pixels": {k: int(v) for k, v in added30.items()},
        "added_30m_area_km2": {
            "GEO": round(float(added30["g"]) * 900 / 1e6, 4),
            "CMSA_binary": round(float(added30["bc"]) * 900 / 1e6, 4),
            "CMSSM_binary": round(float(added30["bm"]) * 900 / 1e6, 4),
        },
        "added_10m_pixels": {k: int(v) for k, v in added10.items()},
        "added_10m_area_km2": {
            "CMSA_binary": round(float(added10["bc"]) * 100 / 1e6, 4),
            "CMSSM_binary": round(float(added10["bm"]) * 100 / 1e6, 4),
        },
        "deltas": delta_frame.to_dict(orient="records"),
        "max_abs_delta_dice": float(delta_frame["delta_dice"].abs().max().round(4)),
        "source_checksums": {
            "s30_cells_csv": _sha256(DERIVED / "s30_cells.csv"),
            "s10_cells_csv": _sha256(DERIVED / "s10_cells.csv"),
            "v1_candidate_csv": _sha256(V1_CANDIDATE),
            "v1_1_core_frozen_csv": _sha256(V1_1_FROZEN),
        },
    }
    note_path = OUT_DIR / "table15_note_domain_v1_1.json"
    note_path.write_text(json.dumps(note, ensure_ascii=False, indent=2) + "\n")
    print(table.to_string(index=False))
    print(delta_frame.to_string(index=False))
    print(f"wrote {out_csv} and {note_path}")


if __name__ == "__main__":
    main()
