#!/usr/bin/env python3
"""Three-tier export volume estimate for the 10 km cell grid (M2.1a2).

ESTIMATE ONLY - no GEE export is triggered. Counts cell x event pairs from
the executed offline simulation and multiplies by documented per-pixel
byte assumptions. Numbers are planning bounds, not measured export sizes.

Tiers
-----
minimal  : M2.1b first controlled-production subset - SMB cells, 2023-2025,
           autumn_primary_v1 window, quality-passing events only.
standard : all 3 bays, 113 coastal cells, all census years, the two
           PROPOSED_NOT_FROZEN biological windows (autumn_primary_v1 +
           early_season_v1), quality-passing events only.
full     : every intersecting cell x event pair on every date, including
           cloud-rejected optical scenes (raw candidate archive).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402

# Planning assumptions (documented, not measured):
# Landsat: 6 SR-equivalent bands x uint16 + QA overhead (~1 B/px)
BYTES_PER_PIXEL = {
    "landsat5": 13,
    "landsat7": 13,
    "landsat8": 13,
    "landsat9": 13,
    # Sentinel-2: 4 x 10 m + 6 x 20 m bands x uint16, expressed at
    # 10 m-pixel equivalents, plus SCL (~20 B/px effective)
    "sentinel2": 20,
    # Sentinel-1: VV + VH float32
    "sentinel1": 8,
}
CELL_AREA_KM2 = 100.0
PIXELS_PER_CELL = {
    "landsat5": 111_111,   # 100 km^2 / 900 m^2
    "landsat7": 111_111,
    "landsat8": 111_111,
    "landsat9": 111_111,
    "sentinel2": 1_000_000,
    "sentinel1": 1_000_000,
}

WINDOWS_STANDARD = ("autumn_primary_v1", "early_season_v1")

# Nominal frame geometry only: L7 Extended Science Mission scenes
# (>= 2022-04, lower orbit) are excluded from the production tiers; they
# remain in the full candidate archive with their regime flag.
NOMINAL_REGIMES = (
    "NOMINAL_WRS_FRAME", "NOMINAL_MGRS_TILE",
    "REPRESENTATIVE_FRAME_PER_TRACK_VARIES")


def window_match(s: pd.Series, wid: str) -> pd.Series:
    return s.fillna("").str.contains(rf"(?:^|\|){wid}(?:\||$)", regex=True)


def estimate(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sensor, g in df.groupby("sensor"):
        n_events = len(g)
        n_cells = g.cell_id.nunique()
        n_cell_years = g[["cell_id", "year"]].drop_duplicates().shape[0]
        px = n_events * PIXELS_PER_CELL[sensor]
        gb = px * BYTES_PER_PIXEL[sensor] / 1e9
        rows.append({
            "sensor": sensor,
            "n_cell_event_pairs": n_events,
            "n_cells_touched": n_cells,
            "n_cell_years": n_cell_years,
            "pixels_estimate": px,
            "bytes_per_pixel_assumed": BYTES_PER_PIXEL[sensor],
            "gigabytes_estimate": round(gb, 2),
        })
    out = pd.DataFrame(rows).sort_values("sensor")
    total = {
        "sensor": "__TOTAL__",
        "n_cell_event_pairs": out.n_cell_event_pairs.sum(),
        "n_cells_touched": "",
        "n_cell_years": out.n_cell_years.sum(),
        "pixels_estimate": out.pixels_estimate.sum(),
        "bytes_per_pixel_assumed": "",
        "gigabytes_estimate": round(out.gigabytes_estimate.sum(), 2),
    }
    return pd.concat([out, pd.DataFrame([total])], ignore_index=True)


def main() -> int:
    pairs = pd.read_parquet(REPO_ROOT / "work/derived/zhejiang_cell_observations_v0.parquet")
    d = pairs[(pairs.cell_size_m == 10_000)].copy()

    tiers = {
        "minimal_m21b_first_subset": d[
            (d.bay_id == "ZJ-SMB")
            & d.year.between(2023, 2025)
            & window_match(d.window_ids, "autumn_primary_v1")
            & d.quality_pass
            & d.geometry_regime.isin(NOMINAL_REGIMES)],
        "standard_quality_biological_windows": d[
            d.quality_pass
            & d.geometry_regime.isin(NOMINAL_REGIMES)
            & (window_match(d.window_ids, WINDOWS_STANDARD[0])
               | window_match(d.window_ids, WINDOWS_STANDARD[1]))],
        "full_candidate_archive_all_dates": d[d.coverage_fraction > 0],
    }

    mdir = REPO_ROOT / "datasets/manifests"
    pieces = []
    for name, sub in tiers.items():
        est = estimate(sub)
        est.insert(0, "tier", name)
        pieces.append(est)
        print(f"\n== {name}: {len(sub)} pairs")
        print(est.to_string(index=False))
    out = pd.concat(pieces, ignore_index=True)
    out["cell_grid"] = "ZJ_U51_10K"
    out["estimate_basis"] = (
        "cell_event_pairs x pixels_per_cell x bytes_per_pixel; "
        "PLANNING_ESTIMATE_NOT_MEASURED; no export executed")
    out.to_csv(mdir / "zhejiang_export_volume_estimate_v0.csv", index=False)
    print("\n-> datasets/manifests/zhejiang_export_volume_estimate_v0.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
